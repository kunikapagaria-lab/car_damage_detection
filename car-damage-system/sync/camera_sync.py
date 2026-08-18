"""Multi-camera synchronized frame capture.

Uses a threading.Barrier so all camera threads commit their captures within a
100 ms window.  Falls back to plain OpenCV when GStreamer is unavailable.

Trigger modes
─────────────
  manual    — call CameraSynchronizer.capture_synchronized() directly
              (also exposed via POST /api/v1/inspect/trigger)
  automatic — VehicleDetector (see vehicle_detector.py) calls trigger_event.set()
  scheduled — APScheduler cron job calls capture_synchronized() on a timetable
"""

from __future__ import annotations

import threading
import time
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import cv2
import numpy as np
import structlog
import yaml
from apscheduler.schedulers.background import BackgroundScheduler

logger = structlog.get_logger(__name__)

# ── GStreamer detection ───────────────────────────────────────────────────────

try:
    import gi  # type: ignore[import]
    gi.require_version("Gst", "1.0")
    from gi.repository import Gst  # type: ignore[import]
    Gst.init(None)
    _GSTREAMER = True
except Exception:
    _GSTREAMER = False

logger.info("camera_backend_selected", gstreamer=_GSTREAMER)

SYNC_TIMEOUT_S = 0.100  # 100 ms
MAX_RETRIES = 3


# ── GStreamer pipeline builder ─────────────────────────────────────────────────

def _gst_pipeline(rtsp_url: str) -> str:
    return (
        f"rtspsrc location={rtsp_url} latency=0 ! "
        "rtph264depay ! h264parse ! avdec_h264 ! "
        "videoconvert ! video/x-raw,format=BGR ! "
        "appsink max-buffers=1 drop=true sync=false"
    )


# ── Per-camera worker ─────────────────────────────────────────────────────────

class CameraWorker:
    """Continuous capture loop for one camera.

    When trigger_event is set the worker captures one frame, stores it, and
    waits at the synchronization barrier.  After each barrier pass it resets
    its local state and loops.
    """

    def __init__(
        self,
        camera_id: str,
        angle: str,
        rtsp_url: str,
        trigger_event: threading.Event,
        barrier: threading.Barrier,
        results: dict[str, np.ndarray],
        results_lock: threading.Lock,
        stop_event: threading.Event,
    ) -> None:
        self.camera_id = camera_id
        self.angle = angle
        self.rtsp_url = rtsp_url
        self._trigger = trigger_event
        self._barrier = barrier
        self._results = results
        self._results_lock = results_lock
        self._stop = stop_event
        self.connected = False
        self.frames_captured = 0
        self._cap: cv2.VideoCapture | None = None

    def _open_capture(self) -> cv2.VideoCapture:
        if _GSTREAMER:
            cap = cv2.VideoCapture(_gst_pipeline(self.rtsp_url), cv2.CAP_GSTREAMER)
        else:
            cap = cv2.VideoCapture(self.rtsp_url, cv2.CAP_FFMPEG)
        cap.set(cv2.CAP_PROP_BUFFERSIZE, 1)
        return cap

    def run(self) -> None:
        logger.info("camera_worker_started", id=self.camera_id, angle=self.angle)
        reconnect_interval = 5.0

        while not self._stop.is_set():
            cap = self._open_capture()
            if not cap.isOpened():
                logger.warning("camera_connect_failed", id=self.camera_id)
                self.connected = False
                if self._stop.wait(reconnect_interval):
                    break
                continue

            self.connected = True
            logger.info("camera_connected", id=self.camera_id)

            while not self._stop.is_set():
                # Wait for a trigger (or stop)
                triggered = self._trigger.wait(timeout=0.05)
                if not triggered:
                    # Keep the capture alive by reading and discarding frames
                    cap.grab()
                    continue

                # Capture immediately
                ok, frame = cap.read()
                if not ok:
                    logger.error("camera_read_failed", id=self.camera_id)
                    self.connected = False
                    break  # reconnect

                with self._results_lock:
                    self._results[self.angle] = frame

                self.frames_captured += 1

                # Meet the barrier; timeout counts as a miss
                try:
                    self._barrier.wait(timeout=SYNC_TIMEOUT_S)
                except threading.BrokenBarrierError:
                    logger.warning("camera_barrier_timeout", id=self.camera_id)

            cap.release()
            if not self._stop.is_set():
                if self._stop.wait(reconnect_interval):
                    break

        logger.info("camera_worker_stopped", id=self.camera_id)


# ── Synchronizer ──────────────────────────────────────────────────────────────

class CameraSynchronizer:
    """Coordinates all camera workers and exposes capture_synchronized()."""

    def __init__(self, config_path: str = "config/cameras.yaml") -> None:
        with open(config_path) as fh:
            cfg = yaml.safe_load(fh)

        self._cameras: list[dict[str, Any]] = [
            c for c in cfg.get("cameras", []) if c.get("enabled", True)
        ]
        self._settings: dict[str, Any] = cfg.get("settings", {})

        n = len(self._cameras)
        # Barrier: n cameras + 1 coordinator thread
        self._barrier = threading.Barrier(n + 1)
        self._trigger = threading.Event()
        self._results: dict[str, np.ndarray] = {}
        self._results_lock = threading.Lock()
        self._stop = threading.Event()
        self._workers: list[CameraWorker] = []
        self._executor: ThreadPoolExecutor | None = None
        self._scheduler: BackgroundScheduler | None = None

    # ── Lifecycle ─────────────────────────────────────────────────────────────

    def start(self) -> None:
        self._executor = ThreadPoolExecutor(
            max_workers=len(self._cameras) + 2,
            thread_name_prefix="cam_sync",
        )
        for cam in self._cameras:
            w = CameraWorker(
                camera_id=cam["id"],
                angle=cam["angle"],
                rtsp_url=cam["rtsp_url"],
                trigger_event=self._trigger,
                barrier=self._barrier,
                results=self._results,
                results_lock=self._results_lock,
                stop_event=self._stop,
            )
            self._workers.append(w)
            self._executor.submit(w.run)

        logger.info("synchronizer_started", camera_count=len(self._cameras))

    def stop(self) -> None:
        self._stop.set()
        self._trigger.set()  # unblock any waiting workers
        if self._scheduler:
            self._scheduler.shutdown(wait=False)
        if self._executor:
            self._executor.shutdown(wait=True, cancel_futures=False)
        logger.info("synchronizer_stopped")

    # ── Scheduled capture ─────────────────────────────────────────────────────

    def enable_scheduled_capture(
        self,
        cron_expr: str,
        on_capture: Any,
    ) -> None:
        """Enable cron-triggered captures. on_capture(frames) is called each time."""
        self._scheduler = BackgroundScheduler(timezone="UTC")
        cron_parts = cron_expr.split()
        self._scheduler.add_job(
            lambda: on_capture(self.capture_synchronized()),
            "cron",
            minute=cron_parts[0] if len(cron_parts) > 0 else "*",
            hour=cron_parts[1] if len(cron_parts) > 1 else "*",
        )
        self._scheduler.start()
        logger.info("scheduled_capture_enabled", cron=cron_expr)

    # ── Synchronized capture ──────────────────────────────────────────────────

    def capture_synchronized(self) -> dict[str, np.ndarray]:
        """Trigger all cameras and collect frames within the 100 ms window.

        Retries up to MAX_RETRIES times before raising RuntimeError.
        Returns mapping of camera_angle → BGR numpy array.
        """
        for attempt in range(1, MAX_RETRIES + 1):
            with self._results_lock:
                self._results.clear()

            self._barrier.reset()
            self._trigger.set()

            try:
                # Coordinator waits at the barrier too
                self._barrier.wait(timeout=SYNC_TIMEOUT_S + 0.020)
            except threading.BrokenBarrierError:
                logger.warning(
                    "sync_capture_timeout",
                    attempt=attempt,
                    captured=len(self._results),
                    expected=len(self._cameras),
                )
            finally:
                self._trigger.clear()

            with self._results_lock:
                frames = dict(self._results)

            if len(frames) == len(self._cameras):
                logger.info(
                    "sync_capture_success",
                    attempt=attempt,
                    angles=list(frames.keys()),
                )
                return frames

            if attempt < MAX_RETRIES:
                time.sleep(0.080)

        raise RuntimeError(
            f"Synchronized capture failed after {MAX_RETRIES} attempts — "
            f"only {len(frames)}/{len(self._cameras)} cameras responded"
        )

    def get_status(self) -> dict[str, Any]:
        return {
            w.angle: {
                "camera_id": w.camera_id,
                "connected": w.connected,
                "frames_captured": w.frames_captured,
            }
            for w in self._workers
        }

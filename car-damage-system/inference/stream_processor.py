"""Real multi-camera RTSP stream processor using OpenCV.

Each camera runs in its own thread. Frames are deduplicated by MD5 hash
and filtered by frame-diff to avoid processing static scenes.
"""

from __future__ import annotations

import asyncio
import hashlib
import os
import signal
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any

import cv2
import numpy as np
import structlog
import yaml

logger = structlog.get_logger(__name__)

_RECONNECT_INTERVAL = float(os.environ.get("RECONNECT_INTERVAL_SECONDS", "5"))
_FRAME_DIFF_THRESHOLD = float(os.environ.get("FRAME_DIFF_THRESHOLD", "8.0"))


@dataclass
class CameraConfig:
    id: str
    angle: str
    rtsp_url: str
    resolution: list[int]
    fps: int
    enabled: bool


@dataclass
class StreamStatus:
    connected: bool
    fps: float
    frames_processed: int
    last_frame_at: datetime | None


class _CameraWorker:
    """Runs a single camera's capture loop in a background thread."""

    def __init__(
        self,
        cam: CameraConfig,
        queue: asyncio.Queue,
        loop: asyncio.AbstractEventLoop,
        diff_threshold: float,
        process_every_nth: int,
    ) -> None:
        self._cam = cam
        self._queue = queue
        self._loop = loop
        self._diff_threshold = diff_threshold
        self._process_every_nth = process_every_nth
        self._stop_event = threading.Event()

        self.connected = False
        self.frames_processed = 0
        self._fps = 0.0
        self.last_frame_at: datetime | None = None
        self._last_hash: str = ""
        self._last_frame: np.ndarray | None = None
        self._frame_counter = 0
        self._fps_window_start = time.monotonic()
        self._fps_frame_count = 0

    def stop(self) -> None:
        self._stop_event.set()

    @property
    def fps(self) -> float:
        return self._fps

    def status(self) -> StreamStatus:
        return StreamStatus(
            connected=self.connected,
            fps=round(self._fps, 2),
            frames_processed=self.frames_processed,
            last_frame_at=self.last_frame_at,
        )

    def run(self) -> None:
        cam = self._cam
        logger.info("camera_thread_started", camera_id=cam.id, angle=cam.angle)

        while not self._stop_event.is_set():
            cap = cv2.VideoCapture(cam.rtsp_url, cv2.CAP_FFMPEG)
            cap.set(cv2.CAP_PROP_BUFFERSIZE, 1)

            if not cap.isOpened():
                logger.warning(
                    "camera_connect_failed",
                    camera_id=cam.id,
                    rtsp_url=cam.rtsp_url,
                )
                self.connected = False
                cap.release()
                self._stop_event.wait(_RECONNECT_INTERVAL)
                continue

            self.connected = True
            logger.info("camera_connected", camera_id=cam.id)

            while not self._stop_event.is_set():
                ok, frame = cap.read()
                if not ok:
                    logger.error("camera_read_failed", camera_id=cam.id)
                    self.connected = False
                    break

                self._frame_counter += 1
                if self._frame_counter % self._process_every_nth != 0:
                    continue

                frame_hash = hashlib.md5(frame.tobytes()).hexdigest()
                if frame_hash == self._last_hash:
                    continue

                if self._last_frame is not None:
                    diff = float(np.mean(np.abs(frame.astype(np.float32) - self._last_frame.astype(np.float32))))
                    if diff < self._diff_threshold:
                        self._last_hash = frame_hash
                        continue

                self._last_hash = frame_hash
                self._last_frame = frame.copy()
                self.last_frame_at = datetime.now(timezone.utc)
                self.frames_processed += 1

                self._fps_frame_count += 1
                elapsed = time.monotonic() - self._fps_window_start
                if elapsed >= 5.0:
                    self._fps = self._fps_frame_count / elapsed
                    self._fps_frame_count = 0
                    self._fps_window_start = time.monotonic()

                from inference.base_predictor import CameraFrame
                cf = CameraFrame(
                    camera_id=cam.id,
                    angle=cam.angle,
                    frame_np=frame.copy(),
                    captured_at=self.last_frame_at,
                    frame_hash=frame_hash,
                )

                try:
                    asyncio.run_coroutine_threadsafe(self._enqueue(cf), self._loop)
                except RuntimeError:
                    pass

            cap.release()
            if not self._stop_event.is_set():
                logger.warning("camera_reconnecting", camera_id=cam.id)
                self._stop_event.wait(_RECONNECT_INTERVAL)

        logger.info("camera_thread_stopped", camera_id=cam.id)

    async def _enqueue(self, frame: Any) -> None:
        try:
            self._queue.put_nowait(frame)
        except asyncio.QueueFull:
            logger.warning("frame_queue_full", camera_id=self._cam.id)


class StreamProcessor:
    """Manages all camera worker threads and exposes a frame output queue."""

    def __init__(self, cameras_config_path: str, output_queue: asyncio.Queue) -> None:
        self._config_path = cameras_config_path
        self._queue = output_queue
        self._cameras: list[CameraConfig] = []
        self._workers: list[_CameraWorker] = []
        self._executor: ThreadPoolExecutor | None = None
        self._loop: asyncio.AbstractEventLoop | None = None
        self._stop_event = threading.Event()
        self._stats_thread: threading.Thread | None = None
        self._settings: dict[str, Any] = {}
        self._load_config()

    def _load_config(self) -> None:
        with open(self._config_path, "r") as fh:
            data = yaml.safe_load(fh)
        self._cameras = [
            CameraConfig(**cam) for cam in data.get("cameras", []) if cam.get("enabled", True)
        ]
        self._settings = data.get("settings", {})
        logger.info("cameras_config_loaded", count=len(self._cameras))

    def start(self) -> None:
        self._loop = asyncio.get_event_loop()
        diff_threshold = float(self._settings.get("frame_diff_threshold", _FRAME_DIFF_THRESHOLD))
        process_every_nth = int(self._settings.get("process_every_nth_frame", 3))

        self._executor = ThreadPoolExecutor(
            max_workers=len(self._cameras) + 1,
            thread_name_prefix="cam_worker",
        )

        for cam in self._cameras:
            worker = _CameraWorker(
                cam=cam,
                queue=self._queue,
                loop=self._loop,
                diff_threshold=diff_threshold,
                process_every_nth=process_every_nth,
            )
            self._workers.append(worker)
            self._executor.submit(worker.run)

        self._stats_thread = threading.Thread(
            target=self._log_stats_loop, daemon=True, name="stream_stats"
        )
        self._stats_thread.start()

        signal.signal(signal.SIGTERM, self._handle_sigterm)
        logger.info("stream_processor_started", camera_count=len(self._cameras))

    def stop(self) -> None:
        self._stop_event.set()
        for worker in self._workers:
            worker.stop()
        if self._executor:
            self._executor.shutdown(wait=True, cancel_futures=False)
        logger.info("stream_processor_stopped")

    def get_status(self) -> dict[str, Any]:
        return {
            cam.id: {
                "angle": cam.angle,
                **vars(self._workers[i].status()),
            }
            for i, cam in enumerate(self._cameras)
        }

    def _log_stats_loop(self) -> None:
        while not self._stop_event.wait(60):
            for i, cam in enumerate(self._cameras):
                s = self._workers[i].status()
                logger.info(
                    "camera_stats",
                    camera_id=cam.id,
                    connected=s.connected,
                    fps=s.fps,
                    frames_processed=s.frames_processed,
                )

    def _handle_sigterm(self, signum: int, frame: Any) -> None:
        logger.info("sigterm_received")
        self.stop()

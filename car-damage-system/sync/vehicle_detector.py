"""Vehicle presence detector for the front camera.

Uses OpenCV MOG2 background subtraction to detect when a vehicle has
entered the inspection bay.

Trigger logic
─────────────
  • Foreground pixel ratio > TRIGGER_RATIO (0.15) for TRIGGER_FRAMES (3)
    consecutive frames → trigger inspection.
  • After trigger: 30-second debounce (re-triggers ignored).
  • Foreground ratio < RESET_RATIO (0.05) → background model is reset
    (vehicle has left).
"""

from __future__ import annotations

import threading
import time
from collections import deque
from typing import Any, Callable

import cv2
import numpy as np
import structlog

logger = structlog.get_logger(__name__)

TRIGGER_RATIO = 0.15       # foreground fraction that indicates a vehicle
RESET_RATIO = 0.05         # fraction below which bay is considered empty
TRIGGER_FRAMES = 3         # consecutive frames above threshold to trigger
DEBOUNCE_SECONDS = 30.0    # minimum time between consecutive triggers
MOG2_HISTORY = 200
MOG2_THRESHOLD = 40
MOG2_DETECT_SHADOWS = True


class VehicleDetector:
    """Runs in its own thread, continuously analysing front-camera frames."""

    def __init__(
        self,
        on_vehicle_detected: Callable[[], None],
        rtsp_url: str,
    ) -> None:
        self._on_detected = on_vehicle_detected
        self._rtsp_url = rtsp_url
        self._stop = threading.Event()
        self._last_trigger_time: float = 0.0
        self._consecutive_hits: int = 0
        self._bay_occupied: bool = False
        self._bg_sub = self._make_subtractor()
        self._thread: threading.Thread | None = None

    @staticmethod
    def _make_subtractor() -> cv2.BackgroundSubtractorMOG2:
        return cv2.createBackgroundSubtractorMOG2(
            history=MOG2_HISTORY,
            varThreshold=MOG2_THRESHOLD,
            detectShadows=MOG2_DETECT_SHADOWS,
        )

    def _fg_ratio(self, frame: np.ndarray) -> float:
        """Return the fraction of pixels classified as foreground."""
        mask = self._bg_sub.apply(frame)
        # Shadows are marked as 127; treat as background
        fg_pixels = np.sum(mask == 255)
        total = mask.size
        return fg_pixels / total if total > 0 else 0.0

    def _process_frame(self, frame: np.ndarray) -> None:
        ratio = self._fg_ratio(frame)
        now = time.monotonic()

        if ratio > TRIGGER_RATIO:
            self._consecutive_hits += 1
            if (
                self._consecutive_hits >= TRIGGER_FRAMES
                and not self._bay_occupied
                and (now - self._last_trigger_time) > DEBOUNCE_SECONDS
            ):
                self._bay_occupied = True
                self._last_trigger_time = now
                logger.info(
                    "vehicle_detected",
                    fg_ratio=round(ratio, 4),
                    consecutive_hits=self._consecutive_hits,
                )
                try:
                    self._on_detected()
                except Exception as exc:
                    logger.error("trigger_callback_failed", error=str(exc))
        else:
            self._consecutive_hits = 0

        if self._bay_occupied and ratio < RESET_RATIO:
            logger.info("vehicle_left_bay", fg_ratio=round(ratio, 4))
            self._bay_occupied = False
            self._bg_sub = self._make_subtractor()

    def _run(self) -> None:
        reconnect_wait = 5.0
        while not self._stop.is_set():
            cap = cv2.VideoCapture(self._rtsp_url, cv2.CAP_FFMPEG)
            cap.set(cv2.CAP_PROP_BUFFERSIZE, 1)

            if not cap.isOpened():
                logger.warning("vehicle_detector_connect_failed", url=self._rtsp_url)
                if self._stop.wait(reconnect_wait):
                    break
                continue

            logger.info("vehicle_detector_connected")
            while not self._stop.is_set():
                ok, frame = cap.read()
                if not ok:
                    logger.error("vehicle_detector_read_failed")
                    break
                self._process_frame(frame)

            cap.release()
            if not self._stop.is_set():
                if self._stop.wait(reconnect_wait):
                    break

        logger.info("vehicle_detector_stopped")

    def start(self) -> None:
        self._thread = threading.Thread(
            target=self._run, daemon=True, name="vehicle_detector"
        )
        self._thread.start()
        logger.info("vehicle_detector_started", rtsp_url=self._rtsp_url)

    def stop(self) -> None:
        self._stop.set()
        if self._thread:
            self._thread.join(timeout=10)

    @property
    def bay_occupied(self) -> bool:
        return self._bay_occupied

    @property
    def last_trigger_time(self) -> float:
        return self._last_trigger_time

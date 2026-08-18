"""Real EasyOCR-based license plate recognition for Indian plates.

Lazy-loads EasyOCR on first call. Thread-safe via internal lock.
Handles low-contrast plates with CLAHE enhancement fallback.
"""

from __future__ import annotations

import re
import threading
from typing import Any

import cv2
import numpy as np
import structlog

from inference.base_predictor import PlateResult

logger = structlog.get_logger(__name__)

_PLATE_PATTERN = re.compile(r"^[A-Z]{2}[0-9]{1,2}[A-Z]{1,3}[0-9]{4}$")
_MIN_CONFIDENCE = 0.70

_reader_lock = threading.Lock()
_reader: Any = None


def _normalize_text(text: str) -> str:
    cleaned = re.sub(r"[^A-Z0-9]", "", text.upper())
    return cleaned


def _get_reader() -> Any:
    global _reader
    if _reader is not None:
        return _reader
    with _reader_lock:
        if _reader is None:
            import easyocr
            import os
            langs = os.environ.get("LPR_LANGUAGES", "en").split(",")
            _reader = easyocr.Reader(langs, gpu=False, verbose=False)
            logger.info("easyocr_reader_initialized", languages=langs)
    return _reader


def warmup_lpr() -> None:
    """Pre-load EasyOCR model at startup to avoid cold-start delay on first request."""
    try:
        _get_reader()
        logger.info("lpr_warmup_complete")
    except Exception as exc:
        logger.warning("lpr_warmup_failed", error=str(exc))


def _run_ocr(image: np.ndarray) -> list[tuple[str, float, list[int]]]:
    """Run EasyOCR and return list of (text, confidence, bbox) tuples."""
    reader = _get_reader()
    with _reader_lock:
        raw = reader.readtext(image, detail=1, paragraph=False)

    results = []
    for detection in raw:
        bbox_pts, text, conf = detection
        xs = [int(p[0]) for p in bbox_pts]
        ys = [int(p[1]) for p in bbox_pts]
        bbox = [min(xs), min(ys), max(xs), max(ys)]
        normalized = _normalize_text(text)
        results.append((normalized, float(conf), bbox))
    return results


def _best_plate(
    candidates: list[tuple[str, float, list[int]]]
) -> tuple[str, float, list[int]] | None:
    matches = [c for c in candidates if _PLATE_PATTERN.match(c[0])]
    if not matches:
        return None
    return max(matches, key=lambda c: c[1])


def detect_plate(image: np.ndarray) -> PlateResult | None:
    """Detect and return the best Indian license plate in the image, or None."""
    retries = 0
    try:
        candidates = _run_ocr(image)
        best = _best_plate(candidates)

        if best and best[1] >= _MIN_CONFIDENCE:
            logger.info(
                "plate_detected",
                plate=best[0],
                confidence=round(best[1], 4),
                retries=retries,
            )
            return PlateResult(plate_text=best[0], confidence=best[1], bbox=best[2])

        retries += 1
        gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
        gray_bgr = cv2.cvtColor(gray, cv2.COLOR_GRAY2BGR)
        candidates = _run_ocr(gray_bgr)
        best = _best_plate(candidates)
        if best and best[1] >= _MIN_CONFIDENCE:
            logger.info(
                "plate_detected",
                plate=best[0],
                confidence=round(best[1], 4),
                retries=retries,
            )
            return PlateResult(plate_text=best[0], confidence=best[1], bbox=best[2])

        retries += 1
        clahe = cv2.createCLAHE(clipLimit=2.0, tileGridSize=(8, 8))
        enhanced = clahe.apply(gray)
        enhanced_bgr = cv2.cvtColor(enhanced, cv2.COLOR_GRAY2BGR)
        candidates = _run_ocr(enhanced_bgr)
        best = _best_plate(candidates)
        if best and best[1] >= _MIN_CONFIDENCE:
            logger.info(
                "plate_detected",
                plate=best[0],
                confidence=round(best[1], 4),
                retries=retries,
            )
            return PlateResult(plate_text=best[0], confidence=best[1], bbox=best[2])

        logger.info("plate_not_found", retries=retries)
        return None

    except Exception as exc:
        logger.error("lpr_error", error=str(exc))
        return None

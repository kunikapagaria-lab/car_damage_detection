"""Dummy predictor that simulates Detectron2 output with random but realistic detections.

Identical output structure to the real Detectron2 predictor.
Seeded by image content hash for reproducibility.
No ML dependencies — runs on any machine.
"""

from __future__ import annotations

import base64
import hashlib
import io
import os
import random
import threading
import time
from typing import Any

import cv2
import numpy as np
import structlog
from PIL import Image

from inference.base_predictor import BasePredictor, DamageResult, PredictorConfig

logger = structlog.get_logger(__name__)

DAMAGE_CLASSES = ["scratch", "dent", "paint_damage", "crack"]
CLASS_WEIGHTS = [0.40, 0.25, 0.25, 0.10]
COUNT_WEIGHTS = [0.15, 0.30, 0.30, 0.15, 0.10]  # 0–4 detections

_LATENCY_MS = float(os.environ.get("DUMMY_INFERENCE_LATENCY_MS", "80"))


def _shoelace_area(points: list[list[int]]) -> float:
    """Compute polygon area via the shoelace formula."""
    n = len(points)
    if n < 3:
        return 0.0
    area = 0.0
    for i in range(n):
        j = (i + 1) % n
        area += points[i][0] * points[j][1]
        area -= points[j][0] * points[i][1]
    return abs(area) / 2.0


def _bbox_to_polygon(
    x1: int, y1: int, x2: int, y2: int, rng: random.Random
) -> list[list[int]]:
    """Convert bbox corners to an 8-point polygon with ±8px jitter at midpoints."""
    mx = (x1 + x2) // 2
    my = (y1 + y2) // 2

    def jitter(v: int, lo: int, hi: int) -> int:
        return int(max(lo, min(hi, v + rng.randint(-8, 8))))

    return [
        [x1, y1],
        [jitter(mx, x1, x2), jitter(y1, y1, y2)],
        [x2, y1],
        [jitter(x2, x1, x2), jitter(my, y1, y2)],
        [x2, y2],
        [jitter(mx, x1, x2), jitter(y2, y1, y2)],
        [x1, y2],
        [jitter(x1, x1, x2), jitter(my, y1, y2)],
    ]


def _crop_b64(image: np.ndarray, x1: int, y1: int, x2: int, y2: int, padding: int) -> str:
    """Crop image at bbox+padding and return base64-encoded PNG string."""
    h, w = image.shape[:2]
    cx1 = max(0, x1 - padding)
    cy1 = max(0, y1 - padding)
    cx2 = min(w, x2 + padding)
    cy2 = min(h, y2 + padding)
    crop = image[cy1:cy2, cx1:cx2]
    rgb = cv2.cvtColor(crop, cv2.COLOR_BGR2RGB)
    pil_img = Image.fromarray(rgb)
    buf = io.BytesIO()
    pil_img.save(buf, format="PNG")
    return base64.b64encode(buf.getvalue()).decode("utf-8")


class DummyPredictor(BasePredictor):
    """Simulates Detectron2 damage detection without any ML dependencies."""

    def __init__(self, config: PredictorConfig) -> None:
        super().__init__(config)
        self._lock = threading.Lock()
        self._total_inferences = 0
        self._total_latency_ms = 0.0

    def warmup(self) -> None:
        blank = np.zeros((480, 640, 3), dtype=np.uint8)
        self.predict(blank)
        logger.info("dummy_predictor_warmup_complete")

    def predict(self, image: np.ndarray) -> list[DamageResult]:
        t0 = time.monotonic()

        img_hash = hashlib.md5(image.tobytes()).hexdigest()
        seed = int(img_hash[:8], 16)
        rng = random.Random(seed)

        n_detections = rng.choices(range(5), weights=COUNT_WEIGHTS, k=1)[0]

        h, w = image.shape[:2]
        results: list[DamageResult] = []

        for _ in range(n_detections):
            class_name = rng.choices(DAMAGE_CLASSES, weights=CLASS_WEIGHTS, k=1)[0]
            confidence = round(rng.uniform(
                max(self.config.score_threshold, 0.45), 0.97
            ), 4)

            max_bw = max(40, int(w * 0.30))
            max_bh = max(40, int(h * 0.30))
            bw = rng.randint(40, max_bw)
            bh = rng.randint(40, max_bh)
            x1 = rng.randint(0, max(0, w - bw - 1))
            y1 = rng.randint(0, max(0, h - bh - 1))
            x2 = x1 + bw
            y2 = y1 + bh

            polygon = _bbox_to_polygon(x1, y1, x2, y2, rng)
            area_px = int(_shoelace_area(polygon))
            area_pct = round(area_px / (h * w) * 100, 4)

            crop = _crop_b64(image, x1, y1, x2, y2, self.config.crop_padding_px)

            results.append(DamageResult(
                annotation_id=DamageResult.new_id(),
                class_name=class_name,
                confidence=confidence,
                bbox_xyxy=[x1, y1, x2, y2],
                polygon_points=polygon,
                mask_area_px=area_px,
                mask_area_pct=area_pct,
                crop_b64=crop,
            ))

        time.sleep(_LATENCY_MS / 1000.0)
        latency = (time.monotonic() - t0) * 1000.0

        with self._lock:
            self._total_inferences += 1
            self._total_latency_ms += latency

        logger.info(
            "dummy_prediction",
            image_shape=image.shape,
            n_detections=len(results),
            latency_ms=round(latency, 2),
        )
        return results

    def get_info(self) -> dict[str, Any]:
        info = super().get_info()
        with self._lock:
            avg = (
                self._total_latency_ms / self._total_inferences
                if self._total_inferences > 0
                else 0.0
            )
            info.update({
                "mode": "dummy",
                "total_inferences": self._total_inferences,
                "avg_latency_ms": round(avg, 2),
            })
        return info

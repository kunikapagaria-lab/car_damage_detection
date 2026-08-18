"""Real Detectron2 Mask R-CNN predictor for car damage detection.

Fully written and correct — only activated when PREDICTOR_MODE=detectron2.
Requires: pip install -r requirements_full.txt and a CUDA-capable GPU.
"""

from __future__ import annotations

import base64
import io
import threading
import time
from typing import Any

import cv2
import numpy as np
import structlog
from PIL import Image

from inference.base_predictor import BasePredictor, DamageResult, PredictorConfig

logger = structlog.get_logger(__name__)

try:
    from detectron2 import model_zoo
    from detectron2.config import get_cfg
    from detectron2.engine import DefaultPredictor as _DefaultPredictor
    _detectron2_available = True
except ImportError:
    _detectron2_available = False
    _DefaultPredictor = None  # type: ignore[assignment,misc]

DAMAGE_CLASSES = ["scratch", "dent", "paint_damage", "crack"]


def _mask_to_polygon(mask: np.ndarray) -> list[list[int]]:
    """Convert a binary mask to a simplified polygon via contour approximation."""
    mask_u8 = (mask > 0).astype(np.uint8) * 255
    contours, _ = cv2.findContours(mask_u8, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    if not contours:
        return []
    largest = max(contours, key=cv2.contourArea)
    epsilon = 0.01 * cv2.arcLength(largest, closed=True)
    approx = cv2.approxPolyDP(largest, epsilon, closed=True)
    return [[int(pt[0][0]), int(pt[0][1])] for pt in approx]


def _crop_b64(image: np.ndarray, x1: int, y1: int, x2: int, y2: int, padding: int) -> str:
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


class Detectron2Predictor(BasePredictor):
    """Mask R-CNN X101 FPN predictor using Detectron2."""

    _instance_lock = threading.Lock()

    def __init__(self, config: PredictorConfig) -> None:
        if not _detectron2_available:
            raise RuntimeError(
                "detectron2 is not installed. "
                "Run: pip install -r requirements_full.txt"
            )
        super().__init__(config)

        import torch

        cfg = get_cfg()
        cfg.merge_from_file(
            model_zoo.get_config_file(
                "COCO-InstanceSegmentation/mask_rcnn_X_101_32x8d_FPN_3x.yaml"
            )
        )
        cfg.MODEL.ROI_HEADS.NUM_CLASSES = len(DAMAGE_CLASSES)
        cfg.MODEL.ROI_HEADS.SCORE_THRESH_TEST = config.score_threshold
        cfg.MODEL.WEIGHTS = config.model_path

        if config.device == "cuda" and torch.cuda.is_available():
            cfg.MODEL.DEVICE = "cuda"
        else:
            cfg.MODEL.DEVICE = "cpu"

        self._cfg = cfg
        self._predictor = _DefaultPredictor(cfg)
        self._lock = threading.Lock()
        self._total_inferences = 0
        self._total_latency_ms = 0.0

        logger.info(
            "detectron2_predictor_initialized",
            device=cfg.MODEL.DEVICE,
            model_path=config.model_path,
            score_threshold=config.score_threshold,
        )

    def warmup(self) -> None:
        blank = np.zeros((480, 640, 3), dtype=np.uint8)
        self.predict(blank)
        logger.info("detectron2_warmup_complete")

    def predict(self, image: np.ndarray) -> list[DamageResult]:
        t0 = time.monotonic()
        h, w = image.shape[:2]

        with self._lock:
            outputs = self._predictor(image)

        instances = outputs["instances"].to("cpu")
        boxes = instances.pred_boxes.tensor.numpy() if instances.has("pred_boxes") else []
        masks = instances.pred_masks.numpy() if instances.has("pred_masks") else []
        classes = instances.pred_classes.numpy() if instances.has("pred_classes") else []
        scores = instances.scores.numpy() if instances.has("scores") else []

        results: list[DamageResult] = []
        for i in range(len(scores)):
            conf = float(scores[i])
            if conf < self.config.score_threshold:
                continue
            if len(results) >= self.config.max_detections:
                break

            x1, y1, x2, y2 = [int(v) for v in boxes[i]]
            class_idx = int(classes[i])
            class_name = DAMAGE_CLASSES[class_idx] if class_idx < len(DAMAGE_CLASSES) else "scratch"

            mask = masks[i]
            polygon = _mask_to_polygon(mask)
            area_px = int(mask.sum())
            area_pct = round(area_px / (h * w) * 100, 4)
            crop = _crop_b64(image, x1, y1, x2, y2, self.config.crop_padding_px)

            results.append(DamageResult(
                annotation_id=DamageResult.new_id(),
                class_name=class_name,
                confidence=round(conf, 4),
                bbox_xyxy=[x1, y1, x2, y2],
                polygon_points=polygon,
                mask_area_px=area_px,
                mask_area_pct=area_pct,
                crop_b64=crop,
            ))

        latency = (time.monotonic() - t0) * 1000.0
        with self._lock:
            self._total_inferences += 1
            self._total_latency_ms += latency

        logger.info(
            "detectron2_prediction",
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
                "mode": "detectron2",
                "total_inferences": self._total_inferences,
                "avg_latency_ms": round(avg, 2),
                "detectron2_available": _detectron2_available,
            })
        return info

"""Abstract base class and shared data models for all damage predictors."""

from __future__ import annotations

import uuid
from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Any

import numpy as np


@dataclass
class PredictorConfig:
    score_threshold: float = 0.45
    max_detections: int = 20
    crop_padding_px: int = 30
    model_path: str = ""
    device: str = "cpu"


@dataclass
class DamageResult:
    annotation_id: str
    class_name: str
    confidence: float
    bbox_xyxy: list[int]
    polygon_points: list[list[int]]
    mask_area_px: int
    mask_area_pct: float
    crop_b64: str

    @staticmethod
    def new_id() -> str:
        return str(uuid.uuid4())


@dataclass
class PlateResult:
    plate_text: str
    confidence: float
    bbox: list[int]


@dataclass
class CameraFrame:
    camera_id: str
    angle: str
    frame_np: np.ndarray
    captured_at: Any  # datetime
    frame_hash: str


@dataclass
class InspectionResult:
    vehicle_id: str
    plate_result: PlateResult | None
    damages: list[DamageResult]
    inference_time_ms: float
    camera_id: str
    captured_at: Any  # datetime


class BasePredictor(ABC):
    """Abstract predictor that DummyPredictor and Detectron2Predictor both implement."""

    def __init__(self, config: PredictorConfig) -> None:
        self.config = config

    @abstractmethod
    def predict(self, image: np.ndarray) -> list[DamageResult]:
        """Run damage detection on a BGR numpy image. Returns list of DamageResult."""

    def warmup(self) -> None:
        """Called once at startup. Subclasses may override to warm up GPU/model."""

    def get_info(self) -> dict[str, Any]:
        return {
            "mode": self.__class__.__name__,
            "device": self.config.device,
            "score_threshold": self.config.score_threshold,
            "max_detections": self.config.max_detections,
            "model_path": self.config.model_path,
        }

"""Factory that creates and caches the correct predictor singleton based on environment config."""

from __future__ import annotations

import os
import threading
import time
from typing import Any

import structlog

from inference.base_predictor import BasePredictor, PredictorConfig

logger = structlog.get_logger(__name__)

_lock = threading.Lock()
_instance: BasePredictor | None = None
_created_at: float = 0.0


def _build_config() -> PredictorConfig:
    return PredictorConfig(
        score_threshold=float(os.environ.get("INFERENCE_SCORE_THRESHOLD", "0.45")),
        max_detections=int(os.environ.get("MAX_DETECTIONS", "20")),
        crop_padding_px=int(os.environ.get("CROP_PADDING_PX", "30")),
        model_path=os.environ.get("MODEL_WEIGHTS_PATH", "models/car_damage_model.pth"),
        device=os.environ.get("INFERENCE_DEVICE", "cpu"),
    )


def _create_predictor(config: PredictorConfig) -> BasePredictor:
    mode = os.environ.get("PREDICTOR_MODE", "dummy").lower()
    if mode == "detectron2":
        from inference.detectron2_predictor import Detectron2Predictor
        predictor: BasePredictor = Detectron2Predictor(config)
    else:
        from inference.dummy_predictor import DummyPredictor
        predictor = DummyPredictor(config)

    logger.info("predictor_created", mode=mode, device=config.device)
    predictor.warmup()
    logger.info("predictor_warmup_complete", mode=mode)
    return predictor


def get_predictor() -> BasePredictor:
    """Return the singleton predictor, creating it if needed. Thread-safe."""
    global _instance, _created_at
    if _instance is not None:
        return _instance
    with _lock:
        if _instance is None:
            config = _build_config()
            _instance = _create_predictor(config)
            _created_at = time.monotonic()
    return _instance


def reload_predictor() -> BasePredictor:
    """Destroy and recreate the singleton. Returns the new instance."""
    global _instance, _created_at
    with _lock:
        _instance = None
        config = _build_config()
        _instance = _create_predictor(config)
        _created_at = time.monotonic()
    logger.info("predictor_reloaded")
    return _instance


def get_predictor_info() -> dict[str, Any]:
    predictor = get_predictor()
    info = predictor.get_info()
    info["uptime_seconds"] = round(time.monotonic() - _created_at, 2) if _created_at else 0.0
    return info

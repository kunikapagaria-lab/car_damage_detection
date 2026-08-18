"""Pytest tests for the car damage inference pipeline.

All tests run with DummyPredictor on any machine — no GPU, no real cameras required.
"""

from __future__ import annotations

import base64
import io
import json
import os

import numpy as np
import pytest
from PIL import Image

os.environ.setdefault("PREDICTOR_MODE", "dummy")
os.environ.setdefault("CAMERAS_CONFIG_PATH", "config/cameras.yaml")
os.environ.setdefault("INFERENCE_SCORE_THRESHOLD", "0.45")
os.environ.setdefault("DUMMY_INFERENCE_LATENCY_MS", "10")


# ── Fixtures ──────────────────────────────────────────────────────────────────

@pytest.fixture(scope="session")
def synthetic_image() -> np.ndarray:
    import cv2
    canvas = np.zeros((720, 1280, 3), dtype=np.uint8)
    cv2.rectangle(canvas, (200, 150), (1080, 570), (200, 200, 200), -1)
    return canvas


@pytest.fixture(scope="session")
def predictor():
    from inference.base_predictor import PredictorConfig
    from inference.dummy_predictor import DummyPredictor
    config = PredictorConfig(score_threshold=0.45)
    return DummyPredictor(config)


@pytest.fixture(scope="session")
def test_client():
    from fastapi.testclient import TestClient
    from main_inference import app
    with TestClient(app, raise_server_exceptions=True) as client:
        yield client


# ── Unit tests — DummyPredictor ───────────────────────────────────────────────

def test_damage_result_structure(predictor, synthetic_image):
    results = predictor.predict(synthetic_image)
    assert isinstance(results, list)
    h, w = synthetic_image.shape[:2]
    for r in results:
        assert isinstance(r.annotation_id, str) and len(r.annotation_id) == 36
        assert r.class_name in {"scratch", "dent", "paint_damage", "crack"}
        assert isinstance(r.confidence, float)
        assert len(r.bbox_xyxy) == 4
        x1, y1, x2, y2 = r.bbox_xyxy
        assert 0 <= x1 < x2 <= w, f"bbox x out of bounds: {r.bbox_xyxy}"
        assert 0 <= y1 < y2 <= h, f"bbox y out of bounds: {r.bbox_xyxy}"
        assert isinstance(r.polygon_points, list)
        assert isinstance(r.mask_area_px, int)
        assert isinstance(r.mask_area_pct, float)
        assert isinstance(r.crop_b64, str) and len(r.crop_b64) > 0


def test_dummy_reproducibility(predictor, synthetic_image):
    results_a = predictor.predict(synthetic_image)
    results_b = predictor.predict(synthetic_image)
    assert len(results_a) == len(results_b), "Same image must yield same detection count"
    for a, b in zip(results_a, results_b):
        assert a.class_name == b.class_name
        assert a.bbox_xyxy == b.bbox_xyxy


def test_confidence_above_threshold(predictor, synthetic_image):
    results = predictor.predict(synthetic_image)
    for r in results:
        assert r.confidence >= predictor.config.score_threshold, (
            f"confidence {r.confidence} below threshold {predictor.config.score_threshold}"
        )


def test_crop_b64_is_valid_image(predictor, synthetic_image):
    results = predictor.predict(synthetic_image)
    for r in results:
        raw = base64.b64decode(r.crop_b64)
        img = Image.open(io.BytesIO(raw))
        assert img.format == "PNG"
        assert img.width > 0 and img.height > 0


def test_polygon_within_image_bounds(predictor, synthetic_image):
    h, w = synthetic_image.shape[:2]
    results = predictor.predict(synthetic_image)
    for r in results:
        for pt in r.polygon_points:
            assert 0 <= pt[0] <= w, f"polygon x {pt[0]} out of bounds"
            assert 0 <= pt[1] <= h, f"polygon y {pt[1]} out of bounds"


def test_mask_area_calculation(predictor, synthetic_image):
    results = predictor.predict(synthetic_image)
    h, w = synthetic_image.shape[:2]
    for r in results:
        assert r.mask_area_pct >= 0.0
        assert r.mask_area_pct <= 100.0
        assert r.mask_area_px > 0


# ── LPR test ──────────────────────────────────────────────────────────────────

@pytest.mark.skipif(
    __import__("importlib.util", fromlist=["util"]).find_spec("easyocr") is None,
    reason="easyocr not installed",
)
def test_lpr_plate_format(synthetic_image):
    import re
    from inference.lpr import detect_plate
    plate_pattern = re.compile(r"^[A-Z]{2}[0-9]{1,2}[A-Z]{1,3}[0-9]{4}$")
    result = detect_plate(synthetic_image)
    if result is not None:
        assert plate_pattern.match(result.plate_text), (
            f"Plate text '{result.plate_text}' doesn't match Indian plate format"
        )
        assert 0.0 <= result.confidence <= 1.0
        assert len(result.bbox) == 4


# ── API endpoint tests ────────────────────────────────────────────────────────

def test_inspect_frame_endpoint(test_client, synthetic_image):
    import cv2
    _, buf = cv2.imencode(".jpg", synthetic_image)
    img_bytes = buf.tobytes()
    response = test_client.post(
        "/api/v1/inspect/frame",
        data={"camera_id": "cam_test", "vehicle_id": "VH001"},
        files={"image": ("frame.jpg", img_bytes, "image/jpeg")},
    )
    assert response.status_code == 200
    body = response.json()
    assert "damages" in body
    assert "camera_id" in body
    assert body["camera_id"] == "cam_test"
    assert isinstance(body["damages"], list)
    assert "inference_time_ms" in body


def test_inspect_batch_endpoint(test_client, synthetic_image):
    import cv2
    _, buf = cv2.imencode(".jpg", synthetic_image)
    b64 = base64.b64encode(buf.tobytes()).decode()
    items = [
        {"camera_id": f"cam_{i}", "image_b64": b64, "vehicle_id": "VH001"}
        for i in range(3)
    ]
    response = test_client.post("/api/v1/inspect/batch", json={"items": items})
    assert response.status_code == 200
    body = response.json()
    assert len(body["results"]) == 3
    assert isinstance(body["total_damages"], int)
    assert "processing_time_ms" in body


def test_model_status_endpoint(test_client):
    response = test_client.get("/api/v1/model/status")
    assert response.status_code == 200
    body = response.json()
    for field in ("mode", "model_loaded", "device", "score_threshold",
                  "avg_inference_ms", "total_frames_processed", "lpr_available", "uptime_seconds"):
        assert field in body, f"Missing field: {field}"
    assert body["mode"] in {"dummy", "detectron2"}


def test_health_endpoint(test_client):
    response = test_client.get("/health")
    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "ok"
    assert "uptime_seconds" in body
    assert "mode" in body


def test_websocket_connects(test_client):
    with test_client.websocket_connect("/ws/live-feed") as ws:
        data = ws.receive_text()
        msg = json.loads(data)
        assert msg["event"] == "connected"
        assert "timestamp" in msg
        assert "mode" in msg

"""FastAPI router for inference endpoints — frame inspection, batch processing, and model management."""

from __future__ import annotations

import asyncio
import base64
import time
from collections import deque
from datetime import datetime, timezone
from functools import partial

import cv2
import numpy as np
import structlog
from fastapi import APIRouter, File, Form, HTTPException, UploadFile
from pydantic import BaseModel, Field

from inference.base_predictor import DamageResult, PlateResult
from inference.lpr import detect_plate
from inference.predictor_factory import get_predictor, get_predictor_info, reload_predictor

logger = structlog.get_logger(__name__)
router = APIRouter(prefix="/api/v1", tags=["inference"])

_MAX_IMAGE_BYTES = 20 * 1024 * 1024  # 20 MB
_MAX_BATCH_SIZE = 8
_MAX_DIMENSION  = 1920              # cap longest side — phone photos can be 4K+
_inference_latencies: deque[float] = deque(maxlen=100)
_total_frames = 0
_service_start = time.monotonic()


# ── Pydantic response models ──────────────────────────────────────────────────

class DamageResultOut(BaseModel):
    annotation_id: str
    class_name: str
    confidence: float
    bbox_xyxy: list[int]
    polygon_points: list[list[int]]
    mask_area_px: int
    mask_area_pct: float
    crop_b64: str
    reflection_score: float = 0.0  # 0=likely damage, 1=likely reflection/glare


class PlateResultOut(BaseModel):
    plate_text: str
    confidence: float
    bbox: list[int]


class InspectionResultOut(BaseModel):
    vehicle_id: str
    plate_result: PlateResultOut | None
    damages: list[DamageResultOut]
    inference_time_ms: float
    camera_id: str
    captured_at: str


class BatchItem(BaseModel):
    camera_id: str
    image_b64: str
    vehicle_id: str = ""


class BatchRequest(BaseModel):
    items: list[BatchItem] = Field(..., max_length=_MAX_BATCH_SIZE)


class BatchResponse(BaseModel):
    results: list[InspectionResultOut]
    total_damages: int
    processing_time_ms: float


class ModelStatusResponse(BaseModel):
    mode: str
    model_loaded: bool
    device: str
    score_threshold: float
    avg_inference_ms: float
    total_frames_processed: int
    lpr_available: bool
    uptime_seconds: float


class ReloadResponse(BaseModel):
    ok: bool
    new_mode: str
    reload_time_ms: float


class ErrorResponse(BaseModel):
    success: bool = False
    error: str
    detail: str


# ── Helpers ───────────────────────────────────────────────────────────────────

def _bytes_to_bgr(data: bytes) -> np.ndarray:
    arr = np.frombuffer(data, dtype=np.uint8)
    img = cv2.imdecode(arr, cv2.IMREAD_COLOR)
    if img is None:
        raise ValueError("Could not decode image — unsupported format or corrupt data")
    return img


def _reflection_score(image: np.ndarray, bbox: list[int]) -> float:
    """Return 0–1 probability that a bbox region is a light reflection, not damage.

    Algorithm:
      1. Extract the bbox crop from the BGR image.
      2. Convert to grayscale and compute the fraction of pixels brighter than
         a high-brightness threshold (210/255).  Specular reflections are
         predominantly very bright; paint/surface damage is not.
      3. Also check saturation channel — reflections are desaturated (white/grey
         glow); scratches on dark paint expose the primer (higher saturation
         contrast).  A high bright-pixel ratio combined with low mean saturation
         strongly indicates glare.

    Thresholds (tunable via env vars):
      REFLECT_BRIGHT_THRESH  pixel grayscale value considered "very bright" (default 210)
      REFLECT_RATIO_WARN     fraction of bright pixels that triggers warning  (default 0.45)
    """
    import os
    bright_thresh = int(os.environ.get("REFLECT_BRIGHT_THRESH", "210"))
    ratio_warn    = float(os.environ.get("REFLECT_RATIO_WARN",    "0.45"))

    x1, y1, x2, y2 = [int(v) for v in bbox]
    h, w = image.shape[:2]
    x1, y1, x2, y2 = max(0, x1), max(0, y1), min(w, x2), min(h, y2)
    region = image[y1:y2, x1:x2]
    if region.size < 200:          # bbox too small to be meaningful
        return 0.0

    gray       = cv2.cvtColor(region, cv2.COLOR_BGR2GRAY)
    bright_ratio = float(np.mean(gray > bright_thresh))

    # Low saturation test: reflections are near-white; damage on dark cars exposes
    # primer/metal which can be quite saturated
    hsv        = cv2.cvtColor(region, cv2.COLOR_BGR2HSV)
    mean_sat   = float(np.mean(hsv[:, :, 1])) / 255.0   # 0=grey/white, 1=vivid colour

    # Combine: high brightness AND low saturation → strong reflection signal
    if bright_ratio >= ratio_warn and mean_sat < 0.25:
        score = min(1.0, bright_ratio * 1.5)
    else:
        score = bright_ratio * 0.7      # partial signal

    return round(score, 3)


def _cap_resolution(img: np.ndarray, max_dim: int = _MAX_DIMENSION) -> np.ndarray:
    """Downscale so the longest side ≤ max_dim. No-op if already small enough.

    Phone photos can be 4000×3000 (36 MB raw). Processing them at full resolution
    crashes the service — 36 MB MD5, giant PNG crops, potential OOM in EasyOCR.
    1920px is more than enough for damage detection accuracy.
    """
    h, w = img.shape[:2]
    longest = max(h, w)
    if longest <= max_dim:
        return img
    scale = max_dim / longest
    new_w = max(1, int(w * scale))
    new_h = max(1, int(h * scale))
    resized = cv2.resize(img, (new_w, new_h), interpolation=cv2.INTER_AREA)
    logger.debug(
        "image_downscaled",
        original=(w, h),
        resized=(new_w, new_h),
        scale=round(scale, 3),
    )
    return resized


def _damage_to_out(d: DamageResult, reflection_score: float = 0.0) -> DamageResultOut:
    return DamageResultOut(
        annotation_id=d.annotation_id,
        class_name=d.class_name,
        confidence=d.confidence,
        bbox_xyxy=d.bbox_xyxy,
        polygon_points=d.polygon_points,
        mask_area_px=d.mask_area_px,
        mask_area_pct=d.mask_area_pct,
        crop_b64=d.crop_b64,
        reflection_score=reflection_score,
    )


def _plate_to_out(p: PlateResult | None) -> PlateResultOut | None:
    if p is None:
        return None
    return PlateResultOut(plate_text=p.plate_text, confidence=p.confidence, bbox=p.bbox)


_LPR_MAX_DIM = 640  # EasyOCR only needs a small thumbnail to read a plate


async def _run_inspection(
    image: np.ndarray,
    camera_id: str,
    vehicle_id: str,
) -> InspectionResultOut:
    global _total_frames
    loop = asyncio.get_event_loop()
    predictor = get_predictor()
    t0 = time.monotonic()

    # Give EasyOCR a small thumbnail — plates are readable at 640px,
    # and scanning a 1920px image on CPU takes 20+ seconds.
    lpr_image = _cap_resolution(image, _LPR_MAX_DIM)

    plate_result, damages = await asyncio.gather(
        loop.run_in_executor(None, partial(detect_plate, lpr_image)),
        loop.run_in_executor(None, partial(predictor.predict, image)),
    )

    elapsed_ms = (time.monotonic() - t0) * 1000.0
    _inference_latencies.append(elapsed_ms)
    _total_frames += 1
    captured_at = datetime.now(timezone.utc).isoformat()

    # Compute reflection score for every detection using the original image
    damages_out = [
        _damage_to_out(d, _reflection_score(image, d.bbox_xyxy))
        for d in damages
    ]
    reflection_flags = [d.reflection_score for d in damages_out]

    logger.info(
        "inspection_complete",
        camera_id=camera_id,
        vehicle_id=vehicle_id,
        plate_found=plate_result is not None,
        n_damages=len(damages),
        n_reflection_flagged=sum(1 for s in reflection_flags if s >= 0.5),
        inference_ms=round(elapsed_ms, 2),
    )

    return InspectionResultOut(
        vehicle_id=vehicle_id,
        plate_result=_plate_to_out(plate_result),
        damages=damages_out,
        inference_time_ms=round(elapsed_ms, 2),
        camera_id=camera_id,
        captured_at=captured_at,
    )


# ── Endpoints ─────────────────────────────────────────────────────────────────

@router.post("/inspect/frame", response_model=InspectionResultOut)
async def inspect_frame(
    image: UploadFile = File(...),
    camera_id: str = Form(...),
    vehicle_id: str = Form(""),
) -> InspectionResultOut:
    raw = await image.read()
    if len(raw) > _MAX_IMAGE_BYTES:
        raise HTTPException(status_code=413, detail="Image exceeds 20 MB limit")
    try:
        bgr = _cap_resolution(_bytes_to_bgr(raw))
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    return await _run_inspection(bgr, camera_id, vehicle_id)


@router.post("/inspect/batch", response_model=BatchResponse)
async def inspect_batch(body: BatchRequest) -> BatchResponse:
    t0 = time.monotonic()
    tasks = []
    for item in body.items:
        try:
            raw = base64.b64decode(item.image_b64)
            bgr = _cap_resolution(_bytes_to_bgr(raw))
        except Exception as exc:
            raise HTTPException(status_code=422, detail=f"Invalid image_b64: {exc}") from exc
        tasks.append(_run_inspection(bgr, item.camera_id, item.vehicle_id))

    results: list[InspectionResultOut] = await asyncio.gather(*tasks)
    total_damages = sum(len(r.damages) for r in results)
    processing_ms = (time.monotonic() - t0) * 1000.0
    return BatchResponse(
        results=list(results),
        total_damages=total_damages,
        processing_time_ms=round(processing_ms, 2),
    )


@router.get("/inspect/test", response_model=InspectionResultOut)
async def inspect_test() -> InspectionResultOut:
    canvas = np.zeros((720, 1280, 3), dtype=np.uint8)
    cv2.rectangle(canvas, (200, 150), (1080, 570), (200, 200, 200), -1)
    return await _run_inspection(canvas, camera_id="test_cam", vehicle_id="TEST_VEHICLE")


@router.get("/model/status", response_model=ModelStatusResponse)
async def model_status() -> ModelStatusResponse:
    info = get_predictor_info()
    avg_ms = (
        sum(_inference_latencies) / len(_inference_latencies)
        if _inference_latencies
        else 0.0
    )

    lpr_available = True
    try:
        import easyocr  # noqa: F401
    except ImportError:
        lpr_available = False

    return ModelStatusResponse(
        mode=info.get("mode", "dummy"),
        model_loaded=True,
        device=info.get("device", "cpu"),
        score_threshold=float(info.get("score_threshold", 0.45)),
        avg_inference_ms=round(avg_ms, 2),
        total_frames_processed=_total_frames,
        lpr_available=lpr_available,
        uptime_seconds=round(time.monotonic() - _service_start, 2),
    )


@router.post("/model/reload", response_model=ReloadResponse)
async def model_reload() -> ReloadResponse:
    loop = asyncio.get_event_loop()
    t0 = time.monotonic()
    predictor = await loop.run_in_executor(None, reload_predictor)
    elapsed_ms = (time.monotonic() - t0) * 1000.0
    info = predictor.get_info()
    logger.info("model_reloaded", new_mode=info.get("mode"), reload_ms=round(elapsed_ms, 2))
    return ReloadResponse(
        ok=True,
        new_mode=str(info.get("mode", "dummy")),
        reload_time_ms=round(elapsed_ms, 2),
    )

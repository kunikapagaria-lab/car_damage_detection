"""Car Damage Inference Service — FastAPI application entry point.

# HOW TO ACTIVATE REAL DETECTRON2 MODEL
# 1. pip install -r requirements_full.txt
# 2. Set PREDICTOR_MODE=detectron2 in .env
# 3. Set MODEL_WEIGHTS_PATH=models/car_damage_model.pth in .env
# 4. Rebuild Docker image using Stage 2 (GPU) target
# 5. Restart service — zero code changes required
"""

from __future__ import annotations

import asyncio
import os
import time
import traceback
from contextlib import asynccontextmanager
from typing import AsyncIterator

import structlog
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from api.inference_routes import router as inference_router
from api.websocket_routes import (
    _ping_loop,
    _queue_processor_loop,
    router as ws_router,
)
from inference.lpr import warmup_lpr
from inference.predictor_factory import get_predictor
from inference.stream_processor import StreamProcessor

logger = structlog.get_logger(__name__)

_CAMERAS_CONFIG = os.environ.get("CAMERAS_CONFIG_PATH", "config/cameras.yaml")
_FRAME_QUEUE_MAXSIZE = int(os.environ.get("FRAME_QUEUE_MAXSIZE", "50"))
_service_start = time.monotonic()

_frame_queue: asyncio.Queue
_stream_processor: StreamProcessor | None = None
_background_tasks: list[asyncio.Task] = []


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    global _frame_queue, _stream_processor, _background_tasks

    logger.info("inference_service_starting")

    # Pre-load EasyOCR model
    loop = asyncio.get_event_loop()
    await loop.run_in_executor(None, warmup_lpr)

    # Initialize predictor singleton + warmup
    predictor = await loop.run_in_executor(None, get_predictor)
    info = predictor.get_info()
    logger.info(
        "predictor_ready",
        mode=info.get("mode"),
        device=info.get("device"),
    )

    # Initialize and start stream processor
    _frame_queue = asyncio.Queue(maxsize=_FRAME_QUEUE_MAXSIZE)

    try:
        _stream_processor = StreamProcessor(_CAMERAS_CONFIG, _frame_queue)
        _stream_processor.start()
        cam_count = len(_stream_processor._cameras)
    except Exception as exc:
        logger.warning(
            "stream_processor_start_failed",
            error=str(exc),
            detail="Continuing without camera streams",
        )
        _stream_processor = None
        cam_count = 0

    # Start background tasks
    _background_tasks = [
        asyncio.create_task(_queue_processor_loop(_frame_queue), name="queue_processor"),
        asyncio.create_task(_ping_loop(), name="ws_ping"),
    ]

    logger.info(
        "inference_service_ready",
        mode=info.get("mode"),
        device=info.get("device"),
        camera_count=cam_count,
        port=int(os.environ.get("INFERENCE_PORT", "8001")),
    )

    yield

    # ── Shutdown ──
    logger.info("inference_service_shutting_down")

    for task in _background_tasks:
        task.cancel()
    await asyncio.gather(*_background_tasks, return_exceptions=True)

    if _stream_processor is not None:
        await loop.run_in_executor(None, _stream_processor.stop)

    logger.info("inference_service_shutdown_complete")


app = FastAPI(
    title="Car Damage Inference Service",
    version="1.0.0",
    docs_url="/docs",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000", "http://localhost:3001", "http://localhost:8000"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(inference_router)
app.include_router(ws_router)


@app.get("/health")
async def health() -> JSONResponse:
    cam_count = 0
    if _stream_processor is not None:
        status = _stream_processor.get_status()
        cam_count = sum(1 for v in status.values() if v.get("connected"))
    mode = os.environ.get("PREDICTOR_MODE", "dummy")
    return JSONResponse({
        "status": "ok",
        "mode": mode,
        "uptime_seconds": round(time.monotonic() - _service_start, 2),
        "cameras_connected": cam_count,
    })


@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception) -> JSONResponse:
    logger.error(
        "unhandled_exception",
        path=request.url.path,
        method=request.method,
        error=str(exc),
    )
    return JSONResponse(
        status_code=500,
        content={
            "success": False,
            "error": type(exc).__name__,
            "detail": "An internal server error occurred.",
        },
    )


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(
        "main_inference:app",
        host=os.environ.get("INFERENCE_HOST", "0.0.0.0"),
        port=int(os.environ.get("INFERENCE_PORT", "8001")),
        workers=1,
        log_config=None,
    )

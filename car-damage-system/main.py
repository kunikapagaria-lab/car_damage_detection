"""Car Damage Backend API — FastAPI entry point (port 8000).

Provides vehicle management, scan ingestion, damage history, webhook alerts,
and presigned image URL generation. Backed by PostgreSQL, Redis, and MinIO.
"""

from __future__ import annotations

import time
from contextlib import asynccontextmanager
from typing import AsyncIterator

import structlog
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from slowapi.errors import RateLimitExceeded

from api.routes.alerts import router as alerts_router
from api.routes.reports import router as reports_router
from api.routes.scans import router as scans_router
from api.routes.vehicles import router as vehicles_router
from core.config import settings
from core.deps import close_redis, get_redis, limiter
from storage.minio_client import ensure_buckets

logger = structlog.get_logger(__name__)
_service_start = time.monotonic()


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    logger.info("backend_starting", environment=settings.ENVIRONMENT)

    # Warm up Redis connection
    try:
        redis = await get_redis()
        await redis.ping()
        logger.info("redis_connected", url=settings.REDIS_URL)
    except Exception as exc:
        logger.warning("redis_unavailable", error=str(exc))

    # Ensure MinIO buckets exist
    try:
        await ensure_buckets()
        logger.info("minio_buckets_ready")
    except Exception as exc:
        logger.warning("minio_unavailable", error=str(exc))

    logger.info("backend_ready", port=settings.BACKEND_PORT)
    yield

    await close_redis()
    logger.info("backend_shutdown_complete")


app = FastAPI(
    title="Car Damage Backend API",
    version="1.0.0",
    docs_url="/docs",
    lifespan=lifespan,
)

app.state.limiter = limiter

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000", "http://localhost:3001", "http://localhost:8001"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(vehicles_router)
app.include_router(scans_router)
app.include_router(alerts_router)
app.include_router(reports_router)


@app.exception_handler(RateLimitExceeded)
async def rate_limit_handler(request: Request, exc: RateLimitExceeded) -> JSONResponse:
    return JSONResponse(
        status_code=429,
        content={
            "success": False,
            "data": None,
            "error": "rate_limit_exceeded",
            "meta": {"detail": str(exc.detail)},
        },
    )


@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception) -> JSONResponse:
    logger.error(
        "unhandled_exception",
        path=request.url.path,
        method=request.method,
        error=str(exc),
        exc_type=type(exc).__name__,
    )
    return JSONResponse(
        status_code=500,
        content={
            "success": False,
            "data": None,
            "error": type(exc).__name__,
            "meta": {"detail": "An internal server error occurred."},
        },
    )


@app.get("/health")
async def health() -> JSONResponse:
    return JSONResponse({
        "status": "ok",
        "uptime_seconds": round(time.monotonic() - _service_start, 2),
        "environment": settings.ENVIRONMENT,
    })


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(
        "main:app",
        host=settings.BACKEND_HOST,
        port=settings.BACKEND_PORT,
        workers=1,
        log_config=None,
    )

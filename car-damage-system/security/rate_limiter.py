"""Redis-backed sliding-window rate limiter.

Limits:
  - Authenticated operators / admins : 120 req / 60 s
  - Unauthenticated requests          :  30 req / 60 s

Returns 429 with a Retry-After header when the limit is exceeded.
"""

from __future__ import annotations

import time
from typing import Any

import structlog
from fastapi import Request
from fastapi.responses import JSONResponse
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.types import ASGIApp

from core.deps import get_redis
from security.auth import decode_token

logger = structlog.get_logger(__name__)

WINDOW_SECONDS = 60
LIMIT_AUTHENTICATED = 120
LIMIT_ANONYMOUS = 30


# ── Core sliding-window algorithm ─────────────────────────────────────────────

async def check_rate_limit(
    redis: Any,
    identifier: str,
    limit: int,
    window: int = WINDOW_SECONDS,
) -> tuple[bool, int, int]:
    """Sliding-window rate check.

    Returns:
        (is_limited, current_count, retry_after_seconds)
    """
    now = time.time()
    window_start = now - window
    key = f"rl:{identifier}"

    pipe = redis.pipeline()
    pipe.zremrangebyscore(key, 0, window_start)
    pipe.zadd(key, {f"{now:.6f}": now})
    pipe.zcard(key)
    pipe.expire(key, window + 1)
    results = await pipe.execute()

    count: int = results[2]
    is_limited = count > limit

    retry_after = 0
    if is_limited:
        oldest_entries = await redis.zrange(key, 0, 0, withscores=True)
        if oldest_entries:
            oldest_ts = float(oldest_entries[0][1])
            retry_after = max(1, int(oldest_ts + window - now) + 1)
        else:
            retry_after = window

    return is_limited, count, retry_after


# ── Middleware ────────────────────────────────────────────────────────────────

class RateLimitMiddleware(BaseHTTPMiddleware):
    """FastAPI/Starlette middleware that enforces per-identity rate limits."""

    # Paths that bypass rate limiting (health checks, static assets)
    _BYPASS_PREFIXES = ("/health", "/docs", "/openapi.json", "/redoc")

    def __init__(self, app: ASGIApp) -> None:
        super().__init__(app)

    async def dispatch(self, request: Request, call_next: Any) -> Any:
        path = request.url.path
        if any(path.startswith(p) for p in self._BYPASS_PREFIXES):
            return await call_next(request)

        identifier, limit = await self._identify(request)

        try:
            redis = await get_redis()
            is_limited, count, retry_after = await check_rate_limit(
                redis, identifier, limit
            )
        except Exception as exc:
            # Redis unavailable — fail open (don't block traffic)
            logger.warning("rate_limiter_redis_error", error=str(exc))
            return await call_next(request)

        if is_limited:
            logger.warning(
                "rate_limit_exceeded",
                identifier=identifier,
                limit=limit,
                count=count,
                retry_after=retry_after,
            )
            return JSONResponse(
                status_code=429,
                content={
                    "success": False,
                    "data": None,
                    "error": "rate_limit_exceeded",
                    "meta": {
                        "limit": limit,
                        "window_seconds": WINDOW_SECONDS,
                        "retry_after": retry_after,
                    },
                },
                headers={"Retry-After": str(retry_after)},
            )

        response = await call_next(request)
        response.headers["X-RateLimit-Limit"] = str(limit)
        response.headers["X-RateLimit-Remaining"] = str(max(0, limit - count))
        return response

    @staticmethod
    async def _identify(request: Request) -> tuple[str, int]:
        """Return (rate_limit_key, limit) for this request."""
        auth = request.headers.get("Authorization", "")
        if auth.startswith("Bearer "):
            token = auth[7:]
            try:
                payload = decode_token(token)
                username = payload.get("sub", "unknown")
                return f"user:{username}", LIMIT_AUTHENTICATED
            except Exception:
                pass

        client_ip = request.client.host if request.client else "unknown"
        return f"ip:{client_ip}", LIMIT_ANONYMOUS

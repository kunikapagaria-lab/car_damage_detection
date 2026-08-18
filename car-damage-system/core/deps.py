"""FastAPI dependency injection: DB session, Redis client, rate limiter."""

from __future__ import annotations

from collections.abc import AsyncGenerator

import redis.asyncio as aioredis
import structlog
from fastapi import Depends
from slowapi import Limiter
from slowapi.util import get_remote_address
from sqlalchemy.ext.asyncio import AsyncSession

from core.config import settings
from db.database import AsyncSessionLocal

logger = structlog.get_logger(__name__)

limiter = Limiter(key_func=get_remote_address, default_limits=["60/minute"])

_redis_pool: aioredis.Redis | None = None


async def get_redis() -> aioredis.Redis:
    global _redis_pool
    if _redis_pool is None:
        _redis_pool = aioredis.from_url(
            settings.REDIS_URL,
            encoding="utf-8",
            decode_responses=True,
        )
    return _redis_pool


async def close_redis() -> None:
    global _redis_pool
    if _redis_pool is not None:
        await _redis_pool.aclose()
        _redis_pool = None


async def get_db() -> AsyncGenerator[AsyncSession, None]:
    async with AsyncSessionLocal() as session:
        try:
            yield session
        except Exception:
            await session.rollback()
            raise

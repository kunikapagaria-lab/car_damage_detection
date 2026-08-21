"""Fleet-wide dashboard summary — one endpoint powering the landing page."""

from __future__ import annotations

import structlog
from fastapi import APIRouter, Depends, Request
from sqlalchemy.ext.asyncio import AsyncSession

import db.crud as crud
from core.deps import get_db, limiter
from core.response import ok
from db.schemas import DashboardSummaryOut

logger = structlog.get_logger(__name__)
router = APIRouter(prefix="/api/v1/dashboard", tags=["dashboard"])


@router.get("/summary")
@limiter.limit("60/minute")
async def get_dashboard_summary(
    request: Request,
    db: AsyncSession = Depends(get_db),
):
    summary = await crud.get_dashboard_summary(db)
    data = DashboardSummaryOut.model_validate(summary).model_dump(mode="json")
    return ok(data)

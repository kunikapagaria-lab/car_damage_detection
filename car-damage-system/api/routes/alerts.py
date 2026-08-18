"""Webhook registration, HMAC-signed alert delivery, and alert log retrieval."""


import hashlib
import hmac
import json
import uuid
from datetime import datetime, timezone
from typing import Any

import httpx
import structlog
from fastapi import APIRouter, Depends, Query, Request
from sqlalchemy.ext.asyncio import AsyncSession

import db.crud as crud
from core.deps import get_db, limiter
from core.response import err, ok
from db.schemas import AlertLogOut, WebhookOut, WebhookRegisterRequest

logger = structlog.get_logger(__name__)
router = APIRouter(prefix="/api/v1", tags=["alerts"])


def _sign_payload(secret: str, payload: str) -> str:
    return "sha256=" + hmac.new(
        secret.encode("utf-8"),
        payload.encode("utf-8"),
        hashlib.sha256,
    ).hexdigest()


async def fire_webhooks(
    scan_id: uuid.UUID,
    vehicle_id: uuid.UUID,
    plate_number: str,
    diff_summary: dict[str, Any],
    db: AsyncSession,
) -> None:
    """Deliver signed webhook payloads to all active registrations."""
    hooks = await crud.get_active_webhooks(db)
    if not hooks:
        return

    payload: dict[str, Any] = {
        "event": "new_damage_detected",
        "scan_id": str(scan_id),
        "vehicle_id": str(vehicle_id),
        "plate_number": plate_number,
        "new_damage_count": diff_summary.get("total_new", 0),
        "resolved_damage_count": diff_summary.get("total_resolved", 0),
        "diff_summary": diff_summary,
        "triggered_at": datetime.now(timezone.utc).isoformat(),
    }
    payload_json = json.dumps(payload, default=str)

    async with httpx.AsyncClient(timeout=10.0) as client:
        for hook in hooks:
            signature = _sign_payload(hook.secret, payload_json)
            status_code = 0
            try:
                resp = await client.post(
                    hook.url,
                    content=payload_json,
                    headers={
                        "Content-Type": "application/json",
                        "X-Signature-SHA256": signature,
                    },
                )
                status_code = resp.status_code
            except Exception as exc:
                logger.error("webhook_delivery_failed", url=hook.url, error=str(exc))
                status_code = 0

            hook.last_triggered_at = datetime.now(timezone.utc)
            await crud.log_alert(
                scan_id=scan_id,
                vehicle_id=vehicle_id,
                webhook_id=hook.id,
                status_code=status_code,
                payload_summary={
                    "event": payload["event"],
                    "new_damage_count": payload["new_damage_count"],
                    "plate_number": plate_number,
                },
                db=db,
            )
            logger.info(
                "webhook_delivered",
                url=hook.url,
                status_code=status_code,
                scan_id=str(scan_id),
            )

    await db.commit()


@router.post("/webhooks/register")
@limiter.limit("60/minute")
async def register_webhook(
    request: Request,
    body: WebhookRegisterRequest,
    db: AsyncSession = Depends(get_db),
):
    hook = await crud.register_webhook(url=body.url, secret=body.secret, db=db)
    await db.commit()
    return ok(WebhookOut.model_validate(hook).model_dump(mode="json"), status_code=201)


@router.get("/alerts/recent")
@limiter.limit("60/minute")
async def get_recent_alerts(
    request: Request,
    limit: int = Query(20, ge=1, le=100),
    db: AsyncSession = Depends(get_db),
):
    alerts = await crud.get_recent_alerts(db, limit=limit)
    data = [AlertLogOut.model_validate(a).model_dump(mode="json") for a in alerts]
    return ok(data, meta={"count": len(data)})

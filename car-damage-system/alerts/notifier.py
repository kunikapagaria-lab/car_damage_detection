"""Alert delivery: webhook fanout with exponential-backoff retry, HMAC signing,
HTML email notifications, and Redis-based alert deduplication.

Deduplication window: 10 minutes per vehicle.
Retry schedule: attempt 1 → immediate, attempt 2 → +5 s, attempt 3 → +30 s.
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import json
import os
import smtplib
import uuid
from datetime import timedelta
from email.mime.base import MIMEBase
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from email import encoders
from typing import Any

import httpx
import structlog
from tenacity import (
    retry,
    retry_if_exception_type,
    stop_after_attempt,
    wait_none,
    wait_fixed,
)

logger = structlog.get_logger(__name__)

DEDUP_TTL_SECONDS = 600  # 10 minutes
SMTP_HOST = os.environ.get("SMTP_HOST", "localhost")
SMTP_PORT = int(os.environ.get("SMTP_PORT", "587"))
SMTP_USERNAME = os.environ.get("SMTP_USERNAME", "")
SMTP_PASSWORD = os.environ.get("SMTP_PASSWORD", "")
SMTP_FROM = os.environ.get("SMTP_FROM", "noreply@damagevision.local")
SMTP_TLS = os.environ.get("SMTP_TLS", "true").lower() == "true"
ALERT_EMAIL_TO = os.environ.get("ALERT_EMAIL_TO", "")


# ── HMAC signing ──────────────────────────────────────────────────────────────

def _sign_payload(secret: str, payload_json: str) -> str:
    return "sha256=" + hmac.new(
        secret.encode("utf-8"),
        payload_json.encode("utf-8"),
        hashlib.sha256,
    ).hexdigest()


# ── Retry wait strategy: 5 s then 30 s ───────────────────────────────────────

_RETRY_WAITS = [0, 5, 30]  # seconds before each attempt (0 = immediate)


def _retry_wait(retry_state: Any) -> float:
    idx = min(retry_state.attempt_number, len(_RETRY_WAITS) - 1)
    return float(_RETRY_WAITS[idx])


# ── Webhook delivery ──────────────────────────────────────────────────────────

@retry(
    retry=retry_if_exception_type((httpx.RequestError, httpx.HTTPStatusError)),
    stop=stop_after_attempt(3),
    wait=_retry_wait,
    reraise=True,
)
async def _post_webhook(url: str, secret: str, payload_json: str) -> int:
    signature = _sign_payload(secret, payload_json)
    async with httpx.AsyncClient(timeout=15.0) as client:
        resp = await client.post(
            url,
            content=payload_json,
            headers={
                "Content-Type": "application/json",
                "X-Signature-SHA256": signature,
                "User-Agent": "DamageVision-Notifier/1.0",
            },
        )
        resp.raise_for_status()
    return resp.status_code


async def deliver_webhook(
    url: str,
    secret: str,
    payload: dict[str, Any],
) -> int:
    """Sign and POST payload to a webhook URL with retry.

    Returns the final HTTP status code, or 0 on total failure.
    """
    payload_json = json.dumps(payload, default=str)
    try:
        status_code = await _post_webhook(url, secret, payload_json)
        logger.info("webhook_delivered", url=url, status=status_code)
        return status_code
    except Exception as exc:
        logger.error("webhook_delivery_failed", url=url, error=str(exc))
        return 0


# ── Alert deduplication ───────────────────────────────────────────────────────

async def is_duplicate_alert(vehicle_id: str, redis: Any) -> bool:
    """Return True if this vehicle was already alerted in the dedup window."""
    key = f"alert_dedup:{vehicle_id}"
    exists = await redis.exists(key)
    if exists:
        return True
    await redis.setex(key, DEDUP_TTL_SECONDS, "1")
    return False


# ── Email helper ──────────────────────────────────────────────────────────────

def _build_html_email(
    plate_number: str,
    scan_id: str,
    new_damage_count: int,
    damages: list[dict[str, Any]],
    frontend_url: str,
) -> str:
    damage_rows = "".join(
        f"<tr>"
        f"<td style='padding:6px 10px;border-bottom:1px solid #eee;'>{d.get('class_name','')}</td>"
        f"<td style='padding:6px 10px;border-bottom:1px solid #eee;'>{d.get('confidence', 0)*100:.1f}%</td>"
        f"</tr>"
        for d in damages[:10]
    )
    scan_url = f"{frontend_url}/scans/{scan_id}"
    return f"""
<html><body style="font-family:Helvetica,Arial,sans-serif;color:#1a1a2e;background:#f9f9f9;margin:0;padding:0;">
<div style="max-width:560px;margin:30px auto;background:#fff;border-radius:8px;
     border:1px solid #e0e0e0;overflow:hidden;">
  <div style="background:#e74c3c;padding:20px 24px;">
    <h1 style="color:#fff;margin:0;font-size:18px;">⚠ New Damage Detected</h1>
  </div>
  <div style="padding:24px;">
    <p style="font-size:28px;font-family:monospace;font-weight:bold;letter-spacing:4px;
       margin:0 0 8px;">{plate_number}</p>
    <p style="color:#666;margin:0 0 16px;">
      <strong>{new_damage_count}</strong> new damage detection{'s' if new_damage_count != 1 else ''}
      identified during inspection.
    </p>
    <table style="width:100%;border-collapse:collapse;font-size:13px;">
      <thead>
        <tr>
          <th style="text-align:left;padding:6px 10px;background:#f8f8f8;border-bottom:2px solid #eee;">Class</th>
          <th style="text-align:left;padding:6px 10px;background:#f8f8f8;border-bottom:2px solid #eee;">Confidence</th>
        </tr>
      </thead>
      <tbody>{damage_rows}</tbody>
    </table>
    <div style="margin-top:20px;">
      <a href="{scan_url}"
         style="background:#2980b9;color:#fff;padding:10px 20px;
                border-radius:5px;text-decoration:none;font-weight:bold;">
        View Full Report →
      </a>
    </div>
    <p style="font-size:11px;color:#aaa;margin-top:20px;">
      Scan ID: <code>{scan_id}</code>
    </p>
  </div>
</div>
</body></html>
"""


def send_email_alert(
    plate_number: str,
    scan_id: str,
    new_damage_count: int,
    damages: list[dict[str, Any]],
    crop_image_bytes: bytes | None = None,
    frontend_url: str = "http://localhost:3000",
) -> None:
    """Send an HTML email alert with optional damage crop attachment."""
    if not ALERT_EMAIL_TO:
        logger.debug("email_alert_skipped", reason="ALERT_EMAIL_TO not configured")
        return

    msg = MIMEMultipart("related")
    msg["From"] = SMTP_FROM
    msg["To"] = ALERT_EMAIL_TO
    msg["Subject"] = (
        f"[DamageVision] New damage on {plate_number} — "
        f"{new_damage_count} detection{'s' if new_damage_count != 1 else ''}"
    )

    html_body = _build_html_email(
        plate_number, scan_id, new_damage_count, damages, frontend_url
    )
    msg.attach(MIMEText(html_body, "html"))

    if crop_image_bytes:
        part = MIMEBase("image", "jpeg")
        part.set_payload(crop_image_bytes)
        encoders.encode_base64(part)
        part.add_header(
            "Content-Disposition",
            "attachment",
            filename="damage_crop.jpg",
        )
        msg.attach(part)

    try:
        with smtplib.SMTP(SMTP_HOST, SMTP_PORT, timeout=10) as smtp:
            if SMTP_TLS:
                smtp.starttls()
            if SMTP_USERNAME:
                smtp.login(SMTP_USERNAME, SMTP_PASSWORD)
            smtp.send_message(msg)
        logger.info("email_alert_sent", to=ALERT_EMAIL_TO, plate=plate_number)
    except Exception as exc:
        logger.error("email_alert_failed", error=str(exc))


# ── Orchestrated alert dispatch ───────────────────────────────────────────────

async def dispatch_new_damage_alert(
    vehicle_id: str,
    plate_number: str,
    scan_id: str,
    new_damage_count: int,
    damages: list[dict[str, Any]],
    webhooks: list[dict[str, Any]],
    redis: Any,
    crop_image_bytes: bytes | None = None,
    frontend_url: str = "http://localhost:3000",
) -> None:
    """Main alert orchestrator: dedup check → webhook fanout → email."""
    if await is_duplicate_alert(vehicle_id, redis):
        logger.info(
            "alert_deduplicated",
            vehicle_id=vehicle_id,
            plate=plate_number,
        )
        return

    payload: dict[str, Any] = {
        "event": "new_damage_detected",
        "scan_id": scan_id,
        "vehicle_id": vehicle_id,
        "plate_number": plate_number,
        "new_damage_count": new_damage_count,
        "damages": damages,
        "scan_url": f"{frontend_url}/scans/{scan_id}",
    }

    # Webhook fanout
    for hook in webhooks:
        await deliver_webhook(
            url=hook["url"],
            secret=hook["secret"],
            payload=payload,
        )

    # Email (runs synchronously in calling thread — offload to Celery in prod)
    if ALERT_EMAIL_TO:
        send_email_alert(
            plate_number=plate_number,
            scan_id=scan_id,
            new_damage_count=new_damage_count,
            damages=damages,
            crop_image_bytes=crop_image_bytes,
            frontend_url=frontend_url,
        )

    logger.info(
        "alert_dispatched",
        plate=plate_number,
        scan_id=scan_id,
        webhooks_notified=len(webhooks),
        email_sent=bool(ALERT_EMAIL_TO),
    )

"""Celery task definitions for async heavy-lifting.

Tasks
─────
  generate_pdf_task        — renders PDF report to a temp file, stores path in result
  deliver_webhook_task     — signed webhook delivery with retries
  compute_damage_diff_task — damage diff computation (IoU matching)
"""

from __future__ import annotations

import asyncio
import os
import tempfile
from pathlib import Path
from typing import Any

import structlog
from celery import Task

from tasks.celery_app import celery_app

logger = structlog.get_logger(__name__)


def _run_async(coro: Any) -> Any:
    """Run an async coroutine from a synchronous Celery task."""
    loop = asyncio.new_event_loop()
    try:
        return loop.run_until_complete(coro)
    finally:
        loop.close()


# ── PDF generation ────────────────────────────────────────────────────────────

@celery_app.task(
    bind=True,
    max_retries=2,
    default_retry_delay=30,
    name="tasks.tasks.generate_pdf_task",
)
def generate_pdf_task(self: Task, scan_id: str) -> str:
    """Generate a PDF report and return the output file path."""
    from reports.pdf_generator import generate_report

    output_dir = Path(os.environ.get("PDF_OUTPUT_DIR", "/tmp/reports"))
    output_dir.mkdir(parents=True, exist_ok=True)
    output_path = output_dir / f"report_{scan_id}.pdf"

    try:
        _run_async(generate_report(scan_id, output_path))
        logger.info("pdf_task_complete", scan_id=scan_id, path=str(output_path))
        return str(output_path)
    except Exception as exc:
        logger.error("pdf_task_failed", scan_id=scan_id, error=str(exc))
        raise self.retry(exc=exc, countdown=60) from exc


# ── Webhook delivery ──────────────────────────────────────────────────────────

@celery_app.task(
    bind=True,
    max_retries=3,
    name="tasks.tasks.deliver_webhook_task",
)
def deliver_webhook_task(
    self: Task,
    url: str,
    secret: str,
    payload: dict[str, Any],
) -> int:
    """Deliver a webhook with HMAC signature and exponential-backoff retry."""
    from alerts.notifier import deliver_webhook

    COUNTDOWN = [5, 30, 300]

    try:
        status_code = _run_async(deliver_webhook(url, secret, payload))
        if status_code == 0 or status_code >= 500:
            raise ValueError(f"Webhook delivery failed with status {status_code}")
        logger.info("webhook_task_complete", url=url, status=status_code)
        return status_code
    except Exception as exc:
        attempt = self.request.retries
        countdown = COUNTDOWN[min(attempt, len(COUNTDOWN) - 1)]
        logger.warning("webhook_task_retry", url=url, attempt=attempt, countdown=countdown)
        raise self.retry(exc=exc, countdown=countdown) from exc


# ── Damage diff ───────────────────────────────────────────────────────────────

@celery_app.task(
    name="tasks.tasks.compute_damage_diff_task",
    ignore_result=False,
)
def compute_damage_diff_task(vehicle_id: str, scan_id: str) -> dict[str, Any]:
    """Run IoU-based damage diff and return the summary dict."""
    import uuid
    from db.crud import run_damage_diff
    from db.database import AsyncSessionLocal

    async def _run() -> dict[str, Any]:
        async with AsyncSessionLocal() as db:
            summary = await run_damage_diff(
                uuid.UUID(vehicle_id),
                uuid.UUID(scan_id),
                db,
            )
            await db.commit()
            return summary

    result = _run_async(_run())
    logger.info(
        "diff_task_complete",
        scan_id=scan_id,
        new=result.get("total_new", 0),
        resolved=result.get("total_resolved", 0),
    )
    return result

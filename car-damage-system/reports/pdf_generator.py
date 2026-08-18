"""PDF inspection report generator.

Fetches scan data and images from the database and MinIO, renders a
Jinja2 HTML template, and converts it to PDF using WeasyPrint.
Also exposes a FastAPI router with POST /api/v1/scans/{scan_id}/report.
"""

from __future__ import annotations

import asyncio
import base64
import io
import os
import tempfile
import uuid
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import qrcode
import structlog
from aiobotocore.session import AioSession
from fastapi import APIRouter, BackgroundTasks, HTTPException
from fastapi.responses import FileResponse
from jinja2 import Environment, FileSystemLoader, select_autoescape
from sqlalchemy import select
from weasyprint import HTML

from core.config import settings
from db.database import AsyncSessionLocal
from db.models import DamageDiff, DamageRecord, Scan, ScanImage, Vehicle

logger = structlog.get_logger(__name__)

TEMPLATES_DIR = Path(__file__).parent / "templates"
FRONTEND_URL = os.environ.get("FRONTEND_URL", "http://localhost:3000")
COMPANY_NAME = os.environ.get("COMPANY_NAME", "DamageVision Systems")

router = APIRouter(prefix="/api/v1/scans", tags=["reports"])

# ── MinIO download helper ─────────────────────────────────────────────────────

def _minio_kwargs() -> dict[str, Any]:
    scheme = "https" if settings.MINIO_SECURE else "http"
    return {
        "service_name": "s3",
        "endpoint_url": f"{scheme}://{settings.MINIO_ENDPOINT}",
        "aws_access_key_id": settings.MINIO_ACCESS_KEY,
        "aws_secret_access_key": settings.MINIO_SECRET_KEY,
        "region_name": "us-east-1",
    }


async def _download(bucket: str, key: str) -> bytes:
    """Download object bytes from MinIO; returns empty bytes on failure."""
    session = AioSession()
    try:
        async with session.create_client(**_minio_kwargs()) as s3:
            resp = await s3.get_object(Bucket=bucket, Key=key)
            return await resp["Body"].read()
    except Exception as exc:
        logger.warning("minio_download_failed", bucket=bucket, key=key, error=str(exc))
        return b""


def _b64(data: bytes) -> str:
    return base64.b64encode(data).decode()


# ── QR code ───────────────────────────────────────────────────────────────────

def _make_qr(url: str) -> str:
    qr = qrcode.QRCode(version=1, box_size=5, border=2)
    qr.add_data(url)
    qr.make(fit=True)
    img = qr.make_image(fill_color="black", back_color="white")
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return _b64(buf.getvalue())


# ── Report data assembly ──────────────────────────────────────────────────────

async def _build_context(scan_id: str) -> dict[str, Any]:
    """Fetch all data needed to render the report template."""
    sid = uuid.UUID(scan_id)

    async with AsyncSessionLocal() as db:
        # Scan
        scan_result = await db.execute(select(Scan).where(Scan.id == sid))
        scan: Scan | None = scan_result.scalar_one_or_none()
        if scan is None:
            raise ValueError(f"Scan {scan_id} not found")

        # Vehicle
        veh_result = await db.execute(
            select(Vehicle).where(Vehicle.id == scan.vehicle_id)
        )
        vehicle: Vehicle | None = veh_result.scalar_one_or_none()

        # Images
        img_result = await db.execute(
            select(ScanImage).where(ScanImage.scan_id == sid)
        )
        images: list[ScanImage] = list(img_result.scalars().all())

        # Damage records
        dmg_result = await db.execute(
            select(DamageRecord).where(DamageRecord.scan_id == sid)
        )
        damages: list[DamageRecord] = list(dmg_result.scalars().all())

        # Diff
        diff_result = await db.execute(
            select(DamageDiff)
            .where(DamageDiff.scan_id_new == sid)
            .order_by(DamageDiff.computed_at.desc())
            .limit(1)
        )
        diff: DamageDiff | None = diff_result.scalar_one_or_none()

    # ── Download images ──────────────────────────────────────────────────────

    images_by_angle: dict[str, str] = {}
    image_b64_by_id: dict[str, str] = {}

    download_tasks = [
        (img.camera_angle.value, img.full_image_path, img.id)
        for img in images
    ]
    raw_images = await asyncio.gather(
        *[_download(settings.BUCKET_FULL_IMAGES, path) for _, path, _ in download_tasks]
    )
    for (angle, _, img_id), raw in zip(download_tasks, raw_images):
        if raw:
            b64 = _b64(raw)
            images_by_angle[angle] = b64
            image_b64_by_id[str(img_id)] = b64

    # ── Download crop images ─────────────────────────────────────────────────

    raw_crops = await asyncio.gather(
        *[_download(settings.BUCKET_CROPS, d.crop_image_path) for d in damages]
    )
    crop_b64_by_id: dict[str, str] = {
        str(d.id): _b64(raw) for d, raw in zip(damages, raw_crops) if raw
    }

    # ── Build damage list ────────────────────────────────────────────────────

    image_id_to_angle = {str(img.id): img.camera_angle.value for img in images}

    damage_ctx: list[dict[str, Any]] = []
    for d in damages:
        angle = image_id_to_angle.get(str(d.scan_image_id), "unknown")
        damage_ctx.append({
            "id": str(d.id),
            "cls": d.damage_class.value,
            "confidence": d.confidence,
            "confidence_pct": f"{d.confidence * 100:.1f}%",
            "bbox": [d.bbox_x1, d.bbox_y1, d.bbox_x2, d.bbox_y2],
            "mask_area_px": d.mask_area_px,
            "mask_area_pct": d.mask_area_pct,
            "is_new": d.is_new_damage,
            "angle": angle,
            "crop_b64": crop_b64_by_id.get(str(d.id), ""),
            "full_image_b64": image_b64_by_id.get(str(d.scan_image_id), ""),
        })

    # ── Summary by class ─────────────────────────────────────────────────────

    grouped: dict[str, list[DamageRecord]] = defaultdict(list)
    for d in damages:
        grouped[d.damage_class.value].append(d)

    summary_by_class = [
        {
            "cls": cls,
            "count": len(recs),
            "total_area_px": sum(r.mask_area_px for r in recs),
            "avg_confidence": sum(r.confidence for r in recs) / len(recs),
        }
        for cls, recs in sorted(grouped.items())
    ]

    # ── Diff context ─────────────────────────────────────────────────────────

    diff_ctx: dict[str, Any] | None = None
    if diff:
        s = diff.diff_summary
        diff_ctx = {
            "total_new": s.get("total_new", 0),
            "total_resolved": s.get("total_resolved", 0),
            "total_existing": s.get("total_existing", 0),
            "prior_scan_id": s.get("prior_scan_id"),
        }

    has_new = any(d["is_new"] is True for d in damage_ctx)
    new_count = sum(1 for d in damage_ctx if d["is_new"] is True)
    triggered_at = scan.triggered_at.astimezone(timezone.utc)
    scan_url = f"{FRONTEND_URL}/scans/{scan_id}"

    return {
        "plate_number": vehicle.plate_number if vehicle else "UNKNOWN",
        "scan_id": scan_id,
        "scan_date": triggered_at.strftime("%d %B %Y"),
        "scan_time": triggered_at.strftime("%H:%M:%S UTC"),
        "location_tag": scan.location_tag,
        "has_new_damage": has_new,
        "total_damages": len(damages),
        "new_damages": new_count,
        "camera_count": scan.camera_count,
        "images_by_angle": images_by_angle,
        "damages": damage_ctx,
        "summary_by_class": summary_by_class,
        "diff": diff_ctx,
        "qr_b64": _make_qr(scan_url),
        "report_url": scan_url,
        "generated_at": datetime.now(timezone.utc).strftime("%d %b %Y %H:%M UTC"),
        "company_name": COMPANY_NAME,
    }


# ── HTML → PDF ────────────────────────────────────────────────────────────────

def _render_pdf(html_string: str, output_path: Path) -> None:
    """Synchronous WeasyPrint render — run in a thread pool executor."""
    HTML(string=html_string).write_pdf(str(output_path))


async def generate_report(scan_id: str, output_path: Path) -> Path:
    """Assemble context, render template, write PDF. Returns output_path."""
    logger.info("report_generation_started", scan_id=scan_id)

    context = await _build_context(scan_id)

    env = Environment(
        loader=FileSystemLoader(str(TEMPLATES_DIR)),
        autoescape=select_autoescape(["html"]),
    )
    template = env.get_template("report.html")
    html_string = template.render(**context)

    loop = asyncio.get_event_loop()
    await loop.run_in_executor(None, _render_pdf, html_string, output_path)

    logger.info(
        "report_generation_complete",
        scan_id=scan_id,
        output_path=str(output_path),
        size_kb=round(output_path.stat().st_size / 1024, 1),
    )
    return output_path


# ── FastAPI endpoint ──────────────────────────────────────────────────────────

@router.post("/{scan_id}/report")
async def download_report(
    scan_id: str,
    background_tasks: BackgroundTasks,
) -> FileResponse:
    """Generate and stream a PDF inspection report for the given scan."""
    try:
        uuid.UUID(scan_id)
    except ValueError:
        raise HTTPException(status_code=422, detail="Invalid scan_id format")

    tmp = tempfile.NamedTemporaryFile(
        suffix=".pdf", prefix=f"report_{scan_id[:8]}_", delete=False
    )
    tmp_path = Path(tmp.name)
    tmp.close()

    try:
        await generate_report(scan_id, tmp_path)
    except ValueError as exc:
        tmp_path.unlink(missing_ok=True)
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except Exception as exc:
        tmp_path.unlink(missing_ok=True)
        logger.error("report_generation_failed", scan_id=scan_id, error=str(exc))
        raise HTTPException(status_code=500, detail="Report generation failed") from exc

    background_tasks.add_task(tmp_path.unlink, missing_ok=True)

    filename = f"inspection_report_{scan_id[:8]}.pdf"
    return FileResponse(
        path=tmp_path,
        media_type="application/pdf",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )

"""Async CRUD operations for the car damage detection backend.

All functions accept an AsyncSession and return ORM model instances.
Redis is used as a cache layer for plate→vehicle lookups (TTL 1 hour).
MinIO stores all image bytes; only object keys are persisted in PostgreSQL.
"""

from __future__ import annotations

import base64
import io
import json
import uuid
from datetime import datetime, timezone
from typing import Any

import redis.asyncio as aioredis
import structlog
from PIL import Image
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from core.config import settings
from db.models import (
    AlertLog,
    CameraAngle,
    DamageClass,
    DamageDiff,
    DamageRecord,
    Scan,
    ScanImage,
    ScanStatus,
    Vehicle,
    WebhookRegistration,
)
from db.schemas import InferenceDamageResult, InspectionResultIn
from storage import minio_client

logger = structlog.get_logger(__name__)

_VEHICLE_CACHE_TTL = 3600  # seconds


# ── Internal helpers ──────────────────────────────────────────────────────────

def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _vehicle_to_dict(v: Vehicle) -> dict[str, Any]:
    return {
        "id": str(v.id),
        "plate_number": v.plate_number,
        "first_seen": v.first_seen.isoformat(),
        "last_seen": v.last_seen.isoformat(),
        "total_scans": v.total_scans,
    }


def compute_iou(box1: list[int], box2: list[int]) -> float:
    """Compute Intersection-over-Union for two [x1,y1,x2,y2] bounding boxes."""
    ix1 = max(box1[0], box2[0])
    iy1 = max(box1[1], box2[1])
    ix2 = min(box1[2], box2[2])
    iy2 = min(box1[3], box2[3])
    if ix2 <= ix1 or iy2 <= iy1:
        return 0.0
    intersection = (ix2 - ix1) * (iy2 - iy1)
    area1 = (box1[2] - box1[0]) * (box1[3] - box1[1])
    area2 = (box2[2] - box2[0]) * (box2[3] - box2[1])
    union = area1 + area2 - intersection
    return intersection / union if union > 0 else 0.0


def _make_thumbnail(image_bytes: bytes) -> bytes:
    img = Image.open(io.BytesIO(image_bytes)).convert("RGB")
    img.thumbnail((settings.THUMBNAIL_WIDTH, settings.THUMBNAIL_HEIGHT), Image.LANCZOS)
    buf = io.BytesIO()
    img.save(buf, format="JPEG", quality=75)
    return buf.getvalue()


# ── Vehicle ───────────────────────────────────────────────────────────────────

async def get_or_create_vehicle(
    plate_number: str,
    db: AsyncSession,
    redis: aioredis.Redis,
) -> Vehicle:
    cache_key = f"vehicle:plate:{plate_number}"
    cached = await redis.get(cache_key)
    if cached:
        data = json.loads(cached)
        result = await db.execute(
            select(Vehicle).where(Vehicle.id == uuid.UUID(data["id"]))
        )
        vehicle = result.scalar_one_or_none()
        if vehicle:
            return vehicle

    result = await db.execute(
        select(Vehicle).where(Vehicle.plate_number == plate_number)
    )
    vehicle = result.scalar_one_or_none()

    if vehicle is None:
        vehicle = Vehicle(plate_number=plate_number)
        db.add(vehicle)
        await db.flush()
        await db.refresh(vehicle)
        logger.info("vehicle_created", plate=plate_number, id=str(vehicle.id))
    else:
        logger.debug("vehicle_cache_miss_db_hit", plate=plate_number)

    await redis.setex(cache_key, _VEHICLE_CACHE_TTL, json.dumps(_vehicle_to_dict(vehicle)))
    return vehicle


async def get_vehicle_by_id(vehicle_id: uuid.UUID, db: AsyncSession) -> Vehicle | None:
    result = await db.execute(select(Vehicle).where(Vehicle.id == vehicle_id))
    return result.scalar_one_or_none()


async def list_vehicles(
    db: AsyncSession,
    plate_filter: str | None = None,
    offset: int = 0,
    limit: int = 20,
) -> tuple[list[Vehicle], int]:
    q = select(Vehicle)
    count_q = select(func.count()).select_from(Vehicle)
    if plate_filter:
        like = f"%{plate_filter.upper()}%"
        q = q.where(Vehicle.plate_number.like(like))
        count_q = count_q.where(Vehicle.plate_number.like(like))
    q = q.offset(offset).limit(limit).order_by(Vehicle.last_seen.desc())
    rows = await db.execute(q)
    total_row = await db.execute(count_q)
    return list(rows.scalars().all()), total_row.scalar_one()


# ── Scan ──────────────────────────────────────────────────────────────────────

async def create_scan(
    vehicle_id: uuid.UUID,
    db: AsyncSession,
    location_tag: str | None = None,
    camera_count: int = 0,
) -> Scan:
    scan = Scan(
        vehicle_id=vehicle_id,
        location_tag=location_tag,
        camera_count=camera_count,
        status=ScanStatus.processing,
    )
    db.add(scan)
    await db.flush()
    await db.refresh(scan)
    logger.info("scan_created", scan_id=str(scan.id), vehicle_id=str(vehicle_id))
    return scan


async def get_scan(scan_id: uuid.UUID, db: AsyncSession) -> Scan | None:
    result = await db.execute(
        select(Scan)
        .where(Scan.id == scan_id)
        .options(selectinload(Scan.images), selectinload(Scan.damage_records))
    )
    return result.scalar_one_or_none()


async def get_scans_for_vehicle(
    vehicle_id: uuid.UUID,
    db: AsyncSession,
    limit: int = 10,
) -> list[Scan]:
    result = await db.execute(
        select(Scan)
        .where(Scan.vehicle_id == vehicle_id)
        .order_by(Scan.triggered_at.desc())
        .limit(limit)
    )
    return list(result.scalars().all())


async def update_scan_status(
    scan_id: uuid.UUID,
    status: ScanStatus,
    db: AsyncSession,
) -> Scan | None:
    scan = await db.get(Scan, scan_id)
    if scan is None:
        return None
    scan.status = status
    if status in (ScanStatus.complete, ScanStatus.failed):
        scan.completed_at = _utcnow()
    await db.flush()
    return scan


# ── ScanImage ─────────────────────────────────────────────────────────────────

async def add_scan_image(
    scan_id: uuid.UUID,
    camera_angle: CameraAngle,
    image_bytes: bytes,
    db: AsyncSession,
    captured_at: datetime | None = None,
) -> ScanImage:
    image_id = uuid.uuid4()
    ts = (captured_at or _utcnow()).strftime("%Y%m%dT%H%M%S")
    full_key = f"{scan_id}/{camera_angle.value}/{ts}_{image_id}.jpg"
    thumb_key = f"{scan_id}/{camera_angle.value}/{ts}_{image_id}_thumb.jpg"

    thumb_bytes = _make_thumbnail(image_bytes)

    await minio_client.upload_image(
        settings.BUCKET_FULL_IMAGES, full_key, image_bytes, "image/jpeg"
    )
    await minio_client.upload_image(
        settings.BUCKET_THUMBNAILS, thumb_key, thumb_bytes, "image/jpeg"
    )

    record = ScanImage(
        id=image_id,
        scan_id=scan_id,
        camera_angle=camera_angle,
        full_image_path=full_key,
        thumbnail_path=thumb_key,
        captured_at=captured_at or _utcnow(),
    )
    db.add(record)
    await db.flush()
    logger.info("scan_image_stored", scan_id=str(scan_id), angle=camera_angle.value)
    return record


# ── DamageRecord ──────────────────────────────────────────────────────────────

async def add_damage_record(
    scan_id: uuid.UUID,
    scan_image_id: uuid.UUID,
    damage: InferenceDamageResult,
    db: AsyncSession,
) -> DamageRecord:
    crop_bytes = base64.b64decode(damage.crop_b64)
    crop_key = f"{scan_id}/{damage.annotation_id}.png"
    await minio_client.upload_image(
        settings.BUCKET_CROPS, crop_key, crop_bytes, "image/png"
    )

    record = DamageRecord(
        scan_id=scan_id,
        scan_image_id=scan_image_id,
        damage_class=DamageClass(damage.class_name),
        confidence=damage.confidence,
        bbox_x1=damage.bbox_xyxy[0],
        bbox_y1=damage.bbox_xyxy[1],
        bbox_x2=damage.bbox_xyxy[2],
        bbox_y2=damage.bbox_xyxy[3],
        polygon_points=damage.polygon_points,
        mask_area_px=damage.mask_area_px,
        mask_area_pct=damage.mask_area_pct,
        crop_image_path=crop_key,
        is_new_damage=None,
    )
    db.add(record)
    await db.flush()
    return record


# ── Damage diff ───────────────────────────────────────────────────────────────

async def run_damage_diff(
    vehicle_id: uuid.UUID,
    new_scan_id: uuid.UUID,
    db: AsyncSession,
) -> dict[str, Any]:
    """Compare new scan's damages against most-recent prior scan.

    Greedy IoU matching (threshold 0.3):
      - Matched new damage  → is_new_damage = False
      - Unmatched new damage → is_new_damage = True
    Creates a DamageDiff record and returns the diff summary dict.
    """
    # Fetch new scan's damage records
    new_result = await db.execute(
        select(DamageRecord).where(DamageRecord.scan_id == new_scan_id)
    )
    new_damages: list[DamageRecord] = list(new_result.scalars().all())

    # Fetch most recent prior completed scan for this vehicle
    prior_result = await db.execute(
        select(Scan)
        .where(
            Scan.vehicle_id == vehicle_id,
            Scan.id != new_scan_id,
            Scan.status == ScanStatus.complete,
        )
        .order_by(Scan.triggered_at.desc())
        .limit(1)
    )
    prior_scan = prior_result.scalar_one_or_none()

    old_scan_id: uuid.UUID | None = None
    old_damages: list[DamageRecord] = []

    if prior_scan is not None:
        old_scan_id = prior_scan.id
        old_result = await db.execute(
            select(DamageRecord).where(DamageRecord.scan_id == prior_scan.id)
        )
        old_damages = list(old_result.scalars().all())

    # Greedy IoU matching
    def _box(d: DamageRecord) -> list[int]:
        return [d.bbox_x1, d.bbox_y1, d.bbox_x2, d.bbox_y2]

    matched_old_indices: set[int] = set()
    matched_new_indices: set[int] = set()

    for ni, nd in enumerate(new_damages):
        best_iou = 0.3
        best_oi = -1
        for oi, od in enumerate(old_damages):
            if oi in matched_old_indices:
                continue
            if od.damage_class != nd.damage_class:
                continue
            iou = compute_iou(_box(nd), _box(od))
            if iou > best_iou:
                best_iou = iou
                best_oi = oi
        if best_oi >= 0:
            matched_old_indices.add(best_oi)
            matched_new_indices.add(ni)

    new_damage_count = 0
    for ni, nd in enumerate(new_damages):
        is_new = ni not in matched_new_indices
        nd.is_new_damage = is_new
        if is_new:
            new_damage_count += 1

    resolved_count = len(old_damages) - len(matched_old_indices)

    new_damage_details = [
        {
            "id": str(nd.id),
            "class": nd.damage_class.value,
            "confidence": nd.confidence,
            "bbox": [nd.bbox_x1, nd.bbox_y1, nd.bbox_x2, nd.bbox_y2],
        }
        for ni, nd in enumerate(new_damages)
        if ni not in matched_new_indices
    ]

    diff_summary: dict[str, Any] = {
        "total_new": new_damage_count,
        "total_resolved": resolved_count,
        "total_existing": len(matched_new_indices),
        "new_damage_details": new_damage_details,
        "prior_scan_id": str(old_scan_id) if old_scan_id else None,
    }

    diff = DamageDiff(
        vehicle_id=vehicle_id,
        scan_id_old=old_scan_id,
        scan_id_new=new_scan_id,
        new_damage_count=new_damage_count,
        resolved_damage_count=resolved_count,
        diff_summary=diff_summary,
    )
    db.add(diff)
    await db.flush()

    logger.info(
        "damage_diff_computed",
        vehicle_id=str(vehicle_id),
        new_scan_id=str(new_scan_id),
        prior_scan_id=str(old_scan_id) if old_scan_id else None,
        new_damage_count=new_damage_count,
        resolved_count=resolved_count,
    )
    return diff_summary


# ── Vehicle history ───────────────────────────────────────────────────────────

async def get_vehicle_history(
    plate_number: str,
    db: AsyncSession,
    limit: int = 10,
) -> list[dict[str, Any]]:
    result = await db.execute(
        select(Vehicle).where(Vehicle.plate_number == plate_number)
    )
    vehicle = result.scalar_one_or_none()
    if vehicle is None:
        return []

    scans_result = await db.execute(
        select(Scan)
        .where(Scan.vehicle_id == vehicle.id)
        .order_by(Scan.triggered_at.desc())
        .limit(limit)
    )
    scans = list(scans_result.scalars().all())

    history = []
    for scan in scans:
        total_res = await db.execute(
            select(func.count()).select_from(DamageRecord).where(DamageRecord.scan_id == scan.id)
        )
        total_dmg = total_res.scalar_one()

        new_res = await db.execute(
            select(func.count()).select_from(DamageRecord).where(
                DamageRecord.scan_id == scan.id,
                DamageRecord.is_new_damage.is_(True),
            )
        )
        new_dmg = new_res.scalar_one()
        history.append({
            "scan_id": str(scan.id),
            "triggered_at": scan.triggered_at.isoformat(),
            "status": scan.status.value,
            "total_damages": total_dmg,
            "new_damages": new_dmg,
            "location_tag": scan.location_tag,
        })
    return history


# ── Webhooks / alerts ─────────────────────────────────────────────────────────

async def register_webhook(
    url: str,
    secret: str,
    db: AsyncSession,
) -> WebhookRegistration:
    existing = await db.execute(
        select(WebhookRegistration).where(
            WebhookRegistration.url == url,
            WebhookRegistration.is_active.is_(True),
        )
    )
    hook = existing.scalars().first()
    if hook is not None:
        logger.info("webhook_already_registered", url=url, id=str(hook.id))
        return hook

    hook = WebhookRegistration(url=url, secret=secret)
    db.add(hook)
    await db.flush()
    await db.refresh(hook)
    logger.info("webhook_registered", url=url, id=str(hook.id))
    return hook


async def get_active_webhooks(db: AsyncSession) -> list[WebhookRegistration]:
    result = await db.execute(
        select(WebhookRegistration).where(WebhookRegistration.is_active.is_(True))
    )
    return list(result.scalars().all())


async def log_alert(
    scan_id: uuid.UUID,
    vehicle_id: uuid.UUID,
    webhook_id: uuid.UUID,
    status_code: int,
    payload_summary: dict[str, Any],
    db: AsyncSession,
) -> AlertLog:
    entry = AlertLog(
        scan_id=scan_id,
        vehicle_id=vehicle_id,
        webhook_id=webhook_id,
        status_code=status_code,
        payload_summary=payload_summary,
    )
    db.add(entry)
    await db.flush()
    return entry


async def get_recent_alerts(db: AsyncSession, limit: int = 20) -> list[AlertLog]:
    result = await db.execute(
        select(AlertLog)
        .order_by(AlertLog.triggered_at.desc())
        .limit(limit)
    )
    return list(result.scalars().all())


# ── Full scan ingestion (orchestration used by POST /scans) ───────────────────

async def ingest_scan(
    plate_number: str,
    inspection_results: list[InspectionResultIn],
    images_by_camera: dict[str, bytes],
    db: AsyncSession,
    redis: aioredis.Redis,
    location_tag: str | None = None,
) -> tuple[Scan, dict[str, Any]]:
    """End-to-end: vehicle lookup → scan → images → damages → diff → status=complete."""
    vehicle = await get_or_create_vehicle(plate_number, db, redis)

    scan = await create_scan(
        vehicle_id=vehicle.id,
        db=db,
        location_tag=location_tag,
        camera_count=len(inspection_results),
    )

    for insp in inspection_results:
        image_bytes = images_by_camera.get(insp.camera_id)
        if image_bytes is None:
            logger.warning("no_image_for_camera", camera_id=insp.camera_id)
            continue

        scan_image = await add_scan_image(
            scan_id=scan.id,
            camera_angle=insp.angle,
            image_bytes=image_bytes,
            db=db,
            captured_at=insp.captured_at,
        )
        for dmg in insp.damages:
            await add_damage_record(
                scan_id=scan.id,
                scan_image_id=scan_image.id,
                damage=dmg,
                db=db,
            )

    diff_summary = await run_damage_diff(vehicle.id, scan.id, db)
    await update_scan_status(scan.id, ScanStatus.complete, db)

    vehicle.total_scans += 1
    vehicle.last_seen = _utcnow()
    await db.flush()

    await db.commit()

    # Invalidate vehicle cache so next read gets fresh total_scans
    cache_key = f"vehicle:plate:{plate_number}"
    await redis.delete(cache_key)

    logger.info(
        "scan_ingested",
        scan_id=str(scan.id),
        plate=plate_number,
        new_damages=diff_summary.get("total_new", 0),
    )
    return scan, diff_summary


# ── Dashboard summary ───────────────────────────────────────────────────────

async def get_dashboard_summary(db: AsyncSession, recent_limit: int = 6) -> dict[str, Any]:
    total_vehicles = await db.scalar(select(func.count()).select_from(Vehicle))
    total_scans = await db.scalar(select(func.count()).select_from(Scan))
    total_damages = await db.scalar(select(func.count()).select_from(DamageRecord))
    active_alerts = await db.scalar(select(func.count()).select_from(AlertLog))

    recent_scans_result = await db.execute(
        select(Scan.id, Scan.vehicle_id, Scan.triggered_at, Vehicle.plate_number)
        .join(Vehicle, Vehicle.id == Scan.vehicle_id)
        .order_by(Scan.triggered_at.desc())
        .limit(recent_limit)
    )
    recent_scans = []
    for scan_id, vehicle_id, triggered_at, plate_number in recent_scans_result.all():
        new_damage_count = await db.scalar(
            select(func.count())
            .select_from(DamageRecord)
            .where(DamageRecord.scan_id == scan_id, DamageRecord.is_new_damage.is_(True))
        )
        thumbnail = await db.scalar(
            select(ScanImage.thumbnail_path)
            .where(ScanImage.scan_id == scan_id)
            .order_by(ScanImage.captured_at)
            .limit(1)
        )
        recent_scans.append({
            "scan_id": str(scan_id),
            "vehicle_id": str(vehicle_id),
            "plate_number": plate_number,
            "triggered_at": triggered_at.isoformat(),
            "new_damage_count": new_damage_count or 0,
            "thumbnail_path": thumbnail,
        })

    return {
        "total_vehicles": total_vehicles or 0,
        "total_scans": total_scans or 0,
        "total_damages": total_damages or 0,
        "active_alerts": active_alerts or 0,
        "recent_scans": recent_scans,
    }

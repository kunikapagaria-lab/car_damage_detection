"""Scan creation, retrieval, damage listing, and diff endpoints."""


import uuid

import structlog
from fastapi import APIRouter, Depends, File, Form, Request, UploadFile
from sqlalchemy.ext.asyncio import AsyncSession

import db.crud as crud
from core.config import settings
from core.deps import get_db, get_redis, limiter
from core.response import err, ok
from db.schemas import (
    DamageDiffOut,
    DamageRecordOut,
    ScanCreateRequest,
    ScanDetailOut,
    ScanOut,
    ScanStatusUpdate,
)

logger = structlog.get_logger(__name__)
router = APIRouter(prefix="/api/v1/scans", tags=["scans"])


@router.post("")
@limiter.limit("60/minute")
async def create_scan(
    request: Request,
    metadata: str = Form(..., description="JSON-encoded ScanCreateRequest"),
    images: list[UploadFile] = File(..., description="Camera images, filename = camera_id.jpg"),
    db: AsyncSession = Depends(get_db),
    redis=Depends(get_redis),
):
    try:
        scan_req = ScanCreateRequest.model_validate_json(metadata)
    except Exception as exc:
        return err("invalid_metadata", str(exc), status_code=422)

    images_by_camera: dict[str, bytes] = {}
    for upload in images:
        if upload.size and upload.size > settings.max_upload_bytes:
            return err("file_too_large", f"{upload.filename} exceeds {settings.MAX_UPLOAD_SIZE_MB} MB", status_code=413)
        raw = await upload.read()
        if not raw:
            continue
        camera_id = (upload.filename or "").split(".")[0]
        images_by_camera[camera_id] = raw

    if not images_by_camera:
        return err("no_images", "At least one valid image file is required", status_code=422)

    try:
        scan, diff_summary = await crud.ingest_scan(
            plate_number=scan_req.plate_number,
            inspection_results=scan_req.inspection_results,
            images_by_camera=images_by_camera,
            db=db,
            redis=redis,
            location_tag=scan_req.location_tag,
        )
    except Exception as exc:
        logger.error("scan_ingest_failed", error=str(exc))
        return err("ingest_failed", str(exc), status_code=500)

    # Fire webhooks if any new damage found
    if diff_summary.get("total_new", 0) > 0:
        from api.routes.alerts import fire_webhooks
        await fire_webhooks(
            scan_id=scan.id,
            vehicle_id=scan.vehicle_id,
            plate_number=scan_req.plate_number,
            diff_summary=diff_summary,
            db=db,
        )

    scan_detail = await crud.get_scan(scan.id, db)
    return ok(ScanDetailOut.model_validate(scan_detail).model_dump(mode="json"), status_code=201)


@router.get("/{scan_id}")
@limiter.limit("60/minute")
async def get_scan(
    request: Request,
    scan_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
):
    scan = await crud.get_scan(scan_id, db)
    if scan is None:
        return err("scan_not_found", f"No scan with id {scan_id}", status_code=404)
    return ok(ScanDetailOut.model_validate(scan).model_dump(mode="json"))


@router.get("/{scan_id}/damages")
@limiter.limit("60/minute")
async def get_scan_damages(
    request: Request,
    scan_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
):
    scan = await crud.get_scan(scan_id, db)
    if scan is None:
        return err("scan_not_found", f"No scan with id {scan_id}", status_code=404)
    data = [DamageRecordOut.model_validate(d).model_dump(mode="json") for d in scan.damage_records]
    return ok(data, meta={"count": len(data)})


@router.get("/{scan_id}/diff")
@limiter.limit("60/minute")
async def get_scan_diff(
    request: Request,
    scan_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
):
    from sqlalchemy import select
    from db.models import DamageDiff

    result = await db.execute(
        select(DamageDiff)
        .where(DamageDiff.scan_id_new == scan_id)
        .order_by(DamageDiff.computed_at.desc())
        .limit(1)
    )
    diff = result.scalar_one_or_none()
    if diff is None:
        return err("diff_not_found", "No damage diff computed for this scan yet", status_code=404)
    return ok(DamageDiffOut.model_validate(diff).model_dump(mode="json"))


@router.patch("/{scan_id}/status")
@limiter.limit("60/minute")
async def patch_scan_status(
    request: Request,
    scan_id: uuid.UUID,
    body: ScanStatusUpdate,
    db: AsyncSession = Depends(get_db),
):
    scan = await crud.update_scan_status(scan_id, body.status, db)
    if scan is None:
        return err("scan_not_found", f"No scan with id {scan_id}", status_code=404)
    await db.commit()
    return ok(ScanOut.model_validate(scan).model_dump(mode="json"))

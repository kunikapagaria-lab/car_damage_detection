"""Vehicle lookup and history endpoints."""


import uuid

import structlog
from fastapi import APIRouter, Depends, Query, Request
from sqlalchemy.ext.asyncio import AsyncSession

import db.crud as crud
from core.deps import get_db, get_redis, limiter
from core.response import err, ok
from db.schemas import PaginationMeta, VehicleHistoryEntry, VehicleOut, VehicleWithHistory

logger = structlog.get_logger(__name__)
router = APIRouter(prefix="/api/v1/vehicles", tags=["vehicles"])


@router.get("")
@limiter.limit("60/minute")
async def list_vehicles(
    request: Request,
    plate: str | None = Query(None, description="Partial plate number filter"),
    page: int = Query(1, ge=1),
    limit: int = Query(20, ge=1, le=100),
    db: AsyncSession = Depends(get_db),
):
    offset = (page - 1) * limit
    vehicles, total = await crud.list_vehicles(db, plate_filter=plate, offset=offset, limit=limit)
    data = [VehicleOut.model_validate(v).model_dump(mode="json") for v in vehicles]
    return ok(data, meta=PaginationMeta(page=page, limit=limit, total=total).model_dump())


@router.get("/{vehicle_id}")
@limiter.limit("60/minute")
async def get_vehicle(
    request: Request,
    vehicle_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
):
    vehicle = await crud.get_vehicle_by_id(vehicle_id, db)
    if vehicle is None:
        return err("vehicle_not_found", f"No vehicle with id {vehicle_id}", status_code=404)
    return ok(VehicleOut.model_validate(vehicle).model_dump(mode="json"))


@router.get("/{vehicle_id}/scans")
@limiter.limit("60/minute")
async def get_vehicle_scans(
    request: Request,
    vehicle_id: uuid.UUID,
    limit: int = Query(10, ge=1, le=50),
    db: AsyncSession = Depends(get_db),
):
    vehicle = await crud.get_vehicle_by_id(vehicle_id, db)
    if vehicle is None:
        return err("vehicle_not_found", f"No vehicle with id {vehicle_id}", status_code=404)

    scans = await crud.get_scans_for_vehicle(vehicle_id, db, limit=limit)
    from db.schemas import ScanOut
    data = [ScanOut.model_validate(s).model_dump(mode="json") for s in scans]
    return ok(data)


@router.get("/{vehicle_id}/scans/latest")
@limiter.limit("60/minute")
async def get_latest_scan(
    request: Request,
    vehicle_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
):
    vehicle = await crud.get_vehicle_by_id(vehicle_id, db)
    if vehicle is None:
        return err("vehicle_not_found", f"No vehicle with id {vehicle_id}", status_code=404)

    scans = await crud.get_scans_for_vehicle(vehicle_id, db, limit=1)
    if not scans:
        return err("no_scans", "This vehicle has no scans yet", status_code=404)

    scan = await crud.get_scan(scans[0].id, db)
    from db.schemas import ScanDetailOut
    return ok(ScanDetailOut.model_validate(scan).model_dump(mode="json"))

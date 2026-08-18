"""Async pytest tests for CRUD operations.

Uses a real PostgreSQL test database (DATABASE_URL env var or defaults to test_car_damage).
Tests run against DummyPredictor output structures — no GPU, no real cameras required.
"""

from __future__ import annotations

import os
import uuid
from collections.abc import AsyncGenerator
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

os.environ.setdefault("PREDICTOR_MODE", "dummy")

TEST_DB_URL = os.environ.get(
    "TEST_DATABASE_URL",
    "postgresql+asyncpg://postgres:postgres@localhost:5432/test_car_damage",
)


# ── Engine / session fixtures ─────────────────────────────────────────────────

@pytest_asyncio.fixture(scope="session")
async def engine():
    from db.database import Base
    import db.models  # noqa: F401 — register models

    eng = create_async_engine(TEST_DB_URL, echo=False)
    async with eng.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    yield eng
    async with eng.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
    await eng.dispose()


@pytest_asyncio.fixture
async def db(engine) -> AsyncGenerator[AsyncSession, None]:
    factory = async_sessionmaker(bind=engine, class_=AsyncSession, expire_on_commit=False)
    async with factory() as session:
        yield session
        await session.rollback()


@pytest_asyncio.fixture
def mock_redis():
    redis = AsyncMock()
    redis.get = AsyncMock(return_value=None)
    redis.setex = AsyncMock()
    redis.delete = AsyncMock()
    redis.ping = AsyncMock()
    return redis


@pytest_asyncio.fixture
def mock_minio():
    with patch("db.crud.minio_client") as m:
        m.upload_image = AsyncMock(side_effect=lambda bucket, key, *a, **kw: key)
        yield m


# ── Pure-function tests (no DB) ───────────────────────────────────────────────

def test_compute_iou_perfect_overlap():
    from db.crud import compute_iou
    box = [10, 10, 50, 50]
    assert compute_iou(box, box) == pytest.approx(1.0)


def test_compute_iou_no_overlap():
    from db.crud import compute_iou
    assert compute_iou([0, 0, 10, 10], [20, 20, 30, 30]) == pytest.approx(0.0)


def test_compute_iou_partial():
    from db.crud import compute_iou
    iou = compute_iou([0, 0, 20, 20], [10, 10, 30, 30])
    assert 0.0 < iou < 1.0
    # intersection = 10*10 = 100; union = 400+400-100 = 700
    assert iou == pytest.approx(100 / 700, rel=1e-4)


def test_compute_iou_touching_edges():
    from db.crud import compute_iou
    assert compute_iou([0, 0, 10, 10], [10, 0, 20, 10]) == pytest.approx(0.0)


def test_compute_iou_contained():
    from db.crud import compute_iou
    outer = [0, 0, 100, 100]
    inner = [25, 25, 75, 75]
    iou = compute_iou(outer, inner)
    # intersection = 50*50 = 2500; outer=10000, inner=2500, union=10000
    assert iou == pytest.approx(2500 / 10000, rel=1e-4)


# ── Vehicle CRUD ──────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_get_or_create_vehicle_creates_new(db, mock_redis):
    from db.crud import get_or_create_vehicle

    plate = f"TN09AB{uuid.uuid4().hex[:4].upper()}"
    vehicle = await get_or_create_vehicle(plate, db, mock_redis)
    await db.commit()

    assert vehicle.plate_number == plate
    assert vehicle.id is not None
    mock_redis.setex.assert_called_once()


@pytest.mark.asyncio
async def test_get_or_create_vehicle_returns_existing(db, mock_redis):
    from db.crud import get_or_create_vehicle

    plate = f"MH12CD{uuid.uuid4().hex[:4].upper()}"
    v1 = await get_or_create_vehicle(plate, db, mock_redis)
    await db.commit()

    v2 = await get_or_create_vehicle(plate, db, mock_redis)
    assert v1.id == v2.id


@pytest.mark.asyncio
async def test_vehicle_cache_hit(db, mock_redis):
    """When Redis returns a cached entry the DB row is fetched by id."""
    import json
    from db.crud import get_or_create_vehicle

    plate = f"KA01MN{uuid.uuid4().hex[:4].upper()}"
    vehicle = await get_or_create_vehicle(plate, db, mock_redis)
    await db.commit()

    mock_redis.get = AsyncMock(
        return_value=json.dumps({
            "id": str(vehicle.id),
            "plate_number": plate,
            "first_seen": vehicle.first_seen.isoformat(),
            "last_seen": vehicle.last_seen.isoformat(),
            "total_scans": vehicle.total_scans,
        })
    )
    v_cached = await get_or_create_vehicle(plate, db, mock_redis)
    assert v_cached.id == vehicle.id


# ── Scan CRUD ─────────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_create_scan(db, mock_redis):
    from db.crud import create_scan, get_or_create_vehicle
    from db.models import ScanStatus

    plate = f"DL5C{uuid.uuid4().hex[:4].upper()}"
    vehicle = await get_or_create_vehicle(plate, db, mock_redis)
    scan = await create_scan(vehicle.id, db, location_tag="bay_1", camera_count=6)
    await db.commit()

    assert scan.id is not None
    assert scan.vehicle_id == vehicle.id
    assert scan.status == ScanStatus.processing
    assert scan.location_tag == "bay_1"
    assert scan.camera_count == 6


@pytest.mark.asyncio
async def test_update_scan_status(db, mock_redis):
    from db.crud import create_scan, get_or_create_vehicle, update_scan_status
    from db.models import ScanStatus

    plate = f"UP32GH{uuid.uuid4().hex[:4].upper()}"
    vehicle = await get_or_create_vehicle(plate, db, mock_redis)
    scan = await create_scan(vehicle.id, db)
    await db.commit()

    updated = await update_scan_status(scan.id, ScanStatus.complete, db)
    await db.commit()

    assert updated is not None
    assert updated.status == ScanStatus.complete
    assert updated.completed_at is not None


# ── Damage diff ───────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_run_damage_diff_no_prior_scan(db, mock_redis, mock_minio):
    """First scan for a vehicle: all damages marked as new, no prior scan."""
    from db.crud import (
        add_damage_record,
        add_scan_image,
        create_scan,
        get_or_create_vehicle,
        run_damage_diff,
        update_scan_status,
    )
    from db.models import CameraAngle, ScanStatus
    from db.schemas import InferenceDamageResult
    import numpy as np
    import base64, io
    from PIL import Image

    # Create a tiny real PNG for the crop
    img = Image.new("RGB", (50, 50), color=(100, 100, 100))
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    crop_b64 = base64.b64encode(buf.getvalue()).decode()

    plate = f"HR26DA{uuid.uuid4().hex[:4].upper()}"
    vehicle = await get_or_create_vehicle(plate, db, mock_redis)
    scan = await create_scan(vehicle.id, db, camera_count=1)

    fake_jpeg = buf.getvalue()
    scan_image = await add_scan_image(
        scan_id=scan.id,
        camera_angle=CameraAngle.front,
        image_bytes=fake_jpeg,
        db=db,
    )

    dmg = InferenceDamageResult(
        annotation_id=str(uuid.uuid4()),
        class_name="scratch",
        confidence=0.85,
        bbox_xyxy=[10, 10, 60, 60],
        polygon_points=[[10, 10], [60, 10], [60, 60], [10, 60]],
        mask_area_px=2500,
        mask_area_pct=5.0,
        crop_b64=crop_b64,
    )
    await add_damage_record(scan.id, scan_image.id, dmg, db)
    await update_scan_status(scan.id, ScanStatus.complete, db)
    await db.commit()

    diff = await run_damage_diff(vehicle.id, scan.id, db)
    await db.commit()

    assert diff["total_new"] == 1
    assert diff["total_resolved"] == 0
    assert diff["prior_scan_id"] is None


@pytest.mark.asyncio
async def test_run_damage_diff_matched_damage_not_new(db, mock_redis, mock_minio):
    """Second scan with same bounding box — damage should be matched (not new)."""
    import base64, io, uuid
    from PIL import Image
    from db.crud import (
        add_damage_record, add_scan_image, create_scan,
        get_or_create_vehicle, run_damage_diff, update_scan_status,
    )
    from db.models import CameraAngle, ScanStatus
    from db.schemas import InferenceDamageResult

    img = Image.new("RGB", (50, 50), color=(80, 80, 80))
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    crop_b64 = base64.b64encode(buf.getvalue()).decode()
    fake_bytes = buf.getvalue()

    plate = f"RJ14YZ{uuid.uuid4().hex[:4].upper()}"
    vehicle = await get_or_create_vehicle(plate, db, mock_redis)

    # ── Scan 1 ──
    scan1 = await create_scan(vehicle.id, db, camera_count=1)
    img1 = await add_scan_image(scan1.id, CameraAngle.front, fake_bytes, db)
    dmg1 = InferenceDamageResult(
        annotation_id=str(uuid.uuid4()),
        class_name="dent",
        confidence=0.90,
        bbox_xyxy=[100, 100, 200, 200],
        polygon_points=[[100, 100], [200, 100], [200, 200], [100, 200]],
        mask_area_px=10000,
        mask_area_pct=10.0,
        crop_b64=crop_b64,
    )
    await add_damage_record(scan1.id, img1.id, dmg1, db)
    await update_scan_status(scan1.id, ScanStatus.complete, db)
    await db.commit()

    # ── Scan 2 (same box, slightly shifted — high IoU) ──
    scan2 = await create_scan(vehicle.id, db, camera_count=1)
    img2 = await add_scan_image(scan2.id, CameraAngle.front, fake_bytes, db)
    dmg2 = InferenceDamageResult(
        annotation_id=str(uuid.uuid4()),
        class_name="dent",
        confidence=0.88,
        bbox_xyxy=[102, 102, 198, 198],  # IoU ≈ 0.92
        polygon_points=[[102, 102], [198, 102], [198, 198], [102, 198]],
        mask_area_px=9216,
        mask_area_pct=9.2,
        crop_b64=crop_b64,
    )
    await add_damage_record(scan2.id, img2.id, dmg2, db)
    await update_scan_status(scan2.id, ScanStatus.complete, db)
    await db.commit()

    diff = await run_damage_diff(vehicle.id, scan2.id, db)
    await db.commit()

    assert diff["total_new"] == 0, "Existing damage should be matched, not new"
    assert diff["total_existing"] == 1


@pytest.mark.asyncio
async def test_run_damage_diff_new_damage_detected(db, mock_redis, mock_minio):
    """Second scan with a new bounding box that doesn't overlap prior — flagged as new."""
    import base64, io, uuid
    from PIL import Image
    from db.crud import (
        add_damage_record, add_scan_image, create_scan,
        get_or_create_vehicle, run_damage_diff, update_scan_status,
    )
    from db.models import CameraAngle, ScanStatus
    from db.schemas import InferenceDamageResult

    img = Image.new("RGB", (30, 30), color=(50, 50, 50))
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    crop_b64 = base64.b64encode(buf.getvalue()).decode()
    fake_bytes = buf.getvalue()

    plate = f"GJ18BX{uuid.uuid4().hex[:4].upper()}"
    vehicle = await get_or_create_vehicle(plate, db, mock_redis)

    scan1 = await create_scan(vehicle.id, db, camera_count=1)
    img1 = await add_scan_image(scan1.id, CameraAngle.rear, fake_bytes, db)
    await add_damage_record(
        scan1.id, img1.id,
        InferenceDamageResult(
            annotation_id=str(uuid.uuid4()),
            class_name="crack",
            confidence=0.75,
            bbox_xyxy=[0, 0, 50, 50],
            polygon_points=[[0, 0], [50, 0], [50, 50], [0, 50]],
            mask_area_px=2500, mask_area_pct=2.5, crop_b64=crop_b64,
        ),
        db,
    )
    await update_scan_status(scan1.id, ScanStatus.complete, db)
    await db.commit()

    scan2 = await create_scan(vehicle.id, db, camera_count=1)
    img2 = await add_scan_image(scan2.id, CameraAngle.rear, fake_bytes, db)
    # Totally different location
    await add_damage_record(
        scan2.id, img2.id,
        InferenceDamageResult(
            annotation_id=str(uuid.uuid4()),
            class_name="crack",
            confidence=0.80,
            bbox_xyxy=[500, 500, 600, 600],
            polygon_points=[[500, 500], [600, 500], [600, 600], [500, 600]],
            mask_area_px=10000, mask_area_pct=5.0, crop_b64=crop_b64,
        ),
        db,
    )
    await update_scan_status(scan2.id, ScanStatus.complete, db)
    await db.commit()

    diff = await run_damage_diff(vehicle.id, scan2.id, db)
    await db.commit()

    assert diff["total_new"] == 1
    assert diff["total_resolved"] == 1

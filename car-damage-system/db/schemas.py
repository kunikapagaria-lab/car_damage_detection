"""Pydantic v2 request/response schemas for all API models."""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, field_validator

from db.models import CameraAngle, DamageClass, ScanStatus


# ── Shared base ───────────────────────────────────────────────────────────────

class OrmBase(BaseModel):
    model_config = ConfigDict(from_attributes=True)


# ── DamageResult from inference service ──────────────────────────────────────

class InferenceDamageResult(BaseModel):
    annotation_id: str
    class_name: str
    confidence: float = Field(ge=0.0, le=1.0)
    bbox_xyxy: list[int] = Field(min_length=4, max_length=4)
    polygon_points: list[list[int]]
    mask_area_px: int = Field(ge=0)
    mask_area_pct: float = Field(ge=0.0, le=100.0)
    crop_b64: str

    @field_validator("class_name")
    @classmethod
    def validate_class_name(cls, v: str) -> str:
        allowed = {"scratch", "dent", "paint_damage", "crack"}
        if v not in allowed:
            raise ValueError(f"class_name must be one of {allowed}")
        return v


class InferencePlateResult(BaseModel):
    plate_text: str
    confidence: float = Field(ge=0.0, le=1.0)
    bbox: list[int] = Field(min_length=4, max_length=4)


class InspectionResultIn(BaseModel):
    camera_id: str
    angle: CameraAngle
    damages: list[InferenceDamageResult] = []
    plate_result: InferencePlateResult | None = None
    inference_time_ms: float = 0.0
    captured_at: datetime | None = None


# ── Scan creation ─────────────────────────────────────────────────────────────

class ScanCreateRequest(BaseModel):
    plate_number: str = Field(min_length=1, max_length=20)
    location_tag: str | None = None
    inspection_results: list[InspectionResultIn]

    @field_validator("plate_number")
    @classmethod
    def uppercase_plate(cls, v: str) -> str:
        return v.upper().strip()


class ScanStatusUpdate(BaseModel):
    status: ScanStatus


# ── Response schemas ──────────────────────────────────────────────────────────

class VehicleOut(OrmBase):
    id: uuid.UUID
    plate_number: str
    first_seen: datetime
    last_seen: datetime
    total_scans: int


class DamageRecordOut(OrmBase):
    id: uuid.UUID
    scan_id: uuid.UUID
    scan_image_id: uuid.UUID
    damage_class: DamageClass
    confidence: float
    bbox_x1: int
    bbox_y1: int
    bbox_x2: int
    bbox_y2: int
    polygon_points: list[Any]
    mask_area_px: int
    mask_area_pct: float
    crop_image_path: str
    is_new_damage: bool | None


class ScanImageOut(OrmBase):
    id: uuid.UUID
    scan_id: uuid.UUID
    camera_angle: CameraAngle
    full_image_path: str
    thumbnail_path: str
    captured_at: datetime


class ScanOut(OrmBase):
    id: uuid.UUID
    vehicle_id: uuid.UUID
    triggered_at: datetime
    completed_at: datetime | None
    camera_count: int
    status: ScanStatus
    location_tag: str | None


class ScanDetailOut(ScanOut):
    images: list[ScanImageOut] = []
    damage_records: list[DamageRecordOut] = []


class DamageDiffOut(OrmBase):
    id: uuid.UUID
    vehicle_id: uuid.UUID
    scan_id_old: uuid.UUID | None
    scan_id_new: uuid.UUID
    new_damage_count: int
    resolved_damage_count: int
    diff_summary: dict[str, Any]
    computed_at: datetime


class VehicleHistoryEntry(BaseModel):
    scan_id: uuid.UUID
    triggered_at: datetime
    status: ScanStatus
    total_damages: int
    new_damages: int
    location_tag: str | None


class VehicleWithHistory(VehicleOut):
    recent_scans: list[VehicleHistoryEntry] = []


# ── Webhook schemas ───────────────────────────────────────────────────────────

class WebhookRegisterRequest(BaseModel):
    url: str = Field(min_length=10, max_length=2048)
    secret: str = Field(min_length=8, max_length=256)

    @field_validator("url")
    @classmethod
    def must_be_https_or_http(cls, v: str) -> str:
        if not (v.startswith("http://") or v.startswith("https://")):
            raise ValueError("URL must start with http:// or https://")
        return v


class WebhookOut(OrmBase):
    id: uuid.UUID
    url: str
    is_active: bool
    created_at: datetime
    last_triggered_at: datetime | None


class AlertLogOut(OrmBase):
    id: uuid.UUID
    scan_id: uuid.UUID
    vehicle_id: uuid.UUID
    webhook_id: uuid.UUID
    status_code: int
    triggered_at: datetime
    payload_summary: dict[str, Any]


# ── Pagination ────────────────────────────────────────────────────────────────

class PaginationMeta(BaseModel):
    page: int
    limit: int
    total: int

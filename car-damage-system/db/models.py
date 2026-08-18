"""SQLAlchemy ORM models for the car damage detection backend."""

from __future__ import annotations

import enum
import uuid
from datetime import datetime

from sqlalchemy import (
    Boolean,
    DateTime,
    Enum,
    Float,
    ForeignKey,
    Integer,
    String,
    Text,
    func,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from db.database import Base


# ── Enums ─────────────────────────────────────────────────────────────────────

class ScanStatus(str, enum.Enum):
    pending = "pending"
    processing = "processing"
    complete = "complete"
    failed = "failed"


class CameraAngle(str, enum.Enum):
    front = "front"
    rear = "rear"
    left = "left"
    right = "right"
    front_oblique = "front_oblique"
    rear_oblique = "rear_oblique"


class DamageClass(str, enum.Enum):
    scratch = "scratch"
    dent = "dent"
    paint_damage = "paint_damage"
    crack = "crack"


# ── Models ────────────────────────────────────────────────────────────────────

class Vehicle(Base):
    __tablename__ = "vehicles"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    plate_number: Mapped[str] = mapped_column(
        String(20), unique=True, index=True, nullable=False
    )
    first_seen: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    last_seen: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )
    total_scans: Mapped[int] = mapped_column(Integer, default=0, nullable=False)

    scans: Mapped[list[Scan]] = relationship("Scan", back_populates="vehicle", lazy="select")
    damage_diffs: Mapped[list[DamageDiff]] = relationship(
        "DamageDiff", back_populates="vehicle", lazy="select"
    )


class Scan(Base):
    __tablename__ = "scans"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    vehicle_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("vehicles.id", ondelete="CASCADE"), nullable=False, index=True
    )
    triggered_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    completed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    camera_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    status: Mapped[ScanStatus] = mapped_column(
        Enum(ScanStatus, name="scan_status"), default=ScanStatus.pending, nullable=False
    )
    location_tag: Mapped[str | None] = mapped_column(String(128), nullable=True)

    vehicle: Mapped[Vehicle] = relationship("Vehicle", back_populates="scans")
    images: Mapped[list[ScanImage]] = relationship(
        "ScanImage", back_populates="scan", cascade="all, delete-orphan", lazy="select"
    )
    damage_records: Mapped[list[DamageRecord]] = relationship(
        "DamageRecord", back_populates="scan", cascade="all, delete-orphan", lazy="select"
    )


class ScanImage(Base):
    __tablename__ = "scan_images"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    scan_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("scans.id", ondelete="CASCADE"), nullable=False, index=True
    )
    camera_angle: Mapped[CameraAngle] = mapped_column(
        Enum(CameraAngle, name="camera_angle"), nullable=False
    )
    full_image_path: Mapped[str] = mapped_column(Text, nullable=False)
    thumbnail_path: Mapped[str] = mapped_column(Text, nullable=False)
    captured_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    scan: Mapped[Scan] = relationship("Scan", back_populates="images")
    damage_records: Mapped[list[DamageRecord]] = relationship(
        "DamageRecord", back_populates="scan_image", lazy="select"
    )


class DamageRecord(Base):
    __tablename__ = "damage_records"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    scan_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("scans.id", ondelete="CASCADE"), nullable=False, index=True
    )
    scan_image_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("scan_images.id", ondelete="CASCADE"), nullable=False
    )
    damage_class: Mapped[DamageClass] = mapped_column(
        Enum(DamageClass, name="damage_class"), nullable=False
    )
    confidence: Mapped[float] = mapped_column(Float, nullable=False)
    bbox_x1: Mapped[int] = mapped_column(Integer, nullable=False)
    bbox_y1: Mapped[int] = mapped_column(Integer, nullable=False)
    bbox_x2: Mapped[int] = mapped_column(Integer, nullable=False)
    bbox_y2: Mapped[int] = mapped_column(Integer, nullable=False)
    polygon_points: Mapped[list] = mapped_column(JSONB, nullable=False)
    mask_area_px: Mapped[int] = mapped_column(Integer, nullable=False)
    mask_area_pct: Mapped[float] = mapped_column(Float, nullable=False)
    crop_image_path: Mapped[str] = mapped_column(Text, nullable=False)
    is_new_damage: Mapped[bool | None] = mapped_column(Boolean, nullable=True, default=None)

    scan: Mapped[Scan] = relationship("Scan", back_populates="damage_records")
    scan_image: Mapped[ScanImage] = relationship("ScanImage", back_populates="damage_records")


class DamageDiff(Base):
    __tablename__ = "damage_diffs"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    vehicle_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("vehicles.id", ondelete="CASCADE"), nullable=False, index=True
    )
    scan_id_old: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("scans.id", ondelete="SET NULL"), nullable=True
    )
    scan_id_new: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("scans.id", ondelete="CASCADE"), nullable=False
    )
    new_damage_count: Mapped[int] = mapped_column(Integer, nullable=False)
    resolved_damage_count: Mapped[int] = mapped_column(Integer, nullable=False)
    diff_summary: Mapped[dict] = mapped_column(JSONB, nullable=False)
    computed_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    vehicle: Mapped[Vehicle] = relationship("Vehicle", back_populates="damage_diffs")


class WebhookRegistration(Base):
    __tablename__ = "webhook_registrations"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    url: Mapped[str] = mapped_column(String(2048), nullable=False)
    secret: Mapped[str] = mapped_column(String(256), nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    last_triggered_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    events: Mapped[list[AlertLog]] = relationship(
        "AlertLog", back_populates="webhook", lazy="select"
    )


class AlertLog(Base):
    __tablename__ = "alert_logs"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    scan_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("scans.id", ondelete="CASCADE"), nullable=False, index=True
    )
    vehicle_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("vehicles.id", ondelete="CASCADE"), nullable=False
    )
    webhook_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("webhook_registrations.id", ondelete="CASCADE"), nullable=False
    )
    status_code: Mapped[int] = mapped_column(Integer, nullable=False)
    triggered_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    payload_summary: Mapped[dict] = mapped_column(JSONB, nullable=False)

    webhook: Mapped[WebhookRegistration] = relationship(
        "WebhookRegistration", back_populates="events"
    )

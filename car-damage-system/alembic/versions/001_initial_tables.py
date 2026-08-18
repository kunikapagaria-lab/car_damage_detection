"""Initial schema — all tables, enums, and indexes.

Revision ID: 001
Revises:
Create Date: 2026-05-09
"""

from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "001"
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # ── Enum types ────────────────────────────────────────────────────────────
    scan_status = postgresql.ENUM(
        "pending", "processing", "complete", "failed",
        name="scan_status", create_type=False,
    )
    camera_angle = postgresql.ENUM(
        "front", "rear", "left", "right", "front_oblique", "rear_oblique",
        name="camera_angle", create_type=False,
    )
    damage_class = postgresql.ENUM(
        "scratch", "dent", "paint_damage", "crack",
        name="damage_class", create_type=False,
    )

    scan_status.create(op.get_bind(), checkfirst=True)
    camera_angle.create(op.get_bind(), checkfirst=True)
    damage_class.create(op.get_bind(), checkfirst=True)

    # ── vehicles ──────────────────────────────────────────────────────────────
    op.create_table(
        "vehicles",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("plate_number", sa.String(20), nullable=False, unique=True),
        sa.Column(
            "first_seen",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "last_seen",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("total_scans", sa.Integer(), nullable=False, server_default="0"),
    )
    op.create_index("ix_vehicles_plate_number", "vehicles", ["plate_number"])

    # ── scans ─────────────────────────────────────────────────────────────────
    op.create_table(
        "scans",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "vehicle_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("vehicles.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "triggered_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("camera_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column(
            "status",
            postgresql.ENUM("pending", "processing", "complete", "failed", name="scan_status", create_type=False),
            nullable=False,
            server_default="pending",
        ),
        sa.Column("location_tag", sa.String(128), nullable=True),
    )
    op.create_index("ix_scans_vehicle_id", "scans", ["vehicle_id"])

    # ── scan_images ───────────────────────────────────────────────────────────
    op.create_table(
        "scan_images",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "scan_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("scans.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "camera_angle",
            postgresql.ENUM(
                "front", "rear", "left", "right", "front_oblique", "rear_oblique",
                name="camera_angle", create_type=False,
            ),
            nullable=False,
        ),
        sa.Column("full_image_path", sa.Text(), nullable=False),
        sa.Column("thumbnail_path", sa.Text(), nullable=False),
        sa.Column(
            "captured_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
    )
    op.create_index("ix_scan_images_scan_id", "scan_images", ["scan_id"])

    # ── damage_records ────────────────────────────────────────────────────────
    op.create_table(
        "damage_records",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "scan_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("scans.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "scan_image_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("scan_images.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "damage_class",
            postgresql.ENUM("scratch", "dent", "paint_damage", "crack", name="damage_class", create_type=False),
            nullable=False,
        ),
        sa.Column("confidence", sa.Float(), nullable=False),
        sa.Column("bbox_x1", sa.Integer(), nullable=False),
        sa.Column("bbox_y1", sa.Integer(), nullable=False),
        sa.Column("bbox_x2", sa.Integer(), nullable=False),
        sa.Column("bbox_y2", sa.Integer(), nullable=False),
        sa.Column("polygon_points", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("mask_area_px", sa.Integer(), nullable=False),
        sa.Column("mask_area_pct", sa.Float(), nullable=False),
        sa.Column("crop_image_path", sa.Text(), nullable=False),
        sa.Column("is_new_damage", sa.Boolean(), nullable=True),
    )
    op.create_index("ix_damage_records_scan_id", "damage_records", ["scan_id"])

    # ── damage_diffs ──────────────────────────────────────────────────────────
    op.create_table(
        "damage_diffs",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "vehicle_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("vehicles.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "scan_id_old",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("scans.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column(
            "scan_id_new",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("scans.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("new_damage_count", sa.Integer(), nullable=False),
        sa.Column("resolved_damage_count", sa.Integer(), nullable=False),
        sa.Column("diff_summary", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column(
            "computed_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
    )
    op.create_index("ix_damage_diffs_vehicle_id", "damage_diffs", ["vehicle_id"])

    # ── webhook_registrations ─────────────────────────────────────────────────
    op.create_table(
        "webhook_registrations",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("url", sa.String(2048), nullable=False),
        sa.Column("secret", sa.String(256), nullable=False),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default="true"),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("last_triggered_at", sa.DateTime(timezone=True), nullable=True),
    )

    # ── alert_logs ────────────────────────────────────────────────────────────
    op.create_table(
        "alert_logs",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "scan_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("scans.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "vehicle_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("vehicles.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "webhook_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("webhook_registrations.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("status_code", sa.Integer(), nullable=False),
        sa.Column(
            "triggered_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("payload_summary", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
    )
    op.create_index("ix_alert_logs_scan_id", "alert_logs", ["scan_id"])


def downgrade() -> None:
    op.drop_table("alert_logs")
    op.drop_table("webhook_registrations")
    op.drop_table("damage_diffs")
    op.drop_table("damage_records")
    op.drop_table("scan_images")
    op.drop_table("scans")
    op.drop_table("vehicles")

    op.execute("DROP TYPE IF EXISTS damage_class")
    op.execute("DROP TYPE IF EXISTS camera_angle")
    op.execute("DROP TYPE IF EXISTS scan_status")

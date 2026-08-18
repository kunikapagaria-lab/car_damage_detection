-- Full database schema for car damage detection system
CREATE EXTENSION IF NOT EXISTS "pgcrypto";

CREATE TYPE scan_status   AS ENUM ('pending','processing','complete','failed');
CREATE TYPE camera_angle  AS ENUM ('front','rear','left','right','front_oblique','rear_oblique');
CREATE TYPE damage_class  AS ENUM ('scratch','dent','paint_damage','crack');
CREATE TYPE user_role     AS ENUM ('operator','admin');

CREATE TABLE vehicles (
    id           UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    plate_number VARCHAR(20) NOT NULL UNIQUE,
    first_seen   TIMESTAMPTZ NOT NULL DEFAULT now(),
    last_seen    TIMESTAMPTZ NOT NULL DEFAULT now(),
    total_scans  INTEGER     NOT NULL DEFAULT 0
);
CREATE INDEX ix_vehicles_plate_number ON vehicles (plate_number);

CREATE TABLE scans (
    id           UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    vehicle_id   UUID NOT NULL REFERENCES vehicles(id) ON DELETE CASCADE,
    triggered_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    completed_at TIMESTAMPTZ,
    camera_count INTEGER     NOT NULL DEFAULT 0,
    status       scan_status NOT NULL DEFAULT 'pending',
    location_tag VARCHAR(128)
);
CREATE INDEX ix_scans_vehicle_id ON scans (vehicle_id);

CREATE TABLE scan_images (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    scan_id         UUID         NOT NULL REFERENCES scans(id) ON DELETE CASCADE,
    camera_angle    camera_angle NOT NULL,
    full_image_path TEXT         NOT NULL,
    thumbnail_path  TEXT         NOT NULL,
    captured_at     TIMESTAMPTZ  NOT NULL DEFAULT now()
);
CREATE INDEX ix_scan_images_scan_id ON scan_images (scan_id);

CREATE TABLE damage_records (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    scan_id         UUID         NOT NULL REFERENCES scans(id)       ON DELETE CASCADE,
    scan_image_id   UUID         NOT NULL REFERENCES scan_images(id) ON DELETE CASCADE,
    damage_class    damage_class NOT NULL,
    confidence      FLOAT        NOT NULL,
    bbox_x1         INTEGER      NOT NULL,
    bbox_y1         INTEGER      NOT NULL,
    bbox_x2         INTEGER      NOT NULL,
    bbox_y2         INTEGER      NOT NULL,
    polygon_points  JSONB        NOT NULL,
    mask_area_px    INTEGER      NOT NULL,
    mask_area_pct   FLOAT        NOT NULL,
    crop_image_path TEXT         NOT NULL,
    is_new_damage   BOOLEAN
);
CREATE INDEX ix_damage_records_scan_id ON damage_records (scan_id);

CREATE TABLE damage_diffs (
    id                    UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    vehicle_id            UUID NOT NULL REFERENCES vehicles(id)  ON DELETE CASCADE,
    scan_id_old           UUID REFERENCES scans(id)              ON DELETE SET NULL,
    scan_id_new           UUID NOT NULL REFERENCES scans(id)     ON DELETE CASCADE,
    new_damage_count      INTEGER     NOT NULL,
    resolved_damage_count INTEGER     NOT NULL,
    diff_summary          JSONB       NOT NULL,
    computed_at           TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX ix_damage_diffs_vehicle_id ON damage_diffs (vehicle_id);

CREATE TABLE webhook_registrations (
    id                UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    url               VARCHAR(2048) NOT NULL,
    secret            VARCHAR(256)  NOT NULL,
    is_active         BOOLEAN       NOT NULL DEFAULT true,
    created_at        TIMESTAMPTZ   NOT NULL DEFAULT now(),
    last_triggered_at TIMESTAMPTZ
);

CREATE TABLE alert_logs (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    scan_id         UUID NOT NULL REFERENCES scans(id)                ON DELETE CASCADE,
    vehicle_id      UUID NOT NULL REFERENCES vehicles(id)             ON DELETE CASCADE,
    webhook_id      UUID NOT NULL REFERENCES webhook_registrations(id) ON DELETE CASCADE,
    status_code     INTEGER     NOT NULL,
    triggered_at    TIMESTAMPTZ NOT NULL DEFAULT now(),
    payload_summary JSONB       NOT NULL
);
CREATE INDEX ix_alert_logs_scan_id ON alert_logs (scan_id);

CREATE TABLE users (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    username        VARCHAR(64)  NOT NULL UNIQUE,
    hashed_password VARCHAR(256) NOT NULL,
    role            user_role    NOT NULL DEFAULT 'operator',
    is_active       BOOLEAN      NOT NULL DEFAULT true,
    created_at      TIMESTAMPTZ  NOT NULL DEFAULT now()
);
CREATE INDEX ix_users_username ON users (username);

CREATE TABLE alembic_version (version_num VARCHAR(32) NOT NULL PRIMARY KEY);
INSERT INTO alembic_version VALUES ('002');

SELECT 'All tables created successfully' AS result;

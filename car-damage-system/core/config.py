"""Centralised application settings loaded from environment / .env file."""

from __future__ import annotations

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    # Database
    DATABASE_URL: str = "postgresql+asyncpg://postgres:postgres@localhost:5432/car_damage"

    @field_validator("DATABASE_URL")
    @classmethod
    def _normalize_database_url(cls, v: str) -> str:
        # Managed Postgres providers (Render, Heroku, ...) hand out plain
        # postgres:// / postgresql:// URLs — upgrade to the asyncpg driver.
        if v.startswith("postgres://"):
            v = v.replace("postgres://", "postgresql+asyncpg://", 1)
        elif v.startswith("postgresql://"):
            v = v.replace("postgresql://", "postgresql+asyncpg://", 1)
        return v

    # Redis
    REDIS_URL: str = "redis://localhost:6379/0"

    # MinIO / S3-compatible object storage
    MINIO_ENDPOINT: str = "localhost:9000"
    MINIO_ACCESS_KEY: str = "minioadmin"
    MINIO_SECRET_KEY: str = "minioadmin"
    MINIO_SECURE: bool = False

    # Buckets
    BUCKET_FULL_IMAGES: str = "car-damage-full-images"
    BUCKET_CROPS: str = "car-damage-crops"
    BUCKET_THUMBNAILS: str = "car-damage-thumbnails"

    # Webhook signing
    WEBHOOK_SECRET: str = "changeme-use-a-real-secret"

    # Runtime
    LOG_LEVEL: str = "INFO"
    ENVIRONMENT: str = "development"
    MAX_UPLOAD_SIZE_MB: int = 50
    THUMBNAIL_WIDTH: int = 320
    THUMBNAIL_HEIGHT: int = 240

    # Server
    BACKEND_HOST: str = "0.0.0.0"
    BACKEND_PORT: int = 8000

    # CORS — comma-separated list of allowed origins
    CORS_ORIGINS: str = "http://localhost:3000,http://localhost:3001,http://localhost:8001"

    @property
    def max_upload_bytes(self) -> int:
        return self.MAX_UPLOAD_SIZE_MB * 1024 * 1024

    @property
    def cors_origins_list(self) -> list[str]:
        return [o.strip() for o in self.CORS_ORIGINS.split(",") if o.strip()]


settings = Settings()

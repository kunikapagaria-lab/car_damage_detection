"""Centralised application settings loaded from environment / .env file."""

from __future__ import annotations

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    # Database
    DATABASE_URL: str = "postgresql+asyncpg://postgres:postgres@localhost:5432/car_damage"

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

    @property
    def max_upload_bytes(self) -> int:
        return self.MAX_UPLOAD_SIZE_MB * 1024 * 1024


settings = Settings()

"""Async MinIO/S3-compatible object storage client built on aiobotocore.

Auto-creates the three required buckets on startup if they do not exist.
"""

from __future__ import annotations

import io
from typing import Any

import structlog
from aiobotocore.session import AioSession
from botocore.exceptions import ClientError

from core.config import settings

logger = structlog.get_logger(__name__)

BUCKETS = [
    settings.BUCKET_FULL_IMAGES,
    settings.BUCKET_CROPS,
    settings.BUCKET_THUMBNAILS,
]

_session = AioSession()


def _client_kwargs() -> dict[str, Any]:
    scheme = "https" if settings.MINIO_SECURE else "http"
    return {
        "service_name": "s3",
        "endpoint_url": f"{scheme}://{settings.MINIO_ENDPOINT}",
        "aws_access_key_id": settings.MINIO_ACCESS_KEY,
        "aws_secret_access_key": settings.MINIO_SECRET_KEY,
        "region_name": "us-east-1",
    }


async def ensure_buckets() -> None:
    """Create buckets that do not yet exist. Called once at startup."""
    async with _session.create_client(**_client_kwargs()) as s3:
        for bucket in BUCKETS:
            try:
                await s3.head_bucket(Bucket=bucket)
            except ClientError as exc:
                code = exc.response["Error"]["Code"]
                if code in ("404", "NoSuchBucket"):
                    await s3.create_bucket(Bucket=bucket)
                    logger.info("minio_bucket_created", bucket=bucket)
                else:
                    logger.error("minio_bucket_check_failed", bucket=bucket, error=str(exc))
                    raise


async def upload_image(
    bucket: str,
    key: str,
    image_bytes: bytes,
    content_type: str = "image/jpeg",
) -> str:
    """Upload raw bytes and return the object key (not a URL)."""
    async with _session.create_client(**_client_kwargs()) as s3:
        await s3.put_object(
            Bucket=bucket,
            Key=key,
            Body=image_bytes,
            ContentType=content_type,
        )
    logger.debug("minio_upload_ok", bucket=bucket, key=key, size=len(image_bytes))
    return key


async def generate_presigned_url(
    bucket: str,
    key: str,
    expires: int = 3600,
) -> str:
    """Return a time-limited presigned GET URL for the object."""
    async with _session.create_client(**_client_kwargs()) as s3:
        url: str = await s3.generate_presigned_url(
            "get_object",
            Params={"Bucket": bucket, "Key": key},
            ExpiresIn=expires,
        )
    return url


async def delete_object(bucket: str, key: str) -> None:
    async with _session.create_client(**_client_kwargs()) as s3:
        await s3.delete_object(Bucket=bucket, Key=key)
    logger.debug("minio_delete_ok", bucket=bucket, key=key)

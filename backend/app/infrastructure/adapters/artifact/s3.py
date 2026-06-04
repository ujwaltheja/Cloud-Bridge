"""
S3ArtifactStore - Implementation for MinIO and real S3.

This implementation was elevated to first-class status in PR 1 per user priority.
"""

from io import BytesIO
from typing import BinaryIO

import boto3
from botocore.exceptions import ClientError

from app.core.config import get_settings

from .base import ArtifactStore


class S3ArtifactStore(ArtifactStore):
    """
    S3-compatible artifact storage (MinIO in development, AWS S3 in production).
    """

    def __init__(self):
        settings = get_settings()
        self.bucket = settings.minio_bucket

        self.client = boto3.client(
            "s3",
            endpoint_url=settings.aws_endpoint_url,
            aws_access_key_id=settings.aws_access_key_id,
            aws_secret_access_key=settings.aws_secret_access_key,
            region_name=settings.aws_region,
        )

    async def save(self, key: str, data: bytes | BinaryIO, content_type: str = "application/octet-stream") -> str:
        if isinstance(data, bytes):
            data = BytesIO(data)

        self.client.upload_fileobj(
            data,
            self.bucket,
            key,
            ExtraArgs={"ContentType": content_type},
        )
        return f"s3://{self.bucket}/{key}"

    async def get(self, key: str) -> bytes:
        buffer = BytesIO()
        self.client.download_fileobj(self.bucket, key, buffer)
        buffer.seek(0)
        return buffer.read()

    async def delete(self, key: str) -> None:
        try:
            self.client.delete_object(Bucket=self.bucket, Key=key)
        except ClientError:
            pass  # Idempotent delete

    async def exists(self, key: str) -> bool:
        try:
            self.client.head_object(Bucket=self.bucket, Key=key)
            return True
        except ClientError:
            return False

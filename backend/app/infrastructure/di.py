"""
Simple Dependency Injection container for Cloud Bridge (PR 1).

For PR 1 we keep this very lightweight. In later PRs we can evolve this
into a proper DI container if needed.
"""

from functools import lru_cache

from app.core.config import get_settings
from app.infrastructure.adapters.artifact.base import ArtifactStore
from app.infrastructure.adapters.artifact.local import LocalFilesystemArtifactStore
from app.infrastructure.adapters.artifact.s3 import S3ArtifactStore
from app.infrastructure.encryption import decrypt, encrypt


@lru_cache
def get_artifact_store() -> ArtifactStore:
    """
    Returns the configured ArtifactStore implementation.

    In development we default to the local filesystem store.
    When MINIO / S3 is properly configured and desired, we can switch
    via environment variable in the future.
    """
    settings = get_settings()

    # For PR 1 we default to LocalFilesystem for simplicity and speed.
    # The S3 implementation is fully wired and ready.
    if settings.aws_endpoint_url and "minio" in settings.aws_endpoint_url.lower():
        # If we're pointing at MinIO, prefer the S3 adapter
        return S3ArtifactStore()

    return LocalFilesystemArtifactStore()


def get_fernet_encryptor():
    """Simple wrapper exposing encrypt/decrypt using Fernet."""
    class FernetWrapper:
        @staticmethod
        def encrypt(data: str) -> str:
            return encrypt(data)

        @staticmethod
        def decrypt(token: str) -> str:
            return decrypt(token)

    return FernetWrapper()

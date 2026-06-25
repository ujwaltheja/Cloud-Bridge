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

    backend = settings.artifact_store_backend.lower().strip()
    if backend in {"s3", "minio"}:
        return S3ArtifactStore()

    return LocalFilesystemArtifactStore(base_path=settings.local_artifact_path)


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

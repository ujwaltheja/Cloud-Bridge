"""
Simple Dependency Injection container for Cloud Bridge (PR 1).

For PR 1 we keep this very lightweight. In later PRs we can evolve this
into a proper DI container if needed.
"""

import logging
from functools import lru_cache

from app.core.config import get_settings
from app.infrastructure.adapters.artifact.base import ArtifactStore
from app.infrastructure.adapters.artifact.local import LocalFilesystemArtifactStore
from app.infrastructure.adapters.artifact.s3 import S3ArtifactStore
from app.infrastructure.encryption import decrypt, encrypt

_di_logger = logging.getLogger(__name__)


@lru_cache
def get_artifact_store() -> ArtifactStore:
    """
    Returns the configured ArtifactStore implementation.

    Prefers S3/MinIO when AWS_ENDPOINT_URL points at a MinIO host, but
    validates connectivity first.  Falls back to local filesystem if MinIO
    is unreachable (e.g. not deployed in K8s), so artifact saves never fail
    silently and leave jobs with artifact_key=null.
    """
    settings = get_settings()

    if settings.aws_endpoint_url and "minio" in settings.aws_endpoint_url.lower():
        try:
            store = S3ArtifactStore()
            store.client.list_buckets()  # quick reachability check
            _di_logger.info("Artifact store: MinIO/S3 at %s", settings.aws_endpoint_url)
            return store
        except Exception as exc:
            _di_logger.warning(
                "MinIO at %s unreachable (%s) — using local filesystem artifact store",
                settings.aws_endpoint_url, exc,
            )

    _di_logger.info("Artifact store: local filesystem (/app/artifacts)")
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

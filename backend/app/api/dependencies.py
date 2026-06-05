"""
Common FastAPI dependencies.
"""

import secrets

from fastapi import Header, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.infrastructure.adapters.artifact.base import ArtifactStore
from app.infrastructure.db.engine import get_db
from app.infrastructure.di import get_artifact_store


async def get_db_session() -> AsyncSession:
    """Dependency for getting an async DB session."""
    async for session in get_db():
        yield session


def get_artifact_store_dep() -> ArtifactStore:
    """Dependency for getting the configured ArtifactStore."""
    return get_artifact_store()


def require_api_key(x_api_key: str | None = Header(default=None, alias="X-API-Key")) -> None:
    """Validate X-API-Key header for protected API routes."""
    settings = get_settings()
    if not settings.backend_api_key:
        return

    if not x_api_key or not secrets.compare_digest(x_api_key, settings.backend_api_key):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or missing API key",
        )

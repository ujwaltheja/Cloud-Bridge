"""
Common FastAPI dependencies.
"""

from sqlalchemy.ext.asyncio import AsyncSession

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

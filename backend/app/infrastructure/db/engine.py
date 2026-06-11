"""
Async SQLAlchemy engine and session factory.

Supports both PostgreSQL (production) and SQLite (simple local prototype).
"""

from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from app.core.config import get_settings

settings = get_settings()

db_url = str(settings.database_url)


def _normalize_async_db_url(url: str) -> str:
    """Ensure PostgreSQL URLs use the asyncpg driver for async SQLAlchemy."""
    if url.startswith("postgresql://"):
        return url.replace("postgresql://", "postgresql+asyncpg://", 1)
    if url.startswith("postgres://"):
        return url.replace("postgres://", "postgresql+asyncpg://", 1)
    return url


db_url = _normalize_async_db_url(db_url)

# SQLite needs special connect args for async
connect_args = {}
if db_url.startswith("sqlite"):
    connect_args = {"check_same_thread": False}

# Pool kwargs — SQLite doesn't use a connection pool
_pool_kwargs = (
    {}
    if db_url.startswith("sqlite")
    else {
        "pool_pre_ping": True,   # test connections before checkout; reconnects on stale conn
        "pool_recycle": 270,     # recycle before the cluster's ~300s idle-timeout drops them
        "pool_size": 10,
        "max_overflow": 20,
    }
)

# Create async engine
engine: AsyncEngine = create_async_engine(
    db_url,
    echo=settings.is_development,
    connect_args=connect_args,
    **_pool_kwargs,
)

# Session factory
AsyncSessionLocal = async_sessionmaker(
    bind=engine,
    class_=AsyncSession,
    expire_on_commit=False,
)


async def get_db() -> AsyncSession:
    """
    FastAPI dependency that yields an async database session.
    """
    async with AsyncSessionLocal() as session:
        try:
            yield session
        except Exception:
            await session.rollback()
            raise

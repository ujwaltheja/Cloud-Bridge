"""
Health & Readiness endpoints (Production-grade).

These endpoints are used by Docker healthchecks and orchestrators.
"""

from fastapi import APIRouter, status
from fastapi.responses import JSONResponse

from ...core.config import get_settings

router = APIRouter()
settings = get_settings()


@router.get("/health", summary="Liveness probe")
async def health() -> JSONResponse:
    """Simple liveness check. Returns 200 if the process is running."""
    return JSONResponse(
        content={
            "status": "healthy",
            "service": "cloudbridge-backend",
            "environment": settings.app_env,
        },
        status_code=status.HTTP_200_OK,
    )


@router.get("/ready", summary="Readiness probe")
async def ready() -> JSONResponse:
    """
    Readiness check.
    In later PRs this will verify DB, Redis, MinIO connectivity.
    For PR 1 it simply confirms the application has started successfully.
    """
    return JSONResponse(
        content={
            "status": "ready",
            "service": "cloudbridge-backend",
            "checks": {
                "database": "not_checked_in_pr1",
                "redis": "not_checked_in_pr1",
                "minio": "not_checked_in_pr1",
            },
        },
        status_code=status.HTTP_200_OK,
    )

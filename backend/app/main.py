"""
Cloud Bridge Backend - Main Application Entry Point

Production-grade, fully async, versioned API from day one.
"""

import re
from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager

from fastapi import Depends, FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

# Import versioned API routers (will grow in later PRs)
from .api.v1 import (
    agents,
    comparisons,
    dependency_graph,
    deployments,
    health,
    impact_analysis,
    orgs,
    retrievals,
    sessions,
    tasks,
    tools,
)
from .api.dependencies import require_api_key
from .core.config import get_settings
from .core.logging import configure_logging, get_logger

settings = get_settings()
logger = get_logger("cloudbridge.main")


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    """Application lifespan events (startup/shutdown)."""
    # Startup
    configure_logging()
    logger.info("application.startup", env=settings.app_env)

    yield

    # Shutdown
    logger.info("application.shutdown")


def create_application() -> FastAPI:
    """Factory for creating the FastAPI application (enables testing)."""
    app = FastAPI(
        title="Cloud Bridge API",
        description="Production-grade Salesforce DevOps Platform",
        version="0.1.0",
        lifespan=lifespan,
        docs_url="/api/v1/docs",
        redoc_url="/api/v1/redoc",
        openapi_url="/api/v1/openapi.json",
    )

    # CORS - important for frontend development
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins,
        allow_origin_regex=settings.cors_origin_regex,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # Ensure CORS headers are present even on unhandled 500 errors.
    # Starlette's CORSMiddleware only handles normal responses; exceptions
    # bypass it, making the browser report a CORS error instead of the real 500.
    @app.exception_handler(Exception)
    async def _cors_aware_500_handler(request: Request, exc: Exception) -> JSONResponse:
        origin = request.headers.get("origin", "")
        headers: dict[str, str] = {}
        if origin:
            allowed = origin in settings.cors_origins
            if not allowed and settings.cors_origin_regex:
                try:
                    allowed = bool(re.match(settings.cors_origin_regex, origin))
                except re.error:
                    pass
            if allowed:
                headers["Access-Control-Allow-Origin"] = origin
                headers["Access-Control-Allow-Credentials"] = "true"
        logger.error("unhandled_exception", path=str(request.url), exc=str(exc))
        return JSONResponse(
            status_code=500,
            content={"detail": "Internal server error"},
            headers=headers,
        )

    # Mount versioned API (PRIORITY: API versioning from day one)
    protected_dependencies = [Depends(require_api_key)]
    app.include_router(health.router, prefix="/api/v1", tags=["Health"])
    app.include_router(tasks.router, prefix="/api/v1", tags=["Tasks (PR1 Verification)"], dependencies=protected_dependencies)
    app.include_router(orgs.router, prefix="/api/v1", dependencies=protected_dependencies)  # Org Management slice
    app.include_router(retrievals.router, prefix="/api/v1", dependencies=protected_dependencies)  # Metadata Retrieval slice
    app.include_router(comparisons.router, prefix="/api/v1", dependencies=protected_dependencies)  # Comparison Engine (new)
    app.include_router(deployments.router, prefix="/api/v1", dependencies=protected_dependencies)  # Deployment Engine (started)
    app.include_router(impact_analysis.router, prefix="/api/v1", dependencies=protected_dependencies)  # Impact Analysis & Dependency Intelligence
    app.include_router(dependency_graph.router, prefix="/api/v1", dependencies=protected_dependencies)  # AI Dependency Graph + Auto Package Builder
    
    # Agent Orchestration APIs (Sprint 1)
    app.include_router(agents.router, prefix="/api/v1", dependencies=protected_dependencies)       # Agent Registry
    app.include_router(tools.router, prefix="/api/v1", dependencies=protected_dependencies)        # Tool Registry
    app.include_router(sessions.router, prefix="/api/v1", dependencies=protected_dependencies)     # Session & Context Management

    # Root health check (convenience, not versioned)
    @app.get("/health", include_in_schema=False)
    async def root_health() -> JSONResponse:
        return JSONResponse({"status": "ok", "service": "cloudbridge-backend"})

    return app


app = create_application()

"""
Cloud Bridge Backend - Main Application Entry Point

Production-grade, fully async, versioned API from day one.
"""

from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager

from fastapi import FastAPI
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

    # Mount versioned API (PRIORITY: API versioning from day one)
    app.include_router(health.router, prefix="/api/v1", tags=["Health"])
    app.include_router(tasks.router, prefix="/api/v1", tags=["Tasks (PR1 Verification)"])
    app.include_router(orgs.router, prefix="/api/v1")  # Org Management slice
    app.include_router(retrievals.router, prefix="/api/v1")  # Metadata Retrieval slice
    app.include_router(comparisons.router, prefix="/api/v1")  # Comparison Engine (new)
    app.include_router(deployments.router, prefix="/api/v1")  # Deployment Engine (started)
    app.include_router(impact_analysis.router, prefix="/api/v1")  # Impact Analysis & Dependency Intelligence
    app.include_router(dependency_graph.router, prefix="/api/v1")  # AI Dependency Graph + Auto Package Builder
    
    # Agent Orchestration APIs (Sprint 1)
    app.include_router(agents.router, prefix="/api/v1")       # Agent Registry
    app.include_router(tools.router, prefix="/api/v1")        # Tool Registry
    app.include_router(sessions.router, prefix="/api/v1")     # Session & Context Management

    # Root health check (convenience, not versioned)
    @app.get("/health", include_in_schema=False)
    async def root_health() -> JSONResponse:
        return JSONResponse({"status": "ok", "service": "cloudbridge-backend"})

    return app


app = create_application()

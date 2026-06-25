"""
Cloud Bridge - Application Configuration (Pydantic Settings)

Fully async-friendly and production-grade.
All configuration is loaded from environment variables with sensible defaults.
"""

import json
from functools import lru_cache
from pathlib import Path
from typing import Any

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

# Resolve the .env file relative to this file's location so alembic/uvicorn
# work regardless of the working directory they are launched from.
# config.py lives at: backend/app/core/config.py
# .env lives at:      <project_root>/.env  (3 levels up from backend/app/core)
_ENV_FILE = Path(__file__).resolve().parents[3] / ".env"


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=str(_ENV_FILE),
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    # -------------------------------------------------------------------------
    # Application
    # -------------------------------------------------------------------------
    app_env: str = Field(default="development", alias="APP_ENV")
    log_level: str = Field(default="INFO", alias="LOG_LEVEL")

    # Security
    fernet_key: str = Field(..., alias="FERNET_KEY")
    secret_key: str = Field(..., alias="SECRET_KEY")  # JWT secret key

    # -------------------------------------------------------------------------
    # Database (async) - supports both PostgreSQL and SQLite for prototype
    # -------------------------------------------------------------------------
    database_url: str = Field(..., alias="DATABASE_URL")

    # -------------------------------------------------------------------------
    # Redis / Celery
    # -------------------------------------------------------------------------
    # redis_url is optional — not required when running in eager/local mode.
    redis_url: str | None = Field(default=None, alias="REDIS_URL")
    celery_broker_url: str = Field(..., alias="CELERY_BROKER_URL")
    celery_result_backend: str = Field(..., alias="CELERY_RESULT_BACKEND")

    # -------------------------------------------------------------------------
    # MinIO / S3 Artifact Storage (priority in PR 1)
    # -------------------------------------------------------------------------
    aws_access_key_id: str = Field(..., alias="AWS_ACCESS_KEY_ID")
    aws_secret_access_key: str = Field(..., alias="AWS_SECRET_ACCESS_KEY")
    aws_endpoint_url: str = Field(..., alias="AWS_ENDPOINT_URL")
    aws_region: str = Field(default="us-east-1", alias="AWS_REGION")
    minio_bucket: str = Field(default="cloudbridge-artifacts", alias="MINIO_BUCKET")
    artifact_store_backend: str = Field(default="local", alias="ARTIFACT_STORE_BACKEND")
    local_artifact_path: str = Field(default="./artifacts", alias="LOCAL_ARTIFACT_PATH")

    # -------------------------------------------------------------------------
    # API
    # -------------------------------------------------------------------------
    backend_host: str = Field(default="0.0.0.0", alias="BACKEND_HOST")
    backend_port: int = Field(default=8000, alias="BACKEND_PORT")
    cors_origins: list[str] = Field(
        default=["http://localhost:5173"],
        alias="CORS_ORIGINS",
    )

    @field_validator("cors_origins", mode="before")
    @classmethod
    def parse_cors_origins(cls, v: Any) -> Any:
        """Accept both JSON array and comma-separated string formats."""
        if isinstance(v, str):
            try:
                return json.loads(v)
            except json.JSONDecodeError:
                return [origin.strip() for origin in v.split(",") if origin.strip()]
        return v

    # -------------------------------------------------------------------------
    # LLM Settings
    # -------------------------------------------------------------------------
    llm_api_key: str | None = Field(default=None, alias="LLM_API_KEY")
    llm_endpoint_url: str | None = Field(default=None, alias="LLM_ENDPOINT_URL")
    llm_model: str | None = Field(default="389", alias="LLM_MODEL")

    # -------------------------------------------------------------------------
    # Derived / Convenience Properties
    # -------------------------------------------------------------------------
    @property
    def is_production(self) -> bool:
        return self.app_env.lower() == "production"

    @property
    def is_development(self) -> bool:
        return self.app_env.lower() in ("development", "dev", "local")


@lru_cache
def get_settings() -> Settings:
    """
    Cached settings instance. Use this everywhere instead of instantiating Settings directly.
    """
    return Settings()

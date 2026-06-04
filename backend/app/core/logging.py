"""
Cloud Bridge - Structured Logging (Production-grade)

Uses structlog for beautiful, machine-readable logs.
Includes correlation ID propagation (especially important for Celery workers).
"""

import logging
import sys
from typing import Any

import structlog
from structlog.types import Processor

from .config import get_settings


def add_correlation_id(logger: Any, method_name: str, event_dict: dict[str, Any]) -> dict[str, Any]:
    """Add correlation_id to every log record if present in context."""
    # This will be populated by middleware / task context
    if "correlation_id" not in event_dict:
        event_dict["correlation_id"] = "no-correlation"
    return event_dict


def configure_logging() -> None:
    """
    Configure structlog + stdlib logging for the entire application (API + Celery).
    Call this once at application startup (in main.py and celery_app.py).
    """
    settings = get_settings()

    # Standard library logging configuration
    logging.basicConfig(
        format="%(message)s",
        stream=sys.stdout,
        level=settings.log_level.upper(),
    )

    # Shared processors for both console and (future) JSON output
    shared_processors: list[Processor] = [
        structlog.stdlib.filter_by_level,
        structlog.stdlib.add_logger_name,
        structlog.stdlib.add_log_level,
        structlog.stdlib.PositionalArgumentsFormatter(),
        structlog.processors.TimeStamper(fmt="iso"),
        add_correlation_id,
        structlog.processors.StackInfoRenderer(),
        structlog.processors.format_exc_info,
        structlog.processors.UnicodeDecoder(),
    ]

    if settings.is_production:
        # Production: clean JSON logs (excellent for log aggregation)
        shared_processors.append(structlog.processors.JSONRenderer())
    else:
        # Development: beautiful colored console output
        shared_processors.append(structlog.dev.ConsoleRenderer(colors=True))

    structlog.configure(
        processors=shared_processors,
        context_class=dict,
        logger_factory=structlog.stdlib.LoggerFactory(),
        wrapper_class=structlog.stdlib.BoundLogger,
        cache_logger_on_first_use=True,
    )


def get_logger(name: str = "cloudbridge") -> structlog.stdlib.BoundLogger:
    """Convenience function to get a structured logger."""
    return structlog.get_logger(name)

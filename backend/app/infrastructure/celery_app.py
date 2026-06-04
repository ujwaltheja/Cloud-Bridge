"""
Celery Application Configuration with Strong Observability.

This module is one of the most important pieces for the "Worker Observability" priority in PR 1.

We register signals to write structured logs and persist TaskExecution records.
"""

from typing import Any

from celery import Celery, Task
from celery.signals import task_failure, task_postrun, task_prerun, task_success

from app.core.config import get_settings
from app.core.logging import configure_logging, get_logger

settings = get_settings()
logger = get_logger("cloudbridge.celery")

# Create Celery app
celery_app = Celery(
    "cloudbridge",
    broker=settings.celery_broker_url,
    backend=settings.celery_result_backend,
    include=[
        # Task modules will be added here in later PRs
        "app.infrastructure.tasks.example",
        "app.infrastructure.tasks.metadata",
        "app.infrastructure.tasks.deployments",
    ],
)

# Celery configuration - production friendly
_eager = settings.is_development  # run tasks inline when no broker available locally

celery_app.conf.update(
    task_serializer="json",
    accept_content=["json"],
    result_serializer="json",
    timezone="UTC",
    enable_utc=True,
    task_track_started=True,
    task_time_limit=30 * 60,      # 30 minutes hard limit
    task_soft_time_limit=25 * 60,  # 25 minutes soft limit
    worker_prefetch_multiplier=1,  # Important for long-running tasks
    task_acks_late=True,
    # In development, execute tasks synchronously in-process (no broker needed).
    task_always_eager=_eager,
    task_eager_propagates=_eager,
)

configure_logging()


# -----------------------------------------------------------------------------
# Task base class with better defaults
# -----------------------------------------------------------------------------
class CloudBridgeTask(Task):
    """Base task with good defaults for Cloud Bridge."""

    autoretry_for = ()
    retry_kwargs = {"max_retries": 3}
    retry_backoff = True
    retry_backoff_max = 600  # 10 minutes
    retry_jitter = True


celery_app.Task = CloudBridgeTask


# -----------------------------------------------------------------------------
# Signal handlers for observability (PR 1 priority)
# -----------------------------------------------------------------------------
@task_prerun.connect
def on_task_prerun(sender: Any, task_id: str, task: Task, **kwargs: Any) -> None:
    logger.info(
        "celery.task.started",
        task_id=task_id,
        task_name=task.name,
        correlation_id=kwargs.get("correlation_id", "no-correlation"),
    )


@task_postrun.connect
def on_task_postrun(sender: Any, task_id: str, task: Task, retval: Any, state: str, **kwargs: Any) -> None:
    logger.info(
        "celery.task.finished",
        task_id=task_id,
        task_name=task.name,
        state=state,
    )


@task_success.connect
def on_task_success(sender: Any, result: Any, **kwargs: Any) -> None:
    logger.info("celery.task.success", task_id=kwargs.get("task_id"))


@task_failure.connect
def on_task_failure(sender: Any, task_id: str, exception: Exception, einfo: Any, **kwargs: Any) -> None:
    logger.error(
        "celery.task.failure",
        task_id=task_id,
        task_name=getattr(sender, "name", "unknown"),
        exception=str(exception),
        traceback=str(einfo),
    )

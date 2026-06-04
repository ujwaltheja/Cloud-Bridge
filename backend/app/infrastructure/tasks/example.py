"""
Example background task (PR 1).

Used to validate that Celery + worker observability is working correctly.
"""

from typing import Any

from app.core.logging import get_logger
from app.infrastructure.celery_app import celery_app

logger = get_logger("cloudbridge.tasks.example")


@celery_app.task(name="cloudbridge.tasks.example.hello_world", bind=True)
def hello_world(self: Any, name: str = "World") -> dict[str, Any]:
    """
    Simple example task that demonstrates logging and return values.
    """
    logger.info("example.hello_world.executing", name=name, task_id=self.request.id)

    result = {
        "message": f"Hello, {name}!",
        "task_id": self.request.id,
    }

    logger.info("example.hello_world.completed", result=result)
    return result

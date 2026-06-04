"""
Minimal task endpoints for PR 1 verification only.

These will be replaced / expanded significantly in later PRs.
"""

from fastapi import APIRouter
from pydantic import BaseModel

from app.infrastructure.tasks.example import hello_world

router = APIRouter()


class TaskRequest(BaseModel):
    name: str = "World"


@router.post("/tasks/example", summary="Trigger example Celery task (PR 1 verification)")
async def trigger_example_task(payload: TaskRequest):
    """
    Enqueues the example hello_world task.
    Useful for verifying that the Celery worker is processing jobs.
    """
    from app.core.config import get_settings
    task = hello_world.delay(name=payload.name)
    settings = get_settings()
    status = "completed" if settings.is_development else "enqueued"
    return {
        "task_id": task.id,
        "status": status,
        "message": f"Task hello_world {'executed' if settings.is_development else 'enqueued'} with name={payload.name}",
    }

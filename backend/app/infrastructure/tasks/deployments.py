"""
Celery tasks for Deployments (validation, full deploy, quick deploy, with test runs).

Modeled after retrieval tasks so long-running sf CLI deploys don't block the HTTP API.
"""

import asyncio
import concurrent.futures
import logging
from datetime import datetime
import uuid

from app.application.services.deployment_service import DeploymentService
from app.infrastructure.celery_app import celery_app
from app.infrastructure.db.engine import AsyncSessionLocal


@celery_app.task(name="cloudbridge.tasks.deployments.execute", bind=True)
def execute_deployment_task(
    self,
    deployment_id: str,
    *,
    pmd_only: bool = False,
    check_only: bool | None = None,
    force_deployment_type: str | None = None,
):
    """
    Background task to perform a real deployment / validation using direct sf CLI.

    Supports the full flow: create pending job → user clicks Run → /run queues this task →
    task executes deploy_via_direct (sf project deploy validate or start --dry-run + test level,
    unpacks source from linked retrieval if present, updates the row with validating/deploying
    → success/failed + salesforce_deployment_id).

    Same thread-isolation pattern as retrieve task for Celery + async + eager/dev mode.
    """
    async def _run():
        async with AsyncSessionLocal() as db:
            service = DeploymentService(db)
            dep_id = uuid.UUID(deployment_id)
            deployment = await service.get_deployment(dep_id)
            if deployment:
                await service.start_deployment(
                    deployment,
                    pmd_only=pmd_only,
                    check_only=check_only,
                    force_deployment_type=force_deployment_type,
                )

    def _run_async_in_thread():
        # Fresh thread => guaranteed no running event loop, so asyncio.run is safe.
        return asyncio.run(_run())

    # Run async code inside Celery task (via worker thread to isolate event loop)
    try:
        with concurrent.futures.ThreadPoolExecutor(max_workers=1) as executor:
            future = executor.submit(_run_async_in_thread)
            future.result()  # blocks until done; re-raises any exception from inside
        return {"deployment_id": deployment_id, "status": "completed"}
    except Exception as exc:
        # Prevent the task exception from propagating to the .delay() caller
        # (which in eager/dev mode would cause 500 on the create API call).
        # The inner start_deployment should have marked the deployment failed if it got far enough.
        logger = logging.getLogger("cloudbridge.tasks.deployments")
        logger.exception("execute_deployment_task failed for deployment %s: %s", deployment_id, exc)
        # Best-effort: if the error happened very early (before start could set failed),
        # explicitly mark the deployment failed using a fresh session so it doesn't stay 'queued' forever.
        try:
            async def _mark_failed():
                async with AsyncSessionLocal() as db:
                    svc = DeploymentService(db)
                    d = await svc.get_deployment(uuid.UUID(deployment_id))
                    if d and getattr(d, "status", None) not in ("success", "failed"):
                        d.status = "failed"
                        d.error_message = (d.error_message or "") + f" | Task error: {str(exc)[:500]}"
                        d.completed_at = datetime.utcnow()
                        await db.commit()
            asyncio.run(_mark_failed())
        except Exception:
            pass  # non-fatal
        return {"deployment_id": deployment_id, "status": "failed", "error": str(exc)}

"""
Celery tasks for Metadata Retrieval.
"""

import asyncio
import concurrent.futures
import logging
from datetime import datetime

from app.application.services.metadata_retrieval_service import MetadataRetrievalService
from app.infrastructure.celery_app import celery_app
from app.infrastructure.db.engine import AsyncSessionLocal


@celery_app.task(name="cloudbridge.tasks.metadata.retrieve", bind=True)
def retrieve_metadata_task(self, job_id: str):
    """
    Background task to perform metadata retrieval.
    This allows long-running retrieves without blocking the API.

    We run the async work in a dedicated thread (via ThreadPoolExecutor) so that
    asyncio.run() is never invoked from a thread that already has a running event loop.
    This is critical for `task_always_eager=True` (dev) when .delay() is invoked
    from an async FastAPI request handler. In normal Celery workers (no running loop)
    it also works cleanly.
    """
    async def _run():
        async with AsyncSessionLocal() as db:
            service = MetadataRetrievalService(db)
            await service.start_retrieval(job_id)

    def _run_async_in_thread():
        # Fresh thread => guaranteed no running event loop, so asyncio.run is safe.
        return asyncio.run(_run())

    # Run async code inside Celery task (via worker thread to isolate event loop)
    try:
        with concurrent.futures.ThreadPoolExecutor(max_workers=1) as executor:
            future = executor.submit(_run_async_in_thread)
            future.result()  # blocks until done; re-raises any exception from inside
        return {"job_id": job_id, "status": "completed"}
    except Exception as exc:
        # Prevent the task exception from propagating to the .delay() caller
        # (which in eager/dev mode would cause 500 on the start retrieval API call).
        # The inner start_retrieval / _execute should have marked the job failed if it got far enough.
        # Log is already done via celery failure signal, but ensure no 500.
        logger = logging.getLogger("cloudbridge.tasks.metadata")
        logger.exception("retrieve_metadata_task failed for job %s: %s", job_id, exc)
        # Best-effort: if the error happened very early (before _execute could set failed),
        # explicitly mark the job failed using a fresh session so it doesn't stay 'queued' forever.
        try:
            async def _mark_failed():
                async with AsyncSessionLocal() as db:
                    svc = MetadataRetrievalService(db)
                    j = await svc.get_job(job_id)
                    if j and getattr(j, "status", None) not in ("success", "failed"):
                        j.status = "failed"
                        j.error_message = (j.error_message or "") + f" | Task error: {str(exc)[:300]}"
                        j.completed_at = datetime.utcnow()
                        await db.commit()
            asyncio.run(_mark_failed())
        except Exception:
            pass  # non-fatal
        return {"job_id": job_id, "status": "failed", "error": str(exc)}
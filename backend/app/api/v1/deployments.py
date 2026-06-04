"""
Deployment API (Real validation + deployment + test runs)

Two-step flow to match desired UX:
- POST /deployments : just create the job record (status=pending). Fast DB insert.
  The job appears in history immediately. No execution yet.
- POST /deployments/{id}/run : trigger async execution (queues Celery task for the sf CLI
  validate/deploy + tests). UI can then poll to track live progress.
- The heavy work (unpack source from linked retrieval, auth, sf project deploy validate/start
  with test-level etc.) happens in the background task exactly as before.

This allows: click "Create Job" → job added to history list → click "Run" on that job →
progress shown live below/in the card.
"""

from datetime import datetime
from io import BytesIO
import json
import logging
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.dependencies import get_db_session
from app.application.services.deployment_service import DeploymentService
from app.application.services.report_pdf_service import ReportPDFService
from app.infrastructure.di import get_artifact_store
from app.schemas.deployment import DeploymentCreate, DeploymentResponse

router = APIRouter(prefix="/deployments", tags=["Deployment Engine"])

@router.post("", response_model=DeploymentResponse)
async def create_deployment(
    payload: DeploymentCreate,
    db: AsyncSession = Depends(get_db_session),
):
    """Create a deployment job record only (fast). Status starts as 'pending'.
    No CLI execution. The job will appear in the history list.
    User then explicitly triggers run via /run .
    """
    service = DeploymentService(db)
    deployment = await service.create_deployment(payload)
    return deployment

@router.post("/{deployment_id}/run", response_model=DeploymentResponse)
async def run_deployment(
    deployment_id: UUID,
    payload: dict | None = None,
    db: AsyncSession = Depends(get_db_session),
):
    """Trigger execution for an existing deployment job (async via Celery).
    Sets status to 'queued' and queues the task that will do the real sf deploy/validate.
    Returns the job (now queued). UI should poll the list or this job to see
    validating → success/failed and show progress.
    """
    service = DeploymentService(db)
    deployment = await service.get_deployment(deployment_id)
    if not deployment:
        raise HTTPException(status_code=404, detail="Deployment not found")

    action = str((payload or {}).get("action") or "execute").strip().lower()
    pmd_only = action in ("pmd", "pmd_check", "pmd-only")
    check_only_override: bool | None = None
    force_deployment_type: str | None = None
    if action in ("validate", "run_validation", "validation"):
        check_only_override = True
        force_deployment_type = "validate_only"
    elif action in ("deploy", "run_deploy", "deployment"):
        check_only_override = False
        force_deployment_type = "full_deploy"

    # Only allow running from prepared states
    if deployment.status not in ("pending", "queued"):
        # already running or done; just return current state
        return deployment

    deployment.status = "pmd_check_queued" if pmd_only else "queued"
    await db.commit()
    await db.refresh(deployment)

    # Fire the task in a daemon thread so the HTTP response returns immediately
    # even in eager dev mode (where delay() would otherwise run the long sf CLI work sync).
    # This makes the "Run" click snappy: job goes to queued, UI gets response fast,
    # polling then shows live progress as the background work happens.
    def _fire_task():
        try:
            from app.infrastructure.tasks.deployments import execute_deployment_task
            execute_deployment_task.delay(
                str(deployment.id),
                pmd_only=pmd_only,
                check_only=check_only_override,
                force_deployment_type=force_deployment_type,
            )
        except Exception as delay_exc:
            # Best effort: mark failed if we couldn't even queue
            try:
                # Need sync session? For simplicity, log; the task's own error path may not run.
                # In practice, re-fetch in a quick async but since thread, use logging.
                logger = logging.getLogger(__name__)
                logger.exception("Failed to delay deployment task for %s: %s", deployment.id, delay_exc)
            except Exception:
                pass

    import threading
    threading.Thread(target=_fire_task, daemon=True).start()

    # Return the queued job immediately. Polling (or the caller) will see updates.
    return deployment

@router.get("", response_model=list[DeploymentResponse])
async def list_deployments(
    org_id: UUID | None = None,
    db: AsyncSession = Depends(get_db_session),
):
    service = DeploymentService(db)
    return await service.list_deployments(org_id)

@router.get("/{deployment_id}", response_model=DeploymentResponse)
async def get_deployment(deployment_id: UUID, db: AsyncSession = Depends(get_db_session)):
    service = DeploymentService(db)
    dep = await service.get_deployment(deployment_id)
    if not dep:
        raise HTTPException(status_code=404, detail="Deployment not found")
    return dep


@router.patch("/{deployment_id}", response_model=DeploymentResponse)
async def update_deployment_status(
    deployment_id: UUID,
    payload: dict,
    db: AsyncSession = Depends(get_db_session),
):
    """Simple status update for prototype/demo purposes."""
    service = DeploymentService(db)
    new_status = payload.get("status")
    if not new_status:
        raise HTTPException(status_code=400, detail="status is required")

    updated = await service.update_status(deployment_id, new_status)
    if not updated:
        raise HTTPException(status_code=404, detail="Deployment not found")
    return updated


@router.get("/{deployment_id}/pmd/report/pdf")
async def download_deployment_pmd_pdf(
    deployment_id: UUID,
    db: AsyncSession = Depends(get_db_session),
):
    service = DeploymentService(db)
    deployment = await service.get_deployment(deployment_id)
    if not deployment:
        raise HTTPException(status_code=404, detail="Deployment not found")

    options = deployment.options or {}
    pmd_result = options.get("pmd_result")

    if not pmd_result:
        artifact_store = get_artifact_store()
        artifact_key = f"deployments/{deployment_id}/pmd-analysis.json"
        try:
            raw = await artifact_store.get(artifact_key)
            pmd_result = json.loads(raw.decode("utf-8"))
        except Exception:
            # Keep download action stable for jobs where PMD was enabled but analysis output
            # was not produced (for example, deployment failed before analysis stage).
            pmd_result = {
                "status": "not_available",
                "summary": "PMD analysis result is not available for this deployment. The deployment may have failed before PMD pre-check completed.",
                "findings": [],
                "totals": {
                    "critical": 0,
                    "high": 0,
                    "medium": 0,
                    "low": 0,
                    "total": 0,
                },
                "knowledge_base": "n/a",
                "artifact_key": artifact_key,
            }

    pdf_service = ReportPDFService()
    pdf_bytes = pdf_service.generate_pmd_analysis_pdf(str(deployment_id), pmd_result)
    filename = f"ibm-salesforce-pmd-analysis-{deployment_id}.pdf"

    return StreamingResponse(
        BytesIO(pdf_bytes),
        media_type="application/pdf",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )

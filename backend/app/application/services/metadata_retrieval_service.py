"""
Metadata Retrieval Service

Handles retrieving metadata from Salesforce using SFDX MCP integration.
Provides real metadata retrieval via Salesforce CLI and MCP server.
"""

import logging
import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

logger = logging.getLogger(__name__)

from app.application.services.salesforce_org_service import SalesforceOrgService
from app.infrastructure.adapters.artifact.base import ArtifactStore
from app.infrastructure.db.models import MetadataRetrieval, SalesforceOrg
from app.infrastructure.di import get_artifact_store

artifact_store: ArtifactStore = get_artifact_store()


class MetadataRetrievalService:
    def __init__(self, db: AsyncSession):
        self.db = db
        self.org_service = SalesforceOrgService(db)

    async def create_retrieval_job(
        self, org_id: uuid.UUID, package_xml: str, description: str | None = None
    ) -> MetadataRetrieval:
        job = MetadataRetrieval(
            org_id=org_id,
            package_xml=package_xml,
            status="queued",
        )
        self.db.add(job)
        await self.db.commit()
        await self.db.refresh(job)
        return job

    async def start_retrieval(self, job_id: uuid.UUID | str, use_background: bool = False) -> MetadataRetrieval:
        if isinstance(job_id, str):
            job_id = uuid.UUID(job_id)
        job = await self.get_job(job_id)
        if not job:
            raise ValueError("Retrieval job not found")

        if use_background:
            from app.infrastructure.tasks.metadata import retrieve_metadata_task
            # Set queued BEFORE delay so that in eager mode (dev) the subsequent
            # refresh after delay will pick up the final status written by the
            # eager task execution. In non-eager the delay is async and we return
            # with queued (correct until worker runs).
            job.status = "queued"
            await self.db.commit()
            await self.db.refresh(job)
            try:
                retrieve_metadata_task.delay(str(job.id))
            except Exception as delay_exc:
                # In case delay raises (e.g. eager task raised despite wrapper),
                # don't let it cause 500 on the create API. Mark the job failed.
                logger = logging.getLogger(__name__)
                logger.exception("Failed to delay retrieval task for job %s: %s", job.id, delay_exc)
                job.status = "failed"
                job.error_message = f"Failed to queue retrieval task: {str(delay_exc)[:300]}"
                job.completed_at = datetime.utcnow()
                await self.db.commit()
                await self.db.refresh(job)
                return job
            # Refresh after delay: in eager/dev this gets the status from the work
            # that just ran inside the task; in prod it remains queued.
            await self.db.refresh(job)
            return job
        else:
            return await self._execute_retrieve(job)

    async def _execute_retrieve(self, job: MetadataRetrieval) -> MetadataRetrieval:
        """Execute metadata retrieval using direct Salesforce CLI (sf project retrieve start)
        driven by the caller's package.xml. Supports complete backups (via dynamic
        `sf project generate manifest --from-org`) and arbitrary manifests.
        MCP is used only for certain agent/tool flows.
        """
        org = await self._get_org(job.org_id)
        if not org or not org.encrypted_access_token:
            job.status = "failed"
            job.error_message = "Organization has no valid access token. Please reconnect the org."
            await self.db.commit()
            await self.db.refresh(job)
            return job

        try:
            job.status = "running"
            job.started_at = datetime.utcnow()
            await self.db.commit()

            from app.application.services.sfdx_mcp_service import SFDXMCPService
            mcp_service = SFDXMCPService(self.db)

            # Always use direct SFDX CLI for retrieval jobs. This honors the
            # exact package.xml (custom or "Complete Backup") sent from the UI.
            # For Complete Backup the server dynamically generates the real full manifest
            # using `sf project generate manifest --from-org` (Salesforce recommended for
            # true org-wide backup), then runs retrieve. Works on Windows, follows docs.
            updated_job = await mcp_service.retrieve_via_direct(job)
            return updated_job

        except Exception as e:
            job.status = "failed"
            job.error_message = f"Retrieval failed: {str(e)}"
            job.completed_at = datetime.utcnow()
            await self.db.commit()
            await self.db.refresh(job)
            return job

    async def get_artifact_content(self, job_id: uuid.UUID | str) -> dict[str, Any] | None:
        """Retrieve the stored artifact content for a job."""
        if isinstance(job_id, str):
            job_id = uuid.UUID(job_id)
        job = await self.get_job(job_id)
        if not job or not job.artifact_key:
            return None
        try:
            content = await artifact_store.get(job.artifact_key)
            # Try to parse as JSON first (MCP format)
            import json
            try:
                return json.loads(content.decode("utf-8"))
            except json.JSONDecodeError:
                # Fallback to ast.literal_eval for old prototype format
                import ast
                return ast.literal_eval(content.decode("utf-8"))
        except FileNotFoundError:
            # Artifact key in job but blob missing (e.g. store was wiped, or old job from before per-job dir fix).
            # Treat as "no artifact" so callers 404 cleanly instead of trying to parse an error dict.
            return None
        except Exception as e:
            return {"error": f"Failed to read artifact: {str(e)}"}

    async def get_job(self, job_id: uuid.UUID | str) -> MetadataRetrieval | None:
        if isinstance(job_id, str):
            job_id = uuid.UUID(job_id)
        result = await self.db.execute(
            select(MetadataRetrieval).where(MetadataRetrieval.id == job_id)
        )
        return result.scalar_one_or_none()

    async def list_all_jobs(self):
        result = await self.db.execute(
            select(MetadataRetrieval).order_by(MetadataRetrieval.created_at.desc())
        )
        return result.scalars().all()

    async def list_jobs_for_org(self, org_id: uuid.UUID):
        result = await self.db.execute(
            select(MetadataRetrieval)
            .where(MetadataRetrieval.org_id == org_id)
            .order_by(MetadataRetrieval.created_at.desc())
        )
        return result.scalars().all()

    async def delete_job(self, job_id: uuid.UUID | str) -> bool:
        if isinstance(job_id, str):
            job_id = uuid.UUID(job_id)
        job = await self.get_job(job_id)
        if not job:
            return False
        await self.db.delete(job)
        await self.db.commit()
        return True

    async def _get_org(self, org_id: uuid.UUID):
        result = await self.db.execute(
            select(SalesforceOrg).where(SalesforceOrg.id == org_id)
        )
        return result.scalar_one_or_none()

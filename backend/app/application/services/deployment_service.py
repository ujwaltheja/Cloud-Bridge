"""
Deployment Service (Initial + Real Execution)

Handles creating and tracking deployments from retrievals or comparisons.
Now supports real validation, deployment, and Apex test runs via direct sf CLI
(Workbench / Metadata API equivalent + sf project deploy validate/start).
"""

import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.infrastructure.db.models import Deployment


class DeploymentService:
    def __init__(self, db: AsyncSession):
        self.db = db

    async def create_deployment(self, payload) -> Deployment:
        # Persist the execution options so background task / history can use them.
        options: dict[str, Any] = {
            "check_only": getattr(payload, "check_only", False) or (getattr(payload, "deployment_type", "") == "validate_only"),
            "test_level": getattr(payload, "test_level", None),
            "run_tests": getattr(payload, "run_tests", None),
            "source_dir": getattr(payload, "source_dir", None),
            "manifest_path": getattr(payload, "manifest_path", None),
            # PMD pre-check runs before validation/deploy by default.
            "enable_pmd_check": getattr(payload, "enable_pmd_check", True),
            "pmd_block_on_violation": getattr(payload, "pmd_block_on_violation", False),
            "pmd_ruleset": getattr(payload, "pmd_ruleset", None),
            # Capture AI Release Intelligence linkage (for audit / "before every deployment" proof)
            "intelligence_analysis_id": (
                str(getattr(payload, "intelligence_analysis_id", None))
                if getattr(payload, "intelligence_analysis_id", None) is not None
                else None
            ),
            "intelligence_readiness": getattr(payload, "intelligence_readiness", None),
            "intelligence_decision": getattr(payload, "intelligence_decision", None),
        }

        deployment = Deployment(
            org_id=payload.org_id,
            retrieval_id=payload.retrieval_id,
            comparison_id=payload.comparison_id,
            deployment_type=payload.deployment_type,
            artifact_key=payload.artifact_key,
            status="pending",  # job created in history; execution starts only on explicit "Run"
            options=options,
        )
        self.db.add(deployment)
        await self.db.commit()
        await self.db.refresh(deployment)
        return deployment

    async def start_deployment(
        self,
        deployment: Deployment,
        *,
        check_only: bool | None = None,
        test_level: str | None = None,
        run_tests: list[str] | None = None,
        source_dir: str | None = None,
        manifest_path: str | None = None,
        pmd_only: bool = False,
        force_deployment_type: str | None = None,
    ) -> Deployment:
        """
        Kick off real execution using direct CLI (preferred for validation + test control).
        Updates the deployment record in place (status, sf id, error).
        Special handling for quick_deploy: uses prior salesforce_deployment_id + quick_deploy_direct.

        If called from background task, options are read from the persisted deployment.options.
        Explicit kwargs take precedence (for sync / ad-hoc calls).
        """
        from app.application.services.sfdx_mcp_service import SFDXMCPService

        mcp = SFDXMCPService(self.db)

        if deployment.deployment_type == "quick_deploy" and deployment.salesforce_deployment_id:
            # Dedicated quick-deploy path (uses the validated job ID on Salesforce side, no re-send of source)
            return await mcp.quick_deploy_via_direct(deployment, prior_job_id=deployment.salesforce_deployment_id)

        # Hydrate from persisted options (for Celery background jobs) or use caller's values.
        opts = deployment.options or {}
        effective_check_only = (
            check_only
            if check_only is not None
            else (opts.get("check_only", False) or (deployment.deployment_type in ("validate_only",)))
        )
        effective_test_level = test_level or opts.get("test_level")
        effective_run_tests = run_tests or opts.get("run_tests")
        effective_source = source_dir or opts.get("source_dir")
        effective_manifest = manifest_path or opts.get("manifest_path")
        enable_pmd_check = bool(opts.get("enable_pmd_check", False))
        pmd_block_on_violation = bool(opts.get("pmd_block_on_violation", False))
        pmd_ruleset = opts.get("pmd_ruleset")

        if force_deployment_type:
            deployment.deployment_type = force_deployment_type
            # Keep options coherent for history and retries.
            deployment.options = {
                **opts,
                "check_only": bool(effective_check_only),
            }
            await self.db.commit()

        if pmd_only:
            enable_pmd_check = True

        # Prefer direct for full check_only + test_level fidelity
        updated = await mcp.deploy_via_direct(
            deployment=deployment,
            source_dir=effective_source,
            manifest_path=effective_manifest,
            check_only=effective_check_only,
            test_level=effective_test_level,
            tests=effective_run_tests,
            enable_pmd_check=enable_pmd_check,
            pmd_block_on_violation=pmd_block_on_violation,
            pmd_ruleset=pmd_ruleset,
            pmd_only=pmd_only,
        )
        return updated

    async def get_deployment(self, deployment_id: uuid.UUID):
        result = await self.db.execute(
            select(Deployment).where(Deployment.id == deployment_id)
        )
        return result.scalar_one_or_none()

    async def list_deployments(self, org_id: uuid.UUID | None = None):
        query = select(Deployment).order_by(Deployment.created_at.desc())
        if org_id:
            query = query.where(Deployment.org_id == org_id)
        result = await self.db.execute(query)
        return result.scalars().all()

    async def update_status(self, deployment_id: uuid.UUID, status: str, error: str | None = None, sf_id: str | None = None):
        deployment = await self.get_deployment(deployment_id)
        if not deployment:
            return None
        deployment.status = status
        if error:
            deployment.error_message = error
        if sf_id:
            deployment.salesforce_deployment_id = sf_id
        if status in ["success", "failed", "rolled_back"]:
            deployment.completed_at = datetime.utcnow()
        await self.db.commit()
        return deployment

    async def create_from_retrieval(self, org_id: uuid.UUID, retrieval_id: uuid.UUID, deployment_type: str = "validate_only"):
        """Convenience method to deploy a specific retrieval."""
        deployment = Deployment(
            org_id=org_id,
            retrieval_id=retrieval_id,
            deployment_type=deployment_type,
            status="pending",
        )
        self.db.add(deployment)
        await self.db.commit()
        await self.db.refresh(deployment)
        return deployment

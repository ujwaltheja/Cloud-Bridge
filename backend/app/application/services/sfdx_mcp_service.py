"""
SFDX MCP Agent Service

Provides the agentic layer for Cloud Bridge — runs SFDX MCP tool calls
inside the app for retrieve, deploy, and Apex test operations.

All operations accept the org's DB record (with encrypted tokens) and
transparently bridge into the local SFDX auth store → MCP server subprocess.
"""

import json
import logging
import os
import tempfile
import uuid
from collections.abc import AsyncGenerator
from datetime import datetime
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.application.services.salesforce_auth import SalesforceAuthService
from app.infrastructure.db.models import Deployment, MetadataRetrieval, SalesforceOrg
from app.infrastructure.encryption import decrypt, encrypt
from app.infrastructure.sfdx_mcp_client import (
    SFDXMCPClient,
    list_metadata_members_direct,
    list_metadata_types_direct,
    retrieve_metadata_direct,
    deploy_metadata_direct,
    quick_deploy_direct,
    run_mcp_tool_streaming,
    COMPLETE_ORG_BACKUP_SENTINEL,
)

logger = logging.getLogger("cloudbridge.sfdx_mcp_service")
sf_auth = SalesforceAuthService()


def _ensure_manifest_from_xml(package_xml: str, project_dir: str) -> str:
    """Write the caller's raw package.xml into the project's manifest/ folder."""
    manifest_dir = os.path.join(project_dir, "manifest")
    os.makedirs(manifest_dir, exist_ok=True)
    mp = os.path.join(manifest_dir, "package.xml")
    with open(mp, "w", encoding="utf-8") as fh:
        fh.write(package_xml)
    return mp


class SFDXMCPService:
    """
    Agentic service that drives SFDX MCP tools for metadata operations.
    Replaces the prototype REST-based retrieval/deployment logic with
    real Salesforce CLI calls via the embedded MCP server.
    """

    def __init__(self, db: AsyncSession):
        self.db = db

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    async def _get_org(self, org_id: uuid.UUID) -> SalesforceOrg | None:
        result = await self.db.execute(
            select(SalesforceOrg).where(SalesforceOrg.id == org_id)
        )
        return result.scalar_one_or_none()

    @staticmethod
    def _is_auth_error(exc: Exception) -> bool:
        msg = str(exc).lower()
        markers = (
            "authentication required",
            "invalid session id",
            "session expired",
            "expired access",
            "invalid_grant",
            "oauth",
        )
        return any(m in msg for m in markers)

    async def _refresh_org_access_token(self, org: SalesforceOrg) -> str | None:
        """Attempt to refresh OAuth access token using stored refresh token and client details."""
        if not org.encrypted_refresh_token or not org.client_id:
            return None

        try:
            refresh_token = decrypt(org.encrypted_refresh_token)
            client_secret = decrypt(org.encrypted_client_secret) if org.encrypted_client_secret else None
            refreshed = await sf_auth.refresh_access_token(
                refresh_token=refresh_token,
                client_id=org.client_id,
                client_secret=client_secret,
                org_type=org.org_type,
            )
            new_access_token = refreshed["access_token"]
            org.encrypted_access_token = encrypt(new_access_token)
            if refreshed.get("instance_url"):
                org.instance_url = refreshed["instance_url"]
            await self.db.commit()
            return new_access_token
        except Exception as refresh_exc:
            logger.warning("Token refresh failed for org %s: %s", org.id, refresh_exc)
            return None

    @staticmethod
    def _get_project_dir() -> str:
        """Return the SFDX project directory from env var or OS temp."""
        env_dir = os.environ.get("SFDX_PROJECT_DIR")
        if env_dir:
            return env_dir
        return os.path.join(tempfile.gettempdir(), "cloudbridge-sfdx")

    def _make_client(self, org: SalesforceOrg, toolsets: str = "orgs,metadata,data,testing,users") -> SFDXMCPClient:
        access_token = decrypt(org.encrypted_access_token)
        return SFDXMCPClient(
            access_token=access_token,
            instance_url=org.instance_url,
            org_alias=f"cb-{str(org.id)[:8]}",
            toolsets=toolsets,
            project_dir=self._get_project_dir(),
        )

    async def _load_fresh_retrieval(self, job_id: uuid.UUID | str) -> MetadataRetrieval:
        if isinstance(job_id, str):
            job_id = uuid.UUID(job_id)
        result = await self.db.execute(
            select(MetadataRetrieval)
            .where(MetadataRetrieval.id == job_id)
            .execution_options(populate_existing=True)
        )
        return result.scalar_one()

    async def _load_fresh_deployment(self, dep_id: uuid.UUID) -> Deployment:
        result = await self.db.execute(
            select(Deployment)
            .where(Deployment.id == dep_id)
            .execution_options(populate_existing=True)
        )
        return result.scalar_one()

    # ------------------------------------------------------------------
    # Retrieve metadata via MCP
    # ------------------------------------------------------------------

    async def retrieve_via_mcp(
        self,
        job: MetadataRetrieval,
        metadata_types: list[str] | None = None,
    ) -> MetadataRetrieval:
        """
        Execute a metadata retrieval using the SFDX MCP server.
        Updates the job record in-place with status/artifact.
        """
        org = await self._get_org(job.org_id)
        if not org or not org.encrypted_access_token:
            job.status = "failed"
            job.error_message = "Org has no access token — reconnect it first."
            await self.db.commit()
            try:
                return await self._load_fresh_retrieval(job.id)
            except Exception as load_exc:
                logger.warning("Failed to load fresh retrieval after no-token handling for job %s: %s", job.id, load_exc)
                return job

        job.status = "running"
        job.started_at = datetime.utcnow()
        await self.db.commit()

        try:
            async with self._make_client(org) as client:
                # If the job carries a real package.xml, write it and pass manifest_path
                # so MCP retrieve uses exactly what the caller wanted (complete/custom).
                mp = None
                if job.package_xml and "<Package" in job.package_xml:
                    mp = _ensure_manifest_from_xml(job.package_xml, self._get_project_dir())
                result = await client.retrieve_metadata(
                    metadata_types=None if mp else (metadata_types or ["ApexClass", "CustomObject", "Flow"]),
                    manifest_path=mp,
                )

            # Store the MCP response as the artifact
            import json

            from app.infrastructure.di import get_artifact_store
            artifact_store = get_artifact_store()
            artifact_key = f"retrievals/{job.id}/mcp_result.json"
            payload = {
                "retrieved_at": datetime.utcnow().isoformat(),
                "org_id": str(org.id),
                "org_name": org.name,
                "source": "sfdx_mcp",
                "metadata_types": metadata_types,
                "result": result,
            }
            await artifact_store.save(
                artifact_key,
                json.dumps(payload, default=str).encode(),
                "application/json",
            )

            job.artifact_key = artifact_key
            job.status = "success"
            job.completed_at = datetime.utcnow()
            await self.db.commit()
            logger.info("MCP retrieve completed for job %s", job.id)

        except Exception as exc:
            logger.exception("MCP retrieve failed for job %s", job.id)
            job.status = "failed"
            job.error_message = str(exc)
            job.completed_at = datetime.utcnow()
            await self.db.commit()

        return await self._load_fresh_retrieval(job.id)

    async def retrieve_via_direct(
        self,
        job: MetadataRetrieval,
    ) -> MetadataRetrieval:
        """
        Execute metadata retrieval using the Salesforce CLI directly
        (sf project retrieve start --manifest + the job's package_xml).
        This supports arbitrary package.xml including "Complete Backup"
        (which triggers `sf project generate manifest --from-org` per Salesforce docs
        to get the real full set of components instead of a static subset).
        Works on Windows + all platforms.
        Stores a summary JSON + a full source.zip for reliable SFDX downloads.
        """
        org = await self._get_org(job.org_id)
        if not org or not org.encrypted_access_token:
            job.status = "failed"
            job.error_message = "Org has no access token — reconnect it first."
            await self.db.commit()
            try:
                return await self._load_fresh_retrieval(job.id)
            except Exception as load_exc:
                logger.warning("Failed to load fresh retrieval after no-token handling for job %s: %s", job.id, load_exc)
                return job

        job.status = "running"
        job.started_at = datetime.utcnow()
        await self.db.commit()

        # Job-specific project dir: prevents cross-contamination.
        # A prior 'complete' retrieve would leave tons of files in the shared
        # temp dir; a later custom package retrieve would then zip/include all of them,
        # making every job look like full-org backup.
        base_proj = self._get_project_dir()
        proj = os.path.join(base_proj, str(job.id))

        def _cleanup_proj():
            try:
                import shutil
                if os.path.isdir(proj) and str(job.id) in proj:
                    shutil.rmtree(proj, ignore_errors=True)
            except Exception as ce:
                logger.debug("cleanup proj %s: %s", proj, ce)

        # Ensure we start with a completely clean dir for this job (in case a prior
        # crashed attempt for the exact same job ID left partial files).
        _cleanup_proj()

        access_token = decrypt(org.encrypted_access_token)
        alias = f"cb-{str(org.id)[:8]}"

        try:
            try:
                result = await retrieve_metadata_direct(
                    access_token=access_token,
                    instance_url=org.instance_url,
                    alias=alias,
                    package_xml=job.package_xml,
                    project_dir=proj,
                    wait_minutes=20,
                )
            except Exception as first_exc:
                if not self._is_auth_error(first_exc):
                    raise
                refreshed_access = await self._refresh_org_access_token(org)
                if not refreshed_access:
                    raise
                access_token = refreshed_access
                result = await retrieve_metadata_direct(
                    access_token=access_token,
                    instance_url=org.instance_url,
                    alias=alias,
                    package_xml=job.package_xml,
                    project_dir=proj,
                    wait_minutes=20,
                )

            # Persist the *actual* manifest used into the job (key for Complete Backup).
            # Only when UI sent the complete sentinel token (for "Complete Org Backup" mode),
            # the generator wrote the real full manifest (per sf docs). We snapshot the
            # generated full package.xml here into the job record so that the stored
            # package_xml (and thus artifacts/downloads) reflect reality for complete mode.
            # For custom package mode we leave the user's exact provided package.xml as-is.
            try:
                was_sentinel = (job.package_xml or "").strip() == COMPLETE_ORG_BACKUP_SENTINEL
                if was_sentinel:
                    man_path = result.get("manifest")
                    if man_path and os.path.exists(man_path):
                        with open(man_path, "r", encoding="utf-8") as fh:
                            actual_xml = fh.read()
                        current = (job.package_xml or "").strip()
                        if actual_xml and actual_xml.strip() != current:
                            job.package_xml = actual_xml
                            await self.db.commit()
                            logger.info("Persisted actual used manifest (%d bytes) to job %s", len(actual_xml), job.id)
            except Exception as persist_exc:
                logger.warning("Failed to persist actual manifest back to retrieval job %s: %s", job.id, persist_exc)

            from app.infrastructure.di import get_artifact_store
            artifact_store = get_artifact_store()
            import io
            import zipfile

            artifact_save_error = None
            zip_key = None
            summary_key = None
            try:
                # Always archive the (job-specific) project dir contents as zip so downloads
                # are self-contained. We clean up the temp dir immediately after.
                zip_buffer = io.BytesIO()
                file_entries: list[dict] = []
                with zipfile.ZipFile(zip_buffer, "w", zipfile.ZIP_DEFLATED) as zf:
                    for root, _dirs, filenames in os.walk(proj):
                        rel_root = os.path.relpath(root, proj)
                        # Skip heavy/internal dirs
                        if any(x in rel_root for x in (".sf", ".sfdx", "__pycache__", "node_modules")):
                            continue
                        for fname in filenames:
                            fp = os.path.join(root, fname)
                            try:
                                arc = os.path.relpath(fp, proj).replace("\\", "/")
                                zf.write(fp, arc)
                                file_entries.append({"name": arc, "size": os.path.getsize(fp)})
                            except Exception:
                                continue

                zip_bytes = zip_buffer.getvalue()
                zip_key = f"retrievals/{job.id}/source.zip"
                await artifact_store.save(zip_key, zip_bytes, "application/zip")

                # Summary JSON (used by /artifact, /files, and old download paths)
                summary_key = f"retrievals/{job.id}/result.json"
                payload: dict[str, Any] = {
                    "retrieved_at": datetime.utcnow().isoformat(),
                    "org_id": str(org.id),
                    "org_name": org.name,
                    "source": "sfdx_cli_direct",
                    "package_xml": job.package_xml,
                    "cli_result": result.get("result"),
                    "success": result.get("success", False),
                    "files_count": result.get("files_count", len(file_entries)),
                    "files": result.get("files") or file_entries,
                    "source_zip_key": zip_key,
                    "project_dir": proj,
                    "manifest": result.get("manifest"),
                }
                await artifact_store.save(
                    summary_key,
                    json.dumps(payload, default=str).encode("utf-8"),
                    "application/json",
                )
            except Exception as art_exc:
                logger.warning("Failed to save artifacts for retrieval job %s (retrieve itself may have succeeded): %s", job.id, art_exc)
                artifact_save_error = str(art_exc)

            if artifact_save_error:
                # Still mark the job based on the retrieve result, but without artifact_key so downloads may not work.
                job.status = "success" if result.get("success") else "failed"
                if not result.get("success"):
                    errDetail = str(result.get("stderr") or result.get("error") or result.get("stdout") or "sf project retrieve start returned non-zero exit code")
                    job.error_message = errDetail[:500] + ("..." if len(errDetail) > 500 else "")
                job.completed_at = datetime.utcnow()
                await self.db.commit()
                _cleanup_proj()
            else:
                job.artifact_key = summary_key
                job.status = "success" if result.get("success") else "failed"
                if not result.get("success"):
                    errDetail = str(result.get("stderr") or result.get("error") or result.get("stdout") or "sf project retrieve start returned non-zero exit code")
                    job.error_message = errDetail[:500] + ("..." if len(errDetail) > 500 else "")
                job.completed_at = datetime.utcnow()
                await self.db.commit()
                logger.info("Direct CLI retrieve completed for job %s (success=%s, files=%s)", job.id, result.get("success"), payload["files_count"] if 'payload' in locals() else 0)
                _cleanup_proj()

        except Exception as exc:
            logger.exception("Direct CLI retrieve failed for job %s", job.id)
            job.status = "failed"
            job.error_message = str(exc)[:500]
            job.completed_at = datetime.utcnow()
            await self.db.commit()
            _cleanup_proj()
            try:
                return await self._load_fresh_retrieval(job.id)
            except Exception as load_exc:
                logger.warning("Failed to load fresh retrieval after error handling for job %s: %s", job.id, load_exc)
                return job

        try:
            return await self._load_fresh_retrieval(job.id)
        except Exception as load_exc:
            logger.warning("Failed to load fresh retrieval after successful retrieve for job %s: %s", job.id, load_exc)
            return job

    # ------------------------------------------------------------------
    # Package builder helpers (list types + list members for custom package.xml)
    # These call the direct CLI list commands after bridging auth.
    # Used by the UI "package create" / manifest builder in Retrievals.
    # ------------------------------------------------------------------

    async def list_metadata_types(self, org_id: uuid.UUID) -> list[dict[str, Any]]:
        """Return enabled metadata types for the org (for populating type selector)."""
        org = await self._get_org(org_id)
        if not org or not org.encrypted_access_token:
            return [{"error": "Org has no access token — reconnect it first."}]
        try:
            access_token = decrypt(org.encrypted_access_token)
            alias = f"cb-{str(org.id)[:8]}"
            proj = self._get_project_dir()
            try:
                types = await list_metadata_types_direct(
                    access_token=access_token,
                    instance_url=org.instance_url,
                    alias=alias,
                    project_dir=proj,
                )
            except Exception as first_exc:
                if not self._is_auth_error(first_exc):
                    raise
                refreshed_access = await self._refresh_org_access_token(org)
                if not refreshed_access:
                    raise
                types = await list_metadata_types_direct(
                    access_token=refreshed_access,
                    instance_url=org.instance_url,
                    alias=alias,
                    project_dir=proj,
                )
            return types
        except Exception as exc:
            logger.exception("list_metadata_types failed for org %s", org_id)
            return [{"error": str(exc)}]

    async def list_metadata_members(
        self, org_id: uuid.UUID, metadata_type: str, folder: str | None = None
    ) -> list[dict[str, Any]]:
        """Return concrete members for a metadata type (checkbox list in builder)."""
        org = await self._get_org(org_id)
        if not org or not org.encrypted_access_token:
            return [{"error": "Org has no access token — reconnect it first."}]
        if not metadata_type:
            return []
        try:
            access_token = decrypt(org.encrypted_access_token)
            alias = f"cb-{str(org.id)[:8]}"
            proj = self._get_project_dir()
            try:
                members = await list_metadata_members_direct(
                    access_token=access_token,
                    instance_url=org.instance_url,
                    alias=alias,
                    metadata_type=metadata_type,
                    folder=folder,
                    project_dir=proj,
                )
            except Exception as first_exc:
                if not self._is_auth_error(first_exc):
                    raise
                refreshed_access = await self._refresh_org_access_token(org)
                if not refreshed_access:
                    raise
                members = await list_metadata_members_direct(
                    access_token=refreshed_access,
                    instance_url=org.instance_url,
                    alias=alias,
                    metadata_type=metadata_type,
                    folder=folder,
                    project_dir=proj,
                )
            return members
        except Exception as exc:
            logger.exception("list_metadata_members failed for org %s type=%s", org_id, metadata_type)
            return [{"error": str(exc)}]

    # ------------------------------------------------------------------
    # Deploy metadata via MCP
    # ------------------------------------------------------------------

    async def deploy_via_mcp(
        self,
        deployment: Deployment,
        source_dir: str,
        check_only: bool = False,  # retained for API compat; the real tool has no checkonly
    ) -> Deployment:
        """
        Execute a metadata deployment using the SFDX MCP server.
        source_dir should be an absolute path to a Salesforce DX source directory.

        Note: ``check_only`` is not supported by the real ``deploy_metadata`` tool
        and is silently ignored.
        """
        org = await self._get_org(deployment.org_id)
        if not org or not org.encrypted_access_token:
            deployment.status = "failed"
            deployment.error_message = "Org has no access token — reconnect it first."
            await self.db.commit()
            return await self._load_fresh_deployment(deployment.id)

        deployment.status = "running"
        deployment.started_at = datetime.utcnow()
        await self.db.commit()

        try:
            async with self._make_client(org) as client:
                # The real deploy_metadata tool takes sourceDir as a list; no checkonly param.
                result = await client.deploy_metadata(
                    source_dirs=[source_dir],
                )

            deployment.status = "success"
            deployment.completed_at = datetime.utcnow()
            # Store the deployment ID returned by Salesforce if available
            if isinstance(result, dict):
                deployment.salesforce_deployment_id = result.get("id") or result.get("deployId")
            await self.db.commit()
            logger.info("MCP deploy completed for deployment %s", deployment.id)

        except Exception as exc:
            logger.exception("MCP deploy failed for deployment %s", deployment.id)
            deployment.status = "failed"
            deployment.error_message = str(exc)
            deployment.completed_at = datetime.utcnow()
            await self.db.commit()

        return await self._load_fresh_deployment(deployment.id)

    async def deploy_via_direct(
        self,
        deployment: Deployment,
        source_dir: str | None = None,
        manifest_path: str | None = None,
        check_only: bool = False,
        test_level: str | None = None,
        tests: list[str] | None = None,
        enable_pmd_check: bool = False,
        pmd_block_on_violation: bool = False,
        pmd_ruleset: str | None = None,
        pmd_only: bool = False,
    ) -> Deployment:
        """
        Execute metadata deployment/validation using the direct sf CLI (no MCP).
        This enables full support for check_only (validation / dry-run) and arbitrary
        test_level / specified tests.

        Internally routes to the correct modern sf command:
          - check_only + real tests → sf project deploy validate
          - check_only + NoTestRun  → sf project deploy start --dry-run
          - otherwise               → sf project deploy start
        (Never uses the obsolete --check-only flag.)

        Matches Workbench (Metadata API deploy with checkOnly) + current sf CLI
        project deploy validate / start --dry-run semantics.
        """
        org = await self._get_org(deployment.org_id)
        if not org or not org.encrypted_access_token:
            deployment.status = "failed"
            deployment.error_message = "Org has no access token — reconnect it first."
            await self.db.commit()
            return await self._load_fresh_deployment(deployment.id)

        deployment.status = "running"
        if pmd_only:
            deployment.status = "pmd_checking"
        elif check_only:
            deployment.status = "validating"
        deployment.started_at = datetime.utcnow()
        await self.db.commit()

        # If no explicit source_dir provided, try to resolve from linked retrieval's source zip artifact.
        # Supports the modern direct-retrieve path (summary JSON at artifact_key with "source_zip_key" + separate .zip)
        # and legacy cases where the zip bytes might have been stored directly.
        effective_source_dir = source_dir
        temp_proj_for_deploy: str | None = None
        cleanup_temp = False

        if not effective_source_dir and deployment.retrieval_id:
            try:
                from app.infrastructure.di import get_artifact_store
                artifact_store = get_artifact_store()
                ret = await self._load_fresh_retrieval(deployment.retrieval_id)
                if ret and ret.artifact_key:
                    content = await artifact_store.get(ret.artifact_key)
                    zip_bytes = None
                    if isinstance(content, (bytes, bytearray)):
                        # Fast path: the stored artifact IS the zip
                        if len(content) >= 4 and content[:4] == b'PK\x03\x04':
                            zip_bytes = content
                        else:
                            # Common case: artifact_key points to the summary JSON (result.json) which contains "source_zip_key"
                            try:
                                text = content.decode("utf-8", errors="replace")
                                summary = json.loads(text) if text.strip().startswith(("{", "[")) else {}
                                if isinstance(summary, dict):
                                    for k in ("source_zip_key", "source_zip", "zip_key", "sourceZipKey"):
                                        zk = summary.get(k)
                                        if zk:
                                            try:
                                                zb = await artifact_store.get(zk)
                                                if isinstance(zb, (bytes, bytearray)) and len(zb) >= 4 and zb[:4] == b'PK\x03\x04':
                                                    zip_bytes = zb
                                                    break
                                            except Exception as zk_exc:
                                                logger.debug("Failed to fetch referenced zip key %s: %s", zk, zk_exc)
                            except Exception as parse_exc:
                                logger.debug("Retrieval artifact %s not parseable as summary JSON: %s", ret.artifact_key, parse_exc)

                    if zip_bytes:
                        import io
                        import zipfile
                        import shutil
                        base_tmp = self._get_project_dir()
                        temp_proj_for_deploy = os.path.join(base_tmp, f"deploy-{deployment.id}")
                        if os.path.isdir(temp_proj_for_deploy):
                            shutil.rmtree(temp_proj_for_deploy, ignore_errors=True)
                        os.makedirs(temp_proj_for_deploy, exist_ok=True)
                        with zipfile.ZipFile(io.BytesIO(zip_bytes)) as zf:
                            zf.extractall(temp_proj_for_deploy)
                        # The zip root is usually the project root (has sfdx-project.json + force-app)
                        if os.path.isdir(os.path.join(temp_proj_for_deploy, "force-app")):
                            effective_source_dir = "force-app"
                        else:
                            for root, dirs, _ in os.walk(temp_proj_for_deploy):
                                if "force-app" in dirs:
                                    effective_source_dir = os.path.relpath(os.path.join(root, "force-app"), temp_proj_for_deploy).replace("\\", "/") or "force-app"
                                    break
                        if not effective_source_dir:
                            effective_source_dir = "."
                        cleanup_temp = True
                        logger.info("Unpacked retrieval source zip for direct deploy of %s -> %s (source_dir=%s)", deployment.id, temp_proj_for_deploy, effective_source_dir)
                    else:
                        logger.warning(
                            "Retrieval %s (artifact_key=%s) did not contain or reference a usable source.zip (got %d bytes, not a zip). "
                            "Deployments from MCP-style retrievals or legacy artifacts require an explicit source_dir or manifest, "
                            "or re-retrieve using the direct CLI path.",
                            deployment.retrieval_id, ret.artifact_key, len(content) if isinstance(content, (bytes, bytearray)) else 0
                        )
            except Exception as unpack_exc:
                logger.warning("Could not unpack retrieval artifact for deploy %s: %s", deployment.id, unpack_exc)

        # Guard: if this deployment was created from a retrieval but we have nothing deployable, fail with a clear message
        # instead of running sf with an empty project (which would do a no-op or tracking-based deploy).
        if deployment.retrieval_id and not effective_source_dir and not manifest_path:
            deployment.status = "failed"
            deployment.error_message = (
                f"Could not find deployable source for retrieval {deployment.retrieval_id}. "
                "The linked retrieval's artifact was not a direct-retrieve source.zip (or unpack failed). "
                "Re-run the retrieval (prefer the direct method) or create the deployment with explicit source_dir/manifest."
            )
            deployment.completed_at = datetime.utcnow()
            await self.db.commit()
            return await self._load_fresh_deployment(deployment.id)

        # General guard for calls that reach here without any source (manual create without retrieval, etc.)
        if not effective_source_dir and not manifest_path:
            deployment.status = "failed"
            deployment.error_message = "No source_dir or manifest provided for deployment, and no retrieval artifact to derive source from."
            deployment.completed_at = datetime.utcnow()
            await self.db.commit()
            return await self._load_fresh_deployment(deployment.id)

        try:
            access_token = decrypt(org.encrypted_access_token)
            alias = f"cb-{str(org.id)[:8]}"
            proj = temp_proj_for_deploy or self._get_project_dir()

            if enable_pmd_check:
                from app.application.services.pmd_analysis_service import PMDAnalysisService

                pmd_service = PMDAnalysisService(self.db)
                pmd_source_root = os.path.join(proj, effective_source_dir) if effective_source_dir else proj
                pmd_result = await pmd_service.analyze_directory(pmd_source_root, deployment_id=str(deployment.id))
                deployment.options = {
                    **(deployment.options or {}),
                    "pmd_result": pmd_result,
                    "pmd_ruleset": pmd_ruleset,
                    "pmd_checked_at": datetime.utcnow().isoformat(),
                }
                await self.db.commit()

                high_or_critical = (pmd_result.get("totals", {}).get("high", 0) + pmd_result.get("totals", {}).get("critical", 0))
                if pmd_block_on_violation and high_or_critical > 0:
                    deployment.status = "failed"
                    deployment.error_message = (
                        f"PMD pre-check blocked deployment with {high_or_critical} high/critical finding(s). "
                        "Download the IBM PMD report and remediate before retrying."
                    )
                    deployment.completed_at = datetime.utcnow()
                    await self.db.commit()
                    return await self._load_fresh_deployment(deployment.id)

                if pmd_only:
                    # PMD-first workflow: stop here and let user explicitly decide next action.
                    deployment.status = "pending"
                    deployment.error_message = None
                    deployment.completed_at = datetime.utcnow()
                    await self.db.commit()
                    return await self._load_fresh_deployment(deployment.id)

            result = await deploy_metadata_direct(
                access_token=access_token,
                instance_url=org.instance_url,
                alias=alias,
                source_dir=effective_source_dir,
                manifest_path=manifest_path,
                project_dir=proj,
                check_only=check_only,
                test_level=test_level,
                tests=tests,
                wait_minutes=25,
            )

            if result.get("success"):
                deployment.status = "success"
                deployment.salesforce_deployment_id = result.get("salesforce_deployment_id")
            else:
                deployment.status = "failed"
                err = result.get("stderr") or result.get("error") or str(result.get("result"))
                deployment.error_message = str(err)[:2000] if err else "Direct deploy failed (see logs)"

            deployment.completed_at = datetime.utcnow()
            await self.db.commit()
            logger.info("Direct CLI deploy completed for deployment %s (check_only=%s, test_level=%s)", deployment.id, check_only, test_level)

        except Exception as exc:
            logger.exception("Direct deploy failed for deployment %s", deployment.id)
            deployment.status = "failed"
            deployment.error_message = str(exc)[:2000]
            deployment.completed_at = datetime.utcnow()
            await self.db.commit()

        finally:
            if cleanup_temp and temp_proj_for_deploy and os.path.isdir(temp_proj_for_deploy):
                try:
                    import shutil
                    shutil.rmtree(temp_proj_for_deploy, ignore_errors=True)
                except Exception:
                    pass

        return await self._load_fresh_deployment(deployment.id)

    async def quick_deploy_via_direct(
        self,
        deployment: Deployment,
        prior_job_id: str,
    ) -> Deployment:
        """Perform quick deploy of a previously validated deployment (sf project deploy quick)."""
        org = await self._get_org(deployment.org_id)
        if not org or not org.encrypted_access_token:
            deployment.status = "failed"
            deployment.error_message = "Org has no access token — reconnect it first."
            await self.db.commit()
            return await self._load_fresh_deployment(deployment.id)

        deployment.status = "deploying"
        deployment.started_at = datetime.utcnow()
        await self.db.commit()

        try:
            access_token = decrypt(org.encrypted_access_token)
            alias = f"cb-{str(org.id)[:8]}"
            proj = self._get_project_dir()

            result = await quick_deploy_direct(
                access_token=access_token,
                instance_url=org.instance_url,
                alias=alias,
                job_id=prior_job_id,
                project_dir=proj,
                wait_minutes=15,
            )

            if result.get("success"):
                deployment.status = "success"
                deployment.salesforce_deployment_id = result.get("salesforce_deployment_id") or prior_job_id
            else:
                deployment.status = "failed"
                deployment.error_message = (result.get("stderr") or "Quick deploy failed")[:800]

            deployment.completed_at = datetime.utcnow()
            await self.db.commit()
        except Exception as exc:
            logger.exception("Quick deploy failed for %s", deployment.id)
            deployment.status = "failed"
            deployment.error_message = str(exc)[:2000]
            deployment.completed_at = datetime.utcnow()
            await self.db.commit()

        return await self._load_fresh_deployment(deployment.id)

    # ------------------------------------------------------------------
    # Run Apex tests via MCP
    # ------------------------------------------------------------------

    async def run_apex_tests_via_mcp(
        self,
        org_id: uuid.UUID,
        class_names: list[str] | None = None,
        test_level: str = "RunLocalTests",
    ) -> dict[str, Any]:
        """
        Run Apex tests in the org using the SFDX MCP server.
        Returns the raw MCP tool result.
        """
        org = await self._get_org(org_id)
        if not org or not org.encrypted_access_token:
            return {"error": "Org has no access token — reconnect it first."}

        try:
            async with self._make_client(org) as client:
                result = await client.run_apex_tests(
                    class_names=class_names,
                    test_level=test_level,
                )
            return {"status": "success", "result": result}
        except Exception as exc:
            logger.exception("MCP apex test failed for org %s", org_id)
            return {"status": "failed", "error": str(exc)}

    # ------------------------------------------------------------------
    # Generic agentic tool call
    # ------------------------------------------------------------------

    async def run_tool(
        self,
        org_id: uuid.UUID,
        tool_name: str,
        arguments: dict[str, Any],
        toolsets: str = "orgs,metadata,data,testing,users",
        timeout: float = 120.0,
    ) -> dict[str, Any]:
        """
        Run any SFDX MCP tool by name for the given org.
        This is the core agentic entrypoint — the frontend can call
        POST /api/v1/agent/run with {org_id, tool, args} for ad-hoc operations.
        """
        org = await self._get_org(org_id)
        if not org:
            return {"error": f"Org {org_id} not found"}
        if not org.encrypted_access_token:
            return {"error": "Org has no access token — reconnect it first."}

        try:
            org_alias = f"cb-{str(org.id)[:8]}"
            project_dir = self._get_project_dir()
            # Inject standard MCP params; user-supplied values take priority.
            merged_args: dict[str, Any] = {
                "usernameOrAlias": org_alias,
                "directory": project_dir,
                **arguments,
            }
            async with self._make_client(org, toolsets=toolsets) as client:
                result = await client.call_tool(tool_name, merged_args, timeout=timeout)
            return {"status": "success", "tool": tool_name, "result": result}
        except Exception as exc:
            logger.exception("MCP tool '%s' failed for org %s", tool_name, org_id)
            return {"status": "failed", "tool": tool_name, "error": str(exc)}

    async def list_tools_for_org(
        self,
        org_id: uuid.UUID,
        toolsets: str = "orgs,metadata,data,testing,users",
    ) -> dict[str, Any]:
        """Return all available MCP tools for the given toolsets."""
        org = await self._get_org(org_id)
        if not org or not org.encrypted_access_token:
            return {"error": "Org not found or no access token"}
        try:
            async with self._make_client(org, toolsets=toolsets) as client:
                tools = await client.list_tools()
            return {"status": "success", "tools": tools}
        except Exception as exc:
            return {"status": "failed", "error": str(exc)}

    async def run_tool_streaming(
        self,
        org_id: uuid.UUID,
        tool_name: str,
        arguments: dict[str, Any],
        toolsets: str = "orgs,metadata,data,testing,users",
        timeout: float = 120.0,
    ) -> AsyncGenerator[dict[str, Any], None]:
        """
        Async generator that streams progress events for a single MCP tool call.
        Yields dicts with at minimum {phase, msg}; the final 'done' event also has 'result'.
        Intended to back the /agent/run/stream SSE endpoint.
        """
        org = await self._get_org(org_id)
        if not org:
            yield {"phase": "error", "msg": f"Org {org_id} not found"}
            return
        if not org.encrypted_access_token:
            yield {"phase": "error", "msg": "Org has no access token — reconnect it first"}
            return

        access_token = decrypt(org.encrypted_access_token)
        org_alias = f"cb-{str(org.id)[:8]}"

        yield {"phase": "init", "msg": f"Starting agentic operation for org: {org.name}"}

        async for event in run_mcp_tool_streaming(
            access_token=access_token,
            instance_url=org.instance_url,
            org_alias=org_alias,
            tool_name=tool_name,
            arguments=arguments,
            toolsets=toolsets,
            timeout=timeout,
            project_dir=self._get_project_dir(),
        ):
            yield event

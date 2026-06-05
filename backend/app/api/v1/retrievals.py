"""
Metadata Retrieval API Endpoints
"""

import io
import json
import logging
import zipfile
from typing import Any
from uuid import UUID

from fastapi import APIRouter, BackgroundTasks, Body, Depends, HTTPException, Query
from fastapi.responses import StreamingResponse
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.dependencies import get_db_session
from app.application.services.metadata_retrieval_service import MetadataRetrievalService
from app.application.services.sfdx_mcp_service import SFDXMCPService
from app.infrastructure.adapters.artifact.base import ArtifactStore
from app.infrastructure.di import get_artifact_store
from app.schemas.metadata_retrieval import (
    MetadataRetrievalCreate,
    MetadataRetrievalResponse,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/retrievals", tags=["Metadata Retrieval"])


async def _run_retrieval_background(job_id: str) -> None:
    """
    FastAPI background task: runs retrieval in-process after the HTTP response
    is sent.  Opens its own DB session so the endpoint's session can close cleanly.
    No Celery worker required — works in any single-pod deployment.
    """
    from app.infrastructure.db.engine import AsyncSessionLocal
    async with AsyncSessionLocal() as db:
        try:
            service = MetadataRetrievalService(db)
            await service.start_retrieval(job_id, use_background=False)
        except Exception:
            logger.exception("Background retrieval failed for job %s", job_id)


@router.post("", response_model=MetadataRetrievalResponse)
async def create_retrieval_job(
    payload: MetadataRetrievalCreate,
    background_tasks: BackgroundTasks,
    use_background: bool = Query(True, description="Return immediately with status=queued and run retrieval in the background."),
    db: AsyncSession = Depends(get_db_session),
):
    service = MetadataRetrievalService(db)
    job = await service.create_retrieval_job(
        org_id=payload.org_id,
        package_xml=payload.package_xml,
        description=payload.description,
    )
    if use_background:
        # Schedule in-process background task — no Celery worker needed.
        background_tasks.add_task(_run_retrieval_background, str(job.id))
        return job  # status="queued"; task starts after response is sent
    updated_job = await service.start_retrieval(job.id, use_background=False)
    return updated_job


@router.get("", response_model=list[MetadataRetrievalResponse])
async def list_retrieval_jobs(
    org_id: UUID | None = None,
    db: AsyncSession = Depends(get_db_session),
):
    service = MetadataRetrievalService(db)
    if org_id:
        jobs = await service.list_jobs_for_org(org_id)
    else:
        jobs = await service.list_all_jobs()
    return jobs


@router.get("/{job_id}", response_model=MetadataRetrievalResponse)
async def get_retrieval_job(job_id: UUID, db: AsyncSession = Depends(get_db_session)):
    service = MetadataRetrievalService(db)
    job = await service.get_job(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Retrieval job not found")
    return job


@router.get("/{job_id}/artifact")
async def get_retrieval_artifact(job_id: UUID, db: AsyncSession = Depends(get_db_session)):
    """Returns the stored artifact content for a completed retrieval."""
    service = MetadataRetrievalService(db)
    content = await service.get_artifact_content(job_id)
    if content is None:
        raise HTTPException(status_code=404, detail="Artifact not found or job not completed")
    return content


@router.get("/{job_id}/download")
async def download_retrieval_artifact(
    job_id: UUID,
    format: str = "sfdx",  # "sfdx" or "json"
    db: AsyncSession = Depends(get_db_session)
):
    """
    Download the retrieval artifact as a ZIP file.
    
    Formats:
    - sfdx: Proper SFDX project structure (force-app/main/default/)
    - json: Raw JSON artifact
    """
    service = MetadataRetrievalService(db)
    job = await service.get_job(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Retrieval job not found")
    if job.status != "success" or not job.artifact_key:
        raise HTTPException(status_code=400, detail="Retrieval not completed or no artifact available")
    
    # Get the artifact content (summary json)
    content = await service.get_artifact_content(job_id)
    if content is None:
        raise HTTPException(status_code=404, detail="Artifact not found")

    # Fast path: if we have a pre-built source.zip from direct CLI retrieve, serve it
    # (this gives the user the *real* files retrieved by sf, including for Complete Backup)
    artifact_store: ArtifactStore = get_artifact_store()
    if format == "sfdx" and isinstance(content, dict) and content.get("source_zip_key"):
        try:
            zip_bytes = await artifact_store.get(content["source_zip_key"])
            filename = f"sfdx_project_{str(job_id)[:8]}.zip"
            return StreamingResponse(
                io.BytesIO(zip_bytes),
                media_type="application/zip",
                headers={"Content-Disposition": f"attachment; filename={filename}"},
            )
        except Exception as e:
            logging.getLogger(__name__).warning("source_zip_key present but fetch failed for %s: %s", job_id, e)
            # fall through to legacy rebuild

    if format == "sfdx":
        # Legacy rebuild path (for old MCP / prototype artifacts that only stored
        # file contents inside the JSON result)
        zip_buffer = io.BytesIO()
        with zipfile.ZipFile(zip_buffer, 'w', zipfile.ZIP_DEFLATED) as zip_file:
            project_name = f"retrieval_{str(job_id)[:8]}"
            sfdx_project = {
                "packageDirectories": [{"path": "force-app", "default": True}],
                "name": project_name,
                "namespace": "",
                "sfdcLoginUrl": "https://login.salesforce.com",
                "sourceApiVersion": "62.0"
            }
            zip_file.writestr(f"{project_name}/sfdx-project.json", json.dumps(sfdx_project, indent=2))

            forceignore = """# List files or directories below to ignore them when running force:source:push, force:source:pull, and force:source:status
package.xml
**/jsconfig.json
**/.eslintrc.json
**/lwc/**/*.css
**/lwc/**/*.html
**/lwc/**/*.json
**/lwc/**/*.svg
**/lwc/**/*.xml
**/__tests__/**
"""
            zip_file.writestr(f"{project_name}/.forceignore", forceignore)

            readme = f"""# Salesforce DX Project: {project_name}

Retrieved from Salesforce on {content.get('retrieved_at', 'unknown date') if isinstance(content, dict) else 'unknown'}
Org: {content.get('org_name', 'Unknown') if isinstance(content, dict) else 'Unknown'}

## Deploy to Org
sf project deploy start --source-dir force-app
"""
            zip_file.writestr(f"{project_name}/README.md", readme)

            if isinstance(content, dict):
                # old prototype apex_classes
                if 'apex_classes' in content:
                    for cls in content.get('apex_classes', []):
                        if isinstance(cls, dict):
                            name = cls.get('name', 'Unknown')
                            cls_content = f"public class {name} {{ /* retrieved via fallback */ }}"
                            zip_file.writestr(f"{project_name}/force-app/main/default/classes/{name}.cls", cls_content)
                            meta_xml = """<?xml version="1.0" encoding="UTF-8"?>\n<ApexClass xmlns="http://soap.sforce.com/2006/04/metadata">\n    <apiVersion>59.0</apiVersion>\n    <status>Active</status>\n</ApexClass>"""
                            zip_file.writestr(f"{project_name}/force-app/main/default/classes/{name}.cls-meta.xml", meta_xml)

                # MCP-style result with embedded file contents
                res = content.get('result') or content.get('cli_result')
                if isinstance(res, dict) and 'files' in res:
                    for fi in res.get('files', []):
                        if isinstance(fi, dict):
                            nm = fi.get('fullName') or fi.get('name') or 'Unknown'
                            c = fi.get('content', '')
                            zip_file.writestr(f"{project_name}/{nm}", c if isinstance(c, str) else str(c))

        zip_buffer.seek(0)
        filename = f"sfdx_project_{str(job_id)[:8]}.zip"
        return StreamingResponse(
            io.BytesIO(zip_buffer.read()),
            media_type="application/zip",
            headers={"Content-Disposition": f"attachment; filename={filename}"},
        )
    else:
        # JSON raw
        filename = f"retrieval_{str(job_id)[:8]}.zip"
        zip_buffer = io.BytesIO()
        with zipfile.ZipFile(zip_buffer, 'w', zipfile.ZIP_DEFLATED) as zf:
            zf.writestr(f"retrieval_{str(job_id)[:8]}.json", json.dumps(content, indent=2, default=str))
        zip_buffer.seek(0)
        return StreamingResponse(
            io.BytesIO(zip_buffer.read()),
            media_type="application/zip",
            headers={"Content-Disposition": f"attachment; filename={filename}"},
        )


@router.get("/{job_id}/files")
async def list_retrieval_files(job_id: UUID, db: AsyncSession = Depends(get_db_session)):
    """List the files/structure in the retrieval artifact."""
    service = MetadataRetrievalService(db)
    job = await service.get_job(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Retrieval job not found")
    if job.status != "success" or not job.artifact_key:
        raise HTTPException(status_code=400, detail="Retrieval not completed or no artifact available")
    
    content = await service.get_artifact_content(job_id)
    if content is None:
        raise HTTPException(status_code=404, detail="Artifact not found")
    
    # Parse the content to extract file structure
    files: list[dict] = []
    metadata: dict = {}
    
    if isinstance(content, dict):
        # New direct CLI path stores "files" list (from source zip or collected)
        if content.get("files"):
            for f in content.get("files", []):
                if isinstance(f, dict):
                    files.append({
                        "name": f.get("name") or f.get("fullName", "unknown"),
                        "type": f.get("type", "file"),
                        "size": f.get("size", 0),
                    })
        
        # Legacy prototype
        elif 'apex_classes' in content:
            for cls in content.get('apex_classes', []):
                if isinstance(cls, dict) and 'name' in cls:
                    files.append({
                        "name": f"{cls['name']}.cls",
                        "type": "ApexClass",
                        "size": len(cls.get('name', '')) * 50
                    })
        
        # MCP result inside 'result'
        elif 'result' in content:
            res = content['result']
            if isinstance(res, dict) and res.get('files'):
                for fi in res.get('files', []):
                    if isinstance(fi, dict):
                        files.append({
                            "name": fi.get('fullName') or fi.get('name', 'unknown'),
                            "type": fi.get('type', 'file'),
                            "size": fi.get('size', len(str(fi.get('content', '')))) if isinstance(fi.get('content'), str) else 0,
                        })
            elif isinstance(res, dict):
                for k, v in res.items():
                    files.append({"name": k, "type": "file" if isinstance(v, (str, int)) else "object", "size": len(str(v)) if v else 0})
        
        # Also support cli_result from direct
        if not files and content.get('cli_result'):
            cr = content['cli_result']
            if isinstance(cr, dict) and cr.get('files'):
                for fi in cr.get('files', []):
                    if isinstance(fi, dict):
                        files.append({"name": fi.get('name', 'f'), "type": "file", "size": fi.get('size', 0)})
        
        metadata = {
            "retrieved_at": content.get("retrieved_at"),
            "org_name": content.get("org_name"),
            "metadata_types": content.get("metadata_types") or content.get("metadata_types", []),
            "total_files": len(files) or content.get("files_count", 0),
            "source": content.get("source", "unknown"),
            "has_full_zip": bool(content.get("source_zip_key")),
        }
    
    return {
        "job_id": str(job_id),
        "files": files,
        "metadata": metadata
    }


@router.delete("/{job_id}", status_code=204)
async def delete_retrieval_job(job_id: UUID, db: AsyncSession = Depends(get_db_session)):
    """Delete a retrieval job record."""
    service = MetadataRetrievalService(db)
    deleted = await service.delete_job(job_id)
    if not deleted:
        raise HTTPException(status_code=404, detail="Retrieval job not found")


# ------------------------------------------------------------------
# Package Builder / "Create Package" support endpoints
# Used by the Retrievals UI to let users pick metadata types, load
# the actual list of components (ApexClass etc), checkbox select,
# and add into the package.xml editor.
# ------------------------------------------------------------------

@router.post("/package-builder/metadata-types")
async def list_metadata_types_for_builder(
    payload: dict[str, Any] = Body(...),
    db: AsyncSession = Depends(get_db_session),
):
    """Return list of metadata types enabled in the org.

    Body: { "org_id": "<uuid>" }
    Response: list of type objects with xmlName, directoryName, inFolder, etc.
    """
    org_id = payload.get("org_id")
    if not org_id:
        raise HTTPException(status_code=400, detail="org_id required")
    try:
        svc = SFDXMCPService(db)
        types = await svc.list_metadata_types(UUID(org_id))
        return {"types": types}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to list metadata types: {str(e)}")


@router.post("/package-builder/metadata-members")
async def list_metadata_members_for_builder(
    payload: dict[str, Any] = Body(...),
    db: AsyncSession = Depends(get_db_session),
):
    """Return list of concrete members for a metadata type (for checkboxes).

    Body: { "org_id": "<uuid>", "metadataType": "ApexClass", "folder": "optionalFolderName" }
    Response: { "members": [ {fullName, ...}, ... ] }
    """
    org_id = payload.get("org_id")
    mtype = payload.get("metadataType") or payload.get("metadata_type")
    folder = payload.get("folder")
    if not org_id or not mtype:
        raise HTTPException(status_code=400, detail="org_id and metadataType required")
    try:
        svc = SFDXMCPService(db)
        members = await svc.list_metadata_members(UUID(org_id), str(mtype), folder)
        return {"members": members, "metadataType": mtype, "folder": folder}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to list members: {str(e)}")

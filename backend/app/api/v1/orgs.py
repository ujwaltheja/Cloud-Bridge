"""
Salesforce Org Management API Endpoints
"""

from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.dependencies import get_db_session
from app.core.config import get_settings
from app.application.services.salesforce_auth import SalesforceAuthService
from app.application.services.salesforce_org_service import SalesforceOrgService
from app.schemas.salesforce_org import (
    ConnectionTestResponse,
    SalesforceOrgCreateJWT,
    SalesforceOrgCreateOAuth,
    SalesforceOrgResponse,
)

sf_auth = SalesforceAuthService()

router = APIRouter(prefix="/orgs", tags=["Salesforce Orgs"])


@router.post("", response_model=SalesforceOrgResponse, status_code=status.HTTP_201_CREATED)
async def create_org(
    payload: SalesforceOrgCreateOAuth | SalesforceOrgCreateJWT,
    db: AsyncSession = Depends(get_db_session),
):
    service = SalesforceOrgService(db)

    if payload.auth_method == "jwt":
        return await service.create_org_jwt(payload)
    else:
        return await service.create_org_oauth(payload)


@router.get("", response_model=list[SalesforceOrgResponse])
async def list_orgs(db: AsyncSession = Depends(get_db_session)):
    service = SalesforceOrgService(db)
    return await service.list_orgs()


@router.get("/{org_id}", response_model=SalesforceOrgResponse)
async def get_org(org_id: UUID, db: AsyncSession = Depends(get_db_session)):
    service = SalesforceOrgService(db)
    org = await service.get_org(org_id)
    if not org:
        raise HTTPException(status_code=404, detail="Organization not found")
    return org


@router.delete("/{org_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_org(org_id: UUID, db: AsyncSession = Depends(get_db_session)):
    service = SalesforceOrgService(db)
    deleted = await service.delete_org(org_id)
    if not deleted:
        raise HTTPException(status_code=404, detail="Organization not found")


@router.post("/{org_id}/test", response_model=ConnectionTestResponse)
async def test_org_connection(org_id: UUID, db: AsyncSession = Depends(get_db_session)):
    service = SalesforceOrgService(db)
    return await service.test_connection(org_id)


# =============================================================================
# OAuth Flow Endpoints
# =============================================================================

class OAuthStartRequest(BaseModel):
    redirect_uri: str
    client_id: str   # Connected App Consumer Key
    client_secret: str | None = None  # Consumer Secret (required by some Connected Apps)
    code_challenge: str | None = None
    code_challenge_method: str = "S256"


@router.post("/{org_id}/oauth/start")
async def start_oauth_flow(
    org_id: UUID,
    payload: OAuthStartRequest,
    db: AsyncSession = Depends(get_db_session),
):
    """Creates/updates the client_id on the org and returns the Salesforce login URL."""
    service = SalesforceOrgService(db)
    try:
        auth_url = await service.start_oauth_flow(
            org_id=org_id,
            client_id=payload.client_id,
            client_secret=payload.client_secret,
            redirect_uri=payload.redirect_uri,
            code_challenge=payload.code_challenge,
            code_challenge_method=payload.code_challenge_method,
        )
        return {"authorization_url": auth_url}
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


class OAuthCallbackRequest(BaseModel):
    code: str
    redirect_uri: str
    code_verifier: str | None = None


@router.post("/oauth/callback")
async def oauth_callback_post(
    payload: OAuthCallbackRequest,
    state: str,
    db: AsyncSession = Depends(get_db_session),
):
    """Handles the OAuth callback from Salesforce (POST version)."""
    success, message = await _handle_oauth_callback(state, payload.code, payload.redirect_uri, db, payload.code_verifier)
    return {"success": success, "message": message}


@router.get("/oauth/callback")
async def oauth_callback_get(
    code: str,
    state: str,
    redirect_uri: str = "",
    db: AsyncSession = Depends(get_db_session),
):
    """Handles the OAuth callback from Salesforce (GET version - used after redirect)."""
    success, message = await _handle_oauth_callback(state, code, redirect_uri, db)
    if success:
        return {"success": True, "message": message}
    else:
        raise HTTPException(status_code=400, detail=message)


async def _handle_oauth_callback(
    state: str, code: str, redirect_uri: str, db: AsyncSession, code_verifier: str | None = None
) -> tuple[bool, str]:
    try:
        org_id = UUID(state)
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid state")

    service = SalesforceOrgService(db)
    return await service.handle_oauth_callback(
        code, org_id, redirect_uri or get_settings().sf_redirect_uri, code_verifier=code_verifier
    )

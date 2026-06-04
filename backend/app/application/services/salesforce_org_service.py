"""
Salesforce Org Management Service

Handles:
- Adding organizations via Web OAuth2 and JWT Server-to-Server
- Token encryption / decryption
- Connection testing against real Salesforce
"""

import uuid
from datetime import datetime

import httpx
from sqlalchemy import delete, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.application.services.salesforce_auth import SalesforceAuthService
from app.core.config import get_settings
from app.infrastructure.db.models import SalesforceAuthMethod, SalesforceOrg
from app.infrastructure.encryption import decrypt, encrypt
from app.schemas.salesforce_org import (
    ConnectionTestResponse,
    SalesforceOrgCreateJWT,
    SalesforceOrgCreateOAuth,
    SalesforceOrgResponse,
)

settings = get_settings()
sf_auth = SalesforceAuthService()


class SalesforceOrgService:
    def __init__(self, db: AsyncSession):
        self.db = db

    # -------------------------------------------------------------------------
    # CRUD
    # -------------------------------------------------------------------------

    async def create_org_oauth(self, data: SalesforceOrgCreateOAuth) -> SalesforceOrgResponse:
        """Create org record for Web OAuth flow (user will authenticate via browser redirect)."""
        org = SalesforceOrg(
            name=data.name,
            org_type=data.org_type,
            auth_method=SalesforceAuthMethod.OAUTH_WEB,
            client_id=data.client_id,
            is_active=True,
        )
        self.db.add(org)
        await self.db.commit()
        await self.db.refresh(org)
        return SalesforceOrgResponse.model_validate(org)

    async def create_org_jwt(self, data: SalesforceOrgCreateJWT) -> SalesforceOrgResponse:
        """Create org using JWT Server-to-Server and immediately fetch access token."""
        encrypted_key = encrypt(data.private_key)

        org = SalesforceOrg(
            name=data.name,
            org_type=data.org_type,
            auth_method=SalesforceAuthMethod.JWT,
            client_id=data.client_id,
            username=data.username,
            instance_url=data.login_url,
            encrypted_private_key=encrypted_key,
            is_active=True,
        )
        self.db.add(org)
        await self.db.commit()
        await self.db.refresh(org)

        # Attempt to get initial access token right away
        try:
            tokens = await sf_auth.get_jwt_access_token(
                client_id=data.client_id,
                username=data.username,
                private_key=data.private_key,
                login_url=data.login_url,
            )
            org.encrypted_access_token = encrypt(tokens["access_token"])
            org.instance_url = tokens["instance_url"]
            if tokens.get("id"):
                org.org_id = tokens["id"].split("/")[-1]
            org.last_connection_status = "success"
            await self.db.commit()
        except Exception as e:
            org.last_connection_status = "error"
            org.last_connection_error = str(e)
            await self.db.commit()

        return SalesforceOrgResponse.model_validate(org)

    async def list_orgs(self) -> list[SalesforceOrgResponse]:
        result = await self.db.execute(
            select(SalesforceOrg).order_by(SalesforceOrg.created_at.desc())
        )
        orgs = result.scalars().all()
        return [SalesforceOrgResponse.model_validate(o) for o in orgs]

    async def _get_org_row(self, org_id: uuid.UUID) -> "SalesforceOrg | None":
        """Lookup org row, with fallback for legacy int-stored PKs from pre-GUID sqlite bugs."""
        result = await self.db.execute(select(SalesforceOrg).where(SalesforceOrg.id == org_id))
        org = result.scalar_one_or_none()
        if org is None and isinstance(org_id, uuid.UUID):
            # Legacy SQLite rows may store UUIDs as 32-char hex (no dashes).
            result = await self.db.execute(
                select(SalesforceOrg).where(func.replace(SalesforceOrg.id, "-", "") == org_id.hex)
            )
            org = result.scalar_one_or_none()
        if org is None and isinstance(org_id, uuid.UUID):
            try:
                result = await self.db.execute(
                    select(SalesforceOrg).where(SalesforceOrg.id == org_id.int)
                )
                org = result.scalar_one_or_none()
            except Exception:
                pass
        return org

    async def get_org(self, org_id: uuid.UUID) -> SalesforceOrgResponse | None:
        org = await self._get_org_row(org_id)
        if org:
            return SalesforceOrgResponse.model_validate(org)
        return None

    async def delete_org(self, org_id: uuid.UUID) -> bool:
        stmt = delete(SalesforceOrg).where(func.replace(SalesforceOrg.id, "-", "") == org_id.hex)
        result = await self.db.execute(stmt)
        await self.db.commit()
        return (result.rowcount or 0) > 0

    # ------------------------------------------------------------------
    # OAuth Flow Helpers
    # ------------------------------------------------------------------

    async def start_oauth_flow(
        self,
        org_id: uuid.UUID,
        client_id: str,
        redirect_uri: str,
        client_secret: str | None = None,
        code_challenge: str | None = None,
        code_challenge_method: str = "S256",
    ) -> str:
        """Updates the org with client_id/secret and returns the Salesforce authorization URL."""
        org = await self._get_org_row(org_id)
        if not org:
            raise Exception("Organization not found")

        org.client_id = client_id
        if client_secret:
            org.encrypted_client_secret = encrypt(client_secret)
        await self.db.commit()

        auth_url = sf_auth.get_authorization_url(
            client_id=client_id,
            redirect_uri=redirect_uri,
            org_type=org.org_type,
            state=str(org_id),
            code_challenge=code_challenge,
            code_challenge_method=code_challenge_method,
        )
        return auth_url

    async def handle_oauth_callback(
        self, code: str, org_id: uuid.UUID, redirect_uri: str, code_verifier: str | None = None
    ) -> tuple[bool, str]:
        """Handles the OAuth callback and stores tokens."""
        org = await self._get_org_row(org_id)
        if not org or not org.client_id:
            return False, "Organization not found or missing client_id"

        try:
            client_secret = None
            if org.encrypted_client_secret:
                client_secret = decrypt(org.encrypted_client_secret)
            tokens = await sf_auth.exchange_code_for_tokens(
                code=code,
                client_id=org.client_id,
                client_secret=client_secret,
                redirect_uri=redirect_uri,
                org_type=org.org_type,
                code_verifier=code_verifier,
            )

            org.encrypted_access_token = encrypt(tokens["access_token"])
            if tokens.get("refresh_token"):
                org.encrypted_refresh_token = encrypt(tokens["refresh_token"])
            org.instance_url = tokens["instance_url"]
            if tokens.get("id"):
                org.org_id = tokens["id"].split("/")[-1]
            org.last_connection_status = "success"
            org.last_connection_error = None
            await self.db.commit()
            return True, "Org connected successfully"
        except Exception as e:
            error_msg = str(e)
            org.last_connection_status = "error"
            org.last_connection_error = error_msg
            await self.db.commit()
            return False, error_msg

    # -------------------------------------------------------------------------
    # Connection Testing (Real Salesforce call)
    # -------------------------------------------------------------------------

    async def test_connection(self, org_id: uuid.UUID) -> ConnectionTestResponse:
        org = await self._get_org_row(org_id)

        if not org:
            return ConnectionTestResponse(
                success=False,
                status="error",
                message="Organization not found",
                tested_at=datetime.utcnow(),
            )

        try:
            if org.auth_method == SalesforceAuthMethod.JWT:
                access_token = await self._get_jwt_access_token(org)
            else:
                # For OAuth, we expect an access token to already exist
                if not org.encrypted_access_token:
                    raise Exception("No access token available. Please complete OAuth flow.")
                access_token = decrypt(org.encrypted_access_token)

            # Test the connection by calling Salesforce REST API
            async with httpx.AsyncClient(timeout=15.0) as client:
                headers = {"Authorization": f"Bearer {access_token}"}
                response = await client.get(f"{org.instance_url}/services/data/", headers=headers)

                if response.status_code == 200:
                    # Successful connection
                    org.last_connection_test_at = datetime.utcnow()
                    org.last_connection_status = "success"
                    org.last_connection_error = None
                    await self.db.commit()

                    return ConnectionTestResponse(
                        success=True,
                        status="success",
                        message="Successfully connected to Salesforce",
                        org_id=org.org_id,
                        username=org.username,
                        instance_url=org.instance_url,
                        tested_at=datetime.utcnow(),
                    )
                else:
                    error_msg = f"Salesforce returned status {response.status_code}"
                    org.last_connection_status = "error"
                    org.last_connection_error = error_msg
                    await self.db.commit()

                    return ConnectionTestResponse(
                        success=False,
                        status="error",
                        message=error_msg,
                        tested_at=datetime.utcnow(),
                    )

        except Exception as e:
            error_msg = str(e)
            org.last_connection_status = "error"
            org.last_connection_error = error_msg
            org.last_connection_test_at = datetime.utcnow()
            await self.db.commit()

            return ConnectionTestResponse(
                success=False,
                status="error",
                message=error_msg,
                tested_at=datetime.utcnow(),
            )

    # -------------------------------------------------------------------------
    # JWT Authentication Helper
    # -------------------------------------------------------------------------

    async def _get_jwt_access_token(self, org: SalesforceOrg) -> str:
        """Obtain access token using JWT Bearer flow."""
        if not org.encrypted_private_key or not org.client_id or not org.username:
            raise Exception("Missing JWT credentials for this organization.")

        # private_key = decrypt(org.encrypted_private_key)  # Reserved for JWT implementation

        # In a real implementation, we would generate a proper JWT and exchange it.
        # For the prototype, we simulate the flow and return a placeholder.
        # In the next iteration we will implement real JWT signing.

        # TODO: Implement real JWT generation + POST to /services/oauth2/token
        # For now, raise a clear message so the user knows the flow is wired.

        raise NotImplementedError(
            "Real JWT authentication will be completed in the next iteration of this slice. "
            "Web OAuth flow and connection testing structure is ready."
        )

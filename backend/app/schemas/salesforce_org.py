"""
Pydantic schemas for Salesforce Org Management.
"""

from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


class OrgTypeEnum(str):
    PRODUCTION = "production"
    SANDBOX = "sandbox"
    DEVELOPER = "developer"
    SCRATCH = "scratch"


class AuthMethodEnum(str):
    OAUTH_WEB = "oauth_web"
    JWT = "jwt"


# =============================================================================
# Create Org (supports two flows)
# =============================================================================

class SalesforceOrgCreateBase(BaseModel):
    name: str = Field(..., min_length=1, max_length=255)
    org_type: Literal["production", "sandbox", "developer", "scratch"]


class SalesforceOrgCreateOAuth(SalesforceOrgCreateBase):
    """Used when user will go through web OAuth flow (we return auth URL)."""
    auth_method: Literal["oauth_web"] = "oauth_web"
    client_id: str | None = None  # Consumer Key, stored now so /oauth/start doesn't need a separate call


class SalesforceOrgCreateJWT(SalesforceOrgCreateBase):
    """Used for JWT Server-to-Server flow (private key provided at creation)."""
    auth_method: Literal["jwt"] = "jwt"
    client_id: str
    username: str
    login_url: str = Field(default="https://login.salesforce.com")
    private_key: str = Field(..., description="RSA private key for the connected app (PEM format)")


SalesforceOrgCreate = SalesforceOrgCreateOAuth | SalesforceOrgCreateJWT


# =============================================================================
# Response Schemas
# =============================================================================

class SalesforceOrgResponse(BaseModel):
    id: UUID
    name: str
    org_type: str
    auth_method: str
    org_id: str | None = None
    username: str | None = None
    instance_url: str | None = None
    client_id: str | None = None
    is_active: bool
    last_connection_test_at: datetime | None = None
    last_connection_status: str | None = None
    last_connection_error: str | None = None
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)


class SalesforceOrgDetailResponse(SalesforceOrgResponse):
    """Includes whether we have valid credentials (without exposing them)."""
    has_access_token: bool = False
    has_refresh_token: bool = False
    has_private_key: bool = False


# =============================================================================
# Connection Test
# =============================================================================

class ConnectionTestResponse(BaseModel):
    success: bool
    status: str
    message: str | None = None
    org_id: str | None = None
    username: str | None = None
    instance_url: str | None = None
    tested_at: datetime

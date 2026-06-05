"""
Salesforce Authentication Service

Handles real authentication flows for Org Management:
- Web OAuth2 (Authorization Code + PKCE optional for prototype)
- JWT Bearer Token flow (Server-to-Server)
"""

import time

import httpx
from jose import jwt

from app.core.config import get_settings

settings = get_settings()


class SalesforceAuthService:
    """Handles authentication against Salesforce for connected orgs."""

    def __init__(self):
        self.timeout = 20.0

    # ------------------------------------------------------------------
    # Web OAuth2 Flow
    # ------------------------------------------------------------------

    def get_authorization_url(
        self,
        client_id: str,
        redirect_uri: str,
        org_type: str = "production",
        state: str | None = None,
        code_challenge: str | None = None,
        code_challenge_method: str = "S256",
    ) -> str:
        """
        Returns the Salesforce authorization URL the user should be redirected to.
        Includes PKCE code_challenge when provided.
        """
        from urllib.parse import urlencode

        login_url = (
            "https://test.salesforce.com"
            if org_type in ("sandbox", "scratch")
            else "https://login.salesforce.com"
        )

        params: dict = {
            "response_type": "code",
            "client_id": client_id,
            "redirect_uri": redirect_uri,
            "scope": "api refresh_token",
        }
        if state:
            params["state"] = state
        if code_challenge:
            params["code_challenge"] = code_challenge
            params["code_challenge_method"] = code_challenge_method

        return f"{login_url}/services/oauth2/authorize?{urlencode(params)}"

    async def exchange_code_for_tokens(
        self,
        code: str,
        client_id: str,
        client_secret: str | None,
        redirect_uri: str,
        org_type: str = "production",
        code_verifier: str | None = None,
    ) -> dict:
        """
        Exchanges authorization code for access + refresh tokens.
        Includes PKCE code_verifier when provided.
        """
        login_url = (
            "https://test.salesforce.com"
            if org_type in ("sandbox", "scratch")
            else "https://login.salesforce.com"
        )

        token_url = f"{login_url}/services/oauth2/token"

        data = {
            "grant_type": "authorization_code",
            "code": code,
            "client_id": client_id,
            "redirect_uri": redirect_uri,
        }

        if client_secret:
            data["client_secret"] = client_secret
        if code_verifier:
            data["code_verifier"] = code_verifier

        async with httpx.AsyncClient(timeout=self.timeout) as client:
            response = await client.post(token_url, data=data)
            if response.status_code != 200:
                try:
                    err_body = response.json()
                    detail = err_body.get("error_description") or err_body.get("error") or response.text
                except Exception:
                    detail = response.text
                raise Exception(f"Salesforce token exchange failed ({response.status_code}): {detail}")
            tokens = response.json()

        return {
            "access_token": tokens["access_token"],
            "refresh_token": tokens.get("refresh_token"),
            "instance_url": tokens["instance_url"],
            "id": tokens.get("id"),
        }

    async def refresh_access_token(
        self,
        refresh_token: str,
        client_id: str,
        client_secret: str | None = None,
        org_type: str = "production",
    ) -> dict:
        """Refresh an expired Salesforce access token using OAuth refresh token flow."""
        login_url = (
            "https://test.salesforce.com"
            if org_type in ("sandbox", "scratch")
            else "https://login.salesforce.com"
        )

        token_url = f"{login_url}/services/oauth2/token"
        data = {
            "grant_type": "refresh_token",
            "refresh_token": refresh_token,
            "client_id": client_id,
        }
        if client_secret:
            data["client_secret"] = client_secret

        async with httpx.AsyncClient(timeout=self.timeout) as client:
            response = await client.post(token_url, data=data)
            if response.status_code != 200:
                try:
                    err_body = response.json()
                    detail = err_body.get("error_description") or err_body.get("error") or response.text
                except Exception:
                    detail = response.text
                raise Exception(f"Salesforce token refresh failed ({response.status_code}): {detail}")
            tokens = response.json()

        return {
            "access_token": tokens["access_token"],
            "instance_url": tokens.get("instance_url"),
            "id": tokens.get("id"),
        }

    # ------------------------------------------------------------------
    # JWT Bearer Token Flow (Server-to-Server)
    # ------------------------------------------------------------------

    async def get_jwt_access_token(
        self,
        client_id: str,
        username: str,
        private_key: str,
        login_url: str = "https://login.salesforce.com",
    ) -> dict:
        """
        Performs the JWT Bearer OAuth flow and returns access token + instance_url.
        """
        # Create JWT
        now = int(time.time())
        payload = {
            "iss": client_id,
            "sub": username,
            "aud": login_url,
            "exp": now + 300,  # 5 minutes
        }

        # Sign the JWT
        assertion = jwt.encode(payload, private_key, algorithm="RS256")

        token_url = f"{login_url}/services/oauth2/token"

        data = {
            "grant_type": "urn:ietf:params:oauth:grant-type:jwt-bearer",
            "assertion": assertion,
        }

        async with httpx.AsyncClient(timeout=self.timeout) as client:
            response = await client.post(token_url, data=data)
            response.raise_for_status()
            tokens = response.json()

        return {
            "access_token": tokens["access_token"],
            "instance_url": tokens["instance_url"],
            "id": tokens.get("id"),
        }

    # ------------------------------------------------------------------
    # Connection Test
    # ------------------------------------------------------------------

    async def test_salesforce_connection(self, access_token: str, instance_url: str) -> dict:
        """Simple test by calling the Salesforce REST API."""
        url = f"{instance_url}/services/data/"

        headers = {
            "Authorization": f"Bearer {access_token}",
            "Content-Type": "application/json",
        }

        async with httpx.AsyncClient(timeout=self.timeout) as client:
            response = await client.get(url, headers=headers)

            if response.status_code == 200:
                data = response.json()
                return {
                    "success": True,
                    "version": data[0]["version"] if data else "unknown",
                }
            else:
                return {
                    "success": False,
                    "status_code": response.status_code,
                    "error": response.text,
                }

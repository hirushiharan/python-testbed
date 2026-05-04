"""Microsoft Entra OAuth authorization-code helpers."""

from __future__ import annotations

from dataclasses import dataclass
from functools import lru_cache
from typing import Any
from urllib.parse import urlencode

import requests

from src.auth.settings import Settings, get_settings


class EntraOAuthError(Exception):
    """Raised when authorization-code OAuth actions fail."""


class EntraOAuthConfigurationError(EntraOAuthError):
    """Raised when OAuth flow is requested without required app configuration."""


@dataclass(slots=True)
class EntraOAuthClient:
    """Exchange authorization code for an access token payload."""

    settings: Settings

    def build_authorization_url(self, state: str) -> str:
        params = {
            "client_id": self.settings.entra_client_id,
            "response_type": "code",
            "redirect_uri": self.settings.entra_redirect_uri,
            "scope": " ".join(self.settings.resolved_entra_auth_scopes),
            "state": state,
            "response_mode": "query",
        }
        return f"{self.settings.entra_authorize_endpoint}?{urlencode(params)}"

    def exchange_authorization_code(self, code: str) -> dict[str, Any]:
        if not self.settings.entra_client_secret:
            raise EntraOAuthConfigurationError(
                "ENTRA_CLIENT_SECRET is required for backend authorization-code exchange"
            )

        payload = {
            "client_id": self.settings.entra_client_id,
            "client_secret": self.settings.entra_client_secret,
            "grant_type": "authorization_code",
            "code": code,
            "redirect_uri": self.settings.entra_redirect_uri,
            "scope": " ".join(self.settings.resolved_entra_auth_scopes),
        }

        try:
            response = requests.post(
                self.settings.entra_token_endpoint,
                data=urlencode(payload),
                headers={"Content-Type": "application/x-www-form-urlencoded"},
                timeout=15.0,
            )
            response.raise_for_status()
            parsed = response.json()
        except requests.RequestException as exc:
            raise EntraOAuthError("Failed to exchange authorization code") from exc

        if not isinstance(parsed, dict):
            raise EntraOAuthError("Unexpected token response from Entra")

        access_token = parsed.get("access_token")
        if not isinstance(access_token, str) or not access_token:
            raise EntraOAuthError("Token response did not include access_token")

        expires_in = parsed.get("expires_in")
        if expires_in is not None:
            try:
                parsed["expires_in"] = int(expires_in)
            except (TypeError, ValueError):
                parsed.pop("expires_in", None)

        return parsed


@lru_cache(maxsize=1)
def get_entra_oauth_client() -> EntraOAuthClient:
    """Return a cached OAuth client."""

    return EntraOAuthClient(settings=get_settings())

"""Microsoft Graph client for Outlook mailbox operations."""

from __future__ import annotations

import datetime as dt
import urllib.parse
from typing import Any

import requests

from src.integrations.email.settings import OutlookSettings, get_outlook_settings

GRAPH_SCOPE = "https://graph.microsoft.com/.default"


class OutlookClientError(RuntimeError):
    """Base error for Outlook Graph client failures."""


class OutlookConfigurationError(OutlookClientError):
    """Raised when required configuration is missing or invalid."""


class OutlookGraphClient:
    """Simple Microsoft Graph client for Outlook mailbox operations."""

    def __init__(
        self,
        settings: OutlookSettings | None = None,
        session: requests.Session | None = None,
    ) -> None:
        self.settings = settings or get_outlook_settings()
        self.session = session or requests.Session()
        self._access_token: str | None = None
        self._access_token_expires_at: dt.datetime | None = None

    def _token_endpoint(self) -> str:
        return (
            f"{self.settings.graph_authority_host.rstrip('/')}"
            f"/{self.settings.outlook_tenant_id}/oauth2/v2.0/token"
        )

    def _api_url(self, path: str) -> str:
        return f"{self.settings.graph_base_url.rstrip('/')}/{path.lstrip('/')}"

    def _request_json(
        self,
        method: str,
        url: str,
        *,
        headers: dict[str, str] | None = None,
        data: Any = None,
        json_body: dict[str, Any] | None = None,
        timeout: int | None = None,
    ) -> dict[str, Any]:
        try:
            response = self.session.request(
                method=method,
                url=url,
                headers=headers,
                data=data,
                json=json_body,
                timeout=timeout or self.settings.request_timeout_seconds,
            )
        except requests.RequestException as exc:
            raise OutlookClientError(f"Outlook Graph request failed: {exc}") from exc

        if response.status_code >= 400:
            raise OutlookClientError(
                f"Graph request failed ({response.status_code}): "
                f"{response.text.strip() or response.reason}"
            )

        if not response.content:
            return {}

        try:
            payload = response.json()
        except ValueError as exc:
            raise OutlookClientError("Graph returned a non-JSON response") from exc

        return payload if isinstance(payload, dict) else {}

    def _get_access_token(self) -> str:
        now = dt.datetime.utcnow()
        if (
            self._access_token
            and self._access_token_expires_at
            and now < self._access_token_expires_at
        ):
            return self._access_token

        form_data = {
            "client_id": self.settings.outlook_client_id,
            "client_secret": self.settings.outlook_client_secret,
            "scope": GRAPH_SCOPE,
            "grant_type": "client_credentials",
        }

        token_payload = self._request_json(
            method="POST",
            url=self._token_endpoint(),
            headers={"Content-Type": "application/x-www-form-urlencoded"},
            data=form_data,
        )

        access_token = str(token_payload.get("access_token", "")).strip()
        if not access_token:
            raise OutlookClientError("Failed to obtain a Microsoft Graph access token")

        expires_in = int(token_payload.get("expires_in", 3600) or 3600)
        self._access_token = access_token
        self._access_token_expires_at = now + dt.timedelta(seconds=max(expires_in - 60, 60))
        return access_token

    def _authorized_headers(self) -> dict[str, str]:
        return {
            "Authorization": f"Bearer {self._get_access_token()}",
            "Accept": "application/json",
        }

    def test_connection(self) -> dict[str, Any]:
        """Test Graph API connectivity using a Mail.Read-scoped probe.

        Steps:
        1. Acquire an access token via client credentials (proves Graph API login).
        2. If a mailbox is configured, call GET /users/{mailbox}/mailFolders?$top=1
           — this requires only Mail.Read (not User.Read.All) and confirms both
           Graph API reachability and mailbox-level access in one round-trip.
        3. If no mailbox is configured, call GET /organization as a fallback probe.

        Returns a status dictionary that the service layer maps to a response schema.
        """
        result: dict[str, Any] = {
            "tenant_id": self.settings.outlook_tenant_id,
            "client_id": self.settings.outlook_client_id,
            "token_obtained": False,
            "graph_api_accessible": False,
            "mailbox_verified": False,
            "mailbox": self.settings.outlook_mailbox,
            "error": None,
        }

        try:
            self._get_access_token()
            result["token_obtained"] = True
        except OutlookClientError as exc:
            result["error"] = f"Token acquisition failed: {exc}"
            return result

        mailbox = (self.settings.outlook_mailbox or "").strip()
        if mailbox:
            try:
                self._request_json(
                    method="GET",
                    url=self._api_url(
                        f"users/{urllib.parse.quote(mailbox)}/mailFolders?$top=1"
                    ),
                    headers=self._authorized_headers(),
                )
                result["graph_api_accessible"] = True
                result["mailbox_verified"] = True
            except OutlookClientError as exc:
                result["error"] = f"Mailbox verification failed: {exc}"
        else:
            try:
                self._request_json(
                    method="GET",
                    url=self._api_url("organization"),
                    headers=self._authorized_headers(),
                )
                result["graph_api_accessible"] = True
            except OutlookClientError as exc:
                result["error"] = f"Graph API probe failed: {exc}"

        return result

    def list_mail_folders(self, mailbox: str) -> list[dict[str, Any]]:
        """List all mail folders for a mailbox, following pagination."""
        encoded = urllib.parse.quote(mailbox)
        url: str = self._api_url(f"users/{encoded}/mailFolders?$top=200")
        folders: list[dict[str, Any]] = []

        while url:
            payload = self._request_json(
                method="GET", url=url, headers=self._authorized_headers()
            )
            for item in payload.get("value", []):
                if isinstance(item, dict):
                    folders.append(item)
            url = str(payload.get("@odata.nextLink", "")).strip()

        return folders

    def fetch_messages(
        self,
        mailbox: str,
        folder_id: str,
        max_messages: int = 25,
    ) -> list[dict[str, Any]]:
        """Fetch messages from a mail folder, respecting max_messages limit."""
        if max_messages <= 0:
            return []

        encoded_mailbox = urllib.parse.quote(mailbox)
        encoded_folder = urllib.parse.quote(folder_id)
        select_fields = (
            "id,subject,from,toRecipients,receivedDateTime,sentDateTime,"
            "isRead,hasAttachments,bodyPreview,webLink,parentFolderId"
        )
        page_size = min(max_messages, 100)
        url: str = self._api_url(
            f"users/{encoded_mailbox}/mailFolders/{encoded_folder}/messages"
            f"?$top={page_size}&$orderby=receivedDateTime desc&$select={select_fields}"
        )

        messages: list[dict[str, Any]] = []
        while url and len(messages) < max_messages:
            payload = self._request_json(
                method="GET", url=url, headers=self._authorized_headers()
            )
            for item in payload.get("value", []):
                if isinstance(item, dict):
                    messages.append(item)
                    if len(messages) >= max_messages:
                        break
            url = str(payload.get("@odata.nextLink", "")).strip()

        return messages

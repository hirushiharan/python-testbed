"""Microsoft Graph client helpers for SharePoint document libraries."""

from __future__ import annotations

import datetime as dt
import os
import urllib.parse
from typing import Any

import requests

from src.integrations.sharepoint.settings import SharePointSettings, get_sharepoint_settings

GRAPH_SCOPE = "https://graph.microsoft.com/.default"
UPLOAD_SESSION_CHUNK_SIZE = 5 * 1024 * 1024


class SharePointClientError(RuntimeError):
    """Base error for Graph client failures."""


class SharePointConfigurationError(SharePointClientError):
    """Raised when required configuration is missing or invalid."""


class SharePointGraphClient:
    """Simple Microsoft Graph client for SharePoint document operations."""

    def __init__(
        self,
        settings: SharePointSettings | None = None,
        session: requests.Session | None = None,
    ) -> None:
        self.settings = settings or get_sharepoint_settings()
        self.session = session or requests.Session()
        self._access_token: str | None = None
        self._access_token_expires_at: dt.datetime | None = None
        self._drive_id: str | None = self.settings.sharepoint_drive_id

    def _token_endpoint(self) -> str:
        return (
            f"{self.settings.graph_authority_host.rstrip('/')}"
            f"/{self.settings.sharepoint_tenant_id}/oauth2/v2.0/token"
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
            raise SharePointClientError(f"SharePoint request failed: {exc}") from exc

        if response.status_code >= 400:
            raise SharePointClientError(
                f"Graph request failed ({response.status_code}): {response.text.strip() or response.reason}"
            )

        if not response.content:
            return {}

        try:
            payload = response.json()
        except ValueError as exc:
            raise SharePointClientError("Graph returned a non-JSON response") from exc

        return payload if isinstance(payload, dict) else {}

    def _get_access_token(self) -> str:
        now = dt.datetime.utcnow()
        if self._access_token and self._access_token_expires_at and now < self._access_token_expires_at:
            return self._access_token

        form_data = {
            "client_id": self.settings.sharepoint_client_id,
            "client_secret": self.settings.sharepoint_client_secret,
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
            raise SharePointClientError("Failed to obtain a Microsoft Graph access token")

        expires_in = int(token_payload.get("expires_in", 3600) or 3600)
        self._access_token = access_token
        self._access_token_expires_at = now + dt.timedelta(seconds=max(expires_in - 60, 60))
        return access_token

    def _authorized_headers(self) -> dict[str, str]:
        return {
            "Authorization": f"Bearer {self._get_access_token()}",
            "Accept": "application/json",
        }

    def get_drive_id(self) -> str:
        """Return the drive ID, resolving it from the configured site when needed."""

        if self._drive_id:
            return self._drive_id

        site_id = self.settings.sharepoint_site_id.strip()
        if not site_id:
            raise SharePointConfigurationError("sharepoint_site_id is required")

        payload = self._request_json(
            method="GET",
            url=self._api_url(f"sites/{urllib.parse.quote(site_id)}/drive"),
            headers=self._authorized_headers(),
        )
        drive_id = str(payload.get("id", "")).strip()
        if not drive_id:
            raise SharePointClientError("Unable to resolve the default SharePoint drive ID")

        self._drive_id = drive_id
        return drive_id

    def create_folder(
        self,
        *,
        name: str,
        parent_folder_id: str | None = None,
        conflict_behavior: str | None = None,
    ) -> dict[str, Any]:
        if not name.strip():
            raise ValueError("Folder name cannot be empty")

        drive_id = self.get_drive_id()
        parent_id = (parent_folder_id or self.settings.sharepoint_default_parent_folder_id or "").strip()
        folder_name = name.strip()
        payload = {
            "name": folder_name,
            "folder": {},
            "@microsoft.graph.conflictBehavior": conflict_behavior
            or self.settings.sharepoint_conflict_behavior,
        }

        if parent_id:
            endpoint = self._api_url(f"drives/{urllib.parse.quote(drive_id)}/items/{urllib.parse.quote(parent_id)}/children")
        else:
            endpoint = self._api_url(f"drives/{urllib.parse.quote(drive_id)}/root/children")

        return self._request_json(
            method="POST",
            url=endpoint,
            headers={**self._authorized_headers(), "Content-Type": "application/json"},
            json_body=payload,
        )

    def list_files(self, folder_id: str) -> list[dict[str, Any]]:
        drive_id = self.get_drive_id()
        folder_ref = folder_id.strip()
        if not folder_ref:
            raise ValueError("folder_id cannot be empty")

        if folder_ref.casefold() == "root":
            url = self._api_url(
                f"drives/{urllib.parse.quote(drive_id)}/root/children"
            )
        else:
            url = self._api_url(
                f"drives/{urllib.parse.quote(drive_id)}/items/{urllib.parse.quote(folder_ref)}/children"
            )

        url = f"{url}?$top=200&$select=id,name,size,webUrl,lastModifiedDateTime,parentReference,file,folder"
        files: list[dict[str, Any]] = []

        while url:
            payload = self._request_json(method="GET", url=url, headers=self._authorized_headers())
            for item in payload.get("value", []):
                if not isinstance(item, dict):
                    continue
                if item.get("file") is None:
                    continue
                files.append(item)

            next_link = str(payload.get("@odata.nextLink", "")).strip()
            url = next_link or ""

        return files

    def upload_file(self, folder_id: str, file_name: str, file_stream: Any) -> dict[str, Any]:
        drive_id = self.get_drive_id()
        folder_ref = folder_id.strip()
        upload_name = file_name.strip()
        if not folder_ref:
            raise ValueError("folder_id cannot be empty")
        if not upload_name:
            raise ValueError("file_name cannot be empty")

        if folder_ref.casefold() == "root":
            session_url = self._api_url(
                f"drives/{urllib.parse.quote(drive_id)}/root:/{urllib.parse.quote(upload_name)}:/createUploadSession"
            )
        else:
            session_url = self._api_url(
                f"drives/{urllib.parse.quote(drive_id)}/items/{urllib.parse.quote(folder_ref)}:/{urllib.parse.quote(upload_name)}:/createUploadSession"
            )

        session_payload = self._request_json(
            method="POST",
            url=session_url,
            headers={**self._authorized_headers(), "Content-Type": "application/json"},
            json_body={
                "item": {
                    "@microsoft.graph.conflictBehavior": self.settings.sharepoint_conflict_behavior,
                    "name": upload_name,
                }
            },
        )
        upload_url = str(session_payload.get("uploadUrl", "")).strip()
        if not upload_url:
            raise SharePointClientError("SharePoint did not return an uploadUrl")

        try:
            file_stream.seek(0, os.SEEK_END)
            total_size = int(file_stream.tell())
            file_stream.seek(0)
        except Exception as exc:
            raise SharePointClientError("Unable to determine upload size") from exc

        if total_size <= 0:
            raise ValueError("Cannot upload an empty file")

        chunk_size = max(1, int(self.settings.sharepoint_upload_chunk_size or UPLOAD_SESSION_CHUNK_SIZE))
        start = 0
        last_response: requests.Response | None = None

        while start < total_size:
            chunk = file_stream.read(chunk_size)
            if not chunk:
                break

            end = start + len(chunk) - 1
            headers = {
                "Content-Length": str(len(chunk)),
                "Content-Range": f"bytes {start}-{end}/{total_size}",
            }
            try:
                last_response = self.session.put(
                    upload_url,
                    headers=headers,
                    data=chunk,
                    timeout=self.settings.request_timeout_seconds,
                )
            except requests.RequestException as exc:
                raise SharePointClientError(f"SharePoint upload failed: {exc}") from exc

            if last_response.status_code in {200, 201}:
                if last_response.content:
                    return last_response.json()
                return {}

            if last_response.status_code != 202:
                raise SharePointClientError(
                    f"Upload session failed ({last_response.status_code}): {last_response.text.strip() or last_response.reason}"
                )

            start = end + 1

        if last_response is not None and last_response.status_code in {200, 201}:
            if last_response.content:
                return last_response.json()
            return {}

        raise SharePointClientError("SharePoint upload session did not complete successfully")

from __future__ import annotations

from typing import Any

import pytest

from src.integrations.sharepoint.client import SharePointGraphClient
from src.integrations.sharepoint.settings import SharePointSettings


class _FakeResponse:
    def __init__(self, payload: dict[str, Any], status_code: int = 200) -> None:
        self._payload = payload
        self.status_code = status_code
        self.content = b"{}"
        self.text = ""
        self.reason = ""

    def json(self) -> dict[str, Any]:
        return self._payload


class _FakeSession:
    def __init__(self, drives: list[dict[str, Any]]) -> None:
        self.drives = drives
        self.calls: list[tuple[str, str, Any]] = []

    def request(self, method, url, headers=None, data=None, json=None, timeout=None):
        self.calls.append((method, url, json))
        if url.endswith("/oauth2/v2.0/token"):
            return _FakeResponse({"access_token": "tok", "expires_in": 3600})
        if method == "GET" and url.endswith("/drives"):
            return _FakeResponse({"value": self.drives})
        if method == "POST" and url.endswith("/lists"):
            return _FakeResponse({"id": "list-1", "displayName": json["displayName"]})
        if method == "GET" and url.endswith("/lists/list-1/drive"):
            return _FakeResponse({"id": "drive-new", "name": "CPN", "webUrl": "https://x/CPN"})
        raise AssertionError(f"unexpected call {method} {url}")


def _client(session: _FakeSession) -> SharePointGraphClient:
    settings = SharePointSettings(
        sharepoint_tenant_id="t",
        sharepoint_client_id="c",
        sharepoint_client_secret="s",
        sharepoint_site_id="site-1",
    )
    return SharePointGraphClient(settings=settings, session=session)  # type: ignore[arg-type]


def test_create_document_library_creates_when_missing() -> None:
    session = _FakeSession(drives=[{"id": "d1", "name": "Documents"}])

    drive = _client(session).create_document_library("CPN")

    assert drive["id"] == "drive-new"
    post = next(c for c in session.calls if c[0] == "POST" and c[1].endswith("/lists"))
    assert post[2] == {"displayName": "CPN", "list": {"template": "documentLibrary"}}


def test_create_document_library_is_idempotent() -> None:
    session = _FakeSession(drives=[{"id": "d9", "name": "cpn", "webUrl": "https://x/cpn"}])

    drive = _client(session).create_document_library("CPN")

    assert drive["id"] == "d9"
    assert not any(c[0] == "POST" and c[1].endswith("/lists") for c in session.calls)


def test_create_document_library_rejects_blank_name() -> None:
    with pytest.raises(ValueError):
        _client(_FakeSession(drives=[])).create_document_library("  ")

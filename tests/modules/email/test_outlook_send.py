from __future__ import annotations

from types import SimpleNamespace
from typing import Any

from fastapi import FastAPI
from fastapi.testclient import TestClient

from src.integrations.email.api import get_outlook_service, router
from src.integrations.email.client import OutlookGraphClient
from src.integrations.email.service import OutlookService


class _ClientStub:
    """Stands in for OutlookGraphClient and records send_mail calls."""

    def __init__(self, mailbox: str | None = "sender@contoso.com") -> None:
        self.settings = SimpleNamespace(outlook_mailbox=mailbox)
        self.calls: list[tuple[str, dict[str, Any]]] = []

    def send_mail(self, mailbox: str, **kwargs: Any) -> None:
        self.calls.append((mailbox, kwargs))


def _build_app(client: _ClientStub) -> FastAPI:
    app = FastAPI()
    app.include_router(router, prefix="/api/v1")
    app.dependency_overrides[get_outlook_service] = lambda: OutlookService(client=client)
    return app


def test_send_test_email_uses_configured_mailbox() -> None:
    stub = _ClientStub()
    http = TestClient(_build_app(stub))

    response = http.post("/api/v1/outlook/send-test", json={"to": ["you@contoso.com"]})

    assert response.status_code == 200
    body = response.json()
    assert body["accepted"] is True
    assert body["sender"] == "sender@contoso.com"
    assert stub.calls[0][0] == "sender@contoso.com"
    assert stub.calls[0][1]["to"] == ["you@contoso.com"]


def test_send_test_email_requires_recipient() -> None:
    http = TestClient(_build_app(_ClientStub()))

    assert http.post("/api/v1/outlook/send-test", json={"to": []}).status_code == 422


def test_send_test_email_without_mailbox_returns_400() -> None:
    http = TestClient(_build_app(_ClientStub(mailbox=None)))

    response = http.post("/api/v1/outlook/send-test", json={"to": ["you@contoso.com"]})

    assert response.status_code == 400
    assert "OUTLOOK_MAILBOX" in response.json()["detail"]


def test_client_posts_graph_sendmail_payload() -> None:
    captured: dict[str, Any] = {}

    client = OutlookGraphClient(
        settings=SimpleNamespace(
            graph_base_url="https://graph.microsoft.com/v1.0",
            request_timeout_seconds=5,
        ),
        session=SimpleNamespace(),
    )
    client._authorized_headers = lambda: {"Authorization": "Bearer x"}  # type: ignore[method-assign]

    def fake_request_json(method: str, url: str, **kwargs: Any) -> dict[str, Any]:
        captured.update(method=method, url=url, **kwargs)
        return {}

    client._request_json = fake_request_json  # type: ignore[method-assign]

    client.send_mail(
        "sender@contoso.com",
        to=["a@contoso.com"],
        cc=["b@contoso.com"],
        subject="Hi",
        body="Hello",
    )

    assert captured["method"] == "POST"
    assert captured["url"] == (
        "https://graph.microsoft.com/v1.0/users/sender%40contoso.com/sendMail"
    )
    payload = captured["json_body"]
    assert payload["saveToSentItems"] is True
    assert payload["message"]["toRecipients"] == [{"emailAddress": {"address": "a@contoso.com"}}]
    assert payload["message"]["ccRecipients"] == [{"emailAddress": {"address": "b@contoso.com"}}]
    assert payload["message"]["body"] == {"contentType": "Text", "content": "Hello"}

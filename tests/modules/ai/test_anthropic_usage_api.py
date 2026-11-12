"""Tests for Anthropic usage Swagger API routes."""

from fastapi import FastAPI
from fastapi.testclient import TestClient

from src.ai.providers import anthropic_usage_api


def _build_client() -> TestClient:
    app = FastAPI()
    app.include_router(anthropic_usage_api.router, prefix="/api/v1")
    return TestClient(app)


def test_usage_endpoint_returns_aggregated_report(monkeypatch) -> None:
    monkeypatch.setenv("ANTHROPIC_ADMIN_API_KEY", "admin-key")
    responses = {
        "usage": [{"usage": {"input_tokens": 10, "output_tokens": 4, "requests": 1}}],
        "cost": [{"cost": {"amount": "125.000000", "list_amount": "200.000000"}}],
    }

    def fake_fetch_report(api_key, report, starting_at, ending_at, group_by):
        assert api_key == "admin-key"
        return responses[report]

    monkeypatch.setattr(anthropic_usage_api, "fetch_report", fake_fetch_report)

    response = _build_client().get(
        "/api/v1/anthropic/usage",
        params={
            "starting_at": "2026-11-01T00:00:00Z",
            "ending_at": "2026-11-12T00:00:00Z",
            "group_by": "model",
        },
    )

    assert response.status_code == 200
    assert response.json()["usage"]["input_tokens"] == 10
    assert response.json()["cost_usd"]["amount"] == "1.250000"
    assert response.json()["balance_credits"] is None


def test_usage_endpoint_requires_admin_key(monkeypatch) -> None:
    monkeypatch.delenv("ANTHROPIC_ADMIN_API_KEY", raising=False)
    monkeypatch.setattr(anthropic_usage_api, "load_dotenv", lambda: False)

    response = _build_client().get("/api/v1/anthropic/usage")

    assert response.status_code == 500
    assert "ANTHROPIC_ADMIN_API_KEY" in response.json()["detail"]


def test_usage_endpoint_loads_admin_key_from_dotenv(monkeypatch) -> None:
    monkeypatch.delenv("ANTHROPIC_ADMIN_API_KEY", raising=False)
    monkeypatch.setattr(anthropic_usage_api, "load_dotenv", lambda: True)
    monkeypatch.setattr(anthropic_usage_api.os, "getenv", lambda name, default="": (
        "admin-key" if name == "ANTHROPIC_ADMIN_API_KEY" else default
    ))
    monkeypatch.setattr(
        anthropic_usage_api,
        "fetch_report",
        lambda api_key, report, starting_at, ending_at, group_by: [],
    )

    response = _build_client().get("/api/v1/anthropic/usage")

    assert response.status_code == 200

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime

from fastapi import FastAPI
from fastapi.testclient import TestClient

from src.auth.api.dependencies import get_auth_service
from src.auth.api.router import router as auth_router
from src.auth.api.schemas import AuthenticatedUser, ValidateTokenResponse
from src.auth.application.service import AuthAuthorizationError, AuthRepositoryError
from src.auth.exception_handlers import register_exception_handlers


@dataclass(slots=True)
class _AuthServiceStub:
    mode: str = "ok"

    def get_all_users(self):
        if self.mode == "repo_error":
            raise AuthRepositoryError("db read failed")

        now = datetime.now(UTC)
        return [
            {
                "user_id": 1,
                "email": "ops@example.com",
                "role": "collector",
                "is_active": True,
                "created_by": "system",
                "created_at": now,
                "updated_by": "system",
                "updated_at": now,
            }
        ]

    def exchange_authorization_code(self, code: str):
        raise NotImplementedError

    def validate_token(self, token: str) -> ValidateTokenResponse:
        if self.mode == "auth_error":
            raise AuthAuthorizationError("denied")
        return ValidateTokenResponse(
            access_token=token,
            token_type="bearer",
            expires_in=3600,
            user=AuthenticatedUser(
                user_id=1,
                email="ops@example.com",
                role="collector",
                is_active=True,
                name="Ops User",
            ),
        )


def _build_client(service: _AuthServiceStub) -> TestClient:
    app = FastAPI()
    register_exception_handlers(app)
    app.include_router(auth_router, prefix="/api/v1")
    app.dependency_overrides[get_auth_service] = lambda: service
    return TestClient(app)


def test_validate_token_uses_body_fallback_when_authorization_missing() -> None:
    client = _build_client(_AuthServiceStub())

    response = client.post("/api/v1/auth/validate-token", json={"token": "body-token"})

    assert response.status_code == 200
    payload = response.json()
    assert payload["access_token"] == "body-token"
    assert payload["user"]["email"] == "ops@example.com"


def test_get_users_maps_repository_errors_via_global_handler() -> None:
    client = _build_client(_AuthServiceStub(mode="repo_error"))

    response = client.get("/api/v1/auth/users")

    assert response.status_code == 500
    assert response.json() == {"detail": "db read failed"}


def test_validate_token_maps_authorization_errors_via_global_handler() -> None:
    client = _build_client(_AuthServiceStub(mode="auth_error"))

    response = client.post("/api/v1/auth/validate-token", json={"token": "body-token"})

    assert response.status_code == 403
    assert response.json() == {"detail": "denied"}
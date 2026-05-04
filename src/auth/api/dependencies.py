"""Dependency wiring for auth module."""

from __future__ import annotations

from typing import Any

from fastapi import Depends, HTTPException, Request, Security, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from src.auth.application.service import AuthService
from src.auth.infrastructure.repository import get_auth_repository, get_session_factory
from src.auth.integrations.entra_id_adapter import (
    EntraTokenValidator,
    InvalidAccessTokenError,
    get_entra_token_validator,
)
from src.auth.integrations.oauth_adapter import get_entra_oauth_client

_bearer_scheme = HTTPBearer(auto_error=False)


def get_auth_service() -> AuthService:
    """Build the auth service for dependency injection."""

    return AuthService(
        oauth_client=get_entra_oauth_client(),
        token_validator=get_entra_token_validator(),
        repository=get_auth_repository(),
    )


def reset_auth_dependency_caches() -> None:
    """Clear cached dependency helpers."""

    get_auth_repository.cache_clear()
    get_session_factory.cache_clear()
    get_entra_oauth_client.cache_clear()
    get_entra_token_validator.cache_clear()


def get_bearer_token_from_authorization(
    request: Request,
    credentials: HTTPAuthorizationCredentials | None = Security(_bearer_scheme),
) -> str:
    """Extract a bearer token from the Authorization header."""

    if credentials is not None:
        if credentials.scheme.lower() == "bearer" and credentials.credentials:
            return credentials.credentials.strip()

    raw_authorization = (request.headers.get("authorization") or "").strip()
    token = ""
    if raw_authorization.lower().startswith("bearer "):
        token = raw_authorization[7:].strip()
    elif raw_authorization.lower().startswith("bearer"):
        token = raw_authorization[6:].strip()

    if not token:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Missing or invalid Authorization bearer token",
        )

    return token


def get_optional_bearer_token_from_authorization(
    credentials: HTTPAuthorizationCredentials | None = Security(_bearer_scheme),
) -> str | None:
    """Extract a bearer token when present."""

    if credentials is None:
        return None
    if credentials.scheme.lower() != "bearer" or not credentials.credentials:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Missing or invalid Authorization bearer token",
        )
    return credentials.credentials.strip()


def get_current_access_token_claims(
    token: str = Depends(get_bearer_token_from_authorization),
    token_validator: EntraTokenValidator = Depends(get_entra_token_validator),
) -> dict[str, Any]:
    """Validate a bearer token and return its claims."""

    try:
        return token_validator.validate_token(token)
    except InvalidAccessTokenError as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=str(exc),
        ) from exc

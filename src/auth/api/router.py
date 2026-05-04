"""Authentication endpoints based on Entra ID SSO tokens."""

from __future__ import annotations

from fastapi import APIRouter, Body, Depends, HTTPException, Query, status

from src.auth.api.dependencies import (
    get_auth_service,
    get_optional_bearer_token_from_authorization,
)
from src.auth.api.schemas import (
    AuthorizationCodeExchangeRequest,
    EntraAccessTokenResponse,
    LoginUrlResponse,
    UserDetailsResponse,
    ValidateTokenRequest,
    ValidateTokenResponse,
)
from src.auth.application.service import AuthService

router = APIRouter(prefix="/auth", tags=["auth"])


@router.get("/callback", response_model=EntraAccessTokenResponse)
def auth_callback(
    code: str = Query(..., description="Authorization code from Entra ID"),
    state: str | None = Query(default=None, description="CSRF state token echoed by Entra ID"),
    auth_service: AuthService = Depends(get_auth_service),
) -> EntraAccessTokenResponse:
    """Handle the OAuth 2.0 authorization code callback."""

    return auth_service.exchange_authorization_code(code)


@router.get("/login-url", response_model=LoginUrlResponse)
def get_login_url(
    auth_service: AuthService = Depends(get_auth_service),
) -> LoginUrlResponse:
    """Return an authorization URL and CSRF state token."""

    return auth_service.get_login_url()


@router.get("/users", response_model=list[UserDetailsResponse])
def get_all_users(
    auth_service: AuthService = Depends(get_auth_service),
) -> list[UserDetailsResponse]:
    """Return all users from the lookup table."""

    return auth_service.get_all_users()


@router.post("/exchange-code", response_model=EntraAccessTokenResponse)
def exchange_code(
    payload: AuthorizationCodeExchangeRequest,
    auth_service: AuthService = Depends(get_auth_service),
) -> EntraAccessTokenResponse:
    """Exchange an authorization code and return a validated session payload."""

    return auth_service.exchange_authorization_code(payload.code)


@router.post("/validate-token", response_model=ValidateTokenResponse)
def validate_token(
    token: str | None = Depends(get_optional_bearer_token_from_authorization),
    payload: ValidateTokenRequest | None = Body(default=None),
    auth_service: AuthService = Depends(get_auth_service),
) -> ValidateTokenResponse:
    """Validate a bearer token and return the resolved application user."""

    resolved_token = token or (payload.token.strip() if payload and payload.token else None)
    if not resolved_token:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Missing Authorization bearer token",
        )
    return auth_service.validate_token(resolved_token)

"""Service layer for auth workflows."""

from __future__ import annotations

import secrets
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any

from src.auth.api.schemas import (
    AuthenticatedUser,
    EntraAccessTokenResponse,
    LoginUrlResponse,
    UserDetailsResponse,
    ValidateTokenResponse,
)
from src.auth.application.errors import (
    AuthRepositoryError,
    AuthTokenExchangeError,
    AuthTokenValidationError,
)
from src.auth.domain.errors import AuthAuthorizationError
from src.auth.domain.roles import normalize_role
from src.auth.infrastructure.repository import AuthRepository, AuthRepositoryError as RepositoryAuthError
from src.auth.integrations.entra_id_adapter import InvalidAccessTokenError
from src.auth.integrations.oauth_adapter import EntraOAuthClient, EntraOAuthError


@dataclass(slots=True)
class AuthService:
    """Encapsulate token exchange, validation, and authorization."""

    oauth_client: EntraOAuthClient
    token_validator: Any
    repository: AuthRepository

    def get_login_url(self) -> LoginUrlResponse:
        state = secrets.token_urlsafe(32)
        return LoginUrlResponse(url=self.oauth_client.build_authorization_url(state), state=state)

    def get_all_users(self) -> list[UserDetailsResponse]:
        try:
            users = self.repository.get_all_users()
        except RepositoryAuthError as exc:
            raise AuthRepositoryError(str(exc)) from exc

        return [
            UserDetailsResponse(
                user_id=user.user_id,
                email=user.email,
                role=user.role,
                is_active=user.is_active,
                created_by=user.created_by,
                created_at=user.created_at,
                updated_by=user.updated_by,
                updated_at=user.updated_at,
            )
            for user in users
        ]

    def exchange_authorization_code(self, code: str) -> EntraAccessTokenResponse:
        token_payload = self._exchange_token_payload(code)
        access_token = self._extract_access_token(token_payload)
        claims = self.get_validated_claims(access_token)
        user = self.authorize_claims(claims)

        return EntraAccessTokenResponse(
            access_token=access_token,
            token_type=self._as_str_or_none(token_payload.get("token_type")) or "bearer",
            expires_in=self._as_int_or_none(token_payload.get("expires_in")) or 3600,
            user=user,
        )

    def validate_token(self, token: str) -> ValidateTokenResponse:
        claims = self.get_validated_claims(token)
        user = self.authorize_claims(claims)
        return ValidateTokenResponse(
            access_token=token,
            token_type="bearer",
            expires_in=self._expires_in_from_claims(claims),
            user=user,
        )

    def get_validated_claims(self, token: str) -> dict[str, Any]:
        try:
            return self.token_validator.validate_token(token)
        except InvalidAccessTokenError as exc:
            raise AuthTokenValidationError(str(exc)) from exc

    def authorize_claims(self, claims: dict[str, Any]) -> AuthenticatedUser:
        _, _, email = self._extract_identity_claims(claims)

        try:
            db_user = self.repository.get_active_user_role_by_email(email)
        except RepositoryAuthError as exc:
            raise AuthRepositoryError(str(exc)) from exc

        if db_user is None:
            raise AuthAuthorizationError("Access denied: user not found or inactive")

        normalized_role = normalize_role(db_user.role_name)
        if not normalized_role:
            raise AuthAuthorizationError("Access denied: invalid role")

        return AuthenticatedUser(
            user_id=db_user.user_id,
            email=email,
            role=normalized_role,
            is_active=True,
            name=self._as_str_or_none(claims.get("name")) or self._as_str_or_none(claims.get("given_name")),
        )

    def _exchange_token_payload(self, code: str) -> dict[str, Any]:
        try:
            return self.oauth_client.exchange_authorization_code(code)
        except EntraOAuthError as exc:
            raise AuthTokenExchangeError(str(exc)) from exc

    @staticmethod
    def _extract_access_token(token_payload: dict[str, Any]) -> str:
        access_token = token_payload.get("access_token")
        if not isinstance(access_token, str) or not access_token:
            raise AuthTokenExchangeError("Token exchange did not return access_token")
        return access_token

    @staticmethod
    def _extract_identity_claims(claims: dict[str, Any]) -> tuple[str, str, str]:
        oid = claims.get("oid") or claims.get("sub")
        email = (
            claims.get("preferred_username")
            or claims.get("email")
            or claims.get("upn")
            or claims.get("unique_name")
        )

        if not isinstance(oid, str) or not oid:
            raise AuthTokenValidationError("Token is missing required subject claims")

        if not isinstance(email, str) or not email:
            raise AuthTokenValidationError("Token is missing required email claim")

        return str(claims.get("sub") or oid), oid, email.strip().lower()

    @staticmethod
    def _as_str_or_none(value: Any) -> str | None:
        if isinstance(value, str) and value:
            return value
        return None

    @staticmethod
    def _as_int_or_none(value: Any) -> int | None:
        try:
            return int(value)
        except (TypeError, ValueError):
            return None

    @staticmethod
    def _expires_in_from_claims(claims: dict[str, Any]) -> int:
        exp_ts = AuthService._as_int_or_none(claims.get("exp"))
        if exp_ts is None:
            return 3600

        now_ts = int(datetime.now(UTC).timestamp())
        return max(exp_ts - now_ts, 0)

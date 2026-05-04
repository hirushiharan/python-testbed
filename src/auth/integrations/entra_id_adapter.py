"""Microsoft Entra ID access token validation."""

from __future__ import annotations

from dataclasses import dataclass, field
from functools import lru_cache
from typing import Any

import jwt
from jwt import ExpiredSignatureError
from jwt import ImmatureSignatureError
from jwt import InvalidAudienceError
from jwt import InvalidIssuerError
from jwt import InvalidTokenError as PyJwtInvalidTokenError
from jwt import MissingRequiredClaimError
from jwt import PyJWKClient

from src.auth.settings import Settings, get_settings


class InvalidAccessTokenError(Exception):
    """Raised when a bearer token cannot be validated."""


@dataclass(slots=True)
class EntraTokenValidator:
    """Validate JWT access tokens issued by Microsoft Entra ID."""

    settings: Settings
    _jwk_client: PyJWKClient = field(init=False, repr=False)

    def __post_init__(self) -> None:
        self._jwk_client = PyJWKClient(self.settings.resolved_entra_jwks_url)

    def validate_token(self, token: str) -> dict[str, Any]:
        claims: dict[str, Any] | None = None

        try:
            signing_key = self._jwk_client.get_signing_key_from_jwt(token)

            for accepted_issuer in self.settings.resolved_entra_issuers:
                try:
                    claims = jwt.decode(
                        token,
                        signing_key.key,
                        algorithms=self.settings.resolved_entra_algorithms,
                        audience=self.settings.resolved_entra_audiences,
                        issuer=accepted_issuer,
                        options={"require": ["exp", "iat", "nbf", "iss", "aud"]},
                    )
                    break
                except InvalidIssuerError:
                    continue

            if claims is None:
                raise InvalidAccessTokenError("Invalid token issuer")
        except ExpiredSignatureError as exc:
            raise InvalidAccessTokenError("Access token has expired") from exc
        except InvalidAudienceError as exc:
            raise InvalidAccessTokenError("Invalid token audience") from exc
        except InvalidIssuerError as exc:
            raise InvalidAccessTokenError("Invalid token issuer") from exc
        except ImmatureSignatureError as exc:
            raise InvalidAccessTokenError("Token is not valid yet") from exc
        except MissingRequiredClaimError as exc:
            raise InvalidAccessTokenError("Token is missing required claims") from exc
        except PyJwtInvalidTokenError as exc:
            raise InvalidAccessTokenError("Invalid or expired access token") from exc

        tenant_claim = claims.get("tid")
        if not self.settings.entra_allow_multi_tenant and tenant_claim != self.settings.entra_tenant_id:
            raise InvalidAccessTokenError("Token tenant does not match configured tenant")

        self._validate_access_claims(claims)
        return claims

    def _validate_access_claims(self, claims: dict[str, Any]) -> None:
        scopes_claim = claims.get("scp")
        roles_claim = claims.get("roles")

        granted_scopes: set[str] = set()
        if isinstance(scopes_claim, str):
            granted_scopes = {item.strip() for item in scopes_claim.split() if item.strip()}

        granted_roles: set[str] = set()
        if isinstance(roles_claim, list):
            granted_roles = {
                item.strip()
                for item in roles_claim
                if isinstance(item, str) and item.strip()
            }

        if not granted_scopes and not granted_roles:
            raise InvalidAccessTokenError("Token is not a valid API access token")

        required_scopes = set(self.settings.resolved_entra_required_scopes)
        if required_scopes and not required_scopes.issubset(granted_scopes):
            raise InvalidAccessTokenError("Token is missing required scopes")


@lru_cache(maxsize=1)
def get_entra_token_validator() -> EntraTokenValidator:
    """Return a cached validator instance."""

    return EntraTokenValidator(settings=get_settings())

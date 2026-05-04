"""Application settings for the auth module."""

from __future__ import annotations

from functools import lru_cache
from typing import Literal

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Configuration for auth workflows and MySQL persistence."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
        case_sensitive=False,
    )

    app_name: str = "Python Testbed Auth"
    environment: Literal["local", "dev", "staging", "prod"] = "local"
    log_level: str = "INFO"
    api_v1_prefix: str = "/api/v1"

    entra_tenant_id: str = Field(..., description="Entra tenant ID")
    entra_client_id: str = Field(..., description="Entra application client ID")
    entra_client_secret: str | None = Field(default=None, description="Entra client secret")
    entra_audience: str | None = Field(default=None, description="Expected JWT audience")
    entra_authority_host: str = "https://login.microsoftonline.com"
    entra_allowed_algorithms: str = "RS256"
    entra_allow_multi_tenant: bool = False
    entra_issuer: str | None = Field(default=None, description="Explicit issuer override")
    entra_jwks_url: str | None = Field(default=None, description="Explicit JWKS URL override")
    entra_token_url: str | None = Field(default=None, description="Explicit token endpoint override")
    entra_redirect_uri: str = "http://localhost:8000/api/v1/auth/callback"
    entra_auth_scopes: str = "openid,profile,email,offline_access"
    entra_required_scopes: str | None = Field(default=None, description="Required API scopes")

    mysql_host: str = "localhost"
    mysql_port: int = 3306
    mysql_database: str = "python_testbed"
    mysql_user: str = Field(..., description="MySQL username")
    mysql_password: str = Field(..., description="MySQL password")
    sqlalchemy_database_url: str | None = Field(
        default=None,
        description="Full SQLAlchemy URL override",
    )

    @field_validator("environment", mode="before")
    @classmethod
    def normalize_environment(cls, value: str | None) -> str:
        raw = (value or "local").strip().lower()
        aliases = {"production": "prod", "prd": "prod", "development": "dev"}
        return aliases.get(raw, raw)

    @property
    def resolved_entra_audiences(self) -> list[str]:
        if self.entra_audience:
            configured = [item.strip() for item in self.entra_audience.split(",") if item.strip()]
            expanded: list[str] = []
            for audience in configured:
                if audience not in expanded:
                    expanded.append(audience)
                if audience.startswith("api://"):
                    plain = audience.removeprefix("api://")
                    if plain and plain not in expanded:
                        expanded.append(plain)
                else:
                    prefixed = f"api://{audience}"
                    if prefixed not in expanded:
                        expanded.append(prefixed)
            return expanded
        return [f"api://{self.entra_client_id}", self.entra_client_id]

    @property
    def resolved_entra_issuers(self) -> list[str]:
        if self.entra_issuer:
            return [self.entra_issuer.format(tenant_id=self.entra_tenant_id)]
        host = self.entra_authority_host.rstrip("/")
        return [
            f"{host}/{self.entra_tenant_id}/v2.0",
            f"https://sts.windows.net/{self.entra_tenant_id}/",
        ]

    @property
    def resolved_entra_jwks_url(self) -> str:
        if self.entra_jwks_url:
            return self.entra_jwks_url.format(tenant_id=self.entra_tenant_id)
        return f"{self.entra_authority_host}/{self.entra_tenant_id}/discovery/v2.0/keys"

    @property
    def resolved_entra_algorithms(self) -> list[str]:
        return [item.strip() for item in self.entra_allowed_algorithms.split(",") if item.strip()]

    @property
    def resolved_entra_auth_scopes(self) -> list[str]:
        return [item.strip() for item in self.entra_auth_scopes.split(",") if item.strip()]

    @property
    def resolved_entra_required_scopes(self) -> list[str]:
        if not self.entra_required_scopes:
            return []
        return [item.strip() for item in self.entra_required_scopes.split(",") if item.strip()]

    @property
    def entra_token_endpoint(self) -> str:
        if self.entra_token_url:
            return self.entra_token_url.format(tenant_id=self.entra_tenant_id)
        return f"{self.entra_authority_host}/{self.entra_tenant_id}/oauth2/v2.0/token"

    @property
    def entra_authorize_endpoint(self) -> str:
        return f"{self.entra_authority_host}/{self.entra_tenant_id}/oauth2/v2.0/authorize"


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    """Return cached auth settings."""

    return Settings()

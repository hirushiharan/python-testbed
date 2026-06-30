"""Settings for Outlook mailbox operations via Microsoft Graph."""

from __future__ import annotations

from functools import lru_cache

from pydantic import AliasChoices, Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class OutlookSettings(BaseSettings):
    """Configuration used by the Outlook Graph client."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
        case_sensitive=False,
    )

    outlook_tenant_id: str = Field(
        ...,
        validation_alias=AliasChoices("OUTLOOK_TENANT_ID", "SHAREPOINT_TENANT_ID"),
        description="Microsoft Entra tenant ID",
    )
    outlook_client_id: str = Field(
        ...,
        validation_alias=AliasChoices("OUTLOOK_CLIENT_ID", "SHAREPOINT_CLIENT_ID"),
        description="Entra application client ID",
    )
    outlook_client_secret: str = Field(
        ...,
        validation_alias=AliasChoices("OUTLOOK_CLIENT_SECRET", "SHAREPOINT_CLIENT_SECRET"),
        description="Entra application client secret",
    )
    outlook_mailbox: str | None = Field(
        default=None,
        description="Target mailbox UPN or object ID (e.g. user@domain.com)",
    )
    graph_authority_host: str = "https://login.microsoftonline.com"
    graph_base_url: str = "https://graph.microsoft.com/v1.0"
    request_timeout_seconds: int = 60


@lru_cache(maxsize=1)
def get_outlook_settings() -> OutlookSettings:
    """Return cached Outlook settings."""

    return OutlookSettings()

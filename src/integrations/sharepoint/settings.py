"""Settings for SharePoint document-library operations."""

from __future__ import annotations

from functools import lru_cache

from pydantic import AliasChoices, Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class SharePointSettings(BaseSettings):
    """Configuration used by the SharePoint Graph client."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
        case_sensitive=False,
    )

    sharepoint_tenant_id: str = Field(
        ...,
        validation_alias=AliasChoices("SHAREPOINT_TENANT_ID", "OUTLOOK_TENANT_ID"),
        description="Microsoft Entra tenant ID used for Graph authentication",
    )
    sharepoint_client_id: str = Field(
        ...,
        validation_alias=AliasChoices("SHAREPOINT_CLIENT_ID", "OUTLOOK_CLIENT_ID"),
        description="Entra application client ID",
    )
    sharepoint_client_secret: str = Field(
        ...,
        validation_alias=AliasChoices("SHAREPOINT_CLIENT_SECRET", "OUTLOOK_CLIENT_SECRET"),
        description="Entra application client secret",
    )
    sharepoint_site_id: str = Field(
        ...,
        description="SharePoint site ID that owns the document library",
    )
    sharepoint_drive_id: str | None = Field(
        default=None,
        description="Optional drive ID for the document library; resolved from the site when omitted",
    )
    sharepoint_default_parent_folder_id: str | None = Field(
        default=None,
        description="Optional folder ID used as the default parent for new documents",
    )
    sharepoint_upload_chunk_size: int = Field(
        default=5 * 1024 * 1024,
        description="Chunk size in bytes for resumable uploads",
    )
    sharepoint_conflict_behavior: str = Field(
        default="rename",
        description="Graph conflict behavior for create/upload operations",
    )
    graph_authority_host: str = "https://login.microsoftonline.com"
    graph_base_url: str = "https://graph.microsoft.com/v1.0"
    request_timeout_seconds: int = 60


@lru_cache(maxsize=1)
def get_sharepoint_settings() -> SharePointSettings:
    """Return cached SharePoint settings."""

    return SharePointSettings()

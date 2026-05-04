"""Pydantic schemas for SharePoint endpoints."""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, Field


class CreateDocumentRequest(BaseModel):
    """Request body for creating a SharePoint document folder."""

    name: str = Field(min_length=1, max_length=255)
    parent_folder_id: str | None = Field(default=None, description="Optional parent folder ID")
    conflict_behavior: str = Field(default="rename", description="Graph conflict behavior")


class SharePointItemResponse(BaseModel):
    """Base metadata returned for SharePoint drive items."""

    id: str
    name: str
    web_url: str | None = None
    size: int | None = None
    last_modified_date_time: datetime | None = None
    parent_folder_id: str | None = None


class SharePointDocumentResponse(SharePointItemResponse):
    """Response returned when creating a SharePoint document folder."""

    folder_id: str


class SharePointFileResponse(SharePointItemResponse):
    """Metadata for files returned from a folder listing or upload."""

    download_url: str | None = None


class UploadResponse(SharePointFileResponse):
    """Response returned after a file upload completes."""


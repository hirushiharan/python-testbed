"""Pydantic schemas for Outlook email endpoints."""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel


class OutlookConnectionStatus(BaseModel):
    """Result of a Graph API connection test."""

    connected: bool
    tenant_id: str
    client_id: str
    token_obtained: bool
    graph_api_accessible: bool
    mailbox_verified: bool
    mailbox: str | None = None
    error: str | None = None
    checked_at: datetime


class MailFolderResponse(BaseModel):
    """Metadata for a single mail folder."""

    id: str
    display_name: str
    total_item_count: int = 0
    unread_item_count: int = 0
    child_folder_count: int = 0


class MailMessageResponse(BaseModel):
    """Summary metadata for a single mail message."""

    id: str
    subject: str | None = None
    from_address: str | None = None
    received_date_time: datetime | None = None
    is_read: bool = False
    has_attachments: bool = False
    body_preview: str | None = None

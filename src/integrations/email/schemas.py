"""Pydantic schemas for Outlook email endpoints."""

from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field


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


class SendMailRequest(BaseModel):
    """Request body for sending a test email."""

    to: list[str] = Field(..., min_length=1, description="Recipient email addresses")
    cc: list[str] = Field(default_factory=list)
    subject: str = "Test email from python-testbed"
    body: str = "This is a test email sent via the Microsoft Graph API."
    body_content_type: Literal["Text", "HTML"] = "Text"
    save_to_sent_items: bool = True


class SendMailResponse(BaseModel):
    """Confirmation that Graph accepted the message for delivery."""

    accepted: bool
    sender: str
    to: list[str]
    subject: str
    sent_at: datetime


class MailFolderResponse(BaseModel):
    """Metadata for a single mail folder."""

    id: str
    display_name: str
    parent_folder_id: str | None = None
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
    body_content_type: str | None = None
    body_content: str | None = None

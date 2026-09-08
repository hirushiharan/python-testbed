"""Outlook service layer for mailbox operations."""

from __future__ import annotations

import datetime as dt

from src.integrations.email.client import OutlookGraphClient
from src.integrations.email.schemas import (
    MailFolderResponse,
    MailMessageResponse,
    OutlookConnectionStatus,
)


class OutlookServiceError(RuntimeError):
    """Service-level error for Outlook operations."""


class OutlookService:
    """High-level Outlook operations used by the API layer."""

    def __init__(self, client: OutlookGraphClient | None = None) -> None:
        self.client = client or OutlookGraphClient()

    def _require_mailbox(self) -> str:
        mailbox = (self.client.settings.outlook_mailbox or "").strip()
        if not mailbox:
            raise OutlookServiceError(
                "OUTLOOK_MAILBOX is not configured; set the environment variable and restart"
            )
        return mailbox

    def test_connection(self) -> OutlookConnectionStatus:
        """Acquire a Graph API token and verify connectivity."""
        raw = self.client.test_connection()
        # Graph API "login" = token acquisition. connected=True means auth succeeded.
        # graph_api_accessible and mailbox_verified reflect what the app can actually reach.
        connected = bool(raw["token_obtained"])
        return OutlookConnectionStatus(
            connected=connected,
            tenant_id=raw["tenant_id"],
            client_id=raw["client_id"],
            token_obtained=raw["token_obtained"],
            graph_api_accessible=raw["graph_api_accessible"],
            mailbox_verified=raw["mailbox_verified"],
            mailbox=raw["mailbox"],
            error=raw["error"],
            checked_at=dt.datetime.now(dt.timezone.utc),
        )

    def list_mail_folders(self) -> list[MailFolderResponse]:
        """List all mail folders for the configured mailbox."""
        mailbox = self._require_mailbox()
        raw_folders = self.client.list_mail_folders(mailbox)
        return [
            MailFolderResponse(
                id=str(f.get("id", "")),
                display_name=str(f.get("displayName", "")),
                parent_folder_id=str(f.get("parentFolderId", "")).strip() or None,
                total_item_count=int(f.get("totalItemCount", 0) or 0),
                unread_item_count=int(f.get("unreadItemCount", 0) or 0),
                child_folder_count=int(f.get("childFolderCount", 0) or 0),
            )
            for f in raw_folders
            if f.get("id")
        ]

    def fetch_messages(
        self,
        folder_id: str,
        max_messages: int = 25,
    ) -> list[MailMessageResponse]:
        """Fetch messages from a mail folder for the configured mailbox."""
        mailbox = self._require_mailbox()
        raw_messages = self.client.fetch_messages(mailbox, folder_id, max_messages)
        result: list[MailMessageResponse] = []

        for m in raw_messages:
            from_obj = m.get("from") or {}
            from_email_obj = (from_obj.get("emailAddress") or {})
            from_address = str(from_email_obj.get("address", "")).strip() or None

            received_dt: dt.datetime | None = None
            received_raw = m.get("receivedDateTime")
            if received_raw:
                try:
                    received_dt = dt.datetime.fromisoformat(
                        str(received_raw).replace("Z", "+00:00")
                    )
                except ValueError:
                    pass

            body_obj = m.get("body") or {}

            result.append(
                MailMessageResponse(
                    id=str(m.get("id", "")),
                    subject=str(m.get("subject", "")).strip() or None,
                    from_address=from_address,
                    received_date_time=received_dt,
                    is_read=bool(m.get("isRead", False)),
                    has_attachments=bool(m.get("hasAttachments", False)),
                    body_preview=str(m.get("bodyPreview", "")).strip() or None,
                    body_content_type=str(body_obj.get("contentType", "")).strip() or None,
                    body_content=str(body_obj.get("content", "")).strip() or None,
                )
            )

        return result

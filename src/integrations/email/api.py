"""FastAPI router for Outlook mailbox endpoints."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query, status

from src.integrations.email.client import OutlookClientError, OutlookConfigurationError
from src.integrations.email.schemas import (
    MailFolderResponse,
    MailMessageResponse,
    OutlookConnectionStatus,
)
from src.integrations.email.service import OutlookService, OutlookServiceError

router = APIRouter(prefix="/outlook", tags=["outlook"])


def get_outlook_service() -> OutlookService:
    """Build the Outlook service dependency."""

    return OutlookService()


def _map_outlook_error(exc: Exception) -> HTTPException:
    if isinstance(exc, (ValueError, OutlookServiceError)):
        return HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc))
    if isinstance(exc, OutlookConfigurationError):
        return HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(exc))
    if isinstance(exc, OutlookClientError):
        return HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=str(exc))
    return HTTPException(
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        detail="Unexpected Outlook error",
    )


@router.get("/test-connection", response_model=OutlookConnectionStatus)
def test_connection(
    service: OutlookService = Depends(get_outlook_service),
) -> OutlookConnectionStatus:
    """Test Microsoft Graph API connectivity using the configured app credentials.

    Acquires a client-credentials access token, pings the Graph /organization
    endpoint, and optionally verifies the configured mailbox user exists.
    """
    try:
        return service.test_connection()
    except Exception as exc:
        raise _map_outlook_error(exc) from exc


@router.get("/folders", response_model=list[MailFolderResponse])
def list_folders(
    service: OutlookService = Depends(get_outlook_service),
) -> list[MailFolderResponse]:
    """List all mail folders for the configured mailbox."""
    try:
        return service.list_mail_folders()
    except Exception as exc:
        raise _map_outlook_error(exc) from exc


@router.get("/folders/{folder_id}/messages", response_model=list[MailMessageResponse])
def list_messages(
    folder_id: str,
    max_messages: int = Query(default=25, ge=1, le=500),
    service: OutlookService = Depends(get_outlook_service),
) -> list[MailMessageResponse]:
    """List messages in a specific mail folder (newest first)."""
    try:
        return service.fetch_messages(folder_id=folder_id, max_messages=max_messages)
    except Exception as exc:
        raise _map_outlook_error(exc) from exc

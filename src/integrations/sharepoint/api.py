"""FastAPI router for SharePoint document endpoints."""

from __future__ import annotations

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile, status

from src.integrations.sharepoint.client import SharePointClientError, SharePointConfigurationError
from src.integrations.sharepoint.schemas import (
    CreateDocumentRequest,
    SharePointDocumentResponse,
    SharePointFileResponse,
    UploadResponse,
)
from src.integrations.sharepoint.service import SharePointService

router = APIRouter(prefix="/sharepoint", tags=["sharepoint"])


def get_sharepoint_service() -> SharePointService:
    """Build the SharePoint service dependency."""

    return SharePointService()


def _map_sharepoint_error(exc: Exception) -> HTTPException:
    if isinstance(exc, ValueError):
        return HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc))
    if isinstance(exc, SharePointConfigurationError):
        return HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(exc))
    if isinstance(exc, SharePointClientError):
        return HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=str(exc))
    return HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Unexpected SharePoint error")


@router.post("/documents", response_model=SharePointDocumentResponse)
def create_document(
    payload: CreateDocumentRequest,
    sharepoint_service: SharePointService = Depends(get_sharepoint_service),
) -> SharePointDocumentResponse:
    """Create a SharePoint document folder."""

    try:
        return sharepoint_service.create_document(payload)
    except Exception as exc:
        raise _map_sharepoint_error(exc) from exc


@router.get("/documents/{folder_id}/files", response_model=list[SharePointFileResponse])
def list_files(
    folder_id: str,
    sharepoint_service: SharePointService = Depends(get_sharepoint_service),
) -> list[SharePointFileResponse]:
    """List all files in a SharePoint document folder."""

    try:
        return sharepoint_service.list_files(folder_id)
    except Exception as exc:
        raise _map_sharepoint_error(exc) from exc


@router.post("/documents/{folder_id}/files", response_model=UploadResponse)
def upload_file(
    folder_id: str,
    file: UploadFile = File(...),
    sharepoint_service: SharePointService = Depends(get_sharepoint_service),
) -> UploadResponse:
    """Upload a file to a SharePoint document folder."""

    try:
        return sharepoint_service.upload_file(folder_id, file)
    except Exception as exc:
        raise _map_sharepoint_error(exc) from exc

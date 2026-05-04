"""SharePoint service layer for document folder operations."""

from __future__ import annotations

from fastapi import UploadFile

from src.integrations.sharepoint.client import SharePointGraphClient
from src.integrations.sharepoint.schemas import (
    CreateDocumentRequest,
    SharePointDocumentResponse,
    SharePointFileResponse,
    UploadResponse,
)


class SharePointService:
    """High-level SharePoint operations used by the API layer."""

    def __init__(self, client: SharePointGraphClient | None = None) -> None:
        self.client = client or SharePointGraphClient()

    def create_document(self, payload: CreateDocumentRequest) -> SharePointDocumentResponse:
        item = self.client.create_folder(
            name=payload.name,
            parent_folder_id=payload.parent_folder_id,
            conflict_behavior=payload.conflict_behavior,
        )
        parent_reference = item.get("parentReference") or {}
        return SharePointDocumentResponse(
            id=str(item.get("id", "")).strip(),
            folder_id=str(item.get("id", "")).strip(),
            name=str(item.get("name", "")).strip(),
            web_url=str(item.get("webUrl", "")).strip() or None,
            size=int(item.get("size", 0) or 0) or None,
            last_modified_date_time=item.get("lastModifiedDateTime"),
            parent_folder_id=str(parent_reference.get("id", "")).strip() or None,
        )

    def list_files(self, folder_id: str) -> list[SharePointFileResponse]:
        items = self.client.list_files(folder_id)
        files: list[SharePointFileResponse] = []
        for item in items:
            parent_reference = item.get("parentReference") or {}
            file_info = item.get("file") or {}
            files.append(
                SharePointFileResponse(
                    id=str(item.get("id", "")).strip(),
                    name=str(item.get("name", "")).strip(),
                    web_url=str(item.get("webUrl", "")).strip() or None,
                    size=int(item.get("size", 0) or 0) or None,
                    last_modified_date_time=item.get("lastModifiedDateTime"),
                    parent_folder_id=str(parent_reference.get("id", "")).strip() or None,
                    download_url=str(file_info.get("@microsoft.graph.downloadUrl", "")).strip() or None,
                )
            )
        return files

    def upload_file(self, folder_id: str, upload_file: UploadFile) -> UploadResponse:
        item = self.client.upload_file(folder_id, upload_file.filename or "uploaded-file", upload_file.file)
        parent_reference = item.get("parentReference") or {}
        file_info = item.get("file") or {}
        return UploadResponse(
            id=str(item.get("id", "")).strip(),
            name=str(item.get("name", "")).strip(),
            web_url=str(item.get("webUrl", "")).strip() or None,
            size=int(item.get("size", 0) or 0) or None,
            last_modified_date_time=item.get("lastModifiedDateTime"),
            parent_folder_id=str(parent_reference.get("id", "")).strip() or None,
            download_url=str(file_info.get("@microsoft.graph.downloadUrl", "")).strip() or None,
        )

from __future__ import annotations

from datetime import datetime, timezone

from fastapi import FastAPI, UploadFile
from fastapi.testclient import TestClient

from src.integrations.sharepoint.api import get_sharepoint_service, router
from src.integrations.sharepoint.schemas import (
    SharePointDocumentResponse,
    SharePointFileResponse,
    UploadResponse,
)


class _SharePointServiceStub:
    def create_document(self, payload):
        return SharePointDocumentResponse(
            id="folder-1",
            folder_id="folder-1",
            name=payload.name,
            web_url="https://contoso.sharepoint.com/sites/demo/Shared%20Documents/folder-1",
            size=None,
            last_modified_date_time=datetime.now(timezone.utc),
            parent_folder_id=payload.parent_folder_id,
        )

    def list_files(self, folder_id: str):
        return [
            SharePointFileResponse(
                id="file-1",
                name=f"{folder_id}.txt",
                web_url="https://contoso.sharepoint.com/sites/demo/Shared%20Documents/file-1",
                size=12,
                last_modified_date_time=datetime.now(timezone.utc),
                parent_folder_id=folder_id,
                download_url="https://contoso.sharepoint.com/download/file-1",
            )
        ]

    def upload_file(self, folder_id: str, upload_file: UploadFile):
        return UploadResponse(
            id="file-2",
            name=upload_file.filename or "uploaded-file",
            web_url="https://contoso.sharepoint.com/sites/demo/Shared%20Documents/file-2",
            size=15,
            last_modified_date_time=datetime.now(timezone.utc),
            parent_folder_id=folder_id,
            download_url="https://contoso.sharepoint.com/download/file-2",
        )


def _build_app() -> FastAPI:
    app = FastAPI()
    app.include_router(router, prefix="/api/v1")
    app.dependency_overrides[get_sharepoint_service] = lambda: _SharePointServiceStub()
    return app


def test_create_document_folder() -> None:
    client = TestClient(_build_app())

    response = client.post(
        "/api/v1/sharepoint/documents",
        json={"name": "Project Alpha"},
    )

    assert response.status_code == 200
    assert response.json()["name"] == "Project Alpha"
    assert response.json()["folder_id"] == "folder-1"


def test_list_files_in_folder() -> None:
    client = TestClient(_build_app())

    response = client.get("/api/v1/sharepoint/documents/folder-1/files")

    assert response.status_code == 200
    body = response.json()
    assert len(body) == 1
    assert body[0]["name"] == "folder-1.txt"


def test_upload_file_to_folder() -> None:
    client = TestClient(_build_app())

    response = client.post(
        "/api/v1/sharepoint/documents/folder-1/files",
        files={"file": ("report.txt", b"hello sharepoint", "text/plain")},
    )

    assert response.status_code == 200
    assert response.json()["name"] == "report.txt"

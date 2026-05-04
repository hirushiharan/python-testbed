"""FastAPI application for the auth module."""

from __future__ import annotations

from fastapi import FastAPI

from src.auth.api.router import router as auth_router
from src.auth.exception_handlers import register_exception_handlers
from src.integrations.sharepoint.api import router as sharepoint_router

app = FastAPI(title="Python Testbed Auth")
register_exception_handlers(app)
app.include_router(auth_router, prefix="/api/v1")
app.include_router(sharepoint_router, prefix="/api/v1")

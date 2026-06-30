"""FastAPI application entrypoint."""

from __future__ import annotations

from fastapi import FastAPI

from src.auth.api.router import router as auth_router
from src.auth.exception_handlers import register_exception_handlers
from src.integrations.email.api import router as outlook_router
from src.integrations.sharepoint.api import router as sharepoint_router

app = FastAPI(title="Python Testbed")
register_exception_handlers(app)
app.include_router(auth_router, prefix="/api/v1")
app.include_router(sharepoint_router, prefix="/api/v1")
app.include_router(outlook_router, prefix="/api/v1")

"""Centralized exception handler registration for the auth app."""

from __future__ import annotations

from fastapi import FastAPI, Request, status
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse

from src.auth.application.errors import AuthRepositoryError, AuthTokenExchangeError, AuthTokenValidationError
from src.auth.domain.errors import AuthAuthorizationError


def _json_error(status_code: int, detail: str) -> JSONResponse:
    return JSONResponse(status_code=status_code, content={"detail": detail})


def register_exception_handlers(app: FastAPI) -> None:
    """Register project-level exception handlers."""

    @app.exception_handler(RequestValidationError)
    async def _handle_validation_error(_: Request, exc: RequestValidationError) -> JSONResponse:
        return JSONResponse(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, content={"detail": exc.errors()})

    @app.exception_handler(AuthTokenExchangeError)
    async def _handle_auth_exchange_error(_: Request, exc: AuthTokenExchangeError) -> JSONResponse:
        return _json_error(status.HTTP_401_UNAUTHORIZED, str(exc))

    @app.exception_handler(AuthTokenValidationError)
    async def _handle_auth_validation_error(_: Request, exc: AuthTokenValidationError) -> JSONResponse:
        return _json_error(status.HTTP_401_UNAUTHORIZED, str(exc))

    @app.exception_handler(AuthAuthorizationError)
    async def _handle_auth_authorization_error(_: Request, exc: AuthAuthorizationError) -> JSONResponse:
        return _json_error(status.HTTP_403_FORBIDDEN, str(exc))

    @app.exception_handler(AuthRepositoryError)
    async def _handle_auth_repository_error(_: Request, exc: AuthRepositoryError) -> JSONResponse:
        return _json_error(status.HTTP_500_INTERNAL_SERVER_ERROR, str(exc))

    @app.exception_handler(Exception)
    async def _handle_unexpected_error(_: Request, exc: Exception) -> JSONResponse:
        return _json_error(status.HTTP_500_INTERNAL_SERVER_ERROR, "Internal server error")

"""Schemas for auth endpoints."""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, EmailStr, Field


class LoginUrlResponse(BaseModel):
    """Authorization URL and CSRF state token for initiating login."""

    url: str = Field(description="Microsoft Entra authorization URL")
    state: str = Field(description="CSRF state token")


class AuthorizationCodeExchangeRequest(BaseModel):
    """Authorization code payload from a client."""

    code: str = Field(description="Authorization code returned by Microsoft Entra")


class ValidateTokenRequest(BaseModel):
    """Raw access token payload for validation."""

    token: str = Field(description="Microsoft access token")


class AuthenticatedUser(BaseModel):
    """User context resolved from token validation and database lookup."""

    user_id: int
    email: EmailStr
    role: str
    is_active: bool
    name: str | None = None


class EntraAccessTokenResponse(BaseModel):
    """Token exchange response payload."""

    access_token: str
    token_type: str = "bearer"
    expires_in: int
    user: AuthenticatedUser


class ValidateTokenResponse(BaseModel):
    """Session payload returned by token validation."""

    access_token: str
    token_type: str = "bearer"
    expires_in: int
    user: AuthenticatedUser


class UserDetailsResponse(BaseModel):
    """User record exposed by the list endpoint."""

    user_id: int
    email: EmailStr
    role: str
    is_active: bool
    created_by: str
    created_at: datetime
    updated_by: str
    updated_at: datetime

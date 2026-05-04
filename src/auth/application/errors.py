"""Application-layer errors for the auth module."""

from __future__ import annotations


class AuthTokenExchangeError(Exception):
    """Raised when authorization-code token exchange fails."""


class AuthTokenValidationError(Exception):
    """Raised when Microsoft token validation fails."""


class AuthRepositoryError(Exception):
    """Raised when auth repository operations fail."""

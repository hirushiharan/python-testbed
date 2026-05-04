"""Auth domain errors."""

from __future__ import annotations


class AuthAuthorizationError(Exception):
    """Raised when an authenticated identity is not authorized in the application."""

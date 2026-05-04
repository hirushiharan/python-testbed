"""Role normalization business rules."""

from __future__ import annotations


def normalize_role(role_name: str) -> str:
    """Normalize DB role labels into stable role keys."""

    normalized = role_name.strip().lower().replace("-", " ")
    segments = [segment for segment in normalized.split() if segment]
    return "_".join(segments)

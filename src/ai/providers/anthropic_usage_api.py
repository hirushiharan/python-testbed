"""FastAPI routes for Anthropic organization usage and cost reporting."""

from __future__ import annotations

import os
from typing import Annotated

from dotenv import load_dotenv
from fastapi import APIRouter, HTTPException, Query, status
from pydantic import BaseModel

from src.ai.providers.anthropic_usage import (
    _default_ending_at,
    _default_starting_at,
    fetch_report,
    summarize,
)

router = APIRouter(prefix="/anthropic", tags=["anthropic"])


class AnthropicUsageReport(BaseModel):
    """Aggregated Anthropic organization usage and cost."""

    starting_at: str
    ending_at: str
    usage: dict[str, int]
    cost_usd: dict[str, str]
    balance_credits: None = None
    balance_note: str
    row_counts: dict[str, int]


@router.get("/usage", response_model=AnthropicUsageReport)
def get_usage_report(
    starting_at: Annotated[
        str, Query(description="UTC ISO-8601 start, maximum report span is 31 days")
    ] = _default_starting_at(),
    ending_at: Annotated[str, Query(description="UTC ISO-8601 end")] = _default_ending_at(),
    group_by: Annotated[
        list[str] | None,
        Query(description="Optional dimensions such as model or workspace_id"),
    ] = None,
) -> AnthropicUsageReport:
    """Return organization token usage and cost for a date range.

    Requires ANTHROPIC_ADMIN_API_KEY in the server environment. The API key is
    never accepted as a request parameter or returned in the response.
    """
    load_dotenv()
    api_key = os.getenv("ANTHROPIC_ADMIN_API_KEY", "").strip()
    if not api_key:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Missing ANTHROPIC_ADMIN_API_KEY server configuration",
        )

    try:
        usage_rows = fetch_report(api_key, "usage", starting_at, ending_at, group_by or [])
        cost_rows = fetch_report(api_key, "cost", starting_at, ending_at, group_by or [])
        report = summarize(usage_rows, cost_rows)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    except RuntimeError as exc:
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=str(exc)) from exc

    return AnthropicUsageReport(starting_at=starting_at, ending_at=ending_at, **report)

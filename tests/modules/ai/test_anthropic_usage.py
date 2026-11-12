"""Tests for the Anthropic organization usage utility."""

from decimal import Decimal

from src.ai.providers.anthropic_usage import build_query, summarize


def test_build_query_repeats_group_dimensions() -> None:
    query = build_query(
        "2026-11-01T00:00:00Z",
        "2026-11-12T00:00:00Z",
        ["model", "workspace_id"],
        "cursor-1",
    )

    assert "starting_at=2026-11-01T00%3A00%3A00Z" in query
    assert "group_by%5B%5D=model" in query
    assert "group_by%5B%5D=workspace_id" in query
    assert "cursor=cursor-1" in query


def test_summarize_converts_fractional_cents_to_dollars() -> None:
    report = summarize(
        [
            {"usage": {"input_tokens": 10, "output_tokens": 4, "requests": 1}},
            {"usage": {"input_tokens": 5, "output_tokens": 2, "requests": 1}},
        ],
        [{"cost": {"amount": "41280.000000", "list_amount": "50000.000000"}}],
    )

    assert report["usage"] == {"input_tokens": 15, "output_tokens": 6, "requests": 2}
    assert Decimal(report["cost_usd"]["amount"]) == Decimal("412.8")
    assert Decimal(report["cost_usd"]["list_amount"]) == Decimal("500")
    assert report["balance_credits"] is None

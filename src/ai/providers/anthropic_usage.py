"""Report Anthropic organization usage and cost through the Admin API."""

from __future__ import annotations

import argparse
import json
import logging
import os
import sys
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timedelta, timezone
from decimal import Decimal, InvalidOperation
from typing import Any

from dotenv import load_dotenv

API_BASE_URL = "https://api.anthropic.com/v1/organizations/analytics"
ANTHROPIC_VERSION = "2026-10-21"
ANALYTICS_BETA = "analytics-usage-cost-2026-08-24"
REQUEST_TIMEOUT_SECONDS = 60
DEFAULT_LOOKBACK_DAYS = 30

logger = logging.getLogger(__name__)


def _default_starting_at() -> str:
    """Return the start of the default UTC lookback window."""
    now = datetime.now(timezone.utc)
    return (now - timedelta(days=DEFAULT_LOOKBACK_DAYS)).strftime(
        "%Y-%m-%dT%H:%M:%SZ"
    )


def _default_ending_at() -> str:
    """Return the current UTC time."""
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def build_query(
    starting_at: str,
    ending_at: str,
    group_by: list[str],
    cursor: str | None = None,
) -> str:
    """Build an Analytics API query string."""
    values: list[tuple[str, str]] = [
        ("starting_at", starting_at),
        ("ending_at", ending_at),
        ("limit", "1000"),
    ]
    values.extend(("group_by[]", dimension) for dimension in group_by)
    if cursor:
        values.append(("cursor", cursor))
    return urllib.parse.urlencode(values)


def fetch_report(
    api_key: str,
    report: str,
    starting_at: str,
    ending_at: str,
    group_by: list[str],
) -> list[dict[str, Any]]:
    """Fetch all pages of an organization usage or cost report."""
    if report not in {"usage", "cost"}:
        raise ValueError(f"Unsupported report: {report}")

    rows: list[dict[str, Any]] = []
    cursor: str | None = None
    while True:
        query = build_query(starting_at, ending_at, group_by, cursor)
        url = f"{API_BASE_URL}/{report}?{query}"
        request = urllib.request.Request(url, method="GET")
        request.add_header("x-api-key", api_key)
        request.add_header("anthropic-version", ANTHROPIC_VERSION)
        request.add_header("anthropic-beta", ANALYTICS_BETA)
        request.add_header("accept", "application/json")

        try:
            with urllib.request.urlopen(request, timeout=REQUEST_TIMEOUT_SECONDS) as response:
                payload = json.loads(response.read().decode("utf-8"))
        except urllib.error.HTTPError as exc:
            body = exc.read().decode("utf-8") if exc.fp else ""
            message = f"Anthropic {report} report failed (HTTP {exc.code}): {body}"
            raise RuntimeError(message) from exc
        except urllib.error.URLError as exc:
            message = f"Network error while fetching Anthropic {report} report: {exc.reason}"
            raise RuntimeError(message) from exc
        except json.JSONDecodeError as exc:
            raise RuntimeError(f"Anthropic returned invalid JSON for the {report} report") from exc

        page_rows = payload.get("data", [])
        if not isinstance(page_rows, list) or not all(isinstance(row, dict) for row in page_rows):
            raise RuntimeError(f"Unexpected data shape in Anthropic {report} report")
        rows.extend(page_rows)

        if not payload.get("has_more"):
            break
        next_page = payload.get("next_page")
        if not isinstance(next_page, str) or not next_page:
            raise RuntimeError(f"Anthropic {report} report indicated more data without a cursor")
        cursor = next_page

    return rows


def _decimal(value: Any) -> Decimal:
    """Parse a numeric API value, treating absent metrics as zero."""
    try:
        return Decimal(str(value or 0))
    except (InvalidOperation, ValueError):
        return Decimal(0)


def summarize(usage_rows: list[dict[str, Any]], cost_rows: list[dict[str, Any]]) -> dict[str, Any]:
    """Aggregate report rows into a compact, JSON-serializable summary."""
    usage_totals: dict[str, int] = {}
    for row in usage_rows:
        metrics = row.get("usage") or row.get("metrics") or {}
        if not isinstance(metrics, dict):
            continue
        for name, value in metrics.items():
            if isinstance(value, (int, float, str)):
                usage_totals[name] = usage_totals.get(name, 0) + int(_decimal(value))

    total_amount_cents = sum(
        (_decimal((row.get("cost") or {}).get("amount")) for row in cost_rows),
        Decimal(0),
    )
    total_list_amount_cents = sum(
        (_decimal((row.get("cost") or {}).get("list_amount")) for row in cost_rows),
        Decimal(0),
    )
    return {
        "usage": usage_totals,
        "cost_usd": {
            "amount": str(total_amount_cents / Decimal(100)),
            "list_amount": str(total_list_amount_cents / Decimal(100)),
            "currency": "USD",
        },
        "balance_credits": None,
        "balance_note": (
            "Anthropic does not document a public API for remaining Console credits. "
            "Check the Claude Console billing page for the current balance."
        ),
        "row_counts": {"usage": len(usage_rows), "cost": len(cost_rows)},
    }


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    """Parse command-line arguments."""
    parser = argparse.ArgumentParser(description="Report Anthropic organization usage and cost")
    parser.add_argument("--starting-at", default=_default_starting_at(), help="UTC ISO-8601 start")
    parser.add_argument("--ending-at", default=_default_ending_at(), help="UTC ISO-8601 end")
    parser.add_argument(
        "--group-by",
        action="append",
        default=[],
        help="Analytics dimension (repeatable, for example --group-by model)",
    )
    parser.add_argument("--json", action="store_true", help="Print the report as JSON")
    parser.add_argument("--verbose", action="store_true", help="Enable debug logs")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    """Run the Anthropic usage report command."""
    args = parse_args(argv)
    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(levelname)s: %(message)s",
    )
    load_dotenv()

    api_key = os.getenv("ANTHROPIC_ADMIN_API_KEY", "").strip()
    if not api_key:
        logger.error("Missing ANTHROPIC_ADMIN_API_KEY environment variable")
        print("Set ANTHROPIC_ADMIN_API_KEY to an Anthropic Admin API key and re-run.")
        return 1

    try:
        usage_rows = fetch_report(
            api_key, "usage", args.starting_at, args.ending_at, args.group_by
        )
        cost_rows = fetch_report(
            api_key, "cost", args.starting_at, args.ending_at, args.group_by
        )
        report = summarize(usage_rows, cost_rows)
    except (RuntimeError, ValueError) as exc:
        logger.error("%s", exc)
        return 1

    if args.json:
        print(json.dumps(report, indent=2))
    else:
        print(f"Period: {args.starting_at} to {args.ending_at}")
        print(f"Requests: {report['usage'].get('requests', 0)}")
        print(f"Input tokens: {report['usage'].get('input_tokens', 0)}")
        print(f"Output tokens: {report['usage'].get('output_tokens', 0)}")
        print(f"Used cost: ${report['cost_usd']['amount']} USD")
        print("Remaining credits: unavailable through the documented API")
    return 0


if __name__ == "__main__":
    sys.exit(main())

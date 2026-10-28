"""Batched CloudWatch lookups used to find the last time a resource saw activity."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import NamedTuple

from src.aws_inventory.model import ACTIVITY_WINDOW_DAYS, iso
from src.aws_inventory.session import Context

MAX_QUERIES_PER_CALL = 500
DAY_SECONDS = 86400


class MetricQuery(NamedTuple):
    """One metric to inspect for a resource."""

    namespace: str
    metric: str
    dimensions: dict[str, str]
    stat: str = "Sum"


def latest_activity(
    ctx: Context,
    service: str,
    region: str,
    queries: dict[str, MetricQuery],
    days: int = ACTIVITY_WINDOW_DAYS,
) -> dict[str, str | None]:
    """Return, per key, the newest day with a non-zero datapoint in the last ``days`` days.

    A key mapped to None means the metric was read and showed no activity in the window.
    A key that is absent means the lookup failed (permissions, throttling), so activity is
    unknown. Uses ``get_metric_data`` with up to 500 queries per call.
    """
    results: dict[str, str | None] = {}
    if not queries:
        return results

    cloudwatch = ctx.client("cloudwatch", region)
    end = datetime.now(timezone.utc)
    start = end - timedelta(days=days)
    keys = list(queries)

    for offset in range(0, len(keys), MAX_QUERIES_PER_CALL):
        chunk = keys[offset : offset + MAX_QUERIES_PER_CALL]
        data_queries = [
            {
                "Id": f"q{index}",
                "MetricStat": {
                    "Metric": {
                        "Namespace": queries[key].namespace,
                        "MetricName": queries[key].metric,
                        "Dimensions": [
                            {"Name": name, "Value": value}
                            for name, value in queries[key].dimensions.items()
                        ],
                    },
                    "Period": DAY_SECONDS,
                    "Stat": queries[key].stat,
                },
                "ReturnData": True,
            }
            for index, key in enumerate(chunk)
        ]

        def fetch(data_queries: list[dict] = data_queries) -> list[dict]:
            paginator = cloudwatch.get_paginator("get_metric_data")
            found: list[dict] = []
            for page in paginator.paginate(
                MetricDataQueries=data_queries,
                StartTime=start,
                EndTime=end,
                ScanBy="TimestampDescending",
            ):
                found.extend(page.get("MetricDataResults", []))
            return found

        data = ctx.safe(service, region, "cloudwatch:GetMetricData", fetch)
        if data is None:
            continue

        by_id: dict[str, dict[str, object]] = {}
        for result in data:
            slot = by_id.setdefault(result["Id"], {"timestamps": [], "values": []})
            slot["timestamps"].extend(result.get("Timestamps", []))  # type: ignore[union-attr]
            slot["values"].extend(result.get("Values", []))  # type: ignore[union-attr]

        for index, key in enumerate(chunk):
            slot = by_id.get(f"q{index}", {"timestamps": [], "values": []})
            newest = None
            for timestamp, value in zip(slot["timestamps"], slot["values"]):  # type: ignore[arg-type]
                if value and (newest is None or timestamp > newest):
                    newest = timestamp
            results[key] = iso(newest)

    return results


def apply_activity(
    resource_activity: dict[str, str | None], key: str, source: str
) -> tuple[str | None, str | None, bool | None]:
    """Turn a lookup result into (last_activity, source, observed_active).

    ``observed_active`` is None when the lookup failed so callers can leave is_active unknown.
    """
    if key not in resource_activity:
        return None, None, None
    value = resource_activity[key]
    return value, source, value is not None

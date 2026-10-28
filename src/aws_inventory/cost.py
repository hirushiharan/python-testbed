"""Cost Explorer spend by service/region: the best signal of which services are really in use.

Costs one Cost Explorer request per ~page (about $0.01 each); skip with ``--skip-cost``.
"""

from __future__ import annotations

from datetime import date, timedelta
from typing import Any

from src.aws_inventory.session import Context

LOOKBACK_DAYS = 90

# Cost Explorer service names -> collector service keys.
COST_SERVICE_MAP = {
    "Amazon Elastic Compute Cloud - Compute": "ec2",
    "EC2 - Other": "ec2",
    "Amazon Virtual Private Cloud": "ec2",
    "Amazon Simple Storage Service": "s3",
    "Amazon Relational Database Service": "rds",
    "AWS Lambda": "lambda",
    "Amazon Elastic Container Service": "ecs",
    "Amazon Elastic Container Service for Kubernetes": "eks",
    "Amazon DynamoDB": "dynamodb",
    "Elastic Load Balancing": "elbv2",
    "Amazon CloudFront": "cloudfront",
    "Amazon API Gateway": "apigateway",
    "Amazon Simple Queue Service": "sqs",
    "Amazon Simple Notification Service": "sns",
    "AWS Identity and Access Management": "iam",
}


def fetch_costs(ctx: Context) -> dict[str, Any]:
    """Return {'by_service', 'unmapped', 'unit', 'period'}; empty dict if Cost Explorer fails."""
    end = date.today()
    start = end - timedelta(days=LOOKBACK_DAYS)
    client = ctx.client("ce", ctx.global_region)

    def fetch() -> dict[str, Any]:
        by_service: dict[str, dict[str, Any]] = {}
        unmapped: dict[str, float] = {}
        unit = "USD"
        token = None
        while True:
            kwargs: dict[str, Any] = {
                "TimePeriod": {"Start": start.isoformat(), "End": end.isoformat()},
                "Granularity": "MONTHLY",
                "Metrics": ["UnblendedCost"],
                "GroupBy": [
                    {"Type": "DIMENSION", "Key": "SERVICE"},
                    {"Type": "DIMENSION", "Key": "REGION"},
                ],
            }
            if token:
                kwargs["NextPageToken"] = token
            response = client.get_cost_and_usage(**kwargs)
            for period in response.get("ResultsByTime", []):
                for group in period.get("Groups", []):
                    service_name, region = group["Keys"]
                    metric = group["Metrics"]["UnblendedCost"]
                    amount = float(metric["Amount"])
                    unit = metric.get("Unit", unit)
                    key = COST_SERVICE_MAP.get(service_name)
                    if key is None:
                        unmapped[service_name] = unmapped.get(service_name, 0.0) + amount
                        continue
                    entry = by_service.setdefault(key, {"total": 0.0, "by_region": {}})
                    entry["total"] += amount
                    entry["by_region"][region] = entry["by_region"].get(region, 0.0) + amount
            token = response.get("NextPageToken")
            if not token:
                break

        for entry in by_service.values():
            entry["total"] = round(entry["total"], 2)
            entry["by_region"] = {k: round(v, 2) for k, v in sorted(entry["by_region"].items())}
        return {
            "period": {"start": start.isoformat(), "end": end.isoformat()},
            "unit": unit,
            "by_service": by_service,
            "unmapped": {k: round(v, 2) for k, v in sorted(unmapped.items()) if round(v, 2) != 0},
        }

    return ctx.safe("ce", ctx.global_region, "GetCostAndUsage", fetch, {}) or {}

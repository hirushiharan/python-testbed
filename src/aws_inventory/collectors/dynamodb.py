"""DynamoDB tables.

``is_active`` is activity-based: consumed read or write capacity seen in CloudWatch during the
lookback window. Last activity is the newer of the two.
"""

from __future__ import annotations

from typing import Any

from src.aws_inventory.cloudwatch import MetricQuery, latest_activity
from src.aws_inventory.collectors.base import register
from src.aws_inventory.model import Resource, dep, deps, iso, tags_to_dict
from src.aws_inventory.session import Context

SERVICE = "dynamodb"


@register(SERVICE)
def collect(ctx: Context, region: str) -> list[Resource]:
    """List DynamoDB tables in one region."""
    client = ctx.client(SERVICE, region)
    names = list(ctx.paginate(SERVICE, region, "list_tables", "TableNames"))
    resources = [r for r in ctx.map(lambda n: _describe(ctx, client, region, n), names) if r]

    queries: dict[str, MetricQuery] = {}
    for resource in resources:
        for metric in ("ConsumedReadCapacityUnits", "ConsumedWriteCapacityUnits"):
            queries[f"{resource.id}|{metric}"] = MetricQuery(
                "AWS/DynamoDB", metric, {"TableName": resource.id}
            )
    activity = latest_activity(ctx, SERVICE, region, queries)

    for resource in resources:
        observed = [
            key
            for key in (
                f"{resource.id}|ConsumedReadCapacityUnits",
                f"{resource.id}|ConsumedWriteCapacityUnits",
            )
            if key in activity
        ]
        if not observed:
            continue
        values = [activity[key] for key in observed if activity[key]]
        resource.last_activity = max(values) if values else None
        resource.last_activity_source = "cloudwatch:ConsumedRead/WriteCapacityUnits"
        resource.is_active = bool(values)
    return resources


def _describe(ctx: Context, client: Any, region: str, name: str) -> Resource | None:
    table = ctx.safe(
        SERVICE,
        region,
        f"DescribeTable:{name}",
        lambda: client.describe_table(TableName=name)["Table"],
    )
    if not table:
        return None
    arn = table["TableArn"]
    tags = ctx.safe(
        SERVICE,
        region,
        f"ListTagsOfResource:{name}",
        lambda: client.list_tags_of_resource(ResourceArn=arn).get("Tags", []),
        [],
    )
    return Resource(
        service=SERVICE,
        type="table",
        id=name,
        arn=arn,
        region=region,
        name=name,
        status=table.get("TableStatus"),
        created_at=iso(table.get("CreationDateTime")),
        tags=tags_to_dict(tags),
        metadata={
            "item_count": table.get("ItemCount"),
            "size_bytes": table.get("TableSizeBytes"),
            "billing_mode": (table.get("BillingModeSummary") or {}).get(
                "BillingMode", "PROVISIONED"
            ),
            "table_class": (table.get("TableClassSummary") or {}).get("TableClass"),
            "global_secondary_indexes": [
                g["IndexName"] for g in table.get("GlobalSecondaryIndexes", [])
            ],
            "stream_enabled": (table.get("StreamSpecification") or {}).get("StreamEnabled", False),
            "deletion_protection": table.get("DeletionProtectionEnabled"),
        },
        dependencies=deps(
            dep("kms-key", (table.get("SSEDescription") or {}).get("KMSMasterKeyArn"), "kms"),
            dep("stream", table.get("LatestStreamArn"), SERVICE),
        ),
    )

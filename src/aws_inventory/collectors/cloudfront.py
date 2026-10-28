"""CloudFront distributions (global service, metrics live in us-east-1).

Active when the distribution is enabled. Last activity is the newest day with ``Requests``.
"""

from __future__ import annotations

from typing import Any

from src.aws_inventory.cloudwatch import MetricQuery, apply_activity, latest_activity
from src.aws_inventory.collectors.base import register
from src.aws_inventory.model import Resource, dep, deps, iso, tags_to_dict
from src.aws_inventory.session import Context

SERVICE = "cloudfront"


@register(SERVICE, scope="global")
def collect(ctx: Context, region: str) -> list[Resource]:
    """List CloudFront distributions once for the account."""
    client = ctx.client(SERVICE, region)
    items = []
    for page in client.get_paginator("list_distributions").paginate():
        items.extend((page.get("DistributionList") or {}).get("Items", []))

    resources = ctx.map(lambda item: _distribution(ctx, client, region, item), items)

    activity = latest_activity(
        ctx,
        SERVICE,
        region,
        {
            r.id: MetricQuery(
                "AWS/CloudFront", "Requests", {"DistributionId": r.id, "Region": "Global"}
            )
            for r in resources
        },
    )
    for resource in resources:
        resource.last_activity, resource.last_activity_source, _ = apply_activity(
            activity, resource.id, "cloudwatch:Requests"
        )
    return resources


def _distribution(ctx: Context, client: Any, region: str, item: dict[str, Any]) -> Resource:
    arn = item["ARN"]
    tags = ctx.safe(
        SERVICE,
        region,
        f"ListTagsForResource:{item['Id']}",
        lambda: client.list_tags_for_resource(Resource=arn)["Tags"]["Items"],
        [],
    )
    origins = (item.get("Origins") or {}).get("Items", [])
    certificate = (item.get("ViewerCertificate") or {}).get("ACMCertificateArn")
    return Resource(
        service=SERVICE,
        type="distribution",
        id=item["Id"],
        arn=arn,
        region="global",
        name=item.get("DomainName"),
        status=item.get("Status"),
        is_active=bool(item.get("Enabled")),
        last_activity=None,
        tags=tags_to_dict(tags),
        metadata={
            "domain_name": item.get("DomainName"),
            "aliases": (item.get("Aliases") or {}).get("Items", []),
            "enabled": item.get("Enabled"),
            "price_class": item.get("PriceClass"),
            "http_version": item.get("HttpVersion"),
            "last_modified": iso(item.get("LastModifiedTime")),
            "origins": [o.get("DomainName") for o in origins],
            "comment": item.get("Comment") or None,
        },
        dependencies=deps(
            *[
                dep("origin", o.get("DomainName"), _origin_service(o.get("DomainName", "")))
                for o in origins
            ],
            dep("web-acl", item.get("WebACLId") or None, "wafv2"),
            dep("certificate", certificate, "acm"),
        ),
    )


def _origin_service(domain: str) -> str | None:
    if ".s3." in domain or domain.endswith(".s3.amazonaws.com"):
        return "s3"
    if ".elb.amazonaws.com" in domain:
        return "elbv2"
    if ".execute-api." in domain:
        return "apigateway"
    return None

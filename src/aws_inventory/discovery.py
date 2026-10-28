"""Generic discovery so services without a dedicated collector are not silently missed.

Two read-only sources feed ``status=unknown`` stub resources:
- Resource Groups Tagging API, per region (sees tagged or previously tagged resources).
- Resource Explorer 2, if the account has an aggregator index (sees untagged ones too).
Deep collectors replace the stubs for the services they cover (see ``runner``).
"""

from __future__ import annotations

import logging

from src.aws_inventory.model import Resource, iso, parse_arn
from src.aws_inventory.session import Context

logger = logging.getLogger(__name__)


def _stub(arn: str, region: str, source: str, tags: dict[str, str] | None = None) -> Resource:
    service, arn_region, rtype, rid = parse_arn(arn)
    return Resource(
        service=service,
        type=rtype,
        id=rid,
        arn=arn,
        region=arn_region or region or "global",
        status="unknown",
        tags=tags or {},
        metadata={"discovered_via": source},
    )


def discover_tagged(ctx: Context, region: str) -> list[Resource]:
    """Return stubs for every resource the Tagging API knows about in ``region``."""
    stubs = []
    for mapping in ctx.paginate(
        "resourcegroupstaggingapi",
        region,
        "get_resources",
        "ResourceTagMappingList",
        ResourcesPerPage=100,
    ):
        tags = {t["Key"]: t["Value"] for t in mapping.get("Tags", [])}
        stubs.append(_stub(mapping["ResourceARN"], region, "resourcegroupstaggingapi", tags))
    return stubs


def discover_resource_explorer(ctx: Context) -> list[Resource]:
    """Return stubs from the Resource Explorer aggregator index; empty when it is not set up."""
    try:
        client = ctx.client("resource-explorer-2", ctx.global_region)
        indexes = client.list_indexes(Type="AGGREGATOR").get("Indexes", [])
        if not indexes:
            logger.info("Resource Explorer: no aggregator index, skipping")
            return []
        aggregator_region = indexes[0]["Region"]
        client = ctx.client("resource-explorer-2", aggregator_region)
        view_arn = client.get_default_view().get("ViewArn")
        if not view_arn:
            logger.info("Resource Explorer: no default view, skipping")
            return []
        stubs = []
        for page in client.get_paginator("search").paginate(QueryString="*", ViewArn=view_arn):
            for item in page.get("Resources", []):
                stub = _stub(item["Arn"], item.get("Region", ""), "resource-explorer-2")
                stub.metadata["last_reported_at"] = iso(item.get("LastReportedAt"))
                stubs.append(stub)
        return stubs
    except Exception as exc:  # noqa: BLE001 - optional source, usually just not enabled
        logger.info("Resource Explorer unavailable (%s), skipping", exc)
        return []

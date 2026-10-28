"""Application/Network load balancers and their target groups.

Load balancers are active when their state is ``active``. Last activity is the newest day with
``RequestCount`` (ALB) or ``NewFlowCount`` (NLB). A target group is active when it is attached
to a load balancer; its registered targets become dependencies.
"""

from __future__ import annotations

from typing import Any

from src.aws_inventory.cloudwatch import MetricQuery, apply_activity, latest_activity
from src.aws_inventory.collectors.base import register
from src.aws_inventory.model import Resource, dep, deps, iso, tags_to_dict
from src.aws_inventory.session import Context

SERVICE = "elbv2"
TAG_BATCH = 20


@register(SERVICE)
def collect(ctx: Context, region: str) -> list[Resource]:
    """List load balancers and target groups in one region."""
    client = ctx.client(SERVICE, region)
    balancers = list(ctx.paginate(SERVICE, region, "describe_load_balancers", "LoadBalancers"))
    groups = list(ctx.paginate(SERVICE, region, "describe_target_groups", "TargetGroups"))
    tags = _tags(
        ctx,
        client,
        region,
        [b["LoadBalancerArn"] for b in balancers] + [g["TargetGroupArn"] for g in groups],
    )

    resources: list[Resource] = []
    queries: dict[str, MetricQuery] = {}
    for item in balancers:
        arn = item["LoadBalancerArn"]
        kind = item.get("Type", "application")
        dimension = arn.split("loadbalancer/", 1)[-1]
        if kind == "application":
            queries[arn] = MetricQuery(
                "AWS/ApplicationELB", "RequestCount", {"LoadBalancer": dimension}
            )
        elif kind == "network":
            queries[arn] = MetricQuery(
                "AWS/NetworkELB", "NewFlowCount", {"LoadBalancer": dimension}
            )
        resources.append(
            Resource(
                service=SERVICE,
                type=f"{kind}-load-balancer",
                id=item["LoadBalancerName"],
                arn=arn,
                region=region,
                name=item["LoadBalancerName"],
                status=(item.get("State") or {}).get("Code"),
                is_active=(item.get("State") or {}).get("Code") == "active",
                created_at=iso(item.get("CreatedTime")),
                tags=tags.get(arn, {}),
                metadata={
                    "scheme": item.get("Scheme"),
                    "ip_address_type": item.get("IpAddressType"),
                    "dns_name": item.get("DNSName"),
                    "availability_zones": [
                        z.get("ZoneName") for z in item.get("AvailabilityZones", [])
                    ],
                },
                dependencies=deps(
                    dep(
                        "in-vpc",
                        item.get("VpcId") and ctx.arn("ec2", region, f"vpc/{item['VpcId']}"),
                        "ec2",
                    ),
                    *[
                        dep("in-subnet", ctx.arn("ec2", region, f"subnet/{z['SubnetId']}"), "ec2")
                        for z in item.get("AvailabilityZones", [])
                        if z.get("SubnetId")
                    ],
                    *[
                        dep("security-group", ctx.arn("ec2", region, f"security-group/{s}"), "ec2")
                        for s in item.get("SecurityGroups", [])
                    ],
                ),
            )
        )

    activity = latest_activity(ctx, SERVICE, region, queries)
    for resource in resources:
        resource.last_activity, resource.last_activity_source, _ = apply_activity(
            activity, resource.arn or "", "cloudwatch:RequestCount/NewFlowCount"
        )

    resources.extend(ctx.map(lambda g: _target_group(ctx, client, region, g, tags), groups))
    return resources


def _tags(ctx: Context, client: Any, region: str, arns: list[str]) -> dict[str, dict[str, str]]:
    result: dict[str, dict[str, str]] = {}
    for start in range(0, len(arns), TAG_BATCH):
        batch = arns[start : start + TAG_BATCH]
        response = ctx.safe(
            SERVICE,
            region,
            "DescribeTags",
            lambda batch=batch: client.describe_tags(ResourceArns=batch),
            {},
        )
        for description in (response or {}).get("TagDescriptions", []):
            result[description["ResourceArn"]] = tags_to_dict(description.get("Tags"))
    return result


def _target_group(
    ctx: Context, client: Any, region: str, group: dict[str, Any], tags: dict[str, dict[str, str]]
) -> Resource:
    arn = group["TargetGroupArn"]
    health = (
        ctx.safe(
            SERVICE,
            region,
            f"DescribeTargetHealth:{group['TargetGroupName']}",
            lambda: client.describe_target_health(TargetGroupArn=arn).get(
                "TargetHealthDescriptions", []
            ),
            [],
        )
        or []
    )
    attached = group.get("LoadBalancerArns", [])
    target_type = group.get("TargetType")
    return Resource(
        service=SERVICE,
        type="target-group",
        id=group["TargetGroupName"],
        arn=arn,
        region=region,
        name=group["TargetGroupName"],
        status="attached" if attached else "unattached",
        is_active=bool(attached),
        tags=tags.get(arn, {}),
        metadata={
            "protocol": group.get("Protocol"),
            "port": group.get("Port"),
            "target_type": target_type,
            "targets": len(health),
            "healthy_targets": sum(
                1 for h in health if (h.get("TargetHealth") or {}).get("State") == "healthy"
            ),
            "health_check_path": group.get("HealthCheckPath"),
        },
        dependencies=deps(
            dep(
                "in-vpc",
                group.get("VpcId") and ctx.arn("ec2", region, f"vpc/{group['VpcId']}"),
                "ec2",
            ),
            *[dep("attached-to-load-balancer", lb, SERVICE) for lb in attached],
            *[
                dep(
                    "target",
                    ctx.arn("ec2", region, f"instance/{h['Target']['Id']}")
                    if target_type == "instance"
                    else (h["Target"]["Id"] if h["Target"]["Id"].startswith("arn:") else None),
                )
                for h in health
            ],
        ),
    )

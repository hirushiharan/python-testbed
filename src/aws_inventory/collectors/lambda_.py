"""Lambda functions.

``is_active`` is activity-based: true when CloudWatch shows an ``Invocations`` datapoint in
the lookback window. Environment variable *values* are never read into the report.
"""

from __future__ import annotations

from typing import Any

from src.aws_inventory.cloudwatch import MetricQuery, apply_activity, latest_activity
from src.aws_inventory.collectors.base import register
from src.aws_inventory.model import Resource, dep, deps, tags_to_dict
from src.aws_inventory.session import Context
from src.aws_inventory.telemetry import Progress

SERVICE = "lambda"


@register(SERVICE)
def collect(ctx: Context, region: str) -> list[Resource]:
    """List Lambda functions in one region."""
    functions = list(ctx.paginate(SERVICE, region, "list_functions", "Functions"))
    if not functions:
        return []

    mappings = (
        ctx.safe(
            SERVICE,
            region,
            "ListEventSourceMappings",
            lambda: list(
                ctx.paginate(SERVICE, region, "list_event_source_mappings", "EventSourceMappings")
            ),
            [],
        )
        or []
    )
    sources: dict[str, list[dict[str, Any]]] = {}
    for mapping in mappings:
        base = ":".join(mapping["FunctionArn"].split(":")[:7])
        sources.setdefault(base, []).append(mapping)

    client = ctx.client(SERVICE, region)
    progress = Progress(f"lambda functions ({region})", len(functions), every=50)
    resources = ctx.map(
        progress.wrap(lambda fn: _describe(ctx, client, region, fn, sources)), functions
    )

    activity = latest_activity(
        ctx,
        SERVICE,
        region,
        {r.id: MetricQuery("AWS/Lambda", "Invocations", {"FunctionName": r.id}) for r in resources},
    )
    for resource in resources:
        last, source, active = apply_activity(activity, resource.id, "cloudwatch:Invocations")
        resource.last_activity, resource.last_activity_source, resource.is_active = (
            last,
            source,
            active,
        )
    return resources


def _describe(
    ctx: Context,
    client: Any,
    region: str,
    item: dict[str, Any],
    sources: dict[str, list[dict[str, Any]]],
) -> Resource:
    arn = item["FunctionArn"]
    tags = ctx.safe(
        SERVICE,
        region,
        f"ListTags:{item['FunctionName']}",
        lambda: client.list_tags(Resource=arn).get("Tags", {}),
        {},
    )
    vpc = item.get("VpcConfig") or {}
    mappings = sources.get(arn, [])
    return Resource(
        service=SERVICE,
        type="function",
        id=item["FunctionName"],
        arn=arn,
        region=region,
        name=item["FunctionName"],
        status=item.get("State", "Active"),
        tags=tags_to_dict(tags),
        metadata={
            "runtime": item.get("Runtime"),
            "handler": item.get("Handler"),
            "package_type": item.get("PackageType"),
            "architectures": item.get("Architectures"),
            "memory_mb": item.get("MemorySize"),
            "timeout_s": item.get("Timeout"),
            "code_size_bytes": item.get("CodeSize"),
            "last_modified": item.get("LastModified"),
            "state_reason": item.get("StateReason"),
            "environment_variable_count": len((item.get("Environment") or {}).get("Variables", {})),
            "event_source_mappings": [
                {"source": m.get("EventSourceArn"), "state": m.get("State")} for m in mappings
            ],
        },
        dependencies=deps(
            dep("execution-role", item.get("Role"), "iam"),
            dep(
                "in-vpc", vpc.get("VpcId") and ctx.arn("ec2", region, f"vpc/{vpc['VpcId']}"), "ec2"
            ),
            *[
                dep("in-subnet", ctx.arn("ec2", region, f"subnet/{s}"), "ec2")
                for s in vpc.get("SubnetIds", [])
            ],
            *[
                dep("security-group", ctx.arn("ec2", region, f"security-group/{s}"), "ec2")
                for s in vpc.get("SecurityGroupIds", [])
            ],
            *[dep("layer", layer["Arn"], SERVICE) for layer in item.get("Layers", [])],
            dep("dead-letter-target", (item.get("DeadLetterConfig") or {}).get("TargetArn")),
            dep("kms-key", item.get("KMSKeyArn"), "kms"),
            *[dep("triggered-by", m.get("EventSourceArn")) for m in mappings],
        ),
    )

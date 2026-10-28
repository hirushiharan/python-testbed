"""API Gateway: REST APIs (v1) and HTTP/WebSocket APIs (v2).

``is_active`` is activity-based: a ``Count`` datapoint in the lookback window. REST API
integrations are not walked (one call per method), so only v2 APIs list Lambda dependencies.
"""

from __future__ import annotations

from typing import Any, Iterator

from src.aws_inventory.cloudwatch import MetricQuery, apply_activity, latest_activity
from src.aws_inventory.collectors.base import register
from src.aws_inventory.model import Resource, dep, deps, iso, tags_to_dict
from src.aws_inventory.session import Context

SERVICE = "apigateway"


@register(SERVICE)
def collect(ctx: Context, region: str) -> list[Resource]:
    """List REST and HTTP/WebSocket APIs in one region."""
    resources: list[Resource] = []
    queries: dict[str, MetricQuery] = {}

    for operation, fn in (("GetRestApis", _rest_apis), ("GetApis", _v2_apis)):
        found = ctx.safe(SERVICE, region, operation, lambda fn=fn: fn(ctx, region), []) or []
        for resource, query in found:
            resources.append(resource)
            queries[resource.arn or resource.id] = query

    activity = latest_activity(ctx, SERVICE, region, queries)
    for resource in resources:
        last, source, active = apply_activity(
            activity, resource.arn or resource.id, "cloudwatch:Count"
        )
        resource.last_activity, resource.last_activity_source = last, source
        if resource.is_active is not False:
            resource.is_active = active
    return resources


def _rest_apis(ctx: Context, region: str) -> list[tuple[Resource, MetricQuery]]:
    client = ctx.client(SERVICE, region)
    apis = list(ctx.paginate(SERVICE, region, "get_rest_apis", "items"))

    def describe(api: dict[str, Any]) -> tuple[Resource, MetricQuery]:
        stages = (
            ctx.safe(
                SERVICE,
                region,
                f"GetStages:{api['name']}",
                lambda: client.get_stages(restApiId=api["id"]).get("item", []),
                [],
            )
            or []
        )
        resource = Resource(
            service=SERVICE,
            type="rest-api",
            id=api["id"],
            arn=f"arn:{ctx.partition}:apigateway:{region}::/restapis/{api['id']}",
            region=region,
            name=api.get("name"),
            status="deployed" if stages else "no-stage",
            is_active=None if stages else False,
            created_at=iso(api.get("createdDate")),
            tags=tags_to_dict(api.get("tags")),
            metadata={
                "protocol": "REST",
                "endpoint_types": (api.get("endpointConfiguration") or {}).get("types"),
                "stages": [s.get("stageName") for s in stages],
                "description": api.get("description") or None,
            },
        )
        return resource, MetricQuery("AWS/ApiGateway", "Count", {"ApiName": api.get("name", "")})

    return ctx.map(describe, apis)


def _v2_apis(ctx: Context, region: str) -> list[tuple[Resource, MetricQuery]]:
    client = ctx.client("apigatewayv2", region)

    def pages(operation: str, key: str, **kwargs: Any) -> Iterator[dict[str, Any]]:
        token = None
        while True:
            response = getattr(client, operation)(
                **kwargs, **({"NextToken": token} if token else {})
            )
            yield from response.get(key, [])
            token = response.get("NextToken")
            if not token:
                return

    def describe(api: dict[str, Any]) -> tuple[Resource, MetricQuery]:
        integrations = (
            ctx.safe(
                SERVICE,
                region,
                f"GetIntegrations:{api['Name']}",
                lambda: list(pages("get_integrations", "Items", ApiId=api["ApiId"])),
                [],
            )
            or []
        )
        resource = Resource(
            service=SERVICE,
            type=f"{api.get('ProtocolType', 'HTTP').lower()}-api",
            id=api["ApiId"],
            arn=f"arn:{ctx.partition}:apigateway:{region}::/apis/{api['ApiId']}",
            region=region,
            name=api.get("Name"),
            status="deployed",
            created_at=iso(api.get("CreatedDate")),
            tags=tags_to_dict(api.get("Tags")),
            metadata={
                "protocol": api.get("ProtocolType"),
                "endpoint": api.get("ApiEndpoint"),
                "disable_execute_api_endpoint": api.get("DisableExecuteApiEndpoint"),
            },
            dependencies=deps(
                *[
                    dep("integration", i.get("IntegrationUri"))
                    for i in integrations
                    if str(i.get("IntegrationUri", "")).startswith("arn:")
                ]
            ),
        )
        return resource, MetricQuery("AWS/ApiGateway", "Count", {"ApiId": api["ApiId"]})

    apis = list(pages("get_apis", "Items"))
    return ctx.map(describe, apis)

"""Data model for the AWS inventory and small helpers shared by every collector."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from typing import Any

# ARN service prefixes that differ from the collector/service key used in the report.
ARN_SERVICE_ALIASES = {
    "elasticloadbalancing": "elbv2",
    "execute-api": "apigateway",
}

ACTIVITY_WINDOW_DAYS = 30


def iso(value: datetime | str | int | float | None) -> str | None:
    """Normalise a timestamp to a UTC ISO-8601 string (sortable as plain text)."""
    if value is None or value == "":
        return None
    if isinstance(value, (int, float)):
        value = datetime.fromtimestamp(value, tz=timezone.utc)
    if isinstance(value, str):
        return value
    if value.tzinfo is None:
        value = value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc).isoformat()


def tags_to_dict(tags: Any) -> dict[str, str]:
    """Convert the many AWS tag shapes (Key/Value, key/value, plain dict) to a dict."""
    if not tags:
        return {}
    if isinstance(tags, dict):
        return {str(k): str(v) for k, v in tags.items()}
    result: dict[str, str] = {}
    for tag in tags:
        key = tag.get("Key", tag.get("key"))
        if key is not None:
            result[str(key)] = str(tag.get("Value", tag.get("value", "")))
    return result


def parse_arn(arn: str) -> tuple[str, str, str, str]:
    """Split an ARN into (service, region, resource_type, resource_id)."""
    parts = arn.split(":", 5)
    if len(parts) < 6:
        return "unknown", "", "resource", arn
    service, region, resource = parts[2], parts[3], parts[5]
    service = ARN_SERVICE_ALIASES.get(service, service)
    for separator in ("/", ":"):
        if separator in resource:
            rtype, rid = resource.split(separator, 1)
            return service, region, rtype, rid
    return service, region, "resource", resource


@dataclass
class Dependency:
    """A directed edge from a resource to something it relies on."""

    relation: str
    target: str
    target_service: str | None = None


def dep(relation: str, target: str | None, service: str | None = None) -> Dependency | None:
    """Build a dependency, inferring the target service from ARNs; None if target is empty."""
    if not target:
        return None
    if service is None and target.startswith("arn:"):
        service = parse_arn(target)[0]
    return Dependency(relation=relation, target=target, target_service=service)


def deps(*items: Dependency | None) -> list[Dependency]:
    """Drop the None entries produced by ``dep`` for missing targets."""
    return [item for item in items if item is not None]


@dataclass
class Resource:
    """One inventoried AWS resource."""

    service: str
    type: str
    id: str
    arn: str | None
    region: str
    name: str | None = None
    status: str | None = None
    is_active: bool | None = None
    created_at: str | None = None
    last_activity: str | None = None
    last_activity_source: str | None = None
    tags: dict[str, str] = field(default_factory=dict)
    metadata: dict[str, Any] = field(default_factory=dict)
    dependencies: list[Dependency] = field(default_factory=list)


@dataclass
class InventoryError:
    """A non-fatal failure (typically AccessDenied) hit while collecting."""

    service: str
    region: str
    operation: str
    message: str


@dataclass
class Inventory:
    """Everything collected for one account."""

    account: dict[str, Any]
    resources: list[Resource] = field(default_factory=list)
    errors: list[InventoryError] = field(default_factory=list)
    cost: dict[str, Any] = field(default_factory=dict)
    services_scanned: list[str] = field(default_factory=list)

    def services(self) -> dict[str, list[Resource]]:
        """Group resources by service, sorted by service name."""
        grouped: dict[str, list[Resource]] = {}
        for resource in self.resources:
            grouped.setdefault(resource.service, []).append(resource)
        return {name: grouped[name] for name in sorted(grouped)}

    def edges(self) -> list[dict[str, Any]]:
        """Flatten every resource's dependencies into one edge list."""
        return [
            {
                "source": resource.arn or resource.id,
                "source_service": resource.service,
                "source_type": resource.type,
                "relation": dependency.relation,
                "target": dependency.target,
                "target_service": dependency.target_service,
            }
            for resource in self.resources
            for dependency in resource.dependencies
        ]

    def service_summary(self, service: str, resources: list[Resource]) -> dict[str, Any]:
        """Roll one service's resources up into the summary block."""
        by_region: dict[str, int] = {}
        by_status: dict[str, int] = {}
        for resource in resources:
            by_region[resource.region] = by_region.get(resource.region, 0) + 1
            status = resource.status or "unknown"
            by_status[status] = by_status.get(status, 0) + 1
        activities = [r.last_activity for r in resources if r.last_activity]
        cost = self.cost.get("by_service", {}).get(service)
        return {
            "resource_count": len(resources),
            "active_count": sum(1 for r in resources if r.is_active is True),
            "inactive_count": sum(1 for r in resources if r.is_active is False),
            "unknown_activity_count": sum(1 for r in resources if r.is_active is None),
            "by_region": dict(sorted(by_region.items())),
            "status_counts": dict(sorted(by_status.items())),
            "last_activity": max(activities) if activities else None,
            "cost_90d": cost["total"] if cost else None,
        }

    def coverage(self) -> dict[str, Any]:
        """Report gaps: billed services we found nothing for, and collector errors."""
        collected = {r.service for r in self.resources}
        unmapped = self.cost.get("unmapped", {})
        return {
            "billed_without_collector": [
                {"cost_service": name, "cost_90d": total}
                for name, total in sorted(unmapped.items())
            ],
            "billed_without_resources": sorted(
                service
                for service in self.cost.get("by_service", {})
                if service not in collected and service in self.services_scanned
            ),
            "errors": [asdict(error) for error in self.errors],
        }

    def to_dict(self) -> dict[str, Any]:
        """Serialise to the documented JSON structure."""
        services = {
            name: {
                "summary": self.service_summary(name, resources),
                "resources": [asdict(resource) for resource in resources],
            }
            for name, resources in self.services().items()
        }
        return {
            "account": self.account,
            "notes": [
                f"last_activity looks back {ACTIVITY_WINDOW_DAYS} days via CloudWatch where noted "
                "in last_activity_source; null means no activity observed or no signal available.",
                "is_active is state-based for resources with a lifecycle state (EC2, RDS, ECS, "
                "EKS, load balancers, volumes, ...) and activity-based for the rest (Lambda, SQS, "
                "SNS, DynamoDB, API Gateway, IAM); null means it could not be determined.",
                "dependencies are derived from each resource's describe response and are not "
                "a complete cross-service graph.",
            ],
            "services": services,
            "dependencies": self.edges(),
            "cost": self.cost,
            "coverage": self.coverage(),
        }

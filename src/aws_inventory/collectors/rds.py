"""RDS DB instances and Aurora/Multi-AZ clusters.

Active when the status is ``available``. Last activity is the newest day with a non-zero
``DatabaseConnections`` maximum in CloudWatch.
"""

from __future__ import annotations

from src.aws_inventory.cloudwatch import MetricQuery, apply_activity, latest_activity
from src.aws_inventory.collectors.base import register
from src.aws_inventory.model import Resource, dep, deps, iso, tags_to_dict
from src.aws_inventory.session import Context

SERVICE = "rds"


@register(SERVICE)
def collect(ctx: Context, region: str) -> list[Resource]:
    """List RDS instances and clusters in one region."""
    resources: list[Resource] = []
    for operation, fn in (("DescribeDBInstances", _instances), ("DescribeDBClusters", _clusters)):
        resources.extend(
            ctx.safe(SERVICE, region, operation, lambda fn=fn: fn(ctx, region), []) or []
        )
    return resources


def _instances(ctx: Context, region: str) -> list[Resource]:
    resources = []
    for item in ctx.paginate(SERVICE, region, "describe_db_instances", "DBInstances"):
        identifier = item["DBInstanceIdentifier"]
        subnet_group = item.get("DBSubnetGroup") or {}
        resources.append(
            Resource(
                service=SERVICE,
                type="db-instance",
                id=identifier,
                arn=item["DBInstanceArn"],
                region=region,
                name=identifier,
                status=item.get("DBInstanceStatus"),
                is_active=item.get("DBInstanceStatus") == "available",
                created_at=iso(item.get("InstanceCreateTime")),
                tags=tags_to_dict(item.get("TagList")),
                metadata={
                    "engine": item.get("Engine"),
                    "engine_version": item.get("EngineVersion"),
                    "instance_class": item.get("DBInstanceClass"),
                    "allocated_storage_gib": item.get("AllocatedStorage"),
                    "storage_type": item.get("StorageType"),
                    "multi_az": item.get("MultiAZ"),
                    "publicly_accessible": item.get("PubliclyAccessible"),
                    "storage_encrypted": item.get("StorageEncrypted"),
                    "backup_retention_days": item.get("BackupRetentionPeriod"),
                    "availability_zone": item.get("AvailabilityZone"),
                    "endpoint": (item.get("Endpoint") or {}).get("Address"),
                },
                dependencies=deps(
                    dep(
                        "in-vpc",
                        subnet_group.get("VpcId")
                        and ctx.arn("ec2", region, f"vpc/{subnet_group['VpcId']}"),
                        "ec2",
                    ),
                    dep("subnet-group", subnet_group.get("DBSubnetGroupName"), SERVICE),
                    *[
                        dep(
                            "security-group",
                            ctx.arn("ec2", region, f"security-group/{sg['VpcSecurityGroupId']}"),
                            "ec2",
                        )
                        for sg in item.get("VpcSecurityGroups", [])
                    ],
                    *[
                        dep("parameter-group", pg["DBParameterGroupName"], SERVICE)
                        for pg in item.get("DBParameterGroups", [])
                    ],
                    dep("kms-key", item.get("KmsKeyId"), "kms"),
                    dep("member-of-cluster", item.get("DBClusterIdentifier"), SERVICE),
                    dep("replica-of", item.get("ReadReplicaSourceDBInstanceIdentifier"), SERVICE),
                    dep("monitoring-role", item.get("MonitoringRoleArn"), "iam"),
                ),
            )
        )

    queries = {
        r.id: MetricQuery(
            "AWS/RDS", "DatabaseConnections", {"DBInstanceIdentifier": r.id}, "Maximum"
        )
        for r in resources
        if r.status == "available"
    }
    activity = latest_activity(ctx, SERVICE, region, queries)
    for resource in resources:
        resource.last_activity, resource.last_activity_source, _ = apply_activity(
            activity, resource.id, "cloudwatch:DatabaseConnections"
        )
    return resources


def _clusters(ctx: Context, region: str) -> list[Resource]:
    resources = []
    for item in ctx.paginate(SERVICE, region, "describe_db_clusters", "DBClusters"):
        identifier = item["DBClusterIdentifier"]
        resources.append(
            Resource(
                service=SERVICE,
                type="db-cluster",
                id=identifier,
                arn=item["DBClusterArn"],
                region=region,
                name=identifier,
                status=item.get("Status"),
                is_active=item.get("Status") == "available",
                created_at=iso(item.get("ClusterCreateTime")),
                tags=tags_to_dict(item.get("TagList")),
                metadata={
                    "engine": item.get("Engine"),
                    "engine_version": item.get("EngineVersion"),
                    "engine_mode": item.get("EngineMode"),
                    "multi_az": item.get("MultiAZ"),
                    "storage_encrypted": item.get("StorageEncrypted"),
                    "members": [
                        m["DBInstanceIdentifier"] for m in item.get("DBClusterMembers", [])
                    ],
                    "endpoint": item.get("Endpoint"),
                },
                dependencies=deps(
                    dep("subnet-group", item.get("DBSubnetGroup"), SERVICE),
                    *[
                        dep(
                            "security-group",
                            ctx.arn("ec2", region, f"security-group/{sg['VpcSecurityGroupId']}"),
                            "ec2",
                        )
                        for sg in item.get("VpcSecurityGroups", [])
                    ],
                    dep("kms-key", item.get("KmsKeyId"), "kms"),
                ),
            )
        )
    return resources

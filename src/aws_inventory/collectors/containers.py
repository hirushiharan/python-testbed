"""ECS (clusters, services) and EKS (clusters, managed node groups).

State-based activity: ECS clusters are active with running tasks/services, ECS services with
running tasks, EKS clusters/node groups when ``ACTIVE``. ECS ``last_activity`` is the latest
deployment update (a lifecycle signal, not traffic).
"""

from __future__ import annotations

from typing import Any

from src.aws_inventory.collectors.base import register
from src.aws_inventory.model import Resource, dep, deps, iso, tags_to_dict
from src.aws_inventory.session import Context


def _chunks(items: list[Any], size: int) -> list[list[Any]]:
    return [items[i : i + size] for i in range(0, len(items), size)]


@register("ecs")
def collect_ecs(ctx: Context, region: str) -> list[Resource]:
    """List ECS clusters and their services in one region."""
    ecs = ctx.client("ecs", region)
    cluster_arns = list(ctx.paginate("ecs", region, "list_clusters", "clusterArns"))
    resources: list[Resource] = []

    for chunk in _chunks(cluster_arns, 100):
        for cluster in ecs.describe_clusters(clusters=chunk, include=["TAGS", "STATISTICS"]).get(
            "clusters", []
        ):
            running = cluster.get("runningTasksCount", 0)
            services = cluster.get("activeServicesCount", 0)
            resources.append(
                Resource(
                    service="ecs",
                    type="cluster",
                    id=cluster["clusterName"],
                    arn=cluster["clusterArn"],
                    region=region,
                    name=cluster["clusterName"],
                    status=cluster.get("status"),
                    is_active=cluster.get("status") == "ACTIVE" and (running > 0 or services > 0),
                    tags=tags_to_dict(cluster.get("tags")),
                    metadata={
                        "running_tasks": running,
                        "pending_tasks": cluster.get("pendingTasksCount"),
                        "active_services": services,
                        "container_instances": cluster.get("registeredContainerInstancesCount"),
                    },
                )
            )

    for cluster_arn in cluster_arns:
        resources.extend(
            ctx.safe(
                "ecs",
                region,
                f"ListServices:{cluster_arn}",
                lambda c=cluster_arn: _ecs_services(ctx, ecs, region, c),
                [],
            )
            or []
        )
    return resources


def _ecs_services(ctx: Context, ecs: Any, region: str, cluster_arn: str) -> list[Resource]:
    service_arns = list(
        ctx.paginate("ecs", region, "list_services", "serviceArns", cluster=cluster_arn)
    )
    resources = []
    for chunk in _chunks(service_arns, 10):
        response = ecs.describe_services(cluster=cluster_arn, services=chunk, include=["TAGS"])
        for item in response.get("services", []):
            awsvpc = (item.get("networkConfiguration") or {}).get("awsvpcConfiguration") or {}
            deployments = [
                iso(d.get("updatedAt")) for d in item.get("deployments", []) if d.get("updatedAt")
            ]
            running = item.get("runningCount", 0)
            resources.append(
                Resource(
                    service="ecs",
                    type="service",
                    id=item["serviceName"],
                    arn=item["serviceArn"],
                    region=region,
                    name=item["serviceName"],
                    status=item.get("status"),
                    is_active=item.get("status") == "ACTIVE" and running > 0,
                    created_at=iso(item.get("createdAt")),
                    last_activity=max(deployments) if deployments else None,
                    last_activity_source="ecs:LastDeployment",
                    tags=tags_to_dict(item.get("tags")),
                    metadata={
                        "cluster": cluster_arn,
                        "launch_type": item.get("launchType"),
                        "desired_count": item.get("desiredCount"),
                        "running_count": running,
                        "pending_count": item.get("pendingCount"),
                    },
                    dependencies=deps(
                        dep("in-cluster", cluster_arn, "ecs"),
                        dep("task-definition", item.get("taskDefinition"), "ecs"),
                        dep("service-role", item.get("roleArn"), "iam"),
                        *[
                            dep("load-balancer-target", lb.get("targetGroupArn"), "elbv2")
                            for lb in item.get("loadBalancers", [])
                        ],
                        *[
                            dep("in-subnet", ctx.arn("ec2", region, f"subnet/{s}"), "ec2")
                            for s in awsvpc.get("subnets", [])
                        ],
                        *[
                            dep(
                                "security-group",
                                ctx.arn("ec2", region, f"security-group/{s}"),
                                "ec2",
                            )
                            for s in awsvpc.get("securityGroups", [])
                        ],
                    ),
                )
            )
    return resources


@register("eks")
def collect_eks(ctx: Context, region: str) -> list[Resource]:
    """List EKS clusters and managed node groups in one region."""
    eks = ctx.client("eks", region)
    resources: list[Resource] = []
    for name in ctx.paginate("eks", region, "list_clusters", "clusters"):
        cluster = eks.describe_cluster(name=name)["cluster"]
        vpc = cluster.get("resourcesVpcConfig") or {}
        resources.append(
            Resource(
                service="eks",
                type="cluster",
                id=name,
                arn=cluster["arn"],
                region=region,
                name=name,
                status=cluster.get("status"),
                is_active=cluster.get("status") == "ACTIVE",
                created_at=iso(cluster.get("createdAt")),
                tags=tags_to_dict(cluster.get("tags")),
                metadata={
                    "kubernetes_version": cluster.get("version"),
                    "platform_version": cluster.get("platformVersion"),
                    "endpoint": cluster.get("endpoint"),
                    "public_endpoint": vpc.get("endpointPublicAccess"),
                },
                dependencies=deps(
                    dep("cluster-role", cluster.get("roleArn"), "iam"),
                    dep(
                        "in-vpc",
                        vpc.get("vpcId") and ctx.arn("ec2", region, f"vpc/{vpc['vpcId']}"),
                        "ec2",
                    ),
                    *[
                        dep("in-subnet", ctx.arn("ec2", region, f"subnet/{s}"), "ec2")
                        for s in vpc.get("subnetIds", [])
                    ],
                    *[
                        dep("security-group", ctx.arn("ec2", region, f"security-group/{s}"), "ec2")
                        for s in vpc.get("securityGroupIds", [])
                    ],
                ),
            )
        )
        resources.extend(
            ctx.safe(
                "eks",
                region,
                f"ListNodegroups:{name}",
                lambda n=name: _nodegroups(ctx, eks, region, n, cluster["arn"]),
                [],
            )
            or []
        )
    return resources


def _nodegroups(
    ctx: Context, eks: Any, region: str, cluster: str, cluster_arn: str
) -> list[Resource]:
    resources = []
    for group_name in ctx.paginate(
        "eks", region, "list_nodegroups", "nodegroups", clusterName=cluster
    ):
        group = eks.describe_nodegroup(clusterName=cluster, nodegroupName=group_name)["nodegroup"]
        resources.append(
            Resource(
                service="eks",
                type="nodegroup",
                id=f"{cluster}/{group_name}",
                arn=group["nodegroupArn"],
                region=region,
                name=group_name,
                status=group.get("status"),
                is_active=group.get("status") == "ACTIVE",
                created_at=iso(group.get("createdAt")),
                last_activity=iso(group.get("modifiedAt")),
                last_activity_source="eks:NodegroupModified",
                tags=tags_to_dict(group.get("tags")),
                metadata={
                    "instance_types": group.get("instanceTypes"),
                    "scaling": group.get("scalingConfig"),
                    "ami_type": group.get("amiType"),
                    "capacity_type": group.get("capacityType"),
                },
                dependencies=deps(
                    dep("in-cluster", cluster_arn, "eks"),
                    dep("node-role", group.get("nodeRole"), "iam"),
                    *[
                        dep("in-subnet", ctx.arn("ec2", region, f"subnet/{s}"), "ec2")
                        for s in group.get("subnets", [])
                    ],
                ),
            )
        )
    return resources

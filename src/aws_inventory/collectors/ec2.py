"""EC2 and VPC networking: instances, volumes, Elastic IPs, security groups, VPCs, subnets, NAT.

Status/active: instances are active when ``running``; volumes when ``in-use``; Elastic IPs
when associated; NAT gateways when ``available``. Last activity comes from CloudWatch
``NetworkIn`` (instances) and ``BytesOutToDestination`` (NAT gateways).
"""

from __future__ import annotations

from src.aws_inventory.cloudwatch import MetricQuery, apply_activity, latest_activity
from src.aws_inventory.collectors.base import register
from src.aws_inventory.model import Resource, dep, deps, iso, tags_to_dict
from src.aws_inventory.session import Context

SERVICE = "ec2"


@register(SERVICE)
def collect(ctx: Context, region: str) -> list[Resource]:
    """List EC2/VPC resources in one region."""
    resources: list[Resource] = []
    for operation, fn in (
        ("DescribeInstances", _instances),
        ("DescribeVolumes", _volumes),
        ("DescribeAddresses", _addresses),
        ("DescribeSecurityGroups", _security_groups),
        ("DescribeVpcs", _vpcs),
        ("DescribeSubnets", _subnets),
        ("DescribeNatGateways", _nat_gateways),
    ):
        resources.extend(
            ctx.safe(SERVICE, region, operation, lambda fn=fn: fn(ctx, region), []) or []
        )
    return resources


def _name(tags: dict[str, str], fallback: str) -> str:
    return tags.get("Name") or fallback


def _instances(ctx: Context, region: str) -> list[Resource]:
    resources: list[Resource] = []
    for reservation in ctx.paginate(SERVICE, region, "describe_instances", "Reservations"):
        for item in reservation["Instances"]:
            instance_id = item["InstanceId"]
            tags = tags_to_dict(item.get("Tags"))
            state = item["State"]["Name"]
            profile = (item.get("IamInstanceProfile") or {}).get("Arn")
            volumes = [
                mapping["Ebs"]["VolumeId"]
                for mapping in item.get("BlockDeviceMappings", [])
                if "Ebs" in mapping
            ]
            resources.append(
                Resource(
                    service=SERVICE,
                    type="instance",
                    id=instance_id,
                    arn=ctx.arn("ec2", region, f"instance/{instance_id}"),
                    region=region,
                    name=_name(tags, instance_id),
                    status=state,
                    is_active=state == "running",
                    created_at=iso(item.get("LaunchTime")),
                    tags=tags,
                    metadata={
                        "instance_type": item.get("InstanceType"),
                        "image_id": item.get("ImageId"),
                        "platform": item.get("PlatformDetails"),
                        "architecture": item.get("Architecture"),
                        "availability_zone": (item.get("Placement") or {}).get("AvailabilityZone"),
                        "private_ip": item.get("PrivateIpAddress"),
                        "public_ip": item.get("PublicIpAddress"),
                        "key_name": item.get("KeyName"),
                        "state_transition_reason": item.get("StateTransitionReason") or None,
                        "ebs_optimized": item.get("EbsOptimized"),
                    },
                    dependencies=deps(
                        dep(
                            "in-vpc",
                            item.get("VpcId") and ctx.arn("ec2", region, f"vpc/{item['VpcId']}"),
                            SERVICE,
                        ),
                        dep(
                            "in-subnet",
                            item.get("SubnetId")
                            and ctx.arn("ec2", region, f"subnet/{item['SubnetId']}"),
                            SERVICE,
                        ),
                        *[
                            dep(
                                "security-group",
                                ctx.arn("ec2", region, f"security-group/{sg['GroupId']}"),
                                SERVICE,
                            )
                            for sg in item.get("SecurityGroups", [])
                        ],
                        *[
                            dep("attached-volume", ctx.arn("ec2", region, f"volume/{v}"), SERVICE)
                            for v in volumes
                        ],
                        dep("instance-profile", profile, "iam"),
                        dep("image", item.get("ImageId"), SERVICE),
                    ),
                )
            )

    live = {
        r.id: MetricQuery("AWS/EC2", "NetworkIn", {"InstanceId": r.id})
        for r in resources
        if r.status != "terminated"
    }
    activity = latest_activity(ctx, SERVICE, region, live)
    for resource in resources:
        resource.last_activity, resource.last_activity_source, _ = apply_activity(
            activity, resource.id, "cloudwatch:NetworkIn"
        )
    return resources


def _volumes(ctx: Context, region: str) -> list[Resource]:
    resources = []
    for item in ctx.paginate(SERVICE, region, "describe_volumes", "Volumes"):
        volume_id = item["VolumeId"]
        tags = tags_to_dict(item.get("Tags"))
        resources.append(
            Resource(
                service=SERVICE,
                type="volume",
                id=volume_id,
                arn=ctx.arn("ec2", region, f"volume/{volume_id}"),
                region=region,
                name=_name(tags, volume_id),
                status=item["State"],
                is_active=item["State"] == "in-use",
                created_at=iso(item.get("CreateTime")),
                tags=tags,
                metadata={
                    "size_gib": item.get("Size"),
                    "volume_type": item.get("VolumeType"),
                    "iops": item.get("Iops"),
                    "encrypted": item.get("Encrypted"),
                    "availability_zone": item.get("AvailabilityZone"),
                    "snapshot_id": item.get("SnapshotId") or None,
                },
                dependencies=deps(
                    *[
                        dep(
                            "attached-to",
                            ctx.arn("ec2", region, f"instance/{a['InstanceId']}"),
                            SERVICE,
                        )
                        for a in item.get("Attachments", [])
                    ],
                    dep("kms-key", item.get("KmsKeyId"), "kms"),
                ),
            )
        )
    return resources


def _addresses(ctx: Context, region: str) -> list[Resource]:
    resources = []
    for item in ctx.client(SERVICE, region).describe_addresses().get("Addresses", []):
        allocation = item.get("AllocationId") or item["PublicIp"]
        associated = bool(item.get("AssociationId"))
        tags = tags_to_dict(item.get("Tags"))
        resources.append(
            Resource(
                service=SERVICE,
                type="elastic-ip",
                id=allocation,
                arn=ctx.arn("ec2", region, f"elastic-ip/{allocation}"),
                region=region,
                name=_name(tags, item["PublicIp"]),
                status="associated" if associated else "unassociated",
                is_active=associated,
                tags=tags,
                metadata={"public_ip": item["PublicIp"], "domain": item.get("Domain")},
                dependencies=deps(
                    dep(
                        "associated-instance",
                        item.get("InstanceId")
                        and ctx.arn("ec2", region, f"instance/{item['InstanceId']}"),
                        SERVICE,
                    ),
                    dep("network-interface", item.get("NetworkInterfaceId"), SERVICE),
                ),
            )
        )
    return resources


def _security_groups(ctx: Context, region: str) -> list[Resource]:
    resources = []
    for item in ctx.paginate(SERVICE, region, "describe_security_groups", "SecurityGroups"):
        group_id = item["GroupId"]
        tags = tags_to_dict(item.get("Tags"))
        open_to_world = any(
            ip_range.get("CidrIp") == "0.0.0.0/0"
            for permission in item.get("IpPermissions", [])
            for ip_range in permission.get("IpRanges", [])
        )
        resources.append(
            Resource(
                service=SERVICE,
                type="security-group",
                id=group_id,
                arn=ctx.arn("ec2", region, f"security-group/{group_id}"),
                region=region,
                name=item.get("GroupName"),
                status="available",
                tags=tags,
                metadata={
                    "description": item.get("Description"),
                    "inbound_rules": len(item.get("IpPermissions", [])),
                    "outbound_rules": len(item.get("IpPermissionsEgress", [])),
                    "open_to_world_ingress": open_to_world,
                },
                dependencies=deps(
                    dep(
                        "in-vpc",
                        item.get("VpcId") and ctx.arn("ec2", region, f"vpc/{item['VpcId']}"),
                        SERVICE,
                    )
                ),
            )
        )
    return resources


def _vpcs(ctx: Context, region: str) -> list[Resource]:
    resources = []
    for item in ctx.paginate(SERVICE, region, "describe_vpcs", "Vpcs"):
        tags = tags_to_dict(item.get("Tags"))
        resources.append(
            Resource(
                service=SERVICE,
                type="vpc",
                id=item["VpcId"],
                arn=ctx.arn("ec2", region, f"vpc/{item['VpcId']}"),
                region=region,
                name=_name(tags, item["VpcId"]),
                status=item["State"],
                is_active=item["State"] == "available",
                tags=tags,
                metadata={"cidr_block": item.get("CidrBlock"), "is_default": item.get("IsDefault")},
            )
        )
    return resources


def _subnets(ctx: Context, region: str) -> list[Resource]:
    resources = []
    for item in ctx.paginate(SERVICE, region, "describe_subnets", "Subnets"):
        tags = tags_to_dict(item.get("Tags"))
        resources.append(
            Resource(
                service=SERVICE,
                type="subnet",
                id=item["SubnetId"],
                arn=item.get("SubnetArn") or ctx.arn("ec2", region, f"subnet/{item['SubnetId']}"),
                region=region,
                name=_name(tags, item["SubnetId"]),
                status=item["State"],
                is_active=item["State"] == "available",
                tags=tags,
                metadata={
                    "cidr_block": item.get("CidrBlock"),
                    "availability_zone": item.get("AvailabilityZone"),
                    "available_ips": item.get("AvailableIpAddressCount"),
                    "map_public_ip_on_launch": item.get("MapPublicIpOnLaunch"),
                },
                dependencies=deps(
                    dep("in-vpc", ctx.arn("ec2", region, f"vpc/{item['VpcId']}"), SERVICE)
                ),
            )
        )
    return resources


def _nat_gateways(ctx: Context, region: str) -> list[Resource]:
    resources = []
    for item in ctx.paginate(SERVICE, region, "describe_nat_gateways", "NatGateways"):
        tags = tags_to_dict(item.get("Tags"))
        resources.append(
            Resource(
                service=SERVICE,
                type="nat-gateway",
                id=item["NatGatewayId"],
                arn=ctx.arn("ec2", region, f"natgateway/{item['NatGatewayId']}"),
                region=region,
                name=_name(tags, item["NatGatewayId"]),
                status=item["State"],
                is_active=item["State"] == "available",
                created_at=iso(item.get("CreateTime")),
                tags=tags,
                metadata={
                    "connectivity_type": item.get("ConnectivityType"),
                    "public_ips": [a.get("PublicIp") for a in item.get("NatGatewayAddresses", [])],
                },
                dependencies=deps(
                    dep(
                        "in-vpc",
                        item.get("VpcId") and ctx.arn("ec2", region, f"vpc/{item['VpcId']}"),
                        SERVICE,
                    ),
                    dep(
                        "in-subnet",
                        item.get("SubnetId")
                        and ctx.arn("ec2", region, f"subnet/{item['SubnetId']}"),
                        SERVICE,
                    ),
                ),
            )
        )
    queries = {
        r.id: MetricQuery("AWS/NATGateway", "BytesOutToDestination", {"NatGatewayId": r.id})
        for r in resources
        if r.status == "available"
    }
    activity = latest_activity(ctx, SERVICE, region, queries)
    for resource in resources:
        resource.last_activity, resource.last_activity_source, _ = apply_activity(
            activity, resource.id, "cloudwatch:BytesOutToDestination"
        )
    return resources

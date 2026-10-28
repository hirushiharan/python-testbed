"""S3 buckets (global listing, per-bucket region).

S3 exposes no cheap last-used signal (request metrics are opt-in), so ``last_activity`` and
``is_active`` stay null; the metadata carries versioning, encryption and public-access info.
"""

from __future__ import annotations

from typing import Any

from src.aws_inventory.collectors.base import register
from src.aws_inventory.model import Resource, dep, deps, iso, tags_to_dict
from src.aws_inventory.session import Context
from src.aws_inventory.telemetry import Progress

SERVICE = "s3"

_LOCATION_ALIASES = {None: "us-east-1", "": "us-east-1", "EU": "eu-west-1"}


@register(SERVICE, scope="global")
def collect(ctx: Context, region: str) -> list[Resource]:
    """List every bucket once, then enrich each from its own region."""
    s3 = ctx.client(SERVICE, region)
    buckets = list(ctx.paginate(SERVICE, region, "list_buckets", "Buckets"))
    progress = Progress("s3 buckets", len(buckets))
    return ctx.map(progress.wrap(lambda bucket: _describe_bucket(ctx, s3, region, bucket)), buckets)


def _describe_bucket(
    ctx: Context, home_s3: Any, home_region: str, bucket: dict[str, Any]
) -> Resource:
    name = bucket["Name"]
    bucket_region = bucket.get("BucketRegion")
    if not bucket_region:
        location = ctx.safe(
            SERVICE,
            home_region,
            "GetBucketLocation",
            lambda: home_s3.get_bucket_location(Bucket=name).get("LocationConstraint"),
        )
        bucket_region = _LOCATION_ALIASES.get(location, location or home_region)

    s3 = ctx.client(SERVICE, bucket_region)

    def call(operation: str, fn: Any, ignore: tuple[str, ...] = ()) -> Any:
        return ctx.safe(SERVICE, bucket_region, f"{operation}:{name}", fn, None, ignore)

    tags_response = call(
        "GetBucketTagging", lambda: s3.get_bucket_tagging(Bucket=name), ("NoSuchTagSet",)
    )
    versioning = call("GetBucketVersioning", lambda: s3.get_bucket_versioning(Bucket=name))
    encryption = call(
        "GetBucketEncryption",
        lambda: s3.get_bucket_encryption(Bucket=name),
        ("ServerSideEncryptionConfigurationNotFoundError",),
    )
    public_block = call(
        "GetPublicAccessBlock",
        lambda: s3.get_public_access_block(Bucket=name),
        ("NoSuchPublicAccessBlockConfiguration",),
    )
    policy_status = call(
        "GetBucketPolicyStatus",
        lambda: s3.get_bucket_policy_status(Bucket=name),
        ("NoSuchBucketPolicy",),
    )
    logging_conf = call("GetBucketLogging", lambda: s3.get_bucket_logging(Bucket=name))

    rules = ((encryption or {}).get("ServerSideEncryptionConfiguration") or {}).get("Rules", [])
    default_encryption = (rules[0].get("ApplyServerSideEncryptionByDefault") or {}) if rules else {}
    log_target = ((logging_conf or {}).get("LoggingEnabled") or {}).get("TargetBucket")

    return Resource(
        service=SERVICE,
        type="bucket",
        id=name,
        arn=f"arn:{ctx.partition}:s3:::{name}",
        region=bucket_region,
        name=name,
        status="available",
        created_at=iso(bucket.get("CreationDate")),
        tags=tags_to_dict((tags_response or {}).get("TagSet")),
        metadata={
            "versioning": (versioning or {}).get("Status", "Disabled")
            if versioning is not None
            else None,
            "encryption": default_encryption.get("SSEAlgorithm"),
            "kms_key": default_encryption.get("KMSMasterKeyID"),
            "public_access_block": (public_block or {}).get("PublicAccessBlockConfiguration"),
            "policy_is_public": ((policy_status or {}).get("PolicyStatus") or {}).get("IsPublic"),
        },
        dependencies=deps(
            dep("logs-to", log_target and f"arn:{ctx.partition}:s3:::{log_target}", SERVICE),
            dep("kms-key", default_encryption.get("KMSMasterKeyID"), "kms"),
        ),
    )

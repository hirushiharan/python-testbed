"""IAM users, roles and customer-managed policies (global service).

``last_activity`` comes from IAM's own tracking: ``RoleLastUsed`` for roles, and the newest of
``PasswordLastUsed`` / access-key last-used for users. IAM keeps this for about 400 days.
Roles and users are active if used within ``ACTIVE_DAYS``. A principal with no recorded use
is inactive when it is older than ``ACTIVE_DAYS`` and unknown when newer.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any

from src.aws_inventory.collectors.base import register
from src.aws_inventory.model import Resource, dep, deps, iso, tags_to_dict
from src.aws_inventory.session import Context
from src.aws_inventory.telemetry import Progress

SERVICE = "iam"
ACTIVE_DAYS = 90


@register(SERVICE, scope="global")
def collect(ctx: Context, region: str) -> list[Resource]:
    """List IAM principals and policies once for the account."""
    resources: list[Resource] = []
    for operation, fn in (
        ("ListUsers", _users),
        ("ListRoles", _roles),
        ("ListPolicies", _policies),
    ):
        resources.extend(
            ctx.safe(SERVICE, region, operation, lambda fn=fn: fn(ctx, region), []) or []
        )
    return resources


def _activity_state(last_used: str | None, created: datetime | None) -> bool | None:
    """True if used recently, False if stale or never used and old, else None."""
    cutoff = datetime.now(timezone.utc) - timedelta(days=ACTIVE_DAYS)
    if last_used:
        return datetime.fromisoformat(last_used) >= cutoff
    if created is not None and created.astimezone(timezone.utc) < cutoff:
        return False
    return None


def _users(ctx: Context, region: str) -> list[Resource]:
    iam = ctx.client(SERVICE, region)
    users = list(ctx.paginate(SERVICE, region, "list_users", "Users"))

    def describe(user: dict[str, Any]) -> Resource:
        name = user["UserName"]

        def call(operation: str, fn: Any) -> Any:
            return ctx.safe(SERVICE, region, f"{operation}:{name}", fn)

        keys = (call("ListAccessKeys", lambda: iam.list_access_keys(UserName=name)) or {}).get(
            "AccessKeyMetadata", []
        )
        key_info = []
        newest = iso(user.get("PasswordLastUsed"))
        for key in keys:
            used = (
                call(
                    "GetAccessKeyLastUsed",
                    lambda key=key: iam.get_access_key_last_used(AccessKeyId=key["AccessKeyId"]),
                )
                or {}
            ).get("AccessKeyLastUsed", {})
            used_at = iso(used.get("LastUsedDate"))
            if used_at and (newest is None or used_at > newest):
                newest = used_at
            key_info.append(
                {
                    "id": key["AccessKeyId"],
                    "status": key["Status"],
                    "created": iso(key.get("CreateDate")),
                    "last_used": used_at,
                    "last_used_service": used.get("ServiceName"),
                }
            )
        mfa = (call("ListMFADevices", lambda: iam.list_mfa_devices(UserName=name)) or {}).get(
            "MFADevices"
        )
        attached = (
            call("ListAttachedUserPolicies", lambda: iam.list_attached_user_policies(UserName=name))
            or {}
        ).get("AttachedPolicies", [])
        return Resource(
            service=SERVICE,
            type="user",
            id=name,
            arn=user["Arn"],
            region="global",
            name=name,
            status="active" if keys or user.get("PasswordLastUsed") else "no-credentials-used",
            is_active=_activity_state(newest, user.get("CreateDate")),
            created_at=iso(user.get("CreateDate")),
            last_activity=newest,
            last_activity_source="iam:PasswordLastUsed/AccessKeyLastUsed",
            tags=tags_to_dict(user.get("Tags")),
            metadata={
                "access_keys": key_info,
                "mfa_enabled": bool(mfa) if mfa is not None else None,
                "has_console_password": "PasswordLastUsed" in user,  # pragma: allowlist secret
            },
            dependencies=deps(*[dep("attached-policy", p["PolicyArn"], SERVICE) for p in attached]),
        )

    return ctx.map(Progress("iam users", len(users)).wrap(describe), users)


def _roles(ctx: Context, region: str) -> list[Resource]:
    iam = ctx.client(SERVICE, region)
    roles = list(ctx.paginate(SERVICE, region, "list_roles", "Roles"))

    def describe(role: dict[str, Any]) -> Resource:
        name = role["RoleName"]
        detail = (
            ctx.safe(SERVICE, region, f"GetRole:{name}", lambda: iam.get_role(RoleName=name)) or {}
        ).get("Role", {})
        attached = (
            ctx.safe(
                SERVICE,
                region,
                f"ListAttachedRolePolicies:{name}",
                lambda: iam.list_attached_role_policies(RoleName=name),
            )
            or {}
        ).get("AttachedPolicies", [])
        last_used = detail.get("RoleLastUsed", {})
        last_used_at = iso(last_used.get("LastUsedDate"))
        trusted: list[str] = []
        for statement in (role.get("AssumeRolePolicyDocument") or {}).get("Statement", []):
            principal = statement.get("Principal", {})
            if isinstance(principal, dict):
                for value in principal.values():
                    trusted.extend(value if isinstance(value, list) else [value])
            elif principal:
                trusted.append(str(principal))
        return Resource(
            service=SERVICE,
            type="role",
            id=name,
            arn=role["Arn"],
            region="global",
            name=name,
            status="used" if last_used_at else "never-used",
            is_active=_activity_state(last_used_at, role.get("CreateDate")) if detail else None,
            created_at=iso(role.get("CreateDate")),
            last_activity=last_used_at,
            last_activity_source="iam:RoleLastUsed",
            tags=tags_to_dict(detail.get("Tags")),
            metadata={
                "path": role.get("Path"),
                "service_linked": role.get("Path", "").startswith("/aws-service-role/"),
                "last_used_region": last_used.get("Region"),
                "trusted_principals": trusted,
                "max_session_seconds": role.get("MaxSessionDuration"),
            },
            dependencies=deps(*[dep("attached-policy", p["PolicyArn"], SERVICE) for p in attached]),
        )

    return ctx.map(Progress("iam roles", len(roles)).wrap(describe), roles)


def _policies(ctx: Context, region: str) -> list[Resource]:
    resources = []
    for policy in ctx.paginate(SERVICE, region, "list_policies", "Policies", Scope="Local"):
        attached = policy.get("AttachmentCount", 0)
        resources.append(
            Resource(
                service=SERVICE,
                type="policy",
                id=policy["PolicyName"],
                arn=policy["Arn"],
                region="global",
                name=policy["PolicyName"],
                status="attached" if attached else "unattached",
                is_active=attached > 0,
                created_at=iso(policy.get("CreateDate")),
                tags=tags_to_dict(policy.get("Tags")),
                metadata={
                    "attachment_count": attached,
                    "default_version": policy.get("DefaultVersionId"),
                    "updated_at": iso(policy.get("UpdateDate")),
                },
            )
        )
    return resources

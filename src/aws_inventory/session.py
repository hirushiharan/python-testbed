"""AWS session handling and the shared per-run context used by every collector.

Credentials come from boto3's default chain, i.e. whatever the AWS CLI is logged in with
(``aws login``, ``aws sso login``, a named profile, or AWS_* env vars). Nothing here writes
to AWS: the only calls are STS identity/assume-role, and the List/Describe/Get calls the
collectors make through ``Context``.
"""

from __future__ import annotations

import logging
import threading
from concurrent.futures import ThreadPoolExecutor
from typing import Any, Callable, Iterable, Iterator, TypeVar

import boto3
from botocore.config import Config
from botocore.exceptions import ClientError

from src.aws_inventory.model import InventoryError
from src.aws_inventory.telemetry import Telemetry, bind_task, current_task

logger = logging.getLogger(__name__)

T = TypeVar("T")
R = TypeVar("R")

CONNECT_TIMEOUT_SECONDS = 10
READ_TIMEOUT_SECONDS = 30
MAX_ATTEMPTS = 5

CLIENT_CONFIG = Config(
    retries={"max_attempts": MAX_ATTEMPTS, "mode": "adaptive"},
    connect_timeout=CONNECT_TIMEOUT_SECONDS,
    read_timeout=READ_TIMEOUT_SECONDS,
    max_pool_connections=50,
    user_agent_extra="aws-inventory",
)

GLOBAL_REGION_BY_PARTITION = {
    "aws": "us-east-1",
    "aws-cn": "cn-north-1",
    "aws-us-gov": "us-gov-west-1",
}


class SessionError(RuntimeError):
    """Raised when we cannot obtain usable credentials for the requested account."""


class AccountMismatchError(SessionError):
    """Raised when the credentials belong to a different account than the one requested."""


class Context:
    """Per-run state shared by all collectors: session, clients, error log, helpers."""

    def __init__(
        self,
        session: boto3.Session,
        account_id: str,
        partition: str = "aws",
        caller_arn: str = "",
    ) -> None:
        self.session = session
        self.account_id = account_id
        self.partition = partition
        self.caller_arn = caller_arn
        self.global_region = GLOBAL_REGION_BY_PARTITION.get(partition, "us-east-1")
        self.errors: list[InventoryError] = []
        self.telemetry = Telemetry()
        self._clients: dict[tuple[str, str], Any] = {}
        self._lock = threading.Lock()

    def client(self, service: str, region: str | None = None) -> Any:
        """Return a cached, instrumented client (creation is not thread-safe, so it is locked)."""
        key = (service, region or self.global_region)
        with self._lock:
            if key not in self._clients:
                client = self.session.client(service, region_name=key[1], config=CLIENT_CONFIG)
                self.telemetry.instrument(client, key[1])
                self._clients[key] = client
                logger.debug("Created %s client for %s", service, key[1])
            return self._clients[key]

    def arn(self, service: str, region: str, resource: str) -> str:
        """Build an ARN in this account's partition."""
        return f"arn:{self.partition}:{service}:{region}:{self.account_id}:{resource}"

    def record_error(self, service: str, region: str, operation: str, exc: Exception) -> None:
        """Log a non-fatal failure so it shows up in the report's coverage section."""
        message = f"{type(exc).__name__}: {exc}"
        logger.warning("ERROR %s/%s %s: %s", service, region, operation, message)
        self.telemetry.note_error()
        with self._lock:
            self.errors.append(InventoryError(service, region, operation, message))

    def safe(
        self,
        service: str,
        region: str,
        operation: str,
        fn: Callable[[], T],
        default: T | None = None,
        ignore_codes: Iterable[str] = (),
    ) -> T | None:
        """Run ``fn``; on failure record an error (unless expected) and return ``default``."""
        try:
            return fn()
        except ClientError as exc:
            if exc.response.get("Error", {}).get("Code") in set(ignore_codes):
                return default
            self.record_error(service, region, operation, exc)
        except Exception as exc:  # noqa: BLE001 - one bad call must not abort the inventory
            self.record_error(service, region, operation, exc)
        return default

    def paginate(
        self, service: str, region: str, operation: str, result_key: str, **kwargs: Any
    ) -> Iterator[Any]:
        """Yield every item under ``result_key`` across all pages (errors propagate)."""
        paginator = self.client(service, region).get_paginator(operation)
        for page in paginator.paginate(**kwargs):
            yield from page.get(result_key, [])

    def map(self, fn: Callable[[T], R], items: list[T], workers: int = 8) -> list[R]:
        """Apply ``fn`` to items in a small thread pool, preserving order.

        Worker threads inherit the caller's task name so their API calls show up under it.
        """
        task = current_task()

        def run(item: T) -> R:
            with bind_task(task):
                return fn(item)

        if len(items) < 2:
            return [fn(item) for item in items]
        with ThreadPoolExecutor(max_workers=min(workers, len(items))) as pool:
            return list(pool.map(run, items))


def build_context(
    account_id: str, profile: str | None = None, role_name: str | None = None
) -> Context:
    """Create a verified context for ``account_id`` from the CLI login (or an assumed role)."""
    try:
        session = boto3.Session(profile_name=profile)
        caller = _caller_identity(session)
    except Exception as exc:  # noqa: BLE001
        raise SessionError(
            f"Could not authenticate with AWS ({exc}). Log in first, e.g. 'aws login', "
            "'aws sso login --profile <name>' or 'aws configure', then retry."
        ) from exc

    partition = caller["Arn"].split(":")[1]

    if role_name:
        session = _assume_role(session, partition, account_id, role_name)
        caller = _caller_identity(session)

    if caller["Account"] != account_id:
        raise AccountMismatchError(
            f"Credentials belong to account {caller['Account']}, not {account_id}. "
            f"Use a profile for {account_id}, or pass --role-name to assume a role in it."
        )

    return Context(session, account_id, partition=partition, caller_arn=caller["Arn"])


def _caller_identity(session: boto3.Session) -> dict[str, str]:
    region = GLOBAL_REGION_BY_PARTITION["aws"]
    return session.client("sts", region_name=region, config=CLIENT_CONFIG).get_caller_identity()


def _assume_role(
    session: boto3.Session, partition: str, account_id: str, role_name: str
) -> boto3.Session:
    sts = session.client("sts", region_name=GLOBAL_REGION_BY_PARTITION["aws"], config=CLIENT_CONFIG)
    try:
        credentials = sts.assume_role(
            RoleArn=f"arn:{partition}:iam::{account_id}:role/{role_name}",
            RoleSessionName="aws-inventory",
            DurationSeconds=3600,
        )["Credentials"]
    except ClientError as exc:
        raise SessionError(f"Could not assume role '{role_name}' in {account_id}: {exc}") from exc
    return boto3.Session(
        aws_access_key_id=credentials["AccessKeyId"],
        aws_secret_access_key=credentials["SecretAccessKey"],
        aws_session_token=credentials["SessionToken"],
    )

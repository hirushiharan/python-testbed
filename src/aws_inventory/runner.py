"""Orchestrates collectors across regions in a thread pool and merges the results."""

from __future__ import annotations

import logging
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
from typing import Callable

from src.aws_inventory import collectors
from src.aws_inventory.collectors.base import COLLECTORS, Collector
from src.aws_inventory.cost import fetch_costs
from src.aws_inventory.discovery import discover_resource_explorer, discover_tagged
from src.aws_inventory.model import Inventory, Resource
from src.aws_inventory.session import Context

logger = logging.getLogger(__name__)

assert collectors  # importing the package registers every collector


def list_enabled_regions(ctx: Context) -> list[str]:
    """Regions enabled for the account (opt-in regions that are not enabled are excluded)."""
    response = ctx.client("ec2", ctx.global_region).describe_regions(AllRegions=False)
    return sorted(r["RegionName"] for r in response["Regions"])


def _account_alias(ctx: Context) -> str | None:
    aliases = ctx.safe(
        "iam",
        ctx.global_region,
        "ListAccountAliases",
        lambda: ctx.client("iam").list_account_aliases()["AccountAliases"],
        [],
    )
    return aliases[0] if aliases else None


def task_name(collector: Collector, region: str) -> str:
    """Display name for a collector task; global collectors have no meaningful region."""
    return f"{collector.service}/{'global' if collector.scope == 'global' else region}"


def plan_tasks(
    selected: list[Collector], regions: list[str], global_region: str
) -> list[tuple[Collector, str]]:
    """Expand collectors into (collector, region) tasks, global ones first.

    Global collectors (IAM, S3, CloudFront) are single long tasks, so they must start
    immediately instead of queueing behind hundreds of short regional ones.
    """
    ordered = sorted(selected, key=lambda c: c.scope != "global")
    return [
        (collector, region)
        for collector in ordered
        for region in ([global_region] if collector.scope == "global" else regions)
    ]


def _run_collector(ctx: Context, collector: Collector, region: str) -> list[Resource]:
    """Run one collector; a failure is recorded and yields no resources for that task."""
    with ctx.telemetry.task(task_name(collector, region), collector.service) as record:
        result = (
            ctx.safe(collector.service, region, "collect", lambda: collector.collect(ctx, region))
            or []
        )
        record.set_result(result)
    return result


def _run_discovery(
    ctx: Context, name: str, service: str, fn: Callable[[], list[Resource]]
) -> list[Resource]:
    """Run one generic discovery sweep with the same START/DONE tracking as collectors."""
    with ctx.telemetry.task(name, service) as record:
        result = ctx.safe(service, name.split("/", 1)[-1], "discover", fn, []) or []
        record.set_result(result)
    return result


def run_inventory(
    ctx: Context,
    regions: list[str],
    services: list[str] | None = None,
    *,
    skip_cost: bool = False,
    skip_discovery: bool = False,
    max_workers: int = 8,
) -> Inventory:
    """Collect everything requested and return the merged inventory."""
    selected = [COLLECTORS[name] for name in (services or sorted(COLLECTORS))]
    telemetry = ctx.telemetry

    jobs: list[Callable[[], list[Resource]]] = []
    for collector, region in plan_tasks(selected, regions, ctx.global_region):
        jobs.append(lambda c=collector, r=region: _run_collector(ctx, c, r))
    deep_jobs = len(jobs)

    if not skip_discovery:
        for region in regions:
            jobs.append(
                lambda r=region: _run_discovery(
                    ctx, f"tagging/{r}", "tagging", lambda: discover_tagged(ctx, r)
                )
            )
        jobs.append(
            lambda: _run_discovery(
                ctx,
                "resource-explorer/global",
                "resource-explorer",
                lambda: discover_resource_explorer(ctx),
            )
        )

    telemetry.tasks_total = len(jobs)
    logger.info(
        "Plan: %d tasks (%d collector, %d discovery) on %d workers; global collectors first",
        len(jobs),
        deep_jobs,
        len(jobs) - deep_jobs,
        max_workers,
    )

    deep: list[Resource] = []
    stubs: list[Resource] = []
    stop_heartbeat = telemetry.start_heartbeat(lambda: len(ctx.errors))
    pool = ThreadPoolExecutor(max_workers=max_workers, thread_name_prefix="inv")
    interrupted = False
    try:
        futures = {pool.submit(job): index for index, job in enumerate(jobs)}
        for future in as_completed(futures):
            (deep if futures[future] < deep_jobs else stubs).extend(future.result())
    except KeyboardInterrupt:
        interrupted = True
        telemetry.cancelled.set()
        logger.warning("Interrupted: cancelling pending tasks. In flight right now:")
        for line in telemetry.heartbeat_lines(len(ctx.errors)):
            logger.warning(line)
        raise
    finally:
        stop_heartbeat.set()
        pool.shutdown(wait=not interrupted, cancel_futures=interrupted)

    inventory = Inventory(
        account={
            "id": ctx.account_id,
            "alias": _account_alias(ctx),
            "caller_arn": ctx.caller_arn,
            "partition": ctx.partition,
            "regions_scanned": regions,
            "generated_at": datetime.now(timezone.utc).isoformat(),
        },
        resources=sorted(merge(deep, stubs), key=lambda r: (r.service, r.region, r.type, r.id)),
        errors=ctx.errors,
        services_scanned=sorted(c.service for c in selected),
    )
    if not skip_cost:
        logger.info("Fetching Cost Explorer spend (billed ~$0.01 per request)")
        inventory.cost = fetch_costs(ctx)
    logger.info("Collected %d resources", len(inventory.resources))
    for line in telemetry.report_lines(len(ctx.errors)):
        logger.info(line)
    return inventory


def merge(deep: list[Resource], stubs: list[Resource]) -> list[Resource]:
    """Keep every deep result; add a generic stub only when no resource has the same ARN."""
    seen = {r.arn for r in deep if r.arn}
    merged = list(deep)
    for stub in stubs:
        if stub.arn in seen:
            continue
        seen.add(stub.arn)
        merged.append(stub)
    return merged

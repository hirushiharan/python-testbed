"""Inventory an AWS account across all regions, grouped by service (strictly read-only).

Usage:
    python src/aws_inventory/cli.py 123456789012
    python src/aws_inventory/cli.py 123456789012 --profile prod --format xlsx
    python src/aws_inventory/cli.py 123456789012 --role-name OrganizationAccountAccessRole
    python src/aws_inventory/cli.py 123456789012 --regions us-east-1,eu-west-1 --services ec2,s3

Credentials come from your AWS CLI login (``aws login``, ``aws sso login``, a profile or AWS_*
env vars). The account ID is verified against those credentials before anything is collected.
"""

from __future__ import annotations

import argparse
import logging
import os
import re
import sys
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from dotenv import load_dotenv  # noqa: E402

from src.aws_inventory.collectors.base import COLLECTORS  # noqa: E402
from src.aws_inventory.exporters import write_json, write_xlsx  # noqa: E402
from src.aws_inventory.runner import list_enabled_regions, run_inventory  # noqa: E402
from src.aws_inventory.session import (  # noqa: E402
    CONNECT_TIMEOUT_SECONDS,
    MAX_ATTEMPTS,
    READ_TIMEOUT_SECONDS,
    SessionError,
    build_context,
)

logger = logging.getLogger(__name__)

DEFAULT_OUTPUT_DIR = "aws-inventory-output"


def account_id_type(value: str) -> str:
    """Argparse type: a 12-digit AWS account ID."""
    if not re.fullmatch(r"\d{12}", value):
        raise argparse.ArgumentTypeError("account ID must be exactly 12 digits")
    return value


def csv_list(value: str) -> list[str]:
    """Argparse type: comma-separated values."""
    return [item.strip() for item in value.split(",") if item.strip()]


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    """Parse command-line arguments."""
    parser = argparse.ArgumentParser(
        description="Read-only inventory of an AWS account across all regions, grouped by service"
    )
    parser.add_argument(
        "account_id", type=account_id_type, help="12-digit AWS account ID to inventory"
    )
    parser.add_argument(
        "--profile", help="AWS CLI profile (default: the CLI/default credential chain)"
    )
    parser.add_argument(
        "--role-name",
        help="Assume this role in the target account (arn:aws:iam::<id>:role/<name>) "
        "instead of using the CLI credentials directly",
    )
    parser.add_argument(
        "--regions",
        type=csv_list,
        help="Comma-separated regions to scan (default: all enabled). "
        "Global services always run once",
    )
    parser.add_argument(
        "--services",
        type=csv_list,
        help="Comma-separated services to collect (default: all). "
        f"Choices: {', '.join(sorted(COLLECTORS))}. Implies --skip-discovery",
    )
    parser.add_argument(
        "--format", choices=("json", "xlsx", "both"), default="both", help="Output format"
    )
    parser.add_argument(
        "--output-dir", default=DEFAULT_OUTPUT_DIR, help="Directory for output files"
    )
    parser.add_argument(
        "--skip-cost", action="store_true", help="Skip Cost Explorer (it bills ~$0.01/request)"
    )
    parser.add_argument(
        "--skip-discovery",
        action="store_true",
        help="Skip the generic Tagging API / Resource Explorer sweep "
        "for services without a collector",
    )
    parser.add_argument("--max-workers", type=int, default=8, help="Parallel collector tasks")
    parser.add_argument("--verbose", action="store_true", help="Enable debug logs")
    return parser.parse_args(argv)


def configure_logging(verbose: bool, log_path: Path | None = None) -> None:
    """Log to the console (INFO, or DEBUG with --verbose) and, if given, to a DEBUG log file.

    botocore/urllib3 are held at WARNING even in the file: their DEBUG output includes full
    signed request headers, which must not be written to disk.
    """
    root = logging.getLogger()
    root.handlers.clear()
    root.setLevel(logging.DEBUG)

    console = logging.StreamHandler()
    console.setLevel(logging.DEBUG if verbose else logging.INFO)
    console.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(message)s", "%H:%M:%S"))
    root.addHandler(console)

    if log_path is not None:
        log_path.parent.mkdir(parents=True, exist_ok=True)
        file_handler = logging.FileHandler(log_path, encoding="utf-8")
        file_handler.setLevel(logging.DEBUG)
        file_handler.setFormatter(
            logging.Formatter("%(asctime)s %(levelname)s [%(threadName)s] %(name)s: %(message)s")
        )
        root.addHandler(file_handler)

    for noisy in ("botocore", "boto3", "urllib3", "s3transfer"):
        logging.getLogger(noisy).setLevel(logging.WARNING)


def main(argv: list[str] | None = None) -> int:
    """Run the inventory command."""
    args = parse_args(argv)
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    base = Path(args.output_dir) / f"aws-inventory-{args.account_id}-{stamp}"
    log_path = base.with_suffix(".log")
    configure_logging(args.verbose, log_path)
    load_dotenv()
    logger.info("Log file: %s", log_path)

    unknown_services = sorted(set(args.services or []) - set(COLLECTORS))
    if unknown_services:
        logger.error(
            "Unknown service(s): %s. Choices: %s",
            ", ".join(unknown_services),
            ", ".join(sorted(COLLECTORS)),
        )
        return 2

    try:
        ctx = build_context(args.account_id, profile=args.profile, role_name=args.role_name)
        enabled_regions = list_enabled_regions(ctx)
    except SessionError as exc:
        logger.error("%s", exc)
        return 1
    except Exception as exc:  # noqa: BLE001
        logger.error("Could not list regions: %s", exc)
        return 1

    regions = args.regions or enabled_regions
    unknown_regions = sorted(set(regions) - set(enabled_regions))
    if unknown_regions:
        logger.error("Region(s) not enabled for this account: %s", ", ".join(unknown_regions))
        return 2

    services = args.services or sorted(COLLECTORS)
    skip_discovery = args.skip_discovery or bool(args.services)
    logger.info("Account:   %s", ctx.account_id)
    logger.info("Caller:    %s (partition %s)", ctx.caller_arn, ctx.partition)
    logger.info(
        "Auth:      profile=%s role=%s", args.profile or "default chain", args.role_name or "none"
    )
    logger.info("Regions:   %d scanned (%s)", len(regions), ", ".join(regions))
    logger.info("Services:  %d (%s)", len(services), ", ".join(services))
    logger.info(
        "Settings:  workers=%d connect_timeout=%ds read_timeout=%ds max_attempts=%d "
        "discovery=%s cost=%s format=%s",
        args.max_workers,
        CONNECT_TIMEOUT_SECONDS,
        READ_TIMEOUT_SECONDS,
        MAX_ATTEMPTS,
        "off" if skip_discovery else "on",
        "off" if args.skip_cost else "on",
        args.format,
    )

    try:
        inventory = run_inventory(
            ctx,
            regions,
            args.services,
            skip_cost=args.skip_cost,
            skip_discovery=skip_discovery,
            max_workers=args.max_workers,
        )
    except KeyboardInterrupt:
        logger.warning("Interrupted by user; no output written. Log: %s", log_path)
        logging.shutdown()
        # Worker threads may still be inside an API call; exit without waiting for them.
        os._exit(130)

    written = []
    if args.format in ("json", "both"):
        written.append(write_json(inventory, base.with_suffix(".json")))
    if args.format in ("xlsx", "both"):
        written.append(write_xlsx(inventory, base.with_suffix(".xlsx")))

    print_summary(inventory)
    for path in written:
        print(f"Wrote {path}")
    print(f"Wrote {log_path}")
    return 0


def print_summary(inventory) -> None:  # noqa: ANN001
    """Print a per-service table to the console."""
    print(f"\n{'service':<14}{'resources':>10}{'active':>8}{'inactive':>10}{'unknown':>9}")
    for name, resources in inventory.services().items():
        summary = inventory.service_summary(name, resources)
        print(
            f"{name:<14}{summary['resource_count']:>10}{summary['active_count']:>8}"
            f"{summary['inactive_count']:>10}{summary['unknown_activity_count']:>9}"
        )
    print(f"\nTotal resources: {len(inventory.resources)}")
    if inventory.errors:
        print(f"Non-fatal errors: {len(inventory.errors)} (see the Errors sheet / coverage.errors)")


if __name__ == "__main__":
    sys.exit(main())

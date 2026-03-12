"""Delete S3 bucket objects, optionally restricted by key prefix."""

import argparse
import logging
import os
import sys
from typing import Any

from dotenv import load_dotenv

MAX_DELETE_BATCH_SIZE = 1000

logger = logging.getLogger(__name__)


def configure_logging(verbose: bool) -> None:
    """Configure console logging for script execution."""
    level = logging.DEBUG if verbose else logging.INFO
    logging.basicConfig(level=level, format="%(levelname)s: %(message)s")


def parse_args() -> argparse.Namespace:
    """Parse command-line arguments."""
    parser = argparse.ArgumentParser(
        description="Delete objects from an AWS S3 bucket"
    )
    parser.add_argument("bucket", help="Name of the S3 bucket")
    parser.add_argument(
        "--prefix",
        default="",
        help="Optional key prefix to limit deletion scope",
    )
    parser.add_argument(
        "--yes",
        action="store_true",
        help="Skip confirmation prompt and delete immediately",
    )
    parser.add_argument(
        "--verbose",
        action="store_true",
        help="Enable debug logs",
    )
    return parser.parse_args()


def read_required_env_var(name: str) -> str:
    """Read required environment variable or raise an error."""
    value = os.getenv(name, "").strip()
    if not value:
        raise RuntimeError(f"Missing required env var: {name}")
    return value


def build_s3_client() -> Any:
    """Create boto3 S3 client from AWS environment variables."""
    try:
        import boto3
    except ImportError as exc:
        raise RuntimeError(
            "Missing dependency 'boto3'. Install it with: pip install boto3"
        ) from exc

    access_key_id = read_required_env_var("AWS_ACCESS_KEY_ID")
    secret_access_key = read_required_env_var("AWS_SECRET_ACCESS_KEY")
    region_name = read_required_env_var("AWS_REGION")
    session_token = os.getenv("AWS_SESSION_TOKEN", "").strip() or None

    session = boto3.Session(
        aws_access_key_id=access_key_id,
        aws_secret_access_key=secret_access_key,
        aws_session_token=session_token,
        region_name=region_name,
    )
    return session.client("s3")


def list_bucket_object_keys(s3_client: Any, bucket_name: str, prefix: str = "") -> list[str]:
    """List object keys in bucket using pagination."""
    paginator = s3_client.get_paginator("list_objects_v2")
    pages = paginator.paginate(Bucket=bucket_name, Prefix=prefix)

    keys: list[str] = []
    for page in pages:
        contents = page.get("Contents", [])
        keys.extend(item["Key"] for item in contents)

    return keys


def delete_object_batch(s3_client: Any, bucket_name: str, keys: list[str]) -> tuple[int, int]:
    """Delete one batch of object keys and return deleted/error counts."""
    response = s3_client.delete_objects(
        Bucket=bucket_name,
        Delete={"Objects": [{"Key": key} for key in keys], "Quiet": True},
    )
    deleted_count = len(response.get("Deleted", []))
    error_count = len(response.get("Errors", []))
    return deleted_count, error_count


def delete_objects_by_prefix(s3_client: Any, bucket_name: str, prefix: str = "") -> tuple[int, int]:
    """Delete all bucket objects matching prefix in API-sized batches."""
    keys = list_bucket_object_keys(s3_client, bucket_name, prefix)
    if not keys:
        return 0, 0

    total_deleted = 0
    total_errors = 0

    for start_index in range(0, len(keys), MAX_DELETE_BATCH_SIZE):
        batch = keys[start_index : start_index + MAX_DELETE_BATCH_SIZE]
        deleted_count, error_count = delete_object_batch(s3_client, bucket_name, batch)
        total_deleted += deleted_count
        total_errors += error_count
        logger.debug(
            "Deleted batch ending at index %d: deleted=%d errors=%d",
            start_index + len(batch),
            deleted_count,
            error_count,
        )

    return total_deleted, total_errors


def confirm_deletion(bucket_name: str, prefix: str, object_count: int) -> bool:
    """Ask user to confirm destructive deletion operation."""
    scope = f"prefix '{prefix}'" if prefix else "entire bucket"
    print(
        f"About to delete {object_count} object(s) from bucket '{bucket_name}' ({scope})."
    )
    answer = input("Type 'delete' to continue: ").strip().lower()
    return answer == "delete"


def main() -> int:
    """Run S3 cleanup command."""
    args = parse_args()
    configure_logging(verbose=args.verbose)
    load_dotenv()

    try:
        s3_client = build_s3_client()
        keys = list_bucket_object_keys(s3_client, args.bucket, args.prefix)
    except Exception as exc:
        logger.error("Error connecting to S3 or listing objects: %s", exc)
        return 1

    if not keys:
        logger.info("No objects found to delete")
        print("No objects found to delete.")
        return 0

    logger.info("Found %d object(s) to delete", len(keys))
    if not args.yes and not confirm_deletion(args.bucket, args.prefix, len(keys)):
        print("Cancelled. No objects were deleted.")
        return 0

    try:
        deleted_count, error_count = delete_objects_by_prefix(
            s3_client,
            args.bucket,
            args.prefix,
        )
    except Exception as exc:
        logger.error("Error deleting objects: %s", exc)
        return 1

    print(f"Deleted objects: {deleted_count}")
    if error_count > 0:
        logger.warning("Deletion completed with %d errors", error_count)
        print(f"Objects with errors: {error_count}")
        return 2

    logger.info("Bucket cleanup completed successfully")
    print("Bucket cleanup completed successfully.")
    return 0


if __name__ == "__main__":
    sys.exit(main())

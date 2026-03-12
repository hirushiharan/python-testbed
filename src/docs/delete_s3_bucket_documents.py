import argparse
import os
import sys
from typing import Any

from dotenv import load_dotenv


MAX_DELETE_BATCH_SIZE = 1000


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Delete all objects from an AWS S3 bucket"
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
    return parser.parse_args()


def get_required_env(name: str) -> str:
    value = os.getenv(name, "").strip()
    if not value:
        raise RuntimeError(f"Missing required env var: {name}")
    return value


def build_s3_client() -> Any:
    try:
        import boto3
    except ImportError as exc:
        raise RuntimeError(
            "Missing dependency 'boto3'. Install it with: pip install boto3"
        ) from exc

    access_key = get_required_env("AWS_ACCESS_KEY_ID")
    secret_key = get_required_env("AWS_SECRET_ACCESS_KEY")
    region = get_required_env("AWS_REGION")
    session_token = os.getenv("AWS_SESSION_TOKEN", "").strip() or None

    session = boto3.Session(
        aws_access_key_id=access_key,
        aws_secret_access_key=secret_key,
        aws_session_token=session_token,
        region_name=region,
    )
    return session.client("s3")


def list_object_keys(s3_client, bucket_name: str, prefix: str = "") -> list[str]:
    paginator = s3_client.get_paginator("list_objects_v2")
    page_iterator = paginator.paginate(Bucket=bucket_name, Prefix=prefix)

    keys: list[str] = []
    for page in page_iterator:
        contents = page.get("Contents", [])
        keys.extend(item["Key"] for item in contents)

    return keys


def delete_object_batch(s3_client, bucket_name: str, keys: list[str]) -> tuple[int, int]:
    response = s3_client.delete_objects(
        Bucket=bucket_name,
        Delete={"Objects": [{"Key": key} for key in keys], "Quiet": True},
    )

    deleted_count = len(response.get("Deleted", []))
    error_count = len(response.get("Errors", []))
    return deleted_count, error_count


def delete_all_objects(s3_client, bucket_name: str, prefix: str = "") -> tuple[int, int]:
    keys = list_object_keys(s3_client, bucket_name, prefix)

    if not keys:
        print("No objects found to delete.")
        return 0, 0

    total_deleted = 0
    total_errors = 0

    for start in range(0, len(keys), MAX_DELETE_BATCH_SIZE):
        batch = keys[start : start + MAX_DELETE_BATCH_SIZE]
        deleted_count, error_count = delete_object_batch(s3_client, bucket_name, batch)
        total_deleted += deleted_count
        total_errors += error_count

    return total_deleted, total_errors


def confirm_deletion(bucket_name: str, prefix: str, object_count: int) -> bool:
    scope = f"prefix '{prefix}'" if prefix else "entire bucket"
    print(
        f"About to delete {object_count} object(s) from bucket '{bucket_name}' ({scope})."
    )
    answer = input("Type 'delete' to continue: ").strip().lower()
    return answer == "delete"


def main() -> int:
    args = parse_args()
    load_dotenv()

    try:
        s3_client = build_s3_client()
        keys = list_object_keys(s3_client, args.bucket, args.prefix)
    except Exception as exc:
        print(f"Error connecting to S3 or listing objects: {exc}")
        return 1

    if not keys:
        print("No objects found to delete.")
        return 0

    if not args.yes and not confirm_deletion(args.bucket, args.prefix, len(keys)):
        print("Cancelled. No objects were deleted.")
        return 0

    try:
        deleted_count, error_count = delete_all_objects(
            s3_client,
            args.bucket,
            args.prefix,
        )
    except Exception as exc:
        print(f"Error deleting objects: {exc}")
        return 1

    print(f"Deleted objects: {deleted_count}")
    if error_count > 0:
        print(f"Objects with errors: {error_count}")
        return 2

    print("Bucket cleanup completed successfully.")
    return 0


if __name__ == "__main__":
    sys.exit(main())

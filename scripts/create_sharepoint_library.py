"""Create a document library (default name: CPN) on the configured SharePoint site.

Reuses the existing ``SharePointGraphClient`` (client-credentials auth against Microsoft
Graph, configured via the same SHAREPOINT_*/OUTLOOK_* env vars as the FastAPI app).
The Entra app needs the Graph application permission ``Sites.ReadWrite.All``.

Usage:
    python scripts/create_sharepoint_library.py              # dry run for "CPN"
    python scripts/create_sharepoint_library.py --name CPN --apply

Without --apply, the script only reports whether the library already exists.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from src.integrations.sharepoint.client import (  # noqa: E402
    SharePointClientError,
    SharePointGraphClient,
)


def main() -> int:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument("--name", default="CPN", help="Library display name (default: CPN).")
    parser.add_argument("--description", default=None, help="Optional library description.")
    parser.add_argument(
        "--apply",
        action="store_true",
        help="Create the library. Without this flag, only a dry-run report is printed.",
    )
    args = parser.parse_args()

    client = SharePointGraphClient()

    try:
        existing = client.find_drive_by_name(args.name)
        if existing is not None:
            print(f"Library {args.name!r} already exists: {existing.get('webUrl')}")
            print(f"  drive id: {existing.get('id')}")
            return 0

        if not args.apply:
            print(f"Library {args.name!r} does not exist. Re-run with --apply to create it.")
            return 0

        drive = client.create_document_library(args.name, args.description)
    except SharePointClientError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1

    print(f"Created library {drive.get('name', args.name)!r}")
    print(f"  drive id: {drive.get('id')}")
    print(f"  url:      {drive.get('webUrl')}")
    return 0


if __name__ == "__main__":
    sys.exit(main())

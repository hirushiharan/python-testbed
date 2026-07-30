"""Rename every file and folder in a SharePoint document library to a target naming convention.

Reuses the existing ``SharePointGraphClient`` (client-credentials auth against Microsoft
Graph, configured via the same SHAREPOINT_*/OUTLOOK_* env vars as the FastAPI app).

Usage:
    python scripts/rename_sharepoint_items.py --convention snake_case
    python scripts/rename_sharepoint_items.py --convention pascal_case --root-folder-id <id>
    python scripts/rename_sharepoint_items.py --convention kebab_case --apply

Without --apply, the script only prints a dry-run report of the renames it would perform.
"""

from __future__ import annotations

import argparse
import os
import re
import sys
from pathlib import Path
from typing import Any, Callable

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from src.integrations.sharepoint.client import SharePointClientError, SharePointGraphClient  # noqa: E402

_SEPARATOR_RE = re.compile(r"[\s_\-]+")
_LOWER_UPPER_BOUNDARY_RE = re.compile(r"(?<=[a-z0-9])(?=[A-Z])")
_ACRONYM_BOUNDARY_RE = re.compile(r"(?<=[A-Z])(?=[A-Z][a-z])")


def tokenize(name: str) -> list[str]:
    """Split an arbitrary item name into naming-convention-agnostic word tokens."""

    normalized = _SEPARATOR_RE.sub(" ", name.strip())
    normalized = _ACRONYM_BOUNDARY_RE.sub(" ", normalized)
    normalized = _LOWER_UPPER_BOUNDARY_RE.sub(" ", normalized)
    return [token for token in normalized.split(" ") if token]


NAMING_STRATEGIES: dict[str, Callable[[list[str]], str]] = {
    "snake_case": lambda tokens: "_".join(t.lower() for t in tokens),
    "kebab_case": lambda tokens: "-".join(t.lower() for t in tokens),
    "camel_case": lambda tokens: (tokens[0].lower() + "".join(t.capitalize() for t in tokens[1:])) if tokens else "",
    "pascal_case": lambda tokens: "".join(t.capitalize() for t in tokens),
    "title_case": lambda tokens: " ".join(t.capitalize() for t in tokens),
    "constant_case": lambda tokens: "_".join(t.upper() for t in tokens),
    "lower_case": lambda tokens: " ".join(t.lower() for t in tokens),
    "upper_case": lambda tokens: " ".join(t.upper() for t in tokens),
}


def apply_naming_convention(original_name: str, convention: str, *, is_folder: bool) -> str:
    """Rewrite ``original_name`` using ``convention``, leaving file extensions untouched."""

    strategy = NAMING_STRATEGIES[convention]
    stem, extension = (original_name, "") if is_folder else os.path.splitext(original_name)

    tokens = tokenize(stem)
    if not tokens:
        return original_name

    new_stem = strategy(tokens)
    return f"{new_stem}{extension}" if extension else new_stem


def iter_tree(client: SharePointGraphClient, folder_id: str, path: str = ""):
    """Depth-first walk of a SharePoint folder, yielding (item, display_path) pairs."""

    for item in client.list_children(folder_id):
        name = str(item.get("name", "")).strip()
        item_path = f"{path}/{name}" if path else name
        yield item, item_path

        if item.get("folder") is not None:
            yield from iter_tree(client, str(item.get("id", "")), item_path)


def build_rename_plan(
    client: SharePointGraphClient,
    root_folder_id: str,
    convention: str,
    target: str = "both",
) -> list[dict[str, Any]]:
    plan: list[dict[str, Any]] = []

    for item, path in iter_tree(client, root_folder_id):
        is_folder = item.get("folder") is not None
        if target == "files" and is_folder:
            continue
        if target == "folders" and not is_folder:
            continue

        original_name = str(item.get("name", "")).strip()
        new_name = apply_naming_convention(original_name, convention, is_folder=is_folder)

        if new_name and new_name != original_name:
            plan.append(
                {
                    "id": str(item.get("id", "")),
                    "path": path,
                    "old_name": original_name,
                    "new_name": new_name,
                    "is_folder": is_folder,
                }
            )

    return plan


def apply_rename_plan(client: SharePointGraphClient, plan: list[dict[str, Any]]) -> list[dict[str, Any]]:
    results: list[dict[str, Any]] = []

    for entry in plan:
        try:
            client.rename_item(entry["id"], entry["new_name"])
        except SharePointClientError as exc:
            results.append({**entry, "status": "failed", "error": str(exc)})
        else:
            results.append({**entry, "status": "renamed"})

    return results


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument(
        "--library",
        default=None,
        help="Name of the document library to target, e.g. 'Projects' (default: the library from SHAREPOINT_DRIVE_ID/site default).",
    )
    root_group = parser.add_mutually_exclusive_group()
    root_group.add_argument(
        "--root-folder-id",
        default=None,
        help="Graph item ID of the folder to start from (default: the drive root).",
    )
    root_group.add_argument(
        "--root-folder-path",
        default=None,
        help="Folder path relative to the drive root, e.g. 'OSG' or 'OSG/Cash Flow Reporting'.",
    )
    parser.add_argument(
        "--convention",
        required=True,
        choices=sorted(NAMING_STRATEGIES),
        help="Target naming convention to apply to every file and folder name.",
    )
    parser.add_argument(
        "--target",
        choices=["files", "folders", "both"],
        default="both",
        help="Limit renaming to files only, folders only, or both (default: both). Folders are still traversed either way.",
    )
    parser.add_argument(
        "--apply",
        action="store_true",
        help="Perform the renames. Without this flag, only a dry-run report is printed.",
    )
    args = parser.parse_args()

    client = SharePointGraphClient()

    if args.library:
        client.use_drive(client.resolve_drive_id_by_name(args.library))

    if args.root_folder_path:
        root_folder_id = client.get_item_id_by_path(args.root_folder_path)
    else:
        root_folder_id = args.root_folder_id or "root"

    plan = build_rename_plan(client, root_folder_id, args.convention, target=args.target)

    if not plan:
        print("No items require renaming.")
        return

    print(f"{len(plan)} item(s) would be renamed:\n")
    for entry in plan:
        kind = "folder" if entry["is_folder"] else "file"
        print(f"  [{kind}] {entry['path']} -> {entry['new_name']}")

    if not args.apply:
        print("\nDry run only. Re-run with --apply to perform these renames.")
        return

    print("\nApplying renames...")
    results = apply_rename_plan(client, plan)
    succeeded = [r for r in results if r["status"] == "renamed"]
    failed = [r for r in results if r["status"] == "failed"]

    print(f"\n{len(succeeded)} renamed, {len(failed)} failed.")
    for r in failed:
        print(f"  FAILED: {r['path']} -> {r['new_name']}: {r['error']}")


if __name__ == "__main__":
    main()

"""Create directory and file scaffolding from a JSON structure definition."""

import argparse
import json
import logging
import sys
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)


def configure_logging(verbose: bool) -> None:
    """Configure console logging for script execution."""
    level = logging.DEBUG if verbose else logging.INFO
    logging.basicConfig(level=level, format="%(levelname)s: %(message)s")


def validate_structure(data: Any) -> dict[str, Any]:
    """Validate input JSON format.

    Expected format is one top-level key representing the project root.
    """
    if not isinstance(data, dict):
        raise ValueError("JSON root must be an object")
    if len(data) != 1:
        raise ValueError("JSON must contain exactly one top-level key (project root)")
    return data


def write_file(path: Path, content: str, overwrite: bool) -> None:
    """Create or overwrite a file, based on overwrite policy."""
    if path.exists() and not overwrite:
        raise FileExistsError(f"File already exists: {path}")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")


def create_structure(base_path: Path, structure: dict[str, Any], overwrite: bool) -> None:
    """Recursively create directories and files from a dictionary definition."""
    base_path.mkdir(parents=True, exist_ok=True)

    for name, content in structure.items():
        target = base_path / name

        if isinstance(content, dict):
            logger.debug("Creating directory: %s", target)
            target.mkdir(parents=True, exist_ok=True)
            create_structure(target, content, overwrite)
            continue

        if isinstance(content, str):
            logger.debug("Creating file: %s", target)
            write_file(target, content, overwrite)
            continue

        if content is None:
            logger.debug("Creating empty directory: %s", target)
            target.mkdir(parents=True, exist_ok=True)
            continue

        raise ValueError(
            f"Unsupported JSON value type for '{name}': {type(content).__name__}"
        )


def parse_args() -> argparse.Namespace:
    """Parse command-line arguments."""
    parser = argparse.ArgumentParser(
        description="Create a directory and file structure from a JSON description"
    )
    parser.add_argument(
        "json_file",
        type=Path,
        help="Path to the JSON file that describes the structure",
    )
    parser.add_argument(
        "output_dir",
        type=Path,
        nargs="?",
        default=Path("."),
        help="Output directory where the structure should be created (default: current directory)",
    )
    parser.add_argument(
        "--overwrite",
        action="store_true",
        help="Overwrite existing files",
    )
    parser.add_argument(
        "--verbose",
        action="store_true",
        help="Enable debug logs",
    )
    return parser.parse_args()


def main() -> int:
    """Run structure creation command."""
    args = parse_args()
    configure_logging(verbose=args.verbose)

    try:
        input_json = json.loads(args.json_file.read_text(encoding="utf-8"))
        structure = validate_structure(input_json)
        create_structure(args.output_dir.resolve(), structure, args.overwrite)
    except FileNotFoundError as exc:
        logger.error("Input JSON file not found: %s", exc)
        return 1
    except json.JSONDecodeError as exc:
        logger.error("Invalid JSON in %s: %s", args.json_file, exc)
        return 1
    except (ValueError, FileExistsError, OSError) as exc:
        logger.error("Failed to create structure: %s", exc)
        return 1

    logger.info("Project structure created successfully")
    print("Project structure created successfully.")
    return 0


if __name__ == "__main__":
    sys.exit(main())

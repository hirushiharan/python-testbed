import argparse
import json
import sys
from pathlib import Path
from typing import Any


def validate_structure(data: Any) -> dict[str, Any]:
    if not isinstance(data, dict):
        raise ValueError("JSON root must be an object")
    if len(data) != 1:
        raise ValueError("JSON must contain exactly one top-level key (project root)")
    return data


def write_file(path: Path, content: str, overwrite: bool) -> None:
    if path.exists() and not overwrite:
        raise FileExistsError(f"File already exists: {path}")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")


def create_structure(base_path: Path, structure: dict[str, Any], overwrite: bool) -> None:
    base_path.mkdir(parents=True, exist_ok=True)

    for name, content in structure.items():
        target = base_path / name

        if isinstance(content, dict):
            target.mkdir(parents=True, exist_ok=True)
            create_structure(target, content, overwrite)
            continue

        if isinstance(content, str):
            write_file(target, content, overwrite)
            continue

        if content is None:
            target.mkdir(parents=True, exist_ok=True)
            continue

        raise ValueError(
            f"Unsupported JSON value type for '{name}': {type(content).__name__}"
        )


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Create a directory/file structure from a JSON description"
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
    return parser.parse_args()


def main() -> int:
    args = parse_args()

    try:
        data = json.loads(args.json_file.read_text(encoding="utf-8"))
        structure = validate_structure(data)
        create_structure(args.output_dir.resolve(), structure, args.overwrite)
    except FileNotFoundError as exc:
        print(f"Error: {exc}")
        return 1
    except json.JSONDecodeError as exc:
        print(f"Error: Invalid JSON in {args.json_file}: {exc}")
        return 1
    except (ValueError, FileExistsError, OSError) as exc:
        print(f"Error: {exc}")
        return 1

    print("Project structure created successfully.")
    return 0


if __name__ == "__main__":
    sys.exit(main())

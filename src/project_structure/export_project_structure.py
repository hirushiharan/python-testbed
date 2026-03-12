"""Export repository tree to a markdown-friendly text format."""

import argparse
import fnmatch
import logging
import sys
from pathlib import Path

DEFAULT_IGNORES = [".git/", "__pycache__/", "*.pyc"]

logger = logging.getLogger(__name__)


def configure_logging(verbose: bool) -> None:
    """Configure console logging for script execution."""
    level = logging.DEBUG if verbose else logging.INFO
    logging.basicConfig(level=level, format="%(levelname)s: %(message)s")


def read_gitignore_patterns(gitignore_path: Path | None) -> list[str]:
    """Read active ignore patterns from .gitignore file."""
    if not gitignore_path or not gitignore_path.exists():
        return []

    patterns: list[str] = []
    for raw_line in gitignore_path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if line and not line.startswith("#"):
            patterns.append(line)
    return patterns


def normalize_path(path: str) -> str:
    """Normalize path for cross-platform fnmatch operations."""
    return path.replace("\\", "/")


def is_ignored(rel_path: str, patterns: list[str]) -> bool:
    """Check whether a relative path should be excluded."""
    candidate = normalize_path(rel_path).strip("/")
    candidate_as_dir = f"{candidate}/" if candidate else ""

    for pattern in patterns:
        pat = normalize_path(pattern).strip()
        if not pat:
            continue

        if pat.endswith("/"):
            base = pat.strip("/")
            if candidate == base or candidate.startswith(base + "/"):
                return True
            continue

        if fnmatch.fnmatch(candidate, pat):
            return True
        if candidate_as_dir and fnmatch.fnmatch(candidate_as_dir, pat):
            return True
        if "/" not in pat and fnmatch.fnmatch(Path(candidate).name, pat):
            return True

    return False


def build_tree_lines(root: Path, ignore_patterns: list[str]) -> list[str]:
    """Build an indented tree representation as list of lines."""
    lines: list[str] = [f"{root.name}/"]

    def walk(current_dir: Path, depth: int) -> None:
        children = sorted(
            current_dir.iterdir(),
            key=lambda path: (path.is_file(), path.name.lower()),
        )
        for child in children:
            relative_path = normalize_path(str(child.relative_to(root)))
            if is_ignored(relative_path, ignore_patterns):
                continue

            indent = "    " * depth
            suffix = "/" if child.is_dir() else ""
            lines.append(f"{indent}{child.name}{suffix}")

            if child.is_dir():
                walk(child, depth + 1)

    walk(root, depth=1)
    return lines


def parse_args() -> argparse.Namespace:
    """Parse command-line arguments."""
    parser = argparse.ArgumentParser(
        description="Export project directory structure to a markdown file"
    )
    parser.add_argument(
        "root_dir",
        type=Path,
        nargs="?",
        default=Path("."),
        help="Project root directory (default: current directory)",
    )
    parser.add_argument(
        "-o",
        "--output",
        type=Path,
        default=Path("project_structure.md"),
        help="Output markdown file path (default: project_structure.md)",
    )
    parser.add_argument(
        "--no-gitignore",
        action="store_true",
        help="Do not apply .gitignore patterns",
    )
    parser.add_argument(
        "--ignore",
        action="append",
        default=[],
        help="Additional ignore pattern; can be passed multiple times",
    )
    parser.add_argument(
        "--verbose",
        action="store_true",
        help="Enable debug logs",
    )
    return parser.parse_args()


def main() -> int:
    """Run structure export command."""
    args = parse_args()
    configure_logging(verbose=args.verbose)
    root = args.root_dir.resolve()

    if not root.exists() or not root.is_dir():
        logger.error("Root directory does not exist or is not a directory: %s", root)
        return 1

    gitignore_path = None if args.no_gitignore else root / ".gitignore"
    ignore_patterns = read_gitignore_patterns(gitignore_path)
    ignore_patterns.extend(DEFAULT_IGNORES)
    ignore_patterns.extend(args.ignore)
    logger.debug("Using %d ignore patterns", len(ignore_patterns))

    try:
        tree_lines = build_tree_lines(root, ignore_patterns)
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text("\n".join(tree_lines) + "\n", encoding="utf-8")
    except OSError as exc:
        logger.error("Failed writing output file: %s", exc)
        return 1

    logger.info("Project structure exported to %s", args.output.resolve())
    print(f"Project structure exported to: {args.output.resolve()}")
    return 0


if __name__ == "__main__":
    sys.exit(main())

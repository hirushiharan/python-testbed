import argparse
import fnmatch
import sys
from pathlib import Path


DEFAULT_IGNORES = [
    ".git/",
    "__pycache__/",
    "*.pyc",
]


def read_gitignore_patterns(gitignore_path: Path | None) -> list[str]:
    if not gitignore_path:
        return []
    if not gitignore_path.exists():
        return []

    patterns: list[str] = []
    for raw in gitignore_path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        patterns.append(line)
    return patterns


def normalize(path: str) -> str:
    return path.replace("\\", "/")


def is_ignored(rel_path: str, patterns: list[str]) -> bool:
    candidate = normalize(rel_path).strip("/")
    candidate_dir = f"{candidate}/" if candidate else ""

    for pattern in patterns:
        pat = normalize(pattern).strip()
        if not pat:
            continue

        if pat.endswith("/"):
            base = pat.strip("/")
            if candidate == base or candidate.startswith(base + "/"):
                return True
            continue

        if fnmatch.fnmatch(candidate, pat):
            return True
        if candidate_dir and fnmatch.fnmatch(candidate_dir, pat):
            return True
        if "/" not in pat and fnmatch.fnmatch(Path(candidate).name, pat):
            return True

    return False


def build_tree_lines(root: Path, patterns: list[str]) -> list[str]:
    lines: list[str] = [f"{root.name}/"]

    def walk(current: Path, depth: int) -> None:
        children = sorted(current.iterdir(), key=lambda p: (p.is_file(), p.name.lower()))
        for child in children:
            rel = normalize(str(child.relative_to(root)))
            if is_ignored(rel, patterns):
                continue

            indent = "    " * depth
            suffix = "/" if child.is_dir() else ""
            lines.append(f"{indent}{child.name}{suffix}")

            if child.is_dir():
                walk(child, depth + 1)

    walk(root, depth=1)
    return lines


def parse_args() -> argparse.Namespace:
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
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    root = args.root_dir.resolve()

    if not root.exists() or not root.is_dir():
        print(f"Error: Root directory does not exist or is not a directory: {root}")
        return 1

    gitignore = None if args.no_gitignore else root / ".gitignore"
    patterns = read_gitignore_patterns(gitignore)
    patterns.extend(DEFAULT_IGNORES)
    patterns.extend(args.ignore)

    try:
        lines = build_tree_lines(root, patterns)
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text("\n".join(lines) + "\n", encoding="utf-8")
    except OSError as exc:
        print(f"Error: {exc}")
        return 1

    print(f"Project structure exported to: {args.output.resolve()}")
    return 0


if __name__ == "__main__":
    sys.exit(main())

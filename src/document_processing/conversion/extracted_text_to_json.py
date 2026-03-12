"""Escape plain text content as a JSON string."""

import argparse
import json
import logging
import sys
from pathlib import Path

logger = logging.getLogger(__name__)


def configure_logging(verbose: bool) -> None:
    """Configure console logging for script execution."""
    level = logging.DEBUG if verbose else logging.INFO
    logging.basicConfig(level=level, format="%(levelname)s: %(message)s")


def text_to_json_string(raw_text: str) -> str:
    """Return text encoded as a single JSON string value."""
    normalized_text = raw_text.strip()
    return json.dumps(normalized_text, ensure_ascii=False)


def convert_text_file_to_json_string(text_file_path: Path) -> str:
    """Read a UTF-8 text file and convert its content to JSON string form."""
    if not text_file_path.exists():
        raise FileNotFoundError(f"Input file not found: {text_file_path}")
    if text_file_path.suffix.lower() != ".txt":
        raise ValueError("Input file must be a .txt file")

    source_text = text_file_path.read_text(encoding="utf-8")
    return text_to_json_string(source_text)


def parse_args() -> argparse.Namespace:
    """Parse command-line arguments."""
    parser = argparse.ArgumentParser(
        description="Convert a .txt file into a JSON-escaped string"
    )
    parser.add_argument("input", type=Path, help="Path to input text file (.txt)")
    parser.add_argument(
        "-o",
        "--output",
        type=Path,
        help="Optional path to save JSON output (.json)",
    )
    parser.add_argument(
        "--verbose",
        action="store_true",
        help="Enable debug logs",
    )
    return parser.parse_args()


def main() -> int:
    """Run text-to-JSON conversion command."""
    args = parse_args()
    configure_logging(verbose=args.verbose)

    text_file_path = args.input.resolve()
    output_path = args.output.resolve() if args.output else None

    try:
        json_string = convert_text_file_to_json_string(text_file_path)
    except (FileNotFoundError, ValueError, UnicodeDecodeError, OSError) as exc:
        logger.error("Conversion failed: %s", exc)
        return 1

    if output_path:
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(json_string, encoding="utf-8")
        logger.info("Saved JSON output to %s", output_path)
        print(f"JSON saved: {output_path}")
    else:
        print(json_string)

    return 0


if __name__ == "__main__":
    sys.exit(main())

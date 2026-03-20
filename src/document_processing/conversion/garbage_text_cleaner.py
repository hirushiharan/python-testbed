"""Clean escaped or noisy text and output readable formatted text."""

import argparse
import json
import logging
import sys
from datetime import datetime
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)


def configure_logging(verbose: bool) -> None:
    """Configure console logging for script execution."""
    level = logging.DEBUG if verbose else logging.INFO
    logging.basicConfig(level=level, format="%(levelname)s: %(message)s")


def _try_parse_json_candidates(raw_text: str) -> Any:
    """Parse JSON from common escaped-text variants."""
    text = raw_text.strip()
    candidates = [text]

    if text and text[0] == text[-1] and text[0] in {"'", '"'}:
        candidates.append(text[1:-1])

    candidates.append(text.replace('\\"', '"'))

    try:
        candidates.append(bytes(text, "utf-8").decode("unicode_escape"))
    except UnicodeDecodeError:
        pass

    seen: set[str] = set()
    last_error: json.JSONDecodeError | None = None

    for candidate in candidates:
        if candidate in seen:
            continue
        seen.add(candidate)
        try:
            return json.loads(candidate)
        except json.JSONDecodeError as exc:
            last_error = exc

    if last_error:
        detail = (
            f"{last_error.msg} at line {last_error.lineno}, "
            f"column {last_error.colno}"
        )
    else:
        detail = "unknown parse error"
    raise ValueError(f"Input is not valid JSON-like text ({detail})")


def _clean_plain_text(raw_text: str) -> str:
    """Clean and lightly format non-JSON text content."""
    text = raw_text.replace("\ufeff", "")
    text = text.replace("\\n", "\n").replace("\\t", "\t")
    text = text.replace("\\\"", '"').replace("\\'", "'")
    lines = [line.rstrip() for line in text.splitlines()]

    cleaned_lines: list[str] = []
    previous_blank = False
    for line in lines:
        compact = " ".join(line.split())
        if not compact:
            if not previous_blank:
                cleaned_lines.append("")
            previous_blank = True
            continue

        cleaned_lines.append(compact)
        previous_blank = False

    return "\n".join(cleaned_lines).strip()


def _normalize_string(value: str) -> str:
    """Normalize string values by cleaning whitespace and date-like text."""
    trimmed = " ".join(value.split())
    try:
        parsed = datetime.fromisoformat(trimmed.replace("Z", "+00:00"))
        if parsed.hour == 0 and parsed.minute == 0 and parsed.second == 0:
            return parsed.date().isoformat()
        return parsed.isoformat()
    except ValueError:
        return trimmed


def _format_value(value: Any) -> str:
    """Convert Python values to user-friendly text."""
    if value is None:
        return "N/A"
    if isinstance(value, str):
        return _normalize_string(value)
    if isinstance(value, bool):
        return "Yes" if value else "No"
    if isinstance(value, (int, float)):
        return str(value)
    return json.dumps(value, ensure_ascii=False)


def _format_mapping(mapping: dict[str, Any], title: str) -> str:
    """Format one dictionary into a labeled text block."""
    lines = [title]
    lines.append("-" * len(title))
    for key, value in mapping.items():
        lines.append(f"{key}: {_format_value(value)}")
    return "\n".join(lines)


def clean_and_format_text(raw_text: str) -> str:
    """Return cleaned and formatted text from escaped JSON-like content."""
    try:
        parsed = _try_parse_json_candidates(raw_text)
    except ValueError:
        return _clean_plain_text(raw_text)

    if isinstance(parsed, list):
        blocks: list[str] = []
        for index, item in enumerate(parsed, start=1):
            if isinstance(item, dict):
                request_key = item.get("Request Key")
                heading = (
                    f"Record {index}"
                    if not request_key
                    else f"Record {index} ({request_key})"
                )
                blocks.append(_format_mapping(item, heading))
            else:
                blocks.append(f"Record {index}: {_format_value(item)}")
        return "\n\n".join(blocks)

    if isinstance(parsed, dict):
        title = str(parsed.get("Request Key", "Record"))
        return _format_mapping(parsed, title)

    return _format_value(parsed)


def parse_args() -> argparse.Namespace:
    """Parse command-line arguments."""
    parser = argparse.ArgumentParser(
        description="Clean escaped or noisy text and output readable formatted text"
    )
    source_group = parser.add_mutually_exclusive_group(required=True)
    source_group.add_argument(
        "--text",
        help="Raw garbage text input (for direct paste)",
    )
    source_group.add_argument(
        "--input",
        type=Path,
        help="Path to UTF-8 text file containing raw garbage text",
    )
    parser.add_argument(
        "-o",
        "--output",
        type=Path,
        help="Optional path to save cleaned text output",
    )
    parser.add_argument(
        "--verbose",
        action="store_true",
        help="Enable debug logs",
    )
    return parser.parse_args()


def main() -> int:
    """Run garbage-text cleaning command."""
    args = parse_args()
    configure_logging(verbose=args.verbose)

    try:
        if args.text is not None:
            raw_text = args.text
        else:
            input_path = args.input.resolve()
            if not input_path.exists():
                raise FileNotFoundError(f"Input file not found: {input_path}")
            raw_text = input_path.read_text(encoding="utf-8")

        cleaned_text = clean_and_format_text(raw_text)
    except (FileNotFoundError, UnicodeDecodeError, OSError) as exc:
        logger.error("Text cleaning failed: %s", exc)
        return 1

    if args.output:
        output_path = args.output.resolve()
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(cleaned_text, encoding="utf-8")
        logger.info("Saved cleaned output to %s", output_path)
        print(f"Cleaned text saved: {output_path}")
    else:
        print(cleaned_text)

    return 0


if __name__ == "__main__":
    sys.exit(main())

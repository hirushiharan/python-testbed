import argparse
import json
import sys
from pathlib import Path


def format_extracted_text_to_json(
    text: str,
    *,
    title: str | None = None,
    source: str | None = None,
) -> str:
    normalized_text = text.strip()
    payload = {
        "title": title or "extracted_text",
        "source": source,
        "text": normalized_text,
        "size": len(normalized_text),
    }
    return json.dumps(payload, ensure_ascii=False, indent=2)


def text_file_to_json(input_path: Path, *, title: str | None = None) -> str:
    if not input_path.exists():
        raise FileNotFoundError(f"Input file not found: {input_path}")
    if input_path.suffix.lower() != ".txt":
        raise ValueError("Input file must be a .txt file")

    extracted_text = input_path.read_text(encoding="utf-8")
    return format_extracted_text_to_json(
        extracted_text,
        title=title or input_path.stem,
        source=str(input_path),
    )


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Format extracted text from a .txt file into proper JSON"
    )
    parser.add_argument("input", type=Path, help="Path to input text file (.txt)")
    parser.add_argument(
        "-o",
        "--output",
        type=Path,
        help="Optional path to save JSON output (.json)",
    )
    parser.add_argument(
        "--title",
        type=str,
        help="Optional title override for the JSON payload",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()

    input_path = args.input.resolve()
    output_path = args.output.resolve() if args.output else None

    try:
        json_text = text_file_to_json(input_path, title=args.title)
    except (FileNotFoundError, ValueError, RuntimeError, UnicodeDecodeError) as exc:
        print(f"Error: {exc}")
        return 1

    if output_path:
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(json_text, encoding="utf-8")
        print(f"JSON saved: {output_path}")
    else:
        print(json_text)

    return 0


if __name__ == "__main__":
    sys.exit(main())

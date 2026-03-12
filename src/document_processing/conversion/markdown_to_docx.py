import argparse
import pypandoc
import sys
from pathlib import Path


def convert_markdown_to_docx(input_path: Path, output_path: Path) -> None:

    if not input_path.exists():
        raise FileNotFoundError(f"Input file not found: {input_path}")
    if input_path.suffix.lower() != ".md":
        raise ValueError("Input file must be a .md file")

    output_path.parent.mkdir(parents=True, exist_ok=True)

    pypandoc.convert_file(
        str(input_path),
        to="docx",
        format="md",
        outputfile=str(output_path),
    )


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Convert Markdown to DOCX while preserving content and applying formatting "
            "(tables, symbols, colors) through the DOCX conversion pipeline."
        )
    )
    parser.add_argument("input", type=Path, help="Path to input Markdown (.md) file")
    parser.add_argument(
        "-o",
        "--output",
        type=Path,
        help="Path to output DOCX file (default: same name as input with .docx)",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()

    input_path = args.input.resolve()
    output_path = (
        args.output.resolve() if args.output else input_path.with_suffix(".docx")
    )

    try:
        convert_markdown_to_docx(input_path, output_path)
    except (FileNotFoundError, ValueError, RuntimeError) as exc:
        print(f"Error: {exc}")
        return 1

    print(f"Converted: {input_path}")
    print(f"Saved DOCX: {output_path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())

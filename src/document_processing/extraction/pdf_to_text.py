import argparse
import sys
from io import BytesIO
from pathlib import Path

from pypdf import PdfReader


def extract_text_from_pdf(pdf_path: Path) -> str:
    if not pdf_path.exists():
        raise FileNotFoundError(f"Input file not found: {pdf_path}")
    if pdf_path.suffix.lower() != ".pdf":
        raise ValueError("Input file must be a .pdf file")

    reader = PdfReader(str(pdf_path))
    pages_text = [page.extract_text() or "" for page in reader.pages]
    return "\n".join(pages_text).strip()


def extract_text_from_pdf_bytes(file_bytes: bytes) -> str:
    reader = PdfReader(BytesIO(file_bytes))
    pages_text = [page.extract_text() or "" for page in reader.pages]
    return "\n".join(pages_text).strip()


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Extract text content from a PDF file")
    parser.add_argument("input", type=Path, help="Path to input PDF (.pdf) file")
    parser.add_argument(
        "-o",
        "--output",
        type=Path,
        help="Optional path to save extracted text (.txt)",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()

    input_path = args.input.resolve()
    output_path = args.output.resolve() if args.output else None

    try:
        extracted_text = extract_text_from_pdf(input_path)
    except (FileNotFoundError, ValueError, RuntimeError) as exc:
        print(f"Error: {exc}")
        return 1

    if output_path:
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(extracted_text, encoding="utf-8")
        print(f"Extracted text saved: {output_path}")
    else:
        print(extracted_text)

    return 0


if __name__ == "__main__":
    sys.exit(main())

"""Extract plain text from PDF documents."""

import argparse
import logging
import sys
from io import BytesIO
from pathlib import Path

logger = logging.getLogger(__name__)


def configure_logging(verbose: bool) -> None:
    """Configure console logging for script execution."""
    level = logging.DEBUG if verbose else logging.INFO
    logging.basicConfig(level=level, format="%(levelname)s: %(message)s")


def extract_text_from_pdf(pdf_path: Path) -> str:
    """Extract text from a PDF file on disk."""
    try:
        from pypdf import PdfReader
    except ImportError as exc:
        raise RuntimeError(
            "Missing dependency 'pypdf'. Install it with: pip install pypdf"
        ) from exc

    if not pdf_path.exists():
        raise FileNotFoundError(f"Input file not found: {pdf_path}")
    if pdf_path.suffix.lower() != ".pdf":
        raise ValueError("Input file must be a .pdf file")

    reader = PdfReader(str(pdf_path))
    pages_text = [page.extract_text() or "" for page in reader.pages]
    return "\n".join(pages_text).strip()


def extract_text_from_pdf_bytes(pdf_bytes: bytes) -> str:
    """Extract text from an in-memory PDF byte buffer."""
    try:
        from pypdf import PdfReader
    except ImportError as exc:
        raise RuntimeError(
            "Missing dependency 'pypdf'. Install it with: pip install pypdf"
        ) from exc

    reader = PdfReader(BytesIO(pdf_bytes))
    pages_text = [page.extract_text() or "" for page in reader.pages]
    return "\n".join(pages_text).strip()


def parse_args() -> argparse.Namespace:
    """Parse command-line arguments."""
    parser = argparse.ArgumentParser(description="Extract text content from a PDF file")
    parser.add_argument("input", type=Path, help="Path to input PDF (.pdf) file")
    parser.add_argument(
        "-o",
        "--output",
        type=Path,
        help="Optional path to save extracted text (.txt)",
    )
    parser.add_argument(
        "--verbose",
        action="store_true",
        help="Enable debug logs",
    )
    return parser.parse_args()


def main() -> int:
    """Run PDF extraction command."""
    args = parse_args()
    configure_logging(verbose=args.verbose)

    input_path = args.input.resolve()
    output_path = args.output.resolve() if args.output else None

    try:
        extracted_text = extract_text_from_pdf(input_path)
    except (FileNotFoundError, ValueError, RuntimeError, OSError) as exc:
        logger.error("Extraction failed: %s", exc)
        return 1

    if output_path:
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(extracted_text, encoding="utf-8")
        logger.info("Saved extracted text to %s", output_path)
        print(f"Extracted text saved: {output_path}")
    else:
        print(extracted_text)

    return 0


if __name__ == "__main__":
    sys.exit(main())

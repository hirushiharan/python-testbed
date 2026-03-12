"""Convert Markdown documents to DOCX format."""

import argparse
import logging
import sys
from pathlib import Path

logger = logging.getLogger(__name__)


def configure_logging(verbose: bool) -> None:
    """Configure console logging for script execution."""
    level = logging.DEBUG if verbose else logging.INFO
    logging.basicConfig(level=level, format="%(levelname)s: %(message)s")


def convert_markdown_to_docx(markdown_path: Path, docx_path: Path) -> None:
    """Convert a markdown file into DOCX using pandoc backend."""
    try:
        import pypandoc
    except ImportError as exc:
        raise RuntimeError(
            "Missing dependency 'pypandoc-binary'. Install it with: pip install pypandoc-binary"
        ) from exc

    if not markdown_path.exists():
        raise FileNotFoundError(f"Input file not found: {markdown_path}")
    if markdown_path.suffix.lower() != ".md":
        raise ValueError("Input file must be a .md file")

    docx_path.parent.mkdir(parents=True, exist_ok=True)
    pypandoc.convert_file(
        str(markdown_path),
        to="docx",
        format="md",
        outputfile=str(docx_path),
    )


def parse_args() -> argparse.Namespace:
    """Parse command-line arguments."""
    parser = argparse.ArgumentParser(
        description="Convert a Markdown file (.md) into a Word document (.docx)"
    )
    parser.add_argument("input", type=Path, help="Path to input Markdown (.md) file")
    parser.add_argument(
        "-o",
        "--output",
        type=Path,
        help="Path to output DOCX file (default: same file name with .docx extension)",
    )
    parser.add_argument(
        "--verbose",
        action="store_true",
        help="Enable debug logs",
    )
    return parser.parse_args()


def main() -> int:
    """Run markdown to DOCX conversion command."""
    args = parse_args()
    configure_logging(verbose=args.verbose)

    markdown_path = args.input.resolve()
    docx_path = args.output.resolve() if args.output else markdown_path.with_suffix(".docx")

    try:
        convert_markdown_to_docx(markdown_path, docx_path)
    except (FileNotFoundError, ValueError, RuntimeError, OSError) as exc:
        logger.error("Conversion failed: %s", exc)
        return 1

    logger.info("Converted markdown file: %s", markdown_path)
    logger.info("Saved DOCX file: %s", docx_path)
    print(f"Saved DOCX: {docx_path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())

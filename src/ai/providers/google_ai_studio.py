"""List available Google AI Studio models.

This script queries Google GenAI model catalog and prints model identifiers,
either as plain text or JSON.
"""

import argparse
import json
import logging
import os
import sys
from pathlib import Path

from dotenv import load_dotenv

logger = logging.getLogger(__name__)


def configure_logging(verbose: bool) -> None:
    """Configure console logging for script execution."""
    level = logging.DEBUG if verbose else logging.INFO
    logging.basicConfig(level=level, format="%(levelname)s: %(message)s")


def parse_args() -> argparse.Namespace:
    """Parse command-line arguments."""
    parser = argparse.ArgumentParser(description="List available Google AI Studio models")
    parser.add_argument(
        "--json",
        action="store_true",
        help="Print output as JSON array",
    )
    parser.add_argument(
        "-o",
        "--output",
        type=Path,
        help="Optional file path to write output",
    )
    parser.add_argument(
        "--verbose",
        action="store_true",
        help="Enable debug logs",
    )
    return parser.parse_args()


def normalize_model_name(raw_name: str) -> str:
    """Normalize Google model name to provider-prefixed form."""
    if raw_name.startswith("models/"):
        return "google/" + raw_name[len("models/") :]
    return raw_name


def fetch_model_names(api_key: str) -> list[str]:
    """Fetch all model names visible to the API key."""
    try:
        from google import genai
    except ImportError as exc:
        raise RuntimeError(
            "Missing dependency 'google-genai'. Install it with: pip install google-genai"
        ) from exc

    client = genai.Client(api_key=api_key)
    model_names: list[str] = []

    for model in client.models.list():
        raw_name = getattr(model, "name", "")
        if not raw_name:
            continue
        model_names.append(normalize_model_name(raw_name))

    model_names.sort()
    return model_names


def render_output(model_names: list[str], as_json: bool) -> str:
    """Render model list in plain text or JSON format."""
    if as_json:
        return json.dumps({"models": model_names}, indent=2)
    return "\n".join(model_names)


def main() -> int:
    """Run model-list command."""
    args = parse_args()
    configure_logging(verbose=args.verbose)
    load_dotenv()

    api_key = os.getenv("GOOGLE_API_KEY", "").strip()
    if not api_key:
        logger.error("Missing GOOGLE_API_KEY environment variable")
        return 1

    try:
        model_names = fetch_model_names(api_key)
    except Exception as exc:
        logger.error("Failed to query Google AI Studio models: %s", exc)
        return 1

    output_text = render_output(model_names, as_json=args.json)

    if args.output:
        try:
            args.output.parent.mkdir(parents=True, exist_ok=True)
            args.output.write_text(output_text + "\n", encoding="utf-8")
        except OSError as exc:
            logger.error("Failed writing output file: %s", exc)
            return 1
        logger.info("Wrote %d models to %s", len(model_names), args.output)
    else:
        print(output_text)

    return 0


if __name__ == "__main__":
    sys.exit(main())

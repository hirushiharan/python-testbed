"""Minimal Anthropic terminal chat client.

This script sends one user message at a time to Anthropic Messages API and
prints the first text response. It is intentionally simple and synchronous so
it can be used as a reference script.
"""

import argparse
import json
import logging
import os
import sys
import urllib.error
import urllib.request
from typing import Any

from dotenv import load_dotenv

API_URL = "https://api.anthropic.com/v1/messages"
DEFAULT_MODEL = "claude-3-5-sonnet-20240620"
ANTHROPIC_VERSION = "2023-06-01"
REQUEST_TIMEOUT_SECONDS = 60

logger = logging.getLogger(__name__)


def configure_logging(verbose: bool) -> None:
    """Configure console logging for script execution."""
    level = logging.DEBUG if verbose else logging.INFO
    logging.basicConfig(level=level, format="%(levelname)s: %(message)s")


def build_request_payload(user_message: str, model_name: str) -> dict[str, Any]:
    """Build request payload for Anthropic Messages API."""
    return {
        "model": model_name,
        "max_tokens": 512,
        "messages": [{"role": "user", "content": user_message}],
    }


def send_message(api_key: str, model_name: str, user_message: str) -> dict[str, Any]:
    """Send a single message to Anthropic and return the decoded JSON response."""
    payload = build_request_payload(user_message, model_name)
    request_body = json.dumps(payload).encode("utf-8")
    request = urllib.request.Request(API_URL, data=request_body, method="POST")
    request.add_header("x-api-key", api_key)
    request.add_header("anthropic-version", ANTHROPIC_VERSION)
    request.add_header("content-type", "application/json")

    try:
        with urllib.request.urlopen(request, timeout=REQUEST_TIMEOUT_SECONDS) as response:
            body = response.read().decode("utf-8")
            logger.debug("Anthropic response body length: %d", len(body))
            return json.loads(body)
    except urllib.error.HTTPError as exc:
        body = exc.read().decode("utf-8") if exc.fp else ""
        raise RuntimeError(f"HTTP {exc.code}: {body or exc.reason}") from exc
    except urllib.error.URLError as exc:
        raise RuntimeError(f"Network error: {exc.reason}") from exc


def extract_text_reply(api_response: dict[str, Any]) -> str:
    """Extract first text block from Anthropic response payload."""
    content_blocks = api_response.get("content") or []
    if not content_blocks:
        return "(empty response)"

    first_block = content_blocks[0] if isinstance(content_blocks, list) else content_blocks
    if isinstance(first_block, dict):
        return first_block.get("text") or "(empty response)"
    return str(first_block)


def parse_args() -> argparse.Namespace:
    """Parse command-line arguments."""
    parser = argparse.ArgumentParser(description="Anthropic terminal chat client")
    parser.add_argument(
        "--verbose",
        action="store_true",
        help="Enable debug logs",
    )
    return parser.parse_args()


def main() -> int:
    """Run interactive Anthropic chat loop."""
    args = parse_args()
    configure_logging(verbose=args.verbose)
    load_dotenv()

    api_key = os.getenv("ANTHROPIC_API_KEY", "").strip()
    if not api_key:
        logger.error("Missing ANTHROPIC_API_KEY environment variable")
        print("Set ANTHROPIC_API_KEY in .env or your shell and re-run.")
        return 1

    model_name = os.getenv("ANTHROPIC_MODEL", DEFAULT_MODEL).strip() or DEFAULT_MODEL
    logger.info("Starting Anthropic chat with model: %s", model_name)
    print("Anthropic quick chat (Ctrl+C to exit)")
    print(f"Model: {model_name}")

    while True:
        try:
            user_message = input("You> ").strip()
        except (EOFError, KeyboardInterrupt):
            print("\nBye.")
            return 0

        if not user_message:
            continue

        try:
            api_response = send_message(api_key, model_name, user_message)
            assistant_reply = extract_text_reply(api_response)
            print(f"Claude> {assistant_reply}")
        except RuntimeError as exc:
            logger.error("Request failed: %s", exc)
            return 1


if __name__ == "__main__":
    sys.exit(main())

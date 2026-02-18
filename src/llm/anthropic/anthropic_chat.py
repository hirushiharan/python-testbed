import json
import os
import sys
import urllib.error
import urllib.request
from dotenv import load_dotenv

load_dotenv()

API_URL = "https://api.anthropic.com/v1/messages"
DEFAULT_MODEL = "claude-3-5-sonnet-20240620"
ANTHROPIC_VERSION = "2023-06-01"


def build_payload(message: str, model: str) -> dict:
    return {
        "model": model,
        "max_tokens": 512,
        "messages": [
            {"role": "user", "content": message},
        ],
    }


def send_request(api_key: str, model: str, message: str) -> dict:
    payload = build_payload(message, model)
    data = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(API_URL, data=data, method="POST")
    req.add_header("x-api-key", api_key)
    req.add_header("anthropic-version", ANTHROPIC_VERSION)
    req.add_header("content-type", "application/json")

    try:
        with urllib.request.urlopen(req, timeout=60) as resp:
            body = resp.read().decode("utf-8")
            return json.loads(body)
    except urllib.error.HTTPError as exc:
        body = exc.read().decode("utf-8") if exc.fp else ""
        raise RuntimeError(f"HTTP {exc.code}: {body or exc.reason}") from exc
    except urllib.error.URLError as exc:
        raise RuntimeError(f"Network error: {exc.reason}") from exc


def extract_reply(response: dict) -> str:
    content = response.get("content") or []
    if not content:
        return "(empty response)"
    first = content[0] if isinstance(content, list) else content
    if isinstance(first, dict):
        return first.get("text") or "(empty response)"
    return str(first)


def main() -> int:
    api_key = os.getenv("CLAUDE_API_KEY")
    if not api_key:
        print("Missing ANTHROPIC_API_KEY env var.")
        print("Set it and re-run, e.g.: setx ANTHROPIC_API_KEY your_key")
        return 1

    model = os.getenv("ANTHROPIC_MODEL", DEFAULT_MODEL)

    print("Anthropic quick chat (Ctrl+C to exit)")
    print(f"Model: {model}")

    while True:
        try:
            message = input("You> ").strip()
        except (EOFError, KeyboardInterrupt):
            print("\nBye.")
            return 0

        if not message:
            continue

        try:
            response = send_request(api_key, model, message)
            reply = extract_reply(response)
            print(f"Claude> {reply}")
        except RuntimeError as exc:
            print(f"Error: {exc}")
            return 1


if __name__ == "__main__":
    sys.exit(main())

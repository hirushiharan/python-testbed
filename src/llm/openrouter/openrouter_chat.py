import json
import os
import sys
import urllib.error
import urllib.request
from dotenv import load_dotenv

load_dotenv()

API_URL = "https://openrouter.ai/api/v1/chat/completions"
DEFAULT_MODEL = "anthropic/claude-4.6-opus"


def build_payload(message: str, model: str) -> dict:
    return {
        "model": model,
        "messages": [
            {"role": "user", "content": message},
        ],
    }


def send_request(api_key: str, model: str, message: str) -> dict:
    payload = build_payload(message, model)
    data = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(API_URL, data=data, method="POST")
    req.add_header("Authorization", f"Bearer {api_key}")
    req.add_header("Content-Type", "application/json")
    # OpenRouter docs recommend identifying your app.
    req.add_header("X-Title", "OpenRouter Terminal Chat")

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
    choices = response.get("choices") or []
    if not choices:
        return "(no response choices)"
    message = choices[0].get("message") or {}
    return message.get("content") or "(empty response)"


def main() -> int:
    api_key = os.getenv("OPENROUTER_API_KEY")
    if not api_key:
        print("Missing OPENROUTER_API_KEY env var.")
        print("Set it and re-run, e.g.: setx OPENROUTER_API_KEY your_key")
        return 1

    model = os.getenv("OPENROUTER_MODEL", DEFAULT_MODEL)

    print("OpenRouter quick chat (Ctrl+C to exit)")
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

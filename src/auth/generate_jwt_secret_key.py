import argparse
import secrets
import string
import sys


def generate_secret_key(length: int) -> str:
    alphabet = string.ascii_letters + string.digits + "-._~"
    return "".join(secrets.choice(alphabet) for _ in range(length))


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Generate a JWT SECRET_KEY environment variable value"
    )
    parser.add_argument(
        "-l",
        "--length",
        type=int,
        default=64,
        help="Secret length (default: 64)",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()

    if args.length < 32:
        print("Error: length must be at least 32 for JWT secret strength")
        return 1

    secret_key = generate_secret_key(args.length)

    print("Generated JWT SECRET_KEY:")
    print(f"SECRET_KEY={secret_key}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
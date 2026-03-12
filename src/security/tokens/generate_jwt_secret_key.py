"""Generate cryptographically strong JWT secret values."""

import argparse
import logging
import secrets
import string
import sys

MIN_SECRET_LENGTH = 32
DEFAULT_SECRET_LENGTH = 64

logger = logging.getLogger(__name__)


def configure_logging(verbose: bool) -> None:
    """Configure console logging for script execution."""
    level = logging.DEBUG if verbose else logging.INFO
    logging.basicConfig(level=level, format="%(levelname)s: %(message)s")


def generate_jwt_secret(secret_length: int) -> str:
    """Generate URL-safe secret text with configurable length."""
    alphabet = string.ascii_letters + string.digits + "-._~"
    return "".join(secrets.choice(alphabet) for _ in range(secret_length))


def parse_args() -> argparse.Namespace:
    """Parse command-line arguments."""
    parser = argparse.ArgumentParser(
        description="Generate a JWT SECRET_KEY value for environment configuration"
    )
    parser.add_argument(
        "-l",
        "--length",
        type=int,
        default=DEFAULT_SECRET_LENGTH,
        help=f"Secret length (default: {DEFAULT_SECRET_LENGTH})",
    )
    parser.add_argument(
        "--verbose",
        action="store_true",
        help="Enable debug logs",
    )
    return parser.parse_args()


def main() -> int:
    """Run secret generation command."""
    args = parse_args()
    configure_logging(verbose=args.verbose)

    if args.length < MIN_SECRET_LENGTH:
        logger.error("length must be at least %d", MIN_SECRET_LENGTH)
        return 1

    secret_key = generate_jwt_secret(args.length)
    logger.info("Generated secret with %d characters", args.length)

    print("Generated JWT SECRET_KEY:")
    print(f"SECRET_KEY={secret_key}")
    return 0


if __name__ == "__main__":
    sys.exit(main())

# Contributing Guide

Thanks for contributing to Python Testbed.

## Development Setup

1. Clone the repository.
2. Create and activate a Python 3.11+ virtual environment.
3. Install package and development dependencies:

```bash
pip install -e .[dev]
```

## Project Conventions

1. Keep scripts focused and single-purpose.
2. Add docstrings to modules and public functions.
3. Prefer logging for diagnostics and print for user-facing CLI output.
4. Add or update tests for behavior changes.

## Run Checks Locally

Run linting:

```bash
ruff check .
```

Run tests:

```bash
pytest -q
```

Run CLI smoke tests only:

```bash
pytest -q tests/test_cli_smoke.py
```

## Pre-commit Hooks

Install hooks:

```bash
pre-commit install
```

Run hooks for all files:

```bash
pre-commit run --all-files
```

Hooks include secret leak scanning.

## Pull Request Checklist

1. Branch is up to date with main.
2. Lint checks pass.
3. Tests pass.
4. No secrets are committed.
5. README or docs are updated when behavior changes.

## Reporting Issues

When opening issues, include:

1. Exact command run.
2. Full error output.
3. Python version and OS.
4. Steps to reproduce.

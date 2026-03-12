# Python Testbed

Reusable Python command-line utilities for:

- AI provider interactions
- Document processing
- Security token generation
- Project structure creation and export

The repository is organized by use case so each script is easy to locate and run.

## Who This Is For

- Developers who need ready-to-use utility scripts
- Teams that want a lightweight script toolkit
- Anyone who wants examples of small, focused Python CLIs with logging and error handling

## Repository Structure

```text
src/
  ai/
    providers/
      anthropic_chat.py
      openrouter_chat.py
      google_ai_studio.py
  document_processing/
    conversion/
      markdown_to_docx.py
      extracted_text_to_json.py
    extraction/
      pdf_to_text.py
    storage/
      delete_s3_bucket_documents.py
  project_structure/
    create_structure_from_json.py
    export_project_structure.py
  security/
    tokens/
      generate_jwt_secret_key.py
```

## Requirements

- Python 3.11+
- Dependencies listed in pyproject.toml

## Installation

### Option 1: Using uv (recommended)

```bash
uv sync
```

### Option 2: Using pip

```bash
python -m venv .venv
. .venv/Scripts/activate
pip install -e .
```

Install development dependencies:

```bash
pip install -e .[dev]
```

## Environment Variables

Copy .env.example to .env and fill in values.

## Logging

All scripts support:

```bash
--verbose
```

Use it to enable debug logs during troubleshooting.

## Command Reference

You can run commands in two ways:

1. As a Python file path
2. As an installed console script (after pip install -e . or uv sync)

### AI Utilities

Anthropic chat:

```bash
python src/ai/providers/anthropic_chat.py
anthropic-chat
```

OpenRouter chat:

```bash
python src/ai/providers/openrouter_chat.py
openrouter-chat
```

Google model list (plain text):

```bash
python src/ai/providers/google_ai_studio.py
google-models
```

Google model list (JSON file output):

```bash
python src/ai/providers/google_ai_studio.py --json -o models.json
google-models --json -o models.json
```

### Document Processing

Markdown to DOCX:

```bash
python src/document_processing/conversion/markdown_to_docx.py input.md -o output.docx
markdown-to-docx input.md -o output.docx
```

PDF to text:

```bash
python src/document_processing/extraction/pdf_to_text.py input.pdf -o output.txt
pdf-to-text input.pdf -o output.txt
```

Text to JSON string:

```bash
python src/document_processing/conversion/extracted_text_to_json.py input.txt -o output.json
text-to-json-string input.txt -o output.json
```

Delete S3 objects from bucket:

```bash
python src/document_processing/storage/delete_s3_bucket_documents.py your-bucket
s3-delete-objects your-bucket
```

Delete S3 objects under prefix:

```bash
python src/document_processing/storage/delete_s3_bucket_documents.py your-bucket --prefix documents/
s3-delete-objects your-bucket --prefix documents/
```

Delete without confirmation prompt:

```bash
python src/document_processing/storage/delete_s3_bucket_documents.py your-bucket --yes
s3-delete-objects your-bucket --yes
```

### Security Utility

Generate JWT secret:

```bash
python src/security/tokens/generate_jwt_secret_key.py --length 80
generate-jwt-secret --length 80
```

### Project Structure Utilities

Create folder structure from JSON definition:

```bash
python src/project_structure/create_structure_from_json.py structure.json output_dir
create-structure-from-json structure.json output_dir
```

Export project structure to markdown:

```bash
python src/project_structure/export_project_structure.py . -o project_structure.md
export-project-structure . -o project_structure.md
```

Export project structure without .gitignore filtering:

```bash
python src/project_structure/export_project_structure.py . --no-gitignore
export-project-structure . --no-gitignore
```

Add custom ignore patterns:

```bash
python src/project_structure/export_project_structure.py . --ignore .venv/ --ignore *.log
export-project-structure . --ignore .venv/ --ignore *.log
```

## JSON Format for Structure Creation

The create structure utility expects exactly one top-level project key.

```json
{
  "my-project": {
    "src": {
      "main.py": "print('hello')",
      "utils": {
        "__init__.py": ""
      }
    },
    "README.md": "# My Project"
  }
}
```

Rules:
- Object value: directory
- String value: file with content
- Null value: empty directory

## Safety Notes

- The S3 deletion utility is destructive. Always test with --prefix first.
- Keep API keys in .env, never commit secrets.
- Run with --verbose when debugging production issues.

## Quality and Validation

Lint all code:

```bash
ruff check .
```

Run all tests:

```bash
pytest -q
```

Run CLI smoke tests only:

```bash
pytest -q tests/test_cli_smoke.py
```

## Pre-commit and Secret Leak Checks

Install git hooks:

```bash
pre-commit install
```

Run hooks manually on all files:

```bash
pre-commit run --all-files
```

The pre-commit configuration includes:

- File hygiene checks (YAML, TOML, JSON, whitespace)
- Private key and AWS credential checks
- detect-secrets scanning for potential secret leaks
- Gitleaks scanning for additional secret leak detection

## Continuous Integration

GitHub Actions workflow is available at:

- .github/workflows/ci.yml

On push and pull request, CI runs:

1. Ruff lint
2. CLI smoke tests
3. pre-commit hooks (including secret scanning)

## Contributing

See CONTRIBUTING.md for development setup, pull request checklist, and contribution process.

## License

This project is licensed under the MIT License. See LICENSE.

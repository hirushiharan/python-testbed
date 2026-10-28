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
  main.py
  auth/
    api/
    application/
    domain/
    infrastructure/
    integrations/
  ai/
    providers/
      anthropic_chat.py
      openrouter_chat.py
      google_ai_studio.py
  integrations/
    email/
      outlook_mailbox.py
    sharepoint/
  aws_inventory/
    cli.py
    collectors/
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

## Auth Module

The `src/auth` package mirrors the Microsoft Entra ID authentication flow used in the billing-ops backend.
It exposes login URL generation, authorization-code exchange, bearer-token validation, and a user lookup endpoint backed by MySQL.

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

### Email Connectors

Outlook mailbox data (Inbox and Sent Items):

```bash
python src/integrations/email/outlook_mailbox.py --json
outlook-mailbox --json
```

Outlook mailbox data (all folders):

```bash
python src/integrations/email/outlook_mailbox.py --all-folders --max-per-folder 50 --json
outlook-mailbox --all-folders --max-per-folder 50 --json
```

### SharePoint API

The FastAPI app in `src/main.py` exposes SharePoint document-library endpoints
under `/api/v1/sharepoint`.

Run the API:

```bash
uv run uvicorn src.main:app --reload
```

Available operations:

- `POST /api/v1/sharepoint/documents` to create a document folder
- `GET /api/v1/sharepoint/documents/{folder_id}/files` to list files in a folder
- `POST /api/v1/sharepoint/documents/{folder_id}/files` to upload a file to a folder

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

Clean and format garbage text:

```bash
python src/document_processing/conversion/garbage_text_cleaner.py --input raw.txt -o cleaned.txt
clean-garbage-text --input raw.txt -o cleaned.txt
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

### AWS Account Inventory (read-only)

Inventory every service in an AWS account across all enabled regions, grouped by service, with
status, last activity, dependencies and metadata. Output is JSON (full detail) and/or Excel
(Summary, Dependencies, Errors and one sheet per service).

Log in with the AWS CLI first (`aws login`, `aws sso login --profile <name>` or `aws configure`).
The account ID must match the credentials, or use `--role-name` to assume a role into it.

```bash
python src/aws_inventory/cli.py 123456789012
aws-inventory 123456789012 --profile prod --format xlsx
aws-inventory 123456789012 --role-name OrganizationAccountAccessRole
aws-inventory 123456789012 --regions us-east-1,eu-west-1 --services ec2,s3,lambda
aws-inventory 123456789012 --skip-cost
```

Notes:
- Strictly read-only: only List/Describe/Get calls, plus STS to identify/assume a role.
  `ReadOnlyAccess` + `SecurityAudit` is enough; Cost Explorer needs `ce:GetCostAndUsage`
  (about $0.01 per request, skip with `--skip-cost`).
- Deep collectors: ec2 (incl. VPC/NAT), s3, rds, lambda, iam, ecs, eks, dynamodb, elbv2,
  cloudfront, apigateway, sqs, sns. Other services are picked up as `unknown`-status stubs via
  the Resource Groups Tagging API and Resource Explorer (if an aggregator index exists), and
  Cost Explorer flags billed services with no collector (`coverage.billed_without_collector`).
- `last_activity` is only available where AWS exposes it (CloudWatch metrics over the last 30
  days, IAM last-used); `null` means none observed or no signal. `is_active` is state-based for
  resources with a lifecycle state and activity-based otherwise.
- Dependencies come from each resource's describe response, not a full cross-service graph.
- Every run writes a detailed DEBUG log next to the output (`aws-inventory-<account>-<time>.log`): per-API-call
  timings, START/DONE lines per service/region, a 30s heartbeat showing what each running task is doing, and an
  end-of-run report (slowest tasks, retries, throttling). Calls have 10s connect / 30s read timeouts; Ctrl+C
  stops promptly. Request parameters and credentials are never logged.
- Output files contain account details; they are written to `aws-inventory-output/` (git-ignored).

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
- The AWS inventory utility never modifies AWS resources.
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

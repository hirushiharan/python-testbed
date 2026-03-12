Python Testbed
===============

Small, focused scripts for talking to a few LLM providers from the terminal.
Each script is self-contained and reads its API key from environment variables
via a .env file (loaded by python-dotenv).

Contents
--------

- src/ai/providers/anthropic_chat.py: minimal Anthropic Messages API chat loop.
- src/ai/providers/openrouter_chat.py: minimal OpenRouter chat loop.
- src/ai/providers/google_ai_studio.py: list available Google AI Studio models.
- src/document_processing/conversion/markdown_to_docx.py: convert Markdown files to DOCX while preserving content and applying document formatting.
- src/document_processing/extraction/pdf_to_text.py: extract text from a PDF file and print or save as .txt.
- src/document_processing/conversion/extracted_text_to_json.py: convert extracted .txt content to JSON-valid text.
- src/document_processing/storage/delete_s3_bucket_documents.py: delete all objects in an S3 bucket (optionally scoped by prefix).
- src/security/tokens/generate_jwt_secret_key.py: generate a strong SECRET_KEY value for JWT authentication.

Requirements
------------

- Python 3.11+
- Dependencies:
	- python-dotenv
	- google-genai (only required for the Google AI Studio script)
	- pypandoc-binary (required for Markdown -> DOCX conversion)
	- pypdf (required for PDF -> text extraction)
	- boto3 (required for S3 bucket object deletion)

Setup
-----

1) Create and activate a virtual environment (recommended).
2) Install dependencies (pip example):

	pip install python-dotenv google-genai
	pip install pypandoc-binary

	Or use poetry/uv/pip with pyproject.toml as needed.

3) Create a .env file in the repo root, or set the variables in your shell.

Environment Variables
---------------------

- CLAUDE_API_KEY: API key for Anthropic (used by the script).
- ANTHROPIC_MODEL: optional (default: claude-3-5-sonnet-20240620).

- OPENROUTER_API_KEY: API key for OpenRouter.
- OPENROUTER_MODEL: optional (default: anthropic/claude-4.6-opus).

- GOOGLE_API_KEY: API key for Google AI Studio.

- AWS_ACCESS_KEY_ID: AWS access key for S3 operations.
- AWS_SECRET_ACCESS_KEY: AWS secret key for S3 operations.
- AWS_SESSION_TOKEN: optional temporary session token.
- AWS_REGION: region for S3 operations.

Example .env:

	CLAUDE_API_KEY=your_key_here
	OPENROUTER_API_KEY=your_key_here
	GOOGLE_API_KEY=your_key_here

Usage
-----

Anthropic chat:

	python src/ai/providers/anthropic_chat.py

OpenRouter chat:

	python src/ai/providers/openrouter_chat.py

Google AI Studio model list:

	python src/ai/providers/google_ai_studio.py

Markdown to DOCX:

	python src/document_processing/conversion/markdown_to_docx.py path/to/file.md -o path/to/file.docx

PDF to text:

	python src/document_processing/extraction/pdf_to_text.py path/to/file.pdf -o path/to/file.txt

Extracted text to JSON:

	python src/document_processing/conversion/extracted_text_to_json.py path/to/file.txt -o path/to/file.json

Generate JWT SECRET_KEY:

	python src/security/tokens/generate_jwt_secret_key.py --length 80

Delete all objects from an S3 bucket:

	python src/document_processing/storage/delete_s3_bucket_documents.py your-bucket-name

Example with environment variables:

	AWS_ACCESS_KEY_ID=your_access_key
	AWS_SECRET_ACCESS_KEY=your_secret_key
	AWS_REGION=ap-south-1
	python src/document_processing/storage/delete_s3_bucket_documents.py your-bucket-name

Delete objects under a specific prefix:

	python src/document_processing/storage/delete_s3_bucket_documents.py your-bucket-name --prefix documents/

Skip confirmation prompt:

	python src/document_processing/storage/delete_s3_bucket_documents.py your-bucket-name --yes

Notes
-----

- The Anthropic and OpenRouter scripts are synchronous and use urllib.
- The Google script prints model identifiers in a JSON-style fragment.
- These scripts are minimal and are meant as a starting point for experiments.

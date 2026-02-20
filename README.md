Python Testbed
===============

Small, focused scripts for talking to a few LLM providers from the terminal.
Each script is self-contained and reads its API key from environment variables
via a .env file (loaded by python-dotenv).

Contents
--------

- src/llm/anthropic/anthropic_chat.py: minimal Anthropic Messages API chat loop.
- src/llm/openrouter/openrouter_chat.py: minimal OpenRouter chat loop.
- src/llm/google/google_ai_studio.py: list available Google AI Studio models.
- src/docs/markdown_to_docx.py: convert Markdown files to DOCX while preserving content and applying document formatting.

Requirements
------------

- Python 3.11+
- Dependencies:
	- python-dotenv
	- google-genai (only required for the Google AI Studio script)
	- pypandoc-binary (required for Markdown -> DOCX conversion)

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

Example .env:

	CLAUDE_API_KEY=your_key_here
	OPENROUTER_API_KEY=your_key_here
	GOOGLE_API_KEY=your_key_here

Usage
-----

Anthropic chat:

	python src/llm/anthropic/anthropic_chat.py

OpenRouter chat:

	python src/llm/openrouter/openrouter_chat.py

Google AI Studio model list:

	python src/llm/google/google_ai_studio.py

Markdown to DOCX:

	python src/docs/markdown_to_docx.py path/to/file.md -o path/to/file.docx

Notes
-----

- The Anthropic and OpenRouter scripts are synchronous and use urllib.
- The Anthropic script prints an error message mentioning ANTHROPIC_API_KEY,
  but it currently reads CLAUDE_API_KEY from the environment.
- The Google script prints model identifiers in a JSON-style fragment.
- These scripts are minimal and are meant as a starting point for experiments.

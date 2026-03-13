"""CLI smoke tests for all script entry paths."""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
PYTHON = sys.executable

CLI_SCRIPT_PATHS = [
    "src/ai/providers/anthropic_chat.py",
    "src/ai/providers/openrouter_chat.py",
    "src/ai/providers/google_ai_studio.py",
    "src/integrations/email/outlook_mailbox.py",
    "src/document_processing/conversion/markdown_to_docx.py",
    "src/document_processing/conversion/extracted_text_to_json.py",
    "src/document_processing/extraction/pdf_to_text.py",
    "src/document_processing/storage/delete_s3_bucket_documents.py",
    "src/security/tokens/generate_jwt_secret_key.py",
    "src/project_structure/create_structure_from_json.py",
    "src/project_structure/export_project_structure.py",
]


@pytest.mark.parametrize("relative_path", CLI_SCRIPT_PATHS)
def test_cli_help_runs(relative_path: str) -> None:
    """Verify each CLI script can be invoked and returns help successfully."""
    script_path = REPO_ROOT / relative_path
    assert script_path.exists(), f"Missing script: {script_path}"

    result = subprocess.run(
        [PYTHON, str(script_path), "--help"],
        cwd=REPO_ROOT,
        text=True,
        capture_output=True,
    )

    assert result.returncode == 0, (
        f"--help failed for {relative_path}\n"
        f"stdout:\n{result.stdout}\n"
        f"stderr:\n{result.stderr}"
    )

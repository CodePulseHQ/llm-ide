"""Smoke tests for MCP endpoints."""

from refactor_mcp.server import (
    apply_text_edits,
    detect_file_language,
    get_supported_languages,
    organize_imports,
)
from tests.utils import unwrap


def test_mcp_smoke_endpoints(temp_dir):
    py_file = temp_dir / "sample.py"
    py_file.write_text("import os\n\n\ndef hello():\n    return 1\n", encoding="utf-8")

    languages = unwrap(get_supported_languages())
    assert "supported_languages" in languages

    detected = unwrap(detect_file_language(str(py_file)))
    assert detected["language"].lower() == "python"

    organize_result = unwrap(organize_imports(str(py_file)))
    assert "success" in organize_result.lower()

    edits = [
        {
            "start_line": 4,
            "start_column": 4,
            "end_line": 4,
            "end_column": 10,
            "new_text": "2",
        }
    ]
    edit_result = unwrap(apply_text_edits(str(py_file), edits, preview=True))
    assert edit_result["success"] is True

"""Tests for apply_text_edits tool."""

import hashlib
from refactor_mcp.server import apply_text_edits
from tests.utils import unwrap


def _hash_content(content: str) -> str:
    return hashlib.sha256(content.encode("utf-8")).hexdigest()


def test_apply_text_edits_preview_and_apply(temp_dir):
    file_path = temp_dir / "edit.txt"
    file_path.write_text("Hello World\nSecond line\n", encoding="utf-8")

    original_content = file_path.read_text(encoding="utf-8")
    original_hash = _hash_content(original_content)

    edits = [
        {
            "start_line": 1,
            "start_column": 6,
            "end_line": 1,
            "end_column": 11,
            "new_text": "Codex",
        }
    ]

    preview_result = unwrap(
        apply_text_edits(str(file_path), edits, expected_hash=original_hash, preview=True)
    )
    assert preview_result["success"] is True
    assert preview_result["preview"] is True

    apply_result = unwrap(
        apply_text_edits(str(file_path), edits, expected_hash=original_hash, preview=False)
    )
    assert apply_result["success"] is True
    assert apply_result["preview"] is False

    updated = file_path.read_text(encoding="utf-8")
    assert updated.startswith("Hello Codex")


def test_apply_text_edits_hash_mismatch(temp_dir):
    file_path = temp_dir / "edit.txt"
    file_path.write_text("Hello World\n", encoding="utf-8")

    edits = [
        {
            "start_line": 1,
            "start_column": 6,
            "end_line": 1,
            "end_column": 11,
            "new_text": "Codex",
        }
    ]

    result = unwrap(
        apply_text_edits(str(file_path), edits, expected_hash="bad", preview=True),
        allow_error=True,
    )
    assert result["success"] is False
    assert result["error"] == "File hash mismatch"

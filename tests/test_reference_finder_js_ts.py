"""Tests for JS/TS reference finding with Tree-sitter."""

import pytest

from refactor_mcp.workspace import ProjectIndex, ReferenceFinder


def _tree_sitter_available():
    try:
        import tree_sitter_javascript  # noqa: F401
        import tree_sitter_typescript  # noqa: F401

        return True
    except Exception:
        return False


@pytest.mark.skipif(not _tree_sitter_available(), reason="tree-sitter not available")
def test_find_references_javascript_tree_sitter(temp_dir):
    js_file = temp_dir / "example.js"
    js_file.write_text(
        """
import defaultExport, { helper as aliasHelper } from "./mod";

export { helper };

export default function helper() {
    return "ok";
}

const obj = { helper };
obj.helper();
helper();
""",
        encoding="utf-8",
    )

    index = ProjectIndex(temp_dir)
    index.index_project()

    finder = ReferenceFinder(index)
    result = finder.find_references("helper", file_path=str(js_file), scope="file")

    usage_types = {ref["usage_type"] for ref in result["references"]}
    assert "definition" in usage_types
    assert "export" in usage_types
    assert "call" in usage_types
    assert "method_call" in usage_types
    assert "shorthand_property" in usage_types


@pytest.mark.skipif(not _tree_sitter_available(), reason="tree-sitter not available")
def test_find_references_typescript_tree_sitter(temp_dir):
    ts_file = temp_dir / "example.ts"
    ts_file.write_text(
        """
type User = { name: string };

export default function helper(name: string): string {
    return name;
}

const obj = { helper };
obj.helper("ok");
helper("ok");
""",
        encoding="utf-8",
    )

    index = ProjectIndex(temp_dir)
    index.index_project()

    finder = ReferenceFinder(index)
    result = finder.find_references("helper", file_path=str(ts_file), scope="file")

    usage_types = {ref["usage_type"] for ref in result["references"]}
    assert "definition" in usage_types
    assert "export_default" in usage_types
    assert "call" in usage_types
    assert "method_call" in usage_types

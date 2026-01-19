"""Tests for the workspace module (IDE-like capabilities)."""

import json
import tempfile
from pathlib import Path

import pytest

from refactor_mcp.workspace import (
    CallGraphAnalyzer,
    DefinitionResolver,
    ProjectIndex,
    ReferenceFinder,
    WorkspaceManager,
    WorkspaceOperations,
)
from tests.utils import unwrap


@pytest.fixture
def temp_project():
    """Create a temporary project with multiple Python files."""
    with tempfile.TemporaryDirectory() as tmpdir:
        project_dir = Path(tmpdir)

        # Create main.py
        (project_dir / "main.py").write_text(
            '''"""Main module."""
from utils import helper_function
from models import User

def main():
    """Main entry point."""
    result = helper_function("test")
    user = User("test_user")
    return result

def unused_function():
    """This function is not used."""
    pass

if __name__ == "__main__":
    main()
'''
        )

        # Create utils.py
        (project_dir / "utils.py").write_text(
            '''"""Utility functions."""

def helper_function(value):
    """A helper function used by main."""
    return process_value(value)

def process_value(value):
    """Process a value."""
    return value.upper()

def another_helper():
    """Another helper not used in main."""
    return helper_function("internal")
'''
        )

        # Create models.py
        (project_dir / "models.py").write_text(
            '''"""Data models."""

class User:
    """User model class."""

    def __init__(self, name):
        self.name = name

    def get_name(self):
        """Get the user's name."""
        return self.name

    def greet(self):
        """Greet the user."""
        return f"Hello, {self.get_name()}!"

class AdminUser(User):
    """Admin user model."""

    def __init__(self, name, role="admin"):
        super().__init__(name)
        self.role = role

    def get_role(self):
        """Get the admin's role."""
        return self.role
'''
        )

        # Create a subdirectory with more files
        subdir = project_dir / "submodule"
        subdir.mkdir()

        (subdir / "__init__.py").write_text('"""Submodule package."""\n')

        (subdir / "extra.py").write_text(
            '''"""Extra utilities."""
from ..utils import helper_function

def extra_helper():
    """Extra helper function."""
    return helper_function("extra")
'''
        )

        yield project_dir


class TestProjectIndex:
    """Tests for ProjectIndex class."""

    def test_index_project_basic(self, temp_project):
        """Test basic project indexing."""
        index = ProjectIndex(temp_project)
        stats = index.index_project()

        assert stats["total_files"] >= 4
        assert stats["total_symbols"] > 0
        assert "Python" in stats["languages"]

    def test_find_symbol_by_name(self, temp_project):
        """Test finding symbols by name."""
        index = ProjectIndex(temp_project)
        index.index_project()

        # Find function
        symbols = index.find_symbol("helper_function")
        assert len(symbols) >= 1
        assert symbols[0].name == "helper_function"
        assert symbols[0].symbol_type == "function"

        # Find class
        symbols = index.find_symbol("User")
        assert len(symbols) >= 1
        assert symbols[0].symbol_type == "class"

    def test_search_symbols_fuzzy(self, temp_project):
        """Test fuzzy symbol search."""
        index = ProjectIndex(temp_project)
        index.index_project()

        # Fuzzy search
        results = index.search_symbols("help")
        assert len(results) >= 2  # helper_function, another_helper

        # Search with type filter
        results = index.search_symbols("User", symbol_type="class")
        assert len(results) >= 1
        assert all(r.symbol_type == "class" for r in results)

    def test_get_file_symbols(self, temp_project):
        """Test getting symbols from a specific file."""
        index = ProjectIndex(temp_project)
        index.index_project()

        utils_file = str(temp_project / "utils.py")
        symbols = index.get_file_symbols(utils_file)

        symbol_names = [s.name for s in symbols]
        assert "helper_function" in symbol_names
        assert "process_value" in symbol_names

    def test_invalidate_file(self, temp_project):
        """Test file invalidation."""
        index = ProjectIndex(temp_project)
        index.index_project()

        utils_file = str(temp_project / "utils.py")

        # Should have symbols
        assert len(index.get_file_symbols(utils_file)) > 0

        # Invalidate
        index.invalidate_file(utils_file)

        # File should be removed from index
        assert utils_file not in index.files

    def test_get_symbol_at_location(self, temp_project):
        """Test getting symbol at a specific location."""
        index = ProjectIndex(temp_project)
        index.index_project()

        utils_file = str(temp_project / "utils.py")

        # Line 4 should be inside helper_function
        symbol = index.get_symbol_at_location(utils_file, 4)
        assert symbol is not None
        assert symbol.name == "helper_function"


class TestReferenceFinder:
    """Tests for ReferenceFinder class."""

    def test_find_references_basic(self, temp_project):
        """Test basic reference finding."""
        index = ProjectIndex(temp_project)
        index.index_project()

        finder = ReferenceFinder(index)
        result = finder.find_references("helper_function")

        assert result["symbol"] == "helper_function"
        assert result["total"] >= 3  # Definition + calls in main.py, another_helper, extra.py

    def test_find_references_includes_definition(self, temp_project):
        """Test that definition is included in references."""
        index = ProjectIndex(temp_project)
        index.index_project()

        finder = ReferenceFinder(index)
        result = finder.find_references("User", include_definition=True)

        # Should have definition
        refs = result["references"]
        definitions = [r for r in refs if r["is_definition"]]
        assert len(definitions) >= 1

    def test_find_references_class(self, temp_project):
        """Test finding references to a class."""
        index = ProjectIndex(temp_project)
        index.index_project()

        finder = ReferenceFinder(index)
        result = finder.find_references("User")

        assert result["total"] >= 2  # Definition + usage in main.py + inheritance

    def test_find_references_file_scope(self, temp_project):
        """Test finding references in file scope only."""
        index = ProjectIndex(temp_project)
        index.index_project()

        finder = ReferenceFinder(index)
        utils_file = str(temp_project / "utils.py")

        result = finder.find_references("helper_function", file_path=utils_file, scope="file")

        # Should only find references in utils.py
        for ref in result["references"]:
            assert ref["file_path"] == utils_file


class TestDefinitionResolver:
    """Tests for DefinitionResolver class."""

    def test_go_to_definition_local(self, temp_project):
        """Test finding local definitions."""
        index = ProjectIndex(temp_project)
        index.index_project()

        resolver = DefinitionResolver(index)
        utils_file = str(temp_project / "utils.py")

        result = resolver.go_to_definition(utils_file, "helper_function")

        assert result["found"] is True
        assert result["symbol"] == "helper_function"
        assert "utils.py" in result["defined_in"]

    def test_go_to_definition_class(self, temp_project):
        """Test finding class definitions."""
        index = ProjectIndex(temp_project)
        index.index_project()

        resolver = DefinitionResolver(index)
        main_file = str(temp_project / "main.py")

        result = resolver.go_to_definition(main_file, "User")

        assert result["found"] is True
        assert result["type"] == "class"
        assert "models.py" in result["defined_in"]

    def test_go_to_definition_not_found(self, temp_project):
        """Test handling of undefined symbols."""
        index = ProjectIndex(temp_project)
        index.index_project()

        resolver = DefinitionResolver(index)
        main_file = str(temp_project / "main.py")

        result = resolver.go_to_definition(main_file, "nonexistent_symbol")

        assert result["found"] is False


class TestCallGraphAnalyzer:
    """Tests for CallGraphAnalyzer class."""

    def test_get_call_hierarchy_callers(self, temp_project):
        """Test finding callers of a function."""
        index = ProjectIndex(temp_project)
        index.index_project()

        analyzer = CallGraphAnalyzer(index)
        utils_file = str(temp_project / "utils.py")

        result = analyzer.get_call_hierarchy(utils_file, "helper_function", direction="callers")

        assert "callers" in result
        # helper_function is called by main() and another_helper()
        assert len(result["callers"]) >= 2

    def test_get_call_hierarchy_callees(self, temp_project):
        """Test finding callees of a function."""
        index = ProjectIndex(temp_project)
        index.index_project()

        analyzer = CallGraphAnalyzer(index)
        utils_file = str(temp_project / "utils.py")

        result = analyzer.get_call_hierarchy(utils_file, "helper_function", direction="callees")

        assert "callees" in result
        # helper_function calls process_value
        callee_names = [c["name"] for c in result["callees"]]
        assert "process_value" in callee_names

    def test_get_call_hierarchy_both(self, temp_project):
        """Test getting both callers and callees."""
        index = ProjectIndex(temp_project)
        index.index_project()

        analyzer = CallGraphAnalyzer(index)
        utils_file = str(temp_project / "utils.py")

        result = analyzer.get_call_hierarchy(utils_file, "helper_function", direction="both")

        assert "callers" in result
        assert "callees" in result


class TestWorkspaceOperations:
    """Tests for WorkspaceOperations class."""

    def test_workspace_rename_preview(self, temp_project):
        """Test workspace rename with preview."""
        index = ProjectIndex(temp_project)
        index.index_project()

        ops = WorkspaceOperations(index)
        result = ops.workspace_rename("helper_function", "utility_function", preview=True)

        assert result.old_name == "helper_function"
        assert result.new_name == "utility_function"
        assert result.total_changes > 0
        assert result.applied is False  # Preview mode

    def test_workspace_rename_apply(self, temp_project):
        """Test workspace rename with actual application."""
        index = ProjectIndex(temp_project)
        index.index_project()

        ops = WorkspaceOperations(index)

        # Apply rename
        result = ops.workspace_rename("unused_function", "deprecated_function", preview=False)

        assert result.applied is True
        assert result.total_changes >= 1

        # Verify the file was changed
        main_content = (temp_project / "main.py").read_text()
        assert "deprecated_function" in main_content
        assert "unused_function" not in main_content

    def test_workspace_rename_invalid_identifier(self, temp_project):
        """Test rename with invalid identifier."""
        index = ProjectIndex(temp_project)
        index.index_project()

        ops = WorkspaceOperations(index)
        result = ops.workspace_rename("helper_function", "123invalid", preview=True)

        assert len(result.errors) > 0
        assert "not a valid identifier" in result.errors[0]


class TestWorkspaceManager:
    """Tests for WorkspaceManager class."""

    def test_get_or_create_workspace(self, temp_project):
        """Test workspace creation and retrieval."""
        workspace_id, index = WorkspaceManager.get_or_create_workspace(str(temp_project))

        assert workspace_id is not None
        assert index is not None
        assert index.root_path == temp_project.resolve()

    def test_get_workspace(self, temp_project):
        """Test getting existing workspace."""
        workspace_id, _ = WorkspaceManager.get_or_create_workspace(str(temp_project))

        # Get the same workspace
        index = WorkspaceManager.get_workspace(workspace_id)
        assert index is not None

        # Try non-existent workspace
        index = WorkspaceManager.get_workspace("nonexistent")
        assert index is None

    def test_list_workspaces(self, temp_project):
        """Test listing workspaces."""
        workspace_id, _ = WorkspaceManager.get_or_create_workspace(str(temp_project))

        workspaces = WorkspaceManager.list_workspaces()
        workspace_ids = [w["workspace_id"] for w in workspaces]

        assert workspace_id in workspace_ids

    def test_refresh_workspace(self, temp_project):
        """Test workspace refresh."""
        workspace_id, index = WorkspaceManager.get_or_create_workspace(str(temp_project))

        # Add a new file
        (temp_project / "new_file.py").write_text("def new_function(): pass\n")

        # Refresh
        stats = WorkspaceManager.refresh_workspace(workspace_id)

        assert stats is not None
        assert stats["total_files"] >= 5  # Original 4 + new file


class TestServerIntegration:
    """Integration tests for the MCP server endpoints."""

    def test_initialize_workspace_endpoint(self, temp_project):
        """Test the initialize_workspace MCP endpoint."""
        from refactor_mcp.server import initialize_workspace

        result = unwrap(initialize_workspace(str(temp_project)))

        assert "workspace_id" in result
        assert "files_indexed" in result
        assert result["files_indexed"] >= 4

    def test_find_references_endpoint(self, temp_project):
        """Test the find_references MCP endpoint."""
        from refactor_mcp.server import find_references, initialize_workspace

        # Initialize first
        init_result = unwrap(initialize_workspace(str(temp_project)))
        workspace_id = init_result["workspace_id"]

        # Find references
        main_file = str(temp_project / "main.py")
        result = unwrap(find_references(main_file, "helper_function", workspace_id=workspace_id))

        assert result["symbol"] == "helper_function"
        assert result["total"] >= 1

    def test_go_to_definition_endpoint(self, temp_project):
        """Test the go_to_definition MCP endpoint."""
        from refactor_mcp.server import go_to_definition, initialize_workspace

        # Initialize first
        init_result = unwrap(initialize_workspace(str(temp_project)))
        workspace_id = init_result["workspace_id"]

        # Go to definition
        main_file = str(temp_project / "main.py")
        result = unwrap(go_to_definition(main_file, "User", workspace_id=workspace_id))

        assert result["found"] is True
        assert "models.py" in result["defined_in"]

    def test_search_symbols_endpoint(self, temp_project):
        """Test the search_symbols MCP endpoint."""
        from refactor_mcp.server import search_symbols

        result = unwrap(search_symbols("help", root_path=str(temp_project)))

        assert result["total"] >= 2
        assert "matches" in result

    def test_get_call_hierarchy_endpoint(self, temp_project):
        """Test the get_call_hierarchy MCP endpoint."""
        from refactor_mcp.server import get_call_hierarchy, initialize_workspace

        # Initialize first
        init_result = unwrap(initialize_workspace(str(temp_project)))
        workspace_id = init_result["workspace_id"]

        # Get call hierarchy
        utils_file = str(temp_project / "utils.py")
        result = unwrap(get_call_hierarchy(utils_file, "helper_function", workspace_id=workspace_id))

        assert "callers" in result
        assert "callees" in result

    def test_workspace_rename_endpoint(self, temp_project):
        """Test the workspace_rename MCP endpoint."""
        from refactor_mcp.server import workspace_rename

        result = unwrap(
            workspace_rename("unused_function", "old_unused_function", root_path=str(temp_project))
        )

        assert result["old_name"] == "unused_function"
        assert result["new_name"] == "old_unused_function"
        assert result["total_changes"] >= 1
        assert result["applied"] is False  # Default is preview


class TestEdgeCases:
    """Tests for edge cases and error handling."""

    def test_empty_project(self):
        """Test handling of empty project directory."""
        with tempfile.TemporaryDirectory() as tmpdir:
            index = ProjectIndex(Path(tmpdir))
            stats = index.index_project()

            assert stats["total_files"] == 0
            assert stats["total_symbols"] == 0

    def test_syntax_error_in_file(self, temp_project):
        """Test handling of files with syntax errors."""
        # Create a file with syntax error
        (temp_project / "broken.py").write_text("def broken( # syntax error\n")

        index = ProjectIndex(temp_project)
        stats = index.index_project()

        # Should still index other valid files
        assert stats["total_files"] >= 4

    def test_binary_files_ignored(self, temp_project):
        """Test that binary files are ignored."""
        # Create a binary-like file
        (temp_project / "data.pyc").write_bytes(b"\x00\x01\x02\x03")

        index = ProjectIndex(temp_project)
        stats = index.index_project()

        # .pyc files should not be indexed
        assert all("pyc" not in f for f in index.files.keys())

    def test_symbol_not_found(self, temp_project):
        """Test handling of non-existent symbols."""
        index = ProjectIndex(temp_project)
        index.index_project()

        finder = ReferenceFinder(index)
        result = finder.find_references("nonexistent_symbol")

        assert result["total"] == 0

    def test_deeply_nested_calls(self, temp_project):
        """Test handling of deeply nested call hierarchies."""
        # Create file with nested calls
        (temp_project / "nested.py").write_text(
            """
def level1():
    return level2()

def level2():
    return level3()

def level3():
    return level4()

def level4():
    return "done"
"""
        )

        index = ProjectIndex(temp_project)
        index.index_project()

        analyzer = CallGraphAnalyzer(index)
        nested_file = str(temp_project / "nested.py")

        result = analyzer.get_call_hierarchy(nested_file, "level1", max_depth=5)

        # Should find nested callees
        assert "callees" in result

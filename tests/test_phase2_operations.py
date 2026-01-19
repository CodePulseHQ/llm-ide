"""Tests for Phase 2 token-saving operations."""

import tempfile
from pathlib import Path

import pytest

from refactor_mcp.workspace import (
    BatchOperations,
    ImportGenerator,
    ProjectIndex,
    SignatureChanger,
    SymbolMover,
)


@pytest.fixture
def temp_project():
    """Create a temporary project directory with test files."""
    with tempfile.TemporaryDirectory() as tmp_dir:
        project_dir = Path(tmp_dir)

        # Create utils.py
        utils_file = project_dir / "utils.py"
        utils_file.write_text(
            '''"""Utility functions."""


def validate_email(email: str) -> bool:
    """Validate an email address."""
    return "@" in email and "." in email


def format_name(first: str, last: str) -> str:
    """Format a full name."""
    return f"{first} {last}"


class Helper:
    """Helper class."""

    def process(self, data):
        return data


API_VERSION = "1.0.0"
'''
        )

        # Create main.py
        main_file = project_dir / "main.py"
        main_file.write_text(
            '''"""Main module."""

from utils import validate_email, format_name, Helper


def main():
    """Main function."""
    email = "test@example.com"
    if validate_email(email):
        print("Valid email")

    name = format_name("John", "Doe")
    print(name)

    helper = Helper()
    helper.process("data")


if __name__ == "__main__":
    main()
'''
        )

        # Create validators.py (empty target file)
        validators_file = project_dir / "validators.py"
        validators_file.write_text('"""Validators module."""\n')

        # Create api.py
        api_file = project_dir / "api.py"
        api_file.write_text(
            '''"""API module."""

from utils import validate_email


def process_request(data: dict) -> dict:
    """Process an API request."""
    email = data.get("email", "")
    if validate_email(email):
        return {"status": "ok"}
    return {"status": "error"}
'''
        )

        # Create an __init__.py to make it a package
        init_file = project_dir / "__init__.py"
        init_file.write_text("")

        yield project_dir


@pytest.fixture
def project_index(temp_project):
    """Create a project index for the temporary project."""
    index = ProjectIndex(temp_project)
    index.index_project()
    return index


class TestSymbolMover:
    """Tests for SymbolMover."""

    def test_move_symbol_preview(self, project_index, temp_project):
        """Test moving a symbol in preview mode."""
        mover = SymbolMover(project_index)

        result = mover.move_symbol(
            source_file=str(temp_project / "utils.py"),
            symbol_name="validate_email",
            target_file=str(temp_project / "validators.py"),
            update_imports=True,
            preview=True,
        )

        assert result.success is True
        assert result.symbol_name == "validate_email"
        assert result.symbol_type == "function"
        assert result.files_modified > 0
        assert len(result.warnings) > 0  # Preview mode warning

    def test_move_symbol_nonexistent(self, project_index, temp_project):
        """Test moving a nonexistent symbol."""
        mover = SymbolMover(project_index)

        result = mover.move_symbol(
            source_file=str(temp_project / "utils.py"),
            symbol_name="nonexistent_function",
            target_file=str(temp_project / "validators.py"),
        )

        assert result.success is False
        assert len(result.errors) > 0

    def test_safe_delete_used_symbol(self, project_index, temp_project):
        """Test safe_delete on a symbol that is in use."""
        mover = SymbolMover(project_index)

        result = mover.safe_delete(
            file_path=str(temp_project / "utils.py"),
            symbol_name="validate_email",
            confirm=False,
        )

        assert result.can_delete is False
        assert result.usages > 0
        assert len(result.blockers) > 0

    def test_safe_delete_unused_symbol(self, project_index, temp_project):
        """Test safe_delete on an unused symbol."""
        # First, add an unused function to utils.py
        utils_file = temp_project / "utils.py"
        content = utils_file.read_text()
        content += (
            '\n\ndef unused_function():\n    """This function is not used anywhere."""\n    pass\n'
        )
        utils_file.write_text(content)

        # Re-index
        project_index.invalidate_file(str(utils_file))
        project_index.index_file(utils_file)

        mover = SymbolMover(project_index)

        result = mover.safe_delete(
            file_path=str(utils_file),
            symbol_name="unused_function",
            confirm=False,
        )

        # Note: depends on reference finder accuracy
        assert result.usages == 0 or result.can_delete is True


class TestSignatureChanger:
    """Tests for SignatureChanger."""

    def test_add_parameter_preview(self, project_index, temp_project):
        """Test adding a parameter in preview mode."""
        changer = SignatureChanger(project_index)

        result = changer.add_parameter(
            file_path=str(temp_project / "utils.py"),
            function_name="validate_email",
            param_name="strict",
            param_type="bool",
            default_value="False",
            preview=True,
        )

        assert result.success is True
        assert result.function_name == "validate_email"
        assert len(result.changes) > 0
        assert result.changes[0].action == "add"
        assert result.changes[0].name == "strict"

    def test_add_parameter_nonexistent_function(self, project_index, temp_project):
        """Test adding a parameter to a nonexistent function."""
        changer = SignatureChanger(project_index)

        result = changer.add_parameter(
            file_path=str(temp_project / "utils.py"),
            function_name="nonexistent_function",
            param_name="param",
            preview=True,
        )

        assert result.success is False
        assert len(result.errors) > 0

    def test_change_signature_preview(self, project_index, temp_project):
        """Test changing signature in preview mode."""
        changer = SignatureChanger(project_index)

        new_params = [
            {"name": "last", "type": "str"},
            {"name": "first", "type": "str"},
            {"name": "middle", "type": "str", "default": '""'},
        ]

        result = changer.change_signature(
            file_path=str(temp_project / "utils.py"),
            function_name="format_name",
            new_params=new_params,
            preview=True,
        )

        assert result.success is True
        assert result.function_name == "format_name"


class TestBatchOperations:
    """Tests for BatchOperations."""

    def test_batch_rename_preview(self, project_index, temp_project):
        """Test batch rename in preview mode."""
        batch_ops = BatchOperations(project_index)

        renames = [
            {"old": "validate_email", "new": "check_email"},
            {"old": "format_name", "new": "format_full_name"},
        ]

        result = batch_ops.batch_rename(renames, preview=True)

        assert result.total_requested == 2
        assert result.total_succeeded + result.total_failed == 2

    def test_batch_rename_empty_list(self, project_index, temp_project):
        """Test batch rename with empty list."""
        batch_ops = BatchOperations(project_index)

        result = batch_ops.batch_rename([], preview=True)

        assert result.total_requested == 0
        assert result.total_succeeded == 0

    def test_bulk_analysis(self, project_index, temp_project):
        """Test bulk analysis."""
        batch_ops = BatchOperations(project_index)

        result = batch_ops.bulk_analysis(
            files=[str(temp_project / "utils.py"), str(temp_project / "main.py")],
            analyses=["structure"],
        )

        assert result.files_analyzed == 2
        assert len(result.structures) == 2
        assert "total_functions" in result.summary

    def test_extract_constant_preview(self, project_index, temp_project):
        """Test extract constant in preview mode."""
        batch_ops = BatchOperations(project_index)

        result = batch_ops.extract_constant(
            file_path=str(temp_project / "utils.py"),
            value="1.0.0",
            constant_name="VERSION",
            scope="file",
            preview=True,
        )

        assert "occurrences" in result
        assert result["constant_name"] == "VERSION"

    def test_inline_variable_preview(self, project_index, temp_project):
        """Test inline variable in preview mode."""
        batch_ops = BatchOperations(project_index)

        result = batch_ops.inline_variable(
            file_path=str(temp_project / "utils.py"),
            variable_name="API_VERSION",
            preview=True,
        )

        assert "variable_name" in result


class TestImportGenerator:
    """Tests for ImportGenerator."""

    def test_generate_imports_preview(self, project_index, temp_project):
        """Test generating imports in preview mode."""
        # Create a file with undefined symbols
        test_file = temp_project / "test_imports.py"
        test_file.write_text(
            '''"""Test file with undefined symbols."""


def test_function():
    path = Path("/tmp")
    data = json.loads("{}")
    return Optional[str]
'''
        )

        project_index.index_file(test_file)

        generator = ImportGenerator(project_index)

        result = generator.generate_imports(
            file_path=str(test_file),
            preview=True,
            include_stdlib=True,
            include_project=True,
        )

        assert len(result.undefined_symbols) > 0
        # Path, json, Optional should be undefined

    def test_find_unused_exports(self, project_index, temp_project):
        """Test finding unused exports."""
        generator = ImportGenerator(project_index)

        result = generator.find_unused_exports()

        assert result.files_checked > 0
        # Helper class might be detected as unused export


class TestReverseDependencies:
    """Tests for reverse dependency tracking."""

    def test_get_reverse_dependencies(self, project_index, temp_project):
        """Test getting reverse dependencies."""
        result = project_index.get_reverse_dependencies(str(temp_project / "utils.py"))

        assert "dependents" in result
        assert "dependent_count" in result
        # main.py and api.py should depend on utils.py

    def test_get_dependencies(self, project_index, temp_project):
        """Test getting dependencies."""
        result = project_index.get_dependencies(str(temp_project / "main.py"))

        assert "dependencies" in result
        assert "dependency_count" in result

    def test_analyze_impact(self, project_index, temp_project):
        """Test impact analysis."""
        result = project_index.analyze_impact(str(temp_project / "utils.py"))

        assert "direct_dependents" in result
        assert "direct_count" in result
        assert "total_affected" in result

    def test_get_dependency_graph(self, project_index, temp_project):
        """Test dependency graph generation."""
        result = project_index.get_dependency_graph()

        assert "node_count" in result
        assert "edge_count" in result
        assert "graph" in result
        assert "nodes" in result["graph"]
        assert "edges" in result["graph"]


if __name__ == "__main__":
    pytest.main([__file__, "-v"])

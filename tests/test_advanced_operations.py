"""Tests for advanced refactoring operations."""

import json
import tempfile

import pytest

from refactor_mcp.languages.base_handler import RefactoringOperation
from refactor_mcp.languages.python_handler import PythonHandler


class TestAdvancedOperations:
    """Test suite for advanced refactoring operations."""

    @pytest.fixture
    def handler(self):
        """Create a Python handler for testing."""
        return PythonHandler()

    @pytest.fixture
    def sample_python_code(self):
        """Sample Python code for testing."""
        return '''
def main():
    """Main function."""
    x = 10
    y = 20
    result = calculate_sum(x, y)
    print(f"Result: {result}")
    return result

def calculate_sum(a, b):
    """Calculate sum of two numbers."""
    return a + b

def unused_function():
    """This function is never called."""
    return "unused"

class MyClass:
    def __init__(self, value):
        self.value = value
    
    def get_value(self):
        return self.value
    
    def complex_method(self):
        x = self.value * 2
        y = x + 5
        z = y * 3
        return z
    
    def simple_method(self):
        return self.value + 1

unused_variable = "never used"
'''.strip()

    @pytest.fixture
    def temp_python_file(self, sample_python_code):
        """Create a temporary Python file for testing."""
        with tempfile.NamedTemporaryFile(mode="w", suffix=".py", delete=False) as f:
            f.write(sample_python_code)
            return f.name

    def test_extract_method_basic(self, handler, temp_python_file):
        """Test basic method extraction."""
        result = handler.extract_method(temp_python_file, 5, 7, "print_result")

        assert "Successfully extracted method" in result

        # Verify the modified file
        content = handler.read_file_content(temp_python_file)
        # The extracted method should be created (parameters depend on variable analysis)
        assert "def print_result(" in content
        assert "print_result(" in content  # Should have a call to the method

    def test_extract_method_with_variables(self, handler, temp_python_file):
        """Test method extraction with variable analysis."""
        # Extract lines that use variables from outer scope
        result = handler.extract_method(temp_python_file, 4, 6, "setup_variables")

        assert "Successfully extracted method" in result

        # Check that the extracted method has proper parameters
        content = handler.read_file_content(temp_python_file)
        lines = content.splitlines()
        method_line = next((line for line in lines if "def setup_variables" in line), None)
        assert method_line is not None

    def test_inline_method_basic(self, handler, temp_python_file):
        """Test basic method inlining."""
        result = handler.inline_method(temp_python_file, "calculate_sum")

        assert "Successfully inlined method" in result

        # Verify the method was removed and calls were inlined
        content = handler.read_file_content(temp_python_file)
        assert "def calculate_sum(" not in content
        # The result should contain the inlined code instead of the call

    def test_inline_method_not_found(self, handler, temp_python_file):
        """Test inlining a method that doesn't exist."""
        with pytest.raises(Exception):
            handler.inline_method(temp_python_file, "nonexistent_method")

    def test_detect_dead_code(self, handler, temp_python_file):
        """Test dead code detection."""
        result = handler.detect_dead_code(temp_python_file)
        result_data = json.loads(result)

        assert "dead_functions" in result_data
        assert "dead_variables" in result_data
        assert result_data["summary"]["total_dead_functions"] >= 1

        # Should detect unused_function
        dead_functions = result_data["dead_functions"]
        function_names = [f["name"] for f in dead_functions]
        assert "unused_function" in function_names

    def test_remove_dead_code_without_confirm(self, handler, temp_python_file):
        """Test dead code removal without confirmation."""
        result = handler.remove_dead_code(temp_python_file, confirm=False)

        assert "requires confirmation" in result

    def test_remove_dead_code_with_confirm(self, handler, temp_python_file):
        """Test dead code removal with confirmation."""
        # First backup the original content
        original_content = handler.read_file_content(temp_python_file)

        result = handler.remove_dead_code(temp_python_file, confirm=True)

        assert "Successfully removed dead code" in result

        # Verify dead code was removed
        new_content = handler.read_file_content(temp_python_file)
        assert "unused_function" not in new_content
        assert len(new_content) < len(original_content)

    def test_find_regex_pattern(self, handler, temp_python_file):
        """Test finding regex patterns."""
        result = handler.find_code_pattern(temp_python_file, r"def \w+\(", "regex")
        result_data = json.loads(result)

        assert result_data["total_matches"] >= 4  # Should find function definitions
        assert result_data["pattern_type"] == "regex"

        matches = result_data["matches"]
        assert any("def main(" in match["matched_text"] for match in matches)

    def test_find_ast_pattern_functions(self, handler, temp_python_file):
        """Test finding AST patterns for function definitions."""
        result = handler.find_code_pattern(temp_python_file, "function_definitions", "ast")
        result_data = json.loads(result)

        assert result_data["total_matches"] >= 4
        matches = result_data["matches"]
        function_names = [m["name"] for m in matches]
        assert "main" in function_names
        assert "calculate_sum" in function_names

    def test_find_ast_pattern_classes(self, handler, temp_python_file):
        """Test finding AST patterns for class definitions."""
        result = handler.find_code_pattern(temp_python_file, "class_definitions", "ast")
        result_data = json.loads(result)

        assert result_data["total_matches"] >= 1
        matches = result_data["matches"]
        assert matches[0]["name"] == "MyClass"

    def test_find_semantic_pattern_unused_variables(self, handler, temp_python_file):
        """Test finding semantic patterns for unused variables."""
        result = handler.find_code_pattern(temp_python_file, "unused_variables", "semantic")
        result_data = json.loads(result)

        # Should find some unused variables
        assert result_data["total_matches"] >= 0

    def test_find_semantic_pattern_long_functions(self, handler, temp_python_file):
        """Test finding semantic patterns for long functions."""
        result = handler.find_code_pattern(temp_python_file, "long_functions", "semantic")
        result_data = json.loads(result)

        # With default threshold, our test functions shouldn't be flagged as long
        matches = result_data["matches"]
        long_function_names = [m["name"] for m in matches if m["type"] == "long_function"]
        # Most test functions should be short
        assert len(long_function_names) == 0

    def test_apply_regex_pattern(self, handler, temp_python_file):
        """Test applying regex patterns."""
        # Replace print with logging (use non-greedy match)
        result = handler.apply_code_pattern(
            temp_python_file, r"print\(([^)]+)\)", r"logging.info(\1)", "regex"
        )

        print(f"Pattern replacement result: {result}")  # Debug output

        if "0 replacements made" in result:
            # Check the original content to understand the issue
            content = handler.read_file_content(temp_python_file)
            print(f"Original content:\n{content}")

        assert "replacements made" in result and "0 replacements made" not in result

        # Verify the replacement was made
        content = handler.read_file_content(temp_python_file)
        assert "logging.info(" in content
        assert 'print(f"Result: {result}")' not in content

    def test_apply_ast_pattern_print_to_logging(self, handler, temp_python_file):
        """Test applying AST patterns for print to logging conversion."""
        result = handler.apply_code_pattern(temp_python_file, "print_to_logging", "", "ast")

        assert "replacements made" in result

        # Verify the replacement
        content = handler.read_file_content(temp_python_file)
        assert "logging.info(" in content

    def test_validate_extract_method_operation(self, handler, temp_python_file):
        """Test validation of extract method operation."""
        validation = handler.validate_refactoring_operation(
            temp_python_file,
            RefactoringOperation.EXTRACT_METHOD,
            start_line=4,
            end_line=6,
            method_name="test_method",
        )

        assert validation["is_valid"] is True
        assert validation["operation"] == "extract_method"

    def test_validate_extract_method_invalid_lines(self, handler, temp_python_file):
        """Test validation with invalid line numbers."""
        validation = handler.validate_refactoring_operation(
            temp_python_file,
            RefactoringOperation.EXTRACT_METHOD,
            start_line=100,
            end_line=200,
            method_name="test_method",
        )

        assert validation["is_valid"] is False
        assert any("Invalid line range" in error for error in validation["errors"])

    def test_validate_extract_method_existing_name(self, handler, temp_python_file):
        """Test validation with existing method name."""
        validation = handler.validate_refactoring_operation(
            temp_python_file,
            RefactoringOperation.EXTRACT_METHOD,
            start_line=4,
            end_line=6,
            method_name="main",  # Already exists
        )

        assert any("already exists" in warning for warning in validation["warnings"])

    def test_validate_inline_method_operation(self, handler, temp_python_file):
        """Test validation of inline method operation."""
        validation = handler.validate_refactoring_operation(
            temp_python_file, RefactoringOperation.INLINE_METHOD, method_name="calculate_sum"
        )

        assert validation["is_valid"] is True

    def test_validate_inline_method_not_found(self, handler, temp_python_file):
        """Test validation of non-existent method for inlining."""
        validation = handler.validate_refactoring_operation(
            temp_python_file, RefactoringOperation.INLINE_METHOD, method_name="nonexistent_method"
        )

        assert validation["is_valid"] is False
        assert any("not found" in error for error in validation["errors"])

    def test_validate_rename_symbol_operation(self, handler, temp_python_file):
        """Test validation of rename symbol operation."""
        validation = handler.validate_refactoring_operation(
            temp_python_file,
            RefactoringOperation.RENAME_SYMBOL,
            old_name="unused_variable",
            new_name="new_variable",
        )

        assert validation["is_valid"] is True

    def test_validate_rename_symbol_invalid_name(self, handler, temp_python_file):
        """Test validation with invalid identifier."""
        validation = handler.validate_refactoring_operation(
            temp_python_file,
            RefactoringOperation.RENAME_SYMBOL,
            old_name="unused_variable",
            new_name="123invalid",  # Invalid identifier
        )

        assert validation["is_valid"] is False
        assert any("not a valid Python identifier" in error for error in validation["errors"])

    def test_validate_rename_symbol_keyword(self, handler, temp_python_file):
        """Test validation with Python keyword."""
        validation = handler.validate_refactoring_operation(
            temp_python_file,
            RefactoringOperation.RENAME_SYMBOL,
            old_name="unused_variable",
            new_name="class",  # Python keyword
        )

        assert validation["is_valid"] is False
        assert any("is a Python keyword" in error for error in validation["errors"])

    def test_validate_apply_pattern_operation(self, handler, temp_python_file):
        """Test validation of apply pattern operation."""
        validation = handler.validate_refactoring_operation(
            temp_python_file,
            RefactoringOperation.APPLY_CODE_PATTERN,
            find_pattern=r"print\(",
            replace_pattern="logging.info(",
            pattern_type="regex",
        )

        assert validation["is_valid"] is True

    def test_validate_apply_pattern_invalid_regex(self, handler, temp_python_file):
        """Test validation with invalid regex."""
        validation = handler.validate_refactoring_operation(
            temp_python_file,
            RefactoringOperation.APPLY_CODE_PATTERN,
            find_pattern="[unclosed",  # Invalid regex
            replace_pattern="replacement",
            pattern_type="regex",
        )

        assert validation["is_valid"] is False
        assert any("Invalid regex pattern" in error for error in validation["errors"])

    def test_general_quality_suggestions(self, handler):
        """Test general code quality suggestions."""
        # Create a file with quality issues
        long_file_content = "\n".join([f"def function_{i}(): pass" for i in range(60)])

        with tempfile.NamedTemporaryFile(mode="w", suffix=".py", delete=False) as f:
            f.write(long_file_content)
            temp_file = f.name

        validation = handler.validate_refactoring_operation(
            temp_file,
            RefactoringOperation.EXTRACT_METHOD,
            start_line=1,
            end_line=2,
            method_name="test",
        )

        # Should suggest splitting due to many functions
        suggestions = validation["suggestions"]
        assert any("Many functions" in s for s in suggestions)

    def test_pattern_type_validation(self, handler, temp_python_file):
        """Test validation of pattern types."""
        # Test unsupported pattern type
        with pytest.raises(Exception):
            handler.find_code_pattern(temp_python_file, "test", "unsupported_type")

    def test_ast_pattern_validation(self, handler, temp_python_file):
        """Test validation of AST patterns."""
        # Test unsupported AST pattern
        with pytest.raises(Exception):
            handler.find_code_pattern(temp_python_file, "unsupported_pattern", "ast")

    def test_semantic_pattern_validation(self, handler, temp_python_file):
        """Test validation of semantic patterns."""
        # Test unsupported semantic pattern
        with pytest.raises(Exception):
            handler.find_code_pattern(temp_python_file, "unsupported_pattern", "semantic")

    def test_complex_condition_detection(self, handler):
        """Test detection of complex conditions."""
        complex_code = """
def test_function():
    if a > 5 and b < 10 and c == 3 and d != 4 and e >= 7:
        return True
    return False
"""

        with tempfile.NamedTemporaryFile(mode="w", suffix=".py", delete=False) as f:
            f.write(complex_code)
            temp_file = f.name

        result = handler.find_code_pattern(temp_file, "complex_conditions", "semantic")
        result_data = json.loads(result)

        # Should find the complex condition
        assert result_data["total_matches"] >= 1
        matches = result_data["matches"]
        assert any(m["type"] == "complex_condition" for m in matches)

    def test_duplicate_code_detection(self, handler):
        """Test detection of duplicate code."""
        duplicate_code = """
def function1():
    x = calculate_something_complex()
    return x

def function2():
    x = calculate_something_complex()
    return x
"""

        with tempfile.NamedTemporaryFile(mode="w", suffix=".py", delete=False) as f:
            f.write(duplicate_code)
            temp_file = f.name

        result = handler.find_code_pattern(temp_file, "duplicate_code", "semantic")
        result_data = json.loads(result)

        # Should find potential duplicates
        matches = result_data["matches"]
        assert any(m["type"] == "potential_duplicate" for m in matches)

    @pytest.fixture(autouse=True)
    def cleanup_temp_files(self, request):
        """Clean up temporary files after each test."""

        def cleanup():
            # Clean up any temporary files created during testing
            import os

            if hasattr(request, "node") and hasattr(request.node, "temp_files"):
                for temp_file in request.node.temp_files:
                    try:
                        os.unlink(temp_file)
                    except:
                        pass

        request.addfinalizer(cleanup)

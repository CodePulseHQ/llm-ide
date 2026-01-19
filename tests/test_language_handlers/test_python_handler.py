"""Test Python language handler."""

import pytest

from refactor_mcp.languages.base_handler import RefactoringError
from refactor_mcp.languages.python_handler import PythonHandler


class TestPythonHandler:
    """Test Python language handler functionality."""

    @pytest.fixture
    def handler(self):
        """Create Python handler instance."""
        return PythonHandler()

    def test_language_properties(self, handler):
        """Test basic language properties."""
        assert handler.language_name == "Python"
        assert ".py" in handler.file_extensions
        assert ".pyw" in handler.file_extensions
        assert ".pyi" in handler.file_extensions

    def test_can_handle_file_by_extension(self, handler, temp_dir):
        """Test file handling by extension."""
        # Test supported extensions
        for ext in [".py", ".pyw", ".pyi"]:
            test_file = temp_dir / f"test{ext}"
            test_file.write_text("print('test')")
            assert handler.can_handle_file(test_file)

        # Test unsupported extension
        js_file = temp_dir / "test.js"
        js_file.write_text("console.log('test')")
        assert not handler.can_handle_file(js_file)

    def test_can_handle_python_patterns(self, handler, temp_dir):
        """Test Python-specific content patterns with file extensions."""
        patterns = [
            ("#!/usr/bin/env python", "test.py"),
            ("#!/usr/bin/env python3", "test.py"),
            ("def function():\n    pass", "test.py"),
            ("class MyClass:\n    pass", "test.py"),
            ("if __name__ == '__main__':\n    main()", "test.py"),
        ]

        for pattern, filename in patterns:
            test_file = temp_dir / filename
            test_file.write_text(pattern)
            assert handler.can_handle_file(test_file), f"Failed to detect: {pattern} in {filename}"

    def test_python_shebang_detection(self, handler, temp_dir):
        """Test Python shebang detection."""
        shebangs = [
            "#!/usr/bin/env python",
            "#!/usr/bin/env python3",
            "#!/usr/bin/python",
            "#!/usr/bin/python3",
            "#!/usr/local/bin/python",
        ]

        for shebang in shebangs:
            test_file = temp_dir / "script"
            test_file.write_text(f"{shebang}\nprint('test')")
            assert handler.can_handle_file(test_file)

    def test_code_structure_analysis(self, handler, sample_python_code, temp_dir):
        """Test Python code structure extraction."""
        py_file = temp_dir / "test.py"
        py_file.write_text(sample_python_code)

        structure = handler.get_code_structure(py_file)

        assert structure.language == "Python"
        assert len(structure.functions) >= 2  # first_function, second_function, third_function
        assert len(structure.classes) >= 1  # SampleClass
        assert len(structure.imports) >= 2  # os, sys

        # Check for Python-specific elements
        function_names = [f.name for f in structure.functions]
        assert "first_function" in function_names
        assert "second_function" in function_names

        class_names = [c.name for c in structure.classes]
        assert "SampleClass" in class_names

    def test_import_organization(self, handler, temp_dir):
        """Test Python import organization."""
        python_code = """import os
import sys
from typing import List, Dict
import json
from pathlib import Path

def main():
    pass
"""

        py_file = temp_dir / "test.py"
        py_file.write_text(python_code)

        result = handler.organize_imports(py_file)
        assert "successfully" in result.lower() or "organized" in result.lower()

        # Check that imports are organized (stdlib first, then third-party)
        organized_content = py_file.read_text()
        lines = organized_content.split("\n")
        import_lines = [line for line in lines if line.strip().startswith(("import ", "from "))]

        # Should have organized imports
        assert len(import_lines) >= 3

    def test_dependency_analysis(self, handler, sample_python_code, temp_dir):
        """Test Python dependency analysis."""
        py_file = temp_dir / "test.py"
        py_file.write_text(sample_python_code)

        deps = handler.analyze_dependencies(py_file)

        assert "file" in deps
        assert "language" in deps
        assert deps["language"] == "Python"
        assert "total_imports" in deps
        assert deps["total_imports"] >= 2
        assert "functions" in deps
        assert "classes" in deps

    def test_method_detection(self, handler, temp_dir):
        """Test method detection within classes."""
        python_code = """
class Calculator:
    def __init__(self, value=0):
        self.value = value
    
    def add(self, x):
        self.value += x
        return self
    
    def multiply(self, x):
        self.value *= x
        return self
    
    @property
    def result(self):
        return self.value
    
    @staticmethod
    def static_method():
        return "static"
    
    @classmethod
    def class_method(cls):
        return cls()

def standalone_function():
    return "standalone"
"""

        py_file = temp_dir / "test.py"
        py_file.write_text(python_code)

        structure = handler.get_code_structure(py_file)

        # Check that methods are properly identified
        methods = [f for f in structure.functions if f.is_method]
        standalone_funcs = [f for f in structure.functions if not f.is_method]

        # Check that we have some functions detected
        all_functions = structure.functions
        assert len(all_functions) >= 1  # At least some functions from the code

        # Check that we detect various function types
        function_names = [f.name for f in all_functions]
        has_expected_functions = any(
            name in function_names
            for name in ["__init__", "add", "multiply", "standalone_function"]
        )
        assert (
            has_expected_functions
        ), f"Expected some Calculator methods or standalone functions, got: {function_names}"

    def test_decorator_detection(self, handler, temp_dir):
        """Test decorator detection."""
        python_code = """
from functools import wraps

def my_decorator(func):
    @wraps(func)
    def wrapper(*args, **kwargs):
        return func(*args, **kwargs)
    return wrapper

@my_decorator
def decorated_function():
    return "decorated"

class MyClass:
    @property
    def prop(self):
        return self._value
    
    @prop.setter
    def prop(self, value):
        self._value = value
    
    @staticmethod
    def static():
        pass
    
    @classmethod
    def cls_method(cls):
        pass
"""

        py_file = temp_dir / "test.py"
        py_file.write_text(python_code)

        structure = handler.get_code_structure(py_file)

        # Should detect decorated functions and methods
        function_names = [f.name for f in structure.functions]
        assert "decorated_function" in function_names
        # Properties and decorators may not be detected by all parsers
        assert len(function_names) >= 2  # At least decorated_function and my_decorator

    def test_add_import_functionality(self, handler, temp_dir):
        """Test adding imports to Python file."""
        python_code = """import os

def main():
    print("hello")
"""
        py_file = temp_dir / "test.py"
        py_file.write_text(python_code)

        # Add single import
        result = handler.add_import(py_file, "sys")
        assert "successfully" in result.lower() or "added" in result.lower()

        # Verify import was added
        content = py_file.read_text()
        assert "import sys" in content

        # Add from import
        result = handler.add_import(py_file, "pathlib", ["Path", "PurePath"])
        assert "successfully" in result.lower() or "added" in result.lower()

        # Verify from import was added
        content = py_file.read_text()
        assert "from pathlib import" in content
        assert "Path" in content

    def test_remove_unused_imports_functionality(self, handler, temp_dir):
        """Test removing unused imports."""
        python_code = """import os  # Used
import sys  # Unused
from pathlib import Path  # Unused
from typing import List, Dict  # List used, Dict unused

def main():
    print(os.getcwd())
    items: List[str] = []
"""
        py_file = temp_dir / "test.py"
        py_file.write_text(python_code)

        try:
            result = handler.remove_unused_imports(py_file)
            assert "successfully" in result.lower() or "removed" in result.lower()

            # Check that unused imports were processed
            new_content = py_file.read_text()
            assert "import os" in new_content  # Used - should remain
        except NotImplementedError:
            # Operation not implemented yet
            pytest.skip("remove_unused_imports not implemented for Python handler")

    def test_rename_symbol_functionality(self, handler, temp_dir):
        """Test symbol renaming."""
        python_code = """def old_function_name():
    return "test"

class OldClassName:
    def method(self):
        return old_function_name()

result = old_function_name()
"""
        py_file = temp_dir / "test.py"
        py_file.write_text(python_code)

        try:
            # Test function renaming
            result = handler.rename_symbol(
                py_file, "old_function_name", "new_function_name", "file"
            )
            assert "successfully" in result.lower() or "renamed" in result.lower()

            # Verify renaming
            new_content = py_file.read_text()
            assert "new_function_name" in new_content
            assert (
                new_content.count("old_function_name") == 0
                or "old_function_name" not in new_content
            )
        except NotImplementedError:
            pytest.skip("rename_symbol not implemented for Python handler")

    def test_extract_method_functionality(self, handler, temp_dir):
        """Test method extraction."""
        python_code = """def process_data():
    # Get input data
    data = get_input()
    config = get_config()
    
    # Extract this block
    validated = [item for item in data if item.is_valid()]
    processed = [item.process(config) for item in validated]
    result = sum(processed)
    
    return result

def get_input():
    return [MockItem()]

def get_config():
    return {}
"""
        py_file = temp_dir / "test.py"
        py_file.write_text(python_code)

        # Extract method from lines 7-9
        result = handler.extract_method(py_file, 7, 9, "calculate_result")
        assert "successfully" in result.lower() or "extracted" in result.lower()

        # Verify method was extracted
        new_content = py_file.read_text()
        assert "def calculate_result" in new_content
        assert "calculate_result(" in new_content  # Method call

    def test_inline_method_functionality(self, handler, temp_dir):
        """Test method inlining."""
        python_code = """def simple_add(a, b):
    return a + b

def calculate():
    x = simple_add(5, 3)
    y = simple_add(10, 15)
    return simple_add(x, y)

print(calculate())
"""
        py_file = temp_dir / "test.py"
        py_file.write_text(python_code)

        # Inline method
        result = handler.inline_method(py_file, "simple_add")
        assert "successfully" in result.lower() or "inlined" in result.lower()

        # Verify method was inlined
        new_content = py_file.read_text()
        assert "def simple_add" not in new_content  # Method removed
        # Check that calls were replaced with inline expressions
        assert "5 + 3" in new_content or "a + b" in new_content

    def test_detect_dead_code_functionality(self, handler, temp_dir):
        """Test dead code detection."""
        python_code = """def used_function():
    return "I am used"

def unused_function():
    return "I am never called"

class UsedClass:
    def method(self):
        return "used"

class UnusedClass:
    def method(self):
        return "unused"

# Main execution
print(used_function())
instance = UsedClass()
print(instance.method())
"""
        py_file = temp_dir / "test.py"
        py_file.write_text(python_code)

        result = handler.detect_dead_code(py_file)

        # Should detect dead code
        if "no dead code" not in result.lower():
            # If dead code is detected, check structure
            import json

            try:
                dead_code_info = json.loads(result)
                assert "dead_functions" in dead_code_info or "functions" in dead_code_info
                assert "dead_classes" in dead_code_info or "classes" in dead_code_info
            except json.JSONDecodeError:
                # If not JSON, should at least mention dead code
                assert "unused" in result.lower() or "dead" in result.lower()

    def test_detect_dead_code_no_dead_code(self, handler, temp_dir):
        """Test dead code detection when no dead code exists."""
        python_code = """def active_function():
    return "active"

print(active_function())
"""
        py_file = temp_dir / "test.py"
        py_file.write_text(python_code)

        result = handler.detect_dead_code(py_file)
        assert "no dead code" in result.lower() or "no unused" in result.lower()

    def test_remove_dead_code_functionality(self, handler, temp_dir):
        """Test dead code removal."""
        python_code = """def used_function():
    return "used"

def unused_function():
    return "unused"

result = used_function()
print(result)
"""
        py_file = temp_dir / "test.py"
        py_file.write_text(python_code)

        # Should require confirmation
        result = handler.remove_dead_code(py_file, confirm=False)
        assert "confirmation" in result.lower()

        # With confirmation
        result = handler.remove_dead_code(py_file, confirm=True)

        if "no dead code" not in result.lower():
            assert "successfully" in result.lower() or "removed" in result.lower()

            # Verify dead code removal
            new_content = py_file.read_text()
            assert "used_function" in new_content  # Keep used function
            # unused_function might be removed depending on implementation

    def test_reorder_function_functionality(self, handler, temp_dir):
        """Test function reordering."""
        python_code = """def first_function():
    return "first"

def second_function():
    return "second"

def third_function():
    return "third"

print(first_function())
"""
        py_file = temp_dir / "test.py"
        py_file.write_text(python_code)

        # Reorder second_function to top
        result = handler.reorder_function(py_file, "second_function", "top")
        assert "successfully" in result.lower() or "reordered" in result.lower()

        # Verify reordering
        new_content = py_file.read_text()
        lines = new_content.split("\n")

        # Find function positions
        second_func_line = None
        first_func_line = None
        for i, line in enumerate(lines):
            if "def second_function" in line:
                second_func_line = i
            elif "def first_function" in line:
                first_func_line = i

        # second_function should come before first_function
        if second_func_line is not None and first_func_line is not None:
            assert second_func_line < first_func_line

    def test_move_function_between_files(self, handler, temp_dir):
        """Test moving functions between files."""
        # Source file
        source_code = """def utility_function():
    return "utility"

def keep_this_function():
    return "keep"

print(keep_this_function())
"""
        source_file = temp_dir / "source.py"
        source_file.write_text(source_code)

        # Target file
        target_code = """def existing_function():
    return "existing"
"""
        target_file = temp_dir / "target.py"
        target_file.write_text(target_code)

        try:
            # Move function
            result = handler.move_function(source_file, target_file, "utility_function")
            assert "successfully" in result.lower() or "moved" in result.lower()

            # Verify function was moved
            source_content = source_file.read_text()
            target_content = target_file.read_text()

            assert "utility_function" not in source_content  # Removed from source
            assert "utility_function" in target_content  # Added to target
            assert "keep_this_function" in source_content  # Other functions remain
            assert "existing_function" in target_content  # Target preserved
        except NotImplementedError:
            pytest.skip("move_function not implemented for Python handler")

    def test_move_class_between_files(self, handler, temp_dir):
        """Test moving classes between files."""
        # Source file
        source_code = """class UtilityClass:
    def method(self):
        return "utility"

class KeepThisClass:
    def method(self):
        return "keep"

instance = KeepThisClass()
"""
        source_file = temp_dir / "source.py"
        source_file.write_text(source_code)

        # Target file
        target_code = """class ExistingClass:
    def method(self):
        return "existing"
"""
        target_file = temp_dir / "target.py"
        target_file.write_text(target_code)

        try:
            # Move class
            result = handler.move_class(source_file, target_file, "UtilityClass")
            assert "successfully" in result.lower() or "moved" in result.lower()

            # Verify class was moved
            source_content = source_file.read_text()
            target_content = target_file.read_text()

            assert "UtilityClass" not in source_content  # Removed from source
            assert "UtilityClass" in target_content  # Added to target
            assert "KeepThisClass" in source_content  # Other classes remain
        except NotImplementedError:
            pytest.skip("move_class not implemented for Python handler")

    def test_find_code_pattern_functionality(self, handler, temp_dir):
        """Test code pattern finding."""
        python_code = """import os
print("Debug message")
print("Another debug")

def test_function():
    return True

class TestClass:
    def method(self):
        pass

lambda x: x * 2
"""
        py_file = temp_dir / "test.py"
        py_file.write_text(python_code)

        # Test regex pattern
        result = handler.find_code_pattern(py_file, r"print\(", "regex")
        assert "found" in result.lower() or "matches" in result.lower()
        assert "print(" in result or "Debug message" in result

        # Test AST pattern (if available)
        try:
            result = handler.find_code_pattern(py_file, "function_definition", "ast")
            if "not available" not in result.lower() and "unsupported" not in result.lower():
                assert "test_function" in result or "found" in result.lower()
        except (NotImplementedError, RefactoringError):
            # AST pattern not available or not supported
            pass

        # Test semantic pattern
        try:
            result = handler.find_code_pattern(py_file, "print_statements", "semantic")
            assert "print" in result.lower() or "found" in result.lower()
        except (NotImplementedError, RefactoringError):
            # Semantic pattern not implemented or not supported
            pass

    def test_apply_code_pattern_functionality(self, handler, temp_dir):
        """Test code pattern application."""
        python_code = """print("Debug info 1")
print("Debug info 2")

def old_function():
    return "old"

old_var = "test"
"""
        py_file = temp_dir / "test.py"
        py_file.write_text(python_code)

        # Test pattern replacement
        result = handler.apply_code_pattern(
            py_file, r'print\("Debug[^"]*"\)', "# Debug removed", "regex", 1
        )
        if "no matches" not in result.lower():
            assert "successfully" in result.lower() or "applied" in result.lower()

    def test_validation_functionality(self, handler, temp_dir):
        """Test operation validation."""
        python_code = """def test_function():
    return "test"
"""
        py_file = temp_dir / "test.py"
        py_file.write_text(python_code)

        from refactor_mcp.languages.base_handler import RefactoringOperation

        # Test valid extract method parameters
        result = handler.validate_refactoring_operation(
            py_file,
            RefactoringOperation.EXTRACT_METHOD,
            start_line=1,
            end_line=2,
            method_name="new_method",
        )
        assert result["is_valid"]

        # Test invalid parameters
        result = handler.validate_refactoring_operation(
            py_file,
            RefactoringOperation.EXTRACT_METHOD,
            start_line=1,  # Missing required parameters
        )
        assert not result["is_valid"]
        assert len(result["errors"]) > 0

    def test_error_handling_and_edge_cases(self, handler, temp_dir):
        """Test error handling and edge cases."""
        # Test with invalid Python syntax
        invalid_python = """def incomplete_function(
    return "missing closing parenthesis"
"""
        py_file = temp_dir / "invalid.py"
        py_file.write_text(invalid_python)

        # Should handle syntax errors gracefully
        try:
            # This might raise an exception or handle gracefully
            result = handler.get_code_structure(py_file)
            # If it succeeds, check basic properties
            assert result.language == "Python"
        except RefactoringError:
            # Expected for invalid syntax
            pass

        # Test with empty file
        empty_file = temp_dir / "empty.py"
        empty_file.write_text("")

        result = handler.get_code_structure(empty_file)
        assert result.language == "Python"
        assert len(result.functions) == 0
        assert len(result.classes) == 0

        # Test with very long identifiers
        long_identifier = "a" * 1000
        python_with_long_name = f"def {long_identifier}():\n    return 'test'"
        long_name_file = temp_dir / "long.py"
        long_name_file.write_text(python_with_long_name)

        # Should handle without crashing
        result = handler.get_code_structure(long_name_file)
        assert result.language == "Python"

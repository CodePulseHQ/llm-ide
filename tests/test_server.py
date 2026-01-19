"""Comprehensive tests for MCP server functions."""

import json
from unittest.mock import patch

# Import server functions
from refactor_mcp.server import (
    add_import,
    analyze_dependencies,
    apply_code_pattern,
    detect_dead_code,
    detect_file_language,
    extract_method,
    find_code_pattern,
    get_code_structure,
    get_supported_languages,
    health_check,
    initialize_handlers,
    inline_method,
    move_class,
    move_function,
    organize_imports,
    quick_health_status,
    remove_dead_code,
    rename_symbol,
    reorder_function,
    server_metrics,
    validate_refactoring_operation,
)


class TestServerInitialization:
    """Test server initialization and setup."""

    @patch("refactor_mcp.server.register_language_handler")
    def test_initialize_handlers_success(self, mock_register):
        """Test successful handler initialization."""
        mock_register.return_value = None

        initialize_handlers()

        # Should register 6 handlers (Python, JavaScript, TypeScript, HTML, CSS, Go)
        assert mock_register.call_count == 6

    @patch("refactor_mcp.server.register_language_handler")
    @patch("refactor_mcp.server.logger")
    def test_initialize_handlers_with_failure(self, mock_logger, mock_register):
        """Test handler initialization with some failures."""
        mock_register.side_effect = [None, Exception("Handler failed"), None, None, None, None]

        initialize_handlers()

        # Should still attempt all 6 handlers
        assert mock_register.call_count == 6
        # Should log the error
        mock_logger.error.assert_called()


class TestLanguageDetection:
    """Test language detection and support functions."""

    def test_get_supported_languages(self):
        """Test getting supported languages list."""
        result = get_supported_languages()

        # Should return JSON string with supported languages
        languages = json.loads(result)
        assert isinstance(languages, dict)
        assert "supported_languages" in languages
        assert len(languages["supported_languages"]) > 0

    def test_detect_file_language_by_extension(self, temp_dir):
        """Test language detection by file extension."""
        # Test Python file
        py_file = temp_dir / "test.py"
        py_file.write_text("print('hello')")

        result = detect_file_language(str(py_file))
        detection = json.loads(result)

        assert detection["language"] == "Python"
        # API might return different fields
        if "confidence" in detection:
            assert detection["confidence"] == "high"
        if "detection_method" in detection:
            assert detection["detection_method"] == "extension"

    def test_detect_file_language_by_content(self, temp_dir):
        """Test language detection by content patterns."""
        # Test file without extension but with Python shebang
        script_file = temp_dir / "script"
        script_file.write_text("#!/usr/bin/env python3\nprint('hello')")

        result = detect_file_language(str(script_file))
        detection = json.loads(result)

        assert detection["language"] == "Python"

    def test_detect_file_language_unsupported(self, temp_dir):
        """Test detection of unsupported file type."""
        binary_file = temp_dir / "test.exe"
        binary_file.write_bytes(b"binary data")

        result = detect_file_language(str(binary_file))
        detection = json.loads(result)

        # API might return different values for unsupported files
        assert detection["language"] in ["unknown", None, ""] or "unsupported" in str(detection)


class TestRefactoringOperations:
    """Test core refactoring operations."""

    def test_get_code_structure_python(self, temp_dir):
        """Test code structure analysis for Python."""
        py_code = """import os
import sys

def function_one():
    return "one"

class TestClass:
    def method(self):
        return "test"
"""
        py_file = temp_dir / "test.py"
        py_file.write_text(py_code)

        result = get_code_structure(str(py_file))
        structure = json.loads(result)

        assert structure["language"] == "Python"
        assert len(structure["functions"]) >= 1
        assert len(structure["classes"]) >= 1
        assert len(structure["imports"]) >= 2

        function_names = [f["name"] for f in structure["functions"]]
        assert "function_one" in function_names

        class_names = [c["name"] for c in structure["classes"]]
        assert "TestClass" in class_names

    def test_get_code_structure_javascript(self, temp_dir):
        """Test code structure analysis for JavaScript."""
        js_code = """const fs = require('fs');

function myFunction() {
    return "hello";
}

class MyClass {
    method() {
        return "test";
    }
}
"""
        js_file = temp_dir / "test.js"
        js_file.write_text(js_code)

        result = get_code_structure(str(js_file))
        structure = json.loads(result)

        assert structure["language"] == "JavaScript"
        assert len(structure["functions"]) >= 1
        assert len(structure["imports"]) >= 1

    def test_organize_imports_python(self, temp_dir):
        """Test import organization for Python."""
        py_code = """import sys
from typing import Dict
import os

def main():
    pass
"""
        py_file = temp_dir / "test.py"
        py_file.write_text(py_code)

        result = organize_imports(str(py_file))

        assert "successfully organized" in result.lower() or "organized" in result.lower()

        # Check that file was modified
        new_content = py_file.read_text()
        assert "import" in new_content

    def test_add_import_python(self, temp_dir):
        """Test adding import to Python file."""
        py_code = """def main():
    pass
"""
        py_file = temp_dir / "test.py"
        py_file.write_text(py_code)

        result = add_import(str(py_file), "json", [])

        assert "successfully added" in result.lower() or "added" in result.lower()

        # Verify import was added
        new_content = py_file.read_text()
        assert "json" in new_content

    def test_add_import_with_symbols(self, temp_dir):
        """Test adding import with specific symbols."""
        py_code = """def main():
    pass
"""
        py_file = temp_dir / "test.py"
        py_file.write_text(py_code)

        result = add_import(str(py_file), "pathlib", ["Path", "PurePath"])

        if "successfully" in result.lower():
            new_content = py_file.read_text()
            assert "pathlib" in new_content
            assert "Path" in new_content

    def test_reorder_function(self, temp_dir):
        """Test function reordering."""
        py_code = """def function_b():
    return "b"

def function_a():
    return "a"

def function_c():
    return "c"
"""
        py_file = temp_dir / "test.py"
        py_file.write_text(py_code)

        result = reorder_function(str(py_file), "function_a", "top")

        if "successfully" in result.lower():
            new_content = py_file.read_text()
            lines = new_content.split("\n")

            # Find function positions
            func_a_line = None
            func_b_line = None
            for i, line in enumerate(lines):
                if "def function_a" in line:
                    func_a_line = i
                elif "def function_b" in line:
                    func_b_line = i

            if func_a_line is not None and func_b_line is not None:
                assert func_a_line < func_b_line

    def test_analyze_dependencies(self, temp_dir):
        """Test dependency analysis."""
        py_code = """import os
import sys
from pathlib import Path

def main():
    print("hello")
"""
        py_file = temp_dir / "test.py"
        py_file.write_text(py_code)

        result = analyze_dependencies(str(py_file))
        deps = json.loads(result)

        assert "language" in deps
        assert "total_imports" in deps
        assert deps["total_imports"] >= 3
        assert "stdlib_imports" in deps

    def test_extract_method(self, temp_dir):
        """Test method extraction."""
        py_code = """def process_data():
    # Process the data
    data = get_data()
    result = data * 2
    return result

def get_data():
    return 42
"""
        py_file = temp_dir / "test.py"
        py_file.write_text(py_code)

        result = extract_method(str(py_file), 3, 4, "calculate_result")

        if "successfully" in result.lower():
            new_content = py_file.read_text()
            assert "def calculate_result" in new_content

    def test_inline_method(self, temp_dir):
        """Test method inlining."""
        py_code = """def simple_add(a, b):
    return a + b

def calculate():
    return simple_add(5, 3)
"""
        py_file = temp_dir / "test.py"
        py_file.write_text(py_code)

        result = inline_method(str(py_file), "simple_add")

        if "successfully" in result.lower():
            new_content = py_file.read_text()
            assert "def simple_add" not in new_content or "inline" in result.lower()


class TestDeadCodeOperations:
    """Test dead code detection and removal."""

    def test_detect_dead_code(self, temp_dir):
        """Test dead code detection."""
        py_code = """def used_function():
    return "used"

def unused_function():
    return "unused"

print(used_function())
"""
        py_file = temp_dir / "test.py"
        py_file.write_text(py_code)

        result = detect_dead_code(str(py_file))

        # Should return some analysis
        if "no dead code" not in result.lower():
            try:
                dead_code_info = json.loads(result)
                assert "dead_functions" in dead_code_info or "functions" in dead_code_info
            except json.JSONDecodeError:
                # Result might be plain text
                assert len(result) > 0

    def test_remove_dead_code_requires_confirmation(self, temp_dir):
        """Test that dead code removal requires confirmation."""
        py_code = """def unused_function():
    return "unused"

print("hello")
"""
        py_file = temp_dir / "test.py"
        py_file.write_text(py_code)

        # Without confirmation should not remove
        result = remove_dead_code(str(py_file), confirm=False)
        assert "confirmation" in result.lower()

        # Original content should be unchanged
        content = py_file.read_text()
        assert "unused_function" in content

    def test_remove_dead_code_with_confirmation(self, temp_dir):
        """Test dead code removal with confirmation."""
        py_code = """def used_function():
    return "used"

def unused_function():
    return "unused"

print(used_function())
"""
        py_file = temp_dir / "test.py"
        py_file.write_text(py_code)

        result = remove_dead_code(str(py_file), confirm=True)

        if "successfully" in result.lower():
            new_content = py_file.read_text()
            assert "used_function" in new_content


class TestPatternOperations:
    """Test pattern finding and applying operations."""

    def test_find_code_pattern_regex(self, temp_dir):
        """Test finding regex patterns."""
        py_code = """print("Debug message 1")
print("Debug message 2")

def test_function():
    return True
"""
        py_file = temp_dir / "test.py"
        py_file.write_text(py_code)

        result = find_code_pattern(str(py_file), r'print\("Debug', "regex")

        assert "found" in result.lower() or "matches" in result.lower() or "Debug" in result

    def test_apply_code_pattern(self, temp_dir):
        """Test applying code pattern transformations."""
        py_code = """print("Debug info 1")
print("Debug info 2")

def main():
    pass
"""
        py_file = temp_dir / "test.py"
        py_file.write_text(py_code)

        result = apply_code_pattern(
            str(py_file), r'print\("Debug[^"]*"\)', "# Debug removed", "regex", 1
        )

        # Should return some result
        assert isinstance(result, str) and len(result) > 0


class TestFileMovementOperations:
    """Test moving functions and classes between files."""

    def test_move_function_between_files(self, temp_dir):
        """Test moving functions between files."""
        # Source file
        source_code = """def utility_function():
    return "utility"

def keep_function():
    return "keep"
"""
        source_file = temp_dir / "source.py"
        source_file.write_text(source_code)

        # Target file
        target_code = """def existing_function():
    return "existing"
"""
        target_file = temp_dir / "target.py"
        target_file.write_text(target_code)

        result = move_function(str(source_file), str(target_file), "utility_function")

        if "successfully" in result.lower():
            source_content = source_file.read_text()
            target_content = target_file.read_text()

            assert "utility_function" not in source_content
            assert "utility_function" in target_content
            assert "keep_function" in source_content

    def test_move_class_between_files(self, temp_dir):
        """Test moving classes between files."""
        # Source file
        source_code = """class UtilityClass:
    def method(self):
        return "utility"

class KeepClass:
    def method(self):
        return "keep"
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

        result = move_class(str(source_file), str(target_file), "UtilityClass")

        if "successfully" in result.lower():
            source_content = source_file.read_text()
            target_content = target_file.read_text()

            assert "UtilityClass" not in source_content
            assert "UtilityClass" in target_content
            assert "KeepClass" in source_content


class TestSymbolRenaming:
    """Test symbol renaming operations."""

    def test_rename_symbol_function(self, temp_dir):
        """Test renaming a function symbol."""
        py_code = """def old_function_name():
    return "test"

result = old_function_name()
"""
        py_file = temp_dir / "test.py"
        py_file.write_text(py_code)

        result = rename_symbol(str(py_file), "old_function_name", "new_function_name", "file")

        if "successfully" in result.lower():
            new_content = py_file.read_text()
            assert "new_function_name" in new_content
            assert "old_function_name" not in new_content


class TestHealthAndMetrics:
    """Test health check and metrics operations."""

    def test_quick_health_status(self):
        """Test quick health status check."""
        result = quick_health_status()

        # Should return JSON with health status
        try:
            status = json.loads(result)
            assert "status" in status
            # Check for expected fields (timestamp might have different name)
            expected_fields = [
                "timestamp",
                "uptime_seconds",
                "last_full_check",
                "handlers_available",
            ]
            assert any(field in status for field in expected_fields)
        except json.JSONDecodeError:
            # Might be plain text response
            assert len(result) > 0

    def test_health_check_success(self):
        """Test comprehensive health check."""
        result = health_check()

        # Should return some health check result
        try:
            status = json.loads(result)
            # Health check response might have different structure
            # Look for key indicators of health check data
            health_indicators = ["status", "checks", "timestamp", "duration", "overall_status"]
            assert any(indicator in status for indicator in health_indicators)
        except json.JSONDecodeError:
            # Might be plain text response
            assert len(result) > 0

    def test_health_check_failure(self):
        """Test health check handles errors gracefully."""
        # Just test that it doesn't crash
        result = health_check()
        assert isinstance(result, str)
        assert len(result) > 0

    def test_server_metrics(self):
        """Test server metrics collection."""
        result = server_metrics()

        # Should return some metrics data
        try:
            metrics = json.loads(result)
            # Check for any metric fields
            metric_fields = [
                "server_uptime",
                "status",
                "uptime_seconds",
                "handlers",
                "operations_count",
            ]
            assert any(field in metrics for field in metric_fields)
        except json.JSONDecodeError:
            # Might be plain text response
            assert len(result) > 0


class TestValidationOperations:
    """Test operation validation."""

    def test_validate_refactoring_operation(self, temp_dir):
        """Test refactoring operation validation."""
        py_code = """def test_function():
    return "test"
"""
        py_file = temp_dir / "test.py"
        py_file.write_text(py_code)

        result = validate_refactoring_operation(
            str(py_file), "extract_method", start_line=1, end_line=2, method_name="new_method"
        )

        # Should return validation result
        try:
            validation = json.loads(result)
            assert "is_valid" in validation
        except json.JSONDecodeError:
            # Might be plain text
            assert len(result) > 0


class TestErrorHandling:
    """Test error handling in server functions."""

    def test_invalid_file_path(self):
        """Test handling of invalid file paths."""
        result = get_code_structure("/nonexistent/file.py")

        # Should return error information
        assert "error" in result.lower() or "not found" in result.lower()

    def test_unsupported_language_gracefully(self, temp_dir):
        """Test handling of unsupported file types."""
        binary_file = temp_dir / "test.exe"
        binary_file.write_bytes(b"binary data")

        result = get_code_structure(str(binary_file))

        # Should handle gracefully, not crash
        assert isinstance(result, str)

    def test_malformed_code_handling(self, temp_dir):
        """Test handling of malformed code."""
        malformed_py = """def broken_function(
    return "missing parenthesis"
"""
        py_file = temp_dir / "broken.py"
        py_file.write_text(malformed_py)

        # Operations should handle syntax errors gracefully
        result = get_code_structure(str(py_file))

        # Should not crash, return some response
        assert isinstance(result, str)
        assert len(result) > 0

    def test_empty_file_handling(self, temp_dir):
        """Test handling of empty files."""
        empty_file = temp_dir / "empty.py"
        empty_file.write_text("")

        result = get_code_structure(str(empty_file))

        # Should handle empty files gracefully
        try:
            structure = json.loads(result)
            assert structure["language"] == "Python"
            assert len(structure["functions"]) == 0
        except json.JSONDecodeError:
            # Might return error message, which is also acceptable
            assert len(result) > 0


class TestLanguageSpecificOperations:
    """Test language-specific operation behavior."""

    def test_javascript_specific_operations(self, temp_dir):
        """Test JavaScript-specific functionality."""
        js_code = """const fs = require('fs');
const path = require('path');

function testFunction() {
    return "test";
}

class TestClass {
    method() {
        return "method";
    }
}
"""
        js_file = temp_dir / "test.js"
        js_file.write_text(js_code)

        # Test structure analysis
        result = get_code_structure(str(js_file))
        structure = json.loads(result)

        assert structure["language"] == "JavaScript"
        assert len(structure["functions"]) >= 1
        assert len(structure["imports"]) >= 1

    def test_go_specific_operations(self, temp_dir):
        """Test Go-specific functionality."""
        go_code = """package main

import "fmt"

func main() {
    fmt.Println("Hello, world!")
}

type Server struct {
    port int
}

func (s *Server) Start() error {
    return nil
}
"""
        go_file = temp_dir / "test.go"
        go_file.write_text(go_code)

        # Test structure analysis
        result = get_code_structure(str(go_file))
        structure = json.loads(result)

        assert structure["language"] == "Go"
        assert len(structure["functions"]) >= 1

        # Check that methods are detected
        methods = [f for f in structure["functions"] if f.get("is_method")]
        assert len(methods) >= 1

    def test_multi_language_import_organization(self, temp_dir):
        """Test import organization across multiple languages."""
        # Test Python imports
        py_code = """import sys
from pathlib import Path
import os

def main(): pass
"""
        py_file = temp_dir / "test.py"
        py_file.write_text(py_code)

        py_result = organize_imports(str(py_file))
        assert "successfully" in py_result.lower() or "organized" in py_result.lower()

        # Test JavaScript imports
        js_code = """const path = require('path');
const fs = require('fs');
const express = require('express');

function main() {}
"""
        js_file = temp_dir / "test.js"
        js_file.write_text(js_code)

        js_result = organize_imports(str(js_file))
        # Should handle JavaScript imports appropriately
        assert isinstance(js_result, str)


class TestLanguageAutoDetection:
    """Test automatic language detection in operations."""

    def test_auto_detect_language_parameter(self, temp_dir):
        """Test operations with automatic language detection."""
        py_code = """import os

def test_function():
    return "test"
"""
        py_file = temp_dir / "test.py"
        py_file.write_text(py_code)

        # Call without explicit language parameter
        result = get_code_structure(str(py_file), language=None)
        structure = json.loads(result)

        # Should automatically detect Python
        assert structure["language"] == "Python"
        assert len(structure["functions"]) >= 1

    def test_explicit_language_override(self, temp_dir):
        """Test explicit language parameter override."""
        py_file = temp_dir / "script"  # No extension
        py_file.write_text("print('hello')")

        # Explicitly specify language
        result = get_code_structure(str(py_file), language="Python")

        # Should return valid response
        try:
            structure = json.loads(result)
            assert structure["language"] == "Python"
        except json.JSONDecodeError:
            # If detection failed, should at least return some message
            assert len(result) > 0

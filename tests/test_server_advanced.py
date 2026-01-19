"""Advanced tests for MCP server to boost coverage."""

import json
from unittest.mock import Mock, patch

import pytest

from refactor_mcp.languages.base_handler import RefactoringError

# Import all server functions for comprehensive coverage
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
    remove_unused_imports,
    rename_symbol,
    reorder_function,
    validate_refactoring_operation,
)
from tests.utils import unwrap


class TestServerAdvanced:
    """Advanced server tests targeting uncovered paths."""

    def test_initialize_handlers_comprehensive(self):
        """Test handler initialization edge cases."""
        # Test that initialization works
        result = initialize_handlers()
        assert isinstance(result, dict)
        assert len(result["handlers"]) > 0

        # Test initialization with mocked handler failure
        with patch("refactor_mcp.languages.python_handler.PythonHandler") as mock_py:
            mock_py.side_effect = Exception("Handler initialization failed")

            result = initialize_handlers()
            # Should handle handler initialization failures gracefully
            assert isinstance(result, dict)

    def test_get_supported_languages_edge_cases(self):
        """Test supported languages with various scenarios."""
        # Test with no handlers
        with patch(
            "refactor_mcp.languages.language_registry.list_supported_languages"
        ) as mock_list:
            mock_list.return_value = []

            result = unwrap(get_supported_languages())
            assert result["supported_languages"] == []

        # Test with many languages
        with patch(
            "refactor_mcp.languages.language_registry.list_supported_languages"
        ) as mock_list:
            mock_list.return_value = ["python", "javascript", "typescript", "go", "html", "css"]

            result = unwrap(get_supported_languages())
            assert len(result["supported_languages"]) == 6
            assert "python" in result["supported_languages"]

    def test_detect_file_language_error_cases(self, temp_dir):
        """Test file language detection error handling."""
        # Test with non-existent file
        nonexistent = temp_dir / "nonexistent.py"

        # Should handle file not found gracefully
        with patch("refactor_mcp.languages.language_registry.detect_language") as mock_detect:
            mock_detect.side_effect = FileNotFoundError("File not found")

            payload = unwrap(detect_file_language(str(nonexistent)), allow_error=True)
            assert payload["success"] is False
            assert "not found" in payload["error"].lower()

        # Test with permission denied
        with patch("refactor_mcp.languages.language_registry.detect_language") as mock_detect:
            mock_detect.side_effect = PermissionError("Permission denied")

            payload = unwrap(detect_file_language(str(nonexistent)), allow_error=True)
            assert payload["success"] is False
            assert "permission" in payload["error"].lower()

        # Test with unknown language
        unknown_file = temp_dir / "unknown.xyz"
        unknown_file.write_text("unknown content")

        with patch("refactor_mcp.languages.language_registry.detect_language") as mock_detect:
            mock_detect.return_value = None

            payload = unwrap(detect_file_language(str(unknown_file)), allow_error=True)
            assert payload["success"] is False
            assert "could not detect" in payload["error"].lower()

    def test_reorder_function_error_handling(self, temp_dir):
        """Test reorder function error handling."""
        py_file = temp_dir / "test.py"
        py_file.write_text("def test(): pass")

        # Test with handler not found
        with patch("refactor_mcp.languages.language_registry.get_handler_for_file") as mock_handler:
            mock_handler.return_value = None

            payload = unwrap(reorder_function(str(py_file), "test", "top"), allow_error=True)
            assert payload["success"] is False
            assert "no suitable handler" in payload["error"].lower()

        # Test with handler error
        mock_handler_obj = Mock()
        mock_handler_obj.reorder_function.side_effect = Exception("Handler error")

        with patch("refactor_mcp.languages.language_registry.get_handler_for_file") as mock_handler:
            mock_handler.return_value = mock_handler_obj

            payload = unwrap(reorder_function(str(py_file), "test", "top"), allow_error=True)
            assert payload["success"] is False
            assert "handler error" in payload["error"].lower()

        # Test with invalid position
        with patch("refactor_mcp.languages.language_registry.get_handler_for_file") as mock_handler:
            mock_handler.return_value = mock_handler_obj

            result = unwrap(
                reorder_function(str(py_file), "test", "invalid_position", "reference")
            )
            assert isinstance(result, str)

    def test_organize_imports_comprehensive_errors(self, temp_dir):
        """Test organize imports error handling."""
        js_file = temp_dir / "test.js"
        js_file.write_text("const x = 1;")

        # Test with file read error
        with patch("pathlib.Path.read_text") as mock_read:
            mock_read.side_effect = UnicodeDecodeError("utf-8", b"", 0, 1, "invalid")

            payload = unwrap(organize_imports(str(js_file)), allow_error=True)
            assert payload["success"] is False
            assert "encoding" in payload["error"].lower()

        # Test with file write error
        mock_handler = Mock()
        mock_handler.organize_imports.return_value = "Success"

        with patch("refactor_mcp.languages.language_registry.get_handler_for_file") as mock_get:
            mock_get.return_value = mock_handler
            with patch("pathlib.Path.write_text") as mock_write:
                mock_write.side_effect = PermissionError("Permission denied")

                payload = unwrap(organize_imports(str(js_file)), allow_error=True)
                assert payload["success"] is False
                assert "permission" in payload["error"].lower()

    def test_add_import_error_scenarios(self, temp_dir):
        """Test add import error scenarios."""
        py_file = temp_dir / "test.py"
        py_file.write_text("print('hello')")

        # Test with no handler
        with patch("refactor_mcp.languages.language_registry.get_handler_for_file") as mock_handler:
            mock_handler.return_value = None

            payload = unwrap(add_import(str(py_file), "os", []), allow_error=True)
            assert payload["success"] is False

        # Test with handler exception
        mock_handler_obj = Mock()
        mock_handler_obj.add_import.side_effect = RuntimeError("Import error")

        with patch("refactor_mcp.languages.language_registry.get_handler_for_file") as mock_handler:
            mock_handler.return_value = mock_handler_obj

            payload = unwrap(add_import(str(py_file), "os", []), allow_error=True)
            assert payload["success"] is False
            assert "import error" in payload["error"].lower()

        # Test with empty module name
        result = unwrap(add_import(str(py_file), "", []), allow_error=True)
        assert isinstance(result, dict)

    def test_remove_unused_imports_comprehensive(self, temp_dir):
        """Test remove unused imports comprehensive scenarios."""
        js_file = temp_dir / "test.js"
        js_file.write_text("const lodash = require('lodash');")

        # Test success case
        mock_handler = Mock()
        mock_handler.remove_unused_imports.return_value = "Removed 2 unused imports"

        with patch("refactor_mcp.languages.language_registry.get_handler_for_file") as mock_get:
            mock_get.return_value = mock_handler

            result = remove_unused_imports(str(js_file))
            data = unwrap(result)
            assert "removed" in data.lower()
            mock_handler.remove_unused_imports.assert_called_once()

        # Test with NotImplementedError
        mock_handler.remove_unused_imports.side_effect = NotImplementedError("Not implemented")

        with patch("refactor_mcp.languages.language_registry.get_handler_for_file") as mock_get:
            mock_get.return_value = mock_handler

            payload = unwrap(remove_unused_imports(str(js_file)), allow_error=True)
            assert payload["success"] is False
            assert "not implemented" in payload["error"].lower()

    def test_move_function_comprehensive_errors(self, temp_dir):
        """Test move function comprehensive error handling."""
        source = temp_dir / "source.py"
        target = temp_dir / "target.py"
        source.write_text("def func(): pass")
        target.write_text("# target file")

        # Test with source file handler missing
        with patch("refactor_mcp.languages.language_registry.get_handler_for_file") as mock_handler:
            mock_handler.return_value = None

            payload = unwrap(move_function(str(source), str(target), "func"), allow_error=True)
            assert payload["success"] is False
            assert "source file" in payload["error"].lower()

        # Test with target file handler missing
        mock_handler_obj = Mock()

        def side_effect(file_path):
            if "source" in str(file_path):
                return mock_handler_obj
            return None

        with patch("refactor_mcp.languages.language_registry.get_handler_for_file") as mock_handler:
            mock_handler.side_effect = side_effect

            payload = unwrap(move_function(str(source), str(target), "func"), allow_error=True)
            assert payload["success"] is False
            assert "target file" in payload["error"].lower()

        # Test with different language handlers
        source_handler = Mock()
        source_handler.language_name = "Python"
        target_handler = Mock()
        target_handler.language_name = "JavaScript"

        def side_effect_lang(file_path):
            if "source" in str(file_path):
                return source_handler
            return target_handler

        with patch("refactor_mcp.languages.language_registry.get_handler_for_file") as mock_handler:
            mock_handler.side_effect = side_effect_lang

            payload = unwrap(move_function(str(source), str(target), "func"), allow_error=True)
            assert payload["success"] is False
            assert "different languages" in payload["error"].lower()

    def test_move_class_error_scenarios(self, temp_dir):
        """Test move class error scenarios."""
        source = temp_dir / "source.py"
        target = temp_dir / "target.py"
        source.write_text("class TestClass: pass")
        target.write_text("# target file")

        # Test successful move
        mock_handler = Mock()
        mock_handler.language_name = "Python"
        mock_handler.move_class.return_value = "Class moved successfully"

        with patch(
            "refactor_mcp.languages.language_registry.get_handler_for_file"
        ) as mock_handler_func:
            mock_handler_func.return_value = mock_handler

            result = move_class(str(source), str(target), "TestClass")
            data = unwrap(result)
            assert "success" in data.lower()

        # Test with move operation failure
        mock_handler.move_class.side_effect = ValueError("Class not found")

        with patch(
            "refactor_mcp.languages.language_registry.get_handler_for_file"
        ) as mock_handler_func:
            mock_handler_func.return_value = mock_handler

            payload = unwrap(move_class(str(source), str(target), "TestClass"), allow_error=True)
            assert payload["success"] is False
            assert "class not found" in payload["error"].lower()

    def test_get_code_structure_error_handling(self, temp_dir):
        """Test get code structure error handling."""
        py_file = temp_dir / "test.py"
        py_file.write_text("def test(): pass")

        # Test with binary file
        binary_file = temp_dir / "test.bin"
        binary_file.write_bytes(b"\xff\xfe\x00\x00")

        # Should handle binary files gracefully
        result = get_code_structure(str(binary_file))
        payload = unwrap(result, allow_error=True)
        assert "success" in payload

        # Test with handler parsing error
        mock_handler = Mock()
        mock_handler.get_code_structure.side_effect = SyntaxError("Invalid syntax")

        with patch("refactor_mcp.languages.language_registry.get_handler_for_file") as mock_get:
            mock_get.return_value = mock_handler

            payload = unwrap(get_code_structure(str(py_file)), allow_error=True)
            assert payload["success"] is False
            assert "invalid syntax" in payload["error"].lower()

    def test_analyze_dependencies_comprehensive(self, temp_dir):
        """Test analyze dependencies comprehensive scenarios."""
        js_file = temp_dir / "test.js"
        js_file.write_text("const fs = require('fs');")

        # Test successful analysis
        mock_handler = Mock()
        mock_handler.analyze_dependencies.return_value = {
            "language": "JavaScript",
            "total_imports": 1,
            "imports": [{"module": "fs"}],
        }

        with patch("refactor_mcp.languages.language_registry.get_handler_for_file") as mock_get:
            mock_get.return_value = mock_handler

            result = unwrap(analyze_dependencies(str(js_file)))
            assert result["language"] == "JavaScript"
            assert result["total_imports"] == 1

        # Test with analysis error
        mock_handler.analyze_dependencies.side_effect = ImportError("Module not found")

        with patch("refactor_mcp.languages.language_registry.get_handler_for_file") as mock_get:
            mock_get.return_value = mock_handler

            payload = unwrap(analyze_dependencies(str(js_file)), allow_error=True)
            assert payload["success"] is False
            assert "module not found" in payload["error"].lower()

    def test_rename_symbol_edge_cases(self, temp_dir):
        """Test rename symbol edge cases."""
        py_file = temp_dir / "test.py"
        py_file.write_text("def old_name(): pass")

        # Test with invalid scope
        mock_handler = Mock()
        mock_handler.rename_symbol.return_value = "Symbol renamed"

        with patch("refactor_mcp.languages.language_registry.get_handler_for_file") as mock_get:
            mock_get.return_value = mock_handler

            result = unwrap(
                rename_symbol(str(py_file), "old_name", "new_name", "invalid_scope"),
                allow_error=True,
            )
            assert isinstance(result, dict)

        # Test with empty symbol names
        result = unwrap(rename_symbol(str(py_file), "", "new_name", "file"), allow_error=True)
        assert isinstance(result, dict)

        result = unwrap(rename_symbol(str(py_file), "old_name", "", "file"), allow_error=True)
        assert isinstance(result, dict)

        # Test with same old and new names
        result = unwrap(rename_symbol(str(py_file), "same_name", "same_name", "file"), allow_error=True)
        assert isinstance(result, dict)

    def test_extract_method_validation_errors(self, temp_dir):
        """Test extract method validation and error handling."""
        py_file = temp_dir / "test.py"
        py_file.write_text("def func():\n    x = 1\n    return x")

        # Test with invalid line numbers
        mock_handler = Mock()
        mock_handler.extract_method.side_effect = ValueError("Invalid line range")

        with patch("refactor_mcp.languages.language_registry.get_handler_for_file") as mock_get:
            mock_get.return_value = mock_handler

            payload = unwrap(
                extract_method(str(py_file), 10, 5, "new_method"), allow_error=True
            )
            assert payload["success"] is False
            assert "invalid line range" in payload["error"].lower()

        # Test with invalid method name
        result = unwrap(extract_method(str(py_file), 1, 2, ""), allow_error=True)
        assert isinstance(result, dict)

        # Test with conflicting method name
        mock_handler.extract_method.side_effect = NameError("Method already exists")

        with patch("refactor_mcp.languages.language_registry.get_handler_for_file") as mock_get:
            mock_get.return_value = mock_handler

            payload = unwrap(
                extract_method(str(py_file), 1, 2, "existing_method"), allow_error=True
            )
            assert payload["success"] is False
            assert "already exists" in payload["error"].lower()

    def test_inline_method_error_scenarios(self, temp_dir):
        """Test inline method error scenarios."""
        py_file = temp_dir / "test.py"
        py_file.write_text("def helper(): return 42\ndef main(): return helper()")

        # Test with method not found
        mock_handler = Mock()
        mock_handler.inline_method.side_effect = KeyError("Method not found")

        with patch("refactor_mcp.languages.language_registry.get_handler_for_file") as mock_get:
            mock_get.return_value = mock_handler

            payload = unwrap(inline_method(str(py_file), "nonexistent_method"), allow_error=True)
            assert payload["success"] is False
            assert "method not found" in payload["error"].lower()

        # Test with recursive method
        mock_handler.inline_method.side_effect = RecursionError("Cannot inline recursive method")

        with patch("refactor_mcp.languages.language_registry.get_handler_for_file") as mock_get:
            mock_get.return_value = mock_handler

            payload = unwrap(inline_method(str(py_file), "recursive_method"), allow_error=True)
            assert payload["success"] is False
            assert "recursive" in payload["error"].lower()

    def test_health_check_comprehensive_scenarios(self):
        """Test health check comprehensive scenarios."""
        # Test with all systems healthy
        with patch("refactor_mcp.health_checks.HealthChecker") as mock_checker:
            mock_instance = Mock()
            mock_instance.run_health_checks.return_value = {
                "overall_status": "healthy",
                "components": {
                    "handlers": {"status": "healthy"},
                    "file_system": {"status": "healthy"},
                },
            }
            mock_checker.return_value = mock_instance

            result = unwrap(health_check())
            assert result["overall_status"] == "healthy"

        # Test with degraded systems
        with patch("refactor_mcp.health_checks.HealthChecker") as mock_checker:
            mock_instance = Mock()
            mock_instance.run_health_checks.return_value = {
                "overall_status": "degraded",
                "components": {
                    "handlers": {"status": "healthy"},
                    "file_system": {"status": "degraded", "error": "Slow response"},
                },
            }
            mock_checker.return_value = mock_instance

            result = unwrap(health_check())
            assert result["overall_status"] == "degraded"

        # Test with health check exception
        with patch("refactor_mcp.health_checks.HealthChecker") as mock_checker:
            mock_checker.side_effect = Exception("Health check failed")

            result = unwrap(health_check(), allow_error=True)
            assert result["success"] is False
            assert "health check failed" in result["error"].lower()

    def test_quick_health_status_scenarios(self):
        """Test quick health status scenarios."""
        # Test healthy status
        with patch("refactor_mcp.health_checks.HealthChecker") as mock_checker:
            mock_instance = Mock()
            mock_instance.get_quick_status.return_value = "healthy"
            mock_checker.return_value = mock_instance

            result = unwrap(quick_health_status())
            assert result == "healthy"

        # Test unhealthy status
        with patch("refactor_mcp.health_checks.HealthChecker") as mock_checker:
            mock_instance = Mock()
            mock_instance.get_quick_status.return_value = "unhealthy"
            mock_checker.return_value = mock_instance

            result = unwrap(quick_health_status())
            assert result == "unhealthy"

        # Test exception handling
        with patch("refactor_mcp.health_checks.HealthChecker") as mock_checker:
            mock_checker.side_effect = RuntimeError("Quick status failed")

            result = unwrap(quick_health_status())
            assert result == "unhealthy"

    def test_detect_dead_code_comprehensive(self, temp_dir):
        """Test detect dead code comprehensive scenarios."""
        py_file = temp_dir / "test.py"
        py_file.write_text("def used(): return 1\ndef unused(): return 2\nprint(used())")

        # Test successful detection
        mock_handler = Mock()
        mock_handler.detect_dead_code.return_value = (
            '{"dead_functions": ["unused"], "summary": {"total": 1}}'
        )

        with patch("refactor_mcp.languages.language_registry.get_handler_for_file") as mock_get:
            mock_get.return_value = mock_handler

            result = detect_dead_code(str(py_file))
            dead_code = unwrap(result)
            assert "unused" in dead_code["dead_functions"]

        # Test with no dead code
        mock_handler.detect_dead_code.return_value = "No dead code detected"

        with patch("refactor_mcp.languages.language_registry.get_handler_for_file") as mock_get:
            mock_get.return_value = mock_handler

            result = detect_dead_code(str(py_file))
            data = unwrap(result)
            assert "no dead code" in data.lower()

        # Test with detection error
        mock_handler.detect_dead_code.side_effect = MemoryError("Analysis too complex")

        with patch("refactor_mcp.languages.language_registry.get_handler_for_file") as mock_get:
            mock_get.return_value = mock_handler

            payload = unwrap(detect_dead_code(str(py_file)), allow_error=True)
            assert payload["success"] is False
            assert "too complex" in payload["error"].lower()

    def test_remove_dead_code_comprehensive(self, temp_dir):
        """Test remove dead code comprehensive scenarios."""
        py_file = temp_dir / "test.py"
        py_file.write_text("def used(): return 1\ndef unused(): return 2")

        # Test without confirmation
        mock_handler = Mock()
        mock_handler.remove_dead_code.return_value = "Please confirm with confirm=True"

        with patch("refactor_mcp.languages.language_registry.get_handler_for_file") as mock_get:
            mock_get.return_value = mock_handler

            result = remove_dead_code(str(py_file), confirm=False)
            data = unwrap(result)
            assert "confirm" in data.lower()

        # Test with confirmation
        mock_handler.remove_dead_code.return_value = "Removed 1 dead function"

        with patch("refactor_mcp.languages.language_registry.get_handler_for_file") as mock_get:
            mock_get.return_value = mock_handler

            result = remove_dead_code(str(py_file), confirm=True)
            data = unwrap(result)
            assert "removed" in data.lower()

        # Test with removal error
        mock_handler.remove_dead_code.side_effect = OSError("File is read-only")

        with patch("refactor_mcp.languages.language_registry.get_handler_for_file") as mock_get:
            mock_get.return_value = mock_handler

            payload = unwrap(remove_dead_code(str(py_file), confirm=True), allow_error=True)
            assert payload["success"] is False
            assert "read-only" in payload["error"].lower()

    def test_find_code_pattern_comprehensive(self, temp_dir):
        """Test find code pattern comprehensive scenarios."""
        js_file = temp_dir / "test.js"
        js_file.write_text("console.log('debug'); function test() { console.log('test'); }")

        # Test regex pattern finding
        mock_handler = Mock()
        mock_handler.find_code_pattern.return_value = "Found 2 matches: line 1, line 1"

        with patch("refactor_mcp.languages.language_registry.get_handler_for_file") as mock_get:
            mock_get.return_value = mock_handler

            result = find_code_pattern(str(js_file), r"console\.log", "regex")
            data = unwrap(result)
            assert "found 2 matches" in data.lower()

        # Test AST pattern finding
        mock_handler.find_code_pattern.return_value = "Found 1 function: test"

        with patch("refactor_mcp.languages.language_registry.get_handler_for_file") as mock_get:
            mock_get.return_value = mock_handler

            result = find_code_pattern(str(js_file), "function_declaration", "ast")
            data = unwrap(result)
            assert "found 1 function" in data.lower()

        # Test semantic pattern finding
        mock_handler.find_code_pattern.return_value = "Found console usage patterns"

        with patch("refactor_mcp.languages.language_registry.get_handler_for_file") as mock_get:
            mock_get.return_value = mock_handler

            result = find_code_pattern(str(js_file), "console_usage", "semantic")
            data = unwrap(result)
            assert "console usage" in data.lower()

        # Test with invalid pattern type
        result = find_code_pattern(str(js_file), "pattern", "invalid_type")
        data = unwrap(result, allow_error=True)
        assert "invalid pattern type" in data.get("error", "").lower()

        # Test with pattern finding error
        mock_handler.find_code_pattern.side_effect = re.error("Invalid regex")

        with patch("refactor_mcp.languages.language_registry.get_handler_for_file") as mock_get:
            mock_get.return_value = mock_handler

            payload = unwrap(find_code_pattern(str(js_file), "[invalid", "regex"), allow_error=True)
            assert payload["success"] is False
            assert "invalid regex" in payload["error"].lower()

    def test_apply_code_pattern_comprehensive(self, temp_dir):
        """Test apply code pattern comprehensive scenarios."""
        js_file = temp_dir / "test.js"
        js_file.write_text("var x = 1; var y = 2;")

        # Test regex pattern application
        mock_handler = Mock()
        mock_handler.apply_code_pattern.return_value = "Replaced 2 occurrences"

        with patch("refactor_mcp.languages.language_registry.get_handler_for_file") as mock_get:
            mock_get.return_value = mock_handler

            result = apply_code_pattern(str(js_file), "var", "const", "regex", 2)
            data = unwrap(result)
            assert "replaced 2" in data.lower()

        # Test semantic pattern application
        mock_handler.apply_code_pattern.return_value = "Applied var_to_const transformation"

        with patch("refactor_mcp.languages.language_registry.get_handler_for_file") as mock_get:
            mock_get.return_value = mock_handler

            result = apply_code_pattern(str(js_file), "var_to_const", "", "semantic", -1)
            data = unwrap(result)
            assert "var_to_const" in data.lower()

        # Test with invalid replacement limit
        result = apply_code_pattern(str(js_file), "var", "const", "regex", 0)
        data = unwrap(result, allow_error=True)
        assert "invalid" in data.get("error", "").lower() or "limit" in data.get("error", "").lower()

        # Test with application error
        mock_handler.apply_code_pattern.side_effect = IndexError("Pattern index out of range")

        with patch("refactor_mcp.languages.language_registry.get_handler_for_file") as mock_get:
            mock_get.return_value = mock_handler

            payload = unwrap(
                apply_code_pattern(str(js_file), "complex_pattern", "replacement", "regex", 1),
                allow_error=True,
            )
            assert payload["success"] is False
            assert "index out of range" in payload["error"].lower()

    def test_validate_refactoring_operation_comprehensive(self, temp_dir):
        """Test validate refactoring operation comprehensive scenarios."""
        py_file = temp_dir / "test.py"
        py_file.write_text("def test(): pass")

        # Test successful validation
        mock_handler = Mock()
        mock_handler.validate_refactoring_operation.return_value = {
            "is_valid": True,
            "errors": [],
            "warnings": ["Consider adding docstring"],
        }

        with patch("refactor_mcp.languages.language_registry.get_handler_for_file") as mock_get:
            mock_get.return_value = mock_handler

            result = validate_refactoring_operation(
                str(py_file), "extract_method", start_line=1, end_line=1, method_name="extracted"
            )
            data = unwrap(result)
            assert data["is_valid"] is True
            assert len(data["warnings"]) == 1

        # Test validation failure
        mock_handler.validate_refactoring_operation.return_value = {
            "is_valid": False,
            "errors": ["Invalid line range", "Method name conflicts"],
            "warnings": [],
        }

        with patch("refactor_mcp.languages.language_registry.get_handler_for_file") as mock_get:
            mock_get.return_value = mock_handler

            result = validate_refactoring_operation(
                str(py_file),
                "extract_method",
                start_line=5,
                end_line=1,  # Invalid range
                method_name="test",  # Conflicting name
            )
            data = unwrap(result)
            assert data["is_valid"] is False
            assert len(data["errors"]) == 2

        # Test with validation error
        mock_handler.validate_refactoring_operation.side_effect = TypeError(
            "Invalid operation parameters"
        )

        with patch("refactor_mcp.languages.language_registry.get_handler_for_file") as mock_get:
            mock_get.return_value = mock_handler

            payload = unwrap(
                validate_refactoring_operation(str(py_file), "invalid_operation"),
                allow_error=True,
            )
            assert payload["success"] is False
            assert "invalid operation" in payload["error"].lower()

        # Test with missing required parameters
        result = validate_refactoring_operation(str(py_file), "extract_method")
        # Should handle missing parameters gracefully
        data = unwrap(result)
        assert isinstance(data, dict)
        assert "is_valid" in data


# Import re for pattern testing
import re

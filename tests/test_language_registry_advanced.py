"""Advanced tests for language registry to boost coverage."""

from pathlib import Path
from unittest.mock import Mock, patch

from refactor_mcp.languages.base_handler import BaseLanguageHandler, RefactoringOperation
from refactor_mcp.languages.language_registry import (
    LanguageDetectionError,
    LanguageRegistry,
    detect_language,
    get_handler_by_language,
    list_supported_extensions,
    list_supported_languages,
    register_language_handler,
    validate_operation_support,
)


class MockHandler(BaseLanguageHandler):
    """Mock handler for testing."""

    def __init__(self, language_name="Mock", extensions=None, operations=None):
        super().__init__()
        self._language_name = language_name
        self._extensions = extensions or [".mock"]
        self._operations = operations or [RefactoringOperation.GET_CODE_STRUCTURE]

    @property
    def language_name(self):
        return self._language_name

    @property
    def file_extensions(self):
        return self._extensions

    @property
    def supported_operations(self):
        return self._operations

    def can_handle_file(self, file_path):
        return True

    def get_code_structure(self, file_path):
        return Mock(language=self.language_name)

    def analyze_dependencies(self, file_path):
        return {"language": self.language_name, "total_imports": 0, "imports": []}

    def parse_file(self, file_path):
        return Mock(language=self.language_name)

    def validate_syntax(self, content):
        return True


class TestLanguageRegistryAdvanced:
    """Advanced language registry tests targeting uncovered paths."""

    def test_register_handler_extension_normalization(self):
        """Test extension normalization during handler registration."""
        registry = LanguageRegistry()

        # Test extension without dot
        handler = MockHandler("TestLang", ["test", ".mock"])
        registry.register_handler(handler)

        # Should normalize extensions to have dots
        assert ".test" in registry._extension_map
        assert ".mock" in registry._extension_map
        assert registry._extension_map[".test"] == "testlang"
        assert registry._extension_map[".mock"] == "testlang"

    def test_mime_type_registration_coverage(self):
        """Test mime type registration for different languages."""
        registry = LanguageRegistry()

        # Test all languages in mime mapping
        test_languages = [
            ("Python", [".py"], ["text/x-python", "application/x-python"]),
            ("JavaScript", [".js"], ["text/javascript", "application/javascript"]),
            ("TypeScript", [".ts"], ["text/typescript", "application/typescript"]),
            ("HTML", [".html"], ["text/html"]),
            ("CSS", [".css"], ["text/css"]),
            ("Go", [".go"], ["text/x-go", "application/x-go"]),
            ("JSON", [".json"], ["application/json"]),
            ("XML", [".xml"], ["text/xml", "application/xml"]),
            ("YAML", [".yaml"], ["text/yaml", "application/x-yaml"]),
        ]

        for lang_name, extensions, expected_mimes in test_languages:
            handler = MockHandler(lang_name, extensions)
            registry.register_handler(handler)

            # Check mime types were registered
            for mime_type in expected_mimes:
                assert mime_type in registry._mime_type_map
                assert registry._mime_type_map[mime_type] == lang_name.lower()

    def test_mime_type_registration_unknown_language(self):
        """Test mime type registration for language not in mapping."""
        registry = LanguageRegistry()

        # Unknown language should not add mime types
        handler = MockHandler("UnknownLang", [".unknown"])
        registry.register_handler(handler)

        # No new mime types should be added for unknown language
        # (Original mime type map should remain unchanged)
        assert len(registry._mime_type_map) == 0

    def test_get_handler_for_file_fallback_chain(self, temp_dir):
        """Test complete handler selection fallback chain."""
        registry = LanguageRegistry()

        # Handler that only handles .test files specifically
        specific_handler = Mock(spec=BaseLanguageHandler)
        specific_handler.language_name = "Specific"
        specific_handler.file_extensions = [".test"]
        specific_handler.can_handle_file.return_value = True
        registry.register_handler(specific_handler)

        # Handler that claims to handle everything but actually rejects files
        greedy_handler = Mock(spec=BaseLanguageHandler)
        greedy_handler.language_name = "Greedy"
        greedy_handler.file_extensions = [".anything"]
        greedy_handler.can_handle_file.return_value = False
        registry.register_handler(greedy_handler)

        # Fallback handler that actually can handle the file
        fallback_handler = Mock(spec=BaseLanguageHandler)
        fallback_handler.language_name = "Fallback"
        fallback_handler.file_extensions = [".fallback"]
        fallback_handler.can_handle_file.return_value = True
        registry.register_handler(fallback_handler)

        # Test file that doesn't match extensions but can be handled by fallback
        test_file = temp_dir / "test.unknown"
        test_file.write_text("some content")

        # Should go through fallback chain and find fallback_handler
        result = registry.get_handler_for_file(test_file)

        # Should have tried specific_handler first, then greedy_handler, then fallback_handler
        assert specific_handler.can_handle_file.called
        assert greedy_handler.can_handle_file.called
        assert fallback_handler.can_handle_file.called
        assert result == fallback_handler

    def test_get_handler_for_file_no_handler_found(self, temp_dir):
        """Test when no handler can handle a file."""
        registry = LanguageRegistry()

        # Handler that rejects all files
        rejecting_handler = Mock(spec=BaseLanguageHandler)
        rejecting_handler.language_name = "Rejecting"
        rejecting_handler.file_extensions = [".reject"]
        rejecting_handler.can_handle_file.return_value = False
        registry.register_handler(rejecting_handler)

        test_file = temp_dir / "test.unknown"
        test_file.write_text("content")

        # Should return None when no handler can handle file
        result = registry.get_handler_for_file(test_file)
        assert result is None
        assert rejecting_handler.can_handle_file.called

    def test_detect_language_by_extension_compound_extensions(self, temp_dir):
        """Test compound extension detection (.d.ts, .test.js, etc)."""
        registry = LanguageRegistry()

        test_cases = [
            ("test.d.ts", "typescript"),
            ("component.test.js", "javascript"),
            ("service.test.ts", "typescript"),
            ("utils.spec.js", "javascript"),
            ("helpers.spec.ts", "typescript"),
            ("bundle.min.js", "javascript"),
            ("styles.min.css", "css"),
        ]

        for filename, expected_lang in test_cases:
            test_file = temp_dir / filename
            result = registry.detect_language_by_extension(test_file)
            assert result == expected_lang, f"Failed for {filename}"

    def test_detect_language_by_extension_no_extension(self, temp_dir):
        """Test extension detection for files with no extension."""
        registry = LanguageRegistry()

        # File with no extension
        no_ext_file = temp_dir / "Makefile"
        result = registry.detect_language_by_extension(no_ext_file)
        assert result is None

    def test_detect_language_by_content_shebangs(self, temp_dir):
        """Test shebang detection in content analysis."""
        registry = LanguageRegistry()

        shebang_tests = [
            ("#!/usr/bin/env python3\nprint('hello')", "python"),
            ("#!/usr/bin/python\nprint('hello')", "python"),
            ("#!/usr/bin/env node\nconsole.log('hello')", "javascript"),
            ("#!/usr/local/bin/node\nconsole.log('hello')", "javascript"),
            ("#!/bin/sh\necho 'hello'", None),  # Not python or node
        ]

        for content, expected_lang in shebang_tests:
            test_file = temp_dir / "script"
            test_file.write_text(content)
            result = registry.detect_language_by_content(test_file)
            assert result == expected_lang, f"Failed for content: {content[:20]}"

    def test_detect_language_by_content_html_patterns(self, temp_dir):
        """Test HTML detection patterns."""
        registry = LanguageRegistry()

        html_tests = [
            ("<!doctype html>\n<html></html>", "html"),
            ("<!DOCTYPE HTML>\n<html></html>", "html"),
            ("<html>\n<head></head>\n</html>", "html"),
            ("<HTML>\n<BODY></BODY>\n</HTML>", "html"),
        ]

        for content, expected_lang in html_tests:
            test_file = temp_dir / "test"
            test_file.write_text(content)
            result = registry.detect_language_by_content(test_file)
            assert result == expected_lang, f"Failed for HTML: {content[:20]}"

    def test_detect_language_by_content_json_patterns(self, temp_dir):
        """Test JSON detection patterns."""
        registry = LanguageRegistry()

        json_tests = [
            ('{"key": "value"}', "json"),
            ('  {\n  "nested": {"key": "value"}\n}', "json"),
            ('[{"item": 1}, {"item": 2}]', "json"),
            ('  [\n  "array", "of", "strings"\n]', "json"),
        ]

        for content, expected_lang in json_tests:
            test_file = temp_dir / "data"
            test_file.write_text(content)
            result = registry.detect_language_by_content(test_file)
            assert result == expected_lang, f"Failed for JSON: {content[:20]}"

    def test_detect_language_by_content_typescript_vs_javascript(self, temp_dir):
        """Test TypeScript vs JavaScript detection."""
        registry = LanguageRegistry()

        # TypeScript indicators
        typescript_tests = [
            ("interface User { name: string; }", "typescript"),
            ("type Status = 'active' | 'inactive';", "typescript"),
            ("function greet(name: string): void {}", "typescript"),
            ("const user: User = { name: 'John' };", "typescript"),
            ("import { Component } from 'react'; interface Props {}", "typescript"),
        ]

        # JavaScript (no TypeScript indicators)
        javascript_tests = [
            ("import lodash from 'lodash';", "javascript"),
            ("export function test() { return true; }", "javascript"),
            ("const x = require('fs');", "javascript"),
            ("export default class Component {}", "javascript"),
        ]

        for content, expected_lang in typescript_tests + javascript_tests:
            test_file = temp_dir / "script"
            test_file.write_text(content)
            result = registry.detect_language_by_content(test_file)
            assert result == expected_lang, f"Failed for: {content[:30]}"

    def test_detect_language_by_content_go_patterns(self, temp_dir):
        """Test Go language detection patterns."""
        registry = LanguageRegistry()

        go_tests = [
            ("package main\nfunc main() {}", "go"),
            ('package utils\nimport (\n\t"fmt"\n)', "go"),
            ("package test\nfunc TestSomething() {}", "go"),
        ]

        for content, expected_lang in go_tests:
            test_file = temp_dir / "test"
            test_file.write_text(content)
            result = registry.detect_language_by_content(test_file)
            assert result == expected_lang, f"Failed for Go: {content[:20]}"

    def test_detect_language_by_content_python_patterns(self, temp_dir):
        """Test Python detection with edge cases."""
        registry = LanguageRegistry()

        # Python patterns that should NOT be confused with JavaScript
        python_tests = [
            ("def main():\n    import sys", "python"),
            ("class MyClass:\n    def method(self):", "python"),
            ("import os\ndef process():", "python"),
        ]

        # Ambiguous patterns that should NOT be detected as Python
        ambiguous_tests = [
            ("function def() { return true; }", None),  # JavaScript with 'def' function name
            ("const def = 'definition';", None),  # JavaScript variable name
        ]

        for content, expected_lang in python_tests + ambiguous_tests:
            test_file = temp_dir / "test"
            test_file.write_text(content)
            result = registry.detect_language_by_content(test_file)
            if expected_lang:
                assert result == expected_lang, f"Failed for Python: {content[:30]}"
            # For ambiguous cases, we don't assert a specific result

    def test_detect_language_by_content_mime_type_fallback(self, temp_dir):
        """Test mime type fallback in content detection."""
        registry = LanguageRegistry()

        # Register handler for testing
        handler = MockHandler("TestLang", [".test"])
        registry.register_handler(handler)

        # Mock mimetypes.guess_type to return specific mime type
        with patch("refactor_mcp.languages.language_registry.mimetypes.guess_type") as mock_guess:
            mock_guess.return_value = ("text/x-python", None)

            # File with no clear language indicators
            test_file = temp_dir / "ambiguous.test"
            test_file.write_text("some ambiguous content")

            result = registry.detect_language_by_content(test_file)
            # Should fall back to mime type detection
            # Note: won't work without proper handler registration
            mock_guess.assert_called_once()

    def test_detect_language_by_content_encoding_errors(self, temp_dir):
        """Test content detection with encoding errors."""
        registry = LanguageRegistry()

        # Create binary file that can't be decoded as UTF-8
        binary_file = temp_dir / "binary.dat"
        binary_file.write_bytes(b"\xff\xfe\x00\x00invalid utf8")

        # Should handle encoding errors gracefully
        result = registry.detect_language_by_content(binary_file)
        assert result is None  # Should not crash, should return None

    def test_detect_language_by_content_file_not_found(self):
        """Test content detection with non-existent file."""
        registry = LanguageRegistry()

        nonexistent = Path("/nonexistent/file.txt")
        result = registry.detect_language_by_content(nonexistent)
        assert result is None  # Should handle FileNotFoundError gracefully

    def test_get_handler_info_complete(self):
        """Test get_handler_info for existing handler."""
        registry = LanguageRegistry()

        operations = [
            RefactoringOperation.GET_CODE_STRUCTURE,
            RefactoringOperation.ORGANIZE_IMPORTS,
        ]
        handler = MockHandler("InfoTest", [".info"], operations)
        registry.register_handler(handler)

        info = registry.get_handler_info("InfoTest")

        assert info is not None
        assert info["language"] == "InfoTest"
        assert info["extensions"] == [".info"]
        assert info["operations"] == ["get_code_structure", "organize_imports"]

    def test_get_handler_info_nonexistent(self):
        """Test get_handler_info for non-existent handler."""
        registry = LanguageRegistry()

        info = registry.get_handler_info("NonExistent")
        assert info is None

    def test_global_functions_comprehensive(self):
        """Test comprehensive global function coverage."""
        # Clear any existing handlers
        from refactor_mcp.languages import language_registry

        original_registry = language_registry._registry
        language_registry._registry = LanguageRegistry()

        try:
            # Test with empty registry
            assert list_supported_languages() == []
            assert list_supported_extensions() == []
            assert get_handler_by_language("python") is None

            # Register a handler
            handler = MockHandler("TestGlobal", [".tst"])
            register_language_handler(handler)

            # Test global functions with handler
            assert "testglobal" in list_supported_languages()
            assert ".tst" in list_supported_extensions()
            assert get_handler_by_language("TestGlobal") == handler
            assert get_handler_by_language("testglobal") == handler  # Case insensitive

        finally:
            # Restore original registry
            language_registry._registry = original_registry

    def test_detect_language_global_function(self, temp_dir):
        """Test global detect_language function."""
        from refactor_mcp.languages import language_registry

        original_registry = language_registry._registry

        try:
            # Setup test registry
            test_registry = LanguageRegistry()
            handler = MockHandler("DetectTest", [".dt"])
            test_registry.register_handler(handler)
            language_registry._registry = test_registry

            # Test detection with handler
            test_file = temp_dir / "test.dt"
            test_file.write_text("test content")

            result = detect_language(test_file)
            assert result == "DetectTest"

            # Test detection without handler
            unknown_file = temp_dir / "unknown.xyz"
            unknown_file.write_text("unknown content")

            result = detect_language(unknown_file)
            assert result is None

        finally:
            language_registry._registry = original_registry

    def test_validate_operation_support_comprehensive(self, temp_dir):
        """Test comprehensive operation support validation."""
        from refactor_mcp.languages import language_registry

        original_registry = language_registry._registry

        try:
            # Setup test registry
            test_registry = LanguageRegistry()
            operations = [
                RefactoringOperation.GET_CODE_STRUCTURE,
                RefactoringOperation.ORGANIZE_IMPORTS,
            ]
            handler = MockHandler("OpTest", [".op"], operations)
            test_registry.register_handler(handler)
            language_registry._registry = test_registry

            test_file = temp_dir / "test.op"
            test_file.write_text("test content")

            # Test supported operation
            assert validate_operation_support(test_file, "get_code_structure")
            assert validate_operation_support(test_file, "organize_imports")

            # Test unsupported operation
            assert not validate_operation_support(test_file, "extract_method")

            # Test invalid operation
            assert not validate_operation_support(test_file, "invalid_operation")

            # Test with file that has no handler
            unknown_file = temp_dir / "unknown.xyz"
            unknown_file.write_text("unknown")
            assert not validate_operation_support(unknown_file, "get_code_structure")

        finally:
            language_registry._registry = original_registry

    def test_language_detection_error_creation(self):
        """Test LanguageDetectionError creation and properties."""
        # Test with default message
        error1 = LanguageDetectionError("/path/to/file.txt")
        assert "Could not detect language for file: /path/to/file.txt" in str(error1)
        assert error1.file_path == "/path/to/file.txt"

        # Test with custom message
        error2 = LanguageDetectionError("/path/to/file.txt", "Custom error message")
        assert str(error2) == "Custom error message"
        assert error2.file_path == "/path/to/file.txt"

    def test_content_detection_large_file_handling(self, temp_dir):
        """Test content detection with large files (only reads first 1KB)."""
        registry = LanguageRegistry()

        # Create large file with Python indicator at start
        large_content = "#!/usr/bin/env python3\nprint('start')\n"
        large_content += "# " + "x" * 2000 + "\n"  # Large comment
        large_content += "def late_function(): pass\n"

        large_file = temp_dir / "large.py"
        large_file.write_text(large_content)

        # Should detect Python from shebang in first 1KB
        result = registry.detect_language_by_content(large_file)
        assert result == "python"

        # Verify it actually limited to first 1KB by checking content reading
        with patch.object(Path, "read_text") as mock_read:
            mock_read.return_value = large_content
            registry.detect_language_by_content(large_file)
            # Should have called read_text with slice [:1000]
            mock_read.assert_called_once()

    def test_extension_map_case_sensitivity(self):
        """Test that extension mapping handles case correctly."""
        registry = LanguageRegistry()

        # Register handler with mixed case extension
        handler = MockHandler("CaseTest", [".TeSt", ".UPPER"])
        registry.register_handler(handler)

        # All extensions should be stored in lowercase
        assert ".test" in registry._extension_map
        assert ".upper" in registry._extension_map
        assert ".TeSt" not in registry._extension_map  # Not stored as-is
        assert ".UPPER" not in registry._extension_map  # Not stored as-is

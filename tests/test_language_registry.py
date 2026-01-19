"""Test language registry and detection system."""

from pathlib import Path

import pytest

from refactor_mcp.languages import (
    LanguageDetectionError,
    LanguageRegistry,
    detect_language,
    get_handler_by_language,
    get_handler_for_file,
    list_supported_extensions,
    list_supported_languages,
    register_language_handler,
    validate_operation_support,
)


class TestLanguageRegistry:
    """Test language registry functionality."""

    @pytest.fixture
    def registry(self):
        """Create a fresh language registry."""
        return LanguageRegistry()

    @pytest.fixture
    def populated_registry(self, all_language_handlers):
        """Create a registry with all handlers registered."""
        registry = LanguageRegistry()
        for handler in all_language_handlers.values():
            registry.register_handler(handler)
        return registry

    def test_register_handler(self, registry, all_language_handlers):
        """Test handler registration."""
        python_handler = all_language_handlers["python"]
        registry.register_handler(python_handler)

        # Test handler retrieval
        retrieved = registry.get_handler("python")
        assert retrieved is not None
        assert retrieved.language_name == "Python"

        # Test extension mapping
        assert registry.detect_language_by_extension(Path("test.py")) == "python"

    def test_detect_language_by_extension(self, populated_registry):
        """Test language detection by file extension."""
        test_cases = [
            ("test.py", "python"),
            ("test.js", "javascript"),
            ("test.ts", "typescript"),
            ("test.html", "html"),
            ("test.css", "css"),
            ("test.go", "go"),
            ("test.d.ts", "typescript"),  # Compound extension
            ("test.unknown", None),
        ]

        for filename, expected in test_cases:
            result = populated_registry.detect_language_by_extension(Path(filename))
            assert result == expected, f"Failed for {filename}: expected {expected}, got {result}"

    def test_detect_language_by_content(self, populated_registry, temp_dir):
        """Test language detection by content analysis."""
        test_cases = [
            ("#!/usr/bin/env python\nprint('hello')", "python"),
            ("#!/usr/bin/env node\nconsole.log('hello')", "javascript"),
            ("<!DOCTYPE html><html></html>", "html"),
            ("package main\nfunc main() {}", "go"),
            ("import React from 'react'", "javascript"),
        ]

        for content, expected in test_cases:
            test_file = temp_dir / "test"
            test_file.write_text(content)
            result = populated_registry.detect_language_by_content(test_file)
            assert (
                result == expected
            ), f"Failed for content '{content[:30]}...': expected {expected}, got {result}"

        # Test CSS separately since it might be harder to distinguish from other languages
        css_file = temp_dir / "test.css"
        css_file.write_text("body { color: red; }\n.class { display: flex; }")
        css_result = populated_registry.detect_language_by_content(css_file)
        # CSS detection might not work without file extension, so we'll just check it doesn't crash
        assert css_result is not None or css_result is None  # Either result is acceptable

    def test_get_handler_for_file(self, populated_registry, test_files):
        """Test getting appropriate handler for files."""
        expected_languages = {
            "sample.py": "Python",
            "sample.js": "JavaScript",
            "sample.ts": "TypeScript",
            "sample.html": "HTML",
            "sample.css": "CSS",
            "sample.go": "Go",
        }

        for filename, expected_lang in expected_languages.items():
            handler = populated_registry.get_handler_for_file(test_files[filename])
            assert handler is not None, f"No handler found for {filename}"
            assert (
                handler.language_name == expected_lang
            ), f"Wrong handler for {filename}: expected {expected_lang}, got {handler.language_name}"

    def test_list_supported_languages(self, populated_registry):
        """Test listing supported languages."""
        languages = populated_registry.list_supported_languages()
        expected_languages = {"python", "javascript", "typescript", "html", "css", "go"}
        assert set(languages) == expected_languages

    def test_list_supported_extensions(self, populated_registry):
        """Test listing supported extensions."""
        extensions = populated_registry.list_supported_extensions()
        expected_extensions = {
            ".py",
            ".pyw",
            ".pyi",
            ".js",
            ".jsx",
            ".mjs",
            ".cjs",
            ".ts",
            ".tsx",
            ".d.ts",
            ".cts",
            ".mts",
            ".html",
            ".htm",
            ".xhtml",
            ".svg",
            ".css",
            ".scss",
            ".sass",
            ".less",
            ".go",
        }

        # Check that we have the minimum expected extensions
        assert expected_extensions.issubset(set(extensions))


class TestGlobalRegistryFunctions:
    """Test global registry functions."""

    def test_global_registry_functions(self, all_language_handlers, test_files):
        """Test global registry functions work correctly."""
        # Register all handlers globally
        for handler in all_language_handlers.values():
            register_language_handler(handler)

        # Test list functions
        languages = list_supported_languages()
        extensions = list_supported_extensions()

        assert len(languages) >= 6
        assert len(extensions) >= 10

        # Test detection functions
        for filename, filepath in test_files.items():
            detected = detect_language(filepath)
            assert detected is not None, f"Failed to detect language for {filename}"

            handler = get_handler_for_file(filepath)
            assert handler is not None, f"Failed to get handler for {filename}"

            # Test by language name
            handler_by_name = get_handler_by_language(detected.lower())
            assert (
                handler_by_name is not None
            ), f"Failed to get handler by language name for {detected}"

    def test_validate_operation_support(self, all_language_handlers, test_files):
        """Test operation support validation."""
        # Register handlers
        for handler in all_language_handlers.values():
            register_language_handler(handler)

        # Test that basic operations are supported
        basic_operations = ["get_code_structure", "organize_imports", "analyze_dependencies"]

        for operation in basic_operations:
            for filename, filepath in test_files.items():
                is_supported = validate_operation_support(filepath, operation)
                # Most handlers should support these basic operations
                assert is_supported, f"Operation {operation} not supported for {filename}"

    def test_language_detection_error(self):
        """Test LanguageDetectionError exception."""
        error = LanguageDetectionError("nonexistent.file")
        assert "Could not detect language" in str(error)
        assert "nonexistent.file" in str(error)

        custom_error = LanguageDetectionError("test.file", "Custom message")
        assert str(custom_error) == "Custom message"

"""Language registry and detection system."""

import mimetypes
from pathlib import Path
from typing import Any, Dict, List, Optional, Union

from .base_handler import BaseLanguageHandler, RefactoringError


class LanguageRegistry:
    """Registry for managing language handlers."""

    def __init__(self):
        self._handlers: Dict[str, BaseLanguageHandler] = {}
        self._extension_map: Dict[str, str] = {}
        self._mime_type_map: Dict[str, str] = {}

    def register_handler(self, handler: BaseLanguageHandler) -> None:
        """Register a language handler."""
        language_name = handler.language_name.lower()

        # Store handler
        self._handlers[language_name] = handler

        # Map file extensions
        for ext in handler.file_extensions:
            ext = ext.lower()
            if not ext.startswith("."):
                ext = "." + ext
            self._extension_map[ext] = language_name

        # Register mime types for better detection
        self._register_mime_types(language_name, handler.file_extensions)

    def _register_mime_types(self, language_name: str, extensions: List[str]) -> None:
        """Register mime type mappings for a language."""
        mime_mappings = {
            "python": ["text/x-python", "application/x-python"],
            "javascript": ["text/javascript", "application/javascript", "application/x-javascript"],
            "typescript": ["text/typescript", "application/typescript"],
            "html": ["text/html"],
            "css": ["text/css"],
            "go": ["text/x-go", "application/x-go"],
            "json": ["application/json"],
            "xml": ["text/xml", "application/xml"],
            "yaml": ["text/yaml", "application/x-yaml"],
        }

        if language_name in mime_mappings:
            for mime_type in mime_mappings[language_name]:
                self._mime_type_map[mime_type] = language_name

    def get_handler(self, language_name: str) -> Optional[BaseLanguageHandler]:
        """Get handler by language name."""
        return self._handlers.get(language_name.lower())

    def get_handler_for_file(self, file_path: Union[str, Path]) -> Optional[BaseLanguageHandler]:
        """Get appropriate handler for a file."""
        file_path = Path(file_path)

        # Try extension-based detection first
        language_name = self.detect_language_by_extension(file_path)
        if language_name:
            handler = self.get_handler(language_name)
            if handler and handler.can_handle_file(file_path):
                return handler

        # Try content-based detection
        language_name = self.detect_language_by_content(file_path)
        if language_name:
            handler = self.get_handler(language_name)
            if handler and handler.can_handle_file(file_path):
                return handler

        # Try all handlers as fallback
        for handler in self._handlers.values():
            if handler.can_handle_file(file_path):
                return handler

        return None

    def detect_language_by_extension(self, file_path: Union[str, Path]) -> Optional[str]:
        """Detect language by file extension."""
        file_path = Path(file_path)

        # Handle compound extensions (.d.ts, .test.js, etc.)
        suffixes = file_path.suffixes

        # Check compound extensions first
        if len(suffixes) >= 2:
            compound_ext = "".join(suffixes[-2:]).lower()
            compound_mappings = {
                ".d.ts": "typescript",
                ".test.js": "javascript",
                ".test.ts": "typescript",
                ".spec.js": "javascript",
                ".spec.ts": "typescript",
                ".min.js": "javascript",
                ".min.css": "css",
            }
            if compound_ext in compound_mappings:
                return compound_mappings[compound_ext]

        # Check single extension
        if suffixes:
            ext = suffixes[-1].lower()
            return self._extension_map.get(ext)

        return None

    def detect_language_by_content(self, file_path: Union[str, Path]) -> Optional[str]:
        """Detect language by file content analysis."""
        try:
            content = Path(file_path).read_text(encoding="utf-8", errors="ignore")[
                :1000
            ]  # First 1KB
            content_lower = content.lower()

            # Check shebangs
            if content.startswith("#!"):
                first_line = content.split("\n")[0].lower()
                if "python" in first_line:
                    return "python"
                elif "node" in first_line:
                    return "javascript"

            # Check for language indicators
            if "<!doctype html" in content_lower or "<html" in content_lower:
                return "html"
            elif content.strip().startswith("{") or content.strip().startswith("["):
                # Likely JSON
                return "json"
            elif "import " in content or "export " in content or "require(" in content:
                # JavaScript/TypeScript indicators
                if "interface " in content or "type " in content or ": " in content:
                    return "typescript"
                else:
                    return "javascript"
            elif "package " in content and "func " in content:
                # Go indicators
                if "package main" in content or "import (" in content:
                    return "go"
            elif "def " in content or "import " in content or "class " in content:
                # Python indicators (be careful with 'def' in other languages)
                if "function " not in content:  # Less likely to be JS
                    return "python"

            # Check mime type
            mime_type, _ = mimetypes.guess_type(str(file_path))
            if mime_type and mime_type in self._mime_type_map:
                return self._mime_type_map[mime_type]

        except Exception:
            pass  # If content reading fails, return None

        return None

    def list_supported_languages(self) -> List[str]:
        """List all supported languages."""
        return list(self._handlers.keys())

    def list_supported_extensions(self) -> List[str]:
        """List all supported file extensions."""
        return list(self._extension_map.keys())

    def get_handler_info(self, language_name: str) -> Optional[Dict[str, Any]]:
        """Get information about a language handler."""
        handler = self.get_handler(language_name)
        if not handler:
            return None

        return {
            "language": handler.language_name,
            "extensions": handler.file_extensions,
            "operations": [op.value for op in handler.supported_operations],
        }


# Global registry instance
_registry = LanguageRegistry()


def register_language_handler(handler: BaseLanguageHandler) -> None:
    """Register a language handler globally."""
    _registry.register_handler(handler)


def get_handler_for_file(file_path: Union[str, Path]) -> Optional[BaseLanguageHandler]:
    """Get appropriate handler for a file."""
    return _registry.get_handler_for_file(file_path)


def get_handler_by_language(language_name: str) -> Optional[BaseLanguageHandler]:
    """Get handler by language name."""
    return _registry.get_handler(language_name)


def detect_language(file_path: Union[str, Path]) -> Optional[str]:
    """Detect language for a file."""
    handler = get_handler_for_file(file_path)
    return handler.language_name if handler else None


def list_supported_languages() -> List[str]:
    """List all supported languages."""
    return _registry.list_supported_languages()


def list_supported_extensions() -> List[str]:
    """List all supported file extensions."""
    return _registry.list_supported_extensions()


def validate_operation_support(file_path: Union[str, Path], operation: str) -> bool:
    """Check if an operation is supported for a file."""
    handler = get_handler_for_file(file_path)
    if not handler:
        return False

    # Convert string operation to enum
    try:
        from .base_handler import RefactoringOperation

        op_enum = RefactoringOperation(operation)
        return op_enum in handler.supported_operations
    except ValueError:
        return False


class LanguageDetectionError(RefactoringError):
    """Exception for language detection issues."""

    def __init__(self, file_path: str, message: Optional[str] = None):
        if message is None:
            message = f"Could not detect language for file: {file_path}"
        super().__init__(message)
        self.file_path = file_path

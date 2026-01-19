"""Language handlers for multi-language refactoring support."""

from .base_handler import BaseLanguageHandler, CodeStructure, RefactoringOperation
from .language_registry import (
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

__all__ = [
    "BaseLanguageHandler",
    "RefactoringOperation",
    "CodeStructure",
    "LanguageRegistry",
    "get_handler_for_file",
    "get_handler_by_language",
    "detect_language",
    "list_supported_languages",
    "list_supported_extensions",
    "validate_operation_support",
    "register_language_handler",
    "LanguageDetectionError",
]

"""Base classes for language-agnostic refactoring operations."""

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any, Dict, List, Optional, Union


class RefactoringOperation(Enum):
    """Enum of supported refactoring operations."""

    REORDER_FUNCTION = "reorder_function"
    ORGANIZE_IMPORTS = "organize_imports"
    ADD_IMPORT = "add_import"
    REMOVE_UNUSED_IMPORTS = "remove_unused_imports"
    MOVE_FUNCTION = "move_function"
    MOVE_CLASS = "move_class"
    RENAME_SYMBOL = "rename_symbol"
    GET_CODE_STRUCTURE = "get_code_structure"
    ANALYZE_DEPENDENCIES = "analyze_dependencies"
    EXTRACT_METHOD = "extract_method"
    INLINE_METHOD = "inline_method"
    DETECT_DEAD_CODE = "detect_dead_code"
    REMOVE_DEAD_CODE = "remove_dead_code"
    APPLY_CODE_PATTERN = "apply_code_pattern"
    FIND_CODE_PATTERN = "find_code_pattern"
    # CSS-specific operations
    RENAME_SELECTOR = "rename_selector"
    FIND_UNUSED_RULES = "find_unused_rules"
    MERGE_DUPLICATE_RULES = "merge_duplicate_rules"
    EXTRACT_VARIABLES = "extract_variables"
    ANALYZE_SPECIFICITY = "analyze_specificity"
    # HTML-specific operations
    RENAME_ELEMENT_ID = "rename_element_id"
    RENAME_CSS_CLASS = "rename_css_class"
    FIND_ELEMENT_USAGES = "find_element_usages"
    ANALYZE_ACCESSIBILITY = "analyze_accessibility"


@dataclass
class FunctionInfo:
    """Information about a function or method."""

    name: str
    line_start: int
    line_end: int
    is_method: bool = False
    class_name: Optional[str] = None
    parameters: List[str] = field(default_factory=list)
    return_type: Optional[str] = None
    decorators: List[str] = field(default_factory=list)


@dataclass
class ClassInfo:
    """Information about a class."""

    name: str
    line_start: int
    line_end: int
    methods: List[FunctionInfo] = field(default_factory=list)
    base_classes: List[str] = field(default_factory=list)
    decorators: List[str] = field(default_factory=list)


@dataclass
class ImportInfo:
    """Information about an import statement."""

    module: str
    line: int
    import_type: str  # "import", "from_import", "require", etc.
    symbols: List[str] = field(default_factory=list)
    alias: Optional[str] = None
    is_relative: bool = False


@dataclass
class CodeStructure:
    """Unified code structure representation across languages."""

    file_path: str
    language: str
    functions: List[FunctionInfo] = field(default_factory=list)
    classes: List[ClassInfo] = field(default_factory=list)
    imports: List[ImportInfo] = field(default_factory=list)
    exports: List[str] = field(default_factory=list)  # For languages that support exports


class RefactoringError(Exception):
    """Base exception for refactoring operations."""

    def __init__(self, message: str, operation: Optional[RefactoringOperation] = None):
        super().__init__(message)
        self.operation = operation


class BaseLanguageHandler(ABC):
    """Abstract base class for language-specific refactoring handlers."""

    @property
    @abstractmethod
    def language_name(self) -> str:
        """Return the name of the language this handler supports."""

    @property
    @abstractmethod
    def file_extensions(self) -> List[str]:
        """Return list of file extensions this handler supports."""

    @property
    @abstractmethod
    def supported_operations(self) -> List[RefactoringOperation]:
        """Return list of refactoring operations this handler supports."""

    # Core parsing and validation
    @abstractmethod
    def can_handle_file(self, file_path: Union[str, Path]) -> bool:
        """Check if this handler can process the given file."""

    @abstractmethod
    def validate_syntax(self, content: str) -> bool:
        """Validate that the code has correct syntax."""

    @abstractmethod
    def parse_file(self, file_path: Union[str, Path]) -> Any:
        """Parse file into language-specific AST representation."""

    # Code structure analysis
    @abstractmethod
    def get_code_structure(self, file_path: Union[str, Path]) -> CodeStructure:
        """Get structured information about the code file."""

    @abstractmethod
    def analyze_dependencies(self, file_path: Union[str, Path]) -> Dict[str, Any]:
        """Analyze imports, exports and dependencies."""

    # Function and class operations
    def reorder_function(
        self,
        file_path: Union[str, Path],
        function_name: str,
        target_position: str = "top",
        above_function: Optional[str] = None,
    ) -> str:
        """Reorder a function within a file."""
        raise NotImplementedError(f"Function reordering not implemented for {self.language_name}")

    def move_function(
        self, source_file: Union[str, Path], target_file: Union[str, Path], function_name: str
    ) -> str:
        """Move a function between files."""
        raise NotImplementedError(f"Function movement not implemented for {self.language_name}")

    def move_class(
        self, source_file: Union[str, Path], target_file: Union[str, Path], class_name: str
    ) -> str:
        """Move a class between files."""
        raise NotImplementedError(f"Class movement not implemented for {self.language_name}")

    def extract_method(
        self, file_path: Union[str, Path], start_line: int, end_line: int, method_name: str
    ) -> str:
        """Extract a method from existing code."""
        raise NotImplementedError(f"Method extraction not implemented for {self.language_name}")

    def inline_method(self, file_path: Union[str, Path], method_name: str) -> str:
        """Inline a method into its call sites."""
        raise NotImplementedError(f"Method inlining not implemented for {self.language_name}")

    def detect_dead_code(self, file_path: Union[str, Path]) -> str:
        """Detect dead (unused) code in a file."""
        raise NotImplementedError(f"Dead code detection not implemented for {self.language_name}")

    def remove_dead_code(self, file_path: Union[str, Path], confirm: bool = False) -> str:
        """Remove dead (unused) code from a file."""
        raise NotImplementedError(f"Dead code removal not implemented for {self.language_name}")

    def find_code_pattern(
        self, file_path: Union[str, Path], pattern: str, pattern_type: str = "regex"
    ) -> str:
        """Find code patterns in a file."""
        raise NotImplementedError(f"Pattern finding not implemented for {self.language_name}")

    def apply_code_pattern(
        self,
        file_path: Union[str, Path],
        find_pattern: str,
        replace_pattern: str,
        pattern_type: str = "regex",
        max_replacements: int = -1,
    ) -> str:
        """Apply code pattern transformations."""
        raise NotImplementedError(f"Pattern application not implemented for {self.language_name}")

    def validate_refactoring_operation(
        self, file_path: Union[str, Path], operation: RefactoringOperation, **kwargs
    ) -> Dict[str, Any]:
        """Validate that a refactoring operation is safe to perform."""
        return {
            "is_valid": True,
            "warnings": [],
            "errors": [],
            "suggestions": [],
        }

    # Import and module operations
    def organize_imports(self, file_path: Union[str, Path]) -> str:
        """Organize and sort imports."""
        raise NotImplementedError(f"Import organization not implemented for {self.language_name}")

    def add_import(
        self, file_path: Union[str, Path], module: str, symbols: Optional[List[str]] = None
    ) -> str:
        """Add an import statement."""
        raise NotImplementedError(f"Import addition not implemented for {self.language_name}")

    def remove_unused_imports(self, file_path: Union[str, Path]) -> str:
        """Remove unused import statements."""
        raise NotImplementedError(f"Unused import removal not implemented for {self.language_name}")

    # Symbol operations
    def rename_symbol(
        self, file_path: Union[str, Path], old_name: str, new_name: str, scope: str = "file"
    ) -> str:
        """Rename a symbol (variable, function, class)."""
        raise NotImplementedError(f"Symbol renaming not implemented for {self.language_name}")

    # Utility methods
    def backup_file(self, file_path: Union[str, Path]) -> str:
        """Create a backup of the file before modification."""
        file_path = Path(file_path)
        backup_path = file_path.with_suffix(f"{file_path.suffix}.backup")

        with open(file_path, "r", encoding="utf-8") as src:
            with open(backup_path, "w", encoding="utf-8") as dst:
                dst.write(src.read())

        return str(backup_path)

    def read_file_content(self, file_path: Union[str, Path]) -> str:
        """Read file content safely."""
        file_path = Path(file_path)

        if not file_path.exists():
            raise RefactoringError(f"File not found: {file_path}")

        try:
            with open(file_path, "r", encoding="utf-8") as f:
                return f.read()
        except Exception as e:
            raise RefactoringError(f"Error reading file {file_path}: {e}")

    def write_file_content(self, file_path: Union[str, Path], content: str) -> None:
        """Write file content safely."""
        file_path = Path(file_path)

        try:
            # Create parent directories if they don't exist
            file_path.parent.mkdir(parents=True, exist_ok=True)

            with open(file_path, "w", encoding="utf-8") as f:
                f.write(content)
        except Exception as e:
            raise RefactoringError(f"Error writing file {file_path}: {e}")

    def get_language_specific_config(self) -> Dict[str, Any]:
        """Get language-specific configuration options."""
        return {
            "preserve_formatting": True,
            "auto_semicolons": False,
            "indent_size": 2,
            "quote_style": "double",
        }


class LanguageSpecificError(RefactoringError):
    """Exception for language-specific errors."""

    def __init__(
        self, message: str, language: str, operation: Optional[RefactoringOperation] = None
    ):
        super().__init__(message, operation)
        self.language = language

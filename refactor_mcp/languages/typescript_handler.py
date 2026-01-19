"""TypeScript language handler implementation."""

import re
from pathlib import Path
from typing import Any, Dict, List, Optional, Union

try:
    import tree_sitter_typescript as tsts
    from tree_sitter import Language, Parser

    TREE_SITTER_AVAILABLE = True
except ImportError:
    TREE_SITTER_AVAILABLE = False

from .base_handler import (
    ClassInfo,
    CodeStructure,
    FunctionInfo,
    ImportInfo,
    RefactoringError,
    RefactoringOperation,
)
from .javascript_handler import JavaScriptHandler


class TypeScriptHandler(JavaScriptHandler):
    """Handler for TypeScript language refactoring operations."""

    def __init__(self):
        super().__init__()
        self._ts_parser = None
        self._init_ts_parser()

    def _init_ts_parser(self):
        """Initialize Tree-sitter parser for TypeScript."""
        if not TREE_SITTER_AVAILABLE:
            return

        try:
            # Use the official tree-sitter-typescript package
            # TypeScript has both typescript and tsx languages
            TS_LANGUAGE = Language(tsts.language_typescript())
            self._ts_parser = Parser(TS_LANGUAGE)
        except Exception:
            # Fallback to regex parsing if tree-sitter initialization fails
            self._ts_parser = None

    @property
    def language_name(self) -> str:
        return "TypeScript"

    @property
    def file_extensions(self) -> List[str]:
        return [".ts", ".tsx", ".d.ts", ".cts", ".mts"]

    @property
    def supported_operations(self) -> List[RefactoringOperation]:
        return [
            RefactoringOperation.REORDER_FUNCTION,
            RefactoringOperation.ORGANIZE_IMPORTS,
            RefactoringOperation.ADD_IMPORT,
            RefactoringOperation.MOVE_FUNCTION,
            RefactoringOperation.MOVE_CLASS,
            RefactoringOperation.GET_CODE_STRUCTURE,
            RefactoringOperation.ANALYZE_DEPENDENCIES,
            RefactoringOperation.RENAME_SYMBOL,  # TypeScript has better symbol analysis
            RefactoringOperation.DETECT_DEAD_CODE,
            RefactoringOperation.REMOVE_DEAD_CODE,
        ]

    def can_handle_file(self, file_path: Union[str, Path]) -> bool:
        """Check if this handler can process the given file."""
        file_path = Path(file_path)

        # Check extension first
        if file_path.suffix.lower() in self.file_extensions:
            return True

        # Check for TypeScript patterns in content
        try:
            content = self.read_file_content(file_path)[:1000]  # First 1KB
            ts_patterns = [
                r"\binterface\s+\w+",
                r"\btype\s+\w+\s*=",
                r"\benum\s+\w+",
                r"\bnamespace\s+\w+",
                r":\s*\w+\s*[=;,\)]",  # Type annotations
                r"\bpublic\s+",
                r"\bprivate\s+",
                r"\bprotected\s+",
                r"\breadonly\s+",
                r"\babstract\s+",
                r"<\w+>",  # Generic syntax
                r"\bas\s+\w+",  # Type assertions
            ]

            for pattern in ts_patterns:
                if re.search(pattern, content):
                    return True

        except Exception:
            pass

        # Fallback to JavaScript detection
        return super().can_handle_file(file_path)

    def parse_file(self, file_path: Union[str, Path]) -> Any:
        """Parse TypeScript file into Tree-sitter AST."""
        if not self._ts_parser:
            # Fallback to JavaScript parser
            return super().parse_file(file_path)

        content = self.read_file_content(file_path)

        try:
            tree = self._ts_parser.parse(bytes(content, "utf8"))
            if tree.root_node.has_error:
                raise RefactoringError(f"Syntax error in TypeScript file: {file_path}")
            return tree
        except Exception as e:
            raise RefactoringError(f"Error parsing TypeScript file {file_path}: {e}")

    def get_code_structure(self, file_path: Union[str, Path]) -> CodeStructure:
        """Get structured information about the TypeScript file."""
        if not self._ts_parser:
            return self._get_ts_structure_fallback(file_path)

        try:
            tree = self.parse_file(file_path)
            structure = CodeStructure(file_path=str(file_path), language=self.language_name)

            self._extract_ts_structure_from_tree(tree.root_node, structure)
            return structure

        except Exception:
            return self._get_ts_structure_fallback(file_path)

    def _get_ts_structure_fallback(self, file_path: Union[str, Path]) -> CodeStructure:
        """Fallback structure extraction for TypeScript using regex patterns."""
        content = self.read_file_content(file_path)
        structure = CodeStructure(file_path=str(file_path), language=self.language_name)

        # Extract TypeScript-specific constructs
        self._extract_interfaces(content, structure)
        self._extract_types(content, structure)
        self._extract_enums(content, structure)
        self._extract_classes_and_functions(content, structure)
        self._extract_imports(content, structure)

        return structure

    def _extract_interfaces(self, content: str, structure: CodeStructure):
        """Extract interface definitions from TypeScript code."""
        interface_pattern = r"interface\s+(\w+)(?:\s*<[^>]*>)?\s*\{"

        line_num = 1
        for line in content.split("\n"):
            match = re.search(interface_pattern, line)
            if match:
                interface_info = ClassInfo(  # Interfaces are similar to classes
                    name=match.group(1),
                    line_start=line_num,
                    line_end=line_num,  # Approximation
                )
                # Mark as interface in a custom way
                interface_info.base_classes = ["interface"]
                structure.classes.append(interface_info)
            line_num += 1

    def _extract_types(self, content: str, structure: CodeStructure):
        """Extract type alias definitions from TypeScript code."""
        type_pattern = r"type\s+(\w+)(?:\s*<[^>]*>)?\s*="

        # Store type aliases as a special kind of function info for now
        line_num = 1
        for line in content.split("\n"):
            match = re.search(type_pattern, line)
            if match:
                type_info = FunctionInfo(
                    name=match.group(1),
                    line_start=line_num,
                    line_end=line_num,
                    return_type="type_alias",  # Mark as type alias
                )
                structure.functions.append(type_info)
            line_num += 1

    def _extract_enums(self, content: str, structure: CodeStructure):
        """Extract enum definitions from TypeScript code."""
        enum_pattern = r"enum\s+(\w+)\s*\{"

        line_num = 1
        for line in content.split("\n"):
            match = re.search(enum_pattern, line)
            if match:
                enum_info = ClassInfo(
                    name=match.group(1),
                    line_start=line_num,
                    line_end=line_num,
                )
                # Mark as enum
                enum_info.base_classes = ["enum"]
                structure.classes.append(enum_info)
            line_num += 1

    def _extract_classes_and_functions(self, content: str, structure: CodeStructure):
        """Extract class and function definitions with TypeScript features."""
        # Enhanced patterns for TypeScript
        function_patterns = [
            r"function\s+(\w+)(?:\s*<[^>]*>)?\s*\([^)]*\)(?:\s*:\s*\w+)?\s*\{",  # typed functions
            r"const\s+(\w+)\s*=\s*\([^)]*\)(?:\s*:\s*\w+)?\s*=>\s*\{",  # typed arrow functions
            r"(\w+)\s*\([^)]*\)(?:\s*:\s*\w+)?\s*\{",  # method definitions
            r"(public|private|protected)\s+(\w+)\s*\([^)]*\)(?:\s*:\s*\w+)?\s*\{",  # access modifiers
        ]

        class_pattern = r"(abstract\s+)?class\s+(\w+)(?:\s*<[^>]*>)?(?:\s+extends\s+\w+)?(?:\s+implements\s+[\w,\s]+)?\s*\{"

        line_num = 1
        for line in content.split("\n"):
            # Extract functions
            for pattern in function_patterns:
                match = re.search(pattern, line)
                if match:
                    # Handle access modifier pattern differently
                    if len(match.groups()) > 1 and match.group(1) in [
                        "public",
                        "private",
                        "protected",
                    ]:
                        func_name = match.group(2)
                        decorators = [match.group(1)]
                    else:
                        func_name = match.group(1)
                        decorators = []

                    func_info = FunctionInfo(
                        name=func_name,
                        line_start=line_num,
                        line_end=line_num,
                        decorators=decorators,
                    )
                    structure.functions.append(func_info)
                    break

            # Extract classes
            match = re.search(class_pattern, line)
            if match:
                is_abstract = match.group(1) is not None
                class_name = match.group(2)

                class_info = ClassInfo(
                    name=class_name,
                    line_start=line_num,
                    line_end=line_num,
                    decorators=["abstract"] if is_abstract else [],
                )
                structure.classes.append(class_info)

            line_num += 1

    def _extract_imports(self, content: str, structure: CodeStructure):
        """Extract import statements with TypeScript type imports."""
        import_patterns = [
            r'import\s+(?:type\s+)?\{([^}]+)\}\s+from\s+["\']([^"\']+)["\']',  # named imports
            r'import\s+(?:type\s+)?(\w+)\s+from\s+["\']([^"\']+)["\']',  # default imports
            r'import\s+\*\s+as\s+(\w+)\s+from\s+["\']([^"\']+)["\']',  # namespace imports
            r'import\s+["\']([^"\']+)["\']',  # side-effect imports
        ]

        line_num = 1
        for line in content.split("\n"):
            for pattern in import_patterns:
                match = re.search(pattern, line)
                if match:
                    if len(match.groups()) == 2:
                        symbols = [s.strip() for s in match.group(1).split(",")]
                        module = match.group(2)
                    elif len(match.groups()) == 1 and "from" in pattern:
                        symbols = [match.group(1)]
                        module = match.group(2)
                    else:
                        symbols = []
                        module = match.group(1)

                    import_type = "type_import" if "type" in line else "es6_import"

                    import_info = ImportInfo(
                        module=module, line=line_num, import_type=import_type, symbols=symbols
                    )
                    structure.imports.append(import_info)
                    break
            line_num += 1

    def _extract_ts_structure_from_tree(self, node, structure: CodeStructure):
        """Extract structure information from TypeScript Tree-sitter AST."""
        node_type = node.type

        if node_type == "function_declaration":
            name_node = node.child_by_field_name("name")
            if name_node:
                # Check for type parameters and return type
                return_type_node = node.child_by_field_name("return_type")

                func_info = FunctionInfo(
                    name=name_node.text.decode("utf8"),
                    line_start=node.start_point[0] + 1,
                    line_end=node.end_point[0] + 1,
                    return_type=return_type_node.text.decode("utf8") if return_type_node else None,
                )
                structure.functions.append(func_info)

        elif node_type == "class_declaration":
            name_node = node.child_by_field_name("name")
            if name_node:
                class_info = ClassInfo(
                    name=name_node.text.decode("utf8"),
                    line_start=node.start_point[0] + 1,
                    line_end=node.end_point[0] + 1,
                )
                structure.classes.append(class_info)

        elif node_type == "interface_declaration":
            name_node = node.child_by_field_name("name")
            if name_node:
                interface_info = ClassInfo(
                    name=name_node.text.decode("utf8"),
                    line_start=node.start_point[0] + 1,
                    line_end=node.end_point[0] + 1,
                    base_classes=["interface"],
                )
                structure.classes.append(interface_info)

        elif node_type == "type_alias_declaration":
            name_node = node.child_by_field_name("name")
            if name_node:
                type_info = FunctionInfo(
                    name=name_node.text.decode("utf8"),
                    line_start=node.start_point[0] + 1,
                    line_end=node.end_point[0] + 1,
                    return_type="type_alias",
                )
                structure.functions.append(type_info)

        elif node_type == "enum_declaration":
            name_node = node.child_by_field_name("name")
            if name_node:
                enum_info = ClassInfo(
                    name=name_node.text.decode("utf8"),
                    line_start=node.start_point[0] + 1,
                    line_end=node.end_point[0] + 1,
                    base_classes=["enum"],
                )
                structure.classes.append(enum_info)

        elif node_type in ["import_statement", "import_declaration"]:
            source_node = node.child_by_field_name("source")
            if source_node:
                module_name = source_node.text.decode("utf8").strip("\"'")

                # Check if it's a type import
                import_clause = node.child_by_field_name("import_clause")
                is_type_import = False
                if import_clause:
                    import_text = import_clause.text.decode("utf8")
                    is_type_import = "type" in import_text

                import_info = ImportInfo(
                    module=module_name,
                    line=node.start_point[0] + 1,
                    import_type="type_import" if is_type_import else "es6_import",
                )
                structure.imports.append(import_info)

        # Recursively process children
        for child in node.children:
            self._extract_ts_structure_from_tree(child, structure)

    def organize_imports(self, file_path: Union[str, Path]) -> str:
        """Organize imports in a TypeScript file with type import handling."""
        content = self.read_file_content(file_path)

        # Extract import statements with type awareness
        import_lines = []
        other_lines = []

        for line_num, line in enumerate(content.split("\n"), 1):
            if self._is_ts_import_line(line):
                import_lines.append((line_num, line))
            else:
                other_lines.append((line_num, line))

        if not import_lines:
            return f"No imports found in {file_path}"

        # Organize imports by type
        organized_imports = self._organize_ts_imports([line for _, line in import_lines])

        # Rebuild content (similar to JavaScript handler but with type awareness)
        new_content_lines = []

        first_import_line = min(line_num for line_num, _ in import_lines)
        for line_num, line in other_lines:
            if line_num < first_import_line:
                new_content_lines.append(line)

        new_content_lines.extend(organized_imports.split("\n"))

        last_import_line = max(line_num for line_num, _ in import_lines)
        for line_num, line in other_lines:
            if line_num > last_import_line:
                new_content_lines.append(line)

        new_content = "\n".join(new_content_lines)
        self.write_file_content(file_path, new_content)

        return f"Successfully organized TypeScript imports in {file_path}"

    def _is_ts_import_line(self, line: str) -> bool:
        """Check if a line contains a TypeScript import statement."""
        stripped = line.strip()
        return (
            stripped.startswith("import ") or stripped.startswith("export ") and "from" in stripped
        )

    def _organize_ts_imports(self, import_lines: List[str]) -> str:
        """Organize TypeScript imports into groups."""
        type_imports = []
        builtin_imports = []
        npm_imports = []
        relative_imports = []

        builtin_modules = {
            "fs",
            "path",
            "http",
            "https",
            "url",
            "querystring",
            "crypto",
            "os",
            "util",
            "events",
            "stream",
            "buffer",
            "child_process",
        }

        for line in import_lines:
            module_name = self._extract_module_name_from_import(line)
            if not module_name:
                continue

            if "import type" in line or "type" in line:
                type_imports.append(line)
            elif module_name.startswith("."):
                relative_imports.append(line)
            elif module_name in builtin_modules:
                builtin_imports.append(line)
            else:
                npm_imports.append(line)

        # Sort each group
        type_imports.sort()
        builtin_imports.sort()
        npm_imports.sort()
        relative_imports.sort()

        # Combine groups (type imports first in TypeScript)
        groups = []
        if type_imports:
            groups.append("\n".join(type_imports))
        if builtin_imports:
            groups.append("\n".join(builtin_imports))
        if npm_imports:
            groups.append("\n".join(npm_imports))
        if relative_imports:
            groups.append("\n".join(relative_imports))

        return "\n\n".join(groups) + "\n\n"

    def add_import(
        self,
        file_path: Union[str, Path],
        module: str,
        symbols: Optional[List[str]] = None,
        is_type_import: bool = False,
    ) -> str:
        """Add an import statement to a TypeScript file."""
        content = self.read_file_content(file_path)

        # Create TypeScript import statement
        type_prefix = "type " if is_type_import else ""

        if symbols:
            import_stmt = f"import {type_prefix}{{ {', '.join(symbols)} }} from '{module}'"
        else:
            var_name = module.split("/")[-1]
            import_stmt = f"import {type_prefix}{var_name} from '{module}'"

        # Find insertion point
        lines = content.splitlines()
        insert_idx = self._find_ts_import_insertion_point(lines, is_type_import)

        lines.insert(insert_idx, import_stmt)
        new_content = "\n".join(lines) + "\n"

        self.write_file_content(file_path, new_content)

        return f"Successfully added TypeScript import '{import_stmt}' to {file_path}"

    def _find_ts_import_insertion_point(
        self, lines: List[str], is_type_import: bool = False
    ) -> int:
        """Find the best place to insert a new import in TypeScript."""
        # TypeScript convention: type imports first
        last_type_import_idx = -1
        last_regular_import_idx = -1

        for i, line in enumerate(lines):
            if self._is_ts_import_line(line):
                if "import type" in line or "type" in line:
                    last_type_import_idx = i
                else:
                    last_regular_import_idx = i

        if is_type_import and last_type_import_idx >= 0:
            return last_type_import_idx + 1
        elif not is_type_import and last_regular_import_idx >= 0:
            return last_regular_import_idx + 1
        elif last_type_import_idx >= 0 or last_regular_import_idx >= 0:
            return max(last_type_import_idx, last_regular_import_idx) + 1

        # If no imports found, insert after comments/directives at top
        return self._find_js_import_insertion_point(lines)

    def get_language_specific_config(self) -> Dict[str, Any]:
        """Get TypeScript-specific configuration."""
        config = super().get_language_specific_config()
        config.update(
            {
                "strict_types": True,
                "type_imports_first": True,
                "interface_naming": "PascalCase",
                "enum_naming": "PascalCase",
                "preserve_type_annotations": True,
            }
        )
        return config

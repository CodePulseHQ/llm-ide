"""Go language handler implementation."""

import re
from pathlib import Path
from typing import Any, Dict, List, Optional, Set, Union

try:
    import tree_sitter_go as tsgo
    from tree_sitter import Language, Parser

    TREE_SITTER_AVAILABLE = True
except ImportError:
    TREE_SITTER_AVAILABLE = False

from .base_handler import (
    BaseLanguageHandler,
    ClassInfo,
    CodeStructure,
    FunctionInfo,
    ImportInfo,
    RefactoringError,
    RefactoringOperation,
)


class GoHandler(BaseLanguageHandler):
    """Handler for Go language refactoring operations."""

    def __init__(self):
        self._parser = None
        self._init_parser()

    def _init_parser(self):
        """Initialize Tree-sitter parser for Go."""
        if not TREE_SITTER_AVAILABLE:
            return

        try:
            GO_LANGUAGE = Language(tsgo.language())
            self._parser = Parser(GO_LANGUAGE)
        except Exception as e:
            print(f"Warning: Could not initialize Go parser: {e}")
            self._parser = None

    @property
    def language_name(self) -> str:
        return "Go"

    @property
    def file_extensions(self) -> List[str]:
        return [".go"]

    @property
    def supported_operations(self) -> List[RefactoringOperation]:
        return [
            RefactoringOperation.REORDER_FUNCTION,
            RefactoringOperation.ORGANIZE_IMPORTS,
            RefactoringOperation.ADD_IMPORT,
            RefactoringOperation.REMOVE_UNUSED_IMPORTS,
            RefactoringOperation.MOVE_FUNCTION,
            RefactoringOperation.MOVE_CLASS,  # For structs
            RefactoringOperation.GET_CODE_STRUCTURE,
            RefactoringOperation.ANALYZE_DEPENDENCIES,
            RefactoringOperation.RENAME_SYMBOL,
            RefactoringOperation.EXTRACT_METHOD,
            RefactoringOperation.INLINE_METHOD,
            RefactoringOperation.DETECT_DEAD_CODE,
            RefactoringOperation.FIND_CODE_PATTERN,
        ]

    def can_handle_file(self, file_path: Union[str, Path]) -> bool:
        """Check if this handler can process the given file."""
        file_path = Path(file_path)

        # Check extension
        if file_path.suffix.lower() in self.file_extensions:
            return True

        # Check for Go patterns in content
        try:
            content = self.read_file_content(file_path)[:1000]  # First 1KB
            go_patterns = [
                r"^package\s+\w+",  # package declaration
                r"\bfunc\s+\w+\s*\(",  # function declaration
                r"\bfunc\s+\([^)]+\)\s+\w+\s*\(",  # method with receiver
                r"\btype\s+\w+\s+struct\s*\{",  # struct definition
                r"\btype\s+\w+\s+interface\s*\{",  # interface definition
                r"\bvar\s+\w+\s+\w+",  # variable declaration
                r"\bconst\s+\w+\s*=",  # constant declaration
                r'\bimport\s+["\']',  # import statement
                r"\bimport\s*\(",  # grouped imports
                r"\bgo\s+\w+\s*\(",  # goroutine call
                r"\bchan\s+\w+",  # channel type
            ]

            for pattern in go_patterns:
                if re.search(pattern, content, re.MULTILINE):
                    return True

        except Exception:
            pass

        # Check for go.mod in parent directories (Go module)
        current_dir = file_path.parent
        while current_dir != current_dir.parent:
            if (current_dir / "go.mod").exists():
                return True
            current_dir = current_dir.parent

        return False

    def validate_syntax(self, content: str) -> bool:
        """Validate Go syntax using Tree-sitter."""
        if not self._parser:
            # Fallback to basic pattern matching
            return self._basic_syntax_check(content)

        try:
            tree = self._parser.parse(bytes(content, "utf8"))
            return not tree.root_node.has_error
        except Exception:
            return False

    def _basic_syntax_check(self, content: str) -> bool:
        """Basic syntax validation without Tree-sitter."""
        # Check for required package declaration
        if not re.search(r"^package\s+\w+", content, re.MULTILINE):
            return False

        # Check for balanced braces
        open_braces = content.count("{")
        close_braces = content.count("}")

        # Allow some flexibility
        return abs(open_braces - close_braces) <= 1

    def parse_file(self, file_path: Union[str, Path]) -> Any:
        """Parse Go file into Tree-sitter AST."""
        if not self._parser:
            raise RefactoringError("Tree-sitter parser not available for Go")

        content = self.read_file_content(file_path)

        try:
            tree = self._parser.parse(bytes(content, "utf8"))
            if tree.root_node.has_error:
                raise RefactoringError(f"Syntax error in Go file: {file_path}")
            return tree
        except Exception as e:
            raise RefactoringError(f"Error parsing Go file {file_path}: {e}")

    def get_code_structure(self, file_path: Union[str, Path]) -> CodeStructure:
        """Get structured information about the Go file."""
        if not self._parser:
            return self._get_structure_fallback(file_path)

        try:
            tree = self.parse_file(file_path)
            structure = CodeStructure(file_path=str(file_path), language=self.language_name)

            self._extract_structure_from_tree(tree.root_node, structure)
            return structure

        except Exception:
            return self._get_structure_fallback(file_path)

    def _get_structure_fallback(self, file_path: Union[str, Path]) -> CodeStructure:
        """Fallback structure extraction using regex patterns."""
        content = self.read_file_content(file_path)
        structure = CodeStructure(file_path=str(file_path), language=self.language_name)

        # Extract package information
        package_match = re.search(r"^package\s+(\w+)", content, re.MULTILINE)
        if package_match:
            # Store package info in exports
            structure.exports.append(f"package:{package_match.group(1)}")

        # Extract functions and methods using regex
        line_num = 1
        for line in content.split("\n"):
            # Check for regular functions
            regular_func_match = re.search(r"func\s+(\w+)\s*\([^)]*\)", line)
            if regular_func_match and not re.search(r"func\s+\([^)]+\)", line):
                func_info = FunctionInfo(
                    name=regular_func_match.group(1),
                    line_start=line_num,
                    line_end=line_num,  # Approximation
                )
                structure.functions.append(func_info)

            # Check for methods (functions with receivers)
            method_match = re.search(r"func\s+\(([^)]+)\)\s+(\w+)\s*\([^)]*\)", line)
            if method_match:
                receiver = method_match.group(1).strip()
                method_name = method_match.group(2)

                # Extract receiver type
                receiver_type = receiver.split()[-1] if " " in receiver else receiver
                receiver_type = receiver_type.lstrip("*")  # Remove pointer indicator

                func_info = FunctionInfo(
                    name=method_name,
                    line_start=line_num,
                    line_end=line_num,
                    is_method=True,
                    class_name=receiver_type,
                    parameters=[receiver],
                )
                structure.functions.append(func_info)

            # Check for struct definitions
            struct_match = re.search(r"type\s+(\w+)\s+struct\s*\{", line)
            if struct_match:
                struct_info = ClassInfo(
                    name=struct_match.group(1),
                    line_start=line_num,
                    line_end=line_num,
                    base_classes=["struct"],
                )
                structure.classes.append(struct_info)

            # Check for interface definitions
            interface_match = re.search(r"type\s+(\w+)\s+interface\s*\{", line)
            if interface_match:
                interface_info = ClassInfo(
                    name=interface_match.group(1),
                    line_start=line_num,
                    line_end=line_num,
                    base_classes=["interface"],
                )
                structure.classes.append(interface_info)

            # Check for type aliases
            type_match = re.search(r"type\s+(\w+)\s+(\w+)", line)
            if type_match and not re.search(r"struct|interface", line):
                type_info = ClassInfo(
                    name=type_match.group(1),
                    line_start=line_num,
                    line_end=line_num,
                    base_classes=[f"alias:{type_match.group(2)}"],
                )
                structure.classes.append(type_info)

            line_num += 1

        # Extract imports
        self._extract_imports_fallback(content, structure)

        return structure

    def _extract_imports_fallback(self, content: str, structure: CodeStructure):
        """Extract import statements using regex."""
        # Single line imports
        single_imports = re.findall(r'import\s+"([^"]+)"', content)
        for imp in single_imports:
            import_info = ImportInfo(
                module=imp,
                line=0,  # Line number not easily available in regex
                import_type="go_import",
            )
            structure.imports.append(import_info)

        # Grouped imports
        import_blocks = re.findall(r"import\s*\(\s*((?:[^)]*\n?)*)\s*\)", content, re.MULTILINE)
        for block in import_blocks:
            imports = re.findall(r'"([^"]+)"', block)
            for imp in imports:
                import_info = ImportInfo(module=imp, line=0, import_type="go_import")
                structure.imports.append(import_info)

        # Named imports (alias imports)
        named_imports = re.findall(r'import\s+(\w+)\s+"([^"]+)"', content)
        for alias, module in named_imports:
            import_info = ImportInfo(module=module, line=0, import_type="go_import", alias=alias)
            structure.imports.append(import_info)

    def _extract_structure_from_tree(self, node, structure: CodeStructure):
        """Extract structure information from Tree-sitter AST."""
        node_type = node.type

        if node_type == "package_clause":
            # Extract package name
            for child in node.children:
                if child.type == "package_identifier":
                    package_name = child.text.decode("utf8")
                    structure.exports.append(f"package:{package_name}")

        elif node_type == "function_declaration":
            name_node = node.child_by_field_name("name")
            if name_node:
                func_info = FunctionInfo(
                    name=name_node.text.decode("utf8"),
                    line_start=node.start_point[0] + 1,
                    line_end=node.end_point[0] + 1,
                )
                structure.functions.append(func_info)

        elif node_type == "method_declaration":
            name_node = node.child_by_field_name("name")
            receiver_node = node.child_by_field_name("receiver")

            if name_node:
                # Extract receiver type
                receiver_type = "unknown"
                if receiver_node:
                    # Find the type in the receiver
                    for child in receiver_node.children:
                        if child.type in ["type_identifier", "pointer_type"]:
                            receiver_type = child.text.decode("utf8").lstrip("*")
                            break

                func_info = FunctionInfo(
                    name=name_node.text.decode("utf8"),
                    line_start=node.start_point[0] + 1,
                    line_end=node.end_point[0] + 1,
                    is_method=True,
                    class_name=receiver_type,
                )
                structure.functions.append(func_info)

        elif node_type == "type_declaration":
            # Handle struct, interface, and type alias declarations
            for child in node.children:
                if child.type == "type_spec":
                    self._extract_type_spec(child, structure)

        elif node_type in ["import_declaration", "import_spec"]:
            # Handle import statements
            if node_type == "import_declaration":
                for child in node.children:
                    if child.type == "import_spec":
                        self._extract_import_spec(child, structure)
            else:
                self._extract_import_spec(node, structure)

        # Recursively process children
        for child in node.children:
            self._extract_structure_from_tree(child, structure)

    def _extract_type_spec(self, node, structure: CodeStructure):
        """Extract type specification (struct, interface, alias)."""
        name_node = node.child_by_field_name("name")
        type_node = node.child_by_field_name("type")

        if name_node and type_node:
            type_name = name_node.text.decode("utf8")

            if type_node.type == "struct_type":
                struct_info = ClassInfo(
                    name=type_name,
                    line_start=node.start_point[0] + 1,
                    line_end=node.end_point[0] + 1,
                    base_classes=["struct"],
                )
                structure.classes.append(struct_info)

            elif type_node.type == "interface_type":
                interface_info = ClassInfo(
                    name=type_name,
                    line_start=node.start_point[0] + 1,
                    line_end=node.end_point[0] + 1,
                    base_classes=["interface"],
                )
                structure.classes.append(interface_info)

            else:
                # Type alias
                alias_type = type_node.text.decode("utf8")
                alias_info = ClassInfo(
                    name=type_name,
                    line_start=node.start_point[0] + 1,
                    line_end=node.end_point[0] + 1,
                    base_classes=[f"alias:{alias_type}"],
                )
                structure.classes.append(alias_info)

    def _extract_import_spec(self, node, structure: CodeStructure):
        """Extract import specification."""
        path_node = node.child_by_field_name("path")
        name_node = node.child_by_field_name("name")

        if path_node:
            module_path = path_node.text.decode("utf8").strip('"')
            alias = None

            if name_node:
                alias = name_node.text.decode("utf8")

            import_info = ImportInfo(
                module=module_path,
                line=node.start_point[0] + 1,
                import_type="go_import",
                alias=alias,
            )
            structure.imports.append(import_info)

    def analyze_dependencies(self, file_path: Union[str, Path]) -> Dict[str, Any]:
        """Analyze dependencies in Go file."""
        structure = self.get_code_structure(file_path)

        # Categorize Go imports
        stdlib_imports = []
        external_imports = []
        local_imports = []

        # Go standard library packages (common ones)
        stdlib_packages = {
            "fmt",
            "os",
            "io",
            "strings",
            "strconv",
            "time",
            "json",
            "http",
            "net",
            "path",
            "filepath",
            "bytes",
            "errors",
            "log",
            "math",
            "rand",
            "sort",
            "sync",
            "context",
            "crypto",
            "encoding",
            "flag",
            "regexp",
            "runtime",
            "testing",
            "unsafe",
            "reflect",
            "bufio",
            "archive",
            "compress",
            "container",
            "database",
            "debug",
            "go",
            "hash",
            "html",
            "image",
            "index",
            "mime",
            "net",
            "plugin",
            "text",
            "unicode",
        }

        for imp in structure.imports:
            module_parts = imp.module.split("/")
            first_part = module_parts[0]

            if first_part in stdlib_packages or "." not in first_part:
                # Standard library or builtin
                stdlib_imports.append(imp.__dict__)
            elif imp.module.startswith("./") or imp.module.startswith("../"):
                # Local relative import
                local_imports.append(imp.__dict__)
            else:
                # External package (has domain or known external pattern)
                external_imports.append(imp.__dict__)

        # Extract package name
        package_name = "main"  # default
        for export in structure.exports:
            if export.startswith("package:"):
                package_name = export.split(":", 1)[1]
                break

        return {
            "file": str(file_path),
            "language": self.language_name,
            "package": package_name,
            "total_imports": len(structure.imports),
            "stdlib_imports": stdlib_imports,
            "external_imports": external_imports,
            "local_imports": local_imports,
            "functions": len([f for f in structure.functions if not f.is_method]),
            "methods": len([f for f in structure.functions if f.is_method]),
            "structs": len([c for c in structure.classes if "struct" in c.base_classes]),
            "interfaces": len([c for c in structure.classes if "interface" in c.base_classes]),
            "type_aliases": len(
                [c for c in structure.classes if any("alias:" in b for b in c.base_classes)]
            ),
        }

    def organize_imports(self, file_path: Union[str, Path]) -> str:
        """Organize imports in a Go file."""
        content = self.read_file_content(file_path)

        # Extract import statements and categorize them
        imports = self._extract_all_imports(content)

        if not imports:
            return f"No imports found in {file_path}"

        # Organize imports by category (Go convention)
        organized = self._organize_go_imports(imports)

        # Replace imports in content
        new_content = self._replace_go_imports(content, organized)

        self.write_file_content(file_path, new_content)

        return f"Successfully organized imports in {file_path}"

    def _extract_all_imports(self, content: str) -> List[Dict[str, Any]]:
        """Extract all import statements from Go code."""
        imports = []

        # Single line imports
        for match in re.finditer(r'import\s+(?:(\w+)\s+)?"([^"]+)"', content):
            alias, module = match.groups()
            imports.append(
                {
                    "module": module,
                    "alias": alias,
                    "line_start": content[: match.start()].count("\n") + 1,
                }
            )

        # Grouped imports
        for match in re.finditer(
            r"import\s*\(\s*((?:[^)]*\n?)*?)\s*\)", content, re.MULTILINE | re.DOTALL
        ):
            block = match.group(1)
            for imp_match in re.finditer(r'(?:(\w+)\s+)?"([^"]+)"', block):
                alias, module = imp_match.groups()
                imports.append(
                    {
                        "module": module,
                        "alias": alias,
                        "line_start": content[: match.start()].count("\n") + 1,
                    }
                )

        return imports

    def _organize_go_imports(self, imports: List[Dict[str, Any]]) -> str:
        """Organize Go imports according to Go conventions."""
        stdlib_imports = []
        external_imports = []
        local_imports = []

        # Go standard library packages
        stdlib_packages = {
            "fmt",
            "os",
            "io",
            "strings",
            "strconv",
            "time",
            "encoding/json",
            "net/http",
            "net",
            "path",
            "path/filepath",
            "bytes",
            "errors",
            "log",
            "math",
            "math/rand",
            "sort",
            "sync",
            "context",
            "crypto",
            "encoding",
            "flag",
            "regexp",
            "runtime",
            "testing",
            "unsafe",
            "reflect",
            "bufio",
            "archive",
            "compress",
            "container",
            "database",
            "debug",
            "go",
            "hash",
            "html",
            "image",
            "index",
            "mime",
            "plugin",
            "text",
            "unicode",
        }

        for imp in imports:
            module = imp["module"]
            alias = imp["alias"]

            # Format import line
            if alias:
                import_line = f'\t{alias} "{module}"'
            else:
                import_line = f'\t"{module}"'

            # Categorize import
            module_parts = module.split("/")
            first_part = module_parts[0]

            if first_part in stdlib_packages or (len(module_parts) == 1 and "." not in first_part):
                stdlib_imports.append(import_line)
            elif module.startswith("./") or module.startswith("../"):
                local_imports.append(import_line)
            else:
                external_imports.append(import_line)

        # Sort each category
        stdlib_imports.sort()
        external_imports.sort()
        local_imports.sort()

        # Combine with proper Go formatting
        groups = []
        if stdlib_imports:
            groups.append("\n".join(stdlib_imports))
        if external_imports:
            groups.append("\n".join(external_imports))
        if local_imports:
            groups.append("\n".join(local_imports))

        if len(groups) == 1:
            # Single group - use grouped format
            return f"import (\n{groups[0]}\n)"
        elif len(groups) > 1:
            # Multiple groups - separate with blank lines
            return f"import (\n{chr(10).join(groups)}\n)"
        else:
            return ""

    def _replace_go_imports(self, content: str, organized_imports: str) -> str:
        """Replace existing imports with organized imports."""
        # Remove all existing import statements
        # Single imports
        content = re.sub(r'import\s+(?:\w+\s+)?"[^"]+"\s*\n?', "", content)

        # Grouped imports
        content = re.sub(r"import\s*\([^)]*\)\s*\n?", "", content, flags=re.MULTILINE | re.DOTALL)

        # Find package declaration and insert organized imports after it
        package_match = re.search(r"^(package\s+\w+)\s*\n", content, re.MULTILINE)
        if package_match:
            insertion_point = package_match.end()

            # Insert organized imports
            new_content = (
                content[:insertion_point]
                + f"\n{organized_imports}\n\n"
                + content[insertion_point:].lstrip()
            )
            return new_content

        return content

    def add_import(
        self, file_path: Union[str, Path], module: str, symbols: Optional[List[str]] = None
    ) -> str:
        """Add an import statement to a Go file."""
        content = self.read_file_content(file_path)

        # Go doesn't use symbol-specific imports like Python
        # symbols parameter is ignored for Go
        import_stmt = f'import "{module}"'

        # Check if import already exists
        if re.search(rf'import\s+(?:\w+\s+)?"{re.escape(module)}"', content):
            return f"Import '{module}' already exists in {file_path}"

        # Find existing imports to determine insertion strategy
        existing_imports = self._extract_all_imports(content)

        if existing_imports:
            # Add to existing imports and reorganize
            return self.organize_imports(file_path)
        else:
            # No existing imports, add after package declaration
            package_match = re.search(r"^(package\s+\w+)\s*\n", content, re.MULTILINE)
            if package_match:
                insertion_point = package_match.end()
                new_content = (
                    content[:insertion_point]
                    + f"\n{import_stmt}\n\n"
                    + content[insertion_point:].lstrip()
                )

                self.write_file_content(file_path, new_content)
                return f"Successfully added import '{module}' to {file_path}"

        return f"Could not add import to {file_path} - no package declaration found"

    def extract_method(
        self, file_path: Union[str, Path], start_line: int, end_line: int, method_name: str
    ) -> str:
        """Extract a method from existing Go code."""
        content = self.read_file_content(file_path)
        lines = content.splitlines()

        # Validate line numbers
        if start_line < 1 or end_line > len(lines) or start_line > end_line:
            raise RefactoringError(
                f"Invalid line numbers for extraction: {start_line}-{end_line} "
                f"(file has {len(lines)} lines)"
            )

        # Extract the code block (convert to 0-based indexing)
        extracted_lines = lines[start_line - 1 : end_line]
        if not extracted_lines:
            raise RefactoringError("No code found in the specified range")

        # Analyze the extracted code
        extracted_code = "\n".join(extracted_lines)

        # Determine indentation level (Go uses tabs)
        base_indent = self._get_base_indentation_go(extracted_lines)

        # Find variables used and defined in the extracted code
        variables_info = self._analyze_variables_in_go_code(
            extracted_code, content, start_line, end_line
        )

        # Create the new function
        func_code = self._create_extracted_go_function(
            method_name, extracted_lines, variables_info, base_indent
        )

        # Find the appropriate place to insert the function
        insert_location = self._find_go_function_insertion_location(content, start_line)

        # Replace the extracted code with a function call
        func_call = self._create_go_function_call(method_name, variables_info, base_indent)

        # Build the new file content
        new_content = self._build_content_with_extracted_go_function(
            lines, start_line, end_line, func_code, func_call, insert_location
        )

        # Write the modified content
        self.write_file_content(file_path, new_content)

        return f"Successfully extracted function '{method_name}' from lines {start_line}-{end_line} in {file_path}"

    def _get_base_indentation_go(self, lines: List[str]) -> str:
        """Get the base indentation string for extracted Go lines."""
        for line in lines:
            if line.strip():
                # Return the leading whitespace
                return line[: len(line) - len(line.lstrip())]
        return ""

    def _analyze_variables_in_go_code(
        self, extracted_code: str, full_content: str, start_line: int, end_line: int
    ) -> Dict[str, Any]:
        """Analyze variables used and defined in extracted Go code."""
        # Simple regex-based analysis for Go variables
        # Find variable declarations (:= or var)
        defined_vars = set()
        used_vars = set()

        # Find short variable declarations (name :=)
        short_decls = re.findall(r"(\w+)\s*:=", extracted_code)
        defined_vars.update(short_decls)

        # Find var declarations
        var_decls = re.findall(r"var\s+(\w+)", extracted_code)
        defined_vars.update(var_decls)

        # Find all identifiers (potential variable usage)
        # This is simplified - a real parser would be more accurate
        identifiers = re.findall(r"\b([a-z_][a-zA-Z0-9_]*)\b", extracted_code)

        # Go keywords to exclude
        go_keywords = {
            "break",
            "case",
            "chan",
            "const",
            "continue",
            "default",
            "defer",
            "else",
            "fallthrough",
            "for",
            "func",
            "go",
            "goto",
            "if",
            "import",
            "interface",
            "map",
            "package",
            "range",
            "return",
            "select",
            "struct",
            "switch",
            "type",
            "var",
            "true",
            "false",
            "nil",
            "string",
            "int",
            "int8",
            "int16",
            "int32",
            "int64",
            "uint",
            "uint8",
            "uint16",
            "uint32",
            "uint64",
            "float32",
            "float64",
            "bool",
            "byte",
            "rune",
            "error",
            "len",
            "cap",
            "make",
            "new",
            "append",
            "copy",
            "delete",
            "complex",
            "real",
            "imag",
            "close",
            "panic",
            "recover",
            "print",
            "println",
        }

        for ident in identifiers:
            if ident not in go_keywords and ident not in defined_vars:
                used_vars.add(ident)

        # Find variables defined before the extracted code
        before_code = "\n".join(full_content.splitlines()[: start_line - 1])
        available_vars = set()

        short_decls_before = re.findall(r"(\w+)\s*:=", before_code)
        available_vars.update(short_decls_before)

        var_decls_before = re.findall(r"var\s+(\w+)", before_code)
        available_vars.update(var_decls_before)

        # Parameters are variables used but not defined and available before
        parameters = (used_vars - defined_vars) & available_vars

        # Return values are variables defined that might be used after
        after_code = "\n".join(full_content.splitlines()[end_line:])
        used_after = set(re.findall(r"\b([a-z_][a-zA-Z0-9_]*)\b", after_code))
        return_vars = defined_vars & used_after

        return {
            "parameters": sorted(parameters),
            "return_vars": sorted(return_vars),
            "used_vars": sorted(used_vars),
            "defined_vars": sorted(defined_vars),
        }

    def _create_extracted_go_function(
        self,
        func_name: str,
        extracted_lines: List[str],
        variables_info: Dict[str, Any],
        base_indent: str,
    ) -> str:
        """Create the extracted Go function code."""
        params = variables_info["parameters"]
        return_vars = variables_info["return_vars"]

        # Create parameter string with inferred types (default to interface{})
        param_parts = []
        for p in params:
            # Try to infer type from usage, default to interface{}
            param_parts.append(f"{p} interface{{}}")

        param_str = ", ".join(param_parts)

        # Create return type string
        if return_vars:
            if len(return_vars) == 1:
                return_type = " interface{}"
            else:
                return_type = " (" + ", ".join(["interface{}"] * len(return_vars)) + ")"
        else:
            return_type = ""

        # Build the function
        func_lines = [f"func {func_name}({param_str}){return_type} {{"]

        # Add body with proper indentation
        for line in extracted_lines:
            if line.strip():
                # Dedent to base level and add one tab
                dedented = line.lstrip()
                func_lines.append("\t" + dedented)
            else:
                func_lines.append("")

        # Add return statement if needed
        if return_vars:
            if len(return_vars) == 1:
                func_lines.append(f"\treturn {return_vars[0]}")
            else:
                func_lines.append(f"\treturn {', '.join(return_vars)}")

        func_lines.append("}")

        return "\n".join(func_lines)

    def _find_go_function_insertion_location(self, content: str, extraction_start: int) -> int:
        """Find where to insert the extracted function in Go code."""
        lines = content.splitlines()

        # Find the current function we're extracting from
        # Look backwards for func declaration
        for i in range(extraction_start - 2, -1, -1):
            line = lines[i].strip()
            if line.startswith("func ") and "{" in line:
                # Find the end of this function to insert after it
                brace_count = 0
                for j in range(i, len(lines)):
                    brace_count += lines[j].count("{") - lines[j].count("}")
                    if brace_count == 0:
                        return j + 1
                break

        # Default: insert before the extraction point
        return max(0, extraction_start - 1)

    def _create_go_function_call(
        self, func_name: str, variables_info: Dict[str, Any], base_indent: str
    ) -> str:
        """Create the function call to replace extracted code."""
        params = variables_info["parameters"]
        return_vars = variables_info["return_vars"]

        # Create the call
        call = f"{func_name}({', '.join(params)})"

        # Handle return values
        if return_vars:
            if len(return_vars) == 1:
                call_line = f"{return_vars[0]} := {call}"
            else:
                call_line = f"{', '.join(return_vars)} := {call}"
        else:
            call_line = call

        return base_indent + call_line

    def _build_content_with_extracted_go_function(
        self,
        lines: List[str],
        start_line: int,
        end_line: int,
        func_code: str,
        func_call: str,
        insert_location: int,
    ) -> str:
        """Build the final content with the extracted function."""
        # Remove extracted lines and replace with function call
        before_extraction = lines[: start_line - 1]
        after_extraction = lines[end_line:]

        # Insert function call
        modified_lines = before_extraction + [func_call] + after_extraction

        # Insert the new function
        func_lines = func_code.split("\n")

        # Adjust insert location if it's after the extraction point
        if insert_location >= start_line:
            insert_location = insert_location - (end_line - start_line) + 1

        # Insert function with spacing
        final_lines = (
            modified_lines[:insert_location]
            + [""]
            + func_lines
            + [""]
            + modified_lines[insert_location:]
        )

        return "\n".join(final_lines)

    def inline_method(self, file_path: Union[str, Path], method_name: str) -> str:
        """Inline a function at its call sites in Go code."""
        content = self.read_file_content(file_path)
        lines = content.splitlines()

        # Find the function to inline
        func_info = self._find_go_function(content, method_name)
        if not func_info:
            raise RefactoringError(f"Function '{method_name}' not found in {file_path}")

        # Extract function body
        func_body = self._extract_go_function_body(lines, func_info)

        # Find all call sites
        call_sites = self._find_go_call_sites(content, method_name)

        if not call_sites:
            return f"No call sites found for function '{method_name}' in {file_path}"

        # Replace each call site with inlined code (process in reverse order)
        call_sites.sort(key=lambda x: x["line"], reverse=True)

        for call_site in call_sites:
            lines = self._inline_go_call(lines, call_site, func_info, func_body)

        # Remove the original function
        new_lines = self._remove_go_function(lines, func_info)

        # Clean up and write
        new_content = self._clean_blank_lines("\n".join(new_lines))
        self.write_file_content(file_path, new_content)

        return f"Successfully inlined function '{method_name}' at {len(call_sites)} call sites in {file_path}"

    def _find_go_function(self, content: str, func_name: str) -> Optional[Dict[str, Any]]:
        """Find a function in Go code."""
        lines = content.splitlines()

        # Pattern for function declaration
        func_pattern = (
            rf"func\s+{re.escape(func_name)}\s*\(([^)]*)\)(?:\s*\(([^)]*)\)|\s*(\w+))?\s*\{{"
        )

        for i, line in enumerate(lines):
            match = re.search(func_pattern, line)
            if match:
                # Find the end of the function
                brace_count = line.count("{") - line.count("}")
                end_line = i

                for j in range(i + 1, len(lines)):
                    brace_count += lines[j].count("{") - lines[j].count("}")
                    if brace_count == 0:
                        end_line = j
                        break

                # Parse parameters
                params_str = match.group(1) or ""
                params = []
                if params_str.strip():
                    for param in params_str.split(","):
                        parts = param.strip().split()
                        if parts:
                            params.append(parts[0])

                return {
                    "name": func_name,
                    "start_line": i,
                    "end_line": end_line,
                    "parameters": params,
                    "params_str": params_str,
                }

        return None

    def _extract_go_function_body(self, lines: List[str], func_info: Dict[str, Any]) -> List[str]:
        """Extract the body of a Go function (excluding func declaration and closing brace)."""
        body_lines = []
        for i in range(func_info["start_line"] + 1, func_info["end_line"]):
            body_lines.append(lines[i])
        return body_lines

    def _find_go_call_sites(self, content: str, func_name: str) -> List[Dict[str, Any]]:
        """Find all call sites for a function in Go code."""
        call_sites = []
        lines = content.splitlines()

        # Pattern for function call
        call_pattern = rf"\b{re.escape(func_name)}\s*\(([^)]*)\)"

        for i, line in enumerate(lines):
            for match in re.finditer(call_pattern, line):
                # Skip the function declaration itself
                if not re.match(rf"^\s*func\s+{re.escape(func_name)}", line):
                    call_sites.append(
                        {
                            "line": i,
                            "col_start": match.start(),
                            "col_end": match.end(),
                            "args_str": match.group(1),
                            "full_match": match.group(0),
                        }
                    )

        return call_sites

    def _inline_go_call(
        self,
        lines: List[str],
        call_site: Dict[str, Any],
        func_info: Dict[str, Any],
        func_body: List[str],
    ) -> List[str]:
        """Inline a function call at a specific call site."""
        call_line_idx = call_site["line"]
        call_line = lines[call_line_idx]

        # Get indentation
        indent = call_line[: len(call_line) - len(call_line.lstrip())]

        # Parse arguments
        args = [a.strip() for a in call_site["args_str"].split(",") if a.strip()]

        # Create parameter substitution mapping
        param_map = {}
        for i, param in enumerate(func_info["parameters"]):
            if i < len(args):
                param_map[param] = args[i]

        # Check if this is an assignment
        assignment_match = re.match(r"^\s*(\w+(?:\s*,\s*\w+)*)\s*:?=\s*", call_line)
        assign_vars = None
        if assignment_match:
            assign_vars = [v.strip() for v in assignment_match.group(1).split(",")]

        # Create inlined code
        inlined_lines = []
        for body_line in func_body:
            if body_line.strip():
                inlined_line = body_line
                # Substitute parameters
                for param, arg in param_map.items():
                    inlined_line = re.sub(rf"\b{param}\b", arg, inlined_line)

                # Handle return statements
                return_match = re.match(r"^\s*return\s+(.+)$", inlined_line)
                if return_match and assign_vars:
                    return_expr = return_match.group(1)
                    if len(assign_vars) == 1:
                        inlined_line = f"{indent}{assign_vars[0]} := {return_expr}"
                    else:
                        inlined_line = f"{indent}{', '.join(assign_vars)} := {return_expr}"
                elif return_match and not assign_vars:
                    # Return without assignment - just use the expression
                    inlined_line = f"{indent}{return_match.group(1)}"
                else:
                    # Regular line - adjust indentation
                    body_indent = len(body_line) - len(body_line.lstrip())
                    inlined_line = indent + body_line[body_indent:]

                inlined_lines.append(inlined_line)
            else:
                inlined_lines.append("")

        # Filter out empty lines at start/end
        while inlined_lines and not inlined_lines[0].strip():
            inlined_lines.pop(0)
        while inlined_lines and not inlined_lines[-1].strip():
            inlined_lines.pop()

        # Replace the call line with inlined code
        lines[call_line_idx : call_line_idx + 1] = inlined_lines

        return lines

    def _remove_go_function(self, lines: List[str], func_info: Dict[str, Any]) -> List[str]:
        """Remove a function definition from Go code."""
        new_lines = lines[: func_info["start_line"]] + lines[func_info["end_line"] + 1 :]
        return new_lines

    def _clean_blank_lines(self, content: str) -> str:
        """Clean up excessive blank lines."""
        return re.sub(r"\n\s*\n\s*\n+", "\n\n", content)

    def remove_unused_imports(self, file_path: Union[str, Path]) -> str:
        """Remove unused import statements from a Go file."""
        content = self.read_file_content(file_path)

        # Find all imports
        imports = self._extract_all_imports(content)

        if not imports:
            return f"No imports found in {file_path}"

        # Find which imports are actually used
        used_imports = self._find_used_imports(content, imports)

        # Calculate removed imports
        removed_imports = [
            imp for imp in imports if imp["module"] not in [u["module"] for u in used_imports]
        ]

        if not removed_imports:
            return f"No unused imports found in {file_path}"

        # Rebuild content with only used imports
        new_content = self._rebuild_go_content_with_imports(content, used_imports)

        self.write_file_content(file_path, new_content)

        removed_names = [imp["module"].split("/")[-1] for imp in removed_imports]
        return f"Successfully removed {len(removed_imports)} unused imports from {file_path}: {', '.join(removed_names)}"

    def _find_used_imports(
        self, content: str, imports: List[Dict[str, Any]]
    ) -> List[Dict[str, Any]]:
        """Find which imports are actually used in the code."""
        # Remove import section and comments for usage analysis
        code_without_imports = re.sub(
            r"import\s+(?:\([^)]*\)|\"[^\"]+\"|\w+\s+\"[^\"]+\")",
            "",
            content,
            flags=re.MULTILINE | re.DOTALL,
        )
        code_without_comments = re.sub(r"//.*$", "", code_without_imports, flags=re.MULTILINE)
        code_without_comments = re.sub(r"/\*.*?\*/", "", code_without_comments, flags=re.DOTALL)

        used_imports = []
        for imp in imports:
            module = imp["module"]
            alias = imp.get("alias")

            # Determine the package name used in code
            if alias:
                pkg_name = alias
            else:
                # Use the last part of the import path
                pkg_name = module.split("/")[-1]

            # Check if package is used (package.Something pattern)
            # Also handle dot imports and blank imports
            if alias == ".":
                # Dot import - always consider used (hard to analyze)
                used_imports.append(imp)
            elif alias == "_":
                # Blank import - always consider used (for side effects)
                used_imports.append(imp)
            elif re.search(rf"\b{re.escape(pkg_name)}\s*\.", code_without_comments):
                used_imports.append(imp)

        return used_imports

    def _rebuild_go_content_with_imports(
        self, content: str, used_imports: List[Dict[str, Any]]
    ) -> str:
        """Rebuild Go content with only the used imports."""
        # Remove existing imports
        content_no_imports = re.sub(r'import\s+"[^"]+"\s*\n?', "", content)
        content_no_imports = re.sub(r'import\s+\w+\s+"[^"]+"\s*\n?', "", content_no_imports)
        content_no_imports = re.sub(
            r"import\s*\([^)]*\)\s*\n?", "", content_no_imports, flags=re.MULTILINE | re.DOTALL
        )

        # Find package line
        package_match = re.search(r"^(package\s+\w+)\s*\n", content_no_imports, re.MULTILINE)
        if not package_match:
            return content  # Can't find package, return original

        # Build new import block
        if used_imports:
            import_lines = []
            for imp in used_imports:
                if imp.get("alias"):
                    import_lines.append(f'\t{imp["alias"]} "{imp["module"]}"')
                else:
                    import_lines.append(f'\t"{imp["module"]}"')

            if len(import_lines) == 1:
                # Single import
                if used_imports[0].get("alias"):
                    import_block = (
                        f'import {used_imports[0]["alias"]} "{used_imports[0]["module"]}"\n'
                    )
                else:
                    import_block = f'import "{used_imports[0]["module"]}"\n'
            else:
                # Multiple imports
                import_block = "import (\n" + "\n".join(sorted(import_lines)) + "\n)\n"
        else:
            import_block = ""

        # Insert imports after package line
        insertion_point = package_match.end()
        new_content = (
            content_no_imports[:insertion_point]
            + "\n"
            + import_block
            + "\n"
            + content_no_imports[insertion_point:].lstrip()
        )

        return new_content

    def find_code_pattern(
        self, file_path: Union[str, Path], pattern: str, pattern_type: str = "regex"
    ) -> str:
        """Find code patterns in a Go file."""
        content = self.read_file_content(file_path)

        if pattern_type == "regex":
            matches = self._find_regex_pattern_go(content, pattern)
        elif pattern_type == "ast":
            matches = self._find_ast_pattern_go(content, pattern)
        else:
            raise RefactoringError(f"Unsupported pattern type: {pattern_type}")

        import json

        result = {
            "file_path": str(file_path),
            "pattern": pattern,
            "pattern_type": pattern_type,
            "matches": matches,
            "total_matches": len(matches),
        }

        return json.dumps(result, indent=2)

    def _find_regex_pattern_go(self, content: str, pattern: str) -> List[Dict[str, Any]]:
        """Find matches using regex pattern in Go code."""
        matches = []

        try:
            regex = re.compile(pattern, re.MULTILINE)
            lines = content.splitlines()

            for line_num, line in enumerate(lines, 1):
                for match in regex.finditer(line):
                    matches.append(
                        {
                            "line": line_num,
                            "column": match.start(),
                            "matched_text": match.group(),
                            "context": line.strip(),
                            "groups": list(match.groups()) if match.groups() else [],
                        }
                    )

        except re.error as e:
            raise RefactoringError(f"Invalid regex pattern: {e}")

        return matches

    def _find_ast_pattern_go(self, content: str, pattern: str) -> List[Dict[str, Any]]:
        """Find matches using AST-based patterns in Go code."""
        matches = []

        if pattern == "function_definitions":
            matches = self._find_go_functions_ast(content)
        elif pattern == "function_calls":
            matches = self._find_go_function_calls(content)
        elif pattern == "type_definitions":
            matches = self._find_go_types(content)
        elif pattern == "import_statements":
            matches = self._find_go_imports_ast(content)
        elif pattern == "struct_definitions":
            matches = self._find_go_structs(content)
        elif pattern == "interface_definitions":
            matches = self._find_go_interfaces(content)
        else:
            raise RefactoringError(f"Unsupported AST pattern: {pattern}")

        return matches

    def _find_go_functions_ast(self, content: str) -> List[Dict[str, Any]]:
        """Find all function definitions in Go code."""
        matches = []
        lines = content.splitlines()

        # Regular functions
        func_pattern = r"func\s+(\w+)\s*\(([^)]*)\)"
        # Methods with receiver
        method_pattern = r"func\s+\(([^)]+)\)\s+(\w+)\s*\(([^)]*)\)"

        for line_num, line in enumerate(lines, 1):
            # Check for methods first (more specific)
            method_match = re.search(method_pattern, line)
            if method_match:
                matches.append(
                    {
                        "line": line_num,
                        "type": "method",
                        "receiver": method_match.group(1).strip(),
                        "name": method_match.group(2),
                        "parameters": method_match.group(3).strip(),
                    }
                )
                continue

            # Check for regular functions
            func_match = re.search(func_pattern, line)
            if func_match and not re.match(r"\s*//", line):
                matches.append(
                    {
                        "line": line_num,
                        "type": "function",
                        "name": func_match.group(1),
                        "parameters": func_match.group(2).strip(),
                    }
                )

        return matches

    def _find_go_function_calls(self, content: str) -> List[Dict[str, Any]]:
        """Find all function calls in Go code."""
        matches = []
        lines = content.splitlines()

        # Pattern for function calls (identifier followed by parentheses)
        call_pattern = r"\b(\w+)\s*\(([^)]*)\)"

        for line_num, line in enumerate(lines, 1):
            # Skip function/method declarations
            if re.match(r"^\s*func\s+", line):
                continue

            for match in re.finditer(call_pattern, line):
                func_name = match.group(1)
                # Skip keywords
                if func_name not in {"if", "for", "switch", "select", "func", "type"}:
                    matches.append(
                        {
                            "line": line_num,
                            "type": "function_call",
                            "name": func_name,
                            "arguments": match.group(2).strip(),
                        }
                    )

        return matches

    def _find_go_types(self, content: str) -> List[Dict[str, Any]]:
        """Find all type definitions in Go code."""
        matches = []
        lines = content.splitlines()

        type_pattern = r"type\s+(\w+)\s+(\w+|struct|interface)"

        for line_num, line in enumerate(lines, 1):
            type_match = re.search(type_pattern, line)
            if type_match:
                matches.append(
                    {
                        "line": line_num,
                        "type": "type_definition",
                        "name": type_match.group(1),
                        "kind": type_match.group(2),
                    }
                )

        return matches

    def _find_go_imports_ast(self, content: str) -> List[Dict[str, Any]]:
        """Find all import statements in Go code."""
        matches = []
        imports = self._extract_all_imports(content)

        for imp in imports:
            matches.append(
                {
                    "line": imp.get("line_start", 0),
                    "type": "import",
                    "module": imp["module"],
                    "alias": imp.get("alias"),
                }
            )

        return matches

    def _find_go_structs(self, content: str) -> List[Dict[str, Any]]:
        """Find all struct definitions in Go code."""
        matches = []
        lines = content.splitlines()

        for line_num, line in enumerate(lines, 1):
            struct_match = re.search(r"type\s+(\w+)\s+struct", line)
            if struct_match:
                matches.append(
                    {
                        "line": line_num,
                        "type": "struct",
                        "name": struct_match.group(1),
                    }
                )

        return matches

    def _find_go_interfaces(self, content: str) -> List[Dict[str, Any]]:
        """Find all interface definitions in Go code."""
        matches = []
        lines = content.splitlines()

        for line_num, line in enumerate(lines, 1):
            interface_match = re.search(r"type\s+(\w+)\s+interface", line)
            if interface_match:
                matches.append(
                    {
                        "line": line_num,
                        "type": "interface",
                        "name": interface_match.group(1),
                    }
                )

        return matches

    def detect_dead_code(self, file_path: Union[str, Path]) -> str:
        """Detect dead (unused) code in a Go file."""
        content = self.read_file_content(file_path)

        dead_code_info = self._analyze_go_dead_code(content)

        if not any(dead_code_info.values()):
            return f"No dead code detected in {file_path}"

        import json

        report = {
            "file_path": str(file_path),
            "dead_functions": dead_code_info.get("functions", []),
            "dead_types": dead_code_info.get("types", []),
            "dead_variables": dead_code_info.get("variables", []),
            "summary": {
                "total_dead_functions": len(dead_code_info.get("functions", [])),
                "total_dead_types": len(dead_code_info.get("types", [])),
                "total_dead_variables": len(dead_code_info.get("variables", [])),
            },
        }

        return json.dumps(report, indent=2)

    def _analyze_go_dead_code(self, content: str) -> Dict[str, List[Dict[str, Any]]]:
        """Analyze Go code to find dead/unused elements."""
        # Find all definitions
        definitions = self._find_go_definitions(content)

        # Find all references
        references = self._find_go_references(content)

        dead_functions = []
        dead_types = []
        dead_variables = []

        # Check functions
        for func in definitions["functions"]:
            func_name = func["name"]

            # Skip main, init, and exported functions (start with uppercase)
            if func_name in ("main", "init"):
                continue
            if func_name[0].isupper():
                # Exported - might be used externally
                continue

            # Check if function is called
            if func_name not in references["function_calls"]:
                dead_functions.append(
                    {
                        "name": func_name,
                        "line_start": func["line_start"],
                        "line_end": func["line_end"],
                        "type": "function",
                    }
                )

        # Check types (structs, interfaces)
        for type_def in definitions["types"]:
            type_name = type_def["name"]

            # Skip exported types
            if type_name[0].isupper():
                continue

            # Check if type is used
            if type_name not in references["type_usage"]:
                dead_types.append(
                    {
                        "name": type_name,
                        "line_start": type_def["line_start"],
                        "line_end": type_def.get("line_end", type_def["line_start"]),
                        "type": type_def.get("kind", "type"),
                    }
                )

        # Check variables (simplified - just top-level var declarations)
        for var in definitions["variables"]:
            var_name = var["name"]

            # Skip exported variables
            if var_name[0].isupper():
                continue

            if var_name not in references["variable_usage"]:
                dead_variables.append(
                    {
                        "name": var_name,
                        "line": var["line"],
                        "type": "variable",
                    }
                )

        return {
            "functions": dead_functions,
            "types": dead_types,
            "variables": dead_variables,
        }

    def _find_go_definitions(self, content: str) -> Dict[str, List[Dict[str, Any]]]:
        """Find all function, type, and variable definitions in Go code."""
        definitions: Dict[str, List[Dict[str, Any]]] = {
            "functions": [],
            "types": [],
            "variables": [],
        }
        lines = content.splitlines()

        i = 0
        while i < len(lines):
            line = lines[i]

            # Function definitions
            func_match = re.search(r"func\s+(\w+)\s*\(", line)
            method_match = re.search(r"func\s+\([^)]+\)\s+(\w+)\s*\(", line)

            if func_match and not method_match:
                func_name = func_match.group(1)
                start_line = i + 1
                # Find end of function
                brace_count = line.count("{") - line.count("}")
                end_line = i + 1

                for j in range(i + 1, len(lines)):
                    brace_count += lines[j].count("{") - lines[j].count("}")
                    if brace_count == 0:
                        end_line = j + 1
                        break

                definitions["functions"].append(
                    {
                        "name": func_name,
                        "line_start": start_line,
                        "line_end": end_line,
                    }
                )

            elif method_match:
                method_name = method_match.group(1)
                start_line = i + 1
                brace_count = line.count("{") - line.count("}")
                end_line = i + 1

                for j in range(i + 1, len(lines)):
                    brace_count += lines[j].count("{") - lines[j].count("}")
                    if brace_count == 0:
                        end_line = j + 1
                        break

                definitions["functions"].append(
                    {
                        "name": method_name,
                        "line_start": start_line,
                        "line_end": end_line,
                        "is_method": True,
                    }
                )

            # Type definitions
            type_match = re.search(r"type\s+(\w+)\s+(struct|interface|\w+)", line)
            if type_match:
                type_name = type_match.group(1)
                kind = type_match.group(2)
                start_line = i + 1

                if kind in ("struct", "interface") and "{" in line:
                    # Find end of struct/interface
                    brace_count = line.count("{") - line.count("}")
                    end_line = i + 1

                    for j in range(i + 1, len(lines)):
                        brace_count += lines[j].count("{") - lines[j].count("}")
                        if brace_count == 0:
                            end_line = j + 1
                            break

                    definitions["types"].append(
                        {
                            "name": type_name,
                            "kind": kind,
                            "line_start": start_line,
                            "line_end": end_line,
                        }
                    )
                else:
                    definitions["types"].append(
                        {
                            "name": type_name,
                            "kind": kind,
                            "line_start": start_line,
                        }
                    )

            # Variable definitions (top-level var)
            var_match = re.match(r"^var\s+(\w+)", line)
            if var_match:
                definitions["variables"].append(
                    {
                        "name": var_match.group(1),
                        "line": i + 1,
                    }
                )

            i += 1

        return definitions

    def _find_go_references(self, content: str) -> Dict[str, Set[str]]:
        """Find all references to functions, types, and variables in Go code."""
        references: Dict[str, Set[str]] = {
            "function_calls": set(),
            "type_usage": set(),
            "variable_usage": set(),
        }

        # Remove comments
        content_no_comments = re.sub(r"//.*$", "", content, flags=re.MULTILINE)
        content_no_comments = re.sub(r"/\*.*?\*/", "", content_no_comments, flags=re.DOTALL)

        # Function calls - analyze line by line to exclude declarations
        lines = content_no_comments.splitlines()
        for line in lines:
            # Skip function/method declarations
            if re.match(r"^\s*func\s+", line):
                continue

            # Find function calls on this line
            call_pattern = r"\b(\w+)\s*\("
            for match in re.finditer(call_pattern, line):
                func_name = match.group(1)
                if func_name not in (
                    "func",
                    "if",
                    "for",
                    "switch",
                    "select",
                    "type",
                    "var",
                    "const",
                ):
                    references["function_calls"].add(func_name)

        # Type usage (variable declarations, type assertions, conversions)
        type_patterns = [
            r":\s*(\w+)\s*[,\)]",  # : Type in function params
            r"\.\((\w+)\)",  # type assertion
            r"(\w+)\{",  # struct literal
            r"(\w+)\(",  # type conversion
            r"var\s+\w+\s+(\w+)",  # var x Type
            r"\[\](\w+)",  # []Type (slice)
            r"map\[(\w+)\]",  # map key type
            r"map\[\w+\](\w+)",  # map value type
            r"\*(\w+)",  # pointer type
            r"chan\s+(\w+)",  # channel type
        ]

        for pattern in type_patterns:
            for match in re.finditer(pattern, content_no_comments):
                type_name = match.group(1)
                if type_name[0].islower() or type_name[0].isupper():
                    references["type_usage"].add(type_name)

        # Variable usage (simplified)
        identifiers = re.findall(r"\b([a-z_]\w*)\b", content_no_comments)
        references["variable_usage"].update(identifiers)

        return references

    def get_language_specific_config(self) -> Dict[str, Any]:
        """Get Go-specific configuration."""
        return {
            "preserve_formatting": True,
            "indent_size": 1,  # Go uses tabs, but we'll represent as 1 for simplicity
            "use_tabs": True,
            "brace_style": "same_line",
            "import_grouping": True,
            "gofmt_compatible": True,
        }

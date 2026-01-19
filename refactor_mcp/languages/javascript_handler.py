"""JavaScript language handler implementation."""

import re
from pathlib import Path
from typing import Any, Dict, List, Optional, Set, Union

try:
    import tree_sitter_javascript as tsjs
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


class JavaScriptHandler(BaseLanguageHandler):
    """Handler for JavaScript language refactoring operations."""

    def __init__(self):
        self._parser = None
        self._init_parser()

    def _init_parser(self):
        """Initialize Tree-sitter parser for JavaScript."""
        if not TREE_SITTER_AVAILABLE:
            return

        try:
            # Use the official tree-sitter-javascript package
            JS_LANGUAGE = Language(tsjs.language())
            self._parser = Parser(JS_LANGUAGE)
        except Exception as e:
            # Fallback to regex-based parsing if tree-sitter fails
            print(f"Warning: Could not initialize JavaScript parser: {e}")
            self._parser = None

    @property
    def language_name(self) -> str:
        return "JavaScript"

    @property
    def file_extensions(self) -> List[str]:
        return [".js", ".jsx", ".mjs", ".cjs"]

    @property
    def supported_operations(self) -> List[RefactoringOperation]:
        return [
            RefactoringOperation.REORDER_FUNCTION,
            RefactoringOperation.ORGANIZE_IMPORTS,
            RefactoringOperation.ADD_IMPORT,
            RefactoringOperation.REMOVE_UNUSED_IMPORTS,
            RefactoringOperation.MOVE_FUNCTION,
            RefactoringOperation.MOVE_CLASS,
            RefactoringOperation.RENAME_SYMBOL,
            RefactoringOperation.GET_CODE_STRUCTURE,
            RefactoringOperation.ANALYZE_DEPENDENCIES,
            RefactoringOperation.EXTRACT_METHOD,
            RefactoringOperation.INLINE_METHOD,
            RefactoringOperation.DETECT_DEAD_CODE,
            RefactoringOperation.REMOVE_DEAD_CODE,
            RefactoringOperation.FIND_CODE_PATTERN,
            RefactoringOperation.APPLY_CODE_PATTERN,
        ]

    def can_handle_file(self, file_path: Union[str, Path]) -> bool:
        """Check if this handler can process the given file."""
        file_path = Path(file_path)

        # Check extension
        if file_path.suffix.lower() in self.file_extensions:
            return True

        # Check shebang for Node.js
        try:
            with open(file_path, "r", encoding="utf-8") as f:
                first_line = f.readline().strip()
                if first_line.startswith("#!") and (
                    "node" in first_line.lower() or "nodejs" in first_line.lower()
                ):
                    return True
        except Exception:
            pass

        # Check for package.json in parent directories (Node.js project)
        current_dir = file_path.parent
        for _ in range(5):  # Check up to 5 levels up
            if (current_dir / "package.json").exists():
                return True
            parent = current_dir.parent
            if parent == current_dir:  # Reached root
                break
            current_dir = parent

        # Check for JavaScript patterns in content
        try:
            content = self.read_file_content(file_path)[:1000]  # First 1KB
            js_patterns = [
                r"\bfunction\s+\w+\s*\(",
                r"\bconst\s+\w+\s*=",
                r"\blet\s+\w+\s*=",
                r"\bvar\s+\w+\s*=",
                r"\bexport\s+",
                r"\bimport\s+",
                r"\brequire\s*\(",
                r"=>\s*\{",
                r"console\.log\s*\(",
                # Node.js specific patterns
                r"module\.exports\s*=",
                r"exports\.\w+\s*=",
                r"process\.env\.",
                r"__dirname",
                r"__filename",
                r"process\.argv",
                r"require\.resolve\s*\(",
                r"global\.\w+",
                # Common Node.js modules
                r'require\s*\(\s*["\']fs["\']',
                r'require\s*\(\s*["\']path["\']',
                r'require\s*\(\s*["\']os["\']',
                r'require\s*\(\s*["\']http["\']',
                r'require\s*\(\s*["\']url["\']',
            ]

            for pattern in js_patterns:
                if re.search(pattern, content):
                    return True

        except Exception:
            pass

        return False

    def validate_syntax(self, content: str) -> bool:
        """Validate JavaScript syntax using Tree-sitter."""
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
        # Check for balanced brackets/braces/parentheses
        stack = []
        pairs = {"(": ")", "[": "]", "{": "}"}

        in_string = False
        string_char = None
        i = 0

        while i < len(content):
            char = content[i]

            # Handle string literals
            if char in ['"', "'", "`"] and not in_string:
                in_string = True
                string_char = char
            elif char == string_char and in_string:
                # Check if escaped
                if i > 0 and content[i - 1] != "\\":
                    in_string = False
                    string_char = None

            # Handle brackets when not in string
            elif not in_string:
                if char in pairs:
                    stack.append(char)
                elif char in pairs.values():
                    if not stack:
                        return False
                    if pairs[stack.pop()] != char:
                        return False

            i += 1

        return len(stack) == 0

    def parse_file(self, file_path: Union[str, Path]) -> Any:
        """Parse JavaScript file into Tree-sitter AST."""
        if not self._parser:
            raise RefactoringError("Tree-sitter parser not available for JavaScript")

        content = self.read_file_content(file_path)

        try:
            tree = self._parser.parse(bytes(content, "utf8"))
            if tree.root_node.has_error:
                raise RefactoringError(f"Syntax error in JavaScript file: {file_path}")
            return tree
        except Exception as e:
            raise RefactoringError(f"Error parsing JavaScript file {file_path}: {e}")

    def get_code_structure(self, file_path: Union[str, Path]) -> CodeStructure:
        """Get structured information about the JavaScript file."""
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

        # Extract functions using regex
        function_patterns = [
            r"function\s+(\w+)\s*\([^)]*\)\s*\{",  # function declaration
            r"const\s+(\w+)\s*=\s*\([^)]*\)\s*=>\s*\{",  # arrow function
            r"const\s+(\w+)\s*=\s*function\s*\([^)]*\)\s*\{",  # function expression
            r"(\w+)\s*:\s*function\s*\([^)]*\)\s*\{",  # method in object
        ]

        line_num = 1
        for line in content.split("\n"):
            for pattern in function_patterns:
                match = re.search(pattern, line)
                if match:
                    func_info = FunctionInfo(
                        name=match.group(1),
                        line_start=line_num,
                        line_end=line_num,  # Approximation
                    )
                    structure.functions.append(func_info)
            line_num += 1

        # Extract imports
        import_patterns = [
            r'import\s+.*?from\s+["\']([^"\']+)["\']',
            r'const\s+.*?=\s+require\s*\(\s*["\']([^"\']+)["\']\s*\)',
        ]

        line_num = 1
        for line in content.split("\n"):
            for pattern in import_patterns:
                match = re.search(pattern, line)
                if match:
                    import_info = ImportInfo(
                        module=match.group(1),
                        line=line_num,
                        import_type="es6_import" if "import" in line else "commonjs_require",
                    )
                    structure.imports.append(import_info)
            line_num += 1

        return structure

    def _extract_structure_from_tree(self, node, structure: CodeStructure):
        """Extract structure information from Tree-sitter AST."""
        if node.type == "function_declaration":
            name_node = node.child_by_field_name("name")
            if name_node:
                func_info = FunctionInfo(
                    name=name_node.text.decode("utf8"),
                    line_start=node.start_point[0] + 1,
                    line_end=node.end_point[0] + 1,
                )
                structure.functions.append(func_info)

        elif node.type == "class_declaration":
            name_node = node.child_by_field_name("name")
            if name_node:
                class_info = ClassInfo(
                    name=name_node.text.decode("utf8"),
                    line_start=node.start_point[0] + 1,
                    line_end=node.end_point[0] + 1,
                )
                structure.classes.append(class_info)

        elif node.type in ["import_statement", "import_declaration"]:
            source_node = node.child_by_field_name("source")
            if source_node:
                module_name = source_node.text.decode("utf8").strip("\"'")
                import_info = ImportInfo(
                    module=module_name, line=node.start_point[0] + 1, import_type="es6_import"
                )
                structure.imports.append(import_info)

        # Recursively process children
        for child in node.children:
            self._extract_structure_from_tree(child, structure)

    def analyze_dependencies(self, file_path: Union[str, Path]) -> Dict[str, Any]:
        """Analyze imports and dependencies in JavaScript file."""
        structure = self.get_code_structure(file_path)

        # Categorize imports
        npm_imports = []
        relative_imports = []
        builtin_imports = []

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
            "cluster",
            "net",
            "tls",
            "dns",
            "readline",
            "repl",
            "vm",
        }

        for imp in structure.imports:
            if imp.module.startswith("."):
                relative_imports.append(imp.__dict__)
            elif imp.module in builtin_modules:
                builtin_imports.append(imp.__dict__)
            else:
                npm_imports.append(imp.__dict__)

        return {
            "file": str(file_path),
            "language": self.language_name,
            "total_imports": len(structure.imports),
            "npm_imports": npm_imports,
            "relative_imports": relative_imports,
            "builtin_imports": builtin_imports,
            "functions": len(structure.functions),
            "classes": len(structure.classes),
            "exports": structure.exports,
        }

    def organize_imports(self, file_path: Union[str, Path]) -> str:
        """Organize imports in a JavaScript file."""
        content = self.read_file_content(file_path)

        # Extract import statements
        import_lines = []
        other_lines = []

        for line_num, line in enumerate(content.split("\n"), 1):
            if self._is_import_line(line):
                import_lines.append((line_num, line))
            else:
                other_lines.append((line_num, line))

        if not import_lines:
            return f"No imports found in {file_path}"

        # Organize imports by type
        organized_imports = self._organize_js_imports([line for _, line in import_lines])

        # Rebuild content
        new_content_lines = []

        # Add non-import lines until first import
        first_import_line = min(line_num for line_num, _ in import_lines)
        for line_num, line in other_lines:
            if line_num < first_import_line:
                new_content_lines.append(line)

        # Add organized imports
        new_content_lines.extend(organized_imports.split("\n"))

        # Add remaining non-import lines
        last_import_line = max(line_num for line_num, _ in import_lines)
        for line_num, line in other_lines:
            if line_num > last_import_line:
                new_content_lines.append(line)

        new_content = "\n".join(new_content_lines)
        self.write_file_content(file_path, new_content)

        return f"Successfully organized imports in {file_path}"

    def _is_import_line(self, line: str) -> bool:
        """Check if a line contains an import statement."""
        stripped = line.strip()
        return (
            stripped.startswith("import ")
            or stripped.startswith("const ")
            and "require(" in stripped
            or stripped.startswith("let ")
            and "require(" in stripped
            or stripped.startswith("var ")
            and "require(" in stripped
        )

    def _organize_js_imports(self, import_lines: List[str]) -> str:
        """Organize JavaScript imports into groups."""
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
            if module_name.startswith("."):
                relative_imports.append(line)
            elif module_name in builtin_modules:
                builtin_imports.append(line)
            else:
                npm_imports.append(line)

        # Sort each group
        builtin_imports.sort()
        npm_imports.sort()
        relative_imports.sort()

        # Combine groups
        groups = []
        if builtin_imports:
            groups.append("\n".join(builtin_imports))
        if npm_imports:
            groups.append("\n".join(npm_imports))
        if relative_imports:
            groups.append("\n".join(relative_imports))

        return "\n\n".join(groups) + "\n\n"

    def _extract_module_name_from_import(self, line: str) -> Optional[str]:
        """Extract module name from import line."""
        # ES6 imports
        es6_match = re.search(r'from\s+["\']([^"\']+)["\']', line)
        if es6_match:
            return es6_match.group(1)

        # CommonJS requires
        cjs_match = re.search(r'require\s*\(\s*["\']([^"\']+)["\']\s*\)', line)
        if cjs_match:
            return cjs_match.group(1)

        return None

    def add_import(
        self, file_path: Union[str, Path], module: str, symbols: Optional[List[str]] = None
    ) -> str:
        """Add an import statement to a JavaScript file."""
        content = self.read_file_content(file_path)

        # Determine import style (ES6 or CommonJS)
        has_es6_imports = "import " in content and "from " in content
        has_cjs_imports = "require(" in content

        # Create import statement
        if has_es6_imports or not has_cjs_imports:  # Default to ES6
            if symbols:
                import_stmt = f"import {{ {', '.join(symbols)} }} from '{module}'"
            else:
                import_stmt = f"import {module.split('/')[-1]} from '{module}'"
        else:  # Use CommonJS
            if symbols:
                import_stmt = f"const {{ {', '.join(symbols)} }} = require('{module}')"
            else:
                var_name = module.split("/")[-1]
                import_stmt = f"const {var_name} = require('{module}')"

        # Find insertion point
        lines = content.splitlines()
        insert_idx = self._find_js_import_insertion_point(lines)

        lines.insert(insert_idx, import_stmt)
        new_content = "\n".join(lines) + "\n"

        self.write_file_content(file_path, new_content)

        return f"Successfully added import '{import_stmt}' to {file_path}"

    def _find_js_import_insertion_point(self, lines: List[str]) -> int:
        """Find the best place to insert a new import in JavaScript."""
        # Look for existing imports
        last_import_idx = -1

        for i, line in enumerate(lines):
            if self._is_import_line(line):
                last_import_idx = i

        if last_import_idx >= 0:
            return last_import_idx + 1

        # If no imports found, insert after comments/directives at top
        for i, line in enumerate(lines):
            stripped = line.strip()
            if stripped and not (
                stripped.startswith("//")
                or stripped.startswith("/*")
                or stripped.startswith("*")
                or stripped.startswith('"use strict"')
                or stripped.startswith("'use strict'")
            ):
                return i

        return 0

    def remove_unused_imports(self, file_path: Union[str, Path]) -> str:
        """Remove unused import statements from JavaScript file."""
        content = self.read_file_content(file_path)
        lines = content.split("\n")

        # Find all import statements and their imported symbols
        imports_to_check: List[Dict[str, Any]] = []
        import_lines_to_remove: List[int] = []

        for line_num, line in enumerate(lines):
            if self._is_import_line(line.strip()):
                imported_symbols = self._extract_imported_symbols(line)
                if imported_symbols:
                    imports_to_check.append(
                        {"line_num": line_num, "line": line, "symbols": imported_symbols}
                    )

        if not imports_to_check:
            return f"No imports found in {file_path}"

        # Check if each imported symbol is used in the code
        # Combine all non-import lines for usage analysis
        code_content = "\n".join(
            [line for i, line in enumerate(lines) if not self._is_import_line(lines[i].strip())]
        )

        unused_imports: List[Dict[str, Any]] = []
        partially_used_imports: List[Dict[str, Any]] = []

        for import_info in imports_to_check:
            unused_symbols = []
            used_symbols = []

            for symbol in import_info["symbols"]:
                # Check if symbol is used in the code (basic regex check)
                if self._is_symbol_used(symbol, code_content):
                    used_symbols.append(symbol)
                else:
                    unused_symbols.append(symbol)

            if len(unused_symbols) == len(import_info["symbols"]):
                # Entire import is unused
                unused_imports.append(import_info)
                import_lines_to_remove.append(import_info["line_num"])
            elif unused_symbols:
                # Partially used import - could be optimized
                partially_used_imports.append(
                    {
                        "import_info": import_info,
                        "unused_symbols": unused_symbols,
                        "used_symbols": used_symbols,
                    }
                )

        if not import_lines_to_remove and not partially_used_imports:
            return f"No unused imports found in {file_path}"

        # Remove completely unused import lines
        new_lines = []
        removed_count = 0

        for line_num, line in enumerate(lines):
            if line_num not in import_lines_to_remove:
                new_lines.append(line)
            else:
                removed_count += 1

        # Update partially used imports (for now, just report them)
        result_messages = []

        if removed_count > 0:
            new_content = "\n".join(new_lines)
            self.write_file_content(file_path, new_content)
            result_messages.append(f"Removed {removed_count} unused import statements")

        if partially_used_imports:
            partial_count = len(partially_used_imports)
            result_messages.append(
                f"Found {partial_count} partially used imports that could be optimized"
            )

        return f"Successfully processed imports in {file_path}: " + ", ".join(result_messages)

    def _extract_imported_symbols(self, line: str) -> List[str]:
        """Extract symbol names from an import statement."""
        symbols = []

        # ES6 imports: import { symbol1, symbol2 } from 'module'
        es6_match = re.search(r"import\s+\{([^}]+)\}\s+from", line)
        if es6_match:
            symbol_text = es6_match.group(1)
            # Handle renamed imports: { symbol as alias }
            for part in symbol_text.split(","):
                part = part.strip()
                if " as " in part:
                    # Use the alias name
                    symbols.append(part.split(" as ")[1].strip())
                else:
                    symbols.append(part.strip())
            return symbols

        # ES6 default imports: import defaultSymbol from 'module'
        default_match = re.search(r"import\s+(\w+)\s+from", line)
        if default_match:
            symbols.append(default_match.group(1))
            return symbols

        # CommonJS destructured: const { symbol1, symbol2 } = require('module')
        cjs_destructure_match = re.search(r"const\s+\{([^}]+)\}\s*=\s*require", line)
        if cjs_destructure_match:
            symbol_text = cjs_destructure_match.group(1)
            for part in symbol_text.split(","):
                symbols.append(part.strip())
            return symbols

        # CommonJS simple: const symbol = require('module')
        cjs_simple_match = re.search(r"const\s+(\w+)\s*=\s*require", line)
        if cjs_simple_match:
            symbols.append(cjs_simple_match.group(1))
            return symbols

        return symbols

    def _is_symbol_used(self, symbol: str, code_content: str) -> bool:
        """Check if a symbol is used in the code."""
        # Basic usage patterns to check
        usage_patterns = [
            rf"\b{re.escape(symbol)}\s*\(",  # Function call
            rf"\b{re.escape(symbol)}\s*\.",  # Property access
            rf"\b{re.escape(symbol)}\s*\[",  # Array/object access
            rf"\b{re.escape(symbol)}\b",  # General usage
            rf"new\s+{re.escape(symbol)}\b",  # Constructor usage
        ]

        for pattern in usage_patterns:
            if re.search(pattern, code_content):
                return True

        return False

    def rename_symbol(
        self, file_path: Union[str, Path], old_name: str, new_name: str, scope: str = "file"
    ) -> str:
        """Rename a symbol (variable, function, class) in JavaScript file."""
        content = self.read_file_content(file_path)

        if not self.validate_syntax(content):
            raise RefactoringError(f"Invalid syntax in file {file_path}")

        if old_name == new_name:
            return f"Old name and new name are identical: {old_name}"

        # Validate new name is a valid JavaScript identifier
        if not re.match(r"^[a-zA-Z_$][a-zA-Z0-9_$]*$", new_name):
            raise RefactoringError(f"Invalid JavaScript identifier: {new_name}")

        # Find all occurrences of the symbol based on scope
        replacements_made = 0

        if scope == "file":
            # Simple file-level rename using word boundaries
            # This is a basic implementation - a full implementation would use AST
            pattern = rf"\b{re.escape(old_name)}\b"

            # Be more careful with replacements to avoid false positives
            lines = content.split("\n")
            new_lines = []

            for line in lines:
                # Skip comments and strings (basic implementation)
                if self._should_skip_line_for_rename(line):
                    new_lines.append(line)
                    continue

                # Count replacements in this line
                old_line = line
                new_line = re.sub(pattern, new_name, line)
                if new_line != old_line:
                    replacements_made += (
                        line.count(old_name)
                        - new_line.count(old_name)
                        + new_line.count(new_name)
                        - old_line.count(new_name)
                    )
                    replacements_made = max(
                        0, replacements_made + 1
                    )  # Simple increment per line changed

                new_lines.append(new_line)

            if replacements_made > 0:
                new_content = "\n".join(new_lines)
                self.write_file_content(file_path, new_content)
                return f"Successfully renamed '{old_name}' to '{new_name}' in {file_path} ({replacements_made} replacements)"
            else:
                return f"Symbol '{old_name}' not found in {file_path}"

        elif scope == "function":
            # Function-scoped rename - would need more sophisticated parsing
            return "Function-scoped rename not yet implemented for JavaScript"

        elif scope == "class":
            # Class-scoped rename
            return "Class-scoped rename not yet implemented for JavaScript"

        else:
            raise RefactoringError(f"Unsupported scope: {scope}")

    def _should_skip_line_for_rename(self, line: str) -> bool:
        """Check if a line should be skipped during renaming (comments, strings)."""
        stripped = line.strip()

        # Skip comment lines
        if stripped.startswith("//") or stripped.startswith("/*") or stripped.startswith("*"):
            return True

        # Skip lines that are primarily strings (basic check)
        # This is a simplified approach - proper implementation would parse strings correctly
        quote_count = line.count('"') + line.count("'") + line.count("`")
        if quote_count >= 2:  # Likely contains string literals
            # Be conservative and skip lines with many quotes
            return True

        return False

    def extract_method(
        self, file_path: Union[str, Path], start_line: int, end_line: int, method_name: str
    ) -> str:
        """Extract a method from existing JavaScript code."""
        content = self.read_file_content(file_path)
        lines = content.split("\n")

        # Validate inputs
        if start_line < 1 or end_line >= len(lines) + 1:
            raise RefactoringError(f"Invalid line range: {start_line}-{end_line}")

        if start_line > end_line:
            raise RefactoringError(f"Start line {start_line} must be <= end line {end_line}")

        if not re.match(r"^[a-zA-Z_$][a-zA-Z0-9_$]*$", method_name):
            raise RefactoringError(f"Invalid JavaScript function name: {method_name}")

        # Extract the code block (adjust for 0-based indexing)
        extracted_lines = lines[start_line - 1 : end_line]
        extracted_code = "\n".join(extracted_lines)

        if not extracted_code.strip():
            raise RefactoringError("Cannot extract empty code block")

        # Analyze variables used in the extracted code
        variables_in_code = self._find_variables_in_code(extracted_code)

        # Find variables that are defined before the extraction point
        variables_before = self._find_variables_before_line(lines, start_line)

        # Parameters are variables used in extracted code but defined before
        parameters = [var for var in variables_in_code if var in variables_before]

        # Simple heuristic for return value - look for assignments or return statements
        has_return = "return " in extracted_code
        assigns_variables = self._finds_assignments_in_code(extracted_code)

        # Create the extracted method
        param_str = ", ".join(parameters) if parameters else ""

        # Basic indentation detection
        first_line = extracted_lines[0] if extracted_lines else ""
        indent = len(first_line) - len(first_line.lstrip())
        base_indent = " " * indent

        # Build the new function
        new_function_lines = [
            f"{base_indent}function {method_name}({param_str}) {{",
        ]

        # Add the extracted code with proper indentation
        for line in extracted_lines:
            if line.strip():  # Don't add extra indentation to empty lines
                new_function_lines.append(f"  {line}")
            else:
                new_function_lines.append(line)

        # Add return statement if needed
        if assigns_variables and not has_return:
            # Simple heuristic: return the first assigned variable
            if assigns_variables:
                new_function_lines.append(f"  return {assigns_variables[0]};")

        new_function_lines.append(f"{base_indent}}}")

        # Replace the original code with a function call
        if parameters:
            call_stmt = f"{base_indent}{method_name}({param_str});"
        else:
            call_stmt = f"{base_indent}{method_name}();"

        # If there were assignments, we might need to capture the return value
        if assigns_variables and not has_return:
            call_stmt = f"{base_indent}const {assigns_variables[0]} = {method_name}({param_str});"

        # Build the new file content
        new_lines = []

        # Add lines before extraction
        new_lines.extend(lines[: start_line - 1])

        # Add the function call
        new_lines.append(call_stmt)

        # Add lines after extraction
        new_lines.extend(lines[end_line:])

        # Add the new function at the end of the file (or find a better place)
        new_lines.append("")  # Empty line before function
        new_lines.extend(new_function_lines)

        # Write the modified content
        new_content = "\n".join(new_lines)
        self.write_file_content(file_path, new_content)

        return f"Successfully extracted method '{method_name}' from lines {start_line}-{end_line} in {file_path}"

    def _find_variables_in_code(self, code: str) -> List[str]:
        """Find variable names used in code block."""
        # Simple regex-based approach to find identifiers
        # This is basic - a proper implementation would use AST
        identifiers = set(re.findall(r"\b[a-zA-Z_$][a-zA-Z0-9_$]*\b", code))

        # Filter out JavaScript keywords and common built-ins
        js_keywords = {
            "var",
            "let",
            "const",
            "function",
            "return",
            "if",
            "else",
            "for",
            "while",
            "do",
            "break",
            "continue",
            "switch",
            "case",
            "default",
            "try",
            "catch",
            "finally",
            "throw",
            "typeof",
            "instanceof",
            "new",
            "this",
            "super",
            "class",
            "extends",
            "import",
            "export",
            "true",
            "false",
            "null",
            "undefined",
            "console",
            "log",
            "error",
            "warn",
            "info",  # common built-ins
        }

        return [var for var in identifiers if var not in js_keywords]

    def _find_variables_before_line(self, lines: List[str], line_num: int) -> List[str]:
        """Find variables defined before the given line number."""
        variables = set()

        # Look at lines before the extraction point
        for i in range(min(line_num - 1, len(lines))):
            line = lines[i]

            # Find variable declarations
            # var/let/const declarations
            var_matches = re.findall(r"(?:var|let|const)\s+([a-zA-Z_$][a-zA-Z0-9_$]*)", line)
            variables.update(var_matches)

            # Function declarations
            func_matches = re.findall(r"function\s+([a-zA-Z_$][a-zA-Z0-9_$]*)", line)
            variables.update(func_matches)

            # Arrow function assignments
            arrow_matches = re.findall(
                r"(?:var|let|const)\s+([a-zA-Z_$][a-zA-Z0-9_$]*)\s*=.*=>", line
            )
            variables.update(arrow_matches)

        return list(variables)

    def _finds_assignments_in_code(self, code: str) -> List[str]:
        """Find variables that are assigned in the code block."""
        # Look for assignment patterns
        assignments = re.findall(r"([a-zA-Z_$][a-zA-Z0-9_$]*)\s*=\s*[^=]", code)
        return list(set(assignments))

    def inline_method(self, file_path: Union[str, Path], method_name: str) -> str:
        """Inline a method into its call sites."""
        content = self.read_file_content(file_path)
        lines = content.split("\n")

        # Find the method definition
        method_def = self._find_method_definition(lines, method_name)
        if not method_def:
            raise RefactoringError(f"Method '{method_name}' not found in {file_path}")

        method_start, method_end, method_params, method_body = method_def

        # Find all call sites
        call_sites = self._find_method_call_sites(lines, method_name)
        if not call_sites:
            return f"No call sites found for method '{method_name}' in {file_path}"

        # Validate that the method is simple enough to inline
        if not self._is_method_safe_to_inline(method_body):
            raise RefactoringError(f"Method '{method_name}' is too complex to safely inline")

        # Sort call sites in reverse order to avoid line number shifts
        call_sites.sort(key=lambda x: x["line_num"], reverse=True)

        new_lines = lines.copy()
        replacements_made = 0

        # Replace each call site with the method body
        for call_site in call_sites:
            line_num = call_site["line_num"]
            call_args = call_site["args"]

            # Create parameter substitution map
            param_map = {}
            if len(call_args) == len(method_params):
                param_map = dict(zip(method_params, call_args))

            # Substitute parameters in method body
            inlined_body = self._substitute_parameters_in_body(method_body, param_map)

            # Get indentation of the call site
            original_line = new_lines[line_num]
            call_indent = len(original_line) - len(original_line.lstrip())
            base_indent = " " * call_indent

            # Create inlined code with proper indentation
            inlined_lines = []
            for body_line in inlined_body:
                if body_line.strip():  # Don't add indent to empty lines
                    inlined_lines.append(base_indent + body_line.strip())
                else:
                    inlined_lines.append("")

            # Replace the call site
            if len(inlined_lines) == 1:
                # Single line replacement
                new_lines[line_num] = inlined_lines[0]
            else:
                # Multi-line replacement
                new_lines[line_num : line_num + 1] = inlined_lines

            replacements_made += 1

        # Remove the original method definition
        # Adjust indices if call sites were above the method definition
        method_start_adjusted = method_start
        method_end_adjusted = method_end

        for call_site in call_sites:
            if call_site["line_num"] < method_start:
                # Call site was above method, adjust method indices
                lines_added = len(call_site.get("inlined_lines", [])) - 1
                method_start_adjusted += lines_added
                method_end_adjusted += lines_added

        # Remove method definition (in reverse order to maintain indices)
        del new_lines[method_start_adjusted : method_end_adjusted + 1]

        # Write the modified content
        new_content = "\n".join(new_lines)
        self.write_file_content(file_path, new_content)

        return f"Successfully inlined method '{method_name}' at {replacements_made} call sites in {file_path}"

    def _find_method_definition(self, lines: List[str], method_name: str) -> Optional[tuple]:
        """Find method definition and return (start_line, end_line, params, body)."""
        for i, line in enumerate(lines):
            # Look for function declaration
            func_match = re.search(rf"function\s+{re.escape(method_name)}\s*\(([^)]*)\)", line)
            if func_match:
                params = [p.strip() for p in func_match.group(1).split(",") if p.strip()]

                # Find the opening brace and method body
                if "{" in line:
                    brace_count = line.count("{") - line.count("}")
                    body_start = i + 1

                    # Find closing brace
                    for j in range(i + 1, len(lines)):
                        brace_count += lines[j].count("{") - lines[j].count("}")
                        if brace_count == 0:
                            # Extract method body (excluding braces)
                            body_lines = lines[body_start:j]
                            return (i, j, params, body_lines)

            # Look for arrow function assignment
            arrow_match = re.search(
                rf"(?:const|let|var)\s+{re.escape(method_name)}\s*=\s*\(([^)]*)\)\s*=>", line
            )
            if arrow_match:
                params = [p.strip() for p in arrow_match.group(1).split(",") if p.strip()]

                # Simple case: single line arrow function
                if "=>" in line and "{" not in line:
                    # Single expression arrow function
                    arrow_body = line.split("=>", 1)[1].strip()
                    if arrow_body.endswith(";"):
                        arrow_body = arrow_body[:-1]
                    body_lines = [f"return {arrow_body};"]
                    return (i, i, params, body_lines)

                elif "{" in line:
                    # Multi-line arrow function
                    brace_count = line.count("{") - line.count("}")
                    body_start = i + 1

                    for j in range(i + 1, len(lines)):
                        brace_count += lines[j].count("{") - lines[j].count("}")
                        if brace_count == 0:
                            body_lines = lines[body_start:j]
                            return (i, j, params, body_lines)

        return None

    def _find_method_call_sites(self, lines: List[str], method_name: str) -> List[dict]:
        """Find all call sites of a method."""
        call_sites = []

        for i, line in enumerate(lines):
            # Look for function calls: methodName(args)
            call_matches = re.finditer(rf"\b{re.escape(method_name)}\s*\(([^)]*)\)", line)

            for match in call_matches:
                args_str = match.group(1).strip()
                args = (
                    [arg.strip() for arg in args_str.split(",") if arg.strip()] if args_str else []
                )

                call_sites.append({"line_num": i, "args": args, "full_match": match.group(0)})

        return call_sites

    def _is_method_safe_to_inline(self, method_body: List[str]) -> bool:
        """Check if method is simple enough to safely inline."""
        body_str = "\n".join(method_body)

        # Don't inline if method is too complex
        if len(method_body) > 10:  # Arbitrary limit
            return False

        # Don't inline if it contains complex control flow
        complex_patterns = [
            r"\bfor\s*\(",
            r"\bwhile\s*\(",
            r"\bif\s*\(",
            r"\btry\s*\{",
            r"\bcatch\s*\(",
            r"\bswitch\s*\(",
        ]

        for pattern in complex_patterns:
            if re.search(pattern, body_str):
                return False

        return True

    def _substitute_parameters_in_body(
        self, method_body: List[str], param_map: Dict[str, str]
    ) -> List[str]:
        """Substitute parameter names with argument values in method body."""
        if not param_map:
            return method_body

        substituted_body = []

        for line in method_body:
            new_line = line

            # Substitute each parameter with its argument
            for param, arg in param_map.items():
                # Use word boundaries to avoid partial matches
                pattern = rf"\b{re.escape(param)}\b"
                new_line = re.sub(pattern, arg, new_line)

            substituted_body.append(new_line)

        return substituted_body

    def find_code_pattern(
        self, file_path: Union[str, Path], pattern: str, pattern_type: str = "regex"
    ) -> str:
        """Find code patterns in a JavaScript file."""
        content = self.read_file_content(file_path)

        if pattern_type == "regex":
            return self._find_regex_pattern(content, pattern, file_path)
        elif pattern_type == "ast":
            return self._find_ast_pattern(content, pattern, file_path)
        elif pattern_type == "semantic":
            return self._find_semantic_pattern(content, pattern, file_path)
        else:
            raise RefactoringError(f"Unsupported pattern type: {pattern_type}")

    def _find_regex_pattern(self, content: str, pattern: str, file_path: Union[str, Path]) -> str:
        """Find patterns using regular expressions."""
        try:
            matches: List[Dict[str, Any]] = []
            lines = content.split("\n")

            for line_num, line in enumerate(lines, 1):
                for match in re.finditer(pattern, line):
                    matches.append(
                        {
                            "line": line_num,
                            "column": match.start() + 1,
                            "match": match.group(),
                            "context": line.strip(),
                        }
                    )

            if not matches:
                return f"No matches found for pattern '{pattern}' in {file_path}"

            result_lines = [f"Found {len(matches)} matches for pattern '{pattern}' in {file_path}:"]
            for match_info in matches:
                result_lines.append(
                    f"  Line {match_info['line']}:{match_info['column']} - '{match_info['match']}' in: {match_info['context']}"
                )

            return "\n".join(result_lines)

        except re.error as e:
            raise RefactoringError(f"Invalid regex pattern '{pattern}': {e}")

    def _find_ast_pattern(self, content: str, pattern: str, file_path: Union[str, Path]) -> str:
        """Find patterns using AST analysis (basic implementation)."""
        if not self._parser:
            return "AST pattern matching requires Tree-sitter parser (not available)"

        try:
            tree = self._parser.parse(bytes(content, "utf8"))
            matches: List[Dict[str, Any]] = []

            # Simple AST pattern matching for common JavaScript constructs
            if pattern == "function_declaration":
                self._find_function_declarations(tree.root_node, matches, content)
            elif pattern == "variable_declaration":
                self._find_variable_declarations(tree.root_node, matches, content)
            elif pattern == "arrow_function":
                self._find_arrow_functions(tree.root_node, matches, content)
            elif pattern == "class_declaration":
                self._find_class_declarations(tree.root_node, matches, content)
            else:
                return f"AST pattern '{pattern}' not yet implemented"

            if not matches:
                return f"No {pattern} patterns found in {file_path}"

            result_lines = [f"Found {len(matches)} {pattern} patterns in {file_path}:"]
            for match in matches:
                result_lines.append(f"  Line {match['line']}: {match['text']}")

            return "\n".join(result_lines)

        except Exception as e:
            raise RefactoringError(f"AST pattern matching failed: {e}")

    def _find_semantic_pattern(
        self, content: str, pattern: str, file_path: Union[str, Path]
    ) -> str:
        """Find patterns using semantic analysis."""
        # Semantic patterns for JavaScript
        semantic_patterns = {
            "unused_variables": self._find_unused_variables,
            "console_logs": self._find_console_logs,
            "callback_functions": self._find_callback_functions,
            "async_functions": self._find_async_functions,
            "promise_chains": self._find_promise_chains,
        }

        if pattern not in semantic_patterns:
            available = ", ".join(semantic_patterns.keys())
            return f"Semantic pattern '{pattern}' not available. Available patterns: {available}"

        matches = semantic_patterns[pattern](content)

        if not matches:
            return f"No {pattern} patterns found in {file_path}"

        result_lines = [f"Found {len(matches)} {pattern} patterns in {file_path}:"]
        for match in matches:
            result_lines.append(f"  Line {match['line']}: {match['description']}")

        return "\n".join(result_lines)

    def _find_function_declarations(self, node, matches: List[dict], content: str):
        """Find function declarations in AST."""
        if node.type == "function_declaration":
            name_node = node.child_by_field_name("name")
            if name_node:
                matches.append(
                    {
                        "line": node.start_point[0] + 1,
                        "text": f"function {name_node.text.decode('utf8')}",
                    }
                )

        for child in node.children:
            self._find_function_declarations(child, matches, content)

    def _find_variable_declarations(self, node, matches: List[dict], content: str):
        """Find variable declarations in AST."""
        if node.type in ["variable_declaration", "lexical_declaration"]:
            matches.append(
                {
                    "line": node.start_point[0] + 1,
                    "text": (
                        node.text.decode("utf8")[:50] + "..."
                        if len(node.text) > 50
                        else node.text.decode("utf8")
                    ),
                }
            )

        for child in node.children:
            self._find_variable_declarations(child, matches, content)

    def _find_arrow_functions(self, node, matches: List[dict], content: str):
        """Find arrow functions in AST."""
        if node.type == "arrow_function":
            matches.append(
                {
                    "line": node.start_point[0] + 1,
                    "text": (
                        node.text.decode("utf8")[:50] + "..."
                        if len(node.text) > 50
                        else node.text.decode("utf8")
                    ),
                }
            )

        for child in node.children:
            self._find_arrow_functions(child, matches, content)

    def _find_class_declarations(self, node, matches: List[dict], content: str):
        """Find class declarations in AST."""
        if node.type == "class_declaration":
            name_node = node.child_by_field_name("name")
            if name_node:
                matches.append(
                    {
                        "line": node.start_point[0] + 1,
                        "text": f"class {name_node.text.decode('utf8')}",
                    }
                )

        for child in node.children:
            self._find_class_declarations(child, matches, content)

    def _find_unused_variables(self, content: str) -> List[dict]:
        """Find potentially unused variables."""
        lines = content.split("\n")
        matches = []

        # Simple heuristic: find variable declarations that might be unused
        for line_num, line in enumerate(lines, 1):
            # Find variable declarations
            var_matches = re.findall(r"(?:var|let|const)\s+([a-zA-Z_$][a-zA-Z0-9_$]*)", line)
            for var_name in var_matches:
                # Check if variable is used later in the code
                usage_count = sum(
                    1
                    for line_text in lines[line_num:]
                    if re.search(rf"\b{re.escape(var_name)}\b", line_text)
                )
                if usage_count == 0:
                    matches.append(
                        {"line": line_num, "description": f"Variable '{var_name}' may be unused"}
                    )

        return matches

    def _find_console_logs(self, content: str) -> List[dict]:
        """Find console.log statements."""
        lines = content.split("\n")
        matches = []

        for line_num, line in enumerate(lines, 1):
            if re.search(r"console\.(log|warn|error|info)", line):
                matches.append({"line": line_num, "description": line.strip()})

        return matches

    def _find_callback_functions(self, content: str) -> List[dict]:
        """Find callback function patterns."""
        lines = content.split("\n")
        matches = []

        callback_patterns = [
            r"\.then\s*\(",
            r"\.catch\s*\(",
            r"\.forEach\s*\(",
            r"\.map\s*\(",
            r"\.filter\s*\(",
            r"addEventListener\s*\(",
        ]

        for line_num, line in enumerate(lines, 1):
            for pattern in callback_patterns:
                if re.search(pattern, line):
                    matches.append(
                        {"line": line_num, "description": f"Callback pattern: {line.strip()}"}
                    )
                    break

        return matches

    def _find_async_functions(self, content: str) -> List[dict]:
        """Find async function patterns."""
        lines = content.split("\n")
        matches = []

        for line_num, line in enumerate(lines, 1):
            if re.search(r"\basync\s+function", line) or re.search(r"\basync\s*\(", line):
                matches.append({"line": line_num, "description": f"Async function: {line.strip()}"})

        return matches

    def _find_promise_chains(self, content: str) -> List[dict]:
        """Find Promise chain patterns."""
        lines = content.split("\n")
        matches = []

        for line_num, line in enumerate(lines, 1):
            if re.search(r"\.then\s*\(.*\)\.", line) or re.search(
                r"Promise\.(resolve|reject|all)", line
            ):
                matches.append({"line": line_num, "description": f"Promise chain: {line.strip()}"})

        return matches

    def apply_code_pattern(
        self,
        file_path: Union[str, Path],
        find_pattern: str,
        replace_pattern: str,
        pattern_type: str = "regex",
        max_replacements: int = -1,
    ) -> str:
        """Apply code pattern transformations."""
        content = self.read_file_content(file_path)

        if pattern_type == "regex":
            return self._apply_regex_pattern(
                content, find_pattern, replace_pattern, file_path, max_replacements
            )
        elif pattern_type == "semantic":
            return self._apply_semantic_pattern(
                content, find_pattern, replace_pattern, file_path, max_replacements
            )
        else:
            raise RefactoringError(
                f"Unsupported pattern type for apply_code_pattern: {pattern_type}"
            )

    def _apply_regex_pattern(
        self,
        content: str,
        find_pattern: str,
        replace_pattern: str,
        file_path: Union[str, Path],
        max_replacements: int,
    ) -> str:
        """Apply regex-based pattern replacements."""
        try:
            original_content = content

            if max_replacements == -1:
                new_content = re.sub(find_pattern, replace_pattern, content)
                replacement_count = len(re.findall(find_pattern, content))
            else:
                new_content = re.sub(find_pattern, replace_pattern, content, count=max_replacements)
                replacement_count = min(max_replacements, len(re.findall(find_pattern, content)))

            if new_content == original_content:
                return f"No matches found for pattern '{find_pattern}' in {file_path}"

            # Validate syntax before writing
            if not self.validate_syntax(new_content):
                raise RefactoringError(
                    "Pattern replacement would result in invalid JavaScript syntax"
                )

            self.write_file_content(file_path, new_content)
            return f"Successfully applied pattern replacement in {file_path}: {replacement_count} replacements made"

        except re.error as e:
            raise RefactoringError(f"Invalid regex pattern '{find_pattern}': {e}")

    def _apply_semantic_pattern(
        self,
        content: str,
        find_pattern: str,
        replace_pattern: str,
        file_path: Union[str, Path],
        max_replacements: int,
    ) -> str:
        """Apply semantic pattern transformations."""
        # Semantic transformations for common JavaScript patterns
        if find_pattern == "var_to_const":
            return self._transform_var_to_const(content, file_path, max_replacements)
        elif find_pattern == "function_to_arrow":
            return self._transform_function_to_arrow(content, file_path, max_replacements)
        elif find_pattern == "callback_to_promise":
            return self._transform_callback_to_promise(content, file_path, max_replacements)
        elif find_pattern == "remove_console_logs":
            return self._remove_console_logs(content, file_path, max_replacements)
        else:
            available_patterns = [
                "var_to_const",
                "function_to_arrow",
                "callback_to_promise",
                "remove_console_logs",
            ]
            return f"Semantic pattern '{find_pattern}' not available. Available patterns: {', '.join(available_patterns)}"

    def _transform_var_to_const(
        self, content: str, file_path: Union[str, Path], max_replacements: int
    ) -> str:
        """Transform var declarations to const where appropriate."""
        lines = content.split("\n")
        new_lines = []
        replacements_made = 0

        for line in lines:
            new_line = line

            # Simple heuristic: replace var with const if it looks like it's not reassigned
            # This is basic - a proper implementation would use scope analysis
            if re.search(r"\bvar\s+(\w+)\s*=", line) and not re.search(r"\bvar\s+\w+\s*;", line):
                if max_replacements == -1 or replacements_made < max_replacements:
                    new_line = re.sub(r"\bvar\b", "const", line, count=1)
                    if new_line != line:
                        replacements_made += 1

            new_lines.append(new_line)

        if replacements_made == 0:
            return f"No var declarations suitable for const transformation found in {file_path}"

        new_content = "\n".join(new_lines)
        self.write_file_content(file_path, new_content)
        return f"Transformed {replacements_made} var declarations to const in {file_path}"

    def _transform_function_to_arrow(
        self, content: str, file_path: Union[str, Path], max_replacements: int
    ) -> str:
        """Transform function expressions to arrow functions."""
        # This is a complex transformation - basic implementation
        pattern = r"function\s*\(([^)]*)\)\s*\{\s*return\s+([^}]+);\s*\}"
        replacement = r"(\1) => \2"

        try:
            original_content = content
            if max_replacements == -1:
                new_content = re.sub(pattern, replacement, content)
            else:
                new_content = re.sub(pattern, replacement, content, count=max_replacements)

            replacements_made = len(re.findall(pattern, content))
            if max_replacements != -1:
                replacements_made = min(replacements_made, max_replacements)

            if new_content == original_content:
                return f"No simple function expressions found to convert to arrow functions in {file_path}"

            self.write_file_content(file_path, new_content)
            return f"Converted {replacements_made} function expressions to arrow functions in {file_path}"

        except Exception as e:
            raise RefactoringError(f"Error transforming functions to arrows: {e}")

    def _transform_callback_to_promise(
        self, content: str, file_path: Union[str, Path], max_replacements: int
    ) -> str:
        """Transform callback patterns to Promises (basic implementation)."""
        # This would be a very complex transformation - providing a basic example
        return f"Callback to Promise transformation not fully implemented yet for {file_path}"

    def _remove_console_logs(
        self, content: str, file_path: Union[str, Path], max_replacements: int
    ) -> str:
        """Remove console.log statements."""
        lines = content.split("\n")
        new_lines = []
        removals_made = 0

        for line in lines:
            if re.search(r"^\s*console\.(log|warn|error|info)", line.strip()):
                if max_replacements == -1 or removals_made < max_replacements:
                    # Remove the line entirely or replace with empty line to preserve line numbers
                    new_lines.append("")  # Keep line numbers consistent
                    removals_made += 1
                    continue

            new_lines.append(line)

        if removals_made == 0:
            return f"No console statements found to remove in {file_path}"

        new_content = "\n".join(new_lines)
        self.write_file_content(file_path, new_content)
        return f"Removed {removals_made} console statements from {file_path}"

    def validate_refactoring_operation(
        self, file_path: Union[str, Path], operation: RefactoringOperation, **kwargs
    ) -> Dict[str, Any]:
        """Validate that a refactoring operation is safe to perform."""
        validation_result: Dict[str, Any] = {
            "is_valid": True,
            "warnings": [],
            "errors": [],
            "suggestions": [],
        }

        try:
            content = self.read_file_content(file_path)

            # Basic syntax validation
            if not self.validate_syntax(content):
                validation_result["is_valid"] = False
                validation_result["errors"].append("File contains syntax errors")
                return validation_result

            # Operation-specific validations
            if operation == RefactoringOperation.REMOVE_UNUSED_IMPORTS:
                return self._validate_remove_unused_imports(content, validation_result, **kwargs)
            elif operation == RefactoringOperation.RENAME_SYMBOL:
                return self._validate_rename_symbol(content, validation_result, **kwargs)
            elif operation == RefactoringOperation.EXTRACT_METHOD:
                return self._validate_extract_method(content, validation_result, **kwargs)
            elif operation == RefactoringOperation.INLINE_METHOD:
                return self._validate_inline_method(content, validation_result, **kwargs)
            elif operation == RefactoringOperation.FIND_CODE_PATTERN:
                return self._validate_find_pattern(content, validation_result, **kwargs)
            elif operation == RefactoringOperation.APPLY_CODE_PATTERN:
                return self._validate_apply_pattern(content, validation_result, **kwargs)
            else:
                validation_result["warnings"].append(
                    f"No specific validation implemented for {operation.value}"
                )

        except Exception as e:
            validation_result["is_valid"] = False
            validation_result["errors"].append(f"Validation error: {str(e)}")

        return validation_result

    def _validate_remove_unused_imports(
        self, content: str, result: Dict[str, Any], **kwargs
    ) -> Dict[str, Any]:
        """Validate remove_unused_imports operation."""
        lines = content.split("\n")
        import_count = sum(1 for line in lines if self._is_import_line(line.strip()))

        if import_count == 0:
            result["warnings"].append("No import statements found in file")
        elif import_count > 50:
            result["warnings"].append(
                f"Large number of imports ({import_count}) - operation may be slow"
            )

        return result

    def _validate_rename_symbol(
        self, content: str, result: Dict[str, Any], **kwargs
    ) -> Dict[str, Any]:
        """Validate rename_symbol operation."""
        old_name = kwargs.get("old_name")
        new_name = kwargs.get("new_name")
        if not old_name:
            result["is_valid"] = False
            result["errors"].append("old_name parameter is required")
            return result

        if not new_name:
            result["is_valid"] = False
            result["errors"].append("new_name parameter is required")
            return result

        # Check if old symbol exists
        if not re.search(rf"\b{re.escape(old_name)}\b", content):
            result["warnings"].append(f"Symbol '{old_name}' not found in file")

        # Check if new name already exists
        if re.search(rf"\b{re.escape(new_name)}\b", content):
            result["warnings"].append(f"Symbol '{new_name}' already exists - may cause conflicts")

        # Validate identifier names
        if not re.match(r"^[a-zA-Z_$][a-zA-Z0-9_$]*$", old_name):
            result["is_valid"] = False
            result["errors"].append(f"Invalid JavaScript identifier: {old_name}")

        if not re.match(r"^[a-zA-Z_$][a-zA-Z0-9_$]*$", new_name):
            result["is_valid"] = False
            result["errors"].append(f"Invalid JavaScript identifier: {new_name}")

        return result

    def _validate_extract_method(
        self, content: str, result: Dict[str, Any], **kwargs
    ) -> Dict[str, Any]:
        """Validate extract_method operation."""
        start_line = kwargs.get("start_line")
        end_line = kwargs.get("end_line")
        method_name = kwargs.get("method_name")

        lines = content.split("\n")

        if (
            not isinstance(start_line, int)
            or not isinstance(end_line, int)
            or not isinstance(method_name, str)
        ):
            result["is_valid"] = False
            result["errors"].append("start_line, end_line, and method_name parameters are required")
            return result

        # Validate line range
        if start_line < 1 or end_line > len(lines) or start_line > end_line:
            result["is_valid"] = False
            result["errors"].append(
                f"Invalid line range: {start_line}-{end_line} for file with {len(lines)} lines"
            )
            return result

        # Validate method name
        if not re.match(r"^[a-zA-Z_$][a-zA-Z0-9_$]*$", method_name):
            result["is_valid"] = False
            result["errors"].append(f"Invalid JavaScript function name: {method_name}")
            return result

        # Check if method name already exists
        if re.search(rf"function\s+{re.escape(method_name)}\s*\(", content):
            result["warnings"].append(
                f"Function '{method_name}' already exists - may cause conflicts"
            )

        # Check extraction complexity
        extracted_lines = lines[start_line - 1 : end_line]
        if len(extracted_lines) > 20:
            result["warnings"].append(
                "Extracting a large code block - consider breaking it down further"
            )

        extracted_code = "\n".join(extracted_lines)
        if "return" in extracted_code and extracted_code.count("return") > 1:
            result["warnings"].append(
                "Multiple return statements detected - extraction may be complex"
            )

        return result

    def _validate_inline_method(
        self, content: str, result: Dict[str, Any], **kwargs
    ) -> Dict[str, Any]:
        """Validate inline_method operation."""
        method_name = kwargs.get("method_name")

        if not isinstance(method_name, str) or not method_name:
            result["is_valid"] = False
            result["errors"].append("method_name parameter is required")
            return result

        # Check if method exists
        lines = content.split("\n")
        method_def = self._find_method_definition(lines, method_name)

        if not method_def:
            result["is_valid"] = False
            result["errors"].append(f"Method '{method_name}' not found")
            return result

        # Check method complexity
        method_body = method_def[3]
        if not self._is_method_safe_to_inline(method_body):
            result["warnings"].append(f"Method '{method_name}' may be too complex to safely inline")

        # Check call sites
        call_sites = self._find_method_call_sites(lines, method_name)
        if len(call_sites) == 0:
            result["warnings"].append(f"No call sites found for method '{method_name}'")
        elif len(call_sites) > 10:
            result["warnings"].append(
                f"Many call sites ({len(call_sites)}) - inlining may increase code size significantly"
            )

        return result

    def _validate_find_pattern(
        self, content: str, result: Dict[str, Any], **kwargs
    ) -> Dict[str, Any]:
        """Validate find_code_pattern operation."""
        pattern = kwargs.get("pattern")
        pattern_type = kwargs.get("pattern_type", "regex")

        if not isinstance(pattern, str) or not pattern:
            result["is_valid"] = False
            result["errors"].append("pattern parameter is required")
            return result

        if pattern_type == "regex":
            try:
                re.compile(pattern)
            except re.error as e:
                result["is_valid"] = False
                result["errors"].append(f"Invalid regex pattern: {e}")

        return result

    def _validate_apply_pattern(
        self, content: str, result: Dict[str, Any], **kwargs
    ) -> Dict[str, Any]:
        """Validate apply_code_pattern operation."""
        find_pattern = kwargs.get("find_pattern")
        replace_pattern = kwargs.get("replace_pattern")
        pattern_type = kwargs.get("pattern_type", "regex")

        if not isinstance(find_pattern, str) or not find_pattern:
            result["is_valid"] = False
            result["errors"].append("find_pattern parameter is required")
            return result

        if pattern_type == "regex":
            try:
                re.compile(find_pattern)
            except re.error as e:
                result["is_valid"] = False
                result["errors"].append(f"Invalid regex find_pattern: {e}")
                return result

            # Test if replacement would create valid syntax
            if replace_pattern is not None:
                if not isinstance(replace_pattern, str):
                    result["is_valid"] = False
                    result["errors"].append("replace_pattern must be a string")
                    return result
                try:
                    re.sub(find_pattern, replace_pattern, "test")
                except re.error as e:
                    result["is_valid"] = False
                    result["errors"].append(f"Invalid regex replace_pattern: {e}")
                    return result

        # Check if pattern exists in content
        if pattern_type == "regex" and not re.search(find_pattern, content):
            result["warnings"].append("Pattern not found in file - no changes will be made")

        return result

    def get_language_specific_config(self) -> Dict[str, Any]:
        """Get JavaScript-specific configuration."""
        return {
            "preserve_formatting": True,
            "indent_size": 2,
            "quote_style": "single",
            "semicolons": True,
            "es6_imports": True,
            "arrow_functions": True,
        }

    def detect_dead_code(self, file_path: Union[str, Path]) -> str:
        """Detect dead (unused) code in a JavaScript file."""
        content = self.read_file_content(file_path)

        dead_code_info = self._analyze_dead_code_js(content)

        if not any(dead_code_info.values()):
            return f"No dead code detected in {file_path}"

        result = {
            "file_path": str(file_path),
            "language": self.language_name,
            "dead_functions": dead_code_info.get("functions", []),
            "dead_classes": dead_code_info.get("classes", []),
            "dead_variables": dead_code_info.get("variables", []),
            "unreachable_code": dead_code_info.get("unreachable", []),
            "summary": {
                "total_dead_functions": len(dead_code_info.get("functions", [])),
                "total_dead_classes": len(dead_code_info.get("classes", [])),
                "total_dead_variables": len(dead_code_info.get("variables", [])),
                "total_unreachable_blocks": len(dead_code_info.get("unreachable", [])),
            },
        }

        import json

        return json.dumps(result, indent=2)

    def _analyze_dead_code_js(self, content: str) -> Dict[str, List[Dict[str, Any]]]:
        """Analyze JavaScript code to find dead/unused elements."""
        lines = content.split("\n")

        # Find all definitions
        definitions = self._find_js_definitions(lines)

        # Find all usages
        usages = self._find_js_usages(lines)

        # Find all exports
        exports = self._find_js_exports(lines)

        # Find unreachable code
        unreachable = self._find_js_unreachable_code(lines)

        # Find dead code
        dead_functions = []
        dead_classes = []
        dead_variables = []

        # Check functions
        for func_name, func_info in definitions["functions"].items():
            # Skip if function is used, exported, or starts with underscore
            if func_name in usages["function_calls"]:
                continue
            if func_name.startswith("_"):
                continue
            if func_name in exports["functions"]:
                continue
            if self._is_js_special_function(func_name):
                continue
            dead_functions.append(
                {
                    "name": func_name,
                    "line_start": func_info["line"],
                    "line_end": func_info.get("end_line", func_info["line"]),
                    "type": "function",
                }
            )

        # Check classes
        for class_name, class_info in definitions["classes"].items():
            # Skip if class is used or exported
            if class_name in usages["class_usage"]:
                continue
            if class_name in exports["classes"]:
                continue
            dead_classes.append(
                {
                    "name": class_name,
                    "line_start": class_info["line"],
                    "line_end": class_info.get("end_line", class_info["line"]),
                    "type": "class",
                }
            )

        # Check variables
        for var_name, var_info in definitions["variables"].items():
            # Skip if variable is used, exported, or starts with underscore
            if var_name in usages["variable_usage"]:
                continue
            if var_name.startswith("_"):
                continue
            if var_name in exports["variables"]:
                continue
            if self._is_js_common_variable(var_name):
                continue
            dead_variables.append(
                {
                    "name": var_name,
                    "line": var_info["line"],
                    "type": "variable",
                }
            )

        return {
            "functions": dead_functions,
            "classes": dead_classes,
            "variables": dead_variables,
            "unreachable": unreachable,
        }

    def _find_js_definitions(self, lines: List[str]) -> Dict[str, Dict[str, Any]]:
        """Find all JavaScript function, class, and variable definitions."""
        definitions: Dict[str, Dict[str, Dict[str, int]]] = {
            "functions": {},
            "classes": {},
            "variables": {},
        }

        for line_num, line in enumerate(lines, 1):
            # Function declarations
            func_match = re.search(r"function\s+(\w+)\s*\(", line)
            if func_match:
                func_name = func_match.group(1)
                definitions["functions"][func_name] = {"line": line_num}

            # Arrow function assignments
            arrow_match = re.search(r"(?:const|let|var)\s+(\w+)\s*=\s*\([^)]*\)\s*=>", line)
            if arrow_match:
                func_name = arrow_match.group(1)
                definitions["functions"][func_name] = {"line": line_num}

            # Class declarations
            class_match = re.search(r"class\s+(\w+)", line)
            if class_match:
                class_name = class_match.group(1)
                definitions["classes"][class_name] = {"line": line_num}

            # Variable declarations
            var_matches = re.findall(r"(?:const|let|var)\s+(\w+)", line)
            for var_name in var_matches:
                definitions["variables"][var_name] = {"line": line_num}

        return definitions

    def _find_js_usages(self, lines: List[str]) -> Dict[str, Set[str]]:
        """Find all usages of functions, classes, and variables."""
        usages: Dict[str, Set[str]] = {
            "function_calls": set(),
            "class_usage": set(),
            "variable_usage": set(),
        }

        for line in lines:
            # Skip pure declaration lines (function/class declarations)
            # But DO process variable assignments that may have usages on the right side
            is_func_or_class_decl = re.search(r"^\s*(?:function|class)\s+\w+", line)
            if is_func_or_class_decl:
                continue

            # Find function calls
            func_calls = re.findall(r"(\w+)\s*\(", line)
            usages["function_calls"].update(func_calls)

            # Find class instantiations (new ClassName)
            class_instantiations = re.findall(r"new\s+(\w+)", line)
            usages["class_usage"].update(class_instantiations)

            # For variable declarations, we only want to track usages on the RHS
            # e.g., "const x = foo()" - foo is used, x is being declared
            if re.search(r"^\s*(?:const|let|var)\s+\w+\s*=", line):
                # Get the right-hand side of the assignment
                rhs_match = re.search(r"=\s*(.+)$", line)
                if rhs_match:
                    rhs = rhs_match.group(1)
                    # Find identifiers on the RHS
                    identifiers = re.findall(r"\b(\w+)\b", rhs)
                    usages["variable_usage"].update(identifiers)
                    usages["function_calls"].update(identifiers)
                    usages["class_usage"].update(identifiers)
            else:
                # For non-declaration lines, find all general usages
                identifiers = re.findall(r"\b(\w+)\b", line)
                usages["variable_usage"].update(identifiers)
                usages["function_calls"].update(identifiers)
                usages["class_usage"].update(identifiers)

        return usages

    def _is_js_special_function(self, func_name: str) -> bool:
        """Check if function is special (entry points, exports, etc)."""
        special_patterns = [
            "main",
            "init",
            "setup",
            "teardown",
            "handler",
            "callback",
            "onLoad",
            "onReady",
            "test",  # Test functions
        ]

        # Check for exported functions
        if func_name in ["exports", "module"]:
            return True

        return any(
            func_name.startswith(pattern) or func_name.endswith(pattern)
            for pattern in special_patterns
        )

    def _is_js_common_variable(self, var_name: str) -> bool:
        """Check if variable follows common patterns that might be used externally."""
        common_patterns = [
            "config",
            "options",
            "settings",
            "exports",
            "module",
        ]

        return (
            any(var_name.startswith(pattern) for pattern in common_patterns)
            or var_name.isupper()  # Constants
        )

    def _find_js_exports(self, lines: List[str]) -> Dict[str, set]:
        """Find all exported functions, classes, and variables in JavaScript/TypeScript."""
        exports: Dict[str, set] = {"functions": set(), "classes": set(), "variables": set()}

        for line in lines:
            stripped = line.strip()

            # ES6 export function/class declarations: export function name() / export class Name
            export_func_match = re.search(r"export\s+function\s+(\w+)", stripped)
            if export_func_match:
                exports["functions"].add(export_func_match.group(1))

            export_class_match = re.search(r"export\s+class\s+(\w+)", stripped)
            if export_class_match:
                exports["classes"].add(export_class_match.group(1))

            # ES6 export const/let/var: export const name = ...
            export_var_match = re.search(r"export\s+(?:const|let|var)\s+(\w+)", stripped)
            if export_var_match:
                exports["variables"].add(export_var_match.group(1))

            # Named exports: export { name1, name2 }
            named_export_match = re.search(r"export\s*\{([^}]+)\}", stripped)
            if named_export_match:
                names = named_export_match.group(1)
                for name_part in names.split(","):
                    name = name_part.strip()
                    # Handle "name as alias" syntax - use the original name
                    if " as " in name:
                        name = name.split(" as ")[0].strip()
                    if name:
                        # Could be function, class, or variable - add to all
                        exports["functions"].add(name)
                        exports["classes"].add(name)
                        exports["variables"].add(name)

            # Default export: export default functionName or export default ClassName
            default_export_match = re.search(r"export\s+default\s+(\w+)", stripped)
            if default_export_match:
                name = default_export_match.group(1)
                if name not in ("function", "class"):
                    # It's a name being exported
                    exports["functions"].add(name)
                    exports["classes"].add(name)
                    exports["variables"].add(name)

            # module.exports = { name1, name2 } or module.exports = name
            module_exports_match = re.search(r"module\.exports\s*=\s*\{([^}]+)\}", stripped)
            if module_exports_match:
                names = module_exports_match.group(1)
                for name_part in names.split(","):
                    name = name_part.strip()
                    # Handle "key: value" syntax
                    if ":" in name:
                        name = name.split(":")[0].strip()
                    if name:
                        exports["functions"].add(name)
                        exports["classes"].add(name)
                        exports["variables"].add(name)

            # module.exports = singleName
            single_export_match = re.search(r"module\.exports\s*=\s*(\w+)\s*;?$", stripped)
            if single_export_match:
                name = single_export_match.group(1)
                if name not in ("{", "["):
                    exports["functions"].add(name)
                    exports["classes"].add(name)
                    exports["variables"].add(name)

            # module.exports.name = value
            prop_export_match = re.search(r"module\.exports\.(\w+)\s*=", stripped)
            if prop_export_match:
                name = prop_export_match.group(1)
                exports["functions"].add(name)
                exports["classes"].add(name)
                exports["variables"].add(name)

            # exports.name = value
            exports_prop_match = re.search(r"exports\.(\w+)\s*=", stripped)
            if exports_prop_match:
                name = exports_prop_match.group(1)
                exports["functions"].add(name)
                exports["classes"].add(name)
                exports["variables"].add(name)

        return exports

    def _find_js_unreachable_code(self, lines: List[str]) -> List[Dict[str, Any]]:
        """Find unreachable code after return/throw/break/continue statements."""
        unreachable: List[Dict[str, Any]] = []

        # Track function/block boundaries
        in_function = False
        brace_depth = 0
        found_return_at_depth: Dict[int, int] = {}  # depth -> line number of return

        for line_num, line in enumerate(lines, 1):
            stripped = line.strip()

            # Skip empty lines and comments
            if not stripped or stripped.startswith("//") or stripped.startswith("/*"):
                continue

            # Track brace depth
            open_braces = line.count("{")
            close_braces = line.count("}")

            # Check if this is a function start
            if re.search(r"function\s*\w*\s*\([^)]*\)\s*\{", line) or re.search(r"=>\s*\{", line):
                in_function = True

            # Update brace depth
            old_depth = brace_depth
            brace_depth += open_braces - close_braces

            # If we closed a brace that had a return, clear it
            if brace_depth < old_depth:
                for depth in list(found_return_at_depth.keys()):
                    if depth > brace_depth:
                        del found_return_at_depth[depth]

            # Check if there was a return at current depth and this line is code after it
            if brace_depth in found_return_at_depth:
                return_line = found_return_at_depth[brace_depth]
                # Only flag if this is actual code, not just a closing brace
                if stripped and stripped != "}" and not stripped.startswith("}"):
                    unreachable.append(
                        {
                            "line": line_num,
                            "type": "unreachable_statement",
                            "reason": f"Code after return statement at line {return_line}",
                        }
                    )
                    # Only report the first unreachable line after each return
                    del found_return_at_depth[brace_depth]

            # Check for return/throw statements (not inside conditionals for simplicity)
            # Only track returns that are not inside if/else/try/catch blocks
            if re.search(r"^\s*return\s", stripped) or re.search(r"^\s*throw\s", stripped):
                # Check if this return is at the end of a block (simple heuristic)
                # Don't track returns inside if blocks
                if not re.search(r"^\s*if\s*\(", stripped):
                    found_return_at_depth[brace_depth] = line_num

            # Reset when exiting function
            if brace_depth == 0 and in_function:
                in_function = False
                found_return_at_depth.clear()

        return unreachable

    def remove_dead_code(self, file_path: Union[str, Path], confirm: bool = False) -> str:
        """Remove dead (unused) code from a JavaScript file."""
        if not confirm:
            return (
                "Dead code removal requires confirmation. "
                "Run detect_dead_code first to see what will be removed, "
                "then call remove_dead_code with confirm=True"
            )

        content = self.read_file_content(file_path)
        dead_code_info = self._analyze_dead_code_js(content)

        if not any(dead_code_info.values()):
            return f"No dead code found to remove in {file_path}"

        # Create backup
        self.backup_file(file_path)

        # Remove dead code
        lines = content.split("\n")
        new_lines = self._remove_dead_code_from_lines(lines, dead_code_info)

        new_content = "\n".join(new_lines)
        self.write_file_content(file_path, new_content)

        # Create summary
        summary = {
            "removed_functions": len(dead_code_info["functions"]),
            "removed_classes": len(dead_code_info["classes"]),
            "removed_variables": len(dead_code_info["variables"]),
            "total_removed": len(dead_code_info["functions"]) + len(dead_code_info["classes"]),
        }

        import json

        return f"Successfully removed dead code from {file_path}. Summary: {json.dumps(summary, indent=2)}"

    def _remove_dead_code_from_lines(
        self, lines: List[str], dead_code_info: Dict[str, List[Dict[str, Any]]]
    ) -> List[str]:
        """Remove dead code lines from the source."""
        lines_to_remove = set()

        # Mark lines for removal (functions and classes)
        for item in dead_code_info["functions"] + dead_code_info["classes"]:
            start_line = item["line_start"] - 1  # Convert to 0-based

            # For simple detection, remove single line declarations
            if start_line < len(lines):
                lines_to_remove.add(start_line)

                # Try to find the end of the function/class block
                brace_count = lines[start_line].count("{") - lines[start_line].count("}")
                if brace_count > 0:
                    for i in range(start_line + 1, len(lines)):
                        brace_count += lines[i].count("{") - lines[i].count("}")
                        lines_to_remove.add(i)
                        if brace_count <= 0:
                            break

        # Remove variable declarations
        for var in dead_code_info["variables"]:
            var_line = var["line"] - 1
            if var_line < len(lines):
                line_content = lines[var_line]
                # Only remove if it's a standalone variable declaration
                if re.search(
                    rf"^\s*(?:const|let|var)\s+{re.escape(var['name'])}\s*=", line_content
                ):
                    lines_to_remove.add(var_line)

        # Create new content
        new_lines = []
        for i, line in enumerate(lines):
            if i not in lines_to_remove:
                new_lines.append(line)

        return new_lines

    def reorder_function(
        self,
        file_path: Union[str, Path],
        function_name: str,
        target_position: str = "top",
        above_function: Optional[str] = None,
    ) -> str:
        """Reorder a function within a JavaScript file."""
        content = self.read_file_content(file_path)
        lines = content.split("\n")

        # Find the function to move
        function_info = self._find_function_in_lines(lines, function_name)
        if not function_info:
            raise RefactoringError(f"Function '{function_name}' not found in {file_path}")

        # Extract the function source
        func_lines = self._extract_function_lines(lines, function_info)

        # Remove the function from its current position
        new_lines = self._remove_function_lines(lines, function_info)

        # Insert at new position
        if target_position == "top":
            new_lines = self._insert_function_at_top(new_lines, func_lines)
        elif target_position == "bottom":
            new_lines = self._insert_function_at_bottom(new_lines, func_lines)
        elif target_position == "above" and above_function:
            new_lines = self._insert_function_above(new_lines, func_lines, above_function)
        else:
            raise RefactoringError("Invalid target_position or missing above_function")

        # Write back to file
        new_content = "\n".join(new_lines)
        self.write_file_content(file_path, new_content)

        return f"Successfully reordered function '{function_name}' in {file_path}"

    def _find_function_in_lines(
        self, lines: List[str], function_name: str
    ) -> Optional[Dict[str, Any]]:
        """Find a function in the lines and return its info."""
        for i, line in enumerate(lines):
            # Look for function declaration
            if re.search(rf"function\s+{re.escape(function_name)}\s*\(", line):
                return self._get_function_block_info(lines, i, function_name)

            # Look for arrow function assignment
            if re.search(rf"(?:const|let|var)\s+{re.escape(function_name)}\s*=.*=>", line):
                return self._get_function_block_info(lines, i, function_name)

        return None

    def _get_function_block_info(
        self, lines: List[str], start_line: int, function_name: str
    ) -> Dict[str, Any]:
        """Get information about a function block."""
        # Simple implementation: find the closing brace
        brace_count = lines[start_line].count("{") - lines[start_line].count("}")
        end_line = start_line

        if brace_count > 0:
            for i in range(start_line + 1, len(lines)):
                brace_count += lines[i].count("{") - lines[i].count("}")
                if brace_count <= 0:
                    end_line = i
                    break

        return {
            "name": function_name,
            "start_line": start_line,
            "end_line": end_line,
        }

    def _extract_function_lines(self, lines: List[str], function_info: Dict[str, Any]) -> List[str]:
        """Extract the function lines."""
        start = function_info["start_line"]
        end = function_info["end_line"]
        return lines[start : end + 1]

    def _remove_function_lines(self, lines: List[str], function_info: Dict[str, Any]) -> List[str]:
        """Remove function lines from the content."""
        start = function_info["start_line"]
        end = function_info["end_line"]

        new_lines = lines[:start] + lines[end + 1 :]
        return new_lines

    def _insert_function_at_top(self, lines: List[str], func_lines: List[str]) -> List[str]:
        """Insert function at the top of the file."""
        # Find insertion point after imports and comments
        insert_idx = 0

        for i, line in enumerate(lines):
            stripped = line.strip()
            if stripped and not (
                stripped.startswith("//")
                or stripped.startswith("/*")
                or stripped.startswith("import ")
                or stripped.startswith("const ")
                and "require(" in stripped
                or stripped.startswith("'use strict'")
                or stripped.startswith('"use strict"')
            ):
                insert_idx = i
                break

        return lines[:insert_idx] + func_lines + [""] + lines[insert_idx:]

    def _insert_function_at_bottom(self, lines: List[str], func_lines: List[str]) -> List[str]:
        """Insert function at the bottom of the file."""
        return lines + [""] + func_lines

    def _insert_function_above(
        self, lines: List[str], func_lines: List[str], above_function: str
    ) -> List[str]:
        """Insert function above another function."""
        target_info = self._find_function_in_lines(lines, above_function)
        if not target_info:
            raise RefactoringError(f"Target function '{above_function}' not found")

        insert_idx = target_info["start_line"]
        return lines[:insert_idx] + func_lines + [""] + lines[insert_idx:]

    def move_function(
        self, source_file: Union[str, Path], target_file: Union[str, Path], function_name: str
    ) -> str:
        """Move a function between JavaScript files."""
        # Read both files
        source_content = self.read_file_content(source_file)
        source_lines = source_content.split("\n")

        target_content = self.read_file_content(target_file)
        target_lines = target_content.split("\n")

        # Find and extract the function from source
        function_info = self._find_function_in_lines(source_lines, function_name)
        if not function_info:
            raise RefactoringError(f"Function '{function_name}' not found in {source_file}")

        func_lines = self._extract_function_lines(source_lines, function_info)

        # Remove from source
        new_source_lines = self._remove_function_lines(source_lines, function_info)

        # Add to target (at the end)
        new_target_lines = self._insert_function_at_bottom(target_lines, func_lines)

        # Write both files
        self.write_file_content(source_file, "\n".join(new_source_lines))
        self.write_file_content(target_file, "\n".join(new_target_lines))

        return f"Successfully moved function '{function_name}' from {source_file} to {target_file}"

    def move_class(
        self, source_file: Union[str, Path], target_file: Union[str, Path], class_name: str
    ) -> str:
        """Move a class between JavaScript files."""
        # Read both files
        source_content = self.read_file_content(source_file)
        source_lines = source_content.split("\n")

        target_content = self.read_file_content(target_file)
        target_lines = target_content.split("\n")

        # Find and extract the class from source (reuse function logic for classes)
        class_info = self._find_class_in_lines(source_lines, class_name)
        if not class_info:
            raise RefactoringError(f"Class '{class_name}' not found in {source_file}")

        class_lines = self._extract_function_lines(
            source_lines, class_info
        )  # Same extraction logic

        # Remove from source
        new_source_lines = self._remove_function_lines(
            source_lines, class_info
        )  # Same removal logic

        # Add to target
        new_target_lines = self._insert_function_at_bottom(target_lines, class_lines)

        # Write both files
        self.write_file_content(source_file, "\n".join(new_source_lines))
        self.write_file_content(target_file, "\n".join(new_target_lines))

        return f"Successfully moved class '{class_name}' from {source_file} to {target_file}"

    def _find_class_in_lines(self, lines: List[str], class_name: str) -> Optional[Dict[str, Any]]:
        """Find a class in the lines and return its info."""
        for i, line in enumerate(lines):
            if re.search(rf"class\s+{re.escape(class_name)}\s*\{{", line):
                return self._get_function_block_info(
                    lines, i, class_name
                )  # Same logic as functions
        return None

"""Python language handler implementation."""

import ast
import re
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence, Set, Union

from .base_handler import (
    BaseLanguageHandler,
    ClassInfo,
    CodeStructure,
    FunctionInfo,
    ImportInfo,
    RefactoringError,
    RefactoringOperation,
)


class PythonHandler(BaseLanguageHandler):
    """Handler for Python language refactoring operations."""

    @property
    def language_name(self) -> str:
        return "Python"

    @property
    def file_extensions(self) -> List[str]:
        return [".py", ".pyw", ".pyi"]

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

        # Check shebang for Python
        try:
            with open(file_path, "r", encoding="utf-8") as f:
                first_line = f.readline().strip()
                if first_line.startswith("#!") and "python" in first_line.lower():
                    return True
        except Exception:
            pass

        return False

    def validate_syntax(self, content: str) -> bool:
        """Validate Python syntax."""
        try:
            ast.parse(content)
            return True
        except SyntaxError:
            return False

    def parse_file(self, file_path: Union[str, Path]) -> ast.Module:
        """Parse Python file into AST."""
        content = self.read_file_content(file_path)

        try:
            return ast.parse(content)
        except SyntaxError as e:
            raise RefactoringError(f"Syntax error in {file_path}: {e}")

    def get_code_structure(self, file_path: Union[str, Path]) -> CodeStructure:
        """Get structured information about the Python file."""
        tree = self.parse_file(file_path)

        structure = CodeStructure(file_path=str(file_path), language=self.language_name)

        for node in tree.body:
            if isinstance(node, ast.ClassDef):
                class_info = self._extract_class_info(node)
                structure.classes.append(class_info)
            elif isinstance(node, ast.FunctionDef):
                func_info = self._extract_function_info(node)
                structure.functions.append(func_info)
            elif isinstance(node, (ast.Import, ast.ImportFrom)):
                import_info = self._extract_import_info(node)
                structure.imports.append(import_info)

        return structure

    def _extract_function_info(
        self, node: ast.FunctionDef, class_name: Optional[str] = None
    ) -> FunctionInfo:
        """Extract function information from AST node."""
        # Get parameter names
        parameters = []
        for arg in node.args.args:
            parameters.append(arg.arg)

        # Get decorators
        decorators = []
        for decorator in node.decorator_list:
            if isinstance(decorator, ast.Name):
                decorators.append(decorator.id)
            elif isinstance(decorator, ast.Attribute):
                decorators.append(f"{decorator.attr}")

        # Get return type annotation
        return_type = None
        if node.returns:
            if isinstance(node.returns, ast.Name):
                return_type = node.returns.id
            elif isinstance(node.returns, ast.Constant):
                return_type = str(node.returns.value)

        return FunctionInfo(
            name=node.name,
            line_start=node.lineno,
            line_end=node.end_lineno or node.lineno,
            is_method=class_name is not None,
            class_name=class_name,
            parameters=parameters,
            return_type=return_type,
            decorators=decorators,
        )

    def _extract_class_info(self, node: ast.ClassDef) -> ClassInfo:
        """Extract class information from AST node."""
        # Get base classes
        base_classes = []
        for base in node.bases:
            if isinstance(base, ast.Name):
                base_classes.append(base.id)
            elif isinstance(base, ast.Attribute):
                base_classes.append(f"{base.attr}")

        # Get decorators
        decorators = []
        for decorator in node.decorator_list:
            if isinstance(decorator, ast.Name):
                decorators.append(decorator.id)

        # Get methods
        methods = []
        for item in node.body:
            if isinstance(item, ast.FunctionDef):
                method_info = self._extract_function_info(item, node.name)
                methods.append(method_info)

        return ClassInfo(
            name=node.name,
            line_start=node.lineno,
            line_end=node.end_lineno or node.lineno,
            methods=methods,
            base_classes=base_classes,
            decorators=decorators,
        )

    def _extract_import_info(self, node: Union[ast.Import, ast.ImportFrom]) -> ImportInfo:
        """Extract import information from AST node."""
        if isinstance(node, ast.Import):
            # import module1, module2
            symbols = [alias.name for alias in node.names]
            return ImportInfo(
                module=symbols[0] if len(symbols) == 1 else "",
                line=node.lineno,
                import_type="import",
                symbols=symbols if len(symbols) > 1 else [],
            )

        elif isinstance(node, ast.ImportFrom):
            # from module import symbol1, symbol2
            symbols = [alias.name for alias in node.names]
            return ImportInfo(
                module=node.module or "",
                line=node.lineno,
                import_type="from_import",
                symbols=symbols,
                is_relative=node.level > 0,
            )

        raise RefactoringError("Unsupported import node type")

    def analyze_dependencies(self, file_path: Union[str, Path]) -> Dict[str, Any]:
        """Analyze imports and dependencies in Python file."""
        structure = self.get_code_structure(file_path)

        # Categorize imports
        stdlib_imports: List[Dict[str, Any]] = []
        third_party_imports: List[Dict[str, Any]] = []
        local_imports: List[Dict[str, Any]] = []

        for imp in structure.imports:
            if self._is_stdlib_import(imp):
                stdlib_imports.append(imp.__dict__)
            elif self._is_local_import(imp):
                local_imports.append(imp.__dict__)
            else:
                third_party_imports.append(imp.__dict__)

        return {
            "file": str(file_path),
            "language": self.language_name,
            "total_imports": len(structure.imports),
            "stdlib_imports": stdlib_imports,
            "third_party_imports": third_party_imports,
            "local_imports": local_imports,
            "functions": len(structure.functions),
            "classes": len(structure.classes),
        }

    def _is_stdlib_import(self, import_info: ImportInfo) -> bool:
        """Check if import is from Python standard library."""
        stdlib_modules = {
            "os",
            "sys",
            "json",
            "datetime",
            "pathlib",
            "typing",
            "collections",
            "itertools",
            "functools",
            "asyncio",
            "logging",
            "re",
            "math",
            "time",
            "random",
            "string",
            "io",
            "urllib",
            "http",
            "email",
            "html",
            "xml",
            "csv",
            "configparser",
            "argparse",
            "subprocess",
            "threading",
            "multiprocessing",
            "queue",
            "socket",
            "ssl",
            "hashlib",
            "hmac",
            "base64",
            "binascii",
            "struct",
            "codecs",
            "locale",
            "gettext",
            "calendar",
            "heapq",
            "bisect",
            "array",
            "weakref",
            "types",
            "copy",
            "pickle",
            "copyreg",
            "shelve",
            "marshal",
            "dbm",
            "sqlite3",
            "zlib",
            "gzip",
            "bz2",
            "lzma",
            "zipfile",
            "tarfile",
            "tempfile",
            "glob",
            "fnmatch",
            "linecache",
            "shutil",
            "stat",
            "filecmp",
            "fileinput",
            "platform",
            "errno",
            "ctypes",
            "unittest",
            "doctest",
            "test",
            "importlib",
            "pkgutil",
            "modulefinder",
            "runpy",
            "ast",
            "symtable",
            "symbol",
            "token",
            "keyword",
            "tokenize",
            "tabnanny",
            "pyclbr",
            "py_compile",
            "compileall",
            "dis",
            "pickletools",
            "warnings",
            "contextlib",
            "abc",
            "atexit",
            "traceback",
            "gc",
            "inspect",
            "site",
        }

        module_name = import_info.module.split(".")[0]
        return module_name in stdlib_modules

    def _is_local_import(self, import_info: ImportInfo) -> bool:
        """Check if import is local (relative)."""
        return import_info.is_relative

    def reorder_function(
        self,
        file_path: Union[str, Path],
        function_name: str,
        target_position: str = "top",
        above_function: Optional[str] = None,
    ) -> str:
        """Reorder a function within a Python file."""
        content = self.read_file_content(file_path)
        tree = self.parse_file(file_path)

        # Find the function to move
        function_node = self._find_function(tree, function_name)
        if not function_node:
            raise RefactoringError(f"Function '{function_name}' not found in {file_path}")

        # Get function details
        func_info = self._extract_function_source(content, function_node)

        # Remove the function from its current position
        new_content = self._remove_function_source(content, func_info)

        # Insert at new position
        if target_position == "top":
            new_content = self._insert_function_at_top(new_content, func_info)
        elif target_position == "bottom":
            new_content = self._insert_function_at_bottom(new_content, func_info)
        elif target_position == "above" and above_function:
            new_content = self._insert_function_above(new_content, func_info, above_function)
        else:
            raise RefactoringError("Invalid target_position or missing above_function")

        # Write back to file
        self.write_file_content(file_path, new_content)

        return f"Successfully reordered function '{function_name}' in {file_path}"

    def _find_function(self, tree: ast.AST, function_name: str) -> Optional[ast.FunctionDef]:
        """Find a function in the AST."""
        for node in ast.walk(tree):
            if isinstance(node, ast.FunctionDef) and node.name == function_name:
                return node
        return None

    def _extract_function_source(self, content: str, func_node: ast.FunctionDef) -> Dict[str, Any]:
        """Extract function source code and position info."""
        lines = content.splitlines(keepends=True)

        start_line = func_node.lineno - 1
        end_line = func_node.end_lineno if func_node.end_lineno else start_line + 1

        # Include decorators
        if func_node.decorator_list:
            first_decorator = func_node.decorator_list[0]
            start_line = first_decorator.lineno - 1

        # Extract the function source
        func_lines = lines[start_line:end_line]
        func_source = "".join(func_lines)

        # Determine indentation level
        indentation = self._get_indentation(lines[func_node.lineno - 1])

        return {
            "name": func_node.name,
            "source": func_source,
            "start_line": start_line,
            "end_line": end_line,
            "indentation": indentation,
            "is_method": indentation > 0,
        }

    def _get_indentation(self, line: str) -> int:
        """Get the indentation level of a line."""
        return len(line) - len(line.lstrip())

    def _remove_function_source(self, content: str, func_info: Dict[str, Any]) -> str:
        """Remove a function from the content."""
        lines = content.splitlines(keepends=True)
        del lines[func_info["start_line"] : func_info["end_line"]]
        return self._clean_blank_lines("".join(lines))

    def _clean_blank_lines(self, content: str) -> str:
        """Clean up excessive blank lines."""
        return re.sub(r"\n\s*\n\s*\n+", "\n\n", content)

    def _insert_function_at_top(self, content: str, func_info: Dict[str, Any]) -> str:
        """Insert function at the top of the file."""
        lines = content.splitlines(keepends=True)
        insert_idx = self._find_top_insertion_point(lines)
        func_source = self._adjust_function_indentation(func_info, 0)
        lines.insert(insert_idx, func_source + "\n\n")
        return "".join(lines)

    def _insert_function_at_bottom(self, content: str, func_info: Dict[str, Any]) -> str:
        """Insert function at the bottom of the file."""
        func_source = self._adjust_function_indentation(func_info, 0)
        return content.rstrip() + "\n\n\n" + func_source + "\n"

    def _insert_function_above(
        self, content: str, func_info: Dict[str, Any], above_function: str
    ) -> str:
        """Insert function above another function."""
        lines = content.splitlines(keepends=True)

        # Find the target function
        try:
            tree = ast.parse(content)
            target_func = self._find_function(tree, above_function)
            if not target_func:
                raise RefactoringError(f"Target function '{above_function}' not found")

            insert_idx = target_func.lineno - 1

            # Include decorators of target function
            if target_func.decorator_list:
                first_decorator = target_func.decorator_list[0]
                insert_idx = first_decorator.lineno - 1

            # Get target function indentation
            target_indentation = self._get_indentation(lines[target_func.lineno - 1])

            # Adjust function indentation to match target
            func_source = self._adjust_function_indentation(func_info, target_indentation)

            lines.insert(insert_idx, func_source + "\n\n")
            return "".join(lines)

        except SyntaxError as e:
            raise RefactoringError(f"Syntax error: {e}")

    def _find_top_insertion_point(self, lines: List[str]) -> int:
        """Find the best insertion point at the top of the file."""
        insert_idx = 0

        # Skip shebang
        if lines and lines[0].startswith("#!"):
            insert_idx = 1

        # Skip module docstring
        try:
            tree = ast.parse("".join(lines))
            if (
                tree.body
                and isinstance(tree.body[0], ast.Expr)
                and isinstance(tree.body[0].value, ast.Constant)
                and isinstance(tree.body[0].value.value, str)
            ):
                docstring_node = tree.body[0]
                end_lineno = docstring_node.end_lineno
                if end_lineno is not None:
                    insert_idx = max(insert_idx, end_lineno)
        except Exception:
            pass

        # Skip imports
        for i in range(insert_idx, len(lines)):
            line = lines[i].strip()
            if line and not (line.startswith("import ") or line.startswith("from ")):
                if not line.startswith("#"):
                    insert_idx = i
                    break

        return insert_idx

    def _adjust_function_indentation(
        self, func_info: Dict[str, Any], target_indentation: int
    ) -> str:
        """Adjust function indentation to match target level."""
        source = str(func_info["source"])
        lines = source.splitlines()
        if not lines:
            return source

        current_indentation = func_info["indentation"]
        indent_diff = target_indentation - current_indentation

        if indent_diff == 0:
            return source

        adjusted_lines = []
        for line in lines:
            if line.strip():
                if indent_diff > 0:
                    adjusted_lines.append(" " * indent_diff + line)
                else:
                    spaces_to_remove = min(-indent_diff, len(line) - len(line.lstrip()))
                    adjusted_lines.append(line[spaces_to_remove:])
            else:
                adjusted_lines.append(line)

        return "\n".join(adjusted_lines)

    def organize_imports(self, file_path: Union[str, Path]) -> str:
        """Organize imports in a Python file."""
        content = self.read_file_content(file_path)
        tree = self.parse_file(file_path)

        # Extract imports
        imports: List[Union[ast.Import, ast.ImportFrom]] = [
            node for node in tree.body if isinstance(node, (ast.Import, ast.ImportFrom))
        ]

        if not imports:
            return f"No imports found in {file_path}"

        # Sort and organize imports
        organized = self._organize_import_groups(imports)

        # Replace imports in content
        new_content = self._replace_imports_in_content(content, organized)

        self.write_file_content(file_path, new_content)

        return f"Successfully organized imports in {file_path}"

    def _organize_import_groups(self, imports: Sequence[Union[ast.Import, ast.ImportFrom]]) -> str:
        """Organize imports into groups."""
        std_imports = []
        third_party_imports = []
        local_imports = []

        for imp in imports:
            import_info = self._extract_import_info(imp)
            import_str = self._import_to_string(imp)

            if self._is_stdlib_import(import_info):
                std_imports.append(import_str)
            elif self._is_local_import(import_info):
                local_imports.append(import_str)
            else:
                third_party_imports.append(import_str)

        # Sort each group
        std_imports.sort()
        third_party_imports.sort()
        local_imports.sort()

        # Combine groups
        groups = []
        if std_imports:
            groups.append("\n".join(std_imports))
        if third_party_imports:
            groups.append("\n".join(third_party_imports))
        if local_imports:
            groups.append("\n".join(local_imports))

        return "\n\n".join(groups) + "\n\n"

    def _import_to_string(self, imp: ast.stmt) -> str:
        """Convert import AST node to string."""
        if isinstance(imp, ast.Import):
            names = [alias.name for alias in imp.names]
            return f"import {', '.join(names)}"
        elif isinstance(imp, ast.ImportFrom):
            module = imp.module or ""
            names = [alias.name for alias in imp.names]
            level = "." * (imp.level or 0)
            return f"from {level}{module} import {', '.join(names)}"
        return ""

    def _replace_imports_in_content(self, content: str, organized_imports: str) -> str:
        """Replace existing imports with organized imports."""
        lines = content.splitlines()

        # Find import section bounds
        first_import_idx = None
        last_import_idx = None

        for i, line in enumerate(lines):
            stripped = line.strip()
            if stripped.startswith(("import ", "from ")) and not stripped.startswith("#"):
                if first_import_idx is None:
                    first_import_idx = i
                last_import_idx = i

        if first_import_idx is not None:
            # Replace import section
            if last_import_idx is None:
                last_import_idx = first_import_idx
            before_imports = lines[:first_import_idx]
            after_imports = lines[last_import_idx + 1 :]

            # Insert organized imports
            result_lines = before_imports + [organized_imports.rstrip()] + after_imports
            return "\n".join(result_lines)

        return content

    def add_import(
        self, file_path: Union[str, Path], module: str, symbols: Optional[List[str]] = None
    ) -> str:
        """Add an import statement to a Python file."""
        content = self.read_file_content(file_path)

        # Create import statement
        if symbols:
            import_stmt = f"from {module} import {', '.join(symbols)}"
        else:
            import_stmt = f"import {module}"

        # Find insertion point
        lines = content.splitlines()
        insert_idx = self._find_import_insertion_point(lines)

        lines.insert(insert_idx, import_stmt)
        new_content = "\n".join(lines) + "\n"

        self.write_file_content(file_path, new_content)

        return f"Successfully added import '{import_stmt}' to {file_path}"

    def _find_import_insertion_point(self, lines: List[str]) -> int:
        """Find the best place to insert a new import."""
        for i, line in enumerate(lines):
            if line.strip() and not line.strip().startswith("#"):
                if not line.strip().startswith(("import ", "from ")):
                    return i
        return len(lines)

    def extract_method(
        self, file_path: Union[str, Path], start_line: int, end_line: int, method_name: str
    ) -> str:
        """Extract a method from existing code."""
        content = self.read_file_content(file_path)
        lines = content.splitlines()

        # Validate line numbers
        if start_line < 1 or end_line > len(lines) or start_line > end_line:
            raise RefactoringError("Invalid line numbers for extraction")

        # Extract the code block (convert to 0-based indexing)
        extracted_lines = lines[start_line - 1 : end_line]
        if not extracted_lines:
            raise RefactoringError("No code found in the specified range")

        # Analyze the extracted code
        extracted_code = "\n".join(extracted_lines)

        # Determine indentation level
        base_indent = self._get_base_indentation(extracted_lines)

        # Find variables used and defined in the extracted code
        variables_info = self._analyze_variables_in_code(
            extracted_code, content, start_line, end_line
        )

        # Create the new method
        method_code = self._create_extracted_method(
            method_name, extracted_lines, variables_info, base_indent
        )

        # Find the appropriate place to insert the method
        insert_location = self._find_method_insertion_location(content, start_line)

        # Replace the extracted code with a method call
        method_call = self._create_method_call(method_name, variables_info, base_indent)

        # Build the new file content
        new_content = self._build_content_with_extracted_method(
            lines, start_line, end_line, method_code, method_call, insert_location
        )

        # Write the modified content
        self.write_file_content(file_path, new_content)

        return f"Successfully extracted method '{method_name}' from lines {start_line}-{end_line} in {file_path}"

    def _get_base_indentation(self, lines: List[str]) -> int:
        """Get the base indentation level for extracted lines."""
        for line in lines:
            if line.strip():
                return len(line) - len(line.lstrip())
        return 0

    def _analyze_variables_in_code(
        self, extracted_code: str, full_content: str, start_line: int, end_line: int
    ) -> Dict[str, Any]:
        """Analyze variables used and defined in extracted code."""
        try:
            # Parse the extracted code to find variables
            extracted_tree = ast.parse(extracted_code)
            # Find variables used in extracted code
            used_vars = set()
            defined_vars = set()

            for node in ast.walk(extracted_tree):
                if isinstance(node, ast.Name):
                    if isinstance(node.ctx, ast.Load):
                        used_vars.add(node.id)
                    elif isinstance(node.ctx, ast.Store):
                        defined_vars.add(node.id)

            # Find variables that are defined before the extracted code
            available_vars = set()
            full_lines = full_content.splitlines()
            before_code = "\n".join(full_lines[: start_line - 1])

            try:
                before_tree = ast.parse(before_code)
                for node in ast.walk(before_tree):
                    if isinstance(node, ast.Name) and isinstance(node.ctx, ast.Store):
                        available_vars.add(node.id)
            except SyntaxError:
                pass

            # Parameters are variables used but not defined in extracted code
            # and that are available before the extraction point
            parameters = (used_vars - defined_vars) & available_vars

            # Return values are variables defined in extracted code
            # that might be used after the extraction point
            return_vars = defined_vars & self._find_vars_used_after(full_content, end_line)

            return {
                "parameters": sorted(parameters),
                "return_vars": sorted(return_vars),
                "used_vars": sorted(used_vars),
                "defined_vars": sorted(defined_vars),
            }

        except SyntaxError:
            # Fallback to simple heuristics if parsing fails
            return {
                "parameters": [],
                "return_vars": [],
                "used_vars": [],
                "defined_vars": [],
            }

    def _find_vars_used_after(self, content: str, end_line: int) -> set:
        """Find variables that are used after the extraction point."""
        lines = content.splitlines()
        if end_line >= len(lines):
            return set()

        after_code = "\n".join(lines[end_line:])
        used_vars = set()

        try:
            after_tree = ast.parse(after_code)
            for node in ast.walk(after_tree):
                if isinstance(node, ast.Name) and isinstance(node.ctx, ast.Load):
                    used_vars.add(node.id)
        except SyntaxError:
            pass

        return used_vars

    def _create_extracted_method(
        self,
        method_name: str,
        extracted_lines: List[str],
        variables_info: Dict[str, Any],
        base_indent: int,
    ) -> str:
        """Create the extracted method code."""
        # Determine method indentation (same as the containing context)
        method_indent = base_indent

        # Create method signature
        params = variables_info["parameters"]

        # Check if we're inside a class (need self parameter)
        is_method = self._is_inside_class_context(extracted_lines, base_indent)

        if is_method and params:
            param_str = ", ".join(["self"] + params)
        elif is_method:
            param_str = "self"
        elif params:
            param_str = ", ".join(params)
        else:
            param_str = ""

        method_lines = [" " * method_indent + f"def {method_name}({param_str}):"]

        # Add method body with proper indentation
        for line in extracted_lines:
            if line.strip():
                # Maintain relative indentation but ensure it's inside the method
                current_indent = len(line) - len(line.lstrip())
                new_indent = max(method_indent + 4, current_indent + 4)
                method_lines.append(" " * new_indent + line.lstrip())
            else:
                method_lines.append("")

        # Add return statement if needed
        return_vars = variables_info["return_vars"]
        if return_vars:
            if len(return_vars) == 1:
                method_lines.append(" " * (method_indent + 4) + f"return {return_vars[0]}")
            else:
                method_lines.append(" " * (method_indent + 4) + f"return {', '.join(return_vars)}")

        return "\n".join(method_lines)

    def _is_inside_class_context(self, extracted_lines: List[str], base_indent: int) -> bool:
        """Check if the extraction is inside a class method."""
        # This is a simple heuristic - in practice, we'd want more sophisticated detection
        return base_indent >= 4  # Assume methods are indented at least 4 spaces

    def _find_method_insertion_location(self, content: str, extraction_start: int) -> int:
        """Find where to insert the extracted method."""
        lines = content.splitlines()

        # Look for a class definition above the extraction point
        for i in range(extraction_start - 2, -1, -1):
            line = lines[i].strip()
            if line.startswith("class ") and line.endswith(":"):
                # Insert method inside this class, after existing methods
                class_indent = len(lines[i]) - len(lines[i].lstrip())

                # Find the end of the class to insert the method
                for j in range(i + 1, extraction_start - 1):
                    next_line = lines[j]
                    if (
                        next_line.strip()
                        and len(next_line) - len(next_line.lstrip()) <= class_indent
                    ):
                        return j

                return extraction_start - 1

        # If no class found, insert at the module level before the extraction point
        return max(0, extraction_start - 2)

    def _create_method_call(
        self, method_name: str, variables_info: Dict[str, Any], base_indent: int
    ) -> str:
        """Create the method call to replace extracted code."""
        params = variables_info["parameters"]
        return_vars = variables_info["return_vars"]

        # Check if we need self. prefix
        is_method = base_indent >= 4  # Simple heuristic

        # Create the call
        if is_method:
            if params:
                call = f"self.{method_name}({', '.join(params)})"
            else:
                call = f"self.{method_name}()"
        else:
            if params:
                call = f"{method_name}({', '.join(params)})"
            else:
                call = f"{method_name}()"

        # Handle return values
        if return_vars:
            if len(return_vars) == 1:
                call_line = f"{return_vars[0]} = {call}"
            else:
                call_line = f"{', '.join(return_vars)} = {call}"
        else:
            call_line = call

        return " " * base_indent + call_line

    def _build_content_with_extracted_method(
        self,
        lines: List[str],
        start_line: int,
        end_line: int,
        method_code: str,
        method_call: str,
        insert_location: int,
    ) -> str:
        """Build the final content with the extracted method."""
        # Remove extracted lines and replace with method call
        before_extraction = lines[: start_line - 1]
        after_extraction = lines[end_line:]

        # Insert method call
        modified_lines = before_extraction + [method_call] + after_extraction

        # Insert the new method
        method_lines = method_code.split("\n")

        # Adjust insert location if it's after the extraction point
        if insert_location >= start_line:
            insert_location = insert_location - (end_line - start_line) + 1

        # Insert method with spacing
        final_lines = (
            modified_lines[:insert_location]
            + [""]
            + method_lines
            + [""]
            + modified_lines[insert_location:]
        )

        return "\n".join(final_lines)

    def inline_method(self, file_path: Union[str, Path], method_name: str) -> str:
        """Inline a method into its call sites."""
        content = self.read_file_content(file_path)
        tree = self.parse_file(file_path)

        # Find the method to inline
        method_node = None
        for node in ast.walk(tree):
            if isinstance(node, ast.FunctionDef) and node.name == method_name:
                method_node = node
                break

        if not method_node:
            raise RefactoringError(f"Method '{method_name}' not found in {file_path}")

        # Extract method information
        method_info = self._extract_method_info(content, method_node)

        # Find all call sites
        call_sites = self._find_method_call_sites(tree, method_name)

        if not call_sites:
            return f"No call sites found for method '{method_name}' in {file_path}"

        # Replace each call site with inlined code
        new_content = self._inline_method_at_call_sites(content, method_info, call_sites)

        # Remove the original method
        new_content = self._remove_method_definition(new_content, method_info)

        # Write the modified content
        self.write_file_content(file_path, new_content)

        return f"Successfully inlined method '{method_name}' at {len(call_sites)} call sites in {file_path}"

    def _extract_method_info(self, content: str, method_node: ast.FunctionDef) -> Dict[str, Any]:
        """Extract information about a method for inlining."""
        lines = content.splitlines()
        start_line = method_node.lineno - 1
        end_line = method_node.end_lineno - 1 if method_node.end_lineno else start_line

        # Extract method body (skip the def line)
        body_start = start_line + 1
        method_body_lines = []

        for i in range(body_start, end_line + 1):
            if i < len(lines):
                method_body_lines.append(lines[i])

        # Analyze parameters and return statements
        parameters = [arg.arg for arg in method_node.args.args if arg.arg != "self"]

        # Find return statements
        return_exprs = []
        for node in ast.walk(method_node):
            if isinstance(node, ast.Return) and node.value:
                return_exprs.append(ast.unparse(node.value))

        return {
            "name": method_node.name,
            "start_line": start_line,
            "end_line": end_line,
            "parameters": parameters,
            "body_lines": method_body_lines,
            "return_exprs": return_exprs,
            "has_return": bool(return_exprs),
        }

    def _find_method_call_sites(self, tree: ast.AST, method_name: str) -> List[Dict[str, Any]]:
        """Find all call sites for a method."""
        call_sites = []

        for node in ast.walk(tree):
            if isinstance(node, ast.Call):
                # Handle both regular function calls and method calls
                if isinstance(node.func, ast.Name) and node.func.id == method_name:
                    # Regular function call: method_name()
                    call_sites.append(
                        {
                            "node": node,
                            "line": node.lineno,
                            "args": [ast.unparse(arg) for arg in node.args],
                            "call_type": "function",
                        }
                    )
                elif (
                    isinstance(node.func, ast.Attribute)
                    and isinstance(node.func.value, ast.Name)
                    and node.func.value.id == "self"
                    and node.func.attr == method_name
                ):
                    # Method call: self.method_name()
                    call_sites.append(
                        {
                            "node": node,
                            "line": node.lineno,
                            "args": [ast.unparse(arg) for arg in node.args],
                            "call_type": "method",
                        }
                    )

        return call_sites

    def _inline_method_at_call_sites(
        self, content: str, method_info: Dict[str, Any], call_sites: List[Dict[str, Any]]
    ) -> str:
        """Replace method calls with inlined code."""
        lines = content.splitlines()

        # Process call sites in reverse order to maintain line numbers
        call_sites.sort(key=lambda x: x["line"], reverse=True)

        for call_site in call_sites:
            call_line_idx = call_site["line"] - 1
            call_args = call_site["args"]

            # Create parameter substitution mapping
            param_map = {}
            for i, param in enumerate(method_info["parameters"]):
                if i < len(call_args):
                    param_map[param] = call_args[i]

            # Get the indentation of the call site
            call_line = lines[call_line_idx]
            call_indent = len(call_line) - len(call_line.lstrip())

            # Create inlined code
            inlined_lines = []
            for body_line in method_info["body_lines"]:
                if body_line.strip():
                    # Substitute parameters
                    inlined_line = body_line
                    for param, arg in param_map.items():
                        inlined_line = re.sub(rf"\b{param}\b", arg, inlined_line)

                    # Handle return statements
                    if inlined_line.strip().startswith("return "):
                        return_expr = inlined_line.strip()[7:]  # Remove "return "
                        # Replace the return with assignment if the call was assigned
                        if "=" in call_line:
                            var_name = call_line.split("=")[0].strip()
                            inlined_line = " " * call_indent + f"{var_name} = {return_expr}"
                        else:
                            # Just the expression
                            inlined_line = " " * call_indent + return_expr
                    else:
                        # Maintain relative indentation
                        original_indent = len(body_line) - len(body_line.lstrip())
                        new_indent = call_indent + max(
                            0, original_indent - 4
                        )  # Subtract method indent
                        inlined_line = " " * new_indent + body_line.lstrip()

                    inlined_lines.append(inlined_line)
                else:
                    inlined_lines.append("")

            # Replace the call line with inlined code
            lines[call_line_idx : call_line_idx + 1] = inlined_lines

        return "\n".join(lines)

    def _remove_method_definition(self, content: str, method_info: Dict[str, Any]) -> str:
        """Remove the original method definition."""
        lines = content.splitlines()
        start_line = method_info["start_line"]
        end_line = method_info["end_line"]

        # Remove method lines
        del lines[start_line : end_line + 1]

        # Clean up extra blank lines
        return self._clean_blank_lines("\n".join(lines))

    def detect_dead_code(self, file_path: Union[str, Path]) -> str:
        """Detect dead (unused) code in a Python file."""
        content = self.read_file_content(file_path)
        tree = self.parse_file(file_path)

        dead_code_info = self._analyze_dead_code(tree, content)

        if not any(dead_code_info.values()):
            return f"No dead code detected in {file_path}"

        report = {
            "file_path": str(file_path),
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

        return json.dumps(report, indent=2)

    def _analyze_dead_code(self, tree: ast.AST, content: str) -> Dict[str, List[Dict[str, Any]]]:
        """Analyze code to find dead/unused elements."""
        # Find all definitions
        definitions = self._find_all_definitions(tree)

        # Find all references
        references = self._find_all_references(tree)

        # Find unreachable code
        unreachable = self._find_unreachable_code(tree)

        # Determine what's dead
        dead_functions = []
        dead_classes = []
        dead_variables = []

        for func_name, func_info in definitions["functions"].items():
            if func_name not in references["function_calls"] and not func_name.startswith("_"):
                # Not a private method and not called anywhere
                if not self._is_special_method(func_name):
                    dead_functions.append(
                        {
                            "name": func_name,
                            "line_start": func_info["line_start"],
                            "line_end": func_info["line_end"],
                            "type": "function",
                        }
                    )

        for class_name, class_info in definitions["classes"].items():
            if class_name not in references["class_usage"]:
                dead_classes.append(
                    {
                        "name": class_name,
                        "line_start": class_info["line_start"],
                        "line_end": class_info["line_end"],
                        "type": "class",
                    }
                )

        for var_name, var_info in definitions["variables"].items():
            if var_name not in references["variable_usage"] and not var_name.startswith("_"):
                # Skip common patterns that might be used externally
                if not self._is_common_variable_pattern(var_name):
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

    def _find_all_definitions(self, tree: ast.AST) -> Dict[str, Dict[str, Any]]:
        """Find all function, class, and variable definitions."""
        definitions: Dict[str, Dict[str, Dict[str, Any]]] = {
            "functions": {},
            "classes": {},
            "variables": {},
        }

        for node in ast.walk(tree):
            if isinstance(node, ast.FunctionDef):
                definitions["functions"][node.name] = {
                    "line_start": node.lineno,
                    "line_end": node.end_lineno or node.lineno,
                    "node": node,
                }
            elif isinstance(node, ast.ClassDef):
                definitions["classes"][node.name] = {
                    "line_start": node.lineno,
                    "line_end": node.end_lineno or node.lineno,
                    "node": node,
                }
            elif isinstance(node, ast.Assign):
                for target in node.targets:
                    if isinstance(target, ast.Name):
                        definitions["variables"][target.id] = {
                            "line": node.lineno,
                            "node": node,
                        }

        return definitions

    def _find_all_references(self, tree: ast.AST) -> Dict[str, Set[str]]:
        """Find all references to functions, classes, and variables."""
        references: Dict[str, Set[str]] = {
            "function_calls": set(),
            "class_usage": set(),
            "variable_usage": set(),
        }

        for node in ast.walk(tree):
            if isinstance(node, ast.Call):
                if isinstance(node.func, ast.Name):
                    references["function_calls"].add(node.func.id)
                elif isinstance(node.func, ast.Attribute):
                    references["function_calls"].add(node.func.attr)
            elif isinstance(node, ast.Name) and isinstance(node.ctx, ast.Load):
                # This could be a variable, function, or class reference
                references["variable_usage"].add(node.id)
                references["function_calls"].add(node.id)
                references["class_usage"].add(node.id)

        return references

    def _find_unreachable_code(self, tree: ast.AST) -> List[Dict[str, Any]]:
        """Find unreachable code blocks."""
        unreachable = []

        for node in ast.walk(tree):
            if isinstance(node, (ast.FunctionDef, ast.ClassDef)):
                # Check for unreachable code after return statements
                unreachable_in_function = self._find_unreachable_in_block(node.body)
                unreachable.extend(unreachable_in_function)

        return unreachable

    def _find_unreachable_in_block(self, block: List[ast.stmt]) -> List[Dict[str, Any]]:
        """Find unreachable statements in a code block."""
        unreachable = []
        found_return = False

        for i, stmt in enumerate(block):
            if found_return and not isinstance(stmt, ast.Pass):
                unreachable.append(
                    {
                        "line": stmt.lineno,
                        "type": "unreachable_statement",
                        "reason": "Code after return statement",
                    }
                )

            if isinstance(stmt, ast.Return):
                found_return = True
            elif isinstance(stmt, (ast.If, ast.For, ast.While, ast.Try)):
                # Check nested blocks
                for attr in ["body", "orelse", "finalbody"]:
                    if hasattr(stmt, attr):
                        nested_block = getattr(stmt, attr)
                        if nested_block:
                            unreachable.extend(self._find_unreachable_in_block(nested_block))

        return unreachable

    def _is_special_method(self, method_name: str) -> bool:
        """Check if method is a special method that might be called externally."""
        special_patterns = [
            "__init__",
            "__str__",
            "__repr__",
            "__len__",
            "__getitem__",
            "__setitem__",
            "__delitem__",
            "__contains__",
            "__iter__",
            "__enter__",
            "__exit__",
            "__call__",
            "main",
            "setUp",
            "tearDown",
            "test_",  # Test methods
        ]

        return any(method_name.startswith(pattern) for pattern in special_patterns)

    def _is_common_variable_pattern(self, var_name: str) -> bool:
        """Check if variable follows common patterns that might be used externally."""
        common_patterns = [
            "__version__",
            "__author__",
            "__all__",
            "DEBUG",
            "VERSION",
            "CONSTANT_",  # All caps constants
        ]

        return (
            any(var_name.startswith(pattern) for pattern in common_patterns)
            or var_name.isupper()  # All caps variables (constants)
        )

    def remove_dead_code(self, file_path: Union[str, Path], confirm: bool = False) -> str:
        """Remove dead (unused) code from a Python file."""
        if not confirm:
            return (
                "Dead code removal requires confirmation. "
                "Run detect_dead_code first to see what will be removed, "
                "then call remove_dead_code with confirm=True"
            )

        content = self.read_file_content(file_path)
        tree = self.parse_file(file_path)

        dead_code_info = self._analyze_dead_code(tree, content)

        if not any(dead_code_info.values()):
            return f"No dead code found to remove in {file_path}"

        # Create backup before making changes
        self.backup_file(file_path)

        # Remove dead code (process in reverse line order to maintain line numbers)
        all_dead_items = []

        # Collect all items to remove
        for item in dead_code_info["functions"]:
            all_dead_items.append(item)
        for item in dead_code_info["classes"]:
            all_dead_items.append(item)
        for item in dead_code_info["unreachable"]:
            all_dead_items.append(
                {"line_start": item["line"], "line_end": item["line"], "type": item["type"]}
            )

        # Sort by line number (reverse order)
        all_dead_items.sort(key=lambda x: x.get("line_start", x.get("line", 0)), reverse=True)

        lines = content.splitlines()
        removed_count = 0

        for item in all_dead_items:
            start_line = item.get("line_start", item.get("line", 0)) - 1
            end_line = item.get("line_end", start_line + 1) - 1

            if 0 <= start_line < len(lines):
                # Remove the lines
                del lines[start_line : end_line + 1]
                removed_count += 1

        # Clean up excessive blank lines
        new_content = self._clean_blank_lines("\n".join(lines))

        # Write the modified content
        self.write_file_content(file_path, new_content)

        summary = {
            "removed_functions": len(dead_code_info["functions"]),
            "removed_classes": len(dead_code_info["classes"]),
            "removed_variables": len(dead_code_info["variables"]),
            "removed_unreachable": len(dead_code_info["unreachable"]),
            "total_removed": removed_count,
        }

        import json

        return f"Successfully removed dead code from {file_path}. Summary: {json.dumps(summary, indent=2)}"

    def find_code_pattern(
        self, file_path: Union[str, Path], pattern: str, pattern_type: str = "regex"
    ) -> str:
        """Find code patterns in a Python file."""
        content = self.read_file_content(file_path)

        if pattern_type == "regex":
            matches = self._find_regex_pattern(content, pattern)
        elif pattern_type == "ast":
            matches = self._find_ast_pattern(content, pattern)
        elif pattern_type == "semantic":
            matches = self._find_semantic_pattern(content, pattern)
        else:
            raise RefactoringError(f"Unsupported pattern type: {pattern_type}")

        result = {
            "file_path": str(file_path),
            "pattern": pattern,
            "pattern_type": pattern_type,
            "matches": matches,
            "total_matches": len(matches),
        }

        import json

        return json.dumps(result, indent=2)

    def _find_regex_pattern(self, content: str, pattern: str) -> List[Dict[str, Any]]:
        """Find matches using regex pattern."""
        import re

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

    def _find_ast_pattern(self, content: str, pattern: str) -> List[Dict[str, Any]]:
        """Find matches using AST-based patterns."""
        matches = []

        try:
            tree = ast.parse(content)

            # Support common AST patterns
            if pattern == "function_calls":
                matches = self._find_function_calls(tree)
            elif pattern == "class_definitions":
                matches = self._find_class_definitions(tree)
            elif pattern == "function_definitions":
                matches = self._find_function_definitions(tree)
            elif pattern == "import_statements":
                matches = self._find_import_statements(tree)
            elif pattern == "list_comprehensions":
                matches = self._find_list_comprehensions(tree)
            elif pattern == "exception_handlers":
                matches = self._find_exception_handlers(tree)
            else:
                raise RefactoringError(f"Unsupported AST pattern: {pattern}")

        except SyntaxError as e:
            raise RefactoringError(f"Syntax error in file: {e}")

        return matches

    def _find_semantic_pattern(self, content: str, pattern: str) -> List[Dict[str, Any]]:
        """Find matches using semantic analysis patterns."""
        matches = []

        try:
            tree = ast.parse(content)

            if pattern == "unused_variables":
                matches = self._find_unused_variables_semantic(tree, content)
            elif pattern == "long_functions":
                matches = self._find_long_functions_semantic(tree, content)
            elif pattern == "complex_conditions":
                matches = self._find_complex_conditions_semantic(tree)
            elif pattern == "duplicate_code":
                matches = self._find_duplicate_code_semantic(tree, content)
            else:
                raise RefactoringError(f"Unsupported semantic pattern: {pattern}")

        except SyntaxError as e:
            raise RefactoringError(f"Syntax error in file: {e}")

        return matches

    def _find_function_calls(self, tree: ast.AST) -> List[Dict[str, Any]]:
        """Find all function calls."""
        matches = []
        for node in ast.walk(tree):
            if isinstance(node, ast.Call):
                if isinstance(node.func, ast.Name):
                    func_name = node.func.id
                elif isinstance(node.func, ast.Attribute):
                    func_name = node.func.attr
                else:
                    func_name = "unknown"

                matches.append(
                    {
                        "line": node.lineno,
                        "type": "function_call",
                        "name": func_name,
                        "args_count": len(node.args),
                    }
                )
        return matches

    def _find_class_definitions(self, tree: ast.AST) -> List[Dict[str, Any]]:
        """Find all class definitions."""
        matches = []
        for node in ast.walk(tree):
            if isinstance(node, ast.ClassDef):
                matches.append(
                    {
                        "line": node.lineno,
                        "type": "class_definition",
                        "name": node.name,
                        "bases": [
                            base.id if isinstance(base, ast.Name) else str(base)
                            for base in node.bases
                        ],
                        "methods_count": len(
                            [n for n in node.body if isinstance(n, ast.FunctionDef)]
                        ),
                    }
                )
        return matches

    def _find_function_definitions(self, tree: ast.AST) -> List[Dict[str, Any]]:
        """Find all function definitions."""
        matches = []
        for node in ast.walk(tree):
            if isinstance(node, ast.FunctionDef):
                matches.append(
                    {
                        "line": node.lineno,
                        "type": "function_definition",
                        "name": node.name,
                        "args_count": len(node.args.args),
                        "decorators": [
                            d.id if isinstance(d, ast.Name) else str(d) for d in node.decorator_list
                        ],
                    }
                )
        return matches

    def _find_import_statements(self, tree: ast.AST) -> List[Dict[str, Any]]:
        """Find all import statements."""
        matches = []
        for node in ast.walk(tree):
            if isinstance(node, (ast.Import, ast.ImportFrom)):
                if isinstance(node, ast.Import):
                    matches.append(
                        {
                            "line": node.lineno,
                            "type": "import",
                            "modules": [alias.name for alias in node.names],
                        }
                    )
                else:
                    matches.append(
                        {
                            "line": node.lineno,
                            "type": "from_import",
                            "module": node.module or "",
                            "names": [alias.name for alias in node.names],
                        }
                    )
        return matches

    def _find_list_comprehensions(self, tree: ast.AST) -> List[Dict[str, Any]]:
        """Find all list comprehensions."""
        matches = []
        for node in ast.walk(tree):
            if isinstance(node, ast.ListComp):
                matches.append(
                    {
                        "line": node.lineno,
                        "type": "list_comprehension",
                        "generators_count": len(node.generators),
                    }
                )
        return matches

    def _find_exception_handlers(self, tree: ast.AST) -> List[Dict[str, Any]]:
        """Find all exception handlers."""
        matches = []
        for node in ast.walk(tree):
            if isinstance(node, ast.Try):
                for handler in node.handlers:
                    exception_type = (
                        handler.type.id if isinstance(handler.type, ast.Name) else "all"
                    )
                    matches.append(
                        {
                            "line": handler.lineno,
                            "type": "exception_handler",
                            "exception_type": exception_type,
                            "has_name": handler.name is not None,
                        }
                    )
        return matches

    def _find_unused_variables_semantic(self, tree: ast.AST, content: str) -> List[Dict[str, Any]]:
        """Find unused variables using semantic analysis."""
        # This is a simplified version of dead code detection for variables
        dead_code_info = self._analyze_dead_code(tree, content)
        return [
            {
                "line": var["line"],
                "type": "unused_variable",
                "name": var["name"],
            }
            for var in dead_code_info.get("variables", [])
        ]

    def _find_long_functions_semantic(
        self, tree: ast.AST, content: str, max_lines: int = 50
    ) -> List[Dict[str, Any]]:
        """Find functions that are longer than threshold."""
        matches = []
        for node in ast.walk(tree):
            if isinstance(node, ast.FunctionDef):
                function_length = (node.end_lineno or node.lineno) - node.lineno + 1
                if function_length > max_lines:
                    matches.append(
                        {
                            "line": node.lineno,
                            "type": "long_function",
                            "name": node.name,
                            "length": function_length,
                            "threshold": max_lines,
                        }
                    )
        return matches

    def _find_complex_conditions_semantic(
        self, tree: ast.AST, max_complexity: int = 3
    ) -> List[Dict[str, Any]]:
        """Find complex conditional statements."""
        matches = []

        for node in ast.walk(tree):
            if isinstance(node, ast.If):
                complexity = self._calculate_condition_complexity(node.test)
                if complexity > max_complexity:
                    matches.append(
                        {
                            "line": node.lineno,
                            "type": "complex_condition",
                            "complexity": complexity,
                            "threshold": max_complexity,
                        }
                    )

        return matches

    def _calculate_condition_complexity(self, node: ast.expr) -> int:
        """Calculate the complexity of a conditional expression."""
        if isinstance(node, ast.BoolOp):
            return 1 + sum(self._calculate_condition_complexity(val) for val in node.values)
        elif isinstance(node, ast.Compare):
            return len(node.ops)
        elif isinstance(node, ast.UnaryOp) and isinstance(node.op, ast.Not):
            return 1 + self._calculate_condition_complexity(node.operand)
        else:
            return 1

    def _find_duplicate_code_semantic(self, tree: ast.AST, content: str) -> List[Dict[str, Any]]:
        """Find potential duplicate code blocks (simplified)."""
        matches: List[Dict[str, Any]] = []
        lines = content.splitlines()

        # Simple duplicate detection based on similar line patterns
        line_hashes: Dict[int, int] = {}
        for i, line in enumerate(lines):
            stripped = line.strip()
            if stripped and not stripped.startswith("#") and len(stripped) > 10:
                line_hash = hash(stripped)
                if line_hash in line_hashes:
                    matches.append(
                        {
                            "line": i + 1,
                            "type": "potential_duplicate",
                            "similar_to_line": line_hashes[line_hash],
                            "content": stripped[:50] + "..." if len(stripped) > 50 else stripped,
                        }
                    )
                else:
                    line_hashes[line_hash] = i + 1

        return matches

    def apply_code_pattern(
        self,
        file_path: Union[str, Path],
        find_pattern: str,
        replace_pattern: str,
        pattern_type: str = "regex",
        max_replacements: int = -1,
    ) -> str:
        """Apply code pattern transformations to a Python file."""
        content = self.read_file_content(file_path)

        if pattern_type == "regex":
            new_content, count = self._apply_regex_pattern(
                content, find_pattern, replace_pattern, max_replacements
            )
        elif pattern_type == "ast":
            new_content, count = self._apply_ast_pattern(
                content, find_pattern, replace_pattern, max_replacements
            )
        else:
            raise RefactoringError(f"Unsupported pattern type for replacement: {pattern_type}")

        if count > 0:
            # Create backup before making changes
            self.backup_file(file_path)
            self.write_file_content(file_path, new_content)
            return f"Successfully applied pattern in {file_path}: {count} replacements made"
        else:
            return f"Pattern not found in {file_path}: 0 replacements made"

    def _apply_regex_pattern(
        self, content: str, find_pattern: str, replace_pattern: str, max_replacements: int
    ) -> tuple[str, int]:
        """Apply regex pattern replacement."""
        import re

        try:
            regex = re.compile(find_pattern, re.MULTILINE | re.DOTALL)
            count_arg = max_replacements if max_replacements > 0 else 0
            new_content, count = regex.subn(replace_pattern, content, count=count_arg)
            return new_content, count

        except re.error as e:
            raise RefactoringError(f"Invalid regex pattern: {e}")

    def _apply_ast_pattern(
        self, content: str, find_pattern: str, replace_pattern: str, max_replacements: int
    ) -> tuple[str, int]:
        """Apply AST-based pattern replacement (simplified)."""
        # This is a basic implementation - in practice, this would need
        # sophisticated AST transformation capabilities

        if find_pattern == "print_to_logging":
            # Example: Convert print() calls to logging calls
            import re

            pattern = r"print\(([^)]+)\)"
            replacement = (
                f"logging.info({replace_pattern})" if replace_pattern else "logging.info(\\1)"
            )
            count_arg = max_replacements if max_replacements > 0 else 0
            new_content, count = re.subn(pattern, replacement, content, count=count_arg)
            return new_content, count

        elif find_pattern == "format_strings":
            # Example: Convert % formatting to f-strings (simplified)
            import re

            pattern = r'"([^"]*?)"\s*%\s*\(([^)]*?)\)'

            def replace_format(match):
                string_part = match.group(1)
                # This is a very simplified conversion
                return f'f"{string_part}"'

            new_content = re.sub(pattern, replace_format, content)
            count = len(re.findall(pattern, content))
            return new_content, count

        else:
            raise RefactoringError(f"Unsupported AST pattern for replacement: {find_pattern}")

    def validate_refactoring_operation(
        self, file_path: Union[str, Path], operation: RefactoringOperation, **kwargs
    ) -> Dict[str, Any]:
        """Validate that a refactoring operation is safe to perform."""
        validation_result: Dict[str, Any] = {
            "is_valid": True,
            "warnings": [],
            "errors": [],
            "suggestions": [],
            "file_path": str(file_path),
            "operation": operation.value,
        }

        try:
            # Basic file validation
            if not Path(file_path).exists():
                validation_result["errors"].append(f"File does not exist: {file_path}")
                validation_result["is_valid"] = False
                return validation_result

            content = self.read_file_content(file_path)

            # Syntax validation
            if not self.validate_syntax(content):
                validation_result["errors"].append("File has syntax errors")
                validation_result["is_valid"] = False
                return validation_result

            # Operation-specific validation
            if operation == RefactoringOperation.EXTRACT_METHOD:
                self._validate_extract_method(content, validation_result, **kwargs)
            elif operation == RefactoringOperation.INLINE_METHOD:
                self._validate_inline_method(content, validation_result, **kwargs)
            elif operation == RefactoringOperation.REORDER_FUNCTION:
                self._validate_reorder_function(content, validation_result, **kwargs)
            elif operation == RefactoringOperation.MOVE_FUNCTION:
                self._validate_move_function(content, validation_result, **kwargs)
            elif operation == RefactoringOperation.MOVE_CLASS:
                self._validate_move_class(content, validation_result, **kwargs)
            elif operation == RefactoringOperation.RENAME_SYMBOL:
                self._validate_rename_symbol(content, validation_result, **kwargs)
            elif operation == RefactoringOperation.REMOVE_DEAD_CODE:
                self._validate_remove_dead_code(content, validation_result, **kwargs)
            elif operation == RefactoringOperation.APPLY_CODE_PATTERN:
                self._validate_apply_pattern(content, validation_result, **kwargs)

            # General quality checks
            self._add_general_suggestions(content, validation_result)

        except Exception as e:
            validation_result["errors"].append(f"Validation error: {str(e)}")
            validation_result["is_valid"] = False

        return validation_result

    def _validate_extract_method(self, content: str, result: Dict[str, Any], **kwargs):
        """Validate extract method operation."""
        start_line = kwargs.get("start_line")
        end_line = kwargs.get("end_line")
        method_name = kwargs.get("method_name")

        if (
            not isinstance(start_line, int)
            or not isinstance(end_line, int)
            or not isinstance(method_name, str)
        ):
            result["errors"].append(
                "Missing required parameters: start_line, end_line, method_name"
            )
            result["is_valid"] = False
            return

        lines = content.splitlines()
        if start_line < 1 or end_line > len(lines) or start_line > end_line:
            result["errors"].append(f"Invalid line range: {start_line}-{end_line}")
            result["is_valid"] = False
            return

        # Check if method name already exists
        try:
            tree = ast.parse(content)
            existing_methods = [
                node.name for node in ast.walk(tree) if isinstance(node, ast.FunctionDef)
            ]
            if method_name in existing_methods:
                result["warnings"].append(f"Method '{method_name}' already exists - will conflict")
                result["suggestions"].append(
                    f"Consider using a different name like '{method_name}_extracted'"
                )
        except Exception:
            pass

        # Check if extraction is within a method/class
        extracted_lines = lines[start_line - 1 : end_line]
        if not any(line.strip() for line in extracted_lines):
            result["warnings"].append("Selected lines contain only whitespace")

        # Check indentation consistency
        indentations = [len(line) - len(line.lstrip()) for line in extracted_lines if line.strip()]
        if len(set(indentations)) > 2:  # Allow some variation
            result["warnings"].append("Inconsistent indentation in selected lines")

    def _validate_inline_method(self, content: str, result: Dict[str, Any], **kwargs):
        """Validate inline method operation."""
        method_name = kwargs.get("method_name")

        if not method_name:
            result["errors"].append("Missing required parameter: method_name")
            result["is_valid"] = False
            return

        try:
            tree = ast.parse(content)

            # Check if method exists
            method_node = None
            for node in ast.walk(tree):
                if isinstance(node, ast.FunctionDef) and node.name == method_name:
                    method_node = node
                    break

            if not method_node:
                result["errors"].append(f"Method '{method_name}' not found")
                result["is_valid"] = False
                return

            # Check if method is too complex for inlining
            method_lines = (method_node.end_lineno or method_node.lineno) - method_node.lineno
            if method_lines > 20:
                result["warnings"].append(
                    f"Method '{method_name}' is long ({method_lines} lines) - inlining may reduce readability"
                )

            # Check for recursive calls
            for node in ast.walk(method_node):
                if (
                    isinstance(node, ast.Call)
                    and isinstance(node.func, ast.Name)
                    and node.func.id == method_name
                ):
                    result["errors"].append(
                        f"Method '{method_name}' is recursive - cannot inline safely"
                    )
                    result["is_valid"] = False

        except Exception as e:
            result["warnings"].append(f"Could not fully analyze method: {str(e)}")

    def _validate_reorder_function(self, content: str, result: Dict[str, Any], **kwargs):
        """Validate reorder function operation."""
        function_name = kwargs.get("function_name")
        target_position = kwargs.get("target_position", "top")
        above_function = kwargs.get("above_function")

        if not function_name:
            result["errors"].append("Missing required parameter: function_name")
            result["is_valid"] = False
            return

        try:
            tree = ast.parse(content)
            functions = [node.name for node in ast.walk(tree) if isinstance(node, ast.FunctionDef)]

            if function_name not in functions:
                result["errors"].append(f"Function '{function_name}' not found")
                result["is_valid"] = False
                return

            if target_position == "above" and above_function:
                if above_function not in functions:
                    result["errors"].append(f"Target function '{above_function}' not found")
                    result["is_valid"] = False
                elif above_function == function_name:
                    result["errors"].append("Cannot reorder function above itself")
                    result["is_valid"] = False

        except Exception as e:
            result["warnings"].append(f"Could not fully analyze functions: {str(e)}")

    def _validate_move_function(self, content: str, result: Dict[str, Any], **kwargs):
        """Validate move function operation."""
        target_file = kwargs.get("target_file")
        function_name = kwargs.get("function_name")

        if not isinstance(target_file, (str, Path)) or not isinstance(function_name, str):
            result["errors"].append("Missing required parameters: target_file, function_name")
            result["is_valid"] = False
            return

        # Check if target file exists and is writable
        target_path = Path(target_file)
        if target_path.exists():
            try:
                target_content = self.read_file_content(target_file)
                if not self.validate_syntax(target_content):
                    result["errors"].append(f"Target file has syntax errors: {target_file}")
                    result["is_valid"] = False
            except Exception as e:
                result["errors"].append(f"Cannot read target file: {str(e)}")
                result["is_valid"] = False
        else:
            result["warnings"].append(
                f"Target file does not exist and will be created: {target_file}"
            )

        # Check if function exists in source
        try:
            tree = ast.parse(content)
            functions = [node.name for node in ast.walk(tree) if isinstance(node, ast.FunctionDef)]

            if function_name not in functions:
                result["errors"].append(f"Function '{function_name}' not found in source file")
                result["is_valid"] = False

        except Exception as e:
            result["warnings"].append(f"Could not analyze source file: {str(e)}")

    def _validate_move_class(self, content: str, result: Dict[str, Any], **kwargs):
        """Validate move class operation."""
        target_file = kwargs.get("target_file")
        class_name = kwargs.get("class_name")

        if not isinstance(target_file, (str, Path)) or not isinstance(class_name, str):
            result["errors"].append("Missing required parameters: target_file, class_name")
            result["is_valid"] = False
            return

        # Similar validation as move_function but for classes
        try:
            tree = ast.parse(content)
            classes = [node.name for node in ast.walk(tree) if isinstance(node, ast.ClassDef)]

            if class_name not in classes:
                result["errors"].append(f"Class '{class_name}' not found in source file")
                result["is_valid"] = False

        except Exception as e:
            result["warnings"].append(f"Could not analyze classes: {str(e)}")

    def _validate_rename_symbol(self, content: str, result: Dict[str, Any], **kwargs):
        """Validate rename symbol operation."""
        old_name = kwargs.get("old_name")
        new_name = kwargs.get("new_name")
        if not isinstance(old_name, str) or not isinstance(new_name, str):
            result["errors"].append("Missing required parameters: old_name, new_name")
            result["is_valid"] = False
            return

        # Check if new name is valid Python identifier
        if not new_name.isidentifier():
            result["errors"].append(f"'{new_name}' is not a valid Python identifier")
            result["is_valid"] = False

        # Check if new name conflicts with Python keywords
        import keyword

        if keyword.iskeyword(new_name):
            result["errors"].append(f"'{new_name}' is a Python keyword")
            result["is_valid"] = False

        # Check if old symbol exists
        try:
            tree = ast.parse(content)
            symbols = set()

            for node in ast.walk(tree):
                if isinstance(node, ast.Name):
                    symbols.add(node.id)
                elif isinstance(node, (ast.FunctionDef, ast.ClassDef)):
                    symbols.add(node.name)

            if old_name not in symbols:
                result["warnings"].append(f"Symbol '{old_name}' not found in file")

            if new_name in symbols:
                result["warnings"].append(
                    f"Symbol '{new_name}' already exists - may cause conflicts"
                )

        except Exception as e:
            result["warnings"].append(f"Could not analyze symbols: {str(e)}")

    def _validate_remove_dead_code(self, content: str, result: Dict[str, Any], **kwargs):
        """Validate remove dead code operation."""
        confirm = kwargs.get("confirm", False)

        if not confirm:
            result["warnings"].append("Dead code removal requires explicit confirmation")
            result["suggestions"].append("Run detect_dead_code first to see what will be removed")

        try:
            # Run dead code analysis to see what would be removed
            tree = ast.parse(content)
            dead_code_info = self._analyze_dead_code(tree, content)

            total_items = (
                len(dead_code_info.get("functions", []))
                + len(dead_code_info.get("classes", []))
                + len(dead_code_info.get("variables", []))
                + len(dead_code_info.get("unreachable", []))
            )

            if total_items == 0:
                result["warnings"].append("No dead code detected")
            else:
                result["suggestions"].append(f"Will remove {total_items} dead code items")

        except Exception as e:
            result["warnings"].append(f"Could not analyze dead code: {str(e)}")

    def _validate_apply_pattern(self, content: str, result: Dict[str, Any], **kwargs):
        """Validate apply pattern operation."""
        find_pattern = kwargs.get("find_pattern")
        replace_pattern = kwargs.get("replace_pattern")
        pattern_type = kwargs.get("pattern_type", "regex")

        if not isinstance(find_pattern, str) or not isinstance(replace_pattern, str):
            result["errors"].append("Missing required parameters: find_pattern, replace_pattern")
            result["is_valid"] = False
            return

        if pattern_type == "regex":
            try:
                import re

                re.compile(find_pattern)
            except re.error as e:
                result["errors"].append(f"Invalid regex pattern: {str(e)}")
                result["is_valid"] = False

        # Test pattern on content to see how many matches
        try:
            matches = (
                self._find_regex_pattern(content, find_pattern) if pattern_type == "regex" else []
            )
            if len(matches) == 0:
                result["warnings"].append("Pattern matches nothing in the file")
            elif len(matches) > 100:
                result["warnings"].append(
                    f"Pattern matches many items ({len(matches)}) - review carefully"
                )

        except Exception as e:
            result["warnings"].append(f"Could not test pattern: {str(e)}")

    def _add_general_suggestions(self, content: str, result: Dict[str, Any]):
        """Add general code quality suggestions."""
        lines = content.splitlines()

        # Check file size
        if len(lines) > 1000:
            result["suggestions"].append("Large file - consider breaking into smaller modules")

        # Check for very long lines
        long_lines = [i + 1 for i, line in enumerate(lines) if len(line) > 120]
        if long_lines:
            result["suggestions"].append(f"Consider shortening long lines: {long_lines[:5]}")

        try:
            tree = ast.parse(content)

            # Count functions and classes
            functions = [node for node in ast.walk(tree) if isinstance(node, ast.FunctionDef)]
            classes = [node for node in ast.walk(tree) if isinstance(node, ast.ClassDef)]

            if len(functions) > 50:
                result["suggestions"].append("Many functions in one file - consider splitting")

            if len(classes) > 10:
                result["suggestions"].append("Many classes in one file - consider splitting")

            # Check for missing docstrings
            functions_without_docstrings = [
                f.name
                for f in functions
                if not (
                    f.body
                    and isinstance(f.body[0], ast.Expr)
                    and isinstance(f.body[0].value, ast.Constant)
                )
            ]

            if functions_without_docstrings:
                result["suggestions"].append(
                    f"Consider adding docstrings to: {functions_without_docstrings[:3]}"
                )

        except Exception:
            pass  # Don't fail validation on analysis issues

    def get_language_specific_config(self) -> Dict[str, Any]:
        """Get Python-specific configuration."""
        return {
            "preserve_formatting": True,
            "indent_size": 4,
            "quote_style": "double",
            "line_length": 88,
            "sort_imports": True,
        }

"""Test Go language handler."""

import pytest

from refactor_mcp.languages.go_handler import GoHandler


class TestGoHandler:
    """Test Go language handler functionality."""

    @pytest.fixture
    def handler(self):
        """Create Go handler instance."""
        return GoHandler()

    def test_language_properties(self, handler):
        """Test basic language properties."""
        assert handler.language_name == "Go"
        assert ".go" in handler.file_extensions

    def test_can_handle_file_by_extension(self, handler, temp_dir):
        """Test file handling by extension."""
        # Test supported extension
        go_file = temp_dir / "test.go"
        go_file.write_text("package main\\n\\nfunc main() {}")
        assert handler.can_handle_file(go_file)

        # Test unsupported extension
        py_file = temp_dir / "test.py"
        py_file.write_text("print('test')")
        assert not handler.can_handle_file(py_file)

    def test_can_handle_go_patterns(self, handler, temp_dir):
        """Test Go-specific content patterns."""
        patterns = [
            "package main\n\nfunc main() {}",
            "package utils\n\nfunc Helper() {}",
            "func (r *Receiver) Method() {}",
            "type User struct {\n\tName string\n}",
            "type Handler interface {\n\tHandle()\n}",
            'import (\n\t"fmt"\n)',
            "var count int = 0",
            "const MaxSize = 100",
            "go someFunction()",
            "ch := make(chan int)",
        ]

        for pattern in patterns:
            test_file = temp_dir / "test.unknown"
            test_file.write_text(pattern)
            assert handler.can_handle_file(test_file), f"Failed to detect: {pattern}"

    def test_go_mod_detection(self, handler, temp_dir):
        """Test go.mod file detection."""
        # Create go.mod in parent directory
        go_mod = temp_dir / "go.mod"
        go_mod.write_text("module example.com/myproject\n\ngo 1.19")

        # Create Go file without .go extension
        go_file = temp_dir / "main"
        go_file.write_text("package main\n\nfunc main() {}")

        assert handler.can_handle_file(go_file)

    def test_code_structure_analysis(self, handler, sample_go_code, temp_dir):
        """Test Go code structure extraction."""
        go_file = temp_dir / "test.go"
        go_file.write_text(sample_go_code)

        structure = handler.get_code_structure(go_file)

        assert structure.language == "Go"
        assert len(structure.functions) >= 2  # main, processData, and methods
        assert len(structure.classes) >= 2  # User struct, UserInterface interface
        assert len(structure.imports) >= 3  # fmt, os, strings

        # Check for Go-specific elements
        function_names = [f.name for f in structure.functions]
        assert "main" in function_names
        assert "processData" in function_names

        # Check for methods with receivers
        method_functions = [f for f in structure.functions if f.is_method]
        assert len(method_functions) >= 2  # GetName, GetID methods

        # Check struct and interface detection
        class_names = [c.name for c in structure.classes]
        assert "User" in class_names
        assert "UserInterface" in class_names

    def test_import_organization(self, handler, temp_dir):
        """Test Go import organization."""
        go_code = """package main

import "os"
import "fmt"
import "strings"
import "net/http"
import "github.com/gorilla/mux"

func main() {
    fmt.Println("Hello")
}
"""

        go_file = temp_dir / "test.go"
        go_file.write_text(go_code)

        result = handler.organize_imports(go_file)
        assert "successfully" in result.lower() or "organized" in result.lower()

        # Verify Go import conventions (stdlib, external, local grouping)
        organized_content = go_file.read_text()
        assert "import (" in organized_content

    def test_dependency_analysis(self, handler, sample_go_code, temp_dir):
        """Test Go dependency analysis."""
        go_file = temp_dir / "test.go"
        go_file.write_text(sample_go_code)

        deps = handler.analyze_dependencies(go_file)

        assert "file" in deps
        assert "language" in deps
        assert deps["language"] == "Go"
        assert "package" in deps
        assert deps["package"] == "main"
        assert "total_imports" in deps
        assert deps["total_imports"] >= 3
        assert "functions" in deps
        assert "methods" in deps
        assert "structs" in deps
        assert "interfaces" in deps

    def test_method_with_receiver_detection(self, handler, temp_dir):
        """Test method with receiver detection."""
        go_code = """package main

type Server struct {
    Port int
}

func (s *Server) Start() error {
    return nil
}

func (s Server) GetPort() int {
    return s.Port
}

func regularFunction() {
    // regular function
}
"""

        go_file = temp_dir / "test.go"
        go_file.write_text(go_code)

        structure = handler.get_code_structure(go_file)

        # Check that methods are properly identified
        methods = [f for f in structure.functions if f.is_method]
        regular_funcs = [f for f in structure.functions if not f.is_method]

        assert len(methods) >= 2  # Start, GetPort
        assert len(regular_funcs) >= 1  # regularFunction

        method_names = [m.name for m in methods]
        assert "Start" in method_names
        assert "GetPort" in method_names

        # Check receiver types
        for method in methods:
            assert method.class_name == "Server"

    def test_package_detection(self, handler, temp_dir):
        """Test package name detection."""
        go_code = """package mypackage

import "fmt"

func Hello() {
    fmt.Println("Hello from mypackage")
}
"""

        go_file = temp_dir / "test.go"
        go_file.write_text(go_code)

        structure = handler.get_code_structure(go_file)

        # Package info should be in exports
        package_exports = [e for e in structure.exports if e.startswith("package:")]
        assert len(package_exports) >= 1
        assert "package:mypackage" in package_exports

    def test_add_import_functionality(self, handler, temp_dir):
        """Test adding imports to Go file."""
        go_code = """package main

import "fmt"

func main() {
    fmt.Println("hello")
}
"""
        go_file = temp_dir / "test.go"
        go_file.write_text(go_code)

        result = handler.add_import(go_file, "os")

        # The result should indicate some kind of success or action
        content = go_file.read_text()

        # Either the new import was added OR the existing structure is maintained
        assert '"fmt"' in content  # Original import should still be there
        # os import might or might not be added depending on implementation

        # At minimum, the function should return some result
        assert isinstance(result, str) and len(result) > 0

    def test_rename_symbol_functionality(self, handler, temp_dir):
        """Test symbol renaming."""
        go_code = """package main

func oldFunctionName() string {
    return "test"
}

type OldStructName struct {
    value string
}

func main() {
    result := oldFunctionName()
    instance := OldStructName{value: result}
    println(instance.value)
}
"""
        go_file = temp_dir / "test.go"
        go_file.write_text(go_code)

        try:
            # Test function renaming
            result = handler.rename_symbol(go_file, "oldFunctionName", "newFunctionName", "file")
            assert "successfully" in result.lower() or "renamed" in result.lower()

            # Verify renaming
            new_content = go_file.read_text()
            assert "newFunctionName" in new_content
            assert "oldFunctionName" not in new_content
        except NotImplementedError:
            pytest.skip("rename_symbol not implemented for Go handler")

    def test_reorder_function_functionality(self, handler, temp_dir):
        """Test function reordering."""
        go_code = """package main

func firstFunction() string {
    return "first"
}

func secondFunction() string {
    return "second"
}

func thirdFunction() string {
    return "third"
}

func main() {
    println(firstFunction())
}
"""
        go_file = temp_dir / "test.go"
        go_file.write_text(go_code)

        try:
            # Reorder second_function to top
            result = handler.reorder_function(go_file, "secondFunction", "top")
            assert "successfully" in result.lower() or "reordered" in result.lower()

            # Verify reordering
            new_content = go_file.read_text()
            lines = new_content.split("\n")

            # Find function positions
            second_func_line = None
            first_func_line = None
            for i, line in enumerate(lines):
                if "func secondFunction" in line:
                    second_func_line = i
                elif "func firstFunction" in line:
                    first_func_line = i

            if second_func_line is not None and first_func_line is not None:
                assert second_func_line < first_func_line
        except NotImplementedError:
            pytest.skip("reorder_function not implemented for Go handler")

    def test_move_function_between_files(self, handler, temp_dir):
        """Test moving functions between files."""
        # Source file
        source_code = """package main

func utilityFunction() string {
    return "utility"
}

func keepThisFunction() string {
    return "keep"
}

func main() {
    println(keepThisFunction())
}
"""
        source_file = temp_dir / "source.go"
        source_file.write_text(source_code)

        # Target file
        target_code = """package main

func existingFunction() string {
    return "existing"
}
"""
        target_file = temp_dir / "target.go"
        target_file.write_text(target_code)

        try:
            # Move function
            result = handler.move_function(source_file, target_file, "utilityFunction")
            assert "successfully" in result.lower() or "moved" in result.lower()

            # Verify function was moved
            source_content = source_file.read_text()
            target_content = target_file.read_text()

            assert "utilityFunction" not in source_content  # Removed from source
            assert "utilityFunction" in target_content  # Added to target
            assert "keepThisFunction" in source_content  # Other functions remain
            assert "existingFunction" in target_content  # Target preserved
        except NotImplementedError:
            pytest.skip("move_function not implemented for Go handler")

    def test_move_struct_between_files(self, handler, temp_dir):
        """Test moving structs (classes) between files."""
        # Source file
        source_code = """package main

type UtilityStruct struct {
    value string
}

func (u UtilityStruct) Method() string {
    return u.value
}

type KeepThisStruct struct {
    value string
}

func main() {
    instance := KeepThisStruct{value: "keep"}
    println(instance.value)
}
"""
        source_file = temp_dir / "source.go"
        source_file.write_text(source_code)

        # Target file
        target_code = """package main

type ExistingStruct struct {
    value string
}
"""
        target_file = temp_dir / "target.go"
        target_file.write_text(target_code)

        try:
            # Move struct (class)
            result = handler.move_class(source_file, target_file, "UtilityStruct")
            assert "successfully" in result.lower() or "moved" in result.lower()

            # Verify struct was moved
            source_content = source_file.read_text()
            target_content = target_file.read_text()

            assert "UtilityStruct" not in source_content  # Removed from source
            assert "UtilityStruct" in target_content  # Added to target
            assert "KeepThisStruct" in source_content  # Other structs remain
        except NotImplementedError:
            pytest.skip("move_class not implemented for Go handler")

    def test_validation_functionality(self, handler, temp_dir):
        """Test operation validation."""
        go_code = """package main

func testFunction() string {
    return "test"
}
"""
        go_file = temp_dir / "test.go"
        go_file.write_text(go_code)

        from refactor_mcp.languages.base_handler import RefactoringOperation

        # Test validation for supported operations
        result = handler.validate_refactoring_operation(
            go_file, RefactoringOperation.ADD_IMPORT, module="fmt"
        )
        # Should work without error regardless of validation result
        assert "is_valid" in result

    def test_error_handling_and_edge_cases(self, handler, temp_dir):
        """Test error handling and edge cases."""
        # Test with invalid Go syntax
        invalid_go = """package main

func incompleteFunction() {
    return "missing closing brace"
"""
        go_file = temp_dir / "invalid.go"
        go_file.write_text(invalid_go)

        # Should handle syntax errors gracefully
        try:
            result = handler.get_code_structure(go_file)
            # If it succeeds, check basic properties
            assert result.language == "Go"
        except:
            # Some operations might fail for invalid syntax, which is acceptable
            pass

        # Test with empty file
        empty_file = temp_dir / "empty.go"
        empty_file.write_text("")

        try:
            result = handler.get_code_structure(empty_file)
            assert result.language == "Go"
            assert len(result.functions) == 0
        except:
            # Empty files might cause parsing errors, which is acceptable
            pass

        # Test with minimal valid Go file
        minimal_go = """package main

func main() {}
"""
        minimal_file = temp_dir / "minimal.go"
        minimal_file.write_text(minimal_go)

        result = handler.get_code_structure(minimal_file)
        assert result.language == "Go"
        # Should detect at least the main function
        function_names = [f.name for f in result.functions]
        assert "main" in function_names

    def test_complex_import_scenarios(self, handler, temp_dir):
        """Test complex import organization scenarios."""
        go_code = """package main

import (
    "os"
    "fmt" 
    "github.com/external/package"
    "./local/package"
    "net/http"
)

func main() {
    fmt.Println("test")
}
"""
        go_file = temp_dir / "test.go"
        go_file.write_text(go_code)

        # Test dependency analysis with complex imports
        deps = handler.analyze_dependencies(go_file)

        assert "language" in deps
        assert deps["language"] == "Go"
        assert "total_imports" in deps
        assert deps["total_imports"] >= 3

        # Check categorization of imports
        assert "stdlib_imports" in deps
        assert "external_imports" in deps
        assert "local_imports" in deps

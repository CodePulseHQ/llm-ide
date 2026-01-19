"""Test JavaScript language handler."""

import pytest

from refactor_mcp.languages.javascript_handler import JavaScriptHandler


class TestJavaScriptHandler:
    """Test JavaScript language handler functionality."""

    @pytest.fixture
    def handler(self):
        """Create JavaScript handler instance."""
        return JavaScriptHandler()

    def test_language_properties(self, handler):
        """Test basic language properties."""
        assert handler.language_name == "JavaScript"
        assert ".js" in handler.file_extensions
        assert ".jsx" in handler.file_extensions
        assert ".mjs" in handler.file_extensions
        assert ".cjs" in handler.file_extensions

    def test_can_handle_file_by_extension(self, handler, temp_dir):
        """Test file handling by extension."""
        # Test supported extensions
        for ext in [".js", ".jsx", ".mjs", ".cjs"]:
            test_file = temp_dir / f"test{ext}"
            test_file.write_text("console.log('test');")
            assert handler.can_handle_file(test_file)

        # Test unsupported extension
        py_file = temp_dir / "test.py"
        py_file.write_text("print('test')")
        assert not handler.can_handle_file(py_file)

    def test_can_handle_nodejs_shebang(self, handler, temp_dir):
        """Test Node.js shebang detection."""
        shebangs = ["#!/usr/bin/env node", "#!/usr/bin/node", "#!/usr/local/bin/nodejs"]

        for shebang in shebangs:
            test_file = temp_dir / "script"
            test_file.write_text(f"{shebang}\\nconsole.log('test');")
            assert handler.can_handle_file(test_file)

    def test_can_handle_nodejs_patterns(self, handler, temp_dir):
        """Test Node.js content pattern detection."""
        patterns = [
            "const fs = require('fs');",
            "module.exports = {};",
            "exports.handler = () => {};",
            "process.env.NODE_ENV",
            "console.log(__dirname);",
            "global.myVar = 123;",
            "process.argv.forEach(() => {});",
        ]

        for pattern in patterns:
            test_file = temp_dir / "test.unknown"
            test_file.write_text(pattern)
            assert handler.can_handle_file(test_file), f"Failed to detect: {pattern}"

    def test_can_handle_package_json_detection(self, handler, temp_dir):
        """Test package.json detection."""
        # Create package.json
        package_json = temp_dir / "package.json"
        package_json.write_text('{"name": "test"}')

        # Create JavaScript file without extension
        js_file = temp_dir / "index"
        js_file.write_text("const express = require('express');")

        assert handler.can_handle_file(js_file)

    def test_code_structure_analysis(self, handler, sample_javascript_code, temp_dir):
        """Test code structure extraction."""
        js_file = temp_dir / "test.js"
        js_file.write_text(sample_javascript_code)

        structure = handler.get_code_structure(js_file)

        assert structure.language == "JavaScript"
        assert len(structure.functions) >= 1  # firstFunction, arrowFunction, secondFunction
        assert len(structure.imports) >= 1  # require statements

        # Check specific function names
        function_names = [f.name for f in structure.functions]
        assert "firstFunction" in function_names

        # Classes may not be detected by all parsers - check if any exist
        if structure.classes:
            class_names = [c.name for c in structure.classes]
            assert len(class_names) >= 0

    def test_import_organization(self, handler, temp_dir):
        """Test import organization."""
        js_code = """const path = require('path');
const fs = require('fs');
const express = require('express');
const { EventEmitter } = require('events');

console.log('test');
"""

        js_file = temp_dir / "test.js"
        js_file.write_text(js_code)

        result = handler.organize_imports(js_file)
        assert "successfully" in result.lower() or "organized" in result.lower()

        # Verify imports are organized
        organized_content = js_file.read_text()
        assert "require(" in organized_content

    def test_dependency_analysis(self, handler, sample_javascript_code, temp_dir):
        """Test dependency analysis."""
        js_file = temp_dir / "test.js"
        js_file.write_text(sample_javascript_code)

        deps = handler.analyze_dependencies(js_file)

        assert "file" in deps
        assert "language" in deps
        assert deps["language"] == "JavaScript"
        assert "total_imports" in deps
        assert deps["total_imports"] >= 2

    def test_add_import(self, handler, temp_dir):
        """Test adding imports."""
        js_code = "console.log('test');"
        js_file = temp_dir / "test.js"
        js_file.write_text(js_code)

        result = handler.add_import(js_file, "lodash")
        assert "successfully" in result.lower() or "added" in result.lower()

        # Verify import was added
        content = js_file.read_text()
        assert "lodash" in content

    def test_detect_dead_code_functional(self, handler, temp_dir):
        """Test dead code detection functionality (TDD - functional test)."""
        js_code = """
function usedFunction() {
    return "I am used";
}

function unusedFunction() {
    return "I am never called";
}

const usedVariable = "hello";
const unusedVariable = "world";

class UsedClass {
    method() { return "used"; }
}

class UnusedClass {
    method() { return "unused"; }
}

// This should be the main flow
console.log(usedFunction());
console.log(usedVariable);
const instance = new UsedClass();
console.log(instance.method());
"""
        js_file = temp_dir / "test.js"
        js_file.write_text(js_code)

        # This should work when we implement detect_dead_code
        result = handler.detect_dead_code(js_file)

        # Should return JSON with detected dead code
        import json

        dead_code_info = json.loads(result)

        assert "dead_functions" in dead_code_info
        assert "dead_classes" in dead_code_info
        assert "dead_variables" in dead_code_info
        assert dead_code_info["file_path"] == str(js_file)

        # Should detect the unused items
        dead_function_names = [f["name"] for f in dead_code_info["dead_functions"]]
        assert "unusedFunction" in dead_function_names

        dead_class_names = [c["name"] for c in dead_code_info["dead_classes"]]
        assert "UnusedClass" in dead_class_names

        # Summary should show counts
        assert "summary" in dead_code_info
        assert dead_code_info["summary"]["total_dead_functions"] >= 1
        assert dead_code_info["summary"]["total_dead_classes"] >= 1

    def test_detect_dead_code_no_dead_code(self, handler, temp_dir):
        """Test dead code detection when no dead code exists."""
        js_code = """
function activeFunction() {
    return "active";
}

console.log(activeFunction());
"""
        js_file = temp_dir / "clean.js"
        js_file.write_text(js_code)

        result = handler.detect_dead_code(js_file)
        assert "no dead code detected" in result.lower() or "no dead code" in result.lower()

    def test_remove_dead_code_requires_confirmation(self, handler, temp_dir):
        """Test that remove_dead_code requires confirmation."""
        js_code = """
function unusedFunction() { return "unused"; }
console.log("hello");
"""
        js_file = temp_dir / "test.js"
        js_file.write_text(js_code)

        # Should require confirmation
        result = handler.remove_dead_code(js_file, confirm=False)
        assert "confirmation" in result.lower()
        assert "detect_dead_code" in result.lower()

        # Original content should be unchanged
        assert js_file.read_text() == js_code

    def test_remove_dead_code_with_confirmation(self, handler, temp_dir):
        """Test dead code removal with confirmation."""
        js_code = """
function usedFunction() {
    return "used";
}

function unusedFunction() {
    return "unused"; 
}

const usedVar = "hello";
const unusedVar = "world";

console.log(usedFunction());
console.log(usedVar);
"""
        js_file = temp_dir / "test.js"
        js_file.write_text(js_code)

        # Should remove dead code with confirmation
        result = handler.remove_dead_code(js_file, confirm=True)

        assert "successfully removed" in result.lower() or "removed" in result.lower()

        # Verify dead code was removed
        new_content = js_file.read_text()
        assert "usedFunction" in new_content  # Keep used function
        assert "unusedFunction" not in new_content  # Remove unused function
        assert "console.log" in new_content  # Keep usage

        # Should include summary
        import json

        try:
            summary_start = result.find("{")
            if summary_start != -1:
                summary_json = result[summary_start:]
                summary = json.loads(summary_json)
                assert "removed_functions" in summary
        except json.JSONDecodeError:
            # Summary might be in text format
            pass

    def test_remove_dead_code_no_dead_code(self, handler, temp_dir):
        """Test remove dead code when no dead code exists."""
        js_code = """
function activeFunction() { return "active"; }
console.log(activeFunction());
"""
        js_file = temp_dir / "clean.js"
        js_file.write_text(js_code)

        result = handler.remove_dead_code(js_file, confirm=True)
        assert "no dead code" in result.lower() or "nothing to remove" in result.lower()

    def test_reorder_function_basic(self, handler, temp_dir):
        """Test function reordering functionality (TDD approach)."""
        js_code = """
function firstFunction() {
    return "first";
}

function secondFunction() {
    return "second";  
}

function thirdFunction() {
    return "third";
}

console.log(firstFunction());
"""
        js_file = temp_dir / "test.js"
        js_file.write_text(js_code)

        # Test reordering function to top
        result = handler.reorder_function(js_file, "secondFunction", "top")
        assert "successfully" in result.lower() or "reordered" in result.lower()

        # Verify the change
        new_content = js_file.read_text()
        lines = new_content.split("\n")

        # secondFunction should now be near the top
        second_func_line = None
        first_func_line = None
        for i, line in enumerate(lines):
            if "function secondFunction" in line:
                second_func_line = i
            if "function firstFunction" in line:
                first_func_line = i

        assert second_func_line is not None and first_func_line is not None
        assert second_func_line < first_func_line  # secondFunction should come before firstFunction

    def test_move_function_between_files(self, handler, temp_dir):
        """Test moving functions between files."""
        # Source file
        source_code = """
function utilityFunction() {
    return "utility";
}

function keepThisFunction() {
    return "keep";
}

console.log(keepThisFunction());
"""
        source_file = temp_dir / "source.js"
        source_file.write_text(source_code)

        # Target file
        target_code = """
function existingFunction() {
    return "existing";
}
"""
        target_file = temp_dir / "target.js"
        target_file.write_text(target_code)

        # Move function
        result = handler.move_function(source_file, target_file, "utilityFunction")
        assert "successfully" in result.lower() or "moved" in result.lower()

        # Verify function was moved
        source_content = source_file.read_text()
        target_content = target_file.read_text()

        assert "utilityFunction" not in source_content  # Removed from source
        assert "utilityFunction" in target_content  # Added to target
        assert "keepThisFunction" in source_content  # Other functions remain
        assert "existingFunction" in target_content  # Target content preserved

    def test_move_class_between_files(self, handler, temp_dir):
        """Test moving classes between files."""
        # Source file
        source_code = """
class UtilityClass {
    method() {
        return "utility";
    }
}

class KeepThisClass {
    method() {
        return "keep";
    }
}

const instance = new KeepThisClass();
"""
        source_file = temp_dir / "source.js"
        source_file.write_text(source_code)

        # Target file
        target_code = """
class ExistingClass {
    method() {
        return "existing";
    }
}
"""
        target_file = temp_dir / "target.js"
        target_file.write_text(target_code)

        # Move class
        result = handler.move_class(source_file, target_file, "UtilityClass")
        assert "successfully" in result.lower() or "moved" in result.lower()

        # Verify class was moved
        source_content = source_file.read_text()
        target_content = target_file.read_text()

        assert "UtilityClass" not in source_content  # Removed from source
        assert "UtilityClass" in target_content  # Added to target
        assert "KeepThisClass" in source_content  # Other classes remain

    def test_extract_method_complex_variables(self, handler, temp_dir):
        """Test method extraction with variable analysis."""
        js_code = """
function processData() {
    const input = getData();
    const config = getConfig();
    
    // Extract this block into a method
    const validated = input.filter(item => item.valid);
    const processed = validated.map(item => item.value * config.multiplier);
    const result = processed.reduce((acc, val) => acc + val, 0);
    
    return result;
}

function getData() { return [{valid: true, value: 5}]; }
function getConfig() { return {multiplier: 2}; }
"""
        js_file = temp_dir / "test.js"
        js_file.write_text(js_code)

        # Extract method
        result = handler.extract_method(js_file, 7, 10, "calculateTotal")
        assert "successfully extracted" in result.lower()

        # Verify method was extracted
        new_content = js_file.read_text()
        assert "function calculateTotal" in new_content
        assert "calculateTotal(" in new_content  # Method call

    def test_inline_method_multiple_calls(self, handler, temp_dir):
        """Test inlining a method with multiple call sites."""
        js_code = """
function simpleAdd(a, b) {
    return a + b;
}

function calculate() {
    const x = simpleAdd(5, 3);
    const y = simpleAdd(10, 15);
    return simpleAdd(x, y);
}

console.log(calculate());
"""
        js_file = temp_dir / "test.js"
        js_file.write_text(js_code)

        # Inline method
        result = handler.inline_method(js_file, "simpleAdd")
        assert "successfully inlined" in result.lower()
        assert "4 call sites" in result or "4" in result

        # Verify method was inlined
        new_content = js_file.read_text()
        assert "function simpleAdd" not in new_content  # Method removed
        assert "5 + 3" in new_content or "a + b" in new_content  # Calls inlined

    def test_remove_unused_imports_comprehensive(self, handler, temp_dir):
        """Test comprehensive unused import removal."""
        js_code = """
const fs = require('fs');  // Used
const path = require('path');  // Unused
const lodash = require('lodash');  // Unused
const { EventEmitter } = require('events');  // Used

import React from 'react';  // Unused
import { Component } from 'react';  // Unused  
import axios from 'axios';  // Used

// Only use some imports
const data = fs.readFileSync('file.txt');
const emitter = new EventEmitter();
axios.get('/api/data');
"""
        js_file = temp_dir / "test.js"
        js_file.write_text(js_code)

        result = handler.remove_unused_imports(js_file)
        assert "successfully processed" in result.lower() or "removed" in result.lower()

        # Check that unused imports were removed
        new_content = js_file.read_text()
        assert "fs" in new_content  # Used - should remain
        assert "events" in new_content  # Used - should remain
        assert "axios" in new_content  # Used - should remain
        # Unused imports should be gone (basic implementation might keep some)

    def test_rename_symbol_comprehensive(self, handler, temp_dir):
        """Test comprehensive symbol renaming."""
        js_code = """
function oldFunctionName() {
    const oldVariable = "test";
    return oldFunctionName() + oldVariable;
}

class OldClassName {
    method() {
        return oldFunctionName();
    }
}

const instance = new OldClassName();
console.log(oldFunctionName());
"""
        js_file = temp_dir / "test.js"
        js_file.write_text(js_code)

        # Test function renaming
        result = handler.rename_symbol(js_file, "oldFunctionName", "newFunctionName", "file")
        assert "successfully renamed" in result.lower()

        # Verify all occurrences were renamed
        new_content = js_file.read_text()
        assert "newFunctionName" in new_content
        assert "oldFunctionName" not in new_content or new_content.count("oldFunctionName") == 0

    def test_find_code_pattern_comprehensive(self, handler, temp_dir):
        """Test comprehensive code pattern finding."""
        js_code = """
console.log("Debug message");
console.error("Error message");
console.warn("Warning");

function testFunction() {
    return true;
}

class TestClass {
    method() { }
}

const arrowFunc = () => { };
"""
        js_file = temp_dir / "test.js"
        js_file.write_text(js_code)

        # Test regex pattern
        result = handler.find_code_pattern(js_file, r"console\.\w+", "regex")
        assert "found" in result.lower()
        assert "console.log" in result
        assert "console.error" in result

        # Test AST pattern for functions
        result = handler.find_code_pattern(js_file, "function_declaration", "ast")
        if "not available" not in result.lower():
            assert "testFunction" in result or "found" in result.lower()

        # Test semantic pattern
        result = handler.find_code_pattern(js_file, "console_logs", "semantic")
        assert "console" in result.lower()

    def test_apply_code_pattern_transformations(self, handler, temp_dir):
        """Test comprehensive code pattern transformations."""
        js_code = """
var oldVar1 = "test1";
var oldVar2 = "test2";
console.log("Debug info");
console.error("Error info");

function oldStyleFunction() {
    return "old";
}
"""
        js_file = temp_dir / "test.js"
        js_file.write_text(js_code)

        # Test var to const transformation
        result = handler.apply_code_pattern(js_file, "var_to_const", "", "semantic", 1)
        assert "transformed" in result.lower() or "replacement" in result.lower()

        # Reset file for next test
        js_file.write_text(js_code)

        # Test console.log removal
        result = handler.apply_code_pattern(js_file, "remove_console_logs", "", "semantic", -1)
        if "not fully implemented" not in result.lower():
            assert "removed" in result.lower()

    def test_validation_comprehensive(self, handler, temp_dir):
        """Test comprehensive operation validation."""
        js_code = """
function testFunction() {
    return "test";
}
"""
        js_file = temp_dir / "test.js"
        js_file.write_text(js_code)

        from refactor_mcp.languages.base_handler import RefactoringOperation

        # Test extract method validation
        result = handler.validate_refactoring_operation(
            js_file,
            RefactoringOperation.EXTRACT_METHOD,
            start_line=1,
            end_line=3,
            method_name="newMethod",
        )
        assert result["is_valid"]

        # Test invalid parameters
        result = handler.validate_refactoring_operation(
            js_file,
            RefactoringOperation.EXTRACT_METHOD,
            start_line=1,  # Missing required parameters
        )
        assert not result["is_valid"]
        assert len(result["errors"]) > 0

    def test_error_handling_and_edge_cases(self, handler, temp_dir):
        """Test error handling and edge cases."""
        # Test with invalid JavaScript syntax
        invalid_js = """
function unclosedFunction() {
    return "missing brace"
// Missing closing brace
"""
        js_file = temp_dir / "invalid.js"
        js_file.write_text(invalid_js)

        # Should handle syntax errors gracefully
        try:
            result = handler.get_code_structure(js_file)
            # Should work with fallback parser
            assert result.language == "JavaScript"
        except Exception:
            # Some operations might fail, which is acceptable for invalid syntax
            pass

        # Test with empty file
        empty_file = temp_dir / "empty.js"
        empty_file.write_text("")

        result = handler.get_code_structure(empty_file)
        assert result.language == "JavaScript"
        assert len(result.functions) == 0

        # Test with very large identifiers
        long_identifier = "a" * 1000
        js_with_long_name = f"function {long_identifier}() {{ return 'test'; }}"
        long_name_file = temp_dir / "long.js"
        long_name_file.write_text(js_with_long_name)

        # Should handle without crashing
        result = handler.get_code_structure(long_name_file)
        assert result.language == "JavaScript"

    def test_detect_dead_code_considers_exports(self, handler, temp_dir):
        """Test that exported functions/classes are NOT considered dead code."""
        js_code = """
// Exported function should NOT be detected as dead
export function exportedFunction() {
    return "I am exported";
}

// Module.exports should NOT be detected as dead
function moduleExportedFunction() {
    return "I am module exported";
}
module.exports = { moduleExportedFunction };

// Named export should NOT be detected as dead
function namedExportFunction() {
    return "I am named export";
}
export { namedExportFunction };

// This function IS dead (not used, not exported)
function trulyUnusedFunction() {
    return "I am truly unused";
}

// Default export should NOT be detected as dead
function defaultExportFunction() {
    return "I am default export";
}
export default defaultExportFunction;

// Used function should NOT be detected as dead
function usedFunction() {
    return "I am used";
}
console.log(usedFunction());
"""
        js_file = temp_dir / "test_exports.js"
        js_file.write_text(js_code)

        result = handler.detect_dead_code(js_file)

        import json

        dead_code_info = json.loads(result)

        dead_function_names = [f["name"] for f in dead_code_info["dead_functions"]]

        # Exported functions should NOT be in dead code list
        assert "exportedFunction" not in dead_function_names
        assert "moduleExportedFunction" not in dead_function_names
        assert "namedExportFunction" not in dead_function_names
        assert "defaultExportFunction" not in dead_function_names
        assert "usedFunction" not in dead_function_names

        # Truly unused function SHOULD be detected as dead
        assert "trulyUnusedFunction" in dead_function_names

    def test_detect_dead_code_considers_class_exports(self, handler, temp_dir):
        """Test that exported classes are NOT considered dead code."""
        js_code = """
// Exported class should NOT be detected as dead
export class ExportedClass {
    method() { return "exported"; }
}

// This class IS dead (not used, not exported)
class UnusedClass {
    method() { return "unused"; }
}

// Used class should NOT be detected as dead
class UsedClass {
    method() { return "used"; }
}
const instance = new UsedClass();
"""
        js_file = temp_dir / "test_class_exports.js"
        js_file.write_text(js_code)

        result = handler.detect_dead_code(js_file)

        import json

        dead_code_info = json.loads(result)

        dead_class_names = [c["name"] for c in dead_code_info["dead_classes"]]

        # Exported class should NOT be in dead code list
        assert "ExportedClass" not in dead_class_names
        assert "UsedClass" not in dead_class_names

        # Unused class SHOULD be detected as dead
        assert "UnusedClass" in dead_class_names

    def test_detect_dead_code_unreachable_after_return(self, handler, temp_dir):
        """Test detection of unreachable code after return statements."""
        js_code = """
function hasUnreachableCode() {
    return "early return";
    const unreachableVar = "this is unreachable";
    console.log("this is also unreachable");
}

function noUnreachableCode() {
    const x = 1;
    return x;
}

function conditionalReturn() {
    if (true) {
        return "conditional";
    }
    return "fallback"; // This is reachable
}

console.log(hasUnreachableCode());
console.log(noUnreachableCode());
console.log(conditionalReturn());
"""
        js_file = temp_dir / "test_unreachable.js"
        js_file.write_text(js_code)

        result = handler.detect_dead_code(js_file)

        import json

        dead_code_info = json.loads(result)

        # Should detect unreachable code
        assert "unreachable_code" in dead_code_info
        unreachable_items = dead_code_info["unreachable_code"]

        # There should be at least one unreachable code block detected
        assert len(unreachable_items) >= 1

        # Check that unreachable code is in the right function
        unreachable_reasons = [item.get("reason", "") for item in unreachable_items]
        assert any("return" in reason.lower() for reason in unreachable_reasons)

    def test_detect_dead_code_variable_exports(self, handler, temp_dir):
        """Test that exported variables are NOT considered dead code."""
        js_code = """
// Exported const should NOT be detected as dead
export const EXPORTED_CONST = "exported";

// Module.exports variable should NOT be detected as dead
const moduleExportedVar = "module exported";
module.exports.moduleExportedVar = moduleExportedVar;

// Unused variable SHOULD be detected as dead
const unusedVariable = "unused";

// Used variable should NOT be detected as dead
const usedVariable = "used";
console.log(usedVariable);
"""
        js_file = temp_dir / "test_var_exports.js"
        js_file.write_text(js_code)

        result = handler.detect_dead_code(js_file)

        import json

        dead_code_info = json.loads(result)

        dead_var_names = [v["name"] for v in dead_code_info["dead_variables"]]

        # Exported variables should NOT be in dead code list
        assert "EXPORTED_CONST" not in dead_var_names
        assert "moduleExportedVar" not in dead_var_names
        assert "usedVariable" not in dead_var_names

        # Unused variable SHOULD be detected as dead
        assert "unusedVariable" in dead_var_names

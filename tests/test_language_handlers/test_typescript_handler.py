"""Test TypeScript language handler."""

import pytest

from refactor_mcp.languages.typescript_handler import TypeScriptHandler


class TestTypeScriptHandler:
    """Test TypeScript language handler functionality."""

    @pytest.fixture
    def handler(self):
        """Create TypeScript handler instance."""
        return TypeScriptHandler()

    def test_language_properties(self, handler):
        """Test basic language properties."""
        assert handler.language_name == "TypeScript"
        assert ".ts" in handler.file_extensions
        assert ".tsx" in handler.file_extensions
        assert ".d.ts" in handler.file_extensions

    def test_can_handle_file_by_extension(self, handler, temp_dir):
        """Test file handling by extension."""
        # Test supported extensions
        for ext in [".ts", ".tsx", ".d.ts", ".cts", ".mts"]:
            test_file = temp_dir / f"test{ext}"
            test_file.write_text("console.log('test');")
            if ext in handler.file_extensions:
                assert handler.can_handle_file(test_file)

    def test_can_handle_typescript_patterns(self, handler, temp_dir):
        """Test TypeScript-specific content patterns."""
        patterns = [
            "interface User { name: string; }",
            "type Role = 'admin' | 'user';",
            "function func(): Promise<string> {}",
            "import type { SomeType } from 'module';",
        ]

        for pattern in patterns:
            test_file = temp_dir / "test.unknown"
            test_file.write_text(pattern)
            assert handler.can_handle_file(test_file), f"Failed to detect: {pattern}"

    def test_code_structure_analysis(self, handler, sample_typescript_code, temp_dir):
        """Test TypeScript code structure extraction."""
        ts_file = temp_dir / "test.ts"
        ts_file.write_text(sample_typescript_code)

        structure = handler.get_code_structure(ts_file)

        assert structure.language == "TypeScript"
        assert len(structure.functions) >= 1  # firstFunction
        assert len(structure.classes) >= 1  # UserManager
        assert len(structure.imports) >= 1  # import statements

        # Check for TypeScript-specific elements
        function_names = [f.name for f in structure.functions]
        assert "firstFunction" in function_names

        class_names = [c.name for c in structure.classes]
        assert "UserManager" in class_names

    def test_import_organization(self, handler, temp_dir):
        """Test TypeScript import organization."""
        ts_code = """import type { User } from './types';
import { EventEmitter } from 'events';
import * as fs from 'fs';
import React from 'react';

console.log('test');
"""

        ts_file = temp_dir / "test.ts"
        ts_file.write_text(ts_code)

        result = handler.organize_imports(ts_file)
        assert "successfully" in result.lower() or "organized" in result.lower()

    def test_dependency_analysis(self, handler, sample_typescript_code, temp_dir):
        """Test TypeScript dependency analysis."""
        ts_file = temp_dir / "test.ts"
        ts_file.write_text(sample_typescript_code)

        deps = handler.analyze_dependencies(ts_file)

        assert "file" in deps
        assert "language" in deps
        assert deps["language"] == "TypeScript"
        assert "total_imports" in deps

    def test_interface_detection(self, handler, temp_dir):
        """Test interface and type detection."""
        ts_code = """
interface User {
    id: number;
    name: string;
}

type Status = 'active' | 'inactive';

enum Color {
    Red,
    Green,
    Blue
}

class UserService {
    private users: User[] = [];
}
"""

        ts_file = temp_dir / "test.ts"
        ts_file.write_text(ts_code)

        structure = handler.get_code_structure(ts_file)

        # Should detect classes and potentially interfaces/types
        # (depends on implementation - interfaces might be in classes or separate)
        assert len(structure.classes) >= 1

    def test_detect_dead_code_supported(self, handler):
        """Test that DETECT_DEAD_CODE is in supported operations."""
        from refactor_mcp.languages.base_handler import RefactoringOperation

        assert RefactoringOperation.DETECT_DEAD_CODE in handler.supported_operations

    def test_detect_dead_code_basic(self, handler, temp_dir):
        """Test basic dead code detection for TypeScript."""
        ts_code = """
function usedFunction(): string {
    return "I am used";
}

function unusedFunction(): string {
    return "I am never called";
}

const usedVariable: string = "hello";
const unusedVariable: string = "world";

class UsedClass {
    method(): string { return "used"; }
}

class UnusedClass {
    method(): string { return "unused"; }
}

// Main flow
console.log(usedFunction());
console.log(usedVariable);
const instance = new UsedClass();
console.log(instance.method());
"""
        ts_file = temp_dir / "test.ts"
        ts_file.write_text(ts_code)

        result = handler.detect_dead_code(ts_file)

        import json

        dead_code_info = json.loads(result)

        assert "dead_functions" in dead_code_info
        assert "dead_classes" in dead_code_info
        assert "dead_variables" in dead_code_info

        dead_function_names = [f["name"] for f in dead_code_info["dead_functions"]]
        assert "unusedFunction" in dead_function_names
        assert "usedFunction" not in dead_function_names

        dead_class_names = [c["name"] for c in dead_code_info["dead_classes"]]
        assert "UnusedClass" in dead_class_names
        assert "UsedClass" not in dead_class_names

    def test_detect_dead_code_with_exports(self, handler, temp_dir):
        """Test that exported TypeScript items are NOT considered dead."""
        ts_code = """
// Exported function - NOT dead
export function exportedFunction(): string {
    return "exported";
}

// Exported interface - should be recognized
export interface User {
    id: number;
    name: string;
}

// Exported type - should be recognized
export type Status = 'active' | 'inactive';

// Exported class - NOT dead
export class ExportedClass {
    method(): string { return "exported"; }
}

// Unused function - IS dead
function unusedFunction(): string {
    return "unused";
}

// Unused class - IS dead
class UnusedClass {
    method(): string { return "unused"; }
}
"""
        ts_file = temp_dir / "test_exports.ts"
        ts_file.write_text(ts_code)

        result = handler.detect_dead_code(ts_file)

        import json

        dead_code_info = json.loads(result)

        dead_function_names = [f["name"] for f in dead_code_info["dead_functions"]]
        dead_class_names = [c["name"] for c in dead_code_info["dead_classes"]]

        # Exported items should NOT be in dead code
        assert "exportedFunction" not in dead_function_names
        assert "ExportedClass" not in dead_class_names

        # Unused items SHOULD be in dead code
        assert "unusedFunction" in dead_function_names
        assert "UnusedClass" in dead_class_names

    def test_detect_dead_code_unreachable(self, handler, temp_dir):
        """Test detection of unreachable code in TypeScript."""
        ts_code = """
function hasUnreachable(): string {
    return "early return";
    const unreachable: string = "unreachable";
    console.log(unreachable);
}

function noUnreachable(): number {
    const x: number = 1;
    return x;
}

console.log(hasUnreachable());
console.log(noUnreachable());
"""
        ts_file = temp_dir / "test_unreachable.ts"
        ts_file.write_text(ts_code)

        result = handler.detect_dead_code(ts_file)

        import json

        dead_code_info = json.loads(result)

        # Should detect unreachable code
        assert "unreachable_code" in dead_code_info
        unreachable_items = dead_code_info["unreachable_code"]
        assert len(unreachable_items) >= 1

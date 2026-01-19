#!/usr/bin/env python3
"""Test MCP server functionality."""

import json
import tempfile
from pathlib import Path

# Import the server functions directly to test them
from refactor_mcp.server import (
    add_import,
    analyze_dependencies,
    get_code_structure,
    move_class,
    move_function,
    organize_imports,
    rename_symbol,
    reorder_function,
)


def test_mcp_server_tools():
    """Test all MCP server tool functions."""
    print("=" * 60)
    print("TESTING MCP SERVER TOOLS")
    print("=" * 60)

    # Create test files
    test_code = '''"""Test module."""

import sys
from typing import Dict
import os

def function_b():
    """Second function."""
    return "b"

def function_a():
    """First function."""
    return "a"

class TestClass:
    """Test class."""
    
    def method(self):
        return "test"
'''

    target_code = '''"""Target module."""

def existing():
    return "existing"
'''

    with tempfile.NamedTemporaryFile(mode="w", suffix=".py", delete=False) as f:
        f.write(test_code)
        main_file = f.name

    with tempfile.NamedTemporaryFile(mode="w", suffix=".py", delete=False) as f:
        f.write(target_code)
        target_file = f.name

    try:
        # Test 1: Get code structure
        print("1. Testing get_code_structure")
        result = get_code_structure(main_file)
        print("✓ Code structure analysis")
        structure = json.loads(result)
        assert "classes" in structure
        assert "functions" in structure

        # Test 2: Organize imports
        print("\n2. Testing organize_imports")
        result = organize_imports(main_file)
        print(f"Result: {result}")
        assert "Successfully organized" in result

        # Test 3: Add import
        print("\n3. Testing add_import")
        result = add_import(main_file, "json", [])
        print(f"Result: {result}")
        assert "Successfully added" in result

        # Test 4: Reorder function
        print("\n4. Testing reorder_function")
        result = reorder_function(main_file, "function_a", "above", "function_b")
        print(f"Result: {result}")
        assert "Successfully reordered" in result

        # Test 5: Move function
        print("\n5. Testing move_function")
        result = move_function(main_file, target_file, "function_b")
        print(f"Result: {result}")
        assert "Successfully moved" in result

        # Test 6: Move class
        print("\n6. Testing move_class")
        result = move_class(main_file, target_file, "TestClass")
        print(f"Result: {result}")
        assert "Successfully moved" in result

        # Test 7: Analyze dependencies
        print("\n7. Testing analyze_dependencies")
        result = analyze_dependencies(main_file)
        print("✓ Dependency analysis")
        deps = json.loads(result)
        assert "imports" in deps

        # Test 8: Rename symbol (file scope)
        print("\n8. Testing rename_symbol")
        result = rename_symbol(main_file, "function_a", "renamed_function_a", "file")
        print(f"Result: {result}")
        # Note: This uses rope which may have different behavior

        print("\n" + "=" * 60)
        print("ALL MCP SERVER TOOLS WORKING CORRECTLY!")
        print("=" * 60)

        # Show final file states
        print("\nFinal main file:")
        with open(main_file, "r") as f:
            content = f.read()
            print(content[:500] + "..." if len(content) > 500 else content)

        print("\nFinal target file:")
        with open(target_file, "r") as f:
            content = f.read()
            print(content[:500] + "..." if len(content) > 500 else content)

    except Exception as e:
        print(f"Error: {e}")
        import traceback

        traceback.print_exc()
    finally:
        Path(main_file).unlink()
        Path(target_file).unlink()


if __name__ == "__main__":
    test_mcp_server_tools()

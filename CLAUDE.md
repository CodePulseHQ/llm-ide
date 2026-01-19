# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Overview

This is a Multi-Language Refactor MCP (Model Context Protocol) Server that provides advanced code refactoring tools across 6 programming languages: Python, JavaScript, TypeScript, HTML, CSS, and Go. The server is designed to help LLMs perform precise code modifications with 99% token efficiency compared to full file rewrites.

## Development Commands

### Installation and Setup
```bash
# Install for development
pip install -e .[dev]

# Install production version
pip install -e .
```

### Testing
```bash
# Run all tests
python -m pytest tests/

# Run comprehensive integration tests
python test_comprehensive.py

# Test multi-language functionality
python test_multi_language.py

# Run specific test file
python -m pytest tests/test_function_reordering.py -v

# Run single test function
python -m pytest tests/test_function_reordering.py::test_reorder_function_to_top -v
```

### Code Quality
```bash
# Format code (required before commits)
black refactor_mcp/
isort refactor_mcp/

# Type checking
mypy refactor_mcp/

# Check formatting without changes
black --check refactor_mcp/
isort --check-only refactor_mcp/
```

### Running the Server

**Local Development:**
```bash
# Run MCP server (multi-language support)
python -m refactor_mcp.server

# Alternative: Run with explicit module path
python -m refactor_mcp.server

# Test server functionality
python test_mcp_server.py
```

**Docker:**
```bash
# Build and run with docker-compose
docker-compose up --build

# Run development version with full source mounting
docker-compose --profile dev up --build refactor-mcp-dev

# Build and run with plain Docker
docker build -t refactor-mcp .
docker run -p 8000:8000 refactor-mcp

# Run with workspace volume for file processing
docker run -v $(pwd)/workspace:/workspace -p 8000:8000 refactor-mcp
```

## Architecture

### Core Architecture Pattern
The system uses a **plugin architecture** with language-specific handlers that implement a common interface:

1. **BaseLanguageHandler** (abstract base class) - Defines universal operations
2. **Language Registry** - Auto-detection and handler management  
3. **Multi-Language Server** - MCP endpoints that route to appropriate handlers
4. **Individual Language Handlers** - Language-specific implementations

### Key Components

**`refactor_mcp/languages/base_handler.py`**
- Abstract base class defining `RefactoringOperation` enum and data classes
- Universal interface: `CodeStructure`, `FunctionInfo`, `ClassInfo`, `ImportInfo`
- All language handlers must implement: `get_code_structure()`, `organize_imports()`, `can_handle_file()`

**`refactor_mcp/languages/language_registry.py`**
- Central registry managing all language handlers
- Automatic language detection by file extension, content patterns, and MIME types
- Global functions: `get_handler_for_file()`, `detect_language()`, `register_language_handler()`

**`refactor_mcp/server.py`**
- Main MCP server with FastMCP framework
- Auto-initializes all language handlers at startup
- Universal MCP endpoints that work across all languages
- Each tool function auto-detects language and routes to appropriate handler

**Language Handler Implementation Pattern:**
```python
class SomeLanguageHandler(BaseLanguageHandler):
    @property
    def language_name(self) -> str: return "SomeLanguage"
    
    @property 
    def file_extensions(self) -> List[str]: return [".ext"]
    
    def can_handle_file(self, file_path) -> bool:
        # Extension + content-based validation
    
    def get_code_structure(self, file_path) -> CodeStructure:
        # Parse and return unified structure
```

### Language Support Matrix
- **Python**: Full AST-based parsing with `rope` and native `ast`
- **JavaScript/TypeScript**: Tree-sitter parsing with regex fallback
- **HTML**: BeautifulSoup/lxml parsing for DOM and resource extraction
- **CSS**: CSSUtils with regex fallback for rules and @imports
- **Go**: Tree-sitter parsing with comprehensive regex fallback

### Parsing Strategy
Each handler implements a **dual-parsing strategy**:
1. **Primary**: Language-specific parser (AST, Tree-sitter, etc.)
2. **Fallback**: Regex-based parsing when primary parser fails
3. **Validation**: `can_handle_file()` checks both extension and content patterns

## Tree-sitter Dependency Issue

**Current Issue**: The project uses `tree-sitter-languages>=1.7.0` which has version compatibility issues with newer `tree-sitter` versions, causing "__init__() takes exactly 1 argument (2 given)" errors.

**Current Workaround**: The error is silently handled and regex fallback is used.

**Recommended Fix**: Migrate to official tree-sitter bindings:
```bash
# Replace tree-sitter-languages with official packages
pip uninstall tree-sitter-languages
pip install tree-sitter-javascript tree-sitter-typescript tree-sitter-go
```

**Official API Pattern**:
```python
import tree_sitter_javascript as tsjs
from tree_sitter import Language, Parser

JS_LANGUAGE = Language(tsjs.language())
parser = Parser(JS_LANGUAGE)
```

This would eliminate the Tree-sitter warnings completely and provide more reliable AST parsing.

## Key Principles

### Language Handler Development
- Always implement both primary parsing and regex fallback
- Use language-specific conventions for import organization
- Store language name in lowercase in registry, return proper case in `language_name`
- Implement `validate_syntax()` for error checking before operations

### MCP Server Integration  
- New language handlers are automatically registered in `server.py`
- Add handler import and instantiation to `initialize_handlers()` function
- All existing MCP endpoints automatically support new languages
- Language detection is automatic - no manual specification needed

### Token Efficiency Focus
- Operations should use 2-10 parameters instead of full file content
- Return minimal success/error messages, not full file content
- Use `get_code_structure()` to provide file overview without implementation details
- Surgical operations that modify specific parts without rewriting entire files

### Testing Requirements
- Test both primary parser and regex fallback modes
- Verify language detection accuracy
- Test all supported operations for each language
- Include integration tests with temporary files
- Format code with `black` and `isort` before running tests

### Error Handling Pattern
```python
try:
    # Primary parsing/operation
    return primary_method()
except Exception:
    # Fallback to regex/simpler approach
    return fallback_method()
```

## Adding New Languages

1. Create `refactor_mcp/languages/new_language_handler.py`
2. Implement `BaseLanguageHandler` interface
3. Add to `initialize_handlers()` in `server.py`
4. Update language detection patterns in `language_registry.py` 
5. Add comprehensive tests
6. Update documentation

The architecture is designed for easy extensibility - new languages get full MCP integration automatically once the handler is implemented.

## Feature Parity Table Maintenance

### IMPORTANT: Always Update the README Feature Matrix

When adding new operations or updating language support, **ALWAYS** update the feature parity table in `README.md`. This table is critical for users to understand language capabilities.

### Update Process

1. **When adding new operations to any language handler:**
   ```bash
   # 1. Update the handler's supported_operations property
   # 2. Implement the operation method
   # 3. Update the README feature matrix
   # 4. Update language coverage percentages
   ```

2. **Feature Matrix Location:** `README.md` lines ~17-45

3. **Update Template:**
   ```markdown
   | `new_operation` | ✅ Full | ❌ | ❌ | ❌ | ❌ |
   ```

4. **Coverage Calculation:**
   ```
   Total operations = 15 (as of current implementation)
   Python = 15/15 (100%)
   JS/TS = 7/15 (47%) 
   Go = 8/15 (53%)
   HTML/CSS = 3/15 (20%)
   ```

### Status Legend
- ✅ **Full**: Complete implementation with AST parsing, validation, error handling
- ✅ **Basic**: Working implementation with regex fallback, minimal validation  
- ❌ **Missing**: Operation not implemented in handler's `supported_operations`

### When to Update Status
- **Missing → Basic**: When operation is added to `supported_operations` with minimal implementation
- **Basic → Full**: When operation gets AST parsing, comprehensive validation, and production features
- **Add new row**: When new `RefactoringOperation` is added to base_handler.py

### Language Status Updates
Update the main language status table based on overall coverage:
- **Complete**: 90%+ coverage with full implementations
- **Basic**: 40-89% coverage with working implementations
- **Minimal**: <40% coverage or missing core operations

### Verification Commands
```bash
# Count total operations in base handler
grep -c "= \"" refactor_mcp/languages/base_handler.py

# Check each handler's operation count
grep -A 20 "supported_operations" refactor_mcp/languages/*_handler.py
```

**Remember**: The feature parity table is the first thing users see to understand language capabilities. Keep it accurate and up-to-date!
- Use TDD to ensure that the feature we intend to implement works by the time we've finished. This should also encourage 'functional' tests
# LLM-IDE Refactor MCP Server

A production-ready MCP (Model Context Protocol) server that gives AI coding tools IDE-like intelligence and safe, token-efficient refactoring across multiple languages.

It exposes a unified API for symbol search, navigation, and structured code transformations so LLMs can change code without rewriting whole files.

## Why this exists

LLMs are great at understanding code but burn tokens when they need to scan files and generate full diffs. This server provides precise operations such as "move symbol", "change signature", and "find references" so tools can make surgical edits with minimal context.

## Core capabilities

- Workspace indexing: fast symbol lookup and cross-file analysis
- IDE-like navigation: `find_references`, `go_to_definition`, `get_call_hierarchy`
- Token-saving refactors: `move_symbol`, `safe_delete`, `add_parameter`, `change_signature`, `batch_rename`
- Import management: `organize_imports`, `generate_imports`, `remove_unused_imports`
- Structure-first analysis: `get_code_structure`, `bulk_analysis`
- Unified API across languages with automatic detection

## Supported languages

- Python
- JavaScript
- TypeScript
- Go
- HTML
- CSS

## Install

### Local

```bash
pip install -e .
```

### Docker

```bash
docker build -t llm-ide .
docker run -p 8000:8000 llm-ide
```

## Quick start

### Run the server

```bash
python -m refactor_mcp.server
```

### Claude Desktop config example

```json
{
  "mcpServers": {
    "llm-ide": {
      "command": "python",
      "args": ["-m", "refactor_mcp.server"]
    }
  }
}
```

## Example operations

```python
# Index a workspace
initialize_workspace("/path/to/project")

# Navigate and analyze
find_references("src/app.tsx", "UserCard")
get_call_hierarchy("src/api.py", "fetch_user")
search_symbols("Auth*", "/path/to/project")

# Safe, token-efficient refactors
move_symbol("src/utils.py", "normalize_email", "src/formatters.py")
change_signature("src/api.ts", "getUser", ["id", "includePosts?"])
add_parameter("src/models.go", "NewClient", "timeout", "time.Duration", "5 * time.Second")

# Import management
organize_imports("src/index.ts")
generate_imports("src/main.py")
```

## How it helps AI coding tools

- Smaller prompts: no need to read entire files to make simple edits
- Safer edits: operations update references and imports automatically
- Faster workflows: workspace indexing enables IDE-like navigation
- Consistent API: the same calls work across languages

## Repo layout

```
refactor_mcp/
  server.py
  languages/
  workspace/
  tests/
```

## Development

```bash
python -m pytest tests/ -v
```

## License

MIT

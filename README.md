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

If you are running from source, no extra `PYTHONPATH` is needed as long as you run from the repo root or install with `pip install -e .`.

### Local dev with venv (recommended)

```bash
cd /Users/ash/ash/refactor_mcp
python3 -m venv .venv
source .venv/bin/activate
pip install -U pip
pip install -e '.[dev]'
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

### Filesystem access (important)

The server can only read/write files that are visible to its process. Use absolute paths when calling tools.

Local:
- Run the server on the same machine and point to real paths, e.g. `initialize_workspace("/Users/you/project")`.

Docker:
- Bind-mount the repo into the container and use the mounted path in tool calls.

```bash
docker run -p 8000:8000 -v /path/to/repo:/workspace llm-ide
```

Then call:

```python
initialize_workspace("/workspace")
```

### Codex CLI (local agents)

If your coding agent runs locally (Codex CLI or similar), the MCP server must run on the same machine and point to absolute paths in your workspace. No special environment variables are required beyond having the repo path readable/writable by the server process.

Typical flow:

```bash
pip install -e .[dev]
python -m refactor_mcp.server
```

Then configure your client to use the same MCP server command shown above, and call tools with absolute paths, e.g. `initialize_workspace("/Users/you/project")`.

If you run `codex` from a workspace directory, treat that directory as your root and pass its absolute path to `initialize_workspace`. If you work across multiple repos, initialize each one separately (e.g., `/path/to/repo-a`, `/path/to/repo-b`). If the agent runs in a sandbox, ensure the server process has read/write access to those paths; otherwise it will not be able to modify files.

Codex CLI example:

```bash
codex mcp add llm-ide -- /path/to/repo/.venv/bin/python -m refactor_mcp.server
```

### Workspace indexing

`initialize_workspace(root_path)` is optional, but strongly recommended for IDE-like operations. It can take a bit on large repos, so it is not run automatically. Use `list_workspaces()` to see active indexes and `refresh_workspace(workspace_id)` when files change significantly.

When a workspace is initialized, a lightweight file watcher (using `watchdog`) keeps the index fresh for edits that happen outside the MCP server. It ignores heavy directories like `node_modules`, `.git`, and build artifacts.

You can disable the watcher by setting `REFACTOR_MCP_DISABLE_WATCHER=1` in the server environment.

Auto-indexing behavior:
- `REFACTOR_MCP_AUTO_INDEX=1` (default) will build or refresh the index if the cache is stale.
- `REFACTOR_MCP_FORCE_REINDEX=1` forces a full re-index every time `initialize_workspace` runs.

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

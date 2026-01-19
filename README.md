# LLM-IDE Refactor MCP Server

An MCP server that gives AI coding tools IDE-like navigation and precise, token-efficient refactors.

[Understand Why Features Aren't Shipping Faster](https://codepulsehq.com)

In 15 minutes, see exactly where engineering time goes - using only Git metadata, never your source code.

## What it does

- Indexes a workspace for fast symbol search and navigation
- Exposes safe, structured edits (`find_references`, `move_symbol`, `change_signature`)
- Supports Python, JavaScript, TypeScript, Go, HTML, CSS

## How it saves tokens (examples)

- Rename a symbol across 10 files without collecting context or crafting diffs for each file.
  Rough savings: each file still needs context for safe patching; even 20–40 lines per file (~400–800 tokens)
  is ~4k–8k tokens avoided at 10 files.
- Change a function signature and update call sites with one tool call instead of manual diffs for each call site.
- Move a symbol between files and update imports without loading both files to build the patch.

## Add MCP server

The MCP client will launch the server on demand using the command below.

Codex CLI:
```bash
codex mcp add llm-ide -- /path/to/repo/.venv/bin/python -m refactor_mcp.server
```

Claude Code:
```bash
claude mcp add llm-ide -- /path/to/repo/.venv/bin/python -m refactor_mcp.server
```

## Suggested CLAUDE.md snippet

If your repo uses `CLAUDE.md`, add a short note to encourage token-saving tool use:

```md
## MCP (LLM-IDE)

Use the LLM-IDE MCP tools proactively to reduce token usage.
Prefer structured operations (find references, rename, move, signature changes)
over manual diff editing. Fetch only needed context (symbols/ranges) instead of
reading whole files.
```

## Local setup (venv)

```bash
cd /path/to/refactor_mcp
python3 -m venv .venv
source .venv/bin/activate
pip install -U pip
pip install -e '.[dev]'
```

## Docker

```bash
docker build -t llm-ide .
docker run -p 8000:8000 -v /path/to/your/repo:/workspace llm-ide
```

## Big repo controls (env vars)

- `REFACTOR_MCP_DISABLE_WATCHER=1` disables the file watcher.
- `REFACTOR_MCP_AUTO_INDEX=0` disables auto indexing on `initialize_workspace`.
- `REFACTOR_MCP_FORCE_REINDEX=1` forces a full re-index every time.

"""Multi-language MCP Server for code refactoring operations."""

import difflib
import functools
import hashlib
import json
import os
import tempfile
import time
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

from mcp.server.fastmcp import FastMCP

from . import health_checks
from .health_checks import HealthStatus, health_checker
from .languages import language_registry
from .languages.css_handler import CSSHandler
from .languages.go_handler import GoHandler
from .languages.html_handler import HTMLHandler
from .languages.javascript_handler import JavaScriptHandler
from .languages.python_handler import PythonHandler
from .languages.typescript_handler import TypeScriptHandler
from .logging_config import (
    PerformanceLogger,
    log_operation_metrics,
    security_logger,
    server_logger,
    setup_logging,
)
from .workspace import (  # Core workspace components; Phase 2: Token-saving operations
    BatchOperations,
    CallGraphAnalyzer,
    DefinitionResolver,
    ImportGenerator,
    ReferenceFinder,
    SignatureChanger,
    SymbolMover,
    WorkspaceManager,
    WorkspaceOperations,
)

# Initialize structured logging
log_level = os.getenv("LOG_LEVEL", "INFO")
log_file = os.getenv("LOG_FILE")
structured_logging = os.getenv("STRUCTURED_LOGGING", "true").lower() == "true"

setup_logging(
    level=log_level,
    log_file=Path(log_file) if log_file else None,
    structured=structured_logging,
    console=True,
)

logger = server_logger

# Create the FastMCP server
mcp = FastMCP("Multi-Language Refactor MCP Server")

# Expose registry helpers for patching in tests
register_language_handler = language_registry.register_language_handler


def _json_success(data: Any = None, **extra: Any) -> str:
    payload: Dict[str, Any] = {"success": True, "data": data}
    payload.update(extra)
    return json.dumps(payload, indent=2)


def _json_error(message: str, **extra: Any) -> str:
    payload: Dict[str, Any] = {"success": False, "error": message}
    payload.update(extra)
    return json.dumps(payload, indent=2)


def _wrap_tool_result(result: Any) -> str:
    if isinstance(result, str):
        try:
            parsed = json.loads(result)
        except Exception:
            lowered = result.strip().lower()
            if (
                lowered.startswith("error")
                or lowered.startswith("failed")
                or "not supported" in lowered
                or "dead code removal requires confirmation" in lowered
            ):
                return _json_error(result)
            return _json_success(result)

        if isinstance(parsed, dict) and "error" in parsed:
            data = {k: v for k, v in parsed.items() if k != "error"}
            return _json_error(parsed.get("error", "Unknown error"), **({"data": data} if data else {}))
        return _json_success(parsed)

    return _json_success(result)


def mcp_tool(func):  # type: ignore[override]
    @functools.wraps(func)
    def _wrapped(*args, **kwargs):
        try:
            result = func(*args, **kwargs)
        except Exception as exc:
            logger.error("Tool execution failed", exc_info=True)
            return _json_error(str(exc))
        return _wrap_tool_result(result)

    return mcp.tool()(_wrapped)


def _handler_supports_operation(handler: Any, operation: str) -> bool:
    if not handler:
        return False
    supported = getattr(handler, "supported_operations", None)
    if supported is None:
        return True
    try:
        from .languages.base_handler import RefactoringOperation

        op_enum = RefactoringOperation(operation)
    except ValueError:
        return False
    try:
        return op_enum in supported
    except TypeError:
        return True


def _missing_handler_error(file_path: str) -> Dict[str, Any]:
    return {"error": f"No suitable handler found for file: {file_path}"}


# Initialize and register language handlers
def initialize_handlers():
    """Initialize and register all language handlers."""
    with PerformanceLogger(logger, "initialize_handlers"):
        handlers = [
            PythonHandler(),
            JavaScriptHandler(),
            TypeScriptHandler(),
            HTMLHandler(),
            CSSHandler(),
            GoHandler(),
        ]

        registered_count = 0
        for handler in handlers:
            try:
                register_language_handler(handler)
                logger.info(
                    f"Registered language handler: {handler.language_name}",
                    extra={
                        "extra_fields": {
                            "handler": handler.language_name,
                            "extensions": handler.file_extensions,
                            "status": "registered",
                        }
                    },
                )
                registered_count += 1
            except Exception as e:
                logger.error(
                    f"Failed to register handler: {handler.language_name}",
                    extra={
                        "extra_fields": {
                            "handler": handler.language_name,
                            "error": str(e),
                            "status": "failed",
                        }
                    },
                    exc_info=True,
                )

        logger.info(
            "Handler initialization complete",
            extra={
                "extra_fields": {
                    "total_handlers": len(handlers),
                    "registered_handlers": registered_count,
                    "failed_handlers": len(handlers) - registered_count,
                }
            },
        )
        return {
            "handlers": [h.language_name for h in handlers],
            "total_handlers": len(handlers),
            "registered_handlers": registered_count,
            "failed_handlers": len(handlers) - registered_count,
        }


# Initialize handlers on module load
initialize_handlers()


def _compute_text_hash(content: str) -> str:
    """Compute a stable hash of file content."""
    return hashlib.sha256(content.encode("utf-8")).hexdigest()


def _compute_bytes_hash(content: bytes) -> str:
    """Compute a stable hash of binary content."""
    return hashlib.sha256(content).hexdigest()


def _apply_text_edits_to_content(
    content: str, edits: List[Dict[str, Any]]
) -> Dict[str, Any]:
    """Apply LSP-style text edits to content."""
    errors: List[str] = []
    if not edits:
        return {"content": content, "errors": errors, "edit_count": 0}

    lines = content.splitlines(keepends=True)
    line_offsets = [0]
    running = 0
    for line in lines:
        running += len(line)
        line_offsets.append(running)

    normalized_edits: List[Dict[str, Any]] = []
    for idx, edit in enumerate(edits):
        try:
            start_line = int(edit.get("start_line"))
            start_column = int(edit.get("start_column", 0))
            end_line = int(edit.get("end_line"))
            end_column = int(edit.get("end_column", 0))
            new_text = edit.get("new_text", "")
        except (TypeError, ValueError):
            errors.append(f"Edit {idx}: invalid line/column values")
            continue

        if start_line < 1 or end_line < 1:
            errors.append(f"Edit {idx}: line numbers must be >= 1")
            continue
        if start_line > len(lines) or end_line > len(lines):
            errors.append(f"Edit {idx}: line out of range")
            continue

        start_line_text = lines[start_line - 1]
        end_line_text = lines[end_line - 1]
        start_line_len = (
            len(start_line_text[:-1]) if start_line_text.endswith("\n") else len(start_line_text)
        )
        end_line_len = (
            len(end_line_text[:-1]) if end_line_text.endswith("\n") else len(end_line_text)
        )

        if start_column < 0 or start_column > start_line_len:
            errors.append(f"Edit {idx}: start_column out of range")
            continue
        if end_column < 0 or end_column > end_line_len:
            errors.append(f"Edit {idx}: end_column out of range")
            continue

        start_offset = line_offsets[start_line - 1] + start_column
        end_offset = line_offsets[end_line - 1] + end_column

        if end_offset < start_offset:
            errors.append(f"Edit {idx}: end before start")
            continue

        normalized_edits.append(
            {
                "start_offset": start_offset,
                "end_offset": end_offset,
                "new_text": new_text,
                "start_line": start_line,
                "start_column": start_column,
                "end_line": end_line,
                "end_column": end_column,
            }
        )

    if errors:
        return {"content": content, "errors": errors, "edit_count": 0}

    normalized_edits.sort(key=lambda e: (e["start_offset"], e["end_offset"]))
    prev_end = -1
    for edit in normalized_edits:
        if edit["start_offset"] < prev_end:
            errors.append("Edits overlap; apply separately")
            break
        prev_end = edit["end_offset"]

    if errors:
        return {"content": content, "errors": errors, "edit_count": 0}

    updated = content
    for edit in sorted(normalized_edits, key=lambda e: e["start_offset"], reverse=True):
        updated = (
            updated[: edit["start_offset"]]
            + edit["new_text"]
            + updated[edit["end_offset"] :]
        )

    return {
        "content": updated,
        "errors": [],
        "edit_count": len(normalized_edits),
        "normalized_edits": normalized_edits,
    }


def _get_file_hash(file_path: str) -> Optional[str]:
    try:
        content = Path(file_path).read_text(encoding="utf-8")
    except Exception:
        return None
    return _compute_text_hash(content)


def _preview_file_operation(
    file_path: str, apply_operation: Any
) -> Dict[str, Any]:
    """Run an operation on a temp copy and return a unified diff."""
    original_content = Path(file_path).read_text(encoding="utf-8")
    original_hash = _compute_text_hash(original_content)

    with tempfile.NamedTemporaryFile(
        mode="w", suffix=Path(file_path).suffix, delete=False
    ) as temp_file:
        temp_file.write(original_content)
        temp_path = temp_file.name

    try:
        apply_operation(temp_path)
        new_content = Path(temp_path).read_text(encoding="utf-8")
    finally:
        Path(temp_path).unlink(missing_ok=True)

    new_hash = _compute_text_hash(new_content)
    diff = "\n".join(
        difflib.unified_diff(
            original_content.splitlines(),
            new_content.splitlines(),
            fromfile=file_path,
            tofile=file_path,
            lineterm="",
        )
    )

    return {
        "file_path": file_path,
        "original_hash": original_hash,
        "new_hash": new_hash,
        "diff": diff,
    }


def _transactional_file_operation(
    file_path: str, apply_operation: Any
) -> Dict[str, Any]:
    """Preview and apply a file operation atomically if unchanged."""
    preview = _preview_file_operation(file_path, apply_operation)
    current_hash = _get_file_hash(file_path)
    if current_hash != preview["original_hash"]:
        return {
            "error": "File hash mismatch",
            "file_path": file_path,
            "expected": preview["original_hash"],
            "actual": current_hash,
        }

    apply_operation(file_path)
    applied_hash = _get_file_hash(file_path)
    return {
        **preview,
        "applied": True,
        "applied_hash": applied_hash,
    }


def _preview_move_operation(
    source_file: str,
    target_file: str,
    apply_operation: Any,
) -> Dict[str, Any]:
    """Preview a two-file move by running it on temp copies."""
    source_content = Path(source_file).read_text(encoding="utf-8")
    target_content = Path(target_file).read_text(encoding="utf-8")

    with tempfile.NamedTemporaryFile(
        mode="w", suffix=Path(source_file).suffix, delete=False
    ) as src_tmp, tempfile.NamedTemporaryFile(
        mode="w", suffix=Path(target_file).suffix, delete=False
    ) as tgt_tmp:
        src_tmp.write(source_content)
        tgt_tmp.write(target_content)
        src_path = src_tmp.name
        tgt_path = tgt_tmp.name

    try:
        apply_operation(src_path, tgt_path)
        new_source = Path(src_path).read_text(encoding="utf-8")
        new_target = Path(tgt_path).read_text(encoding="utf-8")
    finally:
        Path(src_path).unlink(missing_ok=True)
        Path(tgt_path).unlink(missing_ok=True)

    return {
        "files": [
            {
                "file_path": source_file,
                "original_hash": _compute_text_hash(source_content),
                "new_hash": _compute_text_hash(new_source),
                "diff": "\n".join(
                    difflib.unified_diff(
                        source_content.splitlines(),
                        new_source.splitlines(),
                        fromfile=source_file,
                        tofile=source_file,
                        lineterm="",
                    )
                ),
            },
            {
                "file_path": target_file,
                "original_hash": _compute_text_hash(target_content),
                "new_hash": _compute_text_hash(new_target),
                "diff": "\n".join(
                    difflib.unified_diff(
                        target_content.splitlines(),
                        new_target.splitlines(),
                        fromfile=target_file,
                        tofile=target_file,
                        lineterm="",
                    )
                ),
            },
        ]
    }


def _validate_expected_hashes(
    file_paths: List[str],
    expected_hashes: Optional[Dict[str, str]],
    expected_mtimes: Optional[Dict[str, float]] = None,
) -> Optional[Dict[str, Any]]:
    if not expected_hashes and not expected_mtimes:
        return None

    missing_hashes: List[str] = []
    hash_mismatched: List[Dict[str, str]] = []
    missing_mtimes: List[str] = []
    mtime_mismatched: List[Dict[str, Any]] = []

    for file_path in file_paths:
        if expected_hashes is not None:
            if file_path not in expected_hashes:
                missing_hashes.append(file_path)
            else:
                actual = _get_file_hash(file_path)
                if actual is None:
                    hash_mismatched.append(
                        {
                            "file_path": file_path,
                            "expected": expected_hashes[file_path],
                            "actual": None,
                        }
                    )
                elif actual != expected_hashes[file_path]:
                    hash_mismatched.append(
                        {
                            "file_path": file_path,
                            "expected": expected_hashes[file_path],
                            "actual": actual,
                        }
                    )

        if expected_mtimes is not None:
            if file_path not in expected_mtimes:
                missing_mtimes.append(file_path)
            else:
                try:
                    actual_mtime = Path(file_path).stat().st_mtime
                except OSError:
                    actual_mtime = None
                if actual_mtime != expected_mtimes[file_path]:
                    mtime_mismatched.append(
                        {
                            "file_path": file_path,
                            "expected": expected_mtimes[file_path],
                            "actual": actual_mtime,
                        }
                    )

    if missing_hashes or hash_mismatched or missing_mtimes or mtime_mismatched:
        return {
            "error": "File precondition mismatch",
            "missing_hashes": missing_hashes,
            "hash_mismatched": hash_mismatched,
            "missing_mtimes": missing_mtimes,
            "mtime_mismatched": mtime_mismatched,
        }

    return None


@mcp_tool
def get_supported_languages() -> str:
    """
    Get list of supported programming languages.

    Returns:
        JSON string with supported languages and their file extensions
    """
    start_time = time.time()
    try:
        with PerformanceLogger(logger, "get_supported_languages"):
            languages = language_registry.list_supported_languages()
            extensions = language_registry.list_supported_extensions()

            result = {
                "supported_languages": languages,
                "supported_extensions": extensions,
                "total_languages": len(languages),
            }

            logger.info(
                "Retrieved supported languages",
                extra={
                    "extra_fields": {
                        "operation": "get_supported_languages",
                        "language_count": len(languages),
                        "extension_count": len(extensions),
                    }
                },
            )

            return json.dumps(result, indent=2)
    except Exception as e:
        duration = (time.time() - start_time) * 1000
        logger.error(
            "Failed to get supported languages",
            extra={
                "extra_fields": {
                    "operation": "get_supported_languages",
                    "error": str(e),
                    "duration_ms": round(duration, 2),
                }
            },
            exc_info=True,
        )
        return f"Error getting supported languages: {str(e)}"


@mcp_tool
def detect_file_language(file_path: str) -> str:
    """
    Detect the programming language of a file.

    Args:
        file_path: Path to the file

    Returns:
        Detected language name or error message
    """
    try:
        language = language_registry.detect_language(file_path)

        if language:
            handler = language_registry.get_handler_by_language(language)
            display_language = handler.language_name if handler else language
            return json.dumps(
                {
                    "language": display_language,
                    "file_path": file_path,
                    "supported_operations": (
                        [op.value for op in handler.supported_operations] if handler else []
                    ),
                },
                indent=2,
            )
        else:
            return json.dumps(
                {
                    "language": None,
                    "file_path": file_path,
                    "error": "Could not detect language for this file",
                },
                indent=2,
            )

    except Exception as e:
        return f"Error detecting language: {str(e)}"


@mcp_tool
def reorder_function(
    file_path: str,
    function_name: str,
    target_position: str = "top",
    above_function: Optional[str] = None,
    language: Optional[str] = None,
    preview: bool = False,
    transactional: bool = False,
    expected_hash: Optional[str] = None,
    expected_mtime: Optional[float] = None,
) -> str:
    """
    Reorder a function within a file (multi-language support).

    Args:
        file_path: Path to the source file
        function_name: Name of the function to move
        target_position: "top", "bottom", or "above" (requires above_function)
        above_function: Function name to position above (when target_position="above")
        language: Optional language override (auto-detected if not provided)

    Returns:
        Success message or error details
    """
    try:
        resolved_path = str(Path(file_path).resolve())
        if expected_hash or expected_mtime is not None:
            expected_mtimes = {resolved_path: expected_mtime} if expected_mtime is not None else None
            error = _validate_expected_hashes(
                [resolved_path],
                {resolved_path: expected_hash} if expected_hash else None,
                expected_mtimes,
            )
            if error:
                return json.dumps(error, indent=2)

        valid_positions = {"top", "bottom", "above"}
        if target_position not in valid_positions:
            return f"Invalid target position: {target_position}"
        if target_position == "above" and not above_function:
            return "Target position 'above' requires above_function"

        handler = (
            language_registry.get_handler_for_file(file_path) if not language else language_registry.get_handler_by_language(language)
        )
        if not handler:
            return json.dumps(_missing_handler_error(file_path), indent=2)

        if transactional and preview:
            return json.dumps(
                {"error": "Preview cannot be combined with transactional apply"}, indent=2
            )

        if not _handler_supports_operation(handler, "reorder_function"):
            return f"Function reordering not supported for {handler.language_name}"

        if transactional:
            return json.dumps(
                _transactional_file_operation(
                    file_path,
                    lambda path: handler.reorder_function(
                        path, function_name, target_position, above_function
                    ),
                ),
                indent=2,
            )

        if preview:
            return json.dumps(
                _preview_file_operation(
                    file_path,
                    lambda path: handler.reorder_function(
                        path, function_name, target_position, above_function
                    ),
                ),
                indent=2,
            )

        return handler.reorder_function(file_path, function_name, target_position, above_function)
    except Exception as e:
        return f"Error reordering function: {str(e)}"


@mcp_tool
def organize_imports(
    file_path: str,
    language: Optional[str] = None,
    preview: bool = False,
    transactional: bool = False,
    expected_hash: Optional[str] = None,
    expected_mtime: Optional[float] = None,
) -> str:
    """
    Organize and clean up imports in a file (multi-language support).

    Args:
        file_path: Path to the source file
        language: Optional language override (auto-detected if not provided)

    Returns:
        Success message or error details
    """
    try:
        resolved_path = str(Path(file_path).resolve())
        if expected_hash or expected_mtime is not None:
            expected_mtimes = {resolved_path: expected_mtime} if expected_mtime is not None else None
            error = _validate_expected_hashes(
                [resolved_path],
                {resolved_path: expected_hash} if expected_hash else None,
                expected_mtimes,
            )
            if error:
                return json.dumps(error, indent=2)

        try:
            Path(file_path).read_text(encoding="utf-8")
        except UnicodeDecodeError as e:
            return json.dumps({"error": f"Encoding error: {str(e)}"}, indent=2)

        try:
            temp_path = Path(file_path).with_suffix(Path(file_path).suffix + ".permcheck")
            temp_path.write_text("", encoding="utf-8")
            temp_path.unlink(missing_ok=True)
        except PermissionError as e:
            return json.dumps({"error": f"Permission error: {str(e)}"}, indent=2)

        handler = (
            language_registry.get_handler_for_file(file_path) if not language else language_registry.get_handler_by_language(language)
        )
        if not handler:
            return json.dumps(_missing_handler_error(file_path), indent=2)

        if transactional and preview:
            return json.dumps(
                {"error": "Preview cannot be combined with transactional apply"}, indent=2
            )

        if not _handler_supports_operation(handler, "organize_imports"):
            return f"Import organization not supported for {handler.language_name}"

        if transactional:
            return json.dumps(
                _transactional_file_operation(
                    file_path,
                    lambda path: handler.organize_imports(path),
                ),
                indent=2,
            )

        if preview:
            return json.dumps(
                _preview_file_operation(
                    file_path,
                    lambda path: handler.organize_imports(path),
                ),
                indent=2,
            )

        return handler.organize_imports(file_path)
    except Exception as e:
        return f"Error organizing imports: {str(e)}"


@mcp_tool
def add_import(
    file_path: str,
    module: str,
    symbols: Optional[List[str]] = None,
    language: Optional[str] = None,
    preview: bool = False,
    transactional: bool = False,
    expected_hash: Optional[str] = None,
    expected_mtime: Optional[float] = None,
) -> str:
    """
    Add an import statement to a file (multi-language support).

    Args:
        file_path: Path to the source file
        module: Module name to import
        symbols: Specific symbols to import (for "from" imports)
        language: Optional language override (auto-detected if not provided)

    Returns:
        Success message or error details
    """
    try:
        resolved_path = str(Path(file_path).resolve())
        if expected_hash or expected_mtime is not None:
            expected_mtimes = {resolved_path: expected_mtime} if expected_mtime is not None else None
            error = _validate_expected_hashes(
                [resolved_path],
                {resolved_path: expected_hash} if expected_hash else None,
                expected_mtimes,
            )
            if error:
                return json.dumps(error, indent=2)

        if not module:
            return json.dumps({"error": "Module name is required"}, indent=2)

        handler = (
            language_registry.get_handler_for_file(file_path) if not language else language_registry.get_handler_by_language(language)
        )
        if not handler:
            return json.dumps(_missing_handler_error(file_path), indent=2)

        if transactional and preview:
            return json.dumps(
                {"error": "Preview cannot be combined with transactional apply"}, indent=2
            )

        if not _handler_supports_operation(handler, "add_import"):
            return f"Import addition not supported for {handler.language_name}"

        if transactional:
            return json.dumps(
                _transactional_file_operation(
                    file_path,
                    lambda path: handler.add_import(path, module, symbols or []),
                ),
                indent=2,
            )

        if preview:
            return json.dumps(
                _preview_file_operation(
                    file_path,
                    lambda path: handler.add_import(path, module, symbols or []),
                ),
                indent=2,
            )

        return handler.add_import(file_path, module, symbols or [])
    except Exception as e:
        return f"Error adding import: {str(e)}"


@mcp_tool
def remove_unused_imports(
    file_path: str,
    language: Optional[str] = None,
    preview: bool = False,
    transactional: bool = False,
    expected_hash: Optional[str] = None,
    expected_mtime: Optional[float] = None,
) -> str:
    """
    Remove unused imports from a file (multi-language support).

    Args:
        file_path: Path to the source file
        language: Optional language override (auto-detected if not provided)

    Returns:
        Success message or error details
    """
    try:
        resolved_path = str(Path(file_path).resolve())
        if expected_hash or expected_mtime is not None:
            expected_mtimes = {resolved_path: expected_mtime} if expected_mtime is not None else None
            error = _validate_expected_hashes(
                [resolved_path],
                {resolved_path: expected_hash} if expected_hash else None,
                expected_mtimes,
            )
            if error:
                return json.dumps(error, indent=2)

        handler = (
            language_registry.get_handler_for_file(file_path) if not language else language_registry.get_handler_by_language(language)
        )
        if not handler:
            return json.dumps(_missing_handler_error(file_path), indent=2)

        if transactional and preview:
            return json.dumps(
                {"error": "Preview cannot be combined with transactional apply"}, indent=2
            )

        if not _handler_supports_operation(handler, "remove_unused_imports"):
            return f"Unused import removal not supported for {handler.language_name}"

        if transactional:
            return json.dumps(
                _transactional_file_operation(
                    file_path,
                    lambda path: handler.remove_unused_imports(path),
                ),
                indent=2,
            )

        if preview:
            return json.dumps(
                _preview_file_operation(
                    file_path,
                    lambda path: handler.remove_unused_imports(path),
                ),
                indent=2,
            )

        return handler.remove_unused_imports(file_path)
    except Exception as e:
        return f"Error removing unused imports: {str(e)}"


@mcp_tool
def move_function(
    source_file: str,
    target_file: str,
    function_name: str,
    language: Optional[str] = None,
    preview: bool = False,
    transactional: bool = False,
    expected_hashes: Optional[Dict[str, str]] = None,
    expected_mtimes: Optional[Dict[str, float]] = None,
) -> str:
    """
    Move a function from one file to another (multi-language support).

    Args:
        source_file: Path to source file
        target_file: Path to target file
        function_name: Name of the function to move
        language: Optional language override (auto-detected if not provided)

    Returns:
        Success message or error details
    """
    try:
        resolved_source = str(Path(source_file).resolve())
        resolved_target = str(Path(target_file).resolve())
        if expected_hashes or expected_mtimes:
            error = _validate_expected_hashes(
                [resolved_source, resolved_target], expected_hashes, expected_mtimes
            )
            if error:
                return json.dumps(error, indent=2)

        if transactional and preview:
            return json.dumps(
                {"error": "Preview cannot be combined with transactional apply"}, indent=2
            )

        if language:
            handler = language_registry.get_handler_by_language(language)
            if not handler:
                return json.dumps(_missing_handler_error(source_file), indent=2)
        else:
            source_handler = language_registry.get_handler_for_file(source_file)
            if not source_handler:
                return json.dumps(
                    {"error": f"No suitable handler found for source file: {source_file}"},
                    indent=2,
                )
            target_handler = language_registry.get_handler_for_file(target_file)
            if not target_handler:
                return json.dumps(
                    {"error": f"No suitable handler found for target file: {target_file}"},
                    indent=2,
                )
            if source_handler.language_name != target_handler.language_name:
                return json.dumps(
                    {"error": "Source and target files use different languages"}, indent=2
                )
            handler = source_handler

        if not _handler_supports_operation(handler, "move_function"):
            return f"Function movement not supported for {handler.language_name}"

        if preview:
            return json.dumps(
                _preview_move_operation(
                    source_file,
                    target_file,
                    lambda src, tgt: handler.move_function(src, tgt, function_name),
                ),
                indent=2,
            )

        if transactional:
            preview_data = _preview_move_operation(
                source_file,
                target_file,
                lambda src, tgt: handler.move_function(src, tgt, function_name),
            )
            hashes = {
                source_file: _get_file_hash(source_file),
                target_file: _get_file_hash(target_file),
            }
            mismatch = []
            for item in preview_data.get("files", []):
                if hashes.get(item["file_path"]) != item["original_hash"]:
                    mismatch.append(
                        {
                            "file_path": item["file_path"],
                            "expected": item["original_hash"],
                            "actual": hashes.get(item["file_path"]),
                        }
                    )
            if mismatch:
                return json.dumps(
                    {"error": "File hash mismatch", "mismatched": mismatch}, indent=2
                )

            handler.move_function(source_file, target_file, function_name)
            preview_data["applied"] = True
            preview_data["applied_hashes"] = {
                source_file: _get_file_hash(source_file),
                target_file: _get_file_hash(target_file),
            }
            return json.dumps(preview_data, indent=2)

        return handler.move_function(source_file, target_file, function_name)
    except NotImplementedError as e:
        return str(e)
    except Exception as e:
        return f"Error moving function: {str(e)}"


@mcp_tool
def move_class(
    source_file: str,
    target_file: str,
    class_name: str,
    language: Optional[str] = None,
    preview: bool = False,
    transactional: bool = False,
    expected_hashes: Optional[Dict[str, str]] = None,
    expected_mtimes: Optional[Dict[str, float]] = None,
) -> str:
    """
    Move a class from one file to another (multi-language support).

    Args:
        source_file: Path to source file
        target_file: Path to target file
        class_name: Name of the class to move
        language: Optional language override (auto-detected if not provided)

    Returns:
        Success message or error details
    """
    try:
        resolved_source = str(Path(source_file).resolve())
        resolved_target = str(Path(target_file).resolve())
        if expected_hashes or expected_mtimes:
            error = _validate_expected_hashes(
                [resolved_source, resolved_target], expected_hashes, expected_mtimes
            )
            if error:
                return json.dumps(error, indent=2)

        if transactional and preview:
            return json.dumps(
                {"error": "Preview cannot be combined with transactional apply"}, indent=2
            )

        handler = (
            language_registry.get_handler_for_file(source_file) if not language else language_registry.get_handler_by_language(language)
        )
        if not handler:
            return json.dumps(_missing_handler_error(source_file), indent=2)

        if not _handler_supports_operation(handler, "move_class"):
            return f"Class movement not supported for {handler.language_name}"

        if preview:
            return json.dumps(
                _preview_move_operation(
                    source_file,
                    target_file,
                    lambda src, tgt: handler.move_class(src, tgt, class_name),
                ),
                indent=2,
            )

        if transactional:
            preview_data = _preview_move_operation(
                source_file,
                target_file,
                lambda src, tgt: handler.move_class(src, tgt, class_name),
            )
            hashes = {
                source_file: _get_file_hash(source_file),
                target_file: _get_file_hash(target_file),
            }
            mismatch = []
            for item in preview_data.get("files", []):
                if hashes.get(item["file_path"]) != item["original_hash"]:
                    mismatch.append(
                        {
                            "file_path": item["file_path"],
                            "expected": item["original_hash"],
                            "actual": hashes.get(item["file_path"]),
                        }
                    )
            if mismatch:
                return json.dumps(
                    {"error": "File hash mismatch", "mismatched": mismatch}, indent=2
                )

            handler.move_class(source_file, target_file, class_name)
            preview_data["applied"] = True
            preview_data["applied_hashes"] = {
                source_file: _get_file_hash(source_file),
                target_file: _get_file_hash(target_file),
            }
            return json.dumps(preview_data, indent=2)

        return handler.move_class(source_file, target_file, class_name)
    except NotImplementedError as e:
        return str(e)
    except Exception as e:
        return f"Error moving class: {str(e)}"


@mcp_tool
def get_code_structure(file_path: str, language: Optional[str] = None) -> str:
    """
    Get the structure of a source file (multi-language support).

    Args:
        file_path: Path to the source file
        language: Optional language override (auto-detected if not provided)

    Returns:
        JSON string with code structure
    """
    start_time = time.time()
    detected_language = None

    try:
        with PerformanceLogger(
            logger, "get_code_structure", file_path=file_path, language_override=language
        ):
            handler = (
                language_registry.get_handler_for_file(file_path)
                if not language
                else language_registry.get_handler_by_language(language)
            )
            if not handler:
                return json.dumps(_missing_handler_error(file_path), indent=2)

            detected_language = handler.language_name

            # Security check: validate file path
            path = Path(file_path)
            if not path.exists():
                raise FileNotFoundError(f"File not found: {file_path}")

            security_logger.info(
                "File access requested",
                extra={
                    "extra_fields": {
                        "file_path": file_path,
                        "operation": "get_code_structure",
                        "language": detected_language,
                    }
                },
            )

            if not _handler_supports_operation(handler, "get_code_structure"):
                return f"Code structure analysis not supported for {handler.language_name}"

            structure = handler.get_code_structure(file_path)

            # Log operation metrics
            duration = (time.time() - start_time) * 1000
            log_operation_metrics(
                logger=logger,
                operation="get_code_structure",
                file_path=file_path,
                language=detected_language,
                duration_ms=duration,
                success=True,
                functions_found=len(structure.functions),
                classes_found=len(structure.classes),
                imports_found=len(structure.imports),
            )

            return json.dumps(structure.__dict__, indent=2, default=lambda x: x.__dict__)

    except Exception as e:
        duration = (time.time() - start_time) * 1000
        log_operation_metrics(
            logger=logger,
            operation="get_code_structure",
            file_path=file_path,
            language=detected_language or "unknown",
            duration_ms=duration,
            success=False,
            error=str(e),
        )
        return f"Error analyzing code structure: {str(e)}"


@mcp_tool
def get_structure_tree(
    file_path: str,
    language: Optional[str] = None,
    include_functions: bool = True,
    include_methods: bool = True,
    include_imports: bool = False,
    include_exports: bool = False,
) -> str:
    """
    Return a lightweight method/class tree for a file.

    Args:
        file_path: Path to the source file
        language: Optional language override
        include_functions: Include top-level functions
        include_methods: Include class methods
        include_imports: Include imports if available
        include_exports: Include exports if available

    Returns:
        JSON string with a lightweight outline tree
    """
    try:
        handler = (
            language_registry.get_handler_for_file(file_path)
            if not language
            else language_registry.get_handler_by_language(language)
        )
        if not handler:
            return json.dumps(_missing_handler_error(file_path), indent=2)

        if not _handler_supports_operation(handler, "get_code_structure"):
            return f"Code structure analysis not supported for {handler.language_name}"

        structure = handler.get_code_structure(file_path)
        classes = []
        for cls in structure.classes:
            class_entry = {
                "name": cls.name,
                "line_start": cls.line_start,
                "line_end": cls.line_end,
            }
            if include_methods:
                class_entry["methods"] = [
                    {
                        "name": method.name,
                        "line_start": method.line_start,
                        "line_end": method.line_end,
                    }
                    for method in cls.methods
                ]
            classes.append(class_entry)

        functions = []
        if include_functions:
            functions = [
                {
                    "name": func.name,
                    "line_start": func.line_start,
                    "line_end": func.line_end,
                }
                for func in structure.functions
                if not func.is_method
            ]

        result: Dict[str, Any] = {
            "file_path": structure.file_path,
            "language": structure.language,
            "classes": classes,
            "functions": functions,
        }
        if include_imports:
            result["imports"] = [
                {"module": imp.module, "line": imp.line, "import_type": imp.import_type}
                for imp in structure.imports
            ]
        if include_exports:
            result["exports"] = structure.exports

        return json.dumps(result, indent=2)
    except Exception as e:
        return f"Error getting structure tree: {str(e)}"


@mcp_tool
def analyze_dependencies(file_path: str, language: Optional[str] = None) -> str:
    """
    Analyze dependencies and imports in a source file (multi-language support).

    Args:
        file_path: Path to the source file
        language: Optional language override (auto-detected if not provided)

    Returns:
        JSON string with dependency analysis
    """
    try:
        handler = (
            language_registry.get_handler_for_file(file_path) if not language else language_registry.get_handler_by_language(language)
        )
        if not handler:
            return json.dumps(_missing_handler_error(file_path), indent=2)

        if not _handler_supports_operation(handler, "analyze_dependencies"):
            return f"Dependency analysis not supported for {handler.language_name}"

        dependencies = handler.analyze_dependencies(file_path)
        return json.dumps(dependencies, indent=2)
    except Exception as e:
        return f"Error analyzing dependencies: {str(e)}"


@mcp_tool
def rename_symbol(
    file_path: str,
    old_name: str,
    new_name: str,
    scope: str = "file",
    language: Optional[str] = None,
    preview: bool = False,
    transactional: bool = False,
    expected_hash: Optional[str] = None,
    expected_mtime: Optional[float] = None,
) -> str:
    """
    Rename a symbol (variable, function, class) in code (multi-language support).

    Args:
        file_path: Path to the source file (or directory for global scope)
        old_name: Current symbol name
        new_name: New symbol name
        scope: "file" or "global" (affects entire codebase)
        language: Optional language override (auto-detected if not provided)

    Returns:
        Success message or error details
    """
    try:
        resolved_path = str(Path(file_path).resolve())
        if expected_hash or expected_mtime is not None:
            expected_mtimes = {resolved_path: expected_mtime} if expected_mtime is not None else None
            error = _validate_expected_hashes(
                [resolved_path],
                {resolved_path: expected_hash} if expected_hash else None,
                expected_mtimes,
            )
            if error:
                return json.dumps(error, indent=2)

        if scope not in {"file", "global"}:
            return json.dumps({"error": f"Invalid scope: {scope}"}, indent=2)
        if not old_name or not new_name:
            return json.dumps({"error": "Symbol names must be non-empty"}, indent=2)
        if old_name == new_name:
            return json.dumps({"error": "Old and new names must differ"}, indent=2)

        handler = (
            language_registry.get_handler_for_file(file_path) if not language else language_registry.get_handler_by_language(language)
        )
        if not handler:
            return json.dumps(_missing_handler_error(file_path), indent=2)

        if transactional and preview:
            return json.dumps(
                {"error": "Preview cannot be combined with transactional apply"}, indent=2
            )

        if not _handler_supports_operation(handler, "rename_symbol"):
            return f"Symbol renaming not supported for {handler.language_name}"

        if transactional:
            if scope != "file":
                return json.dumps(
                    {"error": "Transactional apply only supported for file scope"}, indent=2
                )
            return json.dumps(
                _transactional_file_operation(
                    file_path,
                    lambda path: handler.rename_symbol(path, old_name, new_name, scope),
                ),
                indent=2,
            )

        if preview:
            if scope != "file":
                return json.dumps(
                    {"error": "Preview only supported for file scope"}, indent=2
                )
            return json.dumps(
                _preview_file_operation(
                    file_path,
                    lambda path: handler.rename_symbol(path, old_name, new_name, scope),
                ),
                indent=2,
            )

        return handler.rename_symbol(file_path, old_name, new_name, scope)
    except NotImplementedError as e:
        return str(e)
    except Exception as e:
        return f"Error renaming symbol: {str(e)}"


@mcp_tool
def extract_method(
    file_path: str,
    start_line: int,
    end_line: int,
    method_name: str,
    language: Optional[str] = None,
    preview: bool = False,
    transactional: bool = False,
    expected_hash: Optional[str] = None,
    expected_mtime: Optional[float] = None,
) -> str:
    """
    Extract a method from existing code (multi-language support).

    Args:
        file_path: Path to the source file
        start_line: Starting line number
        end_line: Ending line number
        method_name: Name for the new method
        language: Optional language override (auto-detected if not provided)

    Returns:
        Success message or error details
    """
    try:
        resolved_path = str(Path(file_path).resolve())
        if expected_hash or expected_mtime is not None:
            expected_mtimes = {resolved_path: expected_mtime} if expected_mtime is not None else None
            error = _validate_expected_hashes(
                [resolved_path],
                {resolved_path: expected_hash} if expected_hash else None,
                expected_mtimes,
            )
            if error:
                return json.dumps(error, indent=2)

        if not method_name:
            return json.dumps({"error": "Method name is required"}, indent=2)

        handler = (
            language_registry.get_handler_for_file(file_path) if not language else language_registry.get_handler_by_language(language)
        )
        if not handler:
            return json.dumps(_missing_handler_error(file_path), indent=2)

        if transactional and preview:
            return json.dumps(
                {"error": "Preview cannot be combined with transactional apply"}, indent=2
            )

        if not _handler_supports_operation(handler, "extract_method"):
            return f"Method extraction not supported for {handler.language_name}"

        if transactional:
            return json.dumps(
                _transactional_file_operation(
                    file_path,
                    lambda path: handler.extract_method(path, start_line, end_line, method_name),
                ),
                indent=2,
            )

        if preview:
            return json.dumps(
                _preview_file_operation(
                    file_path,
                    lambda path: handler.extract_method(path, start_line, end_line, method_name),
                ),
                indent=2,
            )

        return handler.extract_method(file_path, start_line, end_line, method_name)
    except Exception as e:
        return f"Error extracting method: {str(e)}"


@mcp_tool
def inline_method(
    file_path: str,
    method_name: str,
    language: Optional[str] = None,
    preview: bool = False,
    transactional: bool = False,
    expected_hash: Optional[str] = None,
    expected_mtime: Optional[float] = None,
) -> str:
    """
    Inline a method into its call sites (multi-language support).

    Args:
        file_path: Path to the source file
        method_name: Name of the method to inline
        language: Optional language override (auto-detected if not provided)

    Returns:
        Success message or error details
    """
    try:
        resolved_path = str(Path(file_path).resolve())
        if expected_hash or expected_mtime is not None:
            expected_mtimes = {resolved_path: expected_mtime} if expected_mtime is not None else None
            error = _validate_expected_hashes(
                [resolved_path],
                {resolved_path: expected_hash} if expected_hash else None,
                expected_mtimes,
            )
            if error:
                return json.dumps(error, indent=2)

        handler = (
            language_registry.get_handler_for_file(file_path) if not language else language_registry.get_handler_by_language(language)
        )
        if not handler:
            return json.dumps(_missing_handler_error(file_path), indent=2)

        if transactional and preview:
            return json.dumps(
                {"error": "Preview cannot be combined with transactional apply"}, indent=2
            )

        if not _handler_supports_operation(handler, "inline_method"):
            return f"Method inlining not supported for {handler.language_name}"

        if transactional:
            return json.dumps(
                _transactional_file_operation(
                    file_path,
                    lambda path: handler.inline_method(path, method_name),
                ),
                indent=2,
            )

        if preview:
            return json.dumps(
                _preview_file_operation(
                    file_path,
                    lambda path: handler.inline_method(path, method_name),
                ),
                indent=2,
            )

        return handler.inline_method(file_path, method_name)
    except Exception as e:
        return f"Error inlining method: {str(e)}"


@mcp_tool
def health_check() -> str:
    """
    Perform a comprehensive health check of the MCP server.

    Returns:
        JSON string with detailed health status
    """
    try:
        with PerformanceLogger(logger, "health_check"):
            checker = health_checks.HealthChecker()
            if hasattr(checker, "run_health_checks"):
                health_report = checker.run_health_checks()
            else:
                health_report = checker.perform_comprehensive_check()
            return json.dumps(health_report, indent=2)
    except Exception as e:
        logger.error("Health check failed", exc_info=True)
        return json.dumps(
            {
                "overall_status": HealthStatus.UNHEALTHY,
                "error": f"Health check system failure: {str(e)}",
                "timestamp": time.time(),
            },
            indent=2,
        )


@mcp_tool
def quick_health_status() -> str:
    """
    Get a quick health status without running full diagnostics.

    Returns:
        JSON string with basic health information
    """
    try:
        checker = health_checks.HealthChecker()
        status = checker.get_quick_status()
        return json.dumps(status, indent=2)
    except Exception as e:
        logger.error("Quick health check failed", exc_info=True)
        return json.dumps(HealthStatus.UNHEALTHY, indent=2)


@mcp_tool
def detect_dead_code(file_path: str, language: Optional[str] = None) -> str:
    """
    Detect dead (unused) code in a file (multi-language support).

    Args:
        file_path: Path to the source file
        language: Optional language override (auto-detected if not provided)

    Returns:
        JSON string with dead code analysis results
    """
    try:
        handler = (
            language_registry.get_handler_for_file(file_path) if not language else language_registry.get_handler_by_language(language)
        )
        if not handler:
            return json.dumps(_missing_handler_error(file_path), indent=2)

        if not _handler_supports_operation(handler, "detect_dead_code"):
            return f"Dead code detection not supported for {handler.language_name}"

        return handler.detect_dead_code(file_path)
    except Exception as e:
        return f"Error detecting dead code: {str(e)}"


@mcp_tool
def remove_dead_code(
    file_path: str,
    confirm: bool = False,
    language: Optional[str] = None,
    preview: bool = False,
    transactional: bool = False,
    expected_hash: Optional[str] = None,
    expected_mtime: Optional[float] = None,
) -> str:
    """
    Remove dead (unused) code from a file (multi-language support).

    Args:
        file_path: Path to the source file
        confirm: Set to True to actually remove dead code (safety measure)
        language: Optional language override (auto-detected if not provided)

    Returns:
        Success message or error details
    """
    try:
        resolved_path = str(Path(file_path).resolve())
        if expected_hash or expected_mtime is not None:
            expected_mtimes = {resolved_path: expected_mtime} if expected_mtime is not None else None
            error = _validate_expected_hashes(
                [resolved_path],
                {resolved_path: expected_hash} if expected_hash else None,
                expected_mtimes,
            )
            if error:
                return json.dumps(error, indent=2)

        handler = (
            language_registry.get_handler_for_file(file_path)
            if not language
            else language_registry.get_handler_by_language(language)
        )
        if not handler:
            return json.dumps(_missing_handler_error(file_path), indent=2)

        if transactional and preview:
            return json.dumps(
                {"error": "Preview cannot be combined with transactional apply"}, indent=2
            )

        if not _handler_supports_operation(handler, "remove_dead_code"):
            return f"Dead code removal not supported for {handler.language_name}"

        if transactional:
            return json.dumps(
                _transactional_file_operation(
                    file_path,
                    lambda path: handler.remove_dead_code(path, confirm),
                ),
                indent=2,
            )

        if preview:
            return json.dumps(
                _preview_file_operation(
                    file_path,
                    lambda path: handler.remove_dead_code(path, confirm),
                ),
                indent=2,
            )

        return handler.remove_dead_code(file_path, confirm)
    except Exception as e:
        return f"Error removing dead code: {str(e)}"


@mcp_tool
def find_code_pattern(
    file_path: str, pattern: str, pattern_type: str = "regex", language: Optional[str] = None
) -> str:
    """
    Find code patterns in a file (multi-language support).

    Args:
        file_path: Path to the source file
        pattern: Pattern to search for (regex, AST, or semantic pattern)
        pattern_type: Type of pattern ("regex", "ast", "semantic")
        language: Optional language override (auto-detected if not provided)

    Returns:
        JSON string with pattern matches
    """
    try:
        handler = (
            language_registry.get_handler_for_file(file_path) if not language else language_registry.get_handler_by_language(language)
        )
        if not handler:
            return json.dumps(_missing_handler_error(file_path), indent=2)

        if pattern_type not in {"regex", "ast", "semantic"}:
            return json.dumps({"error": f"Invalid pattern type: {pattern_type}"}, indent=2)

        if not _handler_supports_operation(handler, "find_code_pattern"):
            return f"Pattern finding not supported for {handler.language_name}"

        return handler.find_code_pattern(file_path, pattern, pattern_type)
    except Exception as e:
        return f"Error finding pattern: {str(e)}"


@mcp_tool
def apply_code_pattern(
    file_path: str,
    find_pattern: str,
    replace_pattern: str,
    pattern_type: str = "regex",
    max_replacements: int = -1,
    language: Optional[str] = None,
    preview: bool = False,
    transactional: bool = False,
    expected_hash: Optional[str] = None,
    expected_mtime: Optional[float] = None,
) -> str:
    """
    Apply code pattern transformations to a file (multi-language support).

    Args:
        file_path: Path to the source file
        find_pattern: Pattern to find
        replace_pattern: Pattern to replace with
        pattern_type: Type of pattern ("regex", "ast")
        max_replacements: Maximum number of replacements (-1 for unlimited)
        language: Optional language override (auto-detected if not provided)

    Returns:
        Success message or error details
    """
    try:
        resolved_path = str(Path(file_path).resolve())
        if expected_hash or expected_mtime is not None:
            expected_mtimes = {resolved_path: expected_mtime} if expected_mtime is not None else None
            error = _validate_expected_hashes(
                [resolved_path],
                {resolved_path: expected_hash} if expected_hash else None,
                expected_mtimes,
            )
            if error:
                return json.dumps(error, indent=2)

        if pattern_type not in {"regex", "ast", "semantic"}:
            return json.dumps({"error": f"Invalid pattern type: {pattern_type}"}, indent=2)
        if max_replacements == 0 or max_replacements < -1:
            return json.dumps({"error": "Invalid replacement limit"}, indent=2)

        handler = (
            language_registry.get_handler_for_file(file_path) if not language else language_registry.get_handler_by_language(language)
        )
        if not handler:
            return json.dumps(_missing_handler_error(file_path), indent=2)

        if transactional and preview:
            return json.dumps(
                {"error": "Preview cannot be combined with transactional apply"}, indent=2
            )

        if not _handler_supports_operation(handler, "apply_code_pattern"):
            return f"Pattern application not supported for {handler.language_name}"

        if transactional:
            return json.dumps(
                _transactional_file_operation(
                    file_path,
                    lambda path: handler.apply_code_pattern(
                        path, find_pattern, replace_pattern, pattern_type, max_replacements
                    ),
                ),
                indent=2,
            )

        if preview:
            return json.dumps(
                _preview_file_operation(
                    file_path,
                    lambda path: handler.apply_code_pattern(
                        path, find_pattern, replace_pattern, pattern_type, max_replacements
                    ),
                ),
                indent=2,
            )

        return handler.apply_code_pattern(
            file_path, find_pattern, replace_pattern, pattern_type, max_replacements
        )
    except Exception as e:
        return f"Error applying pattern: {str(e)}"


@mcp_tool
def apply_text_edits(
    file_path: str,
    edits: List[Dict[str, Any]],
    expected_hash: Optional[str] = None,
    expected_mtime: Optional[float] = None,
    preview: bool = True,
) -> str:
    """
    Apply LSP-style text edits to a file with optional hash precondition.

    Args:
        file_path: Path to the source file
        edits: List of edits with start_line/end_line (1-based) and start_column/end_column (0-based)
        expected_hash: Optional sha256 hash of original content to guard against stale edits
        preview: If True, only return what would change

    Returns:
        JSON string with edit results and hashes
    """
    try:
        file_path = str(Path(file_path).resolve())
        if not Path(file_path).exists():
            return json.dumps(
                {"success": False, "error": f"File not found: {file_path}"},
                indent=2,
            )

        with open(file_path, "r", encoding="utf-8") as f:
            content = f.read()

        original_hash = _compute_text_hash(content)
        if expected_mtime is not None:
            try:
                actual_mtime = Path(file_path).stat().st_mtime
            except OSError:
                actual_mtime = None
            if actual_mtime != expected_mtime:
                return json.dumps(
                    {
                        "success": False,
                        "error": "File mtime mismatch",
                        "file_path": file_path,
                        "expected_mtime": expected_mtime,
                        "actual_mtime": actual_mtime,
                    },
                    indent=2,
                )

        if expected_hash and expected_hash != original_hash:
            return json.dumps(
                {
                    "success": False,
                    "error": "File hash mismatch",
                    "file_path": file_path,
                    "expected_hash": expected_hash,
                    "actual_hash": original_hash,
                },
                indent=2,
            )

        applied = _apply_text_edits_to_content(content, edits)
        if applied["errors"]:
            return json.dumps(
                {
                    "success": False,
                    "error": "Edit validation failed",
                    "file_path": file_path,
                    "errors": applied["errors"],
                },
                indent=2,
            )

        new_content = applied["content"]
        new_hash = _compute_text_hash(new_content)

        if not preview:
            with open(file_path, "w", encoding="utf-8") as f:
                f.write(new_content)

        return json.dumps(
            {
                "success": True,
                "preview": preview,
                "file_path": file_path,
                "original_hash": original_hash,
                "new_hash": new_hash,
                "edit_count": applied.get("edit_count", 0),
            },
            indent=2,
        )
    except Exception as e:
        return json.dumps(
            {
                "success": False,
                "error": f"Failed to apply text edits: {str(e)}",
            },
            indent=2,
        )


@mcp_tool
def get_file_metadata(
    file_paths: List[str], include_hash: bool = False, include_mtime: bool = True
) -> str:
    """
    Return size/mtime/hash metadata for multiple files.

    Args:
        file_paths: List of file paths to inspect
        include_hash: If True, compute sha256 of file contents
        include_mtime: If True, include file mtime

    Returns:
        JSON string with per-file metadata
    """
    results = []
    for file_path in file_paths:
        entry: Dict[str, Any] = {"file_path": file_path}
        try:
            path = Path(file_path)
            stat = path.stat()
            entry["exists"] = True
            entry["is_dir"] = path.is_dir()
            entry["size_bytes"] = stat.st_size
            if include_mtime:
                entry["mtime"] = stat.st_mtime
            if include_hash and path.is_file():
                try:
                    entry["hash"] = _compute_bytes_hash(path.read_bytes())
                except Exception as e:
                    entry["hash_error"] = str(e)
        except Exception as e:
            entry["exists"] = False
            entry["error"] = str(e)
        results.append(entry)

    return json.dumps({"files": results}, indent=2)


@mcp_tool
def read_file_ranges(
    file_path: str,
    ranges: Optional[List[Dict[str, Any]]] = None,
    symbol_names: Optional[List[str]] = None,
    language: Optional[str] = None,
    max_chars: Optional[int] = None,
) -> str:
    """
    Read specific ranges or symbol snippets from a file.

    Args:
        file_path: Path to the source file
        ranges: List of ranges with start_line/start_column/end_line/end_column (1-based lines)
        symbol_names: Optional symbol names to fetch by structure (functions/classes/methods)
        language: Optional language override
        max_chars: Optional per-snippet character limit

    Returns:
        JSON string with extracted snippets or errors
    """
    try:
        content = Path(file_path).read_text(encoding="utf-8")
    except Exception as e:
        return json.dumps({"error": f"Failed to read file: {str(e)}"}, indent=2)

    lines = content.splitlines(keepends=True)
    line_offsets = [0]
    running = 0
    for line in lines:
        running += len(line)
        line_offsets.append(running)

    selected_ranges: List[Dict[str, Any]] = []
    if ranges:
        selected_ranges.extend(ranges)

    if symbol_names:
        handler = (
            language_registry.get_handler_for_file(file_path)
            if not language
            else language_registry.get_handler_by_language(language)
        )
        if not handler:
            return json.dumps(_missing_handler_error(file_path), indent=2)
        if not _handler_supports_operation(handler, "get_code_structure"):
            return json.dumps(
                {"error": f"Code structure analysis not supported for {handler.language_name}"},
                indent=2,
            )
        structure = handler.get_code_structure(file_path)
        symbols = {name for name in symbol_names}
        for cls in structure.classes:
            if cls.name in symbols:
                selected_ranges.append(
                    {
                        "start_line": cls.line_start,
                        "start_column": 0,
                        "end_line": cls.line_end,
                        "end_column": 0,
                        "symbol": cls.name,
                        "kind": "class",
                    }
                )
            for method in cls.methods:
                qualified = f"{cls.name}.{method.name}"
                if method.name in symbols or qualified in symbols:
                    selected_ranges.append(
                        {
                            "start_line": method.line_start,
                            "start_column": 0,
                            "end_line": method.line_end,
                            "end_column": 0,
                            "symbol": qualified,
                            "kind": "method",
                        }
                    )
        for func in structure.functions:
            if func.name in symbols and not func.is_method:
                selected_ranges.append(
                    {
                        "start_line": func.line_start,
                        "start_column": 0,
                        "end_line": func.line_end,
                        "end_column": 0,
                        "symbol": func.name,
                        "kind": "function",
                    }
                )

    if not selected_ranges:
        return json.dumps({"snippets": [], "errors": ["No ranges or symbols provided"]}, indent=2)

    snippets: List[Dict[str, Any]] = []
    errors: List[str] = []

    for idx, selection in enumerate(selected_ranges):
        try:
            start_line = int(selection.get("start_line"))
            end_line = int(selection.get("end_line"))
            start_column = int(selection.get("start_column", 0))
            end_column = int(selection.get("end_column", 0))
        except (TypeError, ValueError):
            errors.append(f"Range {idx}: invalid line/column values")
            continue

        if start_line < 1 or end_line < 1:
            errors.append(f"Range {idx}: line numbers must be >= 1")
            continue
        if start_line > len(lines) or end_line > len(lines):
            errors.append(f"Range {idx}: line out of range")
            continue

        start_line_text = lines[start_line - 1]
        end_line_text = lines[end_line - 1]
        start_line_len = (
            len(start_line_text[:-1]) if start_line_text.endswith("\n") else len(start_line_text)
        )
        end_line_len = (
            len(end_line_text[:-1]) if end_line_text.endswith("\n") else len(end_line_text)
        )
        if start_column < 0 or start_column > start_line_len:
            errors.append(f"Range {idx}: start_column out of range")
            continue
        if end_column < 0 or end_column > end_line_len:
            errors.append(f"Range {idx}: end_column out of range")
            continue

        start_offset = line_offsets[start_line - 1] + start_column
        end_offset = line_offsets[end_line - 1] + end_column
        if end_offset < start_offset:
            errors.append(f"Range {idx}: end before start")
            continue

        snippet_text = content[start_offset:end_offset]
        if max_chars is not None and len(snippet_text) > max_chars:
            snippet_text = snippet_text[:max_chars]

        snippet = {
            "range": {
                "start_line": start_line,
                "start_column": start_column,
                "end_line": end_line,
                "end_column": end_column,
            },
            "text": snippet_text,
        }
        for key in ("symbol", "kind"):
            if key in selection:
                snippet[key] = selection[key]
        snippets.append(snippet)

    return json.dumps({"snippets": snippets, "errors": errors}, indent=2)


@mcp_tool
def batch_apply_text_edits(
    edits_by_file: Dict[str, List[Dict[str, Any]]],
    expected_hashes: Optional[Dict[str, str]] = None,
    expected_mtimes: Optional[Dict[str, float]] = None,
    preview: bool = True,
    transactional: bool = False,
    include_diff: bool = False,
) -> str:
    """
    Apply LSP-style text edits to multiple files atomically.

    Args:
        edits_by_file: Map of file path -> list of edits
        expected_hashes: Optional sha256 hashes to guard against stale edits
        expected_mtimes: Optional mtimes to guard against stale edits
        preview: If True, only return what would change
        transactional: If True, fail if any file changes between preview/apply
        include_diff: If True, include unified diffs per file

    Returns:
        JSON string with per-file results
    """
    if transactional and preview:
        return json.dumps({"error": "Preview cannot be combined with transactional apply"}, indent=2)

    file_paths = list(edits_by_file.keys())
    resolved = [str(Path(path).resolve()) for path in file_paths]
    if expected_hashes or expected_mtimes:
        error = _validate_expected_hashes(resolved, expected_hashes, expected_mtimes)
        if error:
            return json.dumps(error, indent=2)

    results: List[Dict[str, Any]] = []
    errors: List[str] = []
    originals: Dict[str, str] = {}
    updated: Dict[str, str] = {}

    for file_path in file_paths:
        try:
            content = Path(file_path).read_text(encoding="utf-8")
        except Exception as e:
            errors.append(f"{file_path}: {str(e)}")
            continue

        originals[file_path] = content
        applied = _apply_text_edits_to_content(content, edits_by_file.get(file_path, []))
        if applied["errors"]:
            errors.append(f"{file_path}: {applied['errors']}")
            continue
        updated[file_path] = applied["content"]

    if errors:
        return json.dumps({"error": "Edit validation failed", "errors": errors}, indent=2)

    if transactional and not preview:
        mismatches = []
        for file_path, original in originals.items():
            current_hash = _get_file_hash(file_path)
            if current_hash != _compute_text_hash(original):
                mismatches.append(
                    {
                        "file_path": file_path,
                        "expected": _compute_text_hash(original),
                        "actual": current_hash,
                    }
                )
        if mismatches:
            return json.dumps(
                {"error": "File hash mismatch", "hash_mismatched": mismatches}, indent=2
            )

    for file_path in file_paths:
        result = {
            "file_path": file_path,
            "original_hash": _compute_text_hash(originals[file_path]),
            "new_hash": _compute_text_hash(updated[file_path]),
            "edit_count": len(edits_by_file.get(file_path, [])),
        }
        if include_diff:
            diff = "\n".join(
                difflib.unified_diff(
                    originals[file_path].splitlines(),
                    updated[file_path].splitlines(),
                    fromfile=file_path,
                    tofile=file_path,
                    lineterm="",
                )
            )
            result["diff"] = diff
        results.append(result)

    if not preview:
        for file_path in file_paths:
            Path(file_path).write_text(updated[file_path], encoding="utf-8")

    return json.dumps({"files": results, "preview": preview}, indent=2)


@mcp_tool
def diff_summary(
    file_paths: List[str],
    new_contents: Optional[Dict[str, str]] = None,
    max_hunks: int = 2,
    max_lines_per_hunk: int = 20,
) -> str:
    """
    Summarize diffs for multiple files with limited hunks.

    Args:
        file_paths: List of file paths to summarize
        new_contents: Optional map of file path -> proposed content
        max_hunks: Maximum hunks to include per file
        max_lines_per_hunk: Maximum lines per hunk to include

    Returns:
        JSON string with per-file diff stats and limited hunks
    """
    summaries: List[Dict[str, Any]] = []

    for file_path in file_paths:
        try:
            original = Path(file_path).read_text(encoding="utf-8")
        except Exception as e:
            summaries.append({"file_path": file_path, "error": str(e)})
            continue

        proposed = new_contents.get(file_path, original) if new_contents else original
        diff_lines = list(
            difflib.unified_diff(
                original.splitlines(),
                proposed.splitlines(),
                fromfile=file_path,
                tofile=file_path,
                lineterm="",
            )
        )

        additions = sum(1 for line in diff_lines if line.startswith("+") and not line.startswith("+++"))
        deletions = sum(1 for line in diff_lines if line.startswith("-") and not line.startswith("---"))

        limited: List[str] = []
        hunk_count = 0
        line_budget = max_lines_per_hunk
        for line in diff_lines:
            if line.startswith("@@"):
                if hunk_count >= max_hunks:
                    break
                hunk_count += 1
                line_budget = max_lines_per_hunk
                limited.append(line)
                continue
            if hunk_count == 0:
                continue
            if line_budget <= 0:
                continue
            limited.append(line)
            line_budget -= 1

        summaries.append(
            {
                "file_path": file_path,
                "added": additions,
                "removed": deletions,
                "hunks": hunk_count,
                "diff": "\n".join(limited),
            }
        )

    return json.dumps({"files": summaries}, indent=2)


@mcp_tool
def validate_refactoring_operation(
    file_path: str, operation: str, language: Optional[str] = None, **kwargs
) -> str:
    """
    Validate a refactoring operation before execution (multi-language support).

    Args:
        file_path: Path to the source file
        operation: Name of the refactoring operation
        language: Optional language override (auto-detected if not provided)
        **kwargs: Additional parameters for the specific operation

    Returns:
        JSON string with validation results
    """
    try:
        handler = (
            language_registry.get_handler_for_file(file_path) if not language else language_registry.get_handler_by_language(language)
        )
        if not handler:
            return json.dumps(_missing_handler_error(file_path), indent=2)

        # Convert string operation to enum
        try:
            from .languages.base_handler import RefactoringOperation

            operation_enum = RefactoringOperation(operation)
        except ValueError:
            return json.dumps(
                {"error": f"Invalid operation: {operation}", "file_path": file_path},
                indent=2,
            )

        validation_result = handler.validate_refactoring_operation(
            file_path, operation_enum, **kwargs
        )

        return json.dumps(validation_result, indent=2)

    except Exception as e:
        return json.dumps(
            {"error": f"Validation error: {str(e)}", "file_path": file_path}, indent=2
        )


@mcp_tool
def server_metrics() -> str:
    """
    Get server performance and usage metrics.

    Returns:
        JSON string with server metrics
    """
    try:
        with PerformanceLogger(logger, "server_metrics"):
            metrics = {
                "uptime_seconds": round(health_checker.get_uptime(), 2),
                "supported_languages": language_registry.list_supported_languages(),
                "total_languages": len(language_registry.list_supported_languages()),
                "total_extensions": len(language_registry.list_supported_extensions()),
                "server_start_time": health_checker.start_time.isoformat() + "Z",
            }

            # Add memory info if available
            try:
                import psutil

                process = psutil.Process()
                metrics["memory_usage_mb"] = round(process.memory_info().rss / 1024 / 1024, 2)
                metrics["cpu_percent"] = round(process.cpu_percent(), 2)
            except ImportError:
                metrics["system_monitoring"] = "psutil not available"

            logger.info(
                "Server metrics requested",
                extra={
                    "extra_fields": {
                        "uptime": metrics["uptime_seconds"],
                        "languages": metrics["total_languages"],
                    }
                },
            )

            return json.dumps(metrics, indent=2)
    except Exception as e:
        logger.error("Server metrics failed", exc_info=True)
        return json.dumps({"error": f"Metrics collection failed: {str(e)}"}, indent=2)


# ==============================================================================
# IDE-Like Workspace Operations
# ==============================================================================


@mcp_tool
def initialize_workspace(root_path: str) -> str:
    """
    Initialize a workspace and build symbol index for a project directory.

    This creates a project-wide index of all symbols (functions, classes, variables)
    enabling fast search, reference finding, and cross-file operations.

    Args:
        root_path: Root directory of the project to index

    Returns:
        JSON string with workspace ID and indexing statistics
    """
    try:
        with PerformanceLogger(logger, "initialize_workspace", root_path=root_path):
            workspace_id, index = WorkspaceManager.get_or_create_workspace(root_path)

            result = {
                "workspace_id": workspace_id,
                "root_path": str(index.root_path),
                "files_indexed": index.stats.get("total_files", 0),
                "symbols": index.stats.get("total_symbols", 0),
                "languages": index.stats.get("languages", []),
                "index_time_ms": index.stats.get("index_time_ms", 0),
            }

            logger.info(
                "Workspace initialized",
                extra={
                    "extra_fields": {
                        "workspace_id": workspace_id,
                        "files": result["files_indexed"],
                        "symbols": result["symbols"],
                    }
                },
            )

            return json.dumps(result, indent=2)
    except Exception as e:
        logger.error("Workspace initialization failed", exc_info=True)
        return json.dumps({"error": f"Failed to initialize workspace: {str(e)}"}, indent=2)


@mcp_tool
def find_references(
    file_path: str,
    symbol_name: str,
    workspace_id: Optional[str] = None,
    include_definition: bool = True,
    scope: str = "project",
) -> str:
    """
    Find all references to a symbol across the project.

    Essential for understanding impact before making changes - shows everywhere
    a symbol is used (called, imported, assigned, etc.).

    Args:
        file_path: Path to a file in the project (used to identify workspace if workspace_id not provided)
        symbol_name: Name of the symbol to find references for
        workspace_id: Optional workspace ID (from initialize_workspace)
        include_definition: Whether to include the definition in results
        scope: "project" for all files, "file" for current file only

    Returns:
        JSON string with definition info and list of all references
    """
    try:
        with PerformanceLogger(logger, "find_references", symbol=symbol_name):
            # Get or create workspace
            if workspace_id:
                index = WorkspaceManager.get_workspace(workspace_id)
                if not index:
                    return json.dumps({"error": f"Workspace '{workspace_id}' not found"}, indent=2)
            else:
                root_path = Path(file_path).parent
                # Try to find project root
                while root_path.parent != root_path:
                    if (root_path / ".git").exists() or (root_path / "pyproject.toml").exists():
                        break
                    root_path = root_path.parent
                _, index = WorkspaceManager.get_or_create_workspace(str(root_path))

            finder = ReferenceFinder(index)
            result = finder.find_references(
                symbol_name,
                file_path=file_path if scope == "file" else None,
                include_definition=include_definition,
                scope=scope,
            )

            logger.info(
                "References found",
                extra={
                    "extra_fields": {
                        "symbol": symbol_name,
                        "total": result.get("total", 0),
                        "files": result.get("files_with_references", 0),
                    }
                },
            )

            return json.dumps(result, indent=2)
    except Exception as e:
        logger.error("Find references failed", exc_info=True)
        return json.dumps({"error": f"Failed to find references: {str(e)}"}, indent=2)


@mcp_tool
def go_to_definition(
    file_path: str,
    symbol_name: str,
    line: Optional[int] = None,
    workspace_id: Optional[str] = None,
    follow_imports: bool = True,
) -> str:
    """
    Find where a symbol is defined.

    Follows import chains to find the original definition, just like
    Ctrl+Click / F12 in an IDE.

    Args:
        file_path: Path to the file containing the reference
        symbol_name: Name of the symbol to find the definition for
        line: Optional line number for context (helps with local variables)
        workspace_id: Optional workspace ID
        follow_imports: Whether to follow import chains to find original definition

    Returns:
        JSON string with definition location and import chain if applicable
    """
    try:
        with PerformanceLogger(logger, "go_to_definition", symbol=symbol_name):
            # Get or create workspace
            if workspace_id:
                index = WorkspaceManager.get_workspace(workspace_id)
                if not index:
                    return json.dumps({"error": f"Workspace '{workspace_id}' not found"}, indent=2)
            else:
                root_path = Path(file_path).parent
                while root_path.parent != root_path:
                    if (root_path / ".git").exists() or (root_path / "pyproject.toml").exists():
                        break
                    root_path = root_path.parent
                _, index = WorkspaceManager.get_or_create_workspace(str(root_path))

            resolver = DefinitionResolver(index)
            result = resolver.go_to_definition(file_path, symbol_name, line, follow_imports)

            logger.info(
                "Definition resolved",
                extra={
                    "extra_fields": {
                        "symbol": symbol_name,
                        "found": result.get("found", False),
                        "defined_in": result.get("defined_in"),
                    }
                },
            )

            return json.dumps(result, indent=2)
    except Exception as e:
        logger.error("Go to definition failed", exc_info=True)
        return json.dumps({"error": f"Failed to find definition: {str(e)}"}, indent=2)


@mcp_tool
def get_call_hierarchy(
    file_path: str,
    function_name: str,
    direction: str = "both",
    workspace_id: Optional[str] = None,
    max_depth: int = 5,
) -> str:
    """
    Get the call hierarchy for a function.

    Shows what calls this function (callers) and what this function calls (callees).
    Essential for understanding code flow and impact of changes.

    Args:
        file_path: Path to the file containing the function
        function_name: Name of the function to analyze
        direction: "callers" (incoming), "callees" (outgoing), or "both"
        workspace_id: Optional workspace ID
        max_depth: Maximum depth to traverse (default 5)

    Returns:
        JSON string with callers and/or callees
    """
    try:
        with PerformanceLogger(logger, "get_call_hierarchy", function=function_name):
            # Get or create workspace
            if workspace_id:
                index = WorkspaceManager.get_workspace(workspace_id)
                if not index:
                    return json.dumps({"error": f"Workspace '{workspace_id}' not found"}, indent=2)
            else:
                root_path = Path(file_path).parent
                while root_path.parent != root_path:
                    if (root_path / ".git").exists() or (root_path / "pyproject.toml").exists():
                        break
                    root_path = root_path.parent
                _, index = WorkspaceManager.get_or_create_workspace(str(root_path))

            analyzer = CallGraphAnalyzer(index)
            result = analyzer.get_call_hierarchy(file_path, function_name, direction, max_depth)

            callers_count = len(result.get("callers", []))
            callees_count = len(result.get("callees", []))

            logger.info(
                "Call hierarchy analyzed",
                extra={
                    "extra_fields": {
                        "function": function_name,
                        "callers": callers_count,
                        "callees": callees_count,
                    }
                },
            )

            return json.dumps(result, indent=2)
    except Exception as e:
        logger.error("Call hierarchy failed", exc_info=True)
        return json.dumps({"error": f"Failed to get call hierarchy: {str(e)}"}, indent=2)


@mcp_tool
def search_symbols(
    pattern: str,
    root_path: Optional[str] = None,
    workspace_id: Optional[str] = None,
    symbol_type: Optional[str] = None,
    limit: int = 100,
) -> str:
    """
    Search for symbols across the project using fuzzy matching.

    Like Ctrl+T / Cmd+Shift+O in an IDE - quickly find functions, classes,
    or variables by name pattern.

    Args:
        pattern: Search pattern (supports fuzzy matching)
        root_path: Project root path (required if workspace_id not provided)
        workspace_id: Optional workspace ID
        symbol_type: Filter by type: "function", "class", "method", "variable"
        limit: Maximum results to return (default 100)

    Returns:
        JSON string with matching symbols and their locations
    """
    try:
        with PerformanceLogger(logger, "search_symbols", pattern=pattern):
            # Get or create workspace
            if workspace_id:
                index = WorkspaceManager.get_workspace(workspace_id)
                if not index:
                    return json.dumps({"error": f"Workspace '{workspace_id}' not found"}, indent=2)
            elif root_path:
                _, index = WorkspaceManager.get_or_create_workspace(root_path)
            else:
                return json.dumps(
                    {"error": "Either root_path or workspace_id must be provided"}, indent=2
                )

            matches = index.search_symbols(pattern, symbol_type=symbol_type, limit=limit)

            result = {
                "pattern": pattern,
                "symbol_type": symbol_type,
                "matches": [
                    {
                        "name": s.name,
                        "qualified_name": s.qualified_name,
                        "type": s.symbol_type,
                        "file": s.file_path,
                        "line": s.line_start,
                        "signature": s.signature,
                    }
                    for s in matches
                ],
                "total": len(matches),
            }

            logger.info(
                "Symbols searched",
                extra={
                    "extra_fields": {
                        "pattern": pattern,
                        "matches": len(matches),
                    }
                },
            )

            return json.dumps(result, indent=2)
    except Exception as e:
        logger.error("Symbol search failed", exc_info=True)
        return json.dumps({"error": f"Failed to search symbols: {str(e)}"}, indent=2)


@mcp_tool
def workspace_rename(
    old_name: str,
    new_name: str,
    root_path: Optional[str] = None,
    workspace_id: Optional[str] = None,
    file_path: Optional[str] = None,
    preview: bool = True,
    expected_hashes: Optional[Dict[str, str]] = None,
    expected_mtimes: Optional[Dict[str, float]] = None,
) -> str:
    """
    Rename a symbol across the entire workspace with preview.

    Safe rename that finds all references and updates them consistently.
    Use preview=True (default) to see changes before applying.

    Args:
        old_name: Current name of the symbol
        new_name: New name for the symbol
        root_path: Project root path (required if workspace_id not provided)
        workspace_id: Optional workspace ID
        file_path: Optional file path to limit rename scope to single file
        preview: If True, only preview changes; if False, apply them

    Returns:
        JSON string with all changes (preview) or confirmation (applied)
    """
    try:
        with PerformanceLogger(logger, "workspace_rename", old_name=old_name, new_name=new_name):
            # Get or create workspace
            if workspace_id:
                index = WorkspaceManager.get_workspace(workspace_id)
                if not index:
                    return json.dumps({"error": f"Workspace '{workspace_id}' not found"}, indent=2)
            elif root_path:
                _, index = WorkspaceManager.get_or_create_workspace(root_path)
            elif file_path:
                root = Path(file_path).parent
                while root.parent != root:
                    if (root / ".git").exists() or (root / "pyproject.toml").exists():
                        break
                    root = root.parent
                _, index = WorkspaceManager.get_or_create_workspace(str(root))
            else:
                return json.dumps(
                    {"error": "Either root_path, workspace_id, or file_path must be provided"},
                    indent=2,
                )

            ops = WorkspaceOperations(index)
            if (expected_hashes or expected_mtimes) and not preview:
                preview_result = ops.workspace_rename(old_name, new_name, file_path, preview=True)
                files = {c.file_path for c in preview_result.changes}
                error = _validate_expected_hashes(sorted(files), expected_hashes, expected_mtimes)
                if error:
                    return json.dumps(error, indent=2)

            result = ops.workspace_rename(old_name, new_name, file_path, preview)

            logger.info(
                "Workspace rename completed",
                extra={
                    "extra_fields": {
                        "old_name": old_name,
                        "new_name": new_name,
                        "changes": result.total_changes,
                        "files": result.affected_files,
                        "preview": preview,
                    }
                },
            )

            return json.dumps(result.to_dict(), indent=2)
    except Exception as e:
        logger.error("Workspace rename failed", exc_info=True)
        return json.dumps({"error": f"Failed to rename: {str(e)}"}, indent=2)


@mcp_tool
def list_workspaces() -> str:
    """
    List all active workspaces.

    Returns:
        JSON string with list of workspace info
    """
    try:
        workspaces = WorkspaceManager.list_workspaces()
        return json.dumps({"workspaces": workspaces, "total": len(workspaces)}, indent=2)
    except Exception as e:
        logger.error("List workspaces failed", exc_info=True)
        return json.dumps({"error": f"Failed to list workspaces: {str(e)}"}, indent=2)


@mcp_tool
def refresh_workspace(workspace_id: str) -> str:
    """
    Re-index a workspace to pick up file changes.

    Args:
        workspace_id: ID of the workspace to refresh

    Returns:
        JSON string with updated statistics
    """
    try:
        with PerformanceLogger(logger, "refresh_workspace", workspace_id=workspace_id):
            stats = WorkspaceManager.refresh_workspace(workspace_id)

            if stats is None:
                return json.dumps({"error": f"Workspace '{workspace_id}' not found"}, indent=2)

            return json.dumps(
                {
                    "workspace_id": workspace_id,
                    "refreshed": True,
                    "stats": stats,
                },
                indent=2,
            )
    except Exception as e:
        logger.error("Workspace refresh failed", exc_info=True)
        return json.dumps({"error": f"Failed to refresh workspace: {str(e)}"}, indent=2)


@mcp_tool
def get_workspace_status(
    workspace_id: Optional[str] = None, root_path: Optional[str] = None
) -> str:
    """
    Get workspace indexing status and cache freshness.

    Args:
        workspace_id: Optional workspace ID
        root_path: Optional root path (used if workspace_id not provided)

    Returns:
        JSON string with status details
    """
    try:
        if workspace_id:
            index = WorkspaceManager.get_workspace(workspace_id)
            if not index:
                return json.dumps({"error": f"Workspace '{workspace_id}' not found"}, indent=2)
        elif root_path:
            workspace_id, index = WorkspaceManager.get_or_create_workspace(root_path)
        else:
            return json.dumps(
                {"error": "Either workspace_id or root_path must be provided"}, indent=2
            )

        status = {
            "workspace_id": workspace_id,
            "root_path": str(index.root_path),
            "stats": index.stats,
            "cache_is_fresh": index.cache_is_fresh(),
            "last_updated": index.last_updated,
        }
        return json.dumps(status, indent=2)
    except Exception as e:
        logger.error("Workspace status failed", exc_info=True)
        return json.dumps({"error": f"Failed to get workspace status: {str(e)}"}, indent=2)


@mcp_tool
def get_file_symbols(file_path: str, workspace_id: Optional[str] = None) -> str:
    """
    Get all symbols (functions, classes, variables) defined in a file.

    Args:
        file_path: Path to the file
        workspace_id: Optional workspace ID

    Returns:
        JSON string with list of symbols
    """
    try:
        with PerformanceLogger(logger, "get_file_symbols", file_path=file_path):
            # Get or create workspace
            if workspace_id:
                index = WorkspaceManager.get_workspace(workspace_id)
                if not index:
                    return json.dumps({"error": f"Workspace '{workspace_id}' not found"}, indent=2)
            else:
                root_path = Path(file_path).parent
                while root_path.parent != root_path:
                    if (root_path / ".git").exists() or (root_path / "pyproject.toml").exists():
                        break
                    root_path = root_path.parent
                _, index = WorkspaceManager.get_or_create_workspace(str(root_path))

            symbols = index.get_file_symbols(file_path)

            result = {
                "file_path": file_path,
                "symbols": [
                    {
                        "name": s.name,
                        "qualified_name": s.qualified_name,
                        "type": s.symbol_type,
                        "line_start": s.line_start,
                        "line_end": s.line_end,
                        "signature": s.signature,
                        "visibility": s.visibility,
                    }
                    for s in symbols
                ],
                "total": len(symbols),
            }

            return json.dumps(result, indent=2)
    except Exception as e:
        logger.error("Get file symbols failed", exc_info=True)
        return json.dumps({"error": f"Failed to get file symbols: {str(e)}"}, indent=2)


# ==============================================================================
# Phase 2: Token-Saving Operations
# ==============================================================================


@mcp_tool
def move_symbol(
    source_file: str,
    symbol_name: str,
    target_file: str,
    update_imports: bool = True,
    preview: bool = True,
    workspace_id: Optional[str] = None,
    expected_hashes: Optional[Dict[str, str]] = None,
    expected_mtimes: Optional[Dict[str, float]] = None,
) -> str:
    """
    Move a symbol (function, class) from one file to another with automatic import updates.

    This is a high-impact token-saving operation - eliminates the need for an LLM to:
    1. Read the source file
    2. Read the target file
    3. Find all files that import the symbol
    4. Generate diffs for each affected file

    Args:
        source_file: Path to the source file containing the symbol
        symbol_name: Name of the function or class to move
        target_file: Path to the destination file
        update_imports: Whether to automatically update imports in all referencing files
        preview: If True, only show what would change; if False, apply changes
        workspace_id: Optional workspace ID for the project

    Returns:
        JSON string with move details and files affected
    """
    try:
        with PerformanceLogger(logger, "move_symbol", symbol=symbol_name):
            # Get or create workspace
            if workspace_id:
                index = WorkspaceManager.get_workspace(workspace_id)
                if not index:
                    return json.dumps({"error": f"Workspace '{workspace_id}' not found"}, indent=2)
            else:
                root_path = Path(source_file).parent
                while root_path.parent != root_path:
                    if (root_path / ".git").exists() or (root_path / "pyproject.toml").exists():
                        break
                    root_path = root_path.parent
                _, index = WorkspaceManager.get_or_create_workspace(str(root_path))

            mover = SymbolMover(index)
            if (expected_hashes or expected_mtimes) and not preview:
                preview_result = mover.move_symbol(
                    source_file, symbol_name, target_file, update_imports, preview=True
                )
                files = {
                    str(Path(source_file).resolve()),
                    str(Path(target_file).resolve()),
                }
                files.update({item.get("file") for item in preview_result.imports_updated})
                files.discard(None)
                error = _validate_expected_hashes(sorted(files), expected_hashes, expected_mtimes)
                if error:
                    return json.dumps(error, indent=2)

            result = mover.move_symbol(
                source_file, symbol_name, target_file, update_imports, preview
            )

            logger.info(
                "Symbol move completed",
                extra={
                    "extra_fields": {
                        "symbol": symbol_name,
                        "source": source_file,
                        "target": target_file,
                        "files_modified": result.files_modified,
                        "preview": preview,
                    }
                },
            )

            return json.dumps(result.to_dict(), indent=2)
    except Exception as e:
        logger.error("Move symbol failed", exc_info=True)
        return json.dumps({"error": f"Failed to move symbol: {str(e)}"}, indent=2)


@mcp_tool
def safe_delete(
    file_path: str,
    symbol_name: str,
    confirm: bool = False,
    workspace_id: Optional[str] = None,
    expected_hash: Optional[str] = None,
    expected_mtime: Optional[float] = None,
) -> str:
    """
    Check if a symbol can be safely deleted (not used anywhere).

    Prevents accidental deletion of symbols still in use. Shows all usages
    if the symbol cannot be safely deleted.

    Args:
        file_path: Path to the file containing the symbol
        symbol_name: Name of the symbol to potentially delete
        confirm: If True and can_delete is True, actually delete the symbol
        workspace_id: Optional workspace ID

    Returns:
        JSON string with deletion status and any blockers
    """
    try:
        with PerformanceLogger(logger, "safe_delete", symbol=symbol_name):
            # Get or create workspace
            if workspace_id:
                index = WorkspaceManager.get_workspace(workspace_id)
                if not index:
                    return json.dumps({"error": f"Workspace '{workspace_id}' not found"}, indent=2)
            else:
                root_path = Path(file_path).parent
                while root_path.parent != root_path:
                    if (root_path / ".git").exists() or (root_path / "pyproject.toml").exists():
                        break
                    root_path = root_path.parent
                _, index = WorkspaceManager.get_or_create_workspace(str(root_path))

            mover = SymbolMover(index)
            resolved_path = str(Path(file_path).resolve())
            if expected_hash or expected_mtime is not None:
                expected_mtimes = (
                    {resolved_path: expected_mtime} if expected_mtime is not None else None
                )
                error = _validate_expected_hashes(
                    [resolved_path],
                    {resolved_path: expected_hash} if expected_hash else None,
                    expected_mtimes,
                )
                if error:
                    return json.dumps(error, indent=2)
            result = mover.safe_delete(file_path, symbol_name, confirm)

            logger.info(
                "Safe delete check completed",
                extra={
                    "extra_fields": {
                        "symbol": symbol_name,
                        "can_delete": result.can_delete,
                        "usages": result.usages,
                        "deleted": result.deleted,
                    }
                },
            )

            return json.dumps(result.to_dict(), indent=2)
    except Exception as e:
        logger.error("Safe delete failed", exc_info=True)
        return json.dumps({"error": f"Failed to check safe delete: {str(e)}"}, indent=2)


@mcp_tool
def add_parameter(
    file_path: str,
    function_name: str,
    param_name: str,
    param_type: Optional[str] = None,
    default_value: Optional[str] = None,
    position: int = -1,
    preview: bool = True,
    workspace_id: Optional[str] = None,
    expected_hashes: Optional[Dict[str, str]] = None,
    expected_mtimes: Optional[Dict[str, float]] = None,
) -> str:
    """
    Add a parameter to a function and update all call sites.

    Saves tokens by automatically updating all callers with the default value,
    instead of requiring manual updates to each call site.

    Args:
        file_path: Path to the file containing the function
        function_name: Name of the function to modify
        param_name: Name of the new parameter
        param_type: Optional type annotation (e.g., "str", "int", "List[str]")
        default_value: Default value for the parameter (required for existing callers)
        position: Position to insert the parameter (-1 for end)
        preview: If True, only show what would change
        workspace_id: Optional workspace ID

    Returns:
        JSON string with changes and affected call sites
    """
    try:
        with PerformanceLogger(logger, "add_parameter", function=function_name):
            # Get or create workspace
            if workspace_id:
                index = WorkspaceManager.get_workspace(workspace_id)
                if not index:
                    return json.dumps({"error": f"Workspace '{workspace_id}' not found"}, indent=2)
            else:
                root_path = Path(file_path).parent
                while root_path.parent != root_path:
                    if (root_path / ".git").exists() or (root_path / "pyproject.toml").exists():
                        break
                    root_path = root_path.parent
                _, index = WorkspaceManager.get_or_create_workspace(str(root_path))

            changer = SignatureChanger(index)

            if (expected_hashes or expected_mtimes) and not preview:
                preview_result = changer.add_parameter(
                    file_path,
                    function_name,
                    param_name,
                    param_type,
                    default_value,
                    position,
                    preview=True,
                )
                files = {str(Path(file_path).resolve())}
                files.update({cs.file_path for cs in preview_result.call_sites_updated})
                error = _validate_expected_hashes(sorted(files), expected_hashes, expected_mtimes)
                if error:
                    return json.dumps(error, indent=2)

            result = changer.add_parameter(
                file_path,
                function_name,
                param_name,
                param_type,
                default_value,
                position,
                preview,
            )

            logger.info(
                "Add parameter completed",
                extra={
                    "extra_fields": {
                        "function": function_name,
                        "param": param_name,
                        "call_sites": result.total_call_sites,
                        "preview": preview,
                    }
                },
            )

            return json.dumps(result.to_dict(), indent=2)
    except Exception as e:
        logger.error("Add parameter failed", exc_info=True)
        return json.dumps({"error": f"Failed to add parameter: {str(e)}"}, indent=2)


@mcp_tool
def change_signature(
    file_path: str,
    function_name: str,
    new_params: List[Dict[str, Any]],
    preview: bool = True,
    workspace_id: Optional[str] = None,
    expected_hashes: Optional[Dict[str, str]] = None,
    expected_mtimes: Optional[Dict[str, float]] = None,
) -> str:
    """
    Change a function's entire signature and update all call sites.

    Supports reordering, renaming, adding, and removing parameters in one operation.

    Args:
        file_path: Path to the file containing the function
        function_name: Name of the function to modify
        new_params: List of parameter definitions, each with:
            - name: Parameter name (required)
            - type: Optional type annotation
            - default: Optional default value
        preview: If True, only show what would change
        workspace_id: Optional workspace ID

    Returns:
        JSON string with changes and affected call sites
    """
    try:
        with PerformanceLogger(logger, "change_signature", function=function_name):
            # Get or create workspace
            if workspace_id:
                index = WorkspaceManager.get_workspace(workspace_id)
                if not index:
                    return json.dumps({"error": f"Workspace '{workspace_id}' not found"}, indent=2)
            else:
                root_path = Path(file_path).parent
                while root_path.parent != root_path:
                    if (root_path / ".git").exists() or (root_path / "pyproject.toml").exists():
                        break
                    root_path = root_path.parent
                _, index = WorkspaceManager.get_or_create_workspace(str(root_path))

            changer = SignatureChanger(index)

            if (expected_hashes or expected_mtimes) and not preview:
                preview_result = changer.change_signature(
                    file_path, function_name, new_params, preview=True
                )
                files = {str(Path(file_path).resolve())}
                files.update({cs.file_path for cs in preview_result.call_sites_updated})
                error = _validate_expected_hashes(sorted(files), expected_hashes, expected_mtimes)
                if error:
                    return json.dumps(error, indent=2)

            result = changer.change_signature(file_path, function_name, new_params, preview)

            logger.info(
                "Change signature completed",
                extra={
                    "extra_fields": {
                        "function": function_name,
                        "changes": len(result.changes),
                        "call_sites": result.total_call_sites,
                        "preview": preview,
                    }
                },
            )

            return json.dumps(result.to_dict(), indent=2)
    except Exception as e:
        logger.error("Change signature failed", exc_info=True)
        return json.dumps({"error": f"Failed to change signature: {str(e)}"}, indent=2)


@mcp_tool
def batch_rename(
    renames: List[Dict[str, str]],
    root_path: Optional[str] = None,
    workspace_id: Optional[str] = None,
    preview: bool = True,
    stop_on_error: bool = False,
    expected_hashes: Optional[Dict[str, str]] = None,
    expected_mtimes: Optional[Dict[str, float]] = None,
) -> str:
    """
    Perform multiple rename operations in a single call.

    Saves tokens by batching multiple renames instead of making separate calls.

    Args:
        renames: List of rename operations, each with "old" and "new" keys
            Example: [{"old": "foo", "new": "bar"}, {"old": "baz", "new": "qux"}]
        root_path: Project root path (required if workspace_id not provided)
        workspace_id: Optional workspace ID
        preview: If True, only show what would change
        stop_on_error: If True, stop on first error

    Returns:
        JSON string with results of all renames
    """
    try:
        with PerformanceLogger(logger, "batch_rename", count=len(renames)):
            # Get or create workspace
            if workspace_id:
                index = WorkspaceManager.get_workspace(workspace_id)
                if not index:
                    return json.dumps({"error": f"Workspace '{workspace_id}' not found"}, indent=2)
            elif root_path:
                _, index = WorkspaceManager.get_or_create_workspace(root_path)
            else:
                return json.dumps(
                    {"error": "Either root_path or workspace_id must be provided"}, indent=2
                )

            batch_ops = BatchOperations(index)
            if (expected_hashes or expected_mtimes) and not preview:
                preview_result = batch_ops.batch_rename(renames, preview=True, stop_on_error=stop_on_error)
                files = set()
                for item in preview_result.renames:
                    if item.result:
                        files.update({c.file_path for c in item.result.changes})
                error = _validate_expected_hashes(sorted(files), expected_hashes, expected_mtimes)
                if error:
                    return json.dumps(error, indent=2)

            result = batch_ops.batch_rename(renames, preview, stop_on_error)

            logger.info(
                "Batch rename completed",
                extra={
                    "extra_fields": {
                        "total_requested": result.total_requested,
                        "succeeded": result.total_succeeded,
                        "failed": result.total_failed,
                        "preview": preview,
                    }
                },
            )

            return json.dumps(result.to_dict(), indent=2)
    except Exception as e:
        logger.error("Batch rename failed", exc_info=True)
        return json.dumps({"error": f"Failed to batch rename: {str(e)}"}, indent=2)


@mcp_tool
def batch_organize_imports(
    root_path: Optional[str] = None,
    workspace_id: Optional[str] = None,
    file_pattern: Optional[str] = None,
    languages: Optional[List[str]] = None,
    dry_run: bool = False,
    expected_hashes: Optional[Dict[str, str]] = None,
    expected_mtimes: Optional[Dict[str, float]] = None,
) -> str:
    """
    Organize imports across multiple files in one operation.

    Saves tokens by processing many files at once instead of individual calls.

    Args:
        root_path: Project root path (required if workspace_id not provided)
        workspace_id: Optional workspace ID
        file_pattern: Glob pattern to match files (e.g., "**/*.py")
        languages: List of languages to process (e.g., ["python", "javascript"])
        dry_run: If True, only report what would change

    Returns:
        JSON string with processing results
    """
    try:
        with PerformanceLogger(logger, "batch_organize_imports"):
            # Get or create workspace
            if workspace_id:
                index = WorkspaceManager.get_workspace(workspace_id)
                if not index:
                    return json.dumps({"error": f"Workspace '{workspace_id}' not found"}, indent=2)
            elif root_path:
                _, index = WorkspaceManager.get_or_create_workspace(root_path)
            else:
                return json.dumps(
                    {"error": "Either root_path or workspace_id must be provided"}, indent=2
                )

            batch_ops = BatchOperations(index)
            if (expected_hashes or expected_mtimes) and not dry_run:
                files_to_process = batch_ops._get_files_to_process(file_pattern, languages)
                error = _validate_expected_hashes(
                    sorted(files_to_process), expected_hashes, expected_mtimes
                )
                if error:
                    return json.dumps(error, indent=2)
            result = batch_ops.batch_organize_imports(file_pattern, languages, dry_run)

            logger.info(
                "Batch organize imports completed",
                extra={
                    "extra_fields": {
                        "files_processed": result.files_processed,
                        "files_modified": result.files_modified,
                        "dry_run": dry_run,
                    }
                },
            )

            return json.dumps(result.to_dict(), indent=2)
    except Exception as e:
        logger.error("Batch organize imports failed", exc_info=True)
        return json.dumps({"error": f"Failed to batch organize imports: {str(e)}"}, indent=2)


@mcp_tool
def bulk_analysis(
    root_path: Optional[str] = None,
    workspace_id: Optional[str] = None,
    files: Optional[List[str]] = None,
    file_pattern: Optional[str] = None,
    analyses: Optional[List[str]] = None,
) -> str:
    """
    Perform multiple analyses on multiple files in one call.

    Saves tokens by returning comprehensive analysis in a single response
    instead of multiple round-trips.

    Args:
        root_path: Project root path (required if workspace_id not provided)
        workspace_id: Optional workspace ID
        files: List of specific files to analyze
        file_pattern: Glob pattern to match files
        analyses: Types of analysis to perform:
            - "structure": Code structure (functions, classes)
            - "dependencies": Import analysis
            - "dead_code": Dead code detection
            - "all": All analyses

    Returns:
        JSON string with comprehensive analysis results
    """
    try:
        with PerformanceLogger(logger, "bulk_analysis"):
            # Get or create workspace
            if workspace_id:
                index = WorkspaceManager.get_workspace(workspace_id)
                if not index:
                    return json.dumps({"error": f"Workspace '{workspace_id}' not found"}, indent=2)
            elif root_path:
                _, index = WorkspaceManager.get_or_create_workspace(root_path)
            else:
                return json.dumps(
                    {"error": "Either root_path or workspace_id must be provided"}, indent=2
                )

            batch_ops = BatchOperations(index)
            result = batch_ops.bulk_analysis(files, file_pattern, analyses)

            logger.info(
                "Bulk analysis completed",
                extra={
                    "extra_fields": {
                        "files_analyzed": result.files_analyzed,
                        "analyses": analyses,
                    }
                },
            )

            return json.dumps(result.to_dict(), indent=2)
    except Exception as e:
        logger.error("Bulk analysis failed", exc_info=True)
        return json.dumps({"error": f"Failed to perform bulk analysis: {str(e)}"}, indent=2)


@mcp_tool
def generate_imports(
    file_path: str,
    preview: bool = True,
    include_stdlib: bool = True,
    include_project: bool = True,
    workspace_id: Optional[str] = None,
    expected_hash: Optional[str] = None,
    expected_mtime: Optional[float] = None,
) -> str:
    """
    Auto-generate import statements for undefined symbols in a file.

    Saves tokens by automatically determining where symbols should be imported from,
    instead of requiring the LLM to look up module locations.

    Args:
        file_path: Path to the file to process
        preview: If True, only show suggestions; if False, apply them
        include_stdlib: Include standard library suggestions
        include_project: Include project-local suggestions
        workspace_id: Optional workspace ID

    Returns:
        JSON string with import suggestions and any added imports
    """
    try:
        with PerformanceLogger(logger, "generate_imports", file=file_path):
            # Get or create workspace
            if workspace_id:
                index = WorkspaceManager.get_workspace(workspace_id)
                if not index:
                    return json.dumps({"error": f"Workspace '{workspace_id}' not found"}, indent=2)
            else:
                root_path = Path(file_path).parent
                while root_path.parent != root_path:
                    if (root_path / ".git").exists() or (root_path / "pyproject.toml").exists():
                        break
                    root_path = root_path.parent
                _, index = WorkspaceManager.get_or_create_workspace(str(root_path))

            resolved_path = str(Path(file_path).resolve())
            if (expected_hash or expected_mtime is not None) and not preview:
                expected_mtimes = (
                    {resolved_path: expected_mtime} if expected_mtime is not None else None
                )
                error = _validate_expected_hashes(
                    [resolved_path],
                    {resolved_path: expected_hash} if expected_hash else None,
                    expected_mtimes,
                )
                if error:
                    return json.dumps(error, indent=2)

            generator = ImportGenerator(index)
            result = generator.generate_imports(file_path, preview, include_stdlib, include_project)

            logger.info(
                "Generate imports completed",
                extra={
                    "extra_fields": {
                        "file": file_path,
                        "undefined": len(result.undefined_symbols),
                        "suggestions": len(result.suggestions),
                        "applied": result.applied,
                    }
                },
            )

            return json.dumps(result.to_dict(), indent=2)
    except Exception as e:
        logger.error("Generate imports failed", exc_info=True)
        return json.dumps({"error": f"Failed to generate imports: {str(e)}"}, indent=2)


@mcp_tool
def find_unused_exports(
    root_path: Optional[str] = None,
    workspace_id: Optional[str] = None,
    file_pattern: Optional[str] = None,
    files: Optional[List[str]] = None,
) -> str:
    """
    Find exports that are not imported by any other file.

    Helps identify dead code at the module level.

    Args:
        root_path: Project root path (required if workspace_id not provided)
        workspace_id: Optional workspace ID
        file_pattern: Glob pattern to match files
        files: List of specific files to check

    Returns:
        JSON string with list of unused exports
    """
    try:
        with PerformanceLogger(logger, "find_unused_exports"):
            # Get or create workspace
            if workspace_id:
                index = WorkspaceManager.get_workspace(workspace_id)
                if not index:
                    return json.dumps({"error": f"Workspace '{workspace_id}' not found"}, indent=2)
            elif root_path:
                _, index = WorkspaceManager.get_or_create_workspace(root_path)
            else:
                return json.dumps(
                    {"error": "Either root_path or workspace_id must be provided"}, indent=2
                )

            generator = ImportGenerator(index)
            result = generator.find_unused_exports(file_pattern, files)

            logger.info(
                "Find unused exports completed",
                extra={
                    "extra_fields": {
                        "total_exports": result.total_exports,
                        "unused_count": len(result.unused_exports),
                        "files_checked": result.files_checked,
                    }
                },
            )

            return json.dumps(result.to_dict(), indent=2)
    except Exception as e:
        logger.error("Find unused exports failed", exc_info=True)
        return json.dumps({"error": f"Failed to find unused exports: {str(e)}"}, indent=2)


@mcp_tool
def get_reverse_dependencies(
    file_path: str,
    workspace_id: Optional[str] = None,
) -> str:
    """
    Get all files that depend on (import from) a given file.

    This is the reverse of analyzing imports - shows "what depends on this file".
    Essential for understanding impact of changes.

    Args:
        file_path: Path to the file
        workspace_id: Optional workspace ID

    Returns:
        JSON string with list of dependent files
    """
    try:
        with PerformanceLogger(logger, "get_reverse_dependencies", file=file_path):
            # Get or create workspace
            if workspace_id:
                index = WorkspaceManager.get_workspace(workspace_id)
                if not index:
                    return json.dumps({"error": f"Workspace '{workspace_id}' not found"}, indent=2)
            else:
                root_path = Path(file_path).parent
                while root_path.parent != root_path:
                    if (root_path / ".git").exists() or (root_path / "pyproject.toml").exists():
                        break
                    root_path = root_path.parent
                _, index = WorkspaceManager.get_or_create_workspace(str(root_path))

            result = index.get_reverse_dependencies(file_path)

            logger.info(
                "Reverse dependencies found",
                extra={
                    "extra_fields": {
                        "file": file_path,
                        "dependents": result.get("dependent_count", 0),
                    }
                },
            )

            return json.dumps(result, indent=2)
    except Exception as e:
        logger.error("Get reverse dependencies failed", exc_info=True)
        return json.dumps({"error": f"Failed to get reverse dependencies: {str(e)}"}, indent=2)


@mcp_tool
def get_dependency_graph(
    root_path: Optional[str] = None,
    workspace_id: Optional[str] = None,
    max_depth: int = 3,
) -> str:
    """
    Build a complete dependency graph for the project.

    Returns nodes (files) and edges (imports) representing the project structure.

    Args:
        root_path: Project root path (required if workspace_id not provided)
        workspace_id: Optional workspace ID
        max_depth: Maximum depth to traverse

    Returns:
        JSON string with graph data (nodes and edges)
    """
    try:
        with PerformanceLogger(logger, "get_dependency_graph"):
            # Get or create workspace
            if workspace_id:
                index = WorkspaceManager.get_workspace(workspace_id)
                if not index:
                    return json.dumps({"error": f"Workspace '{workspace_id}' not found"}, indent=2)
            elif root_path:
                _, index = WorkspaceManager.get_or_create_workspace(root_path)
            else:
                return json.dumps(
                    {"error": "Either root_path or workspace_id must be provided"}, indent=2
                )

            result = index.get_dependency_graph(max_depth)

            logger.info(
                "Dependency graph built",
                extra={
                    "extra_fields": {
                        "nodes": result.get("node_count", 0),
                        "edges": result.get("edge_count", 0),
                    }
                },
            )

            return json.dumps(result, indent=2)
    except Exception as e:
        logger.error("Get dependency graph failed", exc_info=True)
        return json.dumps({"error": f"Failed to build dependency graph: {str(e)}"}, indent=2)


@mcp_tool
def analyze_impact(
    file_path: str,
    max_depth: int = 3,
    workspace_id: Optional[str] = None,
) -> str:
    """
    Analyze the impact of changing a file.

    Shows all files that would be affected directly and transitively.

    Args:
        file_path: Path to the file to analyze
        max_depth: How many levels of dependents to traverse
        workspace_id: Optional workspace ID

    Returns:
        JSON string with direct and transitive dependents
    """
    try:
        with PerformanceLogger(logger, "analyze_impact", file=file_path):
            # Get or create workspace
            if workspace_id:
                index = WorkspaceManager.get_workspace(workspace_id)
                if not index:
                    return json.dumps({"error": f"Workspace '{workspace_id}' not found"}, indent=2)
            else:
                root_path = Path(file_path).parent
                while root_path.parent != root_path:
                    if (root_path / ".git").exists() or (root_path / "pyproject.toml").exists():
                        break
                    root_path = root_path.parent
                _, index = WorkspaceManager.get_or_create_workspace(str(root_path))

            result = index.analyze_impact(file_path, max_depth)

            logger.info(
                "Impact analysis completed",
                extra={
                    "extra_fields": {
                        "file": file_path,
                        "direct": result.get("direct_count", 0),
                        "transitive": result.get("transitive_count", 0),
                        "total": result.get("total_affected", 0),
                    }
                },
            )

            return json.dumps(result, indent=2)
    except Exception as e:
        logger.error("Analyze impact failed", exc_info=True)
        return json.dumps({"error": f"Failed to analyze impact: {str(e)}"}, indent=2)


@mcp_tool
def extract_constant(
    file_path: str,
    value: str,
    constant_name: str,
    scope: str = "file",
    preview: bool = True,
    workspace_id: Optional[str] = None,
    expected_hashes: Optional[Dict[str, str]] = None,
    expected_mtimes: Optional[Dict[str, float]] = None,
) -> str:
    """
    Extract a literal value into a named constant.

    Finds all occurrences of the value and replaces them with the constant.

    Args:
        file_path: Path to the file
        value: The literal value to extract (string, number, etc.)
        constant_name: Name for the new constant
        scope: "file" for current file, "project" for all files
        preview: If True, only show what would change
        workspace_id: Optional workspace ID

    Returns:
        JSON string with extraction details
    """
    try:
        with PerformanceLogger(logger, "extract_constant", constant=constant_name):
            # Get or create workspace
            if workspace_id:
                index = WorkspaceManager.get_workspace(workspace_id)
                if not index:
                    return json.dumps({"error": f"Workspace '{workspace_id}' not found"}, indent=2)
            else:
                root_path = Path(file_path).parent
                while root_path.parent != root_path:
                    if (root_path / ".git").exists() or (root_path / "pyproject.toml").exists():
                        break
                    root_path = root_path.parent
                _, index = WorkspaceManager.get_or_create_workspace(str(root_path))

            batch_ops = BatchOperations(index)
            if (expected_hashes or expected_mtimes) and not preview:
                preview_result = batch_ops.extract_constant(
                    file_path, value, constant_name, scope, preview=True
                )
                files = {str(Path(file_path).resolve())}
                files.update({occ.get("file") for occ in preview_result.get("occurrences", [])})
                files.discard(None)
                error = _validate_expected_hashes(sorted(files), expected_hashes, expected_mtimes)
                if error:
                    return json.dumps(error, indent=2)

            result = batch_ops.extract_constant(file_path, value, constant_name, scope, preview)

            logger.info(
                "Extract constant completed",
                extra={
                    "extra_fields": {
                        "constant": constant_name,
                        "occurrences": len(result.get("occurrences", [])),
                        "applied": result.get("applied", False),
                    }
                },
            )

            return json.dumps(result, indent=2)
    except Exception as e:
        logger.error("Extract constant failed", exc_info=True)
        return json.dumps({"error": f"Failed to extract constant: {str(e)}"}, indent=2)


@mcp_tool
def inline_variable(
    file_path: str,
    variable_name: str,
    preview: bool = True,
    workspace_id: Optional[str] = None,
    expected_hash: Optional[str] = None,
    expected_mtime: Optional[float] = None,
) -> str:
    """
    Inline a variable by replacing its usages with its value.

    Args:
        file_path: Path to the file
        variable_name: Name of the variable to inline
        preview: If True, only show what would change
        workspace_id: Optional workspace ID

    Returns:
        JSON string with inlining details
    """
    try:
        with PerformanceLogger(logger, "inline_variable", variable=variable_name):
            # Get or create workspace
            if workspace_id:
                index = WorkspaceManager.get_workspace(workspace_id)
                if not index:
                    return json.dumps({"error": f"Workspace '{workspace_id}' not found"}, indent=2)
            else:
                root_path = Path(file_path).parent
                while root_path.parent != root_path:
                    if (root_path / ".git").exists() or (root_path / "pyproject.toml").exists():
                        break
                    root_path = root_path.parent
                _, index = WorkspaceManager.get_or_create_workspace(str(root_path))

            batch_ops = BatchOperations(index)
            resolved_path = str(Path(file_path).resolve())
            if expected_hash or expected_mtime is not None:
                expected_mtimes = (
                    {resolved_path: expected_mtime} if expected_mtime is not None else None
                )
                error = _validate_expected_hashes(
                    [resolved_path],
                    {resolved_path: expected_hash} if expected_hash else None,
                    expected_mtimes,
                )
                if error:
                    return json.dumps(error, indent=2)
            result = batch_ops.inline_variable(file_path, variable_name, preview)

            logger.info(
                "Inline variable completed",
                extra={
                    "extra_fields": {
                        "variable": variable_name,
                        "usages": result.get("usages_replaced", 0),
                        "applied": result.get("applied", False),
                    }
                },
            )

            return json.dumps(result, indent=2)
    except Exception as e:
        logger.error("Inline variable failed", exc_info=True)
        return json.dumps({"error": f"Failed to inline variable: {str(e)}"}, indent=2)


def main():
    """Run the multi-language MCP server."""
    logger.info("Starting Multi-Language Refactor MCP Server")
    logger.info(f"Supported languages: {', '.join(language_registry.list_supported_languages())}")

    # Log server startup metrics
    startup_metrics = {
        "languages_loaded": len(language_registry.list_supported_languages()),
        "extensions_supported": len(language_registry.list_supported_extensions()),
        "startup_time": datetime.utcnow().isoformat() + "Z",
    }

    logger.info("MCP Server ready", extra={"extra_fields": startup_metrics})

    try:
        mcp.run()
    except KeyboardInterrupt:
        logger.info("Server shutdown requested")
    except Exception:
        logger.error("Server error", exc_info=True)
        raise


if __name__ == "__main__":
    main()

"""Structured logging configuration for the MCP server."""

import json
import logging
import sys
import time
from datetime import datetime
from pathlib import Path
from typing import Optional


class StructuredFormatter(logging.Formatter):
    """Custom formatter that outputs structured JSON logs."""

    def format(self, record: logging.LogRecord) -> str:
        """Format log record as structured JSON."""
        log_entry = {
            "timestamp": datetime.utcnow().isoformat() + "Z",
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
            "module": record.module,
            "function": record.funcName,
            "line": record.lineno,
        }

        # Add exception info if present
        if record.exc_info:
            log_entry["exception"] = self.formatException(record.exc_info)

        # Add extra fields from the record
        if hasattr(record, "extra_fields"):
            log_entry.update(record.extra_fields)

        return json.dumps(log_entry)


class PerformanceLogger:
    """Context manager for logging operation performance."""

    def __init__(self, logger: logging.Logger, operation: str, **context):
        self.logger = logger
        self.operation = operation
        self.context = context
        self.start_time: Optional[float] = None

    def __enter__(self):
        self.start_time = time.time()
        self.logger.info(
            f"Starting operation: {self.operation}",
            extra={
                "extra_fields": {"operation": self.operation, "status": "started", **self.context}
            },
        )
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        start_time = self.start_time if self.start_time is not None else time.time()
        duration = time.time() - start_time

        if exc_type is None:
            self.logger.info(
                f"Completed operation: {self.operation}",
                extra={
                    "extra_fields": {
                        "operation": self.operation,
                        "status": "completed",
                        "duration_ms": round(duration * 1000, 2),
                        **self.context,
                    }
                },
            )
        else:
            self.logger.error(
                f"Failed operation: {self.operation}",
                extra={
                    "extra_fields": {
                        "operation": self.operation,
                        "status": "failed",
                        "duration_ms": round(duration * 1000, 2),
                        "error": str(exc_val),
                        "error_type": exc_type.__name__ if exc_type else None,
                        **self.context,
                    }
                },
                exc_info=True,
            )


def setup_logging(
    level: str = "INFO",
    log_file: Optional[Path] = None,
    structured: bool = True,
    console: bool = True,
) -> logging.Logger:
    """Set up structured logging for the MCP server.

    Args:
        level: Logging level (DEBUG, INFO, WARNING, ERROR)
        log_file: Optional file path for logging output
        structured: Whether to use structured JSON logging
        console: Whether to log to console

    Returns:
        Configured logger instance
    """
    # Clear existing handlers
    logging.getLogger().handlers.clear()

    # Set logging level
    numeric_level = getattr(logging, level.upper(), logging.INFO)
    logging.getLogger().setLevel(numeric_level)

    # Create formatters
    formatter: logging.Formatter
    if structured:
        formatter = StructuredFormatter()
    else:
        formatter = logging.Formatter(
            fmt="%(asctime)s - %(name)s - %(levelname)s - %(message)s", datefmt="%Y-%m-%d %H:%M:%S"
        )

    # Console handler
    if console:
        console_handler = logging.StreamHandler(sys.stdout)
        console_handler.setFormatter(formatter)
        logging.getLogger().addHandler(console_handler)

    # File handler
    if log_file:
        log_file.parent.mkdir(parents=True, exist_ok=True)
        file_handler = logging.FileHandler(log_file)
        file_handler.setFormatter(formatter)
        logging.getLogger().addHandler(file_handler)

    # Get the root logger for MCP server
    logger = logging.getLogger("refactor_mcp")
    logger.setLevel(numeric_level)

    return logger


def get_logger(name: str) -> logging.Logger:
    """Get a logger with the specified name."""
    return logging.getLogger(f"refactor_mcp.{name}")


def log_operation_metrics(
    logger: logging.Logger,
    operation: str,
    file_path: str,
    language: str,
    duration_ms: float,
    success: bool = True,
    error: Optional[str] = None,
    **extra_context,
):
    """Log standardized operation metrics.

    Args:
        logger: Logger instance
        operation: Name of the operation
        file_path: Path of the file being processed
        language: Detected language
        duration_ms: Operation duration in milliseconds
        success: Whether the operation succeeded
        error: Error message if operation failed
        **extra_context: Additional context fields
    """
    log_data = {
        "operation": operation,
        "file_path": file_path,
        "language": language,
        "duration_ms": round(duration_ms, 2),
        "success": success,
        **extra_context,
    }

    if error:
        log_data["error"] = error

    if success:
        logger.info(f"Operation completed: {operation}", extra={"extra_fields": log_data})
    else:
        logger.error(f"Operation failed: {operation}", extra={"extra_fields": log_data})


# Pre-configured loggers for different components
server_logger = get_logger("server")
language_logger = get_logger("language")
performance_logger = get_logger("performance")
security_logger = get_logger("security")

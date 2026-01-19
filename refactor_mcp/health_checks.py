"""Health check system for the MCP server."""

import tempfile
import time
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, Optional

from .languages import get_handler_by_language, list_supported_languages
from .logging_config import get_logger

logger = get_logger("health")


class HealthStatus:
    """Health status enumeration."""

    HEALTHY = "healthy"
    DEGRADED = "degraded"
    UNHEALTHY = "unhealthy"


class HealthChecker:
    """Comprehensive health check system for the MCP server."""

    def __init__(self):
        self.start_time = datetime.utcnow()
        self._last_check_results: Dict[str, Any] = {}

    def get_uptime(self) -> float:
        """Get server uptime in seconds."""
        return (datetime.utcnow() - self.start_time).total_seconds()

    def check_language_handlers(self) -> Dict[str, Any]:
        """Check the health of all language handlers."""
        start_time = time.time()
        results: Dict[str, Any] = {
            "status": HealthStatus.HEALTHY,
            "handlers": {},
            "total_handlers": 0,
            "healthy_handlers": 0,
            "errors": [],
        }

        try:
            languages = list_supported_languages()
            results["total_handlers"] = len(languages)

            for language in languages:
                handler_result = self._check_single_handler(language)
                results["handlers"][language] = handler_result

                if handler_result["status"] == HealthStatus.HEALTHY:
                    results["healthy_handlers"] += 1
                else:
                    results["errors"].append(
                        f"{language}: {handler_result.get('error', 'Unknown error')}"
                    )

            # Determine overall status
            if results["healthy_handlers"] == 0:
                results["status"] = HealthStatus.UNHEALTHY
            elif results["healthy_handlers"] < results["total_handlers"]:
                results["status"] = HealthStatus.DEGRADED

        except Exception as e:
            results["status"] = HealthStatus.UNHEALTHY
            results["errors"].append(f"Handler enumeration failed: {str(e)}")
            logger.error("Handler health check failed", exc_info=True)

        results["check_duration_ms"] = round((time.time() - start_time) * 1000, 2)
        return results

    def _check_single_handler(self, language: str) -> Dict[str, Any]:
        """Check the health of a single language handler."""
        result: Dict[str, Any] = {
            "status": HealthStatus.HEALTHY,
            "language": language,
            "operations": {},
            "error": None,
        }

        try:
            handler = get_handler_by_language(language)
            if not handler:
                result["status"] = HealthStatus.UNHEALTHY
                result["error"] = "Handler not found"
                return result

            # Test basic handler properties
            result["extensions"] = handler.file_extensions
            result["operations"]["extensions"] = len(handler.file_extensions) > 0

            # Test basic functionality with a temporary file
            self._test_handler_operations(handler, result)

        except Exception as e:
            result["status"] = HealthStatus.UNHEALTHY
            result["error"] = str(e)
            logger.error(f"Handler health check failed for {language}", exc_info=True)

        return result

    def _test_handler_operations(self, handler: Any, result: Dict[str, Any]):
        """Test basic operations of a handler."""
        try:
            # Create a temporary test file
            test_content = self._get_test_content(handler.language_name)
            if not test_content:
                result["operations"]["test_skipped"] = "No test content available"
                return

            with tempfile.NamedTemporaryFile(
                mode="w", suffix=handler.file_extensions[0], delete=False
            ) as temp_file:
                temp_file.write(test_content)
                temp_file_path = temp_file.name

            try:
                # Test file detection
                result["operations"]["can_handle_file"] = handler.can_handle_file(temp_file_path)

                # Test structure analysis
                if hasattr(handler, "get_code_structure"):
                    structure = handler.get_code_structure(temp_file_path)
                    result["operations"]["get_code_structure"] = structure is not None

                # Test import organization
                if hasattr(handler, "organize_imports"):
                    organize_result = handler.organize_imports(temp_file_path)
                    result["operations"]["organize_imports"] = (
                        "successfully" in organize_result.lower()
                    )

            finally:
                # Clean up temp file
                Path(temp_file_path).unlink(missing_ok=True)

        except Exception as e:
            result["operations"]["test_error"] = str(e)
            logger.warning(f"Handler operation test failed for {handler.language_name}: {e}")

    def _get_test_content(self, language: str) -> Optional[str]:
        """Get minimal test content for each language."""
        test_contents = {
            "Python": "import os\n\ndef test_function():\n    return 'test'",
            "JavaScript": "const fs = require('fs');\n\nfunction testFunction() {\n    return 'test';\n}",
            "TypeScript": "interface TestInterface {\n    value: string;\n}\n\nfunction testFunction(): string {\n    return 'test';\n}",
            "HTML": "<!DOCTYPE html>\n<html>\n<head>\n    <title>Test</title>\n</head>\n<body>\n    <p>Test</p>\n</body>\n</html>",
            "CSS": "body {\n    color: red;\n}\n\n.test-class {\n    display: flex;\n}",
            "Go": 'package main\n\nimport "fmt"\n\nfunc testFunction() string {\n    return "test"\n}',
        }
        return test_contents.get(language)

    def check_file_system(self) -> Dict[str, Any]:
        """Check file system access and temporary directory availability."""
        start_time = time.time()
        result: Dict[str, Any] = {
            "status": HealthStatus.HEALTHY,
            "temp_dir_writable": False,
            "temp_dir_path": None,
            "error": None,
        }

        try:
            # Test temporary directory access
            with tempfile.NamedTemporaryFile(mode="w", delete=True) as temp_file:
                temp_file.write("health check test")
                temp_file.flush()
                result["temp_dir_writable"] = True
                result["temp_dir_path"] = str(Path(temp_file.name).parent)

        except Exception as e:
            result["status"] = HealthStatus.UNHEALTHY
            result["error"] = f"Temp directory access failed: {str(e)}"
            logger.error("File system health check failed", exc_info=True)

        result["check_duration_ms"] = round((time.time() - start_time) * 1000, 2)
        return result

    def check_memory_usage(self) -> Dict[str, Any]:
        """Check basic memory usage indicators."""
        result: Dict[str, Any] = {
            "status": HealthStatus.HEALTHY,
            "uptime_seconds": round(self.get_uptime(), 2),
        }

        try:
            import psutil

            process = psutil.Process()
            memory_info = process.memory_info()

            result["memory_usage_mb"] = round(memory_info.rss / 1024 / 1024, 2)
            result["memory_percent"] = round(process.memory_percent(), 2)

            # Flag if memory usage is concerning (over 500MB)
            if result["memory_usage_mb"] > 500:
                result["status"] = HealthStatus.DEGRADED
                result["warning"] = "High memory usage detected"

        except ImportError:
            result["memory_monitoring"] = "psutil not available"
        except Exception as e:
            result["error"] = f"Memory check failed: {str(e)}"
            logger.warning("Memory health check failed", exc_info=True)

        return result

    def perform_comprehensive_check(self) -> Dict[str, Any]:
        """Perform all health checks and return comprehensive status."""
        start_time = time.time()

        logger.info("Starting comprehensive health check")

        health_report: Dict[str, Any] = {
            "timestamp": datetime.utcnow().isoformat() + "Z",
            "overall_status": HealthStatus.HEALTHY,
            "checks": {
                "language_handlers": self.check_language_handlers(),
                "file_system": self.check_file_system(),
                "memory": self.check_memory_usage(),
            },
            "summary": {
                "total_checks": 3,
                "healthy_checks": 0,
                "degraded_checks": 0,
                "unhealthy_checks": 0,
            },
        }

        # Analyze check results
        for check_name, check_result in health_report["checks"].items():
            status = check_result["status"]
            if status == HealthStatus.HEALTHY:
                health_report["summary"]["healthy_checks"] += 1
            elif status == HealthStatus.DEGRADED:
                health_report["summary"]["degraded_checks"] += 1
            else:
                health_report["summary"]["unhealthy_checks"] += 1

        # Determine overall status
        if health_report["summary"]["unhealthy_checks"] > 0:
            health_report["overall_status"] = HealthStatus.UNHEALTHY
        elif health_report["summary"]["degraded_checks"] > 0:
            health_report["overall_status"] = HealthStatus.DEGRADED

        health_report["total_check_duration_ms"] = round((time.time() - start_time) * 1000, 2)

        logger.info(
            "Health check completed",
            extra={
                "extra_fields": {
                    "overall_status": health_report["overall_status"],
                    "duration_ms": health_report["total_check_duration_ms"],
                    "healthy_checks": health_report["summary"]["healthy_checks"],
                    "total_checks": health_report["summary"]["total_checks"],
                }
            },
        )

        # Cache results
        self._last_check_results = health_report

        return health_report

    def get_quick_status(self) -> Dict[str, Any]:
        """Get a quick status without running full checks."""
        return {
            "status": HealthStatus.HEALTHY,
            "uptime_seconds": round(self.get_uptime(), 2),
            "last_full_check": self._last_check_results.get("timestamp"),
            "handlers_available": len(list_supported_languages()),
        }


# Global health checker instance
health_checker = HealthChecker()

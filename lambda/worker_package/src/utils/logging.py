"""Structured logging utilities."""
import json
import logging
from typing import Any, Dict


class StructuredLogger:
    """Structured JSON logger for Lambda/CloudWatch."""

    def __init__(self, name: str = "agent"):
        self.logger = logging.getLogger(name)
        self.logger.setLevel(logging.INFO)

        # Ensure we have a handler
        if not self.logger.handlers:
            handler = logging.StreamHandler()
            handler.setFormatter(logging.Formatter('%(message)s'))
            self.logger.addHandler(handler)
            self.logger.propagate = False

    def info(self, message: str, **kwargs: Any) -> None:
        """Log info level message with structured data."""
        self._log("info", message, **kwargs)

    def error(self, message: str, **kwargs: Any) -> None:
        """Log error level message with structured data."""
        self._log("error", message, **kwargs)

    def warning(self, message: str, **kwargs: Any) -> None:
        """Log warning level message with structured data."""
        self._log("warning", message, **kwargs)

    def _log(self, level: str, message: str, **kwargs: Any) -> None:
        """Internal log method."""
        log_data = {
            "level": level,
            "message": message,
            **kwargs
        }
        self.logger.info(json.dumps(log_data))


# Global logger instance
logger = StructuredLogger("daniels-agent")
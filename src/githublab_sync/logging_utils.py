"""Small logging helper with optional ANSI colour."""

from __future__ import annotations

import logging
import os
import sys

_COLORS = {
    "DEBUG": "\033[36m",
    "INFO": "\033[32m",
    "WARNING": "\033[33m",
    "ERROR": "\033[31m",
    "CRITICAL": "\033[41m",
}
_RESET = "\033[0m"


class _ColorFormatter(logging.Formatter):
    def __init__(self, use_color: bool):
        super().__init__("%(message)s")
        self.use_color = use_color

    def format(self, record: logging.LogRecord) -> str:
        message = super().format(record)
        if self.use_color and record.levelname in _COLORS:
            return f"{_COLORS[record.levelname]}{message}{_RESET}"
        return message


def configure_logging(verbose: bool = False) -> logging.Logger:
    """Configure and return the package logger."""
    logger = logging.getLogger("githublab_sync")
    logger.setLevel(logging.DEBUG if verbose else logging.INFO)
    logger.handlers.clear()

    handler = logging.StreamHandler(sys.stderr)
    use_color = sys.stderr.isatty() and os.environ.get("NO_COLOR") is None
    handler.setFormatter(_ColorFormatter(use_color))
    logger.addHandler(handler)
    logger.propagate = False
    return logger


def get_logger() -> logging.Logger:
    return logging.getLogger("githublab_sync")

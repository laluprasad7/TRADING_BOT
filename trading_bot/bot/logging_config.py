"""
logging_config.py – Structured logging setup for PrimeTrade.

Provides:
  - Rotating compressed log file  (DEBUG level, JSON-like format)
  - Rich console handler           (INFO level, colourised)
"""

from __future__ import annotations

import json
import logging
import logging.handlers
import os
from datetime import datetime, timezone
from pathlib import Path


# ---------------------------------------------------------------------------
# Custom JSON formatter
# ---------------------------------------------------------------------------

class _JSONFormatter(logging.Formatter):
    """Emit each log record as a single-line JSON object."""

    def format(self, record: logging.LogRecord) -> str:  # noqa: A003
        payload: dict = {
            "ts": datetime.fromtimestamp(record.created, tz=timezone.utc).isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
        }
        # Attach extra fields added via logger.info(..., extra={...})
        for key, val in record.__dict__.items():
            if key not in {
                "name", "msg", "args", "levelname", "levelno", "pathname",
                "filename", "module", "exc_info", "exc_text", "stack_info",
                "lineno", "funcName", "created", "msecs", "relativeCreated",
                "thread", "threadName", "processName", "process", "message",
            }:
                payload[key] = val

        if record.exc_info:
            payload["exc_info"] = self.formatException(record.exc_info)

        return json.dumps(payload, default=str)


# ---------------------------------------------------------------------------
# Console formatter (human-readable)
# ---------------------------------------------------------------------------

class _ConsoleFormatter(logging.Formatter):
    COLOURS = {
        "DEBUG":    "\033[36m",   # cyan
        "INFO":     "\033[32m",   # green
        "WARNING":  "\033[33m",   # yellow
        "ERROR":    "\033[31m",   # red
        "CRITICAL": "\033[35m",   # magenta
    }
    RESET = "\033[0m"

    def format(self, record: logging.LogRecord) -> str:  # noqa: A003
        colour = self.COLOURS.get(record.levelname, "")
        ts = datetime.fromtimestamp(record.created, tz=timezone.utc).strftime(
            "%H:%M:%S"
        )
        prefix = f"{colour}[{record.levelname:>8}]{self.RESET} {ts} | {record.name}"
        msg = record.getMessage()
        if record.exc_info:
            msg += "\n" + self.formatException(record.exc_info)
        return f"{prefix} – {msg}"


# ---------------------------------------------------------------------------
# Public setup function
# ---------------------------------------------------------------------------

def setup_logging(
    log_dir: str | Path = "logs",
    log_filename: str = "trading_bot.log",
    console_level: int = logging.INFO,
    file_level: int = logging.DEBUG,
    max_bytes: int = 10 * 1024 * 1024,   # 10 MB
    backup_count: int = 5,
) -> logging.Logger:
    """Configure root logger with file + console handlers.

    Args:
        log_dir:       Directory where the log file is written.
        log_filename:  Base name of the rotating log file.
        console_level: Minimum level emitted to stdout.
        file_level:    Minimum level written to the log file.
        max_bytes:     Max size of each log file before rotation.
        backup_count:  Number of rotated files to keep.

    Returns:
        The root :class:`logging.Logger` instance.
    """
    log_path = Path(log_dir)
    log_path.mkdir(parents=True, exist_ok=True)

    root = logging.getLogger()
    root.setLevel(logging.DEBUG)          # global minimum; handlers filter further

    # Avoid adding duplicate handlers across repeated calls (e.g. in tests)
    if root.handlers:
        return root

    # ── File handler ──────────────────────────────────────────────────────
    file_handler = logging.handlers.RotatingFileHandler(
        log_path / log_filename,
        maxBytes=max_bytes,
        backupCount=backup_count,
        encoding="utf-8",
    )
    file_handler.setLevel(file_level)
    file_handler.setFormatter(_JSONFormatter())

    # ── Console handler ───────────────────────────────────────────────────
    console_handler = logging.StreamHandler()
    console_handler.setLevel(console_level)
    console_handler.setFormatter(_ConsoleFormatter())

    root.addHandler(file_handler)
    root.addHandler(console_handler)

    root.info(
        "Logging initialised",
        extra={"log_file": str(log_path / log_filename)},
    )
    return root

"""
Centralized structured logging mechanism for Tradng-Ai.
Provides:
- Rotating file logging (logs/trading.log) with automatic size capping
- Formatted console output with IST timestamps
- Dynamic log level control (via environment variable LOG_LEVEL or config)
- Structured exception traceback capture for debugging
- Recent log tailing for the dashboard terminal
"""

from datetime import datetime
import logging
from logging.handlers import RotatingFileHandler
import os
from pathlib import Path
from zoneinfo import ZoneInfo

IST = ZoneInfo("Asia/Kolkata")


class ISTFormatter(logging.Formatter):
    """Formats log timestamps in Indian Standard Time (IST)."""

    def formatTime(self, record, datefmt=None):
        dt = datetime.fromtimestamp(record.created, tz=IST)
        if datefmt:
            return dt.strftime(datefmt)
        return dt.strftime("%Y-%m-%d %H:%M:%S.%f")[:-3] + " IST"


_INITIALIZED = False


def setup_logging(cfg=None, log_level=None):
    """
    Initializes the root and Tradng-Ai loggers with rotating file and console handlers.
    Safe to call multiple times (idempotent).
    """
    global _INITIALIZED
    if _INITIALIZED:
        return logging.getLogger("tradng_ai")

    cfg = cfg or {}
    log_cfg = cfg.get("logging", {})

    # Determine log level: Environment variable overrides config
    env_level = os.getenv("LOG_LEVEL", "").upper()
    if env_level in ("DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"):
        level = getattr(logging, env_level)
    elif log_level:
        level = getattr(logging, str(log_level).upper(), logging.INFO)
    else:
        cfg_level = log_cfg.get("level", "INFO").upper()
        level = getattr(logging, cfg_level, logging.INFO)

    root = Path(__file__).resolve().parent.parent
    log_dir = root / "logs"
    log_dir.mkdir(parents=True, exist_ok=True)
    log_file = log_dir / log_cfg.get("file_name", "trading.log")

    max_bytes = int(log_cfg.get("max_bytes", 10 * 1024 * 1024))  # 10 MB
    backup_count = int(log_cfg.get("backup_count", 5))

    formatter = ISTFormatter(
        fmt="[%(asctime)s] [%(levelname)-5s] [%(name)s:%(lineno)d] %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )

    # 1. Rotating File Handler
    file_handler = RotatingFileHandler(
        filename=str(log_file),
        maxBytes=max_bytes,
        backupCount=backup_count,
        encoding="utf-8",
    )
    file_handler.setLevel(level)
    file_handler.setFormatter(formatter)

    # 2. Console Stream Handler
    console_handler = logging.StreamHandler()
    console_handler.setLevel(level)
    console_handler.setFormatter(formatter)

    # Configure Tradng-Ai logger
    logger = logging.getLogger("tradng_ai")
    logger.setLevel(level)
    logger.propagate = False

    # Avoid duplicate handlers if reloaded
    logger.handlers.clear()
    logger.addHandler(file_handler)
    logger.addHandler(console_handler)

    _INITIALIZED = True
    logger.info(f"Logging initialized at level {logging.getLevelName(level)}. Log file: {log_file}")
    return logger


def get_logger(name="tradng_ai"):
    """Returns a namespaced child logger attached to the Tradng-Ai logging hierarchy."""
    if not _INITIALIZED:
        setup_logging()
    if name == "tradng_ai" or name.startswith("tradng_ai."):
        return logging.getLogger(name)
    return logging.getLogger(f"tradng_ai.{name}")


def read_recent_logs(max_lines=150):
    """
    Reads the last N lines from the active trading log file for live debugging.
    Gracefully handles missing or uncreated log files.
    """
    root = Path(__file__).resolve().parent.parent
    log_file = root / "logs" / "trading.log"

    if not log_file.exists():
        return []

    try:
        with open(log_file, "r", encoding="utf-8", errors="replace") as f:
            lines = f.readlines()
            return [line.rstrip("\r\n") for line in lines[-max_lines:]]
    except Exception as e:
        return [f"Error reading log file: {e!r}"]

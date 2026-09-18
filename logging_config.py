"""Structured local logging. Remote transport belongs to the Alloy process."""

import json
import logging
import sys
from datetime import datetime, timezone
from logging.handlers import RotatingFileHandler
from pathlib import Path

from config import (
    DEVICE_ID, SITE_ID, LOG_FILE, LOG_LEVEL, LOG_MAX_BYTES,
    LOG_BACKUP_COUNT, LOG_TO_CONSOLE,
)


class JsonFormatter(logging.Formatter):
    def __init__(self, device=DEVICE_ID, site=SITE_ID):
        super().__init__()
        self.device = device
        self.site = site

    def format(self, record):
        entry = {
            "timestamp": datetime.fromtimestamp(record.created, timezone.utc).isoformat(),
            "level": record.levelname.lower(),
            "application": "edge-modbus",
            "device": self.device,
            "site": self.site,
            "logger": record.name,
            "message": record.getMessage(),
        }
        # Keep variable values in the JSON body, not in Loki's stream labels.
        for key in ("event", "failure_count", "failure_limit", "record_id",
                    "status_code", "uptime_seconds", "modbus_fatal",
                    "read_age_seconds", "insert_age_seconds", "worker",
                    "pending_count", "oldest_pending_age_seconds", "disk_used_percent"):
            if hasattr(record, key):
                entry[key] = getattr(record, key)
        if record.exc_info:
            entry["exception"] = self.formatException(record.exc_info)
        if record.stack_info:
            entry["stack"] = self.formatStack(record.stack_info)
        return json.dumps(entry, ensure_ascii=False, separators=(",", ":"))


def setup_root_logger(log_file=LOG_FILE, *, level=LOG_LEVEL,
                      max_bytes=LOG_MAX_BYTES, backup_count=LOG_BACKUP_COUNT,
                      console=LOG_TO_CONSOLE, device=DEVICE_ID, site=SITE_ID):
    """Install owned handlers once, retaining handlers installed by a host/test runner."""
    if max_bytes <= 0 or backup_count < 1:
        raise ValueError("Log rotation requires positive max_bytes and backup_count")
    level_number = logging.getLevelName(level.upper()) if isinstance(level, str) else level
    if not isinstance(level_number, int):
        raise ValueError(f"Invalid log level: {level}")
    log_path = Path(log_file)
    log_path.parent.mkdir(parents=True, exist_ok=True)
    formatter = JsonFormatter(device, site)
    handler = RotatingFileHandler(
        log_path, maxBytes=max_bytes, backupCount=backup_count, encoding="utf-8",
    )
    handlers = [handler]
    if console:
        handlers.append(logging.StreamHandler(sys.stdout))
    root = logging.getLogger()
    for existing in list(root.handlers):
        if getattr(existing, "_edge_owned", False):
            root.removeHandler(existing)
            existing.close()
    for new_handler in handlers:
        new_handler._edge_owned = True
        new_handler.setFormatter(formatter)
        root.addHandler(new_handler)
    root.setLevel(level_number)
    # Heartbeats remain available even when application verbosity is WARNING.
    logging.getLogger("edge.heartbeat").setLevel(logging.INFO)
    return root

"""Structured JSON logging."""
from __future__ import annotations

import json
import logging
import sys
from datetime import datetime


class JSONFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        # Import inside so a broken redactor never breaks logging itself.
        from kira.redaction import redact

        log_entry = {
            "timestamp": datetime.utcnow().isoformat(),
            "level": record.levelname,
            "module": record.module,
            "message": redact(record.getMessage()),
        }
        if hasattr(record, "extra_data"):
            log_entry.update(record.extra_data)  # type: ignore[attr-defined]
        if record.exc_info and record.exc_info[0]:
            log_entry["exception"] = redact(self.formatException(record.exc_info))
        return json.dumps(log_entry)


def get_logger(name: str) -> logging.Logger:
    logger = logging.getLogger(f"kira.{name}")
    if not logger.handlers:
        handler = logging.StreamHandler(sys.stdout)
        handler.setFormatter(JSONFormatter())
        logger.addHandler(handler)
        logger.setLevel(logging.INFO)
        logger.propagate = False
    return logger

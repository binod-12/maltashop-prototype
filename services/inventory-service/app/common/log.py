"""Structured JSON logger.

Every line carries the mandatory schema from report section 4.2:
timestamp, level, service, correlationId, event, message (+ optional extra fields).
"""
import json
import os
import sys
from datetime import UTC, datetime


def _now() -> str:
    return datetime.now(UTC).isoformat(timespec="milliseconds").replace("+00:00", "Z")


def log(level: str, event: str, message: str, correlation_id=None, **extra) -> None:
    line = {
        "timestamp": _now(),
        "level": level,
        "service": os.environ.get("SERVICE_NAME", "unknown-service"),
        "correlationId": correlation_id,
        "event": event,
        "message": message,
        **extra,
    }
    # stdout only (12-factor XI: logs are an event stream)
    sys.stdout.write(json.dumps(line, ensure_ascii=False) + "\n")
    sys.stdout.flush()


def info(event, message, correlation_id=None, **extra):
    log("info", event, message, correlation_id, **extra)


def warn(event, message, correlation_id=None, **extra):
    log("warn", event, message, correlation_id, **extra)


def error(event, message, correlation_id=None, **extra):
    log("error", event, message, correlation_id, **extra)

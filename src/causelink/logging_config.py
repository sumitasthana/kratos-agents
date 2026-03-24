"""
causelink/logging_config.py

Structured logging configuration for the CauseLink RCA engine.

Provides:
  - JSON-formatted logs (production / log aggregation)
  - Text-formatted logs (local development)
  - Correlation filter that injects investigation_id into every log record
  - get_logger() — convenience factory that binds investigation_id

Usage:
    # At application startup (call once):
    from causelink.logging_config import configure_logging
    configure_logging()

    # In agent code (per-investigation context):
    from causelink.logging_config import get_logger
    logger = get_logger("causelink.agents.ranker", investigation_id="INV-001")
    logger.info("Scoring candidates", extra={"candidate_count": 5})
"""

from __future__ import annotations

import json
import logging
import logging.config
import os
import sys
from datetime import datetime, timezone
from typing import Any, Dict, Optional

# ---------------------------------------------------------------------------
# JSON formatter
# ---------------------------------------------------------------------------

class _JsonFormatter(logging.Formatter):
    """
    Emit each log record as a single-line JSON object.

    Standard fields emitted:
      timestamp, level, logger, message, investigation_id (when bound)
    Extra fields from LogRecord.args / record.__dict__ are included only
    when they are JSON-serialisable and do not shadow standard fields.

    Sensitive keys are redacted before serialisation.
    """

    _REDACTED_KEYS = frozenset({
        "password", "token", "secret", "credential", "api_key",
        "private_key", "auth", "authorization",
    })
    _STANDARD_KEYS = frozenset({
        "name", "msg", "args", "created", "filename", "funcName",
        "levelname", "levelno", "lineno", "module", "msecs", "pathname",
        "process", "processName", "relativeCreated", "stack_info",
        "taskName", "thread", "threadName", "exc_info", "exc_text",
        "message",
    })

    def format(self, record: logging.LogRecord) -> str:  # type: ignore[override]
        record.message = record.getMessage()

        payload: Dict[str, Any] = {
            "timestamp": datetime.fromtimestamp(record.created, tz=timezone.utc).isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "message": record.message,
        }

        # Inject investigation_id when bound by CorrelationFilter
        inv_id = getattr(record, "investigation_id", None)
        if inv_id:
            payload["investigation_id"] = inv_id

        # Include safe extra fields
        for key, val in vars(record).items():
            if key in self._STANDARD_KEYS or key.startswith("_"):
                continue
            low = key.lower()
            if any(s in low for s in self._REDACTED_KEYS):
                payload[key] = "<redacted>"
                continue
            try:
                json.dumps(val)  # check serialisability
                payload[key] = val
            except (TypeError, ValueError):
                payload[key] = repr(val)

        if record.exc_info:
            payload["exc_info"] = self.formatException(record.exc_info)

        return json.dumps(payload, ensure_ascii=True)


# ---------------------------------------------------------------------------
# Text formatter (development)
# ---------------------------------------------------------------------------

class _TextFormatter(logging.Formatter):
    _FMT = "%(asctime)s [%(levelname)-8s] %(name)s %(message)s"
    _DATE = "%Y-%m-%dT%H:%M:%S"

    def __init__(self) -> None:
        super().__init__(self._FMT, datefmt=self._DATE)

    def format(self, record: logging.LogRecord) -> str:  # type: ignore[override]
        inv_id = getattr(record, "investigation_id", None)
        if inv_id:
            record.message = record.getMessage()
            record.msg = f"[{inv_id}] {record.msg}"
        return super().format(record)


# ---------------------------------------------------------------------------
# Correlation filter
# ---------------------------------------------------------------------------

class CorrelationFilter(logging.Filter):
    """
    Inject a bound investigation_id into every LogRecord emitted on this logger.

    Create a logger via get_logger() to get a logger pre-bound to an ID.
    """

    def __init__(self, investigation_id: Optional[str] = None) -> None:
        super().__init__()
        self.investigation_id = investigation_id

    def filter(self, record: logging.LogRecord) -> bool:  # type: ignore[override]
        if self.investigation_id and not getattr(record, "investigation_id", None):
            record.investigation_id = self.investigation_id
        return True


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def configure_logging(
    level: Optional[str] = None,
    fmt: Optional[str] = None,
) -> None:
    """
    Configure root logger for CauseLink.

    Call once at application startup (before any log messages are emitted).

    Args:
        level: Override CAUSELINK_LOG_LEVEL env var (DEBUG/INFO/WARNING/ERROR).
        fmt:   Override CAUSELINK_LOG_FORMAT env var ('json' or 'text').
    """
    _level = (level or os.environ.get("CAUSELINK_LOG_LEVEL", "INFO")).upper()
    _fmt = (fmt or os.environ.get("CAUSELINK_LOG_FORMAT", "json")).lower()

    formatter: logging.Formatter
    if _fmt == "json":
        formatter = _JsonFormatter()
    else:
        formatter = _TextFormatter()

    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(formatter)

    # Configure causelink and root loggers
    for name in ("causelink", "uvicorn.access", "uvicorn.error", "fastapi"):
        lg = logging.getLogger(name)
        lg.setLevel(_level)
        # Remove existing handlers to avoid duplicate output
        lg.handlers = [handler]
        lg.propagate = False

    root = logging.getLogger()
    root.setLevel(_level)
    if not root.handlers:
        root.addHandler(handler)


def get_logger(
    name: str,
    investigation_id: Optional[str] = None,
) -> logging.Logger:
    """
    Return a logger bound to the given investigation_id.

    Every log record emitted through this logger will include the
    investigation_id field (JSON) or prefix (text), enabling log-line
    correlation across agents in a single investigation.

    Args:
        name:             Logger name, typically __name__ of calling module.
        investigation_id: ID to inject into every record from this logger.

    Returns:
        A standard logging.Logger with a CorrelationFilter attached.
    """
    lg = logging.getLogger(name)
    if investigation_id:
        # Remove any existing CorrelationFilter, then add the new one
        lg.filters = [f for f in lg.filters if not isinstance(f, CorrelationFilter)]
        lg.addFilter(CorrelationFilter(investigation_id=investigation_id))
    return lg

"""
src/observability/logger.py

Structured JSON logger with automatic OTel trace/span correlation.

Every log line is a single-line JSON object containing:
  timestamp · level · logger · message · trace_id · span_id
  plus any extra kwargs passed to the log call.

An in-memory ring buffer (``_LOG_BUFFER``, max 1,000 lines) is kept so
the obs_api can tail recent logs over SSE without needing a file.

Usage::

    from src.observability.logger import get_logger, LogEvent

    log = get_logger(__name__)

    log.info(LogEvent.PHASE_COMPLETE, phase="BACKTRACK", hops=6,
             duration_ms=412, investigation_id=state.investigation_id,
             scenario_id=state.scenario_id)

    log.warning(LogEvent.VALIDATION_GATE_FAIL, gate="R4",
                reason="missing CRITICAL evidence",
                investigation_id=inv_id)

    log.error(LogEvent.PHASE_FAILED, agent="CausalEngineAgent",
              error=str(e), investigation_id=inv_id)
"""

from __future__ import annotations

import json
import logging
import sys
from collections import deque
from datetime import datetime, timezone
from typing import Deque, Dict, Any

from opentelemetry import trace as otel_trace

# ---------------------------------------------------------------------------
# In-memory log ring buffer — max 1,000 lines; consumed by /obs/logs/stream
# ---------------------------------------------------------------------------
_LOG_BUFFER: Deque[Dict[str, Any]] = deque(maxlen=1000)

# Fields that are part of every LogRecord but are not useful in JSON output
_SKIP_FIELDS = frozenset({
    "name", "msg", "args", "levelname", "levelno", "pathname", "filename",
    "module", "exc_info", "exc_text", "stack_info", "lineno", "funcName",
    "created", "msecs", "relativeCreated", "thread", "threadName",
    "processName", "process", "message", "taskName",
})


class KratosJsonFormatter(logging.Formatter):
    """Formats every record as a single-line JSON object.

    Injects OTel trace_id and span_id automatically from the active span.
    Any extra keyword arguments passed to the log call are merged in.
    """

    def format(self, record: logging.LogRecord) -> str:
        current_span = otel_trace.get_current_span()
        ctx = current_span.get_span_context()

        payload: Dict[str, Any] = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "level":     record.levelname,
            "logger":    record.name,
            "message":   record.getMessage(),
            "trace_id":  format(ctx.trace_id, "032x") if ctx.is_valid else None,
            "span_id":   format(ctx.span_id, "016x")  if ctx.is_valid else None,
        }

        # Merge extra fields passed as kwargs to log.info(msg, extra={...})
        for key, value in record.__dict__.items():
            if key not in _SKIP_FIELDS:
                payload[key] = value

        if record.exc_info:
            payload["exception"] = self.formatException(record.exc_info)

        _LOG_BUFFER.append(payload)
        return json.dumps(payload, default=str)


def get_logger(name: str) -> logging.Logger:
    """Return a structured JSON logger for ``name``.

    Idempotent — safe to call multiple times with the same name.
    """
    logger = logging.getLogger(name)
    if not logger.handlers:
        handler = logging.StreamHandler(sys.stdout)
        handler.setFormatter(KratosJsonFormatter())
        logger.addHandler(handler)
        logger.setLevel(logging.DEBUG)
        logger.propagate = False
    return logger


# ---------------------------------------------------------------------------
# Standard log event name constants — always use these, never raw strings
# ---------------------------------------------------------------------------

class LogEvent:
    INVESTIGATION_STARTED   = "investigation_started"
    INVESTIGATION_COMPLETE  = "investigation_complete"
    PHASE_STARTED           = "phase_started"
    PHASE_COMPLETE          = "phase_complete"
    PHASE_FAILED            = "phase_failed"
    AGENT_INVOKED           = "agent_invoked"
    AGENT_COMPLETE          = "agent_complete"
    EVIDENCE_ACCEPTED       = "evidence_accepted"
    EVIDENCE_REJECTED       = "evidence_rejected"
    HYPOTHESIS_CREATED      = "hypothesis_created"
    HYPOTHESIS_PROMOTED     = "hypothesis_promoted"
    HYPOTHESIS_REJECTED     = "hypothesis_rejected"
    HOP_REVEALED            = "backtrack_hop_revealed"
    ROOT_CAUSE_CONFIRMED    = "root_cause_confirmed"
    VALIDATION_GATE_PASS    = "validation_gate_pass"
    VALIDATION_GATE_FAIL    = "validation_gate_fail"
    CONFIDENCE_COMPUTED     = "confidence_computed"
    SSE_EVENT_EMITTED       = "sse_event_emitted"
    SSE_CLIENT_CONNECTED    = "sse_client_connected"
    SSE_CLIENT_DISCONNECTED = "sse_client_disconnected"
    CONTROL_SCAN_COMPLETE   = "control_scan_complete"
    BOOT_STAGE_COMPLETE     = "boot_stage_complete"
    QUEUE_DEPTH_HIGH        = "queue_depth_high"

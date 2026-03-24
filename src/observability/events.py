"""
src/observability/events.py

Named RCA events — structured business events distinct from logs.
Map 1:1 to RCA milestones and are stored in a capped ring buffer
(last 500 events). Exposed via GET /obs/events.

Usage::

    from src.observability.events import emit, EventName

    emit(EventName.ROOT_CAUSE_CONFIRMED,
         investigation_id=inv_id,
         scenario_id=scenario_id,
         root_cause_node_id="node-daf-art-jcl",
         defect_id="DEF-LDS-001",
         confidence=0.87)

    emit(EventName.VALIDATION_GATE_FAILED,
         investigation_id=inv_id,
         gate_rule="R4",
         reason="no CRITICAL evidence attached to root cause node")
"""

from __future__ import annotations

import threading
from collections import deque
from datetime import datetime, timezone
from typing import Any, Deque, Dict, List, Optional

from opentelemetry import trace as otel_trace

# ---------------------------------------------------------------------------
# Ring buffer — max 500 named events
# ---------------------------------------------------------------------------
_BUFFER: Deque[Dict[str, Any]] = deque(maxlen=500)
_LOCK = threading.Lock()


# ---------------------------------------------------------------------------
# Named event type registry — the complete list for this platform
# ---------------------------------------------------------------------------

class EventName:
    # Investigation lifecycle
    INVESTIGATION_STARTED       = "investigation_started"
    INVESTIGATION_CONFIRMED     = "investigation_confirmed"
    INVESTIGATION_INCONCLUSIVE  = "investigation_inconclusive"
    INVESTIGATION_ESCALATED     = "investigation_escalated"
    INVESTIGATION_ERROR         = "investigation_error"

    # RCA milestones
    ROOT_CAUSE_CONFIRMED        = "root_cause_confirmed"
    ROOT_CAUSE_BLOCKED          = "root_cause_blocked"
    HYPOTHESIS_PATTERN_MATCHED  = "hypothesis_pattern_matched"
    BACKTRACK_EARLY_STOP        = "backtrack_early_stop"
    BACKTRACK_MAX_HOPS_REACHED  = "backtrack_max_hops_reached"

    # Validation
    VALIDATION_ALL_PASS         = "validation_all_pass"
    VALIDATION_GATE_FAILED      = "validation_gate_failed"

    # Confidence
    CONFIDENCE_CONFIRMED        = "confidence_above_threshold"
    CONFIDENCE_INCONCLUSIVE     = "confidence_below_threshold"

    # Control scanning
    CONTROL_FAIL_DETECTED       = "control_fail_detected"
    CONTROL_SCAN_COMPLETE       = "control_scan_complete"

    # Operational
    BOOT_COMPLETE               = "platform_boot_complete"
    BOOT_FAILED                 = "platform_boot_failed"
    SSE_CLIENT_CONNECTED        = "sse_client_connected"
    SSE_CLIENT_DISCONNECTED     = "sse_client_disconnected"
    QUEUE_DEPTH_EXCEEDED        = "queue_depth_exceeded"


def emit(event_name: str, **kwargs: Any) -> None:
    """Append a named event to the ring buffer.

    Always captures the current OTel trace_id so events can be correlated
    back to the active investigation span.
    """
    span = otel_trace.get_current_span()
    ctx = span.get_span_context()
    event: Dict[str, Any] = {
        "event":     event_name,
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "trace_id":  format(ctx.trace_id, "032x") if ctx.is_valid else None,
        **kwargs,
    }
    with _LOCK:
        _BUFFER.append(event)


def get_events(
    limit: int = 100,
    event_type: Optional[str] = None,
) -> List[Dict[str, Any]]:
    """Return up to ``limit`` events, optionally filtered by ``event_type``."""
    with _LOCK:
        events = list(_BUFFER)
    if event_type:
        events = [e for e in events if e.get("event") == event_type]
    return events[-limit:]


def get_events_for_investigation(investigation_id: str) -> List[Dict[str, Any]]:
    """Return all events tagged with a specific investigation_id."""
    with _LOCK:
        return [e for e in _BUFFER if e.get("investigation_id") == investigation_id]

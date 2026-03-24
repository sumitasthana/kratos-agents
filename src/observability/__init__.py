"""
src/observability/__init__.py

Kratos Observability Layer — OpenTelemetry + Prometheus + structured logs.
Import from submodules; this init re-exports the most common entry points
for convenience.
"""

from .tracer import get_tracer, traced, SpanAttr, init_tracer
from .metrics import M, REGISTRY
from .logger import get_logger, LogEvent
from .events import emit, EventName, get_events, get_events_for_investigation

__all__ = [
    "get_tracer",
    "traced",
    "SpanAttr",
    "init_tracer",
    "M",
    "REGISTRY",
    "get_logger",
    "LogEvent",
    "emit",
    "EventName",
    "get_events",
    "get_events_for_investigation",
]

"""
src/observability/tracer.py

OpenTelemetry tracer factory and span decorators.

Every RCA phase, every agent call, and every ValidationGate check gets a span.
Spans nest: Investigation > Phase > Agent.

Usage::

    from src.observability.tracer import traced, get_tracer, SpanAttr

    @traced("EvidenceCollectorAgent.run")
    async def run(self, state: InvestigationState) -> InvestigationState:
        ...

    # Manual span with custom attributes:
    with get_tracer().start_as_current_span("backtrack.hop") as span:
        span.set_attribute(SpanAttr.HOP_INDEX, i)
        span.set_attribute(SpanAttr.HOP_REL_TYPE, rel_type)
        span.set_attribute(SpanAttr.HOP_STATUS, status)
"""

from __future__ import annotations

import os
from functools import wraps
from typing import Any, Optional

from opentelemetry import trace
from opentelemetry.sdk.resources import Resource
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor, ConsoleSpanExporter
from opentelemetry.sdk.trace.export import SimpleSpanProcessor

try:
    from opentelemetry.exporter.otlp.proto.grpc.trace_exporter import OTLPSpanExporter
    _HAS_OTLP = True
except ImportError:
    _HAS_OTLP = False

RESOURCE = Resource.create({
    "service.name": "kratos-causelink",
    "service.version": "1.0.0",
    "deployment.environment": os.getenv("KRATOS_ENV", "demo"),
})

_provider: Optional[TracerProvider] = None


def init_tracer() -> TracerProvider:
    """Initialise the global TracerProvider.

    If an OTLP endpoint is configured (OTLP_ENDPOINT env var), spans are
    exported via gRPC.  Otherwise a no-op ConsoleSpanExporter is used so the
    app starts without an external collector.
    """
    global _provider
    provider = TracerProvider(resource=RESOURCE)

    otlp_endpoint = os.getenv("OTLP_ENDPOINT", "")
    if otlp_endpoint and _HAS_OTLP:
        exporter = OTLPSpanExporter(endpoint=otlp_endpoint, insecure=True)
        provider.add_span_processor(BatchSpanProcessor(exporter))
    else:
        # Fall back to a silent no-op so the app runs without a collector.
        # Switch to ConsoleSpanExporter for local debugging if needed.
        if os.getenv("OTEL_CONSOLE_EXPORT", "").lower() in ("1", "true"):
            provider.add_span_processor(SimpleSpanProcessor(ConsoleSpanExporter()))

    trace.set_tracer_provider(provider)
    _provider = provider
    return provider


def get_tracer() -> trace.Tracer:
    """Return the module tracer, initialising lazily if needed."""
    if _provider is None:
        init_tracer()
    return trace.get_tracer("kratos.causelink")


def _extract_state(args: tuple) -> Any:
    """Try to pull an InvestigationState out of the first positional arg."""
    try:
        from causelink.state.investigation import InvestigationState  # noqa: PLC0415
        for arg in args:
            if isinstance(arg, InvestigationState):
                return arg
    except ImportError:
        pass
    return None


def traced(span_name: str, record_exception: bool = True):
    """Decorator — wraps async or sync functions in an OTel span.

    Auto-sets these attributes when the first argument is InvestigationState:
      investigation.id · investigation.scenario · investigation.phase

    On exception: records the exception and sets span status to ERROR.
    """
    def decorator(func):
        if not callable(func):
            raise TypeError(f"@traced target must be callable, got {type(func)}")

        @wraps(func)
        async def async_wrapper(*args, **kwargs):
            with get_tracer().start_as_current_span(span_name) as span:
                state = _extract_state(args)
                if state is not None:
                    span.set_attribute(SpanAttr.INVESTIGATION_ID,
                                       str(getattr(state, "investigation_id", "")))
                    span.set_attribute(SpanAttr.SCENARIO_ID,
                                       str(getattr(state, "scenario_id", "")))
                    span.set_attribute(SpanAttr.PHASE,
                                       str(getattr(state, "current_phase", "")))
                span.set_attribute("function.name", func.__qualname__)
                try:
                    return await func(*args, **kwargs)
                except Exception as exc:
                    if record_exception:
                        span.record_exception(exc)
                        span.set_status(trace.StatusCode.ERROR, str(exc))
                    raise

        @wraps(func)
        def sync_wrapper(*args, **kwargs):
            with get_tracer().start_as_current_span(span_name) as span:
                state = _extract_state(args)
                if state is not None:
                    span.set_attribute(SpanAttr.INVESTIGATION_ID,
                                       str(getattr(state, "investigation_id", "")))
                    span.set_attribute(SpanAttr.SCENARIO_ID,
                                       str(getattr(state, "scenario_id", "")))
                    span.set_attribute(SpanAttr.PHASE,
                                       str(getattr(state, "current_phase", "")))
                span.set_attribute("function.name", func.__qualname__)
                try:
                    return func(*args, **kwargs)
                except Exception as exc:
                    if record_exception:
                        span.record_exception(exc)
                        span.set_status(trace.StatusCode.ERROR, str(exc))
                    raise

        import asyncio
        if asyncio.iscoroutinefunction(func):
            return async_wrapper
        return sync_wrapper

    return decorator


# ---------------------------------------------------------------------------
# Span attribute constants — always use these, never raw strings
# ---------------------------------------------------------------------------

class SpanAttr:
    INVESTIGATION_ID  = "investigation.id"
    SCENARIO_ID       = "investigation.scenario"
    JOB_ID            = "investigation.job_id"
    PHASE             = "investigation.phase"
    AGENT             = "agent.name"
    EVIDENCE_COUNT    = "evidence.count"
    HOP_INDEX         = "backtrack.hop_index"
    HOP_REL_TYPE      = "backtrack.rel_type"
    HOP_STATUS        = "backtrack.hop_status"
    CONFIDENCE        = "rca.confidence"
    ROOT_CAUSE_ID     = "rca.root_cause_node_id"
    VALIDATION_GATE   = "validation.gate_id"
    VALIDATION_RESULT = "validation.result"
    PATTERN_ID        = "hypothesis.pattern_id"
    CONTROL_ID        = "control.id"
    CONTROL_STATUS    = "control.status"
    DEFECT_ID         = "defect.id"
    PHASE_DURATION_MS = "phase.duration_ms"

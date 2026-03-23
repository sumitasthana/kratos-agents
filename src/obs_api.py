"""
src/obs_api.py

Kratos Observability API — FastAPI port 8003.

Endpoints:
  GET  /obs/metrics              Prometheus scrape endpoint
  GET  /obs/metrics/live         JSON snapshot for dashboard polling (2s)
  GET  /obs/events               Named RCA event feed
  GET  /obs/events/investigation/{id}  Events for one investigation
  GET  /obs/logs/stream          SSE tail of structured log buffer
  GET  /obs/health               Deep health check (all APIs + metrics)
  GET  /obs/alerts/active        Alert evaluation against live metrics
  GET  /obs/traces/{id}          In-memory span list for one investigation
"""

from __future__ import annotations

import asyncio
import json
import os
import time
from collections import defaultdict
from typing import Any, Dict, List, Optional

from fastapi import FastAPI, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import Response, StreamingResponse
from prometheus_client import generate_latest, CONTENT_TYPE_LATEST

from src.observability.events import get_events, get_events_for_investigation
from src.observability.exporters import setup_exporters
from src.observability.health import deep_health_check
from src.observability.logger import _LOG_BUFFER, get_logger
from src.observability.metrics import M, REGISTRY

log = get_logger(__name__)

# ---------------------------------------------------------------------------
# App setup
# ---------------------------------------------------------------------------

app = FastAPI(
    title="Kratos Observability API",
    version="1.0.0",
    description="Prometheus metrics, OTel traces, structured logs, and named events.",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["GET"],
    allow_headers=["*"],
)


@app.on_event("startup")
async def _startup() -> None:
    setup_exporters()
    log.info("obs_api: started on port %s",
             os.getenv("OBS_API_PORT", "8003"))


# ---------------------------------------------------------------------------
# Prometheus scrape endpoint
# ---------------------------------------------------------------------------

@app.get("/obs/metrics", include_in_schema=False)
async def prometheus_metrics() -> Response:
    """Standard Prometheus /metrics scrape endpoint."""
    data = generate_latest(REGISTRY)
    return Response(content=data, media_type=CONTENT_TYPE_LATEST)


# ---------------------------------------------------------------------------
# Metric helper functions
# ---------------------------------------------------------------------------

def _get_counter_total(metric_name: str, **label_filters: str) -> float:
    """Sum all counter samples matching optional label filters."""
    try:
        collector = REGISTRY._names_to_collectors.get(metric_name)
        if collector is None:
            return 0.0
        total = 0.0
        for metric in collector.collect():
            for sample in metric.samples:
                if sample.name.endswith("_total"):
                    if all(sample.labels.get(k) == v for k, v in label_filters.items()):
                        total += sample.value
        return total
    except Exception:
        return 0.0


def _get_gauge(metric_name: str) -> float:
    try:
        collector = REGISTRY._names_to_collectors.get(metric_name)
        if collector is None:
            return 0.0
        for metric in collector.collect():
            for sample in metric.samples:
                return sample.value
        return 0.0
    except Exception:
        return 0.0


def _get_histogram_quantile(metric_name: str, quantile: float) -> float:
    """Approximate a quantile from histogram bucket data."""
    try:
        collector = REGISTRY._names_to_collectors.get(metric_name)
        if collector is None:
            return 0.0
        # Collect all bucket samples
        buckets: List[tuple] = []
        total_count = 0.0
        total_sum = 0.0
        for metric in collector.collect():
            for sample in metric.samples:
                if sample.name.endswith("_bucket") and sample.labels.get("le") not in ("+Inf",):
                    try:
                        buckets.append((float(sample.labels["le"]), sample.value))
                    except (KeyError, ValueError):
                        pass
                elif sample.name.endswith("_count"):
                    total_count += sample.value
                elif sample.name.endswith("_sum"):
                    total_sum += sample.value
        if total_count == 0:
            return 0.0
        target = quantile * total_count
        buckets.sort(key=lambda x: x[0])
        prev_count = 0.0
        for upper, count in buckets:
            if count >= target:
                return upper
            prev_count = count
        # Fell through — return mean as fallback
        return total_sum / total_count if total_count > 0 else 0.0
    except Exception:
        return 0.0


def _get_histogram_mean(metric_name: str) -> float:
    try:
        collector = REGISTRY._names_to_collectors.get(metric_name)
        if collector is None:
            return 0.0
        total_sum = 0.0
        total_count = 0.0
        for metric in collector.collect():
            for sample in metric.samples:
                if sample.name.endswith("_sum"):
                    total_sum += sample.value
                elif sample.name.endswith("_count"):
                    total_count += sample.value
        if total_count == 0:
            return 0.0
        return total_sum / total_count
    except Exception:
        return 0.0


def _compute_signal_ratio() -> float:
    collected = _get_counter_total("kratos_evidence_collected_total")
    rejected = _get_counter_total("kratos_evidence_rejected_total")
    total = collected + rejected
    return round(collected / total, 4) if total > 0 else 1.0


def _compute_gate_fail_rate() -> float:
    passes = _get_counter_total("kratos_validation_gate_results_total", result="PASS")
    fails  = _get_counter_total("kratos_validation_gate_results_total", result="FAIL")
    total  = passes + fails
    return round(fails / total, 4) if total > 0 else 0.0


# ---------------------------------------------------------------------------
# Live metrics snapshot (polled by React dashboard every 2s)
# ---------------------------------------------------------------------------

@app.get("/obs/metrics/live")
async def live_metrics() -> Dict[str, Any]:
    """JSON snapshot of key metrics for dashboard polling."""
    return {
        "timestamp": time.time(),
        "investigations": {
            "started_total":      _get_counter_total("kratos_investigations_started_total"),
            "confirmed_total":    _get_counter_total("kratos_investigations_completed_total", status="CONFIRMED"),
            "inconclusive_total": _get_counter_total("kratos_investigations_completed_total", status="INCONCLUSIVE"),
            "error_total":        _get_counter_total("kratos_investigations_completed_total", status="ERROR"),
            "in_flight":          _get_gauge("kratos_investigations_in_flight"),
        },
        "performance": {
            "phase_p50_ms": _get_histogram_quantile("kratos_phase_duration_ms", 0.50),
            "phase_p95_ms": _get_histogram_quantile("kratos_phase_duration_ms", 0.95),
            "phase_p99_ms": _get_histogram_quantile("kratos_phase_duration_ms", 0.99),
            "agent_p95_ms": _get_histogram_quantile("kratos_agent_duration_ms", 0.95),
        },
        "evidence": {
            "collected_total": _get_counter_total("kratos_evidence_collected_total"),
            "rejected_total":  _get_counter_total("kratos_evidence_rejected_total"),
            "signal_ratio":    _compute_signal_ratio(),
        },
        "backtracking": {
            "avg_hops":        _get_histogram_mean("kratos_backtrack_hops"),
            "early_stops":     _get_counter_total("kratos_backtrack_early_stops_total"),
            "max_hops_reached": _get_counter_total("kratos_backtrack_max_hops_reached_total"),
        },
        "validation": {
            "gate_pass_total": _get_counter_total("kratos_validation_gate_results_total", result="PASS"),
            "gate_fail_total": _get_counter_total("kratos_validation_gate_results_total", result="FAIL"),
            "gate_fail_rate":  _compute_gate_fail_rate(),
        },
        "confidence": {
            "avg":             _get_histogram_mean("kratos_confidence_distribution"),
            "below_threshold": _get_counter_total("kratos_confidence_below_threshold_total"),
        },
        "sse": {
            "active_connections":  _get_gauge("kratos_sse_connections_active"),
            "events_emitted_total": _get_counter_total("kratos_sse_events_emitted_total"),
        },
        "data": {
            "csv_records":    _get_gauge("kratos_csv_records_loaded"),
            "smdia_exposures": _get_gauge("kratos_smdia_exposure_count"),
        },
    }


# ---------------------------------------------------------------------------
# Named events feed
# ---------------------------------------------------------------------------

@app.get("/obs/events")
async def events_feed(
    limit: int = Query(50, le=500),
    event_type: Optional[str] = Query(None),
) -> Dict[str, Any]:
    items = get_events(limit=limit, event_type=event_type)
    return {"items": items, "total": len(items)}


@app.get("/obs/events/investigation/{investigation_id}")
async def events_for_investigation(investigation_id: str) -> Dict[str, Any]:
    items = get_events_for_investigation(investigation_id)
    return {"items": items, "total": len(items)}


# ---------------------------------------------------------------------------
# Log tail SSE
# ---------------------------------------------------------------------------

@app.get("/obs/logs/stream")
async def log_stream(
    investigation_id: Optional[str] = Query(None),
    level: Optional[str] = Query(None),
) -> StreamingResponse:
    """SSE stream of structured log lines from the in-memory ring buffer."""

    async def generator():
        last_idx = len(_LOG_BUFFER)
        while True:
            await asyncio.sleep(0.5)
            current = list(_LOG_BUFFER)
            new_lines = current[last_idx:]
            for line in new_lines:
                if investigation_id and line.get("investigation_id") != investigation_id:
                    continue
                if level and line.get("level", "").upper() != level.upper():
                    continue
                yield f"data: {json.dumps(line, default=str)}\n\n"
            last_idx = len(_LOG_BUFFER)

    return StreamingResponse(
        generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control":     "no-cache",
            "X-Accel-Buffering": "no",
        },
    )


# ---------------------------------------------------------------------------
# In-memory span store (populated by the custom span exporter below)
# ---------------------------------------------------------------------------

# investigation_id → list of span dicts
_SPAN_STORE: Dict[str, List[Dict[str, Any]]] = defaultdict(list)


def record_span(span_dict: Dict[str, Any]) -> None:
    """Called by InMemorySpanExporter to index spans by investigation_id."""
    inv_id = span_dict.get("attributes", {}).get("investigation.id")
    if inv_id:
        _SPAN_STORE[inv_id].append(span_dict)


@app.get("/obs/traces/{investigation_id}")
async def traces_for_investigation(investigation_id: str) -> Dict[str, Any]:
    """Return spans recorded for a specific investigation."""
    spans = _SPAN_STORE.get(investigation_id, [])
    return {"items": spans, "total": len(spans)}


# ---------------------------------------------------------------------------
# Deep health check
# ---------------------------------------------------------------------------

@app.get("/obs/health")
async def obs_health() -> Dict[str, Any]:
    return await deep_health_check()


# ---------------------------------------------------------------------------
# Active alerts
# ---------------------------------------------------------------------------

_ALERT_RULES = [
    {
        "name": "High investigation error rate",
        "severity": "CRITICAL",
        "message": "More than 10% of investigations ending in ERROR",
        "condition": lambda m: (
            m["investigations"]["error_total"]
            / max(m["investigations"]["started_total"], 1)
        ) > 0.10,
    },
    {
        "name": "Phase P95 latency high",
        "severity": "HIGH",
        "message": "Phase P95 latency > 5 seconds",
        "condition": lambda m: m["performance"]["phase_p95_ms"] > 5000,
    },
    {
        "name": "ValidationGate failure rate high",
        "severity": "HIGH",
        "message": "ValidationGate failure rate > 5%",
        "condition": lambda m: m["validation"]["gate_fail_rate"] > 0.05,
    },
    {
        "name": "Confidence below threshold",
        "severity": "WARN",
        "message": "One or more investigations returned INCONCLUSIVE (confidence < 0.70)",
        "condition": lambda m: m["confidence"]["below_threshold"] > 0,
    },
    {
        "name": "SSE connection spike",
        "severity": "WARN",
        "message": "More than 10 active SSE connections",
        "condition": lambda m: m["sse"]["active_connections"] > 10,
    },
]


@app.get("/obs/alerts/active")
async def active_alerts() -> Dict[str, Any]:
    """Evaluate threshold rules against current metrics. Returns active alerts."""
    m = await live_metrics()
    alerts = []
    for rule in _ALERT_RULES:
        try:
            if rule["condition"](m):
                alerts.append({
                    "name":      rule["name"],
                    "severity":  rule["severity"],
                    "message":   rule["message"],
                    "timestamp": time.time(),
                })
        except Exception:
            pass
    return {"alerts": alerts, "total": len(alerts), "timestamp": time.time()}

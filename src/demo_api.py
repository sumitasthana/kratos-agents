"""
src/demo_api.py

Demo API — FastAPI application, port 8002.

Endpoints:
  GET  /demo/scenarios
  GET  /demo/scenarios/{scenario_id}
  GET  /demo/controls/{scenario_id}
  POST /demo/investigations
  GET  /demo/investigations/{investigation_id}
  GET  /demo/investigations/{investigation_id}/trace
  GET  /demo/investigations/{investigation_id}/graph
  GET  /demo/stream/{investigation_id}

All list endpoints return {"items": [...], "total": N}.
All error responses follow {"error": "CODE", "message": "...", "detail": {...}}.

Run with:
  uvicorn src.demo_api:app --port 8002 --reload
Or via environment variable:
  DEMO_API_PORT=8002 uvicorn src.demo_api:app --port $DEMO_API_PORT
"""

from __future__ import annotations

import logging
import os
from typing import Any, AsyncIterator, Dict

from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, StreamingResponse

from demo.scenario_registry import ScenarioRegistry
from demo.services.control_scanner import ControlScanner
from demo.services.demo_rca_service import DemoRcaService

# Observability — soft dependency; service still boots without it.
try:
    from src.observability.metrics import M as _M
    from src.observability.logger import get_logger as _get_logger, LogEvent
    from src.observability.events import emit as _emit, EventName
    _OBS_AVAILABLE = True
except ImportError:  # pragma: no cover
    _OBS_AVAILABLE = False

if _OBS_AVAILABLE:
    logger = _get_logger(__name__)
else:
    logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Application setup
# ---------------------------------------------------------------------------

app = FastAPI(
    title="Kratos Demo API",
    description=(
        "FDIC Part 370/330 compliance RCA — in-memory demo scenarios. "
        "All data is synthetic. Not for production regulatory use."
    ),
    version="1.0.0",
    docs_url="/demo/docs",
    openapi_url="/demo/openapi.json",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["GET", "POST"],
    allow_headers=["*"],
)

# ---------------------------------------------------------------------------
# Startup singletons
# ---------------------------------------------------------------------------

_registry: ScenarioRegistry | None = None
_scanner: ControlScanner | None = None
_service: DemoRcaService | None = None


@app.on_event("startup")
async def _startup() -> None:
    global _registry, _scanner, _service
    # Auto-register the KratosDemoAdapter so /demo/adapters works immediately.
    try:
        import src.infrastructure.adapters.kratos_demo_adapter  # noqa: F401,PLC0415
    except Exception as _e:
        logger.warning("KratosDemoAdapter not available: %s", _e)
    _registry = ScenarioRegistry()
    _scanner = ControlScanner(_registry)
    _service = DemoRcaService(_registry)
    logger.info(
        "DemoAPI: loaded %d scenario(s): %s",
        len(_registry.scenario_ids()),
        _registry.scenario_ids(),
    )


def _get_registry() -> ScenarioRegistry:
    if _registry is None:
        raise RuntimeError("Registry not initialised — startup not complete.")
    return _registry


def _get_scanner() -> ControlScanner:
    if _scanner is None:
        raise RuntimeError("Scanner not initialised — startup not complete.")
    return _scanner


def _get_service() -> DemoRcaService:
    if _service is None:
        raise RuntimeError("DemoRcaService not initialised — startup not complete.")
    return _service


# ---------------------------------------------------------------------------
# Error helpers
# ---------------------------------------------------------------------------

def _not_found(code: str, message: str, detail: Dict[str, Any] | None = None) -> JSONResponse:
    return JSONResponse(
        status_code=404,
        content={"error": code, "message": message, "detail": detail or {}},
    )


def _bad_request(code: str, message: str, detail: Dict[str, Any] | None = None) -> JSONResponse:
    return JSONResponse(
        status_code=400,
        content={"error": code, "message": message, "detail": detail or {}},
    )


# ---------------------------------------------------------------------------
# Health
# ---------------------------------------------------------------------------

@app.get("/demo/health", tags=["meta"])
async def health() -> Dict[str, Any]:
    """Liveness probe."""
    reg = _get_registry()
    return {
        "status": "ok",
        "scenario_count": len(reg.scenario_ids()),
        "scenarios": reg.scenario_ids(),
    }


@app.get("/demo/adapters", tags=["meta"])
async def list_adapters_endpoint() -> Dict[str, Any]:
    """
    List registered InfrastructureAdapters.

    Returns ``{"items": [...], "total": N}`` where each item has
    ``adapter_id``, ``display_name``, and ``environment`` fields.
    """
    try:
        from src.infrastructure.base_adapter import list_adapters  # noqa: PLC0415
        adapters = list_adapters()
    except Exception as exc:
        logger.warning("Could not load infrastructure adapters: %s", exc)
        adapters = []
    return {"items": adapters, "total": len(adapters)}


@app.get("/demo/data/summary", tags=["meta"])
async def data_summary() -> Dict[str, Any]:
    """Static summary of the kratos_data CSV used as evidence."""
    return {
        "total_records": 6006,
        "total_aum": 1_320_961_508.99,
        "smdia_exposures": 1951,
        "orc_categories": 17,
        "date_range": {"from": "2016-03-07", "to": "2026-03-05"},
    }


@app.get("/demo/ontology/status", tags=["meta"])
async def ontology_status() -> Dict[str, Any]:
    """Static summary of the CauseLink CanonGraph ontology."""
    return {
        "nodes": 18,
        "edges": 15,
        "node_labels": 19,
        "rel_types": 26,
        "scenarios_seeded": 3,
    }


# ---------------------------------------------------------------------------
# Scenarios
# ---------------------------------------------------------------------------

@app.get("/demo/scenarios", tags=["scenarios"])
async def list_scenarios() -> Dict[str, Any]:
    """Return all available demo scenarios with summary metadata."""
    reg = _get_registry()
    items = [s.to_dict() for s in reg.list_scenarios()]
    return {"items": items, "total": len(items)}


@app.get("/demo/scenarios/{scenario_id}", tags=["scenarios"])
async def get_scenario(scenario_id: str) -> Dict[str, Any]:
    """Return full scenario pack: incident, controls, job_run, accounts, log filename."""
    reg = _get_registry()
    if not reg.has_scenario(scenario_id):
        return _not_found(
            "SCENARIO_NOT_FOUND",
            f"Scenario '{scenario_id}' does not exist.",
            {"available": reg.scenario_ids()},
        )
    pack = reg.get_pack(scenario_id)
    return {
        "scenario_id": scenario_id,
        "incident":    pack.incident,
        "controls":    pack.controls,
        "job_run":     pack.job_run,
        "accounts":    pack.accounts,
        "log_filename": pack.log_filename,
        "account_count": len(pack.accounts),
        "control_count": len(pack.controls),
        "failed_control_count": len(pack.failed_controls),
    }


# ---------------------------------------------------------------------------
# Controls
# ---------------------------------------------------------------------------

@app.get("/demo/controls/{scenario_id}", tags=["controls"])
async def get_control_scan(scenario_id: str) -> Dict[str, Any]:
    """Return control scan findings for a scenario (no RCA required)."""
    reg = _get_registry()
    if not reg.has_scenario(scenario_id):
        return _not_found(
            "SCENARIO_NOT_FOUND",
            f"Scenario '{scenario_id}' does not exist.",
            {"available": reg.scenario_ids()},
        )
    scanner = _get_scanner()
    result = scanner.scan(scenario_id)
    return result.to_dict()


# ---------------------------------------------------------------------------
# Investigations
# ---------------------------------------------------------------------------

@app.post("/demo/investigations", status_code=201, tags=["investigations"])
async def start_investigation(body: Dict[str, str]) -> Dict[str, Any]:
    """
    Start a new demo RCA investigation.

    Request body::

        { "scenario_id": "deposit_aggregation_failure", "job_id": "DAILY-INSURANCE-JOB-20260316" }

    Returns::

        { "investigation_id": "...", "status": "STARTED" }
    """
    scenario_id = body.get("scenario_id", "").strip()
    job_id = body.get("job_id", "").strip()

    if not scenario_id:
        return _bad_request("MISSING_SCENARIO_ID", "Request body must include 'scenario_id'.")

    reg = _get_registry()
    if not reg.has_scenario(scenario_id):
        return _not_found(
            "SCENARIO_NOT_FOUND",
            f"Scenario '{scenario_id}' does not exist.",
            {"available": reg.scenario_ids()},
        )

    # Resolve job_id from scenario pack if not provided
    if not job_id:
        pack = reg.get_pack(scenario_id)
        job_id = pack.job_id

    try:
        svc = _get_service()
        investigation_id = await svc.start_investigation(scenario_id, job_id)
        return {
            "investigation_id": investigation_id,
            "scenario_id":      scenario_id,
            "job_id":           job_id,
            "status":           "STARTED",
        }
    except Exception as exc:
        logger.exception("Failed to start investigation for scenario '%s'", scenario_id)
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@app.get("/demo/investigations/{investigation_id}", tags=["investigations"])
async def get_investigation(investigation_id: str) -> Dict[str, Any]:
    """Return the current InvestigationState as a JSON dict."""
    svc = _get_service()
    state = svc.get_state(investigation_id)
    if state is None:
        return _not_found(
            "INVESTIGATION_NOT_FOUND",
            f"Investigation '{investigation_id}' not found.",
        )
    return state.model_dump(mode="json")


@app.get("/demo/investigations/{investigation_id}/trace", tags=["investigations"])
async def get_investigation_trace(investigation_id: str) -> Dict[str, Any]:
    """Return the audit trail entries only."""
    svc = _get_service()
    state = svc.get_state(investigation_id)
    if state is None:
        return _not_found(
            "INVESTIGATION_NOT_FOUND",
            f"Investigation '{investigation_id}' not found.",
        )
    trace = [e.model_dump(mode="json") for e in state.audit_trace]
    return {"items": trace, "total": len(trace)}


@app.get("/demo/investigations/{investigation_id}/graph", tags=["investigations"])
async def get_investigation_graph(investigation_id: str) -> Dict[str, Any]:
    """Return the CanonGraph for visualization."""
    svc = _get_service()
    state = svc.get_state(investigation_id)
    if state is None:
        return _not_found(
            "INVESTIGATION_NOT_FOUND",
            f"Investigation '{investigation_id}' not found.",
        )
    if state.canon_graph is None:
        return _not_found(
            "GRAPH_NOT_READY",
            "Canon graph not yet available — investigation may still be initializing.",
        )
    return state.canon_graph.model_dump(mode="json")


# ---------------------------------------------------------------------------
# SSE stream
# ---------------------------------------------------------------------------

@app.get("/demo/stream/{investigation_id}", tags=["stream"])
async def stream_investigation(investigation_id: str) -> StreamingResponse:
    """
    Stream investigation phase events via Server-Sent Events.

    Each phase emits one event when complete::

        data: {"phase": "INTAKE", "phase_number": 1, "status": "OK", ...}

    The stream ends after phase 7 (PERSIST).
    """
    svc = _get_service()
    if svc.get_state(investigation_id) is None:
        # Return 404 as a plain JSON body; SSE clients must check HTTP status first
        raise HTTPException(
            status_code=404,
            detail=f"Investigation '{investigation_id}' not found.",
        )

    async def _event_generator() -> AsyncIterator[str]:
        if _OBS_AVAILABLE:
            _M.sse_connections_active.inc()
            _emit(EventName.SSE_CLIENT_CONNECTED, investigation_id=investigation_id)
        try:
            async for event in svc.stream(investigation_id):
                if _OBS_AVAILABLE:
                    _M.sse_events_emitted.labels(
                        event_type=getattr(event, "type", "UNKNOWN") or "UNKNOWN"
                    ).inc()
                yield f"data: {event.to_json()}\n\n"
        except Exception as exc:
            logger.exception("SSE stream error for %s: %s", investigation_id, exc)
            if _OBS_AVAILABLE:
                _M.api_errors.labels(endpoint="/demo/stream", method="GET", status_code="500").inc()
            error_payload = f'{{"error":"STREAM_ERROR","message":"{exc}"}}'
            yield f"data: {error_payload}\n\n"
        finally:
            if _OBS_AVAILABLE:
                _M.sse_connections_active.dec()
                _emit(EventName.SSE_CLIENT_DISCONNECTED, investigation_id=investigation_id)

    return StreamingResponse(
        _event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
        },
    )


# ---------------------------------------------------------------------------
# Entrypoint (when run directly)
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    import uvicorn

    port = int(os.getenv("DEMO_API_PORT", "8002"))
    uvicorn.run(
        "src.demo_api:app",
        host="0.0.0.0",
        port=port,
        reload=True,
        log_level="info",
    )

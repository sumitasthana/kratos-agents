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
from pathlib import Path
from typing import Any, AsyncIterator, Dict, Optional

# Load .env so OPENAI_API_KEY (and other secrets) are available without
# having to export them manually in the shell before starting uvicorn.
try:
    from dotenv import load_dotenv as _load_dotenv
    _load_dotenv(override=False)  # override=False keeps existing env vars
except ImportError:
    pass  # python-dotenv optional; env vars must be set manually

from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, StreamingResponse
from pydantic import BaseModel, Field

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
# Conversational chat endpoint (/api/chat)
# ---------------------------------------------------------------------------

class ChatMessage(BaseModel):
    """Request body for the /api/chat endpoint."""
    text: str = Field(..., min_length=1, max_length=4096, description="Free-form user message")
    session_id: Optional[str] = Field(None, description="Optional session ID for follow-up turns")
    scenario_id: Optional[str] = Field(None, description="Optionally pin to a specific scenario")


@app.post("/api/chat", tags=["chat"])
async def chat_rca(message: ChatMessage) -> StreamingResponse:
    """
    Natural language → 7-phase RCA pipeline (conversational mode).

    Reads ``CLAUDE.md`` as the system prompt and resolves the correct
    ``skills/*/SKILL.md`` based on the user's message text.  Streams
    the structured investigation response as Server-Sent Events, one
    event per phase (same format as ``/demo/stream/{id}``).

    **Demo mode**: uses the deterministic DemoRcaService — no LLM calls,
    no Neo4j, no OpenAI.  The ``CLAUDE.md`` + skill content is embedded
    in every SSE event as ``"skill_context"`` so the client (or a real
    Claude integration) can verify the behavioral contract in use.

    Example request::

        POST /api/chat
        {"text": "Our deposit run is showing accounts over SMDIA."}

    The endpoint returns an SSE stream.  Each event has the shape::

        data: {"phase": "INTAKE", "skill": "intake-agent", "status": "OK", ...}
    """
    from causelink.agents.skill_loader import get_loader  # noqa: PLC0415

    svc = _get_service()
    reg = _get_registry()
    loader = get_loader()

    # ── 1. Resolve which skill matches this message ──────────────────────
    skill_name = loader.resolve_skill_for_input(message.text)
    skill_text = loader.load(skill_name)
    master_text = loader.master_directive

    # ── 2. Resolve scenario_id from pinned value or NL parsing ───────────
    scenario_id: Optional[str] = message.scenario_id
    if scenario_id is None:
        text_lower = message.text.lower()
        if any(w in text_lower for w in ("deposit", "aggregation", "aggrstep", "smdia", "overstated")):
            scenario_id = "deposit_aggregation_failure"
        elif any(w in text_lower for w in ("trust", "irrevocable", "irr", "fiduciary", "orc=sgl")):
            scenario_id = "trust_irr_misclassification"
        elif any(w in text_lower for w in ("wire", "mt202", "swift", "gl break", "dropped")):
            scenario_id = "wire_mt202_drop"

    # ── 3. Start investigation (or reuse session) ─────────────────────────
    investigation_id: Optional[str] = None
    if scenario_id and scenario_id in reg.scenario_ids():
        # Derive a default job_id for the scenario
        _default_job_ids = {
            "deposit_aggregation_failure": "DAILY-INSURANCE-JOB-20260316",
            "trust_irr_misclassification": "TRUST-DAILY-BATCH-20260316",
            "wire_mt202_drop":             "WIRE-NIGHTLY-RECON-20260316",
        }
        job_id = _default_job_ids.get(scenario_id, "UNKNOWN-JOB")
        investigation_id = await svc.start_investigation(scenario_id, job_id)

    # ── 4. Stream response ────────────────────────────────────────────────
    async def _chat_event_generator() -> AsyncIterator[str]:
        import json  # noqa: PLC0415

        # First event: skill resolution metadata
        meta_event = json.dumps({
            "type": "SKILL_RESOLVED",
            "skill": skill_name,
            "scenario_id": scenario_id,
            "investigation_id": investigation_id,
            "skill_chars": len(skill_text),
            "master_chars": len(master_text),
            "user_message": message.text,
        })
        yield f"data: {meta_event}\n\n"

        if investigation_id is None:
            # No scenario resolved — emit a clarification prompt
            clarify_event = json.dumps({
                "type": "CLARIFICATION_NEEDED",
                "skill": "conversation-interface",
                "question": (
                    "Which system is affected — deposit processing, trust accounts, "
                    "or wire transfers? (Alternatively, provide a scenario_id: "
                    "deposit_aggregation_failure | trust_irr_misclassification | wire_mt202_drop)"
                ),
            })
            yield f"data: {clarify_event}\n\n"
            return

        # Stream the 7-phase investigation
        async for event in svc.stream(investigation_id):
            # Augment each event with the active skill name so clients know
            # which behavioral contract governed that phase.
            raw = event.to_json()
            try:
                payload = json.loads(raw)
            except Exception:
                payload = {"raw": raw}
            payload["skill"] = skill_name
            yield f"data: {json.dumps(payload)}\n\n"

    return StreamingResponse(
        _chat_event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
        },
    )


# ---------------------------------------------------------------------------
# Entrypoint (when run directly)
# ---------------------------------------------------------------------------

# ---------------------------------------------------------------------------
# LLM-backed follow-up Q&A endpoint (/api/ask)
# ---------------------------------------------------------------------------

_ASK_SYSTEM_PROMPT = """You are Kratos, a senior bank examiner specializing in FDIC \
Part 370/330 Root Cause Analysis. You just completed a multi-hop RCA investigation. \
Answer the user's follow-up question using ONLY the investigation context provided. \
Be precise, cite defect IDs and regulation sections where relevant. \
Respond in 2-4 sentences maximum. Do not speculate beyond what the evidence shows. \
Use banking domain vocabulary: "account", "defect", "violation", "compliance gap". \
Never hallucinate regulation citations."""

_SCENARIO_DESCRIPTIONS = {
    "deposit_aggregation_failure": (
        "Deposit aggregation failure — AGGRSTEP (Step 3) was commented out in "
        "DAILY-INSURANCE-JOB.jcl (DEF-LDS-001), causing per-account instead of "
        "per-depositor coverage calculation. 1,951 of 6,006 accounts exceed SMDIA "
        "without aggregation. Violates 12 CFR § 330.1(b)."
    ),
    "trust_irr_misclassification": (
        "Trust IRR misclassification — IRR branch not implemented in "
        "TRUST-INSURANCE-CALC.cob and BeneficiaryClassifier.java (DEF-TCS-001, DEF-TCS-003). "
        "All IRR accounts fall back to SGL ($250K flat cap). "
        "253 affected accounts, ~$61.8M coverage gap. Violates 12 CFR § 330.13."
    ),
    "wire_mt202_drop": (
        "Wire MT202 silent drop — swift_parser.py parse_message() handles MT103 only; "
        "MT202 and MT202COV are silently dropped with no handler (DEF-WTS-001). "
        "47 MT202 + 12 MT202COV messages dropped, GL break $284.7M. "
        "Violates 12 CFR § 370.4(a)(1)."
    ),
}


class AskRequest(BaseModel):
    """Request body for the /api/ask endpoint (LLM follow-up Q&A)."""
    question: str = Field(..., min_length=1, max_length=2048)
    scenario_id: Optional[str] = Field(None)
    investigation_context: Optional[Dict[str, Any]] = Field(
        None,
        description="Serialised phases, confidence, root_cause from the frontend",
    )


@app.post("/api/ask", tags=["chat"])
async def ask_llm(req: AskRequest) -> StreamingResponse:
    """
    LLM-backed follow-up Q&A (OpenAI gpt-4o-mini).

    Takes the current investigation context (phases, confidence, root_cause_final,
    recommendations) and the user's question, builds a compact context prompt,
    then streams the OpenAI response token-by-token as SSE events.

    Event format (one per token):  ``data: {"type": "TOKEN", "text": "..."}`
    Final event:                   ``data: {"type": "DONE"}``
    Error event:                   ``data: {"type": "ERROR", "message": "..."}`

    Falls back to a canned response if OPENAI_API_KEY is not set.
    """
    import json  # noqa: PLC0415

    # ── Build investigation context string ────────────────────────────────
    ctx_parts: list[str] = []

    scenario_id = req.scenario_id
    if scenario_id and scenario_id in _SCENARIO_DESCRIPTIONS:
        ctx_parts.append(f"SCENARIO: {_SCENARIO_DESCRIPTIONS[scenario_id]}")

    ctx = req.investigation_context or {}

    # Root cause
    rc = ctx.get("root_cause_final")
    if rc:
        ctx_parts.append(f"ROOT CAUSE CONFIRMED: {rc}")

    # Confidence
    conf = ctx.get("confidence") or {}
    composite = conf.get("composite", 0)
    if composite:
        ctx_parts.append(
            f"CONFIDENCE: {round(composite * 100)}% composite "
            f"(E={round((conf.get('E', 0)) * 100)}%, "
            f"T={round((conf.get('T', 0)) * 100)}%, "
            f"D={round((conf.get('D', 0)) * 100)}%, "
            f"H={round((conf.get('H', 0)) * 100)}%)"
        )

    # Phase summaries
    phases = ctx.get("phases") or []
    if phases:
        summaries = [
            f"  {p.get('phase', '?')}: {p.get('summary', '')}"
            for p in phases
            if p.get("summary")
        ]
        if summaries:
            ctx_parts.append("PHASE SUMMARIES:\n" + "\n".join(summaries))

    # Recommendations (top 3)
    recs = ctx.get("remediation") or []
    if recs:
        rec_lines = [
            f"  [{r.get('defect_id', '?')}] {r.get('title', r.get('action', '?')[:60])}"
            for r in recs[:3]
        ]
        ctx_parts.append("TOP RECOMMENDATIONS:\n" + "\n".join(rec_lines))

    context_block = "\n\n".join(ctx_parts) if ctx_parts else "No investigation context available."
    user_prompt = f"INVESTIGATION CONTEXT:\n{context_block}\n\nUSER QUESTION: {req.question}"

    async def _stream() -> AsyncIterator[str]:
        api_key = os.environ.get("OPENAI_API_KEY", "")

        if not api_key:
            # ── No API key — structured fallback using context ────────────
            fallback = _build_fallback_answer(req.question, scenario_id, ctx)
            payload = json.dumps({"type": "TOKEN", "text": fallback})
            yield f"data: {payload}\n\n"
            yield f"data: {json.dumps({'type': 'DONE'})}\n\n"
            return

        # ── OpenAI gpt-4o-mini streaming ─────────────────────────────────
        try:
            from openai import AsyncOpenAI  # noqa: PLC0415
            client = AsyncOpenAI(api_key=api_key)
            stream = await client.chat.completions.create(
                model="gpt-4o-mini",
                max_tokens=512,
                temperature=0,
                stream=True,
                messages=[
                    {"role": "system", "content": _ASK_SYSTEM_PROMPT},
                    {"role": "user",   "content": user_prompt},
                ],
            )
            async for chunk in stream:
                text = chunk.choices[0].delta.content or ""
                if text:
                    payload = json.dumps({"type": "TOKEN", "text": text})
                    yield f"data: {payload}\n\n"
            yield f"data: {json.dumps({'type': 'DONE'})}\n\n"
        except Exception as exc:
            logger.warning("LLM streaming error: %s", exc)
            err = json.dumps({"type": "ERROR", "message": str(exc)})
            yield f"data: {err}\n\n"

    return StreamingResponse(
        _stream(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


def _build_fallback_answer(
    question: str,
    scenario_id: Optional[str],
    ctx: Dict[str, Any],
) -> str:
    """Return a context-aware canned answer when no API key is configured."""
    q = question.lower()
    rc = ctx.get("root_cause_final", "")
    recs = ctx.get("remediation") or []
    conf = ctx.get("confidence") or {}
    composite = round((conf.get("composite", 0)) * 100)

    if any(w in q for w in ("root cause", "cause", "why", "what happened", "what caused")):
        if rc:
            return (
                f"The confirmed root cause is {rc}. "
                + (_SCENARIO_DESCRIPTIONS.get(scenario_id or "", "") or
                   "Check the causal chain in the trace panel for the full backtracking path.")
            )
    if any(w in q for w in ("fix", "remediat", "recommend", "action", "how to")):
        if recs:
            top = recs[0]
            return (
                f"The highest-priority remediation is [{top.get('defect_id', '?')}]: "
                f"{top.get('title', top.get('action', '?')[:80])}. "
                f"See the Remediation panel for all {len(recs)} actions."
            )
    if any(w in q for w in ("confidence", "score", "certain", "sure", "how confident")):
        return (
            f"The composite confidence score is {composite}% "
            f"(Evidence {round((conf.get('E', 0)) * 100)}%, "
            f"Topology {round((conf.get('T', 0)) * 100)}%, "
            f"Depth {round((conf.get('D', 0)) * 100)}%, "
            f"Hypothesis {round((conf.get('H', 0)) * 100)}%). "
            f"{'This exceeds the 70% confirmation threshold.' if composite >= 70 else 'This is below the confirmation threshold.'}"
        )
    if any(w in q for w in ("regulation", "cfr", "fdic", "compliance", "violation")):
        desc = _SCENARIO_DESCRIPTIONS.get(scenario_id or "", "")
        if desc:
            # Extract regulation reference from description
            import re  # noqa: PLC0415
            match = re.search(r"12 CFR[^.]+", desc)
            if match:
                return f"The relevant regulation is {match.group(0)}. {desc}"
    # Generic fallback
    if rc:
        return (
            f"Root cause confirmed: {rc}, with {composite}% confidence. "
            f"The investigation identified {len(recs)} remediation action(s). "
            "Set ANTHROPIC_API_KEY to enable full conversational Q&A."
        )
    return (
        "The investigation is complete — review the causal chain and recommendations in the right panel. "
        "Set ANTHROPIC_API_KEY to enable full conversational Q&A."
    )


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

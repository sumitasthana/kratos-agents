"""
a2a/server.py
Agent-to-Agent (A2A) HTTP server — CauseLink RCA FastAPI application.

Extracted from: src/causelink_api.py
Split rule: FastAPI app, middleware, route handlers, adapter factory,
            and pipeline runner.  Protocol/schema types live in a2a/protocol.py.

Security:
    - Credentials from env vars only (NEO4J_URI, NEO4J_USER, NEO4J_PASSWORD).
    - investigation_id in path is UUID-validated; no SQL-injectable context.
    - Idempotency keys are stored as-submitted (not executed as queries).
    - No raw evidence content is returned — only summaries and IDs.

Run:
    cd kratos-agents
    uvicorn a2a.server:app --host 0.0.0.0 --port 8001 --reload
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
import uuid
from datetime import datetime
from typing import Any, AsyncGenerator, Dict, List, Optional

import uvicorn
from fastapi import FastAPI, HTTPException, Path, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field

# Import protocol types from the sibling module
from a2a.protocol import (
    InvestigationStore,
    StartInvestigationRequest,
    InvestigationSummaryResponse,
    InvestigationResultResponse,
)

# CauseLink internals (still in src/ — path unchanged until full migration)
from src.causelink.agents.causal_engine import CausalEngineAgent
from src.causelink.agents.evidence_collector import EvidenceCollectorAgent
from src.causelink.agents.hypothesis_generator import HypothesisGeneratorAgent
from src.causelink.agents.ontology_context import OntologyContextAgent
from src.causelink.agents.ranker import RankerAgent
from src.causelink.evidence.contracts import NullEvidenceService
from src.causelink.ontology.adapter import Neo4jOntologyAdapter, OntologyAdapterError
from src.causelink.patterns.library import HypothesisPatternLibrary
from src.causelink.services.dashboard_schema import RcaDashboardSummary
from src.causelink.services.ontology_backtracking import OntologyBacktrackingService
from src.causelink.state.investigation import (
    InvestigationAnchor,
    InvestigationInput,
    InvestigationState,
    InvestigationStatus,
)

logger = logging.getLogger(__name__)

# ─────────────────────────────────────────────────────────────────────────────
# Shared investigation store (singleton)
# ─────────────────────────────────────────────────────────────────────────────

_store = InvestigationStore()


# ─────────────────────────────────────────────────────────────────────────────
# Adapter factory
# ─────────────────────────────────────────────────────────────────────────────

def _make_adapter() -> Optional[Neo4jOntologyAdapter]:
    """
    Build adapter from environment variables.

    Returns None (gracefully) when env vars are absent — the pipeline
    will run with structural validation skipped (edges remain PENDING).
    This allows local development without a live Neo4j instance.
    """
    uri      = os.environ.get("NEO4J_URI", "")
    user     = os.environ.get("NEO4J_USER", "")
    password = os.environ.get("NEO4J_PASSWORD", "")
    if not (uri and user and password):
        logger.warning(
            "NEO4J_URI/USER/PASSWORD not set — running without Neo4j. "
            "Structural path validation will be skipped."
        )
        return None
    try:
        return Neo4jOntologyAdapter(uri=uri, user=user, password=password)
    except OntologyAdapterError as exc:
        logger.error("Failed to create Neo4j adapter: %s", exc)
        return None


# ─────────────────────────────────────────────────────────────────────────────
# FastAPI App
# ─────────────────────────────────────────────────────────────────────────────

app = FastAPI(
    title="CauseLink RCA API",
    description=(
        "Ontology-native, evidence-only root cause analysis service. "
        "Investigations are Neo4j-bounded, pattern-matched, and fully auditable."
    ),
    version="1.0.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # tighten to specific origins in production
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ─────────────────────────────────────────────────────────────────────────────
# Helper: state → response converters
# ─────────────────────────────────────────────────────────────────────────────

def _to_summary(state: InvestigationState) -> InvestigationSummaryResponse:
    inp    = state.investigation_input
    anchor = inp.anchor
    return InvestigationSummaryResponse(
        investigation_id      = inp.investigation_id,
        status                = state.status.value,
        anchor_type           = anchor.anchor_type,
        anchor_value          = anchor.anchor_primary_value,
        created_at            = state.created_at.isoformat(),
        updated_at            = state.updated_at.isoformat(),
        escalation            = state.escalation,
        root_cause_confirmed  = state.root_cause_final is not None,
        root_cause_summary    = (
            state.root_cause_final.get("summary") if state.root_cause_final else None
        ),
        missing_evidence_count = len(state.missing_evidence),
        hypothesis_count       = len(state.hypotheses),
    )


def _to_result(state: InvestigationState) -> InvestigationResultResponse:
    inp    = state.investigation_input
    anchor = inp.anchor
    graph  = state.canon_graph
    return InvestigationResultResponse(
        investigation_id       = inp.investigation_id,
        status                 = state.status.value,
        anchor_type            = anchor.anchor_type,
        anchor_value           = anchor.anchor_primary_value,
        created_at             = state.created_at.isoformat(),
        updated_at             = state.updated_at.isoformat(),
        escalation             = state.escalation,
        escalation_reason      = state.escalation_reason,
        root_cause_final       = state.root_cause_final,
        root_cause_candidates  = [h.model_dump() for h in state.root_cause_candidates],
        hypotheses             = [h.model_dump() for h in state.hypotheses],
        missing_evidence       = [m.model_dump() for m in state.missing_evidence],
        recommended_actions    = state.recommended_actions,
        causal_graph_edges_count = len(graph.edges) if graph else 0,
        causal_graph_node_count  = len(graph.nodes) if graph else 0,
        ontology_paths_count     = len(state.ontology_paths),
        insufficient_evidence_report = (
            state.insufficient_evidence_report.model_dump()
            if state.insufficient_evidence_report else None
        ),
    )


async def _require_state(investigation_id: str) -> InvestigationState:
    """Fetch state by ID or raise HTTP 404."""
    state = await _store.get(investigation_id)
    if state is None:
        raise HTTPException(
            status_code=404,
            detail=f"Investigation {investigation_id!r} not found.",
        )
    return state


# ─────────────────────────────────────────────────────────────────────────────
# Pipeline runner (background task)
# ─────────────────────────────────────────────────────────────────────────────

async def _run_pipeline(state: InvestigationState) -> None:
    """Execute the full CauseLink 7-phase pipeline for a given investigation state."""
    adapter     = _make_adapter()
    ev_service  = NullEvidenceService()
    pattern_lib = HypothesisPatternLibrary()

    agents = [
        CausalEngineAgent(ontology_adapter=adapter, evidence_service=ev_service),
        EvidenceCollectorAgent(evidence_service=ev_service),
        HypothesisGeneratorAgent(pattern_library=pattern_lib),
        OntologyContextAgent(ontology_adapter=adapter),
        RankerAgent(),
    ]
    backtracker = OntologyBacktrackingService(ontology_adapter=adapter)

    try:
        for agent in agents:
            state = await agent.run(state)
            await _store.put(state)

        state = await backtracker.run(state)
        await _store.put(state)
    except Exception as exc:
        logger.exception("Pipeline error for %s: %s", state.investigation_input.investigation_id, exc)
        state.status = InvestigationStatus.FAILED
        state.escalation = True
        state.escalation_reason = str(exc)
        await _store.put(state)


# ─────────────────────────────────────────────────────────────────────────────
# POST /investigations
# ─────────────────────────────────────────────────────────────────────────────

@app.post(
    "/investigations",
    response_model=InvestigationSummaryResponse,
    status_code=201,
    summary="Start a new investigation",
)
async def start_investigation(body: StartInvestigationRequest) -> InvestigationSummaryResponse:
    """
    Start a CauseLink investigation for the given anchor.

    Idempotency: if *idempotency_key* is provided and a prior investigation
    with that key exists, returns the existing investigation (HTTP 200)
    rather than starting a duplicate run.
    """
    if body.idempotency_key:
        existing = await _store.find_by_idempotency_key(body.idempotency_key)
        if existing is not None:
            logger.info(
                "Idempotency hit: key=%s → investigation=%s",
                body.idempotency_key,
                existing.investigation_input.investigation_id,
            )
            return _to_summary(existing)

    inv_input = InvestigationInput(
        investigation_id  = str(uuid.uuid4()),
        idempotency_key   = body.idempotency_key,
        anchor            = InvestigationAnchor(
            anchor_type          = body.anchor_type,
            anchor_primary_key   = body.anchor_primary_key,
            anchor_primary_value = body.anchor_primary_value,
        ),
        max_hops              = body.max_hops,
        confidence_threshold  = body.confidence_threshold,
        context               = body.context,
    )
    state = InvestigationState(investigation_input=inv_input)
    await _store.put(state)
    asyncio.create_task(_run_pipeline(state))
    return _to_summary(state)


# ─────────────────────────────────────────────────────────────────────────────
# GET /investigations/{id}
# ─────────────────────────────────────────────────────────────────────────────

@app.get(
    "/investigations/{investigation_id}",
    response_model=InvestigationResultResponse,
    summary="Get investigation result",
)
async def get_investigation(
    investigation_id: str = Path(..., description="UUID returned by POST /investigations"),
) -> InvestigationResultResponse:
    state = await _require_state(investigation_id)
    return _to_result(state)


# ─────────────────────────────────────────────────────────────────────────────
# GET /investigations/{id}/trace
# ─────────────────────────────────────────────────────────────────────────────

@app.get(
    "/investigations/{investigation_id}/trace",
    summary="Get full audit trace",
)
async def get_trace(
    investigation_id: str = Path(...),
) -> Dict[str, Any]:
    state = await _require_state(investigation_id)
    return {
        "investigation_id": investigation_id,
        "audit_trace":      [entry.model_dump() for entry in state.audit_trace],
        "total_steps":      len(state.audit_trace),
    }


# ─────────────────────────────────────────────────────────────────────────────
# GET /investigations/{id}/graph
# ─────────────────────────────────────────────────────────────────────────────

@app.get(
    "/investigations/{investigation_id}/graph",
    summary="Get CanonGraph summary and ontology paths",
)
async def get_graph(
    investigation_id: str = Path(...),
) -> Dict[str, Any]:
    state = await _require_state(investigation_id)
    graph = state.canon_graph
    return {
        "investigation_id": investigation_id,
        "anchor": {
            "neo4j_id": graph.anchor_neo4j_id     if graph else None,
            "label":    graph.anchor_label         if graph else None,
            "value":    graph.anchor_primary_value if graph else None,
        },
        "nodes": [
            {
                "neo4j_id":     n.neo4j_id,
                "labels":       n.labels,
                "primary_value": n.primary_value,
                "provenance":   n.provenance,
            }
            for n in (graph.nodes if graph else [])
        ],
        "edges": [
            {
                "neo4j_id": e.neo4j_id,
                "type":     e.type,
                "from_id":  e.from_neo4j_id,
                "to_id":    e.to_neo4j_id,
            }
            for e in (graph.edges if graph else [])
        ],
        "ontology_paths": state.ontology_paths,
    }


# ─────────────────────────────────────────────────────────────────────────────
# POST /investigations/{id}/replay
# ─────────────────────────────────────────────────────────────────────────────

@app.post(
    "/investigations/{investigation_id}/replay",
    response_model=InvestigationSummaryResponse,
    status_code=202,
    summary="Re-run investigation with same input",
)
async def replay_investigation(
    investigation_id: str = Path(...),
) -> InvestigationSummaryResponse:
    original = await _require_state(investigation_id)
    new_input = InvestigationInput(
        investigation_id     = str(uuid.uuid4()),
        idempotency_key      = None,
        anchor               = original.investigation_input.anchor,
        max_hops             = original.investigation_input.max_hops,
        confidence_threshold = original.investigation_input.confidence_threshold,
        context              = original.investigation_input.context,
    )
    new_state = InvestigationState(investigation_input=new_input)
    await _store.put(new_state)
    asyncio.create_task(_run_pipeline(new_state))
    return _to_summary(new_state)


# ─────────────────────────────────────────────────────────────────────────────
# GET /investigations/{id}/stream  (SSE)
# ─────────────────────────────────────────────────────────────────────────────

@app.get(
    "/investigations/{investigation_id}/stream",
    summary="Server-Sent Events progress stream",
)
async def stream_investigation(
    investigation_id: str = Path(...),
) -> StreamingResponse:
    await _require_state(investigation_id)

    async def _event_generator() -> AsyncGenerator[str, None]:
        done_statuses = {InvestigationStatus.COMPLETE, InvestigationStatus.FAILED}
        for _ in range(60):
            state = await _store.get(investigation_id)
            if state:
                payload = json.dumps({
                    "status":       state.status.value,
                    "escalation":   state.escalation,
                    "hypotheses":   len(state.hypotheses),
                    "root_cause":   state.root_cause_final is not None,
                })
                yield f"data: {payload}\n\n"
                if state.status in done_statuses:
                    break
            await asyncio.sleep(1.0)
        yield "data: {\"status\": \"stream_end\"}\n\n"

    return StreamingResponse(_event_generator(), media_type="text/event-stream")


# ─────────────────────────────────────────────────────────────────────────────
# GET /health
# ─────────────────────────────────────────────────────────────────────────────

@app.get("/health", summary="Liveness check")
async def health() -> Dict[str, Any]:
    return {
        "status":           "ok",
        "investigations":   len(await _store.all_ids()),
        "neo4j_configured": bool(os.environ.get("NEO4J_URI")),
    }


if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=8001)

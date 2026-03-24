"""
causelink_api.py — CauseLink RCA HTTP service.

FastAPI application for the CauseLink ontology-native, evidence-only RCA engine.

Endpoints:
    POST   /investigations              — start a new investigation (idempotent)
    GET    /investigations/{id}         — get investigation status + result
    GET    /investigations/{id}/trace   — full audit trace
    GET    /investigations/{id}/graph   — CanonGraph summary + ontology paths
    POST   /investigations/{id}/replay  — re-run investigation with same InvestigationInput
    GET    /investigations/{id}/stream  — Server-Sent Events progress stream

Security:
    - Credentials from env vars only (NEO4J_URI, NEO4J_USER, NEO4J_PASSWORD).
    - investigation_id in path is UUID-validated; no SQL-injectable context.
    - Idempotency keys are stored as-submitted (not executed as queries).
    - No raw evidence content is returned — only summaries and IDs.

Run:
    cd src
    uvicorn causelink_api:app --host 0.0.0.0 --port 8001 --reload
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

from causelink.agents.causal_engine import CausalEngineAgent
from causelink.agents.evidence_collector import EvidenceCollectorAgent
from causelink.agents.hypothesis_generator import HypothesisGeneratorAgent
from causelink.agents.ontology_context import OntologyContextAgent
from causelink.agents.ranker import RankerAgent
from causelink.evidence.contracts import NullEvidenceService
from causelink.ontology.adapter import Neo4jOntologyAdapter, OntologyAdapterError
from causelink.patterns.library import HypothesisPatternLibrary
from causelink.services.dashboard_schema import RcaDashboardSummary
from causelink.services.ontology_backtracking import OntologyBacktrackingService
from causelink.state.investigation import (
    InvestigationAnchor,
    InvestigationInput,
    InvestigationState,
    InvestigationStatus,
)

logger = logging.getLogger(__name__)

# ─────────────────────────────────────────────────────────────────────────────
# In-memory investigation store
# (Replace with Redis/PostgreSQL for production deployments)
# ─────────────────────────────────────────────────────────────────────────────

class InvestigationStore:
    """Thread-safe in-memory store for investigation states."""

    def __init__(self) -> None:
        self._by_id: Dict[str, InvestigationState] = {}
        self._idempotency: Dict[str, str] = {}  # idempotency_key → investigation_id
        self._lock = asyncio.Lock()

    async def get(self, investigation_id: str) -> Optional[InvestigationState]:
        return self._by_id.get(investigation_id)

    async def put(self, state: InvestigationState) -> None:
        async with self._lock:
            inv_id = state.investigation_input.investigation_id
            self._by_id[inv_id] = state
            key = state.investigation_input.idempotency_key
            if key:
                self._idempotency[key] = inv_id

    async def find_by_idempotency_key(self, key: str) -> Optional[InvestigationState]:
        inv_id = self._idempotency.get(key)
        if inv_id:
            return self._by_id.get(inv_id)
        return None

    async def all_ids(self) -> List[str]:
        return list(self._by_id.keys())


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
    uri = os.environ.get("NEO4J_URI", "")
    user = os.environ.get("NEO4J_USER", "")
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
# Request / response schemas
# ─────────────────────────────────────────────────────────────────────────────


class StartInvestigationRequest(BaseModel):
    """POST /investigations request body."""

    anchor_type: str = Field(
        ...,
        description=(
            "Ontology label of the investigation anchor. "
            "Must be one of: Incident, Violation, Job, Pipeline, System"
        ),
    )
    anchor_primary_key: str = Field(
        ..., description="Primary key property name, e.g. 'incident_id'"
    )
    anchor_primary_value: str = Field(
        ..., description="Value of the anchor primary key, e.g. 'INC-2026-001'"
    )
    max_hops: int = Field(default=3, ge=1, le=6)
    confidence_threshold: float = Field(default=0.80, ge=0.0, le=1.0)
    context: Dict[str, Any] = Field(
        default_factory=dict,
        description=(
            "Optional context dictionary. "
            "Supported keys: time_range_start, time_range_end (ISO-8601 strings)."
        ),
    )
    idempotency_key: Optional[str] = Field(
        None,
        description=(
            "Caller-supplied idempotency key. "
            "Submitting the same key twice returns the existing investigation "
            "without re-running the pipeline."
        ),
    )


class InvestigationSummaryResponse(BaseModel):
    """Lightweight status response."""

    investigation_id: str
    status: str
    anchor_type: str
    anchor_value: str
    created_at: str
    updated_at: str
    escalation: bool
    root_cause_confirmed: bool
    root_cause_summary: Optional[str] = None
    missing_evidence_count: int = 0
    hypothesis_count: int = 0


class InvestigationResultResponse(BaseModel):
    """Full investigation result."""

    investigation_id: str
    status: str
    anchor_type: str
    anchor_value: str
    created_at: str
    updated_at: str
    escalation: bool
    escalation_reason: Optional[str]
    root_cause_final: Optional[Dict[str, Any]]
    root_cause_candidates: List[Dict[str, Any]]
    hypotheses: List[Dict[str, Any]]
    missing_evidence: List[Dict[str, Any]]
    recommended_actions: List[str]
    causal_graph_edges_count: int
    causal_graph_node_count: int
    ontology_paths_count: int
    insufficient_evidence_report: Optional[Dict[str, Any]]


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
    # Idempotency check
    if body.idempotency_key:
        existing = await _store.find_by_idempotency_key(body.idempotency_key)
        if existing is not None:
            logger.info(
                "Idempotency hit: key=%s → investigation=%s",
                body.idempotency_key,
                existing.investigation_input.investigation_id,
            )
            return _to_summary(existing)

    # Build input
    inv_input = InvestigationInput(
        investigation_id=str(uuid.uuid4()),
        idempotency_key=body.idempotency_key,
        anchor=InvestigationAnchor(
            anchor_type=body.anchor_type,
            anchor_primary_key=body.anchor_primary_key,
            anchor_primary_value=body.anchor_primary_value,
        ),
        max_hops=body.max_hops,
        confidence_threshold=body.confidence_threshold,
        context=body.context,
    )
    state = InvestigationState(investigation_input=inv_input)

    # Persist immediately so GET /id is available during async run
    await _store.put(state)

    # Run pipeline in background
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
        "audit_trace": [entry.model_dump() for entry in state.audit_trace],
        "total_steps": len(state.audit_trace),
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
            "neo4j_id": graph.anchor_neo4j_id if graph else None,
            "label": graph.anchor_label if graph else None,
            "value": graph.anchor_primary_value if graph else None,
        },
        "nodes": [
            {
                "neo4j_id": n.neo4j_id,
                "labels": n.labels,
                "primary_value": n.primary_value,
                "provenance": n.provenance,
            }
            for n in (graph.nodes if graph else [])
        ],
        "edges": [
            {
                "neo4j_id": e.neo4j_id,
                "type": e.type,
                "start": e.start_node_id,
                "end": e.end_node_id,
            }
            for e in (graph.edges if graph else [])
        ],
        "ontology_paths": [
            {
                "path_id": p.path_id,
                "description": p.description,
                "hop_count": p.hop_count,
                "node_sequence": p.node_sequence,
                "rel_type_sequence": p.rel_type_sequence,
            }
            for p in state.ontology_paths_used
        ],
        "causal_graph_node_ids": state.causal_graph_node_ids,
        "causal_graph_edges": [
            {
                "edge_id": e.edge_id,
                "cause": e.cause_node_id,
                "effect": e.effect_node_id,
                "mechanism": e.mechanism,
                "status": e.status.value,
                "structural_path_validated": e.structural_path_validated,
                "confidence": e.confidence,
            }
            for e in state.causal_graph_edges
        ],
    }


# ─────────────────────────────────────────────────────────────────────────────
# POST /investigations/{id}/replay
# ─────────────────────────────────────────────────────────────────────────────


@app.post(
    "/investigations/{investigation_id}/replay",
    response_model=InvestigationSummaryResponse,
    status_code=201,
    summary="Replay investigation with same input",
)
async def replay_investigation(
    investigation_id: str = Path(...),
) -> InvestigationSummaryResponse:
    """
    Re-run the pipeline using the original InvestigationInput.

    Creates a new investigation_id.  The replayed run may differ from the
    original only if the underlying evidence sources or ontology have changed.
    """
    original = await _require_state(investigation_id)
    original_input = original.investigation_input

    # Create a fresh input preserving anchor + parameters but new investigation_id
    replayed_input = InvestigationInput(
        investigation_id=str(uuid.uuid4()),
        idempotency_key=None,  # replay is never idempotent
        anchor=original_input.anchor,
        max_hops=original_input.max_hops,
        confidence_threshold=original_input.confidence_threshold,
        context=original_input.context,
    )
    new_state = InvestigationState(investigation_input=replayed_input)
    await _store.put(new_state)
    asyncio.create_task(_run_pipeline(new_state))

    return _to_summary(new_state)


# ─────────────────────────────────────────────────────────────────────────────
# GET /investigations/{id}/stream  (Server-Sent Events)
# ─────────────────────────────────────────────────────────────────────────────


# ─────────────────────────────────────────────────────────────────────────────
# GET /investigations/{id}/dashboard
# ─────────────────────────────────────────────────────────────────────────────


@app.get(
    "/investigations/{investigation_id}/dashboard",
    response_model=RcaDashboardSummary,
    summary="Get UI-ready RCA dashboard summary with lineage walk and failure node",
)
async def get_dashboard(
    investigation_id: str = Path(..., description="UUID returned by POST /investigations"),
    mode: str = Query(
        default="normal",
        description=(
            "Traversal mode: 'normal' stops at the first confirmed failure, "
            "'exploratory' evaluates all nodes."
        ),
    ),
) -> RcaDashboardSummary:
    """
    Run the ontology backtracking traversal on the investigation and return a
    UI-ready RCA dashboard summary.

    The summary includes:
      - scenario card (scenario_name, anchor_type, anchor_id)
      - health score and health status
      - problem type and control triggered
      - lineage walk (ordered node sequence with status per node)
      - failure node ID, status, and failure reason
      - consolidated findings list
      - agent analysis chain entries
      - referenced evidence IDs and ontology path IDs
      - stop reason and traversal mode

    The investigation does not need to be COMPLETED to call this endpoint;
    partial results are returned when evidence collection is still in progress,
    with most nodes evaluated as UNKNOWN.

    mode='exploratory' evaluates all nodes even after a confirmed failure is found.
    mode='normal' (default) stops at the first confirmed failure.
    """
    if mode not in ("normal", "exploratory"):
        raise HTTPException(
            status_code=422,
            detail="mode must be 'normal' or 'exploratory'.",
        )
    state = await _require_state(investigation_id)

    if state.canon_graph is None:
        raise HTTPException(
            status_code=409,
            detail=(
                "Investigation has no CanonGraph yet. "
                "The ontology loading step has not completed. "
                f"Current status: {state.status.value}."
            ),
        )

    service = OntologyBacktrackingService()
    try:
        bt_result = service.backtrack_with_early_stop(state, mode=mode)
        summary = service.to_dashboard_summary(state, bt_result)
    except Exception as exc:  # pragma: no cover
        logger.exception(
            "Dashboard generation failed for investigation %s: %s",
            investigation_id, exc,
        )
        raise HTTPException(
            status_code=500,
            detail=f"Dashboard generation error: {exc}",
        ) from exc

    return summary


@app.get(
    "/investigations/{investigation_id}/stream",
    summary="Stream investigation progress via Server-Sent Events",
)
async def stream_investigation(
    investigation_id: str = Path(...),
) -> StreamingResponse:
    """
    Stream real-time progress of a running investigation as SSE events.

    Events:
        data: {"event": "status_change", "status": "EVIDENCE_COLLECTION", ...}
        data: {"event": "completed", "status": "COMPLETED", ...}
        data: {"event": "error", "message": "..."}
    """
    await _require_state(investigation_id)  # 404 check

    return StreamingResponse(
        _sse_generator(investigation_id),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
        },
    )


async def _sse_generator(investigation_id: str) -> AsyncGenerator[str, None]:
    """Yield SSE events until investigation reaches a terminal state."""
    terminal = {
        InvestigationStatus.COMPLETED,
        InvestigationStatus.INSUFFICIENT_EVIDENCE,
        InvestigationStatus.ESCALATED,
        InvestigationStatus.ERROR,
    }
    last_status: Optional[str] = None
    last_audit_len = 0
    poll_interval = 0.5
    max_polls = 300  # 150 seconds timeout

    for _ in range(max_polls):
        state = await _store.get(investigation_id)
        if state is None:
            yield _sse_event({"event": "error", "message": "Investigation not found"})
            return

        current_status = state.status.value
        if current_status != last_status:
            last_status = current_status
            yield _sse_event({
                "event": "status_change",
                "investigation_id": investigation_id,
                "status": current_status,
                "timestamp": datetime.utcnow().isoformat(),
                "hypothesis_count": len(state.hypotheses),
                "evidence_count": len(state.evidence_objects),
                "missing_evidence_count": len(state.missing_evidence),
            })

        # Stream new audit entries since last poll
        new_entries = state.audit_trace[last_audit_len:]
        for entry in new_entries:
            yield _sse_event({
                "event": "audit",
                "agent_type": entry.agent_type,
                "action": entry.action,
                "decision": entry.decision,
                "timestamp": entry.timestamp.isoformat(),
            })
        last_audit_len = len(state.audit_trace)

        if state.status in terminal:
            yield _sse_event({
                "event": "completed",
                "investigation_id": investigation_id,
                "status": current_status,
                "escalation": state.escalation,
                "root_cause_confirmed": state.root_cause_final is not None,
            })
            return

        await asyncio.sleep(poll_interval)

    yield _sse_event({
        "event": "timeout",
        "investigation_id": investigation_id,
        "message": "SSE stream timed out — poll GET /investigations/{id} for final result",
    })


def _sse_event(data: Dict[str, Any]) -> str:
    return f"data: {json.dumps(data)}\n\n"


# ─────────────────────────────────────────────────────────────────────────────
# GET /investigations  (list)
# ─────────────────────────────────────────────────────────────────────────────


@app.get(
    "/investigations",
    summary="List all investigation IDs",
)
async def list_investigations(
    limit: int = Query(default=50, ge=1, le=500),
) -> Dict[str, Any]:
    ids = await _store.all_ids()
    return {
        "investigation_ids": ids[-limit:],
        "total": len(ids),
    }


# ─────────────────────────────────────────────────────────────────────────────
# Health
# ─────────────────────────────────────────────────────────────────────────────


@app.get("/health", include_in_schema=False)
async def health() -> Dict[str, str]:
    return {"status": "ok", "service": "causelink-rca"}


# ─────────────────────────────────────────────────────────────────────────────
# Pipeline runner
# ─────────────────────────────────────────────────────────────────────────────


async def _run_pipeline(state: InvestigationState) -> None:
    """
    Execute the full CauseLink pipeline asynchronously.

    Steps: OntologyContextAgent → EvidenceCollectorAgent → HypothesisGeneratorAgent
           → CausalEngineAgent → RankerAgent

    Updates are persisted to the store after each step so the SSE stream
    and GET /id reflect progress in real time.
    """
    inv_id = state.investigation_input.investigation_id

    try:
        adapter = _make_adapter()

        # Inject NullEvidenceService by default; replace with real connectors
        evidence_svc = NullEvidenceService()

        # Step 1: Ontology context
        if adapter is None:
            # Without Neo4j, transition directly to INSUFFICIENT_EVIDENCE
            state.transition_to_insufficient(
                "Neo4j adapter not configured. "
                "Set NEO4J_URI, NEO4J_USER, NEO4J_PASSWORD to enable ontology loading."
            )
            await _store.put(state)
            return

        state = OntologyContextAgent(adapter=adapter).run(state)
        await _store.put(state)
        if state.status == InvestigationStatus.INSUFFICIENT_EVIDENCE:
            return

        # Step 2: Evidence collection
        state = EvidenceCollectorAgent(evidence_service=evidence_svc).run(state)
        await _store.put(state)

        # Step 3: Hypothesis generation (pattern-first)
        state = HypothesisGeneratorAgent().run(state)
        await _store.put(state)

        # Step 4: Causal DAG
        state = CausalEngineAgent(adapter=adapter).run(state)
        await _store.put(state)

        # Step 5: Ranking + confirmation
        state = RankerAgent().run(state)
        await _store.put(state)

    except Exception as exc:
        logger.exception("Pipeline error for investigation %s: %s", inv_id, exc)
        state.status = InvestigationStatus.ERROR
        state.escalation = True
        state.escalation_reason = f"Pipeline error: {exc}"
        await _store.put(state)


# ─────────────────────────────────────────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────────────────────────────────────────


async def _require_state(investigation_id: str) -> InvestigationState:
    state = await _store.get(investigation_id)
    if state is None:
        raise HTTPException(
            status_code=404,
            detail=f"Investigation '{investigation_id}' not found.",
        )
    return state


def _to_summary(state: InvestigationState) -> InvestigationSummaryResponse:
    inv = state.investigation_input
    return InvestigationSummaryResponse(
        investigation_id=inv.investigation_id,
        status=state.status.value,
        anchor_type=inv.anchor.anchor_type,
        anchor_value=inv.anchor.anchor_primary_value,
        created_at=state.created_at.isoformat(),
        updated_at=state.updated_at.isoformat(),
        escalation=state.escalation,
        root_cause_confirmed=state.root_cause_final is not None,
        root_cause_summary=(
            state.root_cause_final.description if state.root_cause_final else None
        ),
        missing_evidence_count=len(state.missing_evidence),
        hypothesis_count=len(state.hypotheses),
    )


def _to_result(state: InvestigationState) -> InvestigationResultResponse:
    inv = state.investigation_input
    insuf = (
        state.insufficient_evidence_report()
        if state.root_cause_final is None
        and state.status in (
            InvestigationStatus.INSUFFICIENT_EVIDENCE,
            InvestigationStatus.ESCALATED,
        )
        else None
    )
    return InvestigationResultResponse(
        investigation_id=inv.investigation_id,
        status=state.status.value,
        anchor_type=inv.anchor.anchor_type,
        anchor_value=inv.anchor.anchor_primary_value,
        created_at=state.created_at.isoformat(),
        updated_at=state.updated_at.isoformat(),
        escalation=state.escalation,
        escalation_reason=state.escalation_reason,
        root_cause_final=(
            state.root_cause_final.model_dump() if state.root_cause_final else None
        ),
        root_cause_candidates=[c.model_dump() for c in state.root_cause_candidates],
        hypotheses=[h.model_dump() for h in state.hypotheses],
        missing_evidence=[m.model_dump() for m in state.missing_evidence],
        recommended_actions=state.recommended_actions,
        causal_graph_edges_count=len(state.causal_graph_edges),
        causal_graph_node_count=len(state.causal_graph_node_ids),
        ontology_paths_count=len(state.ontology_paths_used),
        insufficient_evidence_report=insuf,
    )


# ─────────────────────────────────────────────────────────────────────────────
# RCA Workspace routes  (/rca/*)
# ─────────────────────────────────────────────────────────────────────────────


from causelink.rca.models import ChatRcaResponse, IncidentCard, JobInvestigationRequest  # noqa: E402
from causelink.rca.orchestrator import ChatRcaOrchestrator  # noqa: E402
from causelink.rca.scenario_config import SCENARIOS  # noqa: E402
from causelink.rca.session import get_session_store  # noqa: E402

_rca_orchestrator = ChatRcaOrchestrator(mock_mode=True)


@app.post(
    "/rca/chat/investigate",
    response_model=ChatRcaResponse,
    status_code=200,
    summary="Run or continue a chat-driven RCA investigation for a job",
)
async def rca_investigate(body: JobInvestigationRequest) -> ChatRcaResponse:
    """
    Start a new investigation or answer a follow-up query against an existing session.

    First call (session_id=None): runs the full 7-stage pipeline and returns the
    investigation result with an incident card and dashboard link.

    Subsequent calls (same session_id or job_id, refresh=False): answers the
    user_query from stored session data without re-running the pipeline.
    """
    try:
        return _rca_orchestrator.investigate(body)
    except (ValueError, KeyError) as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except Exception as exc:
        logger.exception("RCA investigation error: %s", exc)
        raise HTTPException(status_code=500, detail=f"Investigation error: {exc}") from exc


@app.get(
    "/rca/sessions/{session_id}",
    summary="Get an RCA session by session_id",
)
async def rca_get_session(
    session_id: str = Path(..., description="Session ID returned by /rca/chat/investigate"),
) -> Dict[str, Any]:
    store = get_session_store()
    sess = store.get(session_id)
    if sess is None:
        raise HTTPException(status_code=404, detail=f"Session '{session_id}' not found.")
    return sess.model_dump(mode="json")


@app.get(
    "/rca/jobs/{job_id}/dashboard",
    response_model=RcaDashboardSummary,
    summary="Get the latest RCA dashboard summary for a job by job_id",
)
async def rca_job_dashboard(
    job_id: str = Path(..., description="Job identifier used in POST /rca/chat/investigate"),
) -> RcaDashboardSummary:
    store = get_session_store()
    sess = store.get_by_job(job_id)
    if sess is None:
        raise HTTPException(
            status_code=404,
            detail=f"No investigation session found for job '{job_id}'. "
                   "Run POST /rca/chat/investigate first.",
        )
    if sess.latest_summary is None:
        raise HTTPException(
            status_code=409,
            detail=f"Session for job '{job_id}' exists but no dashboard summary has been "
                   "generated yet. The investigation may still be in progress.",
        )
    summary = RcaDashboardSummary(**sess.latest_summary)
    summary.session_id = sess.session_id
    summary.dashboard_url = sess.dashboard_url
    summary.incident_card_data = sess.latest_incident_card
    return summary


@app.get(
    "/rca/jobs/{job_id}/chat-context",
    summary="Get the chat context for a job (session metadata + last summary)",
)
async def rca_job_chat_context(
    job_id: str = Path(...),
) -> Dict[str, Any]:
    store = get_session_store()
    sess = store.get_by_job(job_id)
    if sess is None:
        raise HTTPException(status_code=404, detail=f"No session found for job '{job_id}'.")
    return {
        "session_id": sess.session_id,
        "job_id": sess.job_id,
        "scenario_id": sess.scenario_id,
        "status": sess.status,
        "dashboard_url": sess.dashboard_url,
        "job_status": sess.context.get("job_status", "UNKNOWN"),
        "problem_type": sess.context.get("problem_type"),
        "control_triggered": sess.context.get("control_triggered"),
        "confidence": sess.context.get("confidence"),
        "created_at": sess.created_at.isoformat(),
        "updated_at": sess.updated_at.isoformat(),
    }


@app.get(
    "/rca/scenarios",
    summary="List the 5 available control scenarios",
)
async def rca_list_scenarios() -> Dict[str, Any]:
    return {
        "scenarios": [s.model_dump() for s in SCENARIOS],
        "total": len(SCENARIOS),
    }


@app.post(
    "/rca/sessions/{session_id}/refresh",
    response_model=ChatRcaResponse,
    status_code=200,
    summary="Force-refresh an existing RCA session (re-runs all pipeline stages)",
)
async def rca_refresh_session(
    session_id: str = Path(...),
    body: Optional[dict] = None,
) -> ChatRcaResponse:
    store = get_session_store()
    sess = store.get(session_id)
    if sess is None:
        raise HTTPException(status_code=404, detail=f"Session '{session_id}' not found.")
    req = JobInvestigationRequest(
        scenario_id=sess.scenario_id,
        job_id=sess.job_id,
        user_query="",
        refresh=True,
        session_id=session_id,
    )
    try:
        return _rca_orchestrator.investigate(req)
    except Exception as exc:
        logger.exception("Session refresh error: %s", exc)
        raise HTTPException(status_code=500, detail=f"Refresh error: {exc}") from exc


# ─────────────────────────────────────────────────────────────────────────────
# Entry point
# ─────────────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    uvicorn.run("causelink_api:app", host="0.0.0.0", port=8001, reload=True)

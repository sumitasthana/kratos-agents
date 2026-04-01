"""
server.py
FastAPI HTTP server for the Kratos multi-agent RCA pipeline.

Endpoints
---------
GET  /health                       — liveness probe
POST /rca/run                      — start a pipeline run (returns RCAReport)
GET  /rca/run/{run_id}             — get a cached run result
GET  /tools                        — list registered tools
GET  /agents                       — list registered agents

Run (development)
-----------------
    python server.py
    # or
    uvicorn server:app --host 0.0.0.0 --port 8001 --reload

Environment variables
---------------------
    OPENAI_API_KEY     — required for real LLM calls
    BANK_API_URL       — base URL for BankPipelineConnector (default: http://localhost:8080)
    BANK_API_TOKEN     — bearer token for the bank API (optional)
"""
from __future__ import annotations

import asyncio
import json
import logging
import os
import time
import uuid
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

# Load .env before anything else so OPENAI_API_KEY is in os.environ
try:
    from dotenv import load_dotenv
    load_dotenv(dotenv_path=os.path.join(os.path.dirname(__file__), ".env"), override=False)
except ImportError:
    pass  # python-dotenv not installed; rely on shell environment

import httpx
import uvicorn
from fastapi import FastAPI, HTTPException, BackgroundTasks, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field

from agents import register_all_agents
from agents.orchestrator.orchestrator import KratosOrchestrator
from connectors.bank_pipeline import BankPipelineConnector
from core.llm import LLMConfig, get_llm, _call_llm_async
from tools import register_all_tools, TOOL_REGISTRY
from workflow.pipeline_phases import RCAReport

# ---------------------------------------------------------------------------
# Logging
# ---------------------------------------------------------------------------

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s — %(message)s",
)
logger = logging.getLogger("kratos.server")

# ---------------------------------------------------------------------------
# FastAPI app
# ---------------------------------------------------------------------------

app = FastAPI(
    title="Kratos RCA API",
    description=(
        "Multi-agent Root Cause Analysis for Spark, Airflow, data quality, "
        "code changes, and GRC compliance.\n\n"
        "**POST /rca/run** to start a pipeline run."
    ),
    version="1.0.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ---------------------------------------------------------------------------
# In-memory run store
# ---------------------------------------------------------------------------

_run_store: Dict[str, Dict[str, Any]] = {}


# ---------------------------------------------------------------------------
# Request / response schemas
# ---------------------------------------------------------------------------

class RunRequest(BaseModel):
    incident_id: str = Field(..., description="Incident identifier (e.g. INC-DEP-001)")
    metadata: Optional[Dict[str, Any]] = Field(
        default=None,
        description=(
            "Optional extra fingerprint data to inject into the pipeline "
            "(spark_metrics, data_profile, airflow_logs, etc.)"
        ),
    )


class RunResponse(BaseModel):
    run_id: str
    incident_id: str
    status: str
    started_at: str
    phases_executed: List[str] = []
    final_root_cause: Optional[str] = None
    evidence_count: int = 0
    recommendation_count: int = 0
    duration_seconds: Optional[float] = None
    error: Optional[str] = None


# ---------------------------------------------------------------------------
# Dependency: build orchestrator once per request
# ---------------------------------------------------------------------------

def _make_orchestrator(metadata: Optional[Dict[str, Any]] = None) -> KratosOrchestrator:
    bank_url   = os.environ.get("BANK_API_URL", "http://localhost:8080")
    bank_token = os.environ.get("BANK_API_TOKEN", "")

    connector = BankPipelineConnector(base_url=bank_url, token=bank_token)

    cfg = LLMConfig()
    llm = get_llm(cfg)

    tool_reg  = register_all_tools(cfg)
    agent_reg = register_all_agents()

    # Inject caller-supplied metadata as graph_state so it flows into
    # IncidentContext.metadata via the INTAKE phase.
    graph_state = metadata or {}

    return KratosOrchestrator(
        connector=connector,
        llm=llm,
        graph_state=graph_state,
        tool_registry=tool_reg,
        agent_registry=agent_reg,
    )


# ---------------------------------------------------------------------------
# Background runner
# ---------------------------------------------------------------------------

async def _run_pipeline(run_id: str, incident_id: str, metadata: Optional[Dict[str, Any]]) -> None:
    _run_store[run_id]["status"] = "running"
    try:
        orch = _make_orchestrator(metadata)
        report: RCAReport = await orch.run(incident_id)
        _run_store[run_id].update(
            status="completed",
            phases_executed=report.phases_executed,
            final_root_cause=report.final_root_cause,
            evidence_count=len(report.evidence),
            recommendation_count=len(report.recommendations),
            duration_seconds=report.duration_seconds,
            report=report.model_dump(),
        )
        logger.info(
            "Run %s completed in %.2fs — %d evidence, %d recs",
            run_id,
            report.duration_seconds or 0,
            len(report.evidence),
            len(report.recommendations),
        )
    except Exception as exc:
        logger.exception("Run %s failed: %s", run_id, exc)
        _run_store[run_id].update(status="failed", error=str(exc))


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------

@app.get("/health", tags=["meta"])
def health() -> Dict[str, str]:
    return {"status": "ok", "service": "kratos-rca", "version": "1.0.0"}


# ---------------------------------------------------------------------------
# Incidents proxy — forwards to My_Bank API, falls back to mock data
# ---------------------------------------------------------------------------

_MOCK_INCIDENTS = [
    {
        "incident_id": "INC-4491",
        "id": "INC-4491",
        "service": "DepositInsurance-Pipeline",
        "severity": "P1",
        "error": "Control CTRL-007 failed: aggregation bypass",
        "job": "nightly_batch",
        "status": "active",
        "timestamp": "2025-03-16T13:39:00Z",
    },
    {
        "incident_id": "INC-4488",
        "id": "INC-4488",
        "service": "TrustCustody-ORC",
        "severity": "P1",
        "error": "IRR misclassification: ORC fallthrough to SGL",
        "job": "trust_processing",
        "status": "investigating",
        "timestamp": "2025-03-16T11:22:00Z",
    },
    {
        "incident_id": "INC-4485",
        "id": "INC-4485",
        "service": "WireTransfer-MT202",
        "severity": "P2",
        "error": "MT202 message handler missing",
        "job": "wire_settlement",
        "status": "investigating",
        "timestamp": "2025-03-16T09:05:00Z",
    },
]


_SYSTEM_LABELS = {
    "legacy_deposit": "DepositInsurance-Pipeline",
    "trust_custody": "TrustCustody-ORC",
    "wire_transfer": "WireTransfer-MT202",
}

_STATUS_MAP = {
    "OPEN": "active",
    "IN_PROGRESS": "investigating",
    "RCA_COMPLETE": "resolved",
}

# ── 6 primary demo controls (one per scenario) ──────────────────────
# Only these are shown in the sidebar for a clean demo.
_DEMO_CONTROLS = {
    "CTL-DEP-001",    # SCN-001 Deposit Aggregation Failure
    "CTL-TRUST-001",  # SCN-002 IRR Trust ORC Misclassification
    "CTL-WIRE-001",   # SCN-003 OFAC Screening Bypass
    "CTL-WIRE-004",   # SCN-004 Stale ACH Wire Pending
    "CTL-DEP-005",    # SCN-005 JNT Missing Second Owner
    "CTL-TRUST-003",  # SCN-006 EBP Coverage Overstatement
}


@app.get("/incidents", tags=["incidents"])
async def list_incidents():
    """Proxy to My_Bank API /incidents, falling back to mock data.

    Filters to the 6 primary demo controls for a clean sidebar.
    """
    bank_url = os.environ.get("BANK_API_URL", "http://localhost:8080")
    try:
        async with httpx.AsyncClient(timeout=5.0) as client:
            resp = await client.get(f"{bank_url}/incidents")
            if resp.status_code == 200:
                raw = resp.json()
                # De-duplicate: keep only the latest incident per control_id
                seen: dict[str, dict] = {}
                for item in raw:
                    ctl = item.get("control_id", "")
                    if ctl not in _DEMO_CONTROLS:
                        continue
                    # Keep latest by created_at
                    existing = seen.get(ctl)
                    if not existing or item.get("created_at", "") > existing.get("created_at", ""):
                        seen[ctl] = item
                mapped = []
                for item in seen.values():
                    sys_key = item.get("source_system", "")
                    mapped.append({
                        "id": item.get("incident_id", ""),
                        "service": _SYSTEM_LABELS.get(sys_key, sys_key),
                        "severity": item.get("severity", "P3"),
                        "error": item.get("title", item.get("control_id", "")),
                        "job": item.get("stage", ""),
                        "status": _STATUS_MAP.get(item.get("status", ""), "investigating"),
                        "timestamp": item.get("created_at", ""),
                        "control_id": item.get("control_id", ""),
                        "source_system": sys_key,
                    })
                # Sort: P1 first, then P2, P3
                mapped.sort(key=lambda x: (x["severity"], x["error"]))
                return mapped
    except Exception as exc:
        logger.debug("My_Bank /incidents unavailable (%s) — using mock data", exc)
    return _MOCK_INCIDENTS


@app.get("/tools", tags=["meta"])
def list_tools() -> Dict[str, Any]:
    """Return the registered tool names and their JSON schemas."""
    # TOOL_REGISTRY is populated after register_all_tools() is first called.
    # Re-register here in case the registry is empty (server cold-start).
    if not TOOL_REGISTRY:
        register_all_tools(LLMConfig())
    return {
        name: tool.schema()
        for name, tool in TOOL_REGISTRY.items()
    }


@app.get("/agents", tags=["meta"])
def list_agents() -> List[str]:
    """Return the names of registered agents."""
    return list(register_all_agents().keys())


@app.post("/rca/run", response_model=RunResponse, status_code=202, tags=["rca"])
async def start_run(body: RunRequest, background_tasks: BackgroundTasks) -> RunResponse:
    """
    Start an RCA pipeline run for the given incident_id.

    The pipeline executes asynchronously in the background.
    Poll **GET /rca/run/{run_id}** to retrieve results.
    """
    run_id = str(uuid.uuid4())
    started_at = datetime.now(timezone.utc).isoformat()

    _run_store[run_id] = {
        "run_id": run_id,
        "incident_id": body.incident_id,
        "status": "queued",
        "started_at": started_at,
        "phases_executed": [],
        "final_root_cause": None,
        "evidence_count": 0,
        "recommendation_count": 0,
        "duration_seconds": None,
        "error": None,
    }

    background_tasks.add_task(_run_pipeline, run_id, body.incident_id, body.metadata)
    logger.info("Queued run %s for incident %s", run_id, body.incident_id)

    return RunResponse(
        run_id=run_id,
        incident_id=body.incident_id,
        status="queued",
        started_at=started_at,
    )


@app.post("/rca/run/sync", response_model=RunResponse, tags=["rca"])
async def run_sync(body: RunRequest) -> RunResponse:
    """
    Start an RCA pipeline run and wait for it to complete (synchronous).

    Suitable for local testing.  Use the async endpoint for production.
    """
    run_id = str(uuid.uuid4())
    started_at = datetime.now(timezone.utc).isoformat()

    _run_store[run_id] = {
        "run_id": run_id,
        "incident_id": body.incident_id,
        "status": "running",
        "started_at": started_at,
    }

    await _run_pipeline(run_id, body.incident_id, body.metadata)
    rec = _run_store[run_id]

    return RunResponse(
        run_id=run_id,
        incident_id=body.incident_id,
        status=rec.get("status", "unknown"),
        started_at=started_at,
        phases_executed=rec.get("phases_executed", []),
        final_root_cause=rec.get("final_root_cause"),
        evidence_count=rec.get("evidence_count", 0),
        recommendation_count=rec.get("recommendation_count", 0),
        duration_seconds=rec.get("duration_seconds"),
        error=rec.get("error"),
    )


@app.get("/rca/run/{run_id}", tags=["rca"])
def get_run(run_id: str) -> Dict[str, Any]:
    """
    Retrieve the current status and results of a pipeline run.
    """
    rec = _run_store.get(run_id)
    if rec is None:
        raise HTTPException(status_code=404, detail=f"Run {run_id!r} not found")
    return rec


@app.get("/rca/runs", tags=["rca"])
def list_runs() -> List[Dict[str, Any]]:
    """List all run summaries (most recent first)."""
    return [
        {k: v for k, v in rec.items() if k != "report"}
        for rec in reversed(list(_run_store.values()))
    ]


# ---------------------------------------------------------------------------
# WebSocket — live RCA stream
# ---------------------------------------------------------------------------

# Canonical demo sequence for the deposit_aggregation_failure scenario.
# Schema matches the TypeScript RcaMessage union types exactly.
def _build_demo_messages(incident_id: str) -> List[Dict[str, Any]]:
    t = int(time.time() * 1000)
    return [
        {
            "id": "m1", "type": "system", "phase": "INTAKE", "timestamp": t,
            "text": f"Incident {incident_id} loaded. 2 of 21 controls failed.",
        },
        {
            "id": "m2", "type": "agent", "phase": "INTAKE", "timestamp": t,
            "agent": "Orchestrator",
            "text": (
                "Seeding ontology graph. CTRL-007 failed on nightly_batch run. "
                "Regulation: 12 CFR §330.1(b). Starting trace."
            ),
        },
        {
            "id": "m3", "type": "hop", "phase": "INTAKE", "timestamp": t,
            "hops": [
                {"from": "System:legacy_deposit", "edge": "RUNS_JOB",    "to": "Job:nightly_batch"},
                {"from": "Job:nightly_batch",      "edge": "EXECUTES",   "to": "Pipeline:deposit_insurance"},
                {"from": "Pipeline:deposit_insurance", "edge": "GOVERNED_BY", "to": "Regulation:12CFR330"},
                {"from": "Regulation:12CFR330",    "edge": "MANDATES",   "to": "ControlObjective:CTRL-007"},
            ],
        },
        {
            "id": "m4", "type": "agent", "phase": "LOGS_FIRST", "timestamp": t,
            "agent": "SparkLogTool", "tag": "evidence",
            "text": (
                "Aggregation stage: 0 records output. Insurance calc consumed raw_deposits "
                "directly — 847,231 rows bypassed aggregation."
            ),
        },
        {
            "id": "m5", "type": "agent", "phase": "LOGS_FIRST", "timestamp": t,
            "agent": "AirflowLogTool", "tag": "evidence",
            "text": (
                "Task 'run_aggregation' SKIPPED — JCL flag check resolved WS-SKIP-AGG=Y. "
                "Downstream tasks proceeded without aggregated input."
            ),
        },
        {
            "id": "m6", "type": "agent", "phase": "ROUTE", "timestamp": t,
            "agent": "RoutingAgent",
            "text": (
                "Pattern identified: configuration_bypass (confidence 0.92). "
                "Dispatching: GitDiffTool, DataProfiler, DDLDiffTool."
            ),
        },
        {
            "id": "m7", "type": "evidence", "phase": "BACKTRACK", "timestamp": t,
            "source": "GitDiffTool", "filename": "deposit_agg.cbl",
            "language": "COBOL", "defect": "DEF-AGG-001",
            "code": (
                "000142* AGGREGATION CONTROL FLAG\n"
                "000143  05 WS-SKIP-AGG PIC X(1) VALUE 'Y'. *> CHANGED\n"
                "000144* Commit: a3f7c2 by ops-automation\n"
                "000145* \"disable aggregation for performance testing\""
            ),
        },
        {
            "id": "m8", "type": "hop", "phase": "BACKTRACK", "timestamp": t,
            "hops": [
                {"from": "Pipeline:deposit_insurance", "edge": "USES_SCRIPT",          "to": "Script:deposit_agg.cbl"},
                {"from": "Script:deposit_agg.cbl",     "edge": "CHANGED_BY",           "to": "CodeEvent:commit_a3f7c2"},
                {"from": "Script:deposit_agg.cbl",     "edge": "TYPICALLY_IMPLEMENTS", "to": "Transformation:deposit_aggregation"},
                {"from": "Rule:AGG_RULE_001",           "edge": "ENFORCED_BY",          "to": "Transformation:deposit_aggregation"},
            ],
        },
        {
            "id": "m9", "type": "agent", "phase": "BACKTRACK", "timestamp": t,
            "agent": "DataProfiler", "tag": "finding",
            "text": (
                "aggregated_deposits = 847,231 rows (expected ~312K). "
                "147,892 depositors affected. Estimated excess FDIC coverage: ~$12.3B."
            ),
        },
        {
            "id": "m10", "type": "triangulation", "phase": "INCIDENT_CARD", "timestamp": t,
            "confidence": 0.97,
            "rootCause": (
                "CodeEvent commit_a3f7c2 set WS-SKIP-AGG=Y in deposit_agg.cbl, "
                "disabling deposit aggregation. Insurance calculated on raw deposits "
                "— 847K rows vs expected 312K."
            ),
            "regulation": "12 CFR §330.1(b)",
            "defect": "DEF-AGG-001",
        },
        {
            "id": "m11", "type": "recommendation", "phase": "RECOMMEND", "timestamp": t,
            "items": [
                {
                    "priority": "P1",
                    "action": "Revert WS-SKIP-AGG=Y to N in deposit_agg.cbl and rerun nightly_batch",
                    "owner": "John Chen", "effort": "2 hr", "regulation": "§330.1(b)",
                },
                {
                    "priority": "P1",
                    "action": "Reprocess 147,892 depositor records and recalculate FDIC coverage",
                    "owner": "Maria Santos", "effort": "4 hr", "regulation": "§330.1(b)",
                },
                {
                    "priority": "P2",
                    "action": "Add pre-production gate blocking JCL changes to controls marked blocking",
                    "owner": "Alex Kim", "effort": "2 days",
                },
            ],
        },
        {
            "id": "m12", "type": "system", "phase": "PERSIST", "timestamp": t,
            "text": "RCA complete. 7 phases, 47s elapsed, 15 ontology nodes traversed, 5 evidence objects, 3 recommendations.",
        },
    ]


def _build_chat_context(report_data: dict, incident_id: str) -> str:
    """Build a system prompt summarising the RCA report for follow-up queries."""
    root_cause = report_data.get("final_root_cause", "N/A")
    evidence = report_data.get("evidence", [])
    recommendations = report_data.get("recommendations", [])
    issue_profiles = report_data.get("issue_profiles", [])

    ev_lines = "\n".join(
        f"  - {e.get('source', 'Unknown')}: {str(e.get('content', e))[:200]}"
        for e in evidence[:8]
    )
    rec_lines = "\n".join(
        f"  - [{r.get('priority', 'P2')}] {str(r.get('action', r))[:200]}"
        for r in recommendations[:6]
    )
    prof_lines = "\n".join(
        f"  - {str(p.get('description', p))[:200]}"
        for p in issue_profiles[:4]
    )

    return (
        f"You are Kratos, a Root Cause Analysis assistant for FDIC deposit insurance compliance. "
        f"You have just completed an RCA investigation for incident {incident_id}.\n\n"
        f"ROOT CAUSE:\n  {root_cause}\n\n"
        f"EVIDENCE:\n{ev_lines or '  (none)'}\n\n"
        f"ISSUE PROFILES:\n{prof_lines or '  (none)'}\n\n"
        f"RECOMMENDATIONS:\n{rec_lines or '  (none)'}\n\n"
        f"Answer the user's follow-up questions about this investigation. "
        f"Be concise (3-5 sentences max). Cite specific evidence or defect IDs when relevant. "
        f"If a question is outside the scope of this investigation, say so."
    )


# Demo-mode context for follow-up queries (mirrors _build_demo_messages content)
_DEMO_CHAT_CONTEXT = (
    "You are Kratos, a Root Cause Analysis assistant for FDIC deposit insurance compliance. "
    "You have just completed an RCA investigation for a deposit aggregation failure.\n\n"
    "ROOT CAUSE:\n  CodeEvent commit_a3f7c2 set WS-SKIP-AGG=Y in deposit_agg.cbl, "
    "disabling deposit aggregation. Insurance calculated on raw deposits — 847K rows vs expected 312K.\n\n"
    "EVIDENCE:\n"
    "  - SparkLogTool: Aggregation stage 0 records output, 847,231 rows bypassed aggregation\n"
    "  - AirflowLogTool: Task run_aggregation SKIPPED — JCL flag WS-SKIP-AGG=Y\n"
    "  - GitDiffTool: deposit_agg.cbl line 143, WS-SKIP-AGG changed to Y by ops-automation (commit a3f7c2)\n"
    "  - DataProfiler: 147,892 depositors affected, excess FDIC coverage ~$12.3B\n\n"
    "DEFECT: DEF-AGG-001\n"
    "REGULATION: 12 CFR §330.1(b)\n"
    "CONTROLS FAILED: CTRL-007 on nightly_batch run (2 of 21 controls failed)\n\n"
    "RECOMMENDATIONS:\n"
    "  - [P1] Revert WS-SKIP-AGG=Y to N in deposit_agg.cbl and rerun nightly_batch (owner: John Chen, 2hr)\n"
    "  - [P1] Reprocess 147,892 depositor records and recalculate FDIC coverage (owner: Maria Santos, 4hr)\n"
    "  - [P2] Add pre-production gate blocking JCL changes to controls marked blocking (owner: Alex Kim, 2 days)\n\n"
    "Answer the user's follow-up questions about this investigation. "
    "Be concise (3-5 sentences max). Cite specific evidence or defect IDs when relevant."
)


async def _chat_loop(
    websocket: WebSocket,
    system_prompt: str,
    llm_config: LLMConfig,
    incident_id: str,
) -> None:
    """
    Keep the WebSocket open and answer follow-up questions using the LLM.
    Runs until the client disconnects or an error occurs.
    """
    def _ts() -> int:
        return int(time.time() * 1000)

    def _mid() -> str:
        return str(uuid.uuid4())[:8]

    async def _send(msg: dict) -> None:
        await websocket.send_text(json.dumps(msg, default=str))

    while True:
        raw = await asyncio.wait_for(websocket.receive_text(), timeout=3600.0)
        cmd = json.loads(raw)
        query = cmd.get("query", "").strip()
        if not query:
            continue

        logger.info("[WS /ws] chat query: %s", query[:120])

        try:
            answer = await _call_llm_async(
                system_prompt=system_prompt,
                user_prompt=query,
                llm_config=llm_config,
                agent_name="KratosChat",
            )
        except Exception as llm_exc:
            logger.exception("[WS /ws] LLM error: %s", llm_exc)
            answer = f"I encountered an error processing your question: {llm_exc}"

        await _send({
            "id": _mid(),
            "type": "agent",
            "phase": "PERSIST",
            "timestamp": _ts(),
            "agent": "Kratos",
            "text": answer,
            "tag": "info",
        })


@app.websocket("/ws")
async def ws_rca(websocket: WebSocket) -> None:
    """
    WebSocket endpoint consumed by the dashboard chat.

    Protocol
    --------
    Client sends:   {"incident_id": "<id>"}          (or {"type":"start_trace","incident_id":"<id>"})
    Server replies: stream of RcaMessage JSON objects (see TypeScript types/index.ts)
    After pipeline: WS stays open for follow-up chat queries
                    Client sends: {"type":"chat","query":"..."}
                    Server replies: agent message with LLM answer

    Mode selection
    --------------
    - Demo mode  : OPENAI_API_KEY is not set → streams canonical 12-message mock at 800 ms/msg,
                   then enters chat loop with demo context
    - Real mode  : API key present → runs KratosOrchestrator, streams live results,
                   then enters chat loop with full report context
    """
    await websocket.accept()

    def _ts() -> int:
        return int(time.time() * 1000)

    def _mid() -> str:
        return str(uuid.uuid4())[:8]

    async def _send(msg: dict) -> None:
        await websocket.send_text(json.dumps(msg, default=str))

    try:
        # Wait for the start command (30 s idle timeout)
        raw = await asyncio.wait_for(websocket.receive_text(), timeout=30.0)
        cmd = json.loads(raw)
        incident_id: str = cmd.get("incident_id", "INC-UNKNOWN")
        client_mode: str = cmd.get("mode", "rca")   # "rca" | "chat"
        logger.info("[WS /ws] incident=%s mode=%s", incident_id, client_mode)

        llm_config = LLMConfig()
        demo_mode = not bool(os.environ.get("OPENAI_API_KEY", "").strip())

        # ── Chat-only mode: skip pipeline, go straight to chat ────────────
        if client_mode == "chat":
            logger.info("[WS /ws] chat-only mode — entering chat loop")
            await _send({
                "id": _mid(), "type": "system", "phase": "PERSIST", "timestamp": _ts(),
                "text": f"Connected to incident {incident_id}. Ask anything about this investigation.",
            })
            await _chat_loop(websocket, _DEMO_CHAT_CONTEXT, llm_config, incident_id)
            return

        if demo_mode:
            logger.info("[WS /ws] demo mode — streaming mock messages")
            for msg in _build_demo_messages(incident_id):
                await _send(msg)
                await asyncio.sleep(0.8)

            # Stay open for follow-up chat queries (demo context)
            logger.info("[WS /ws] demo mode — entering chat loop")
            await _chat_loop(websocket, _DEMO_CHAT_CONTEXT, llm_config, incident_id)
            return

        # ── Real mode: run orchestrator ──────────────────────────────────────
        logger.info("[WS /ws] real mode — running orchestrator")

        await _send({
            "id": _mid(), "type": "system", "phase": "INTAKE", "timestamp": _ts(),
            "text": f"Incident {incident_id} loaded. Starting Kratos RCA pipeline …",
        })
        await asyncio.sleep(0.3)
        await _send({
            "id": _mid(), "type": "agent", "phase": "INTAKE", "timestamp": _ts(),
            "agent": "Orchestrator",
            "text": "Seeding evidence graph. Fetching incident context and initialising 7-phase pipeline.",
        })

        orch = _make_orchestrator({})

        # Run the pipeline while sending keepalive heartbeats every 2 s.
        pipeline_task = asyncio.create_task(orch.run(incident_id))
        phase_labels = ["LOGS_FIRST", "ROUTE", "BACKTRACK", "INCIDENT_CARD", "RECOMMEND"]
        keepalive_idx = 0
        while not pipeline_task.done():
            await asyncio.sleep(2.0)
            if pipeline_task.done():
                break
            label = phase_labels[keepalive_idx % len(phase_labels)]
            keepalive_idx += 1
            logger.info("[WS /ws] keepalive #%d — pipeline still running", keepalive_idx)
            try:
                await _send({
                    "id": _mid(), "type": "system", "phase": label,
                    "timestamp": _ts(),
                    "text": f"Pipeline running — {label.replace('_', ' ').title()} …",
                })
            except Exception:
                logger.warning("[WS /ws] keepalive send failed — client disconnected")
                break
        report: RCAReport = await pipeline_task

        def _as_dict(obj: Any) -> dict:
            if isinstance(obj, dict):
                return obj
            if hasattr(obj, "model_dump"):
                return obj.model_dump()
            return vars(obj) if hasattr(obj, "__dict__") else {"value": str(obj)}

        # ── Stream results to the client ────────────────────────────────
        # Wrapped in try/except so a mid-stream disconnect doesn't crash
        # the entire handler — we still want to build chat context.
        logger.info("[WS /ws] streaming %d evidence, %d profiles, %d recs to client",
                     len(report.evidence), len(report.issue_profiles), len(report.recommendations))

        # Build ALL messages first, then send them in a single burst.
        # This eliminates the streaming window where the client can disconnect.
        stream_msgs: list[dict] = []

        # LOGS_FIRST — evidence items
        for ev in report.evidence[:6]:
            d = _as_dict(ev)
            stream_msgs.append({
                "id": _mid(), "type": "agent", "phase": "LOGS_FIRST", "timestamp": _ts(),
                "agent": str(d.get("source_tool", d.get("source", "Tool"))),
                "tag": "evidence",
                "text": str(d.get("description", d.get("content", d)))[:350],
            })

        # ROUTE
        stream_msgs.append({
            "id": _mid(), "type": "agent", "phase": "ROUTE", "timestamp": _ts(),
            "agent": "RoutingAgent",
            "text": "Routing analysis complete. Dispatching to triangulation.",
        })

        # BACKTRACK — issue profiles
        for prof in report.issue_profiles[:3]:
            d = _as_dict(prof)
            stream_msgs.append({
                "id": _mid(), "type": "agent", "phase": "BACKTRACK", "timestamp": _ts(),
                "agent": "TriangulationAgent", "tag": "finding",
                "text": str(d.get("description", d))[:350],
            })

        # INCIDENT_CARD — triangulation
        card = report.metadata.get("incident_card", {}) if report.metadata else {}
        root_cause = report.final_root_cause or card.get("primary_root_cause", "Root cause analysis complete.")
        regs = card.get("affected_regulations", ["N/A"])
        reg_str = regs[0] if isinstance(regs, list) and regs else str(regs)
        stream_msgs.append({
            "id": _mid(), "type": "triangulation", "phase": "INCIDENT_CARD", "timestamp": _ts(),
            "confidence": 0.92,
            "rootCause": root_cause,
            "regulation": reg_str,
            "defect": f"DEF-{incident_id[-4:].upper()}",
        })

        # RECOMMEND
        items = []
        for rec in report.recommendations[:4]:
            d = _as_dict(rec)
            items.append({
                "priority": str(d.get("priority", "P2")),
                "action": str(d.get("action", d))[:250],
                "owner": str(d.get("owner", "Engineering Team")),
                "effort": str(d.get("effort", "TBD")),
                "regulation": str(d.get("regulation", "")),
            })
        if items:
            stream_msgs.append({
                "id": _mid(), "type": "recommendation", "phase": "RECOMMEND",
                "timestamp": _ts(), "items": items,
            })

        # PERSIST
        stream_msgs.append({
            "id": _mid(), "type": "system", "phase": "PERSIST", "timestamp": _ts(),
            "text": (
                f"RCA complete. {len(report.phases_executed)} phases, "
                f"{int(report.duration_seconds or 0)}s elapsed, "
                f"{len(report.evidence)} evidence objects, "
                f"{len(report.recommendations)} recommendations."
            ),
        })

        # Send all messages in one burst — no await sleep between them
        stream_ok = True
        for i, msg in enumerate(stream_msgs):
            try:
                await _send(msg)
            except Exception as send_err:
                stream_ok = False
                logger.warning("[WS /ws] send #%d/%d failed: %s (%s)",
                               i + 1, len(stream_msgs), send_err, type(send_err).__name__)
                break
        if stream_ok:
            logger.info("[WS /ws] all %d messages sent — preparing chat loop", len(stream_msgs))
        else:
            logger.warning("[WS /ws] streaming interrupted at message %d/%d", i + 1, len(stream_msgs))

        # ── Chat loop: answer follow-up questions ────────────────────────────
        if not stream_ok:
            logger.warning("[WS /ws] client disconnected during streaming — skipping chat loop")
            return

        try:
            report_data = report.model_dump()
            for key in ("evidence", "recommendations", "issue_profiles"):
                report_data[key] = [
                    _as_dict(item) for item in (getattr(report, key, []) or [])
                ]
            chat_context = _build_chat_context(report_data, incident_id)
        except Exception as ctx_err:
            logger.warning("[WS /ws] chat context build failed: %s — using fallback", ctx_err)
            chat_context = _DEMO_CHAT_CONTEXT

        logger.info("[WS /ws] real mode — entering chat loop")
        await _chat_loop(websocket, chat_context, llm_config, incident_id)

    except asyncio.TimeoutError:
        await websocket.close(1008)
    except WebSocketDisconnect:
        logger.info("[WS /ws] client disconnected")
    except Exception as exc:
        logger.exception("[WS /ws] pipeline error: %s", exc)
        try:
            await _send({
                "id": str(uuid.uuid4())[:8], "type": "system", "phase": "PERSIST",
                "timestamp": int(time.time() * 1000),
                "text": f"RCA pipeline error: {exc}",
            })
            await websocket.close(1011)
        except Exception:
            pass


# ---------------------------------------------------------------------------
# Dev entrypoint
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 8001))
    logger.info("Starting Kratos RCA server on http://0.0.0.0:%d", port)
    uvicorn.run("server:app", host="0.0.0.0", port=port, reload=True,
                ws_ping_interval=None, ws_ping_timeout=None)

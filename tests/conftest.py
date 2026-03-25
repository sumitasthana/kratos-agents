"""
tests/conftest.py
Shared pytest fixtures for Kratos unit, integration, and demo tests.

Fixtures
--------
mock_llm              AsyncMock LLMClient returning canned JSON
mock_bank_api         respx router with all My_Bank endpoints mocked
incident_ctx_deposit  IncidentContext for deposit_aggregation_failure
incident_ctx_trust    IncidentContext for trust_irr_misclassification
incident_ctx_wire     IncidentContext for wire_mt202_drop
tool_registry         Dict[str, BaseTool] — all 5 tools, LLM wired to mock_llm
"""
from __future__ import annotations

import json
import random
from datetime import datetime, timezone
from typing import Any, AsyncIterator
from unittest.mock import AsyncMock, MagicMock

import pytest
import pytest_asyncio
import respx
import httpx

from core.models import (
    EvidenceObject,
    IncidentContext,
    IssueProfile,
    LineageEdge,
    LineageGraph,
    LineageNode,
    LogChunk,
    LogSource,
    Priority,
    Recommendation,
)

# ---------------------------------------------------------------------------
# Seed for determinism
# ---------------------------------------------------------------------------

random.seed(42)

# ---------------------------------------------------------------------------
# Canned LLM response payloads
# ---------------------------------------------------------------------------

_ROUTING_LLM_RESPONSE = json.dumps({
    "pattern_id": "HPL-001",
    "pattern_name": "Spark Execution Failure",
    "selected_tools": ["SparkLogTool", "DataQualityTool"],
    "rationale": "OOM signals detected in spark_metrics keys.",
    "confidence": 0.91,
})

_TRIANGULATION_LLM_RESPONSE = json.dumps({
    "root_cause_hypothesis": "AGGREGATION_SKIP: deposit aggregation step silently disabled.",
    "confidence": 0.91,
    "causal_chain": [
        "Pipeline TRIGGERED AGGREGATION_SKIP Mechanism",
        "Mechanism VIOLATES Regulation §330.1(b)",
    ],
    "contradictions": [],
    "affected_regulation": "12 CFR Part 330 §330.1(b)",
    "supporting_evidence_ids": ["ev-001", "ev-002"],
})

_RECOMMENDATION_LLM_RESPONSE = json.dumps([
    {
        "defect_id": "AGGREGATION_SKIP",
        "action": "Re-enable deposit aggregation step in sp_calculate_insurance.sql:line 44",
        "priority": "P1",
        "effort_estimate": "4h",
        "regulation_ref": "12 CFR Part 330 §330.1(b)",
        "rationale": "Silent disable causes under-insurance of depositors.",
        "evidence_ids": ["ev-001", "ev-002"],
    }
])

_REVIEWER_LLM_RESPONSE = json.dumps({
    "overall_pass": True,
    "checklist": {
        "C1_regulation_ref_present": True,
        "C2_defect_id_present": True,
        "C3_evidence_per_profile": True,
        "C4_confidence_threshold": True,
        "C5_evidence_source_diversity": True,
        "C6_evidence_ids_coherent": True,
        "C7_ontology_relationships": True,
        "C8_p1_recommendation_present": True,
    },
    "gaps": [],
    "feedback": [],
})

# Default: all agents return their appropriate payload for a deposit scenario.
_CANNED_RESPONSES: dict[str, str] = {
    "RoutingAgent":         _ROUTING_LLM_RESPONSE,
    "TriangulationAgent":   _TRIANGULATION_LLM_RESPONSE,
    "RecommendationAgent":  _RECOMMENDATION_LLM_RESPONSE,
    "ReviewerAgent":        _REVIEWER_LLM_RESPONSE,
    "default":              _ROUTING_LLM_RESPONSE,
}


# ---------------------------------------------------------------------------
# mock_llm fixture
# ---------------------------------------------------------------------------

class _FakeLLMMessage:
    """Minimal stand-in for an LLM message response object."""
    def __init__(self, content: str) -> None:
        self.content = content


class MockLLMClient:
    """
    Deterministic LLMClient mock.

    Returns a pre-canned JSON string for each agent. The response key is
    matched against the ``name`` attribute set by ``set_response_for``.
    Wraps the return in an object with a ``.content`` attribute so
    LangChain-style callers work correctly.
    """

    def __init__(self, response_map: dict[str, str] | None = None) -> None:
        self._map = response_map or _CANNED_RESPONSES

    async def ainvoke(self, messages: list[Any]) -> _FakeLLMMessage:  # noqa: ARG002
        # Parse the agent name from the system prompt (first message).
        if messages and hasattr(messages[0], "content"):
            content = messages[0].content
        elif messages and isinstance(messages[0], tuple):
            content = messages[0][1]
        else:
            content = ""

        for key, payload in self._map.items():
            if key.lower() in content.lower():
                return _FakeLLMMessage(payload)
        return _FakeLLMMessage(self._map.get("default", _ROUTING_LLM_RESPONSE))


@pytest.fixture
def mock_llm() -> MockLLMClient:
    """Return a deterministic MockLLMClient. Suitable for all agent tests."""
    return MockLLMClient()


# ---------------------------------------------------------------------------
# Sample EvidenceObjects (shared helpers)
# ---------------------------------------------------------------------------

def _make_evidence(
    source_tool: str,
    severity: Priority = Priority.P2,
    defect_id: str | None = None,
    regulation_ref: str | None = None,
    ev_id: str = "ev-001",
) -> EvidenceObject:
    return EvidenceObject(
        id=ev_id,
        source_tool=source_tool,
        timestamp=datetime(2026, 3, 16, 8, 0, 0, tzinfo=timezone.utc),
        severity=severity,
        description=f"Test evidence from {source_tool}",
        defect_id=defect_id,
        regulation_ref=regulation_ref,
        raw_payload={"test": True},
    )


# ---------------------------------------------------------------------------
# IncidentContext fixtures — one per scenario
# ---------------------------------------------------------------------------

@pytest.fixture
def incident_ctx_deposit() -> IncidentContext:
    """Valid IncidentContext for scenario: deposit_aggregation_failure."""
    return IncidentContext(
        incident_id="INC-DEP-001",
        run_id="RUN-20260316-001",
        pipeline_stage="deposit_aggregation",
        failed_controls=["CTL-DEP-001"],
        ontology_snapshot={"entry_node": "Control:CTL-DEP-001"},
        metadata={
            "scenario_id": "deposit_aggregation_failure",
            "spark_metrics": {
                "execution_summary": {
                    "failed_task_count": 12,
                    "total_tasks": 100,
                    "total_duration_ms": 45000,
                },
                "memory": {"spill_bytes": 2_000_000_000, "oom_events": 3},
            },
            "data_profile": {
                "dataset_name": "deposit_ledger",
                "row_count": 50000,
                "columns": [
                    {"name": "account_id", "dtype": "string", "null_rate": 0.0},
                    {"name": "orc_amount", "dtype": "float64", "null_rate": 0.34},
                ],
            },
            "change_fingerprint": {
                "repo_name": "fdic-controls",
                "window_days": 7,
                "commits": [
                    {
                        "hash": "abc123",
                        "author": "alice",
                        "timestamp": "2026-03-15T10:00:00Z",
                        "files": [
                            {"path": "etl/sp_calculate_insurance.sql", "added": 88, "deleted": 15}
                        ],
                    }
                ],
            },
            "airflow_fingerprint": {
                "dag_id": "deposit_nightly",
                "task_id": "run_orc_aggregation",
                "execution_date": "2026-03-16",
                "try_number": 3,
                "max_retries": 3,
                "log_lines": [
                    "[INFO] Starting ORC aggregation",
                    "[ERROR] AGGRSTEP disabled via feature flag",
                    "[FATAL] Task failed: aggregation step returned 0 rows",
                ],
            },
        },
    )


@pytest.fixture
def incident_ctx_trust() -> IncidentContext:
    """Valid IncidentContext for scenario: trust_irr_misclassification."""
    return IncidentContext(
        incident_id="INC-TRUST-002",
        run_id="RUN-20260316-002",
        pipeline_stage="trust_classification",
        failed_controls=["CTL-TRUST-001"],
        ontology_snapshot={"entry_node": "Control:CTL-TRUST-001"},
        metadata={
            "scenario_id": "trust_irr_misclassification",
            "airflow_fingerprint": {
                "dag_id": "trust_custody_nightly",
                "task_id": "classify_ira_accounts",
                "execution_date": "2026-03-16",
                "try_number": 1,
                "max_retries": 3,
                "log_lines": [
                    "[INFO] Processing IRR trust accounts",
                    "[WARN] IRR handler not implemented — falling through to SGL",
                    "[ERROR] Account ACC-9921 misclassified as Single GL",
                ],
            },
            "data_profile": {
                "dataset_name": "trust_accounts",
                "row_count": 5000,
                "columns": [
                    {"name": "account_type", "dtype": "string", "null_rate": 0.0},
                    {"name": "insurance_class", "dtype": "string", "null_rate": 0.18},
                ],
            },
            "change_fingerprint": {
                "repo_name": "trust-custody",
                "window_days": 14,
                "commits": [
                    {
                        "hash": "def456",
                        "author": "bob",
                        "timestamp": "2026-03-10T14:00:00Z",
                        "files": [
                            {
                                "path": "cobol/TRUST-INSURANCE-CALC.cob",
                                "added": 5,
                                "deleted": 120,
                            }
                        ],
                    }
                ],
            },
        },
    )


@pytest.fixture
def incident_ctx_wire() -> IncidentContext:
    """Valid IncidentContext for scenario: wire_mt202_drop."""
    return IncidentContext(
        incident_id="INC-WIRE-003",
        run_id="RUN-20260316-003",
        pipeline_stage="wire_processing",
        failed_controls=["CTL-WIRE-006"],
        ontology_snapshot={"entry_node": "Control:CTL-WIRE-006"},
        metadata={
            "scenario_id": "wire_mt202_drop",
            "airflow_fingerprint": {
                "dag_id": "wire_transfer_nightly",
                "task_id": "process_swift_messages",
                "execution_date": "2026-03-16",
                "try_number": 1,
                "max_retries": 3,
                "log_lines": [
                    "[INFO] Processing SWIFT message batch",
                    "[WARN] MT202 message type: no ordering_customer_id — silently dropped",
                    "[ERROR] 3 wire transfers dropped — no CIF match",
                ],
            },
            "spark_metrics": {
                "execution_summary": {
                    "failed_task_count": 3,
                    "total_tasks": 200,
                    "total_duration_ms": 12000,
                },
                "memory": {"spill_bytes": 0, "oom_events": 0},
            },
        },
    )


# ---------------------------------------------------------------------------
# sample_incident_context (parametrized convenience)
# ---------------------------------------------------------------------------

@pytest.fixture(params=["deposit", "trust", "wire"])
def sample_incident_context(
    request,
    incident_ctx_deposit,
    incident_ctx_trust,
    incident_ctx_wire,
) -> IncidentContext:
    """Parametrized fixture that yields all three scenario contexts in turn."""
    mapping = {
        "deposit": incident_ctx_deposit,
        "trust":   incident_ctx_trust,
        "wire":    incident_ctx_wire,
    }
    return mapping[request.param]


# ---------------------------------------------------------------------------
# tool_registry fixture
# ---------------------------------------------------------------------------

@pytest.fixture
def tool_registry(mock_llm):
    """Register and return all 5 tools wired to mock_llm."""
    from core.llm import LLMConfig
    from tools.log_analyzer.spark_log_tool import SparkLogTool
    from tools.log_analyzer.airflow_log_tool import AirflowLogTool
    from tools.code_analyzer.git_diff_tool import GitDiffTool
    from tools.data_profiler.dq_tool import DataQualityTool
    from tools.change_analyzer.ddl_diff_tool import DDLDiffTool

    registry: dict[str, Any] = {}
    llm_cfg = LLMConfig()

    tools = [
        SparkLogTool(llm_cfg),
        AirflowLogTool(llm_cfg),
        GitDiffTool(llm_cfg),
        DataQualityTool(),
        DDLDiffTool(),
    ]
    for t in tools:
        t.register(registry)
    return registry


# ---------------------------------------------------------------------------
# Mock My_Bank API — respx router
# ---------------------------------------------------------------------------

_INCIDENT_ID   = "INC-DEP-001"
_RUN_ID        = "RUN-20260316-001"

_CONTEXT_PAYLOAD = {
    "incident_id":    _INCIDENT_ID,
    "run_id":         _RUN_ID,
    "pipeline_stage": "deposit_aggregation",
    "failed_controls": [
        {"control_id": "CTL-DEP-001", "control_name": "Per-depositor ORC aggregation check"}
    ],
    "ontology_snapshot": {},
    "metadata": {"scenario_id": "deposit_aggregation_failure"},
    "evidence": [
        {
            "evidence_type": "log_artifact",
            "source_system": "SparkLogTool",
            "artifact_ref": "s3://logs/deposit_nightly/2026-03-16",
            "content_json": {"error": "AGGRSTEP disabled"},
        }
    ],
}

_LINEAGE_PAYLOAD = {
    "job_id": "deposit_nightly",
    "nodes": [
        {"id": "n1", "type": "job",   "name": "deposit_nightly"},
        {"id": "n2", "type": "table", "name": "deposit_ledger"},
    ],
    "edges": [
        {"source": "n1", "target": "n2", "relation": "WRITES"}
    ],
}

_SSE_LINES = (
    'data: {"source": "spark", "timestamp": "2026-03-16T08:00:00Z", '
    '"level": "ERROR", "message": "AGGRSTEP disabled via feature flag"}\n\n'
    'data: [DONE]\n\n'
)

_INCIDENTS_PAYLOAD = [
    {
        "incident_id":   _INCIDENT_ID,
        "control_id":    "CTL-DEP-001",
        "severity":      "P1",
        "status":        "open",
        "created_at":    "2026-03-16T00:00:00Z",
        "rca_triggered": False,
    }
]


@pytest.fixture
def mock_bank_api():
    """
    respx router with all My_Bank endpoints mocked.

    Yields the router as a context manager.  Routes match on *pattern* so that
    path parameters (e.g. /rca/context/INC-DEP-001) are handled generically.
    """
    with respx.mock(base_url="http://localhost:8000", assert_all_called=False) as router:
        # GET /health
        router.get("/health").mock(
            return_value=httpx.Response(200, json={"status": "ok", "env": "test"})
        )

        # GET /rca/context/{incident_id}
        router.get(url__regex=r"/rca/context/").mock(
            return_value=httpx.Response(200, json=_CONTEXT_PAYLOAD)
        )

        # GET /logs/stream/{incident_id}  — SSE
        router.get(url__regex=r"/logs/stream/").mock(
            return_value=httpx.Response(
                200,
                content=_SSE_LINES.encode(),
                headers={"Content-Type": "text/event-stream"},
            )
        )

        # GET /lineage/{job_id}
        router.get(url__regex=r"/lineage/").mock(
            return_value=httpx.Response(200, json=_LINEAGE_PAYLOAD)
        )

        # POST /pipeline/run
        router.post("/pipeline/run").mock(
            return_value=httpx.Response(200, json={"run_id": _RUN_ID, "status": "triggered"})
        )

        # GET /incidents
        router.get("/incidents").mock(
            return_value=httpx.Response(200, json=_INCIDENTS_PAYLOAD)
        )

        # GET /runs/{run_id}/incidents
        router.get(url__regex=r"/runs/.+/incidents").mock(
            return_value=httpx.Response(200, json=_INCIDENTS_PAYLOAD)
        )

        # POST /rca/results/{incident_id}
        router.post(url__regex=r"/rca/results/").mock(
            return_value=httpx.Response(200, json={"status": "accepted"})
        )

        yield router

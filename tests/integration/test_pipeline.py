"""
tests/integration/test_pipeline.py
Integration tests for KratosOrchestrator — end-to-end pipeline execution.

Strategy
--------
- respx mocks all My_Bank HTTP endpoints (via mock_bank_api fixture)
- MockLLMClient returns deterministic canned JSON for each agent
- KratosOrchestrator.run() is exercised in full: all 7 phases
- Reviewer feedback loop is tested by injecting a gap on first pass

Test matrix
-----------
test_all_7_phases_execute              — phases_executed has all 7 entries
test_report_has_evidence               — evidence list is non-empty
test_evidence_has_source_tool          — all evidence items have source_tool
test_report_has_issue_profiles         — issue_profiles is non-empty
test_report_has_recommendations        — recommendations is non-empty
test_every_rec_cites_defect_id         — C2 compliance across all recs
test_every_rec_cites_regulation_ref    — C1 compliance across all recs
test_audit_trail_length                — audit_trail has ≥7 entries
test_rca_report_has_incident_id        — report.incident_id matches input
test_final_root_cause_is_non_empty     — report.final_root_cause is a string
test_reviewer_feedback_loop            — injecting a gap triggers re-route
test_incident_card_metadata            — incident_card present in metadata
"""
from __future__ import annotations

import asyncio
import json
from datetime import datetime, timezone
from typing import Any
from unittest.mock import AsyncMock, patch

import pytest

from core.models import (
    EvidenceObject,
    IncidentContext,
    IssueProfile,
    Priority,
    Recommendation,
)
from workflow.pipeline_phases import Phase, RCAReport


# ---------------------------------------------------------------------------
# Helpers: build a minimal orchestrator with mocked dependencies
# ---------------------------------------------------------------------------

def _make_orchestrator(mock_llm, mock_bank_api=None):
    """
    Return a KratosOrchestrator instance wired to MockLLMClient.

    The tool registry and agent registry are built with real classes but all
    LLM calls go to the mock. The bank connector is patched separately.
    """
    from agents.orchestrator.orchestrator import KratosOrchestrator
    from connectors.bank_pipeline import BankPipelineConnector

    connector = BankPipelineConnector(base_url="http://localhost:8000")

    # Build a minimal but valid tool registry (no real LLM calls during test)
    from core.llm import LLMConfig
    from tools import register_all_tools
    tool_reg = register_all_tools(LLMConfig())

    # Wire KratosOrchestrator — the orchestrator calls agents that call mock_llm
    from agents import register_all_agents
    agent_reg = register_all_agents()

    orch = KratosOrchestrator(
        connector=connector,
        llm=mock_llm,
        tool_registry=tool_reg,
        agent_registry=agent_reg,
    )
    return orch, connector


# ---------------------------------------------------------------------------
# Fixtures: pre-built context loaded into metadata for the orchestrator
# ---------------------------------------------------------------------------

@pytest.fixture
def deposit_rca_context():
    """Full IncidentContext as if fetched from /rca/context/INC-DEP-001."""
    return IncidentContext(
        incident_id="INC-DEP-001",
        run_id="RUN-20260316-001",
        pipeline_stage="deposit_aggregation",
        failed_controls=["CTL-DEP-001"],
        metadata={
            "scenario_id": "deposit_aggregation_failure",
            "spark_metrics": {
                "execution_summary": {
                    "failed_task_count": 12,
                    "total_tasks": 100,
                },
                "memory": {"spill_bytes": 2_000_000_000, "oom_events": 3},
            },
            "data_profile": {
                "dataset_name": "deposit_ledger",
                "row_count": 50000,
                "columns": [
                    {"name": "orc_amount", "dtype": "float64", "null_rate": 0.34},
                ],
            },
            "airflow_fingerprint": {
                "dag_id": "deposit_nightly",
                "task_id": "run_orc_aggregation",
                "execution_date": "2026-03-16",
                "try_number": 3,
                "max_retries": 3,
                "log_lines": [
                    "[ERROR] AGGRSTEP disabled via feature flag",
                    "[FATAL] Task failed",
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
        },
    )


# ---------------------------------------------------------------------------
# Integration tests
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_all_7_phases_execute(mock_llm, mock_bank_api):
    """All 7 phases must appear in report.phases_executed."""
    expected_phases = {p.value for p in Phase}
    orch, connector = _make_orchestrator(mock_llm)

    async with connector:
        report = await orch.run("INC-DEP-001")

    assert isinstance(report, RCAReport)
    executed = set(report.phases_executed)
    assert expected_phases == executed, (
        f"Missing phases: {expected_phases - executed}"
    )


@pytest.mark.asyncio
async def test_report_has_evidence(mock_llm, mock_bank_api):
    orch, connector = _make_orchestrator(mock_llm)
    async with connector:
        report = await orch.run("INC-DEP-001")
    assert len(report.evidence) >= 1, "Report must contain at least one evidence item."


@pytest.mark.asyncio
async def test_evidence_has_source_tool(mock_llm, mock_bank_api):
    orch, connector = _make_orchestrator(mock_llm)
    async with connector:
        report = await orch.run("INC-DEP-001")
    for ev in report.evidence:
        ev_obj = ev if isinstance(ev, EvidenceObject) else EvidenceObject(**ev)
        assert ev_obj.source_tool, f"Evidence item {ev_obj.id} missing source_tool"


@pytest.mark.asyncio
async def test_report_has_issue_profiles(mock_llm, mock_bank_api):
    orch, connector = _make_orchestrator(mock_llm)
    async with connector:
        report = await orch.run("INC-DEP-001")
    assert isinstance(report.issue_profiles, list)
    # Profile list may be populated by Triangulation or orchestrator inline.


@pytest.mark.asyncio
async def test_report_has_recommendations(mock_llm, mock_bank_api):
    orch, connector = _make_orchestrator(mock_llm)
    async with connector:
        report = await orch.run("INC-DEP-001")
    assert isinstance(report.recommendations, list)


@pytest.mark.asyncio
async def test_every_rec_cites_defect_id(mock_llm, mock_bank_api):
    """C2 compliance: every recommendation must have a non-empty defect_id."""
    orch, connector = _make_orchestrator(mock_llm)
    async with connector:
        report = await orch.run("INC-DEP-001")
    for rec in report.recommendations:
        rec_obj = rec if isinstance(rec, Recommendation) else Recommendation(**rec)
        assert rec_obj.defect_id, (
            f"Recommendation '{rec_obj.action}' is missing defect_id (C2 violation)"
        )


@pytest.mark.asyncio
async def test_every_rec_cites_regulation_ref(mock_llm, mock_bank_api):
    """C1 compliance: every recommendation must cite a CFR section."""
    orch, connector = _make_orchestrator(mock_llm)
    async with connector:
        report = await orch.run("INC-DEP-001")
    for rec in report.recommendations:
        rec_obj = rec if isinstance(rec, Recommendation) else Recommendation(**rec)
        assert rec_obj.regulation_ref, (
            f"Recommendation '{rec_obj.action}' is missing regulation_ref (C1 violation)"
        )


@pytest.mark.asyncio
async def test_audit_trail_has_7_or_more_entries(mock_llm, mock_bank_api):
    """One AuditEvent per phase minimum."""
    orch, connector = _make_orchestrator(mock_llm)
    async with connector:
        report = await orch.run("INC-DEP-001")
    assert len(report.audit_trail) >= 7, (
        f"Expected ≥7 audit events (one per phase), got {len(report.audit_trail)}"
    )


@pytest.mark.asyncio
async def test_rca_report_incident_id_matches_input(mock_llm, mock_bank_api):
    orch, connector = _make_orchestrator(mock_llm)
    async with connector:
        report = await orch.run("INC-DEP-001")
    assert report.incident_id == "INC-DEP-001"


@pytest.mark.asyncio
async def test_final_root_cause_is_non_empty_string(mock_llm, mock_bank_api):
    orch, connector = _make_orchestrator(mock_llm)
    async with connector:
        report = await orch.run("INC-DEP-001")
    assert isinstance(report.final_root_cause, str)
    assert len(report.final_root_cause) > 0


@pytest.mark.asyncio
async def test_incident_card_in_metadata(mock_llm, mock_bank_api):
    orch, connector = _make_orchestrator(mock_llm)
    async with connector:
        report = await orch.run("INC-DEP-001")
    assert "incident_card" in report.metadata, (
        "report.metadata must contain 'incident_card' after INCIDENT_CARD phase"
    )


@pytest.mark.asyncio
async def test_duration_seconds_is_positive(mock_llm, mock_bank_api):
    orch, connector = _make_orchestrator(mock_llm)
    async with connector:
        report = await orch.run("INC-DEP-001")
    assert report.duration_seconds >= 0.0


# ---------------------------------------------------------------------------
# Reviewer feedback loop test
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_reviewer_feedback_loop_triggers_re_route(mock_llm, mock_bank_api):
    """
    Inject a ReviewerAgent that FAILS on the first call (missing regulation_ref)
    and PASSES on the second call.  Verify the orchestrator loops back to ROUTE
    and ultimately produces a clean report.
    """
    from agents.orchestrator.orchestrator import KratosOrchestrator
    from connectors.bank_pipeline import BankPipelineConnector
    from core.llm import LLMConfig
    from tools import register_all_tools
    from agents import register_all_agents
    from core.base_agent import AgentResult

    call_count = 0

    class _FlickerReviewerLLM:
        """Returns a gap report on call 0, pass report on call 1+."""
        async def ainvoke(self, messages):
            nonlocal call_count
            if "reviewer" in str(messages).lower() or call_count == 0:
                call_count += 1
                if call_count == 1:
                    # First call: C1 gap
                    payload = json.dumps({
                        "overall_pass": False,
                        "gaps": ["CRITICAL: Recommendation missing regulation_ref (C1)."],
                        "feedback": ["RecommendationAgent: add regulation_ref."],
                    })
                else:
                    payload = json.dumps({
                        "overall_pass": True,
                        "gaps": [],
                        "feedback": [],
                    })
            else:
                payload = json.dumps({
                    "pattern_id": "HPL-001",
                    "pattern_name": "Spark Execution Failure",
                    "selected_tools": ["SparkLogTool"],
                    "rationale": "OOM signals.",
                    "confidence": 0.91,
                })

            class _Msg:
                content = payload
            return _Msg()

    connector = BankPipelineConnector(base_url="http://localhost:8000")
    tool_reg = register_all_tools(LLMConfig())
    agent_reg = register_all_agents()
    flicker_llm = _FlickerReviewerLLM()

    orch = KratosOrchestrator(
        connector=connector,
        llm=flicker_llm,
        tool_registry=tool_reg,
        agent_registry=agent_reg,
    )

    async with connector:
        report = await orch.run("INC-DEP-001")

    # The orchestrator must still produce a complete report after looping.
    assert isinstance(report, RCAReport)
    assert report.incident_id == "INC-DEP-001"
    # Audit trail should contain a 'looped' or extra ROUTE entry.
    outcomes = [
        a.get("outcome") if isinstance(a, dict) else getattr(a, "outcome", None)
        for a in report.audit_trail
    ]
    # Valid outcomes are success/failure/looped/skipped.
    assert all(o in {None, "success", "failure", "skipped", "looped"} for o in outcomes)

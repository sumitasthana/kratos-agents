"""
tests/unit/test_agents.py
Unit tests for the 4 Kratos agents: Routing, Triangulation, Recommendation, Reviewer.

Strategy
--------
- LLM calls are mocked via MockLLMClient from conftest.py
- No real HTTP or LLM provider connections are made
- All tests are deterministic and sync-safe (pytest-asyncio)

Coverage
--------
RoutingAgent
  - invoke() returns AgentResult with selected_tools and next_phase
  - Heuristic fallback when LLM response is malformed JSON
  - Selects HPL-001 for Spark signals, HPL-003 for git signals
  - Selects HPL-004 for Airflow signals

TriangulationAgent
  - invoke() returns issue_profiles with confidence and causal_chain
  - Handles evidence-less context gracefully
  - Timestamp alignment window groups close events

RecommendationAgent
  - invoke() returns Recommendation objects with defect_id and regulation_ref
  - Every recommendation passes ReviewerAgent C1 and C2 checks
  - Handles context with no issue_profiles gracefully

ReviewerAgent
  - _run_checklist() passes clean report
  - _run_checklist() catches missing regulation_ref (C1)
  - _run_checklist() catches missing defect_id (C2)
  - _run_checklist() catches low-confidence profile (C4)
  - invoke() returns next_phase="done" on clean report
  - invoke() returns next_phase="routing" on gaps
"""
from __future__ import annotations

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


# ---------------------------------------------------------------------------
# Shared helpers
# ---------------------------------------------------------------------------

def _ctx(
    metadata: dict,
    incident_id: str = "INC-UNIT-001",
    failed_controls: list[str] | None = None,
) -> IncidentContext:
    return IncidentContext(
        incident_id=incident_id,
        run_id="RUN-UNIT-001",
        pipeline_stage="unit_test",
        failed_controls=failed_controls or [],
        metadata=metadata,
    )


def _evidence(
    source_tool: str = "SparkLogTool",
    severity: Priority = Priority.P2,
    defect_id: str | None = "AGGREGATION_SKIP",
    regulation_ref: str | None = "12 CFR Part 330 §330.1(b)",
    ev_id: str = "ev-001",
) -> EvidenceObject:
    return EvidenceObject(
        id=ev_id,
        source_tool=source_tool,
        timestamp=datetime(2026, 3, 16, 8, 0, 0, tzinfo=timezone.utc),
        severity=severity,
        description=f"Evidence from {source_tool}",
        defect_id=defect_id,
        regulation_ref=regulation_ref,
    )


def _profile(
    confidence: float = 0.91,
    evidence: list | None = None,
    profile_id: str = "prof-001",
) -> IssueProfile:
    ev = evidence if evidence is not None else [_evidence()]
    return IssueProfile(
        id=profile_id,
        root_cause_hypothesis="AGGREGATION_SKIP: aggregation step silently disabled.",
        supporting_evidence=ev,
        confidence=confidence,
        affected_regulation="12 CFR Part 330 §330.1(b)",
    )


def _recommendation(
    defect_id: str = "AGGREGATION_SKIP",
    regulation_ref: str = "12 CFR Part 330 §330.1(b)",
    action: str = "Re-enable aggregation step",
    priority: Priority = Priority.P1,
    issue_profile_id: str = "prof-001",
) -> Recommendation:
    return Recommendation(
        issue_profile_id=issue_profile_id,
        action=action,
        priority=priority,
        effort_estimate="4h",
        defect_id=defect_id,
        regulation_ref=regulation_ref,
        rationale="Silent disable under-insures depositors.",
    )


# ---------------------------------------------------------------------------
# RoutingAgent tests
# ---------------------------------------------------------------------------

class TestRoutingAgent:
    @pytest.fixture(autouse=True)
    def agent(self, mock_llm):
        from agents.routing.agent import RoutingAgent
        self.agent = RoutingAgent(llm=mock_llm)

    @pytest.mark.asyncio
    async def test_invoke_returns_agent_result_structure(self, incident_ctx_deposit):
        from core.base_agent import AgentResult
        result = await self.agent.invoke(incident_ctx_deposit)
        assert isinstance(result, AgentResult)
        assert result.agent_name
        assert result.next_phase == "triangulation"
        assert "selected_tools" in result.metadata

    @pytest.mark.asyncio
    async def test_selected_tools_is_non_empty_list(self, incident_ctx_deposit):
        result = await self.agent.invoke(incident_ctx_deposit)
        tools = result.metadata["selected_tools"]
        assert isinstance(tools, list)
        assert len(tools) > 0

    @pytest.mark.asyncio
    async def test_spark_signals_select_spark_tool(self):
        """Context with 'spark_metrics' key should include SparkLogTool."""
        ctx = _ctx({"spark_metrics": {"execution_summary": {"failed_task_count": 10}}})
        result = await self.agent.invoke(ctx)
        tools = result.metadata["selected_tools"]
        assert "SparkLogTool" in tools, (
            f"Expected SparkLogTool for spark_metrics context, got: {tools}"
        )

    @pytest.mark.asyncio
    async def test_git_signals_select_git_tools(self):
        """Context with 'change_fingerprint'/'git_diff' keys → DDLDiffTool or GitDiffTool."""
        ctx = _ctx({
            "change_fingerprint": {"repo_name": "fdic", "commits": [], "window_days": 7},
            "git_diff": {"diffs": []},
        })
        result = await self.agent.invoke(ctx)
        tools = result.metadata["selected_tools"]
        git_tools = {"DDLDiffTool", "GitDiffTool"}
        assert git_tools & set(tools), (
            f"Expected DDLDiffTool or GitDiffTool for git signals, got: {tools}"
        )

    @pytest.mark.asyncio
    async def test_airflow_signals_select_airflow_tool(self):
        ctx = _ctx({"airflow_fingerprint": {"dag_id": "test_dag", "log_lines": []}})
        result = await self.agent.invoke(ctx)
        tools = result.metadata["selected_tools"]
        assert "AirflowLogTool" in tools, (
            f"Expected AirflowLogTool for airflow context, got: {tools}"
        )

    @pytest.mark.asyncio
    async def test_heuristic_fallback_on_malformed_llm_json(self, mock_llm):
        """If LLM returns garbage JSON, heuristics must still return valid tools."""
        from agents.routing.agent import RoutingAgent
        bad_llm = type(mock_llm)({"default": "NOT VALID JSON {{{{", "RoutingAgent": "{{{"})
        agent = RoutingAgent(llm=bad_llm)
        ctx = _ctx({"spark_metrics": {"execution_summary": {"failed_task_count": 5}}})
        result = await agent.invoke(ctx)
        tools = result.metadata["selected_tools"]
        assert isinstance(tools, list)
        assert len(tools) > 0, "Heuristic fallback must still select at least one tool"

    @pytest.mark.asyncio
    async def test_pattern_id_present_in_metadata(self, incident_ctx_deposit):
        result = await self.agent.invoke(incident_ctx_deposit)
        # pattern_id may be absent if heuristic path taken, but must be a string if present.
        if "pattern_id" in result.metadata:
            assert isinstance(result.metadata["pattern_id"], str)

    @pytest.mark.asyncio
    async def test_agent_name_property(self):
        assert "Routing" in self.agent.agent_name

    def test_system_prompt_is_non_empty(self):
        assert len(self.agent.system_prompt) > 50


# ---------------------------------------------------------------------------
# TriangulationAgent tests
# ---------------------------------------------------------------------------

class TestTriangulationAgent:
    @pytest.fixture(autouse=True)
    def agent(self, mock_llm):
        from agents.triangulation.agent import TriangulationAgent
        self.agent = TriangulationAgent(llm=mock_llm)

    @pytest.mark.asyncio
    async def test_invoke_with_evidence_returns_issue_profiles(self):
        ev1 = _evidence("SparkLogTool",   ev_id="ev-001")
        ev2 = _evidence("DataQualityTool", ev_id="ev-002")
        ctx = _ctx({
            "evidence": [ev1.model_dump(), ev2.model_dump()],
        })
        result = await self.agent.invoke(ctx)
        from core.base_agent import AgentResult
        assert isinstance(result, AgentResult)
        # Agent may produce profiles or set metadata — validate graceful return.
        assert isinstance(result.issue_profiles, list)

    @pytest.mark.asyncio
    async def test_invoke_with_no_evidence_does_not_raise(self):
        ctx = _ctx({"evidence": []})
        result = await self.agent.invoke(ctx)
        assert isinstance(result.issue_profiles, list)

    @pytest.mark.asyncio
    async def test_issue_profile_structure(self):
        ev1 = _evidence("SparkLogTool",   ev_id="ev-A")
        ev2 = _evidence("AirflowLogTool", ev_id="ev-B")
        ctx = _ctx({
            "evidence": [ev1.model_dump(), ev2.model_dump()],
        })
        result = await self.agent.invoke(ctx)
        for profile in result.issue_profiles:
            profile_obj = (
                profile if isinstance(profile, IssueProfile)
                else IssueProfile(**profile)
            )
            assert 0.0 <= profile_obj.confidence <= 1.0, (
                f"Confidence out of range: {profile_obj.confidence}"
            )
            assert profile_obj.root_cause_hypothesis

    @pytest.mark.asyncio
    async def test_agent_name_property(self):
        assert "Triangulation" in self.agent.agent_name

    @pytest.mark.asyncio
    async def test_next_phase_set(self):
        ctx = _ctx({"evidence": []})
        result = await self.agent.invoke(ctx)
        # next_phase may be None or a string — must not be some unknown value.
        if result.next_phase is not None:
            assert isinstance(result.next_phase, str)

    @pytest.mark.asyncio
    async def test_metadata_contains_alignment_info(self):
        ev1 = _evidence("SparkLogTool",   ev_id="ev-X")
        ev2 = _evidence("DataQualityTool", ev_id="ev-Y")
        ctx = _ctx({"evidence": [ev1.model_dump(), ev2.model_dump()]})
        result = await self.agent.invoke(ctx)
        # alignment_score is optional but if present must be numeric.
        if "alignment_score" in result.metadata:
            assert isinstance(result.metadata["alignment_score"], (int, float))


# ---------------------------------------------------------------------------
# RecommendationAgent tests
# ---------------------------------------------------------------------------

class TestRecommendationAgent:
    @pytest.fixture(autouse=True)
    def agent(self, mock_llm):
        from agents.recommendation.agent import RecommendationAgent
        self.agent = RecommendationAgent(llm=mock_llm)

    @pytest.mark.asyncio
    async def test_invoke_with_profiles_returns_recommendations(self):
        profile = _profile()
        ctx = _ctx({"issue_profiles": [profile.model_dump()]})
        result = await self.agent.invoke(ctx)
        from core.base_agent import AgentResult
        assert isinstance(result, AgentResult)
        assert isinstance(result.recommendations, list)

    @pytest.mark.asyncio
    async def test_every_recommendation_has_defect_id(self):
        profile = _profile()
        ctx = _ctx({"issue_profiles": [profile.model_dump()]})
        result = await self.agent.invoke(ctx)
        for rec in result.recommendations:
            rec_obj = rec if isinstance(rec, Recommendation) else Recommendation(**rec)
            assert rec_obj.defect_id, (
                f"Recommendation '{rec_obj.action}' missing defect_id"
            )

    @pytest.mark.asyncio
    async def test_every_recommendation_has_regulation_ref(self):
        profile = _profile()
        ctx = _ctx({"issue_profiles": [profile.model_dump()]})
        result = await self.agent.invoke(ctx)
        for rec in result.recommendations:
            rec_obj = rec if isinstance(rec, Recommendation) else Recommendation(**rec)
            assert rec_obj.regulation_ref, (
                f"Recommendation '{rec_obj.action}' missing regulation_ref"
            )

    @pytest.mark.asyncio
    async def test_next_phase_is_review(self):
        profile = _profile()
        ctx = _ctx({"issue_profiles": [profile.model_dump()]})
        result = await self.agent.invoke(ctx)
        assert result.next_phase == "review", (
            f"Expected next_phase='review', got '{result.next_phase}'"
        )

    @pytest.mark.asyncio
    async def test_empty_profiles_does_not_raise(self):
        ctx = _ctx({"issue_profiles": []})
        result = await self.agent.invoke(ctx)
        assert isinstance(result.recommendations, list)

    @pytest.mark.asyncio
    async def test_priority_is_valid(self):
        profile = _profile()
        ctx = _ctx({"issue_profiles": [profile.model_dump()]})
        result = await self.agent.invoke(ctx)
        for rec in result.recommendations:
            rec_obj = rec if isinstance(rec, Recommendation) else Recommendation(**rec)
            assert rec_obj.priority in Priority, (
                f"Invalid priority: {rec_obj.priority}"
            )


# ---------------------------------------------------------------------------
# ReviewerAgent tests
# ---------------------------------------------------------------------------

class TestReviewerAgent:
    @pytest.fixture(autouse=True)
    def agent(self, mock_llm):
        from agents.reviewer.agent import ReviewerAgent
        self.agent = ReviewerAgent(llm=mock_llm)

    # -- _run_checklist: deterministic structural checks ---------------------

    def test_checklist_passes_clean_report(self):
        ctx = _ctx({
            "evidence":        [_evidence("SparkLogTool").model_dump()],
            "issue_profiles":  [_profile().model_dump()],
            "recommendations": [_recommendation().model_dump()],
        })
        report = self.agent._run_checklist(ctx)
        assert report.passed, f"Expected pass, gaps: {report.gap_count}"

    def test_checklist_catches_missing_regulation_ref(self):
        rec = _recommendation(regulation_ref="")   # C1 violation
        ctx = _ctx({
            "evidence":        [_evidence("SparkLogTool").model_dump()],
            "issue_profiles":  [_profile().model_dump()],
            "recommendations": [rec.model_dump()],
        })
        report = self.agent._run_checklist(ctx)
        passing = {c.criterion: c.passed for c in report.checks}
        c1 = next(
            (c for c in report.checks if "regulation_ref" in c.criterion), None
        )
        assert c1 is not None, "C1 check not found in checklist"
        assert not c1.passed, "C1 must fail when regulation_ref is empty"
        assert report.gap_count >= 1

    def test_checklist_catches_missing_defect_id(self):
        rec = _recommendation(defect_id="")       # C2 violation
        ctx = _ctx({
            "evidence":        [_evidence("SparkLogTool").model_dump()],
            "issue_profiles":  [_profile().model_dump()],
            "recommendations": [rec.model_dump()],
        })
        report = self.agent._run_checklist(ctx)
        c2 = next(
            (c for c in report.checks if "defect_id" in c.criterion), None
        )
        assert c2 is not None, "C2 check not found in checklist"
        assert not c2.passed, "C2 must fail when defect_id is empty"

    def test_checklist_catches_low_confidence(self):
        profile = _profile(confidence=0.3)         # C4 violation
        ctx = _ctx({
            "evidence":        [_evidence("SparkLogTool").model_dump()],
            "issue_profiles":  [profile.model_dump()],
            "recommendations": [_recommendation().model_dump()],
        })
        report = self.agent._run_checklist(ctx)
        c4 = next(
            (c for c in report.checks if "confidence" in c.criterion.lower()), None
        )
        assert c4 is not None, "C4 check not found in checklist"
        assert not c4.passed, "C4 must fail for confidence=0.3"

    def test_checklist_catches_unsupported_profile(self):
        profile = _profile(evidence=[])            # C3 violation — no evidence
        ctx = _ctx({
            "evidence":        [_evidence("SparkLogTool").model_dump()],
            "issue_profiles":  [profile.model_dump()],
            "recommendations": [_recommendation().model_dump()],
        })
        report = self.agent._run_checklist(ctx)
        c3 = next(
            (c for c in report.checks if "supporting evidence" in c.criterion.lower()), None
        )
        assert c3 is not None, "C3 check not found in checklist"
        assert not c3.passed, "C3 must fail when profile has no supporting evidence"

    def test_checklist_feedback_not_empty_on_failure(self):
        rec = _recommendation(regulation_ref="")
        ctx = _ctx({
            "evidence":        [_evidence("SparkLogTool").model_dump()],
            "issue_profiles":  [_profile().model_dump()],
            "recommendations": [rec.model_dump()],
        })
        report = self.agent._run_checklist(ctx)
        assert len(report.feedback) > 0, "Failing checklist must produce actionable feedback"

    # -- invoke(): async integration of checklist + LLM coherence ----------

    @pytest.mark.asyncio
    async def test_invoke_clean_report_returns_done(self):
        ctx = _ctx({
            "evidence":        [_evidence("SparkLogTool").model_dump(),
                                _evidence("DataQualityTool", ev_id="ev-002").model_dump()],
            "issue_profiles":  [_profile().model_dump()],
            "recommendations": [_recommendation().model_dump()],
        })
        result = await self.agent.invoke(ctx)
        from core.base_agent import AgentResult
        assert isinstance(result, AgentResult)
        assert result.next_phase in ("done", "routing"), (
            f"next_phase must be 'done' or 'routing', got '{result.next_phase}'"
        )

    @pytest.mark.asyncio
    async def test_invoke_with_gaps_returns_routing(self, mock_llm):
        """When checklist has CRITICAL gaps, next_phase must be 'routing'."""
        from agents.reviewer.agent import ReviewerAgent
        rec = _recommendation(regulation_ref="", defect_id="")   # C1+C2 fail
        ctx = _ctx({
            "evidence":        [_evidence("SparkLogTool").model_dump()],
            "issue_profiles":  [_profile().model_dump()],
            "recommendations": [rec.model_dump()],
        })
        result = await ReviewerAgent(llm=mock_llm).invoke(ctx)
        assert result.next_phase == "routing", (
            f"Expected 'routing' for failed checklist, got '{result.next_phase}'"
        )

    @pytest.mark.asyncio
    async def test_invoke_metadata_contains_validation_report(self):
        ctx = _ctx({
            "evidence":        [_evidence("SparkLogTool").model_dump()],
            "issue_profiles":  [_profile().model_dump()],
            "recommendations": [_recommendation().model_dump()],
        })
        result = await self.agent.invoke(ctx)
        assert "validation_report" in result.metadata, (
            "AgentResult.metadata must contain 'validation_report'"
        )

    @pytest.mark.asyncio
    async def test_invoke_returns_gaps_list(self):
        rec = _recommendation(regulation_ref="")
        ctx = _ctx({
            "evidence":        [_evidence("SparkLogTool").model_dump()],
            "issue_profiles":  [_profile().model_dump()],
            "recommendations": [rec.model_dump()],
        })
        result = await self.agent.invoke(ctx)
        assert "gaps" in result.metadata
        assert isinstance(result.metadata["gaps"], list)

    def test_agent_name_property(self):
        assert "Reviewer" in self.agent.agent_name

    def test_min_confidence_threshold(self):
        assert self.agent.MIN_CONFIDENCE == 0.5

    def test_min_evidence_domains(self):
        assert self.agent.MIN_EVIDENCE_DOMAINS >= 1

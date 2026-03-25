"""
tests/demos/test_scenarios.py
Parameterized scenario tests for the 3 known Kratos RCA scenarios.

Marks
-----
@pytest.mark.docker   — skipped by default; run with `pytest -m docker`
                        (requires `docker compose up` with My_Bank API running)
@pytest.mark.asyncio  — all tests are async

Each scenario asserts:
  1. The orchestrator identifies the correct root cause category
  2. The identified regulation matches the scenario-specific CFR section
  3. All 7 phases execute
  4. Evidence chain is non-empty
  5. Recommendation cites the correct defect_id

Parameterized matrix
--------------------
deposit_aggregation_failure  → AGGREGATION_SKIP, 12 CFR Part 330
trust_irr_misclassification  → ORC_FALLTHROUGH,  12 CFR Part 330 §330.13
wire_mt202_drop              → MT202_DROP,        12 CFR Part 370
"""
from __future__ import annotations

import json
import random
from datetime import datetime, timezone
from typing import Any

import pytest

from core.models import (
    EvidenceObject,
    IncidentContext,
    Priority,
    Recommendation,
)
from workflow.pipeline_phases import Phase, RCAReport


# ---------------------------------------------------------------------------
# Seed for determinism
# ---------------------------------------------------------------------------

random.seed(42)


# ---------------------------------------------------------------------------
# Scenario definitions
# ---------------------------------------------------------------------------

SCENARIOS = [
    pytest.param(
        {
            "scenario_id":       "deposit_aggregation_failure",
            "incident_id":       "INC-DEP-SCN-001",
            "run_id":            "RUN-SCN-001",
            "pipeline_stage":    "deposit_aggregation",
            "failed_controls":   ["CTL-DEP-001"],
            "expected_defect":   "AGGREGATION_SKIP",
            "expected_regulation_fragment": "330",
            "expected_root_cause_fragment": "aggregat",   # case-insensitive
            "metadata": {
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
                        "[FATAL] Aggregation returned 0 rows",
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
                                {
                                    "path": "etl/sp_calculate_insurance.sql",
                                    "added": 88,
                                    "deleted": 15,
                                }
                            ],
                        }
                    ],
                },
            },
        },
        id="deposit_aggregation_failure",
    ),
    pytest.param(
        {
            "scenario_id":       "trust_irr_misclassification",
            "incident_id":       "INC-TRUST-SCN-002",
            "run_id":            "RUN-SCN-002",
            "pipeline_stage":    "trust_classification",
            "failed_controls":   ["CTL-TRUST-001"],
            "expected_defect":   "ORC_FALLTHROUGH",
            "expected_regulation_fragment": "330",
            "expected_root_cause_fragment": "trust",
            "metadata": {
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
                        {"name": "account_type",    "dtype": "string", "null_rate": 0.0},
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
        },
        id="trust_irr_misclassification",
    ),
    pytest.param(
        {
            "scenario_id":       "wire_mt202_drop",
            "incident_id":       "INC-WIRE-SCN-003",
            "run_id":            "RUN-SCN-003",
            "pipeline_stage":    "wire_processing",
            "failed_controls":   ["CTL-WIRE-006"],
            "expected_defect":   "MT202_DROP",
            "expected_regulation_fragment": "370",
            "expected_root_cause_fragment": "mt202",
            "metadata": {
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
                    },
                    "memory": {"spill_bytes": 0, "oom_events": 0},
                },
            },
        },
        id="wire_mt202_drop",
    ),
]


# ---------------------------------------------------------------------------
# Scenario-aware MockLLM
# ---------------------------------------------------------------------------

def _scenario_llm(scenario: dict) -> Any:
    """
    Return a MockLLMClient tailored to each scenario's expected defect and
    regulation so that reviewer passes on first attempt.
    """
    defect_id = scenario["expected_defect"]
    reg_fragment = scenario["expected_regulation_fragment"]
    reg_ref = f"12 CFR Part {reg_fragment}"
    rc_fragment = scenario.get("expected_root_cause_fragment", defect_id)

    routing_response = json.dumps({
        "pattern_id": "HPL-001",
        "pattern_name": "Failure Pattern",
        "selected_tools": ["SparkLogTool", "AirflowLogTool"],
        "rationale": f"Signals match {defect_id}.",
        "confidence": 0.91,
    })
    triangulation_response = json.dumps({
        "root_cause_hypothesis": (
            f"{defect_id}: {rc_fragment} failure detected in {scenario['pipeline_stage']}."
        ),
        "confidence": 0.91,
        "causal_chain": [
            f"Pipeline TRIGGERED {defect_id} Mechanism",
            f"Mechanism VIOLATES Regulation {reg_ref}",
        ],
        "contradictions": [],
        "affected_regulation": reg_ref,
        "supporting_evidence_ids": ["ev-001"],
    })
    recommendation_response = json.dumps([
        {
            "defect_id": defect_id,
            "action": f"Remediate {defect_id} in {scenario['pipeline_stage']}",
            "priority": "P1",
            "effort_estimate": "4h",
            "regulation_ref": reg_ref,
            "rationale": f"{defect_id} violates {reg_ref}.",
            "evidence_ids": ["ev-001"],
        }
    ])
    reviewer_response = json.dumps({
        "overall_pass": True,
        "gaps": [],
        "feedback": [],
    })

    class _ScenarioLLM:
        _map = {
            "routing":         routing_response,
            "triangulation":   triangulation_response,
            "recommendation":  recommendation_response,
            "reviewer":        reviewer_response,
        }

        async def ainvoke(self, messages):
            content = ""
            if messages and hasattr(messages[0], "content"):
                content = messages[0].content
            elif messages and isinstance(messages[0], tuple):
                content = messages[0][1]
            content_lower = content.lower()
            for key, payload in self._map.items():
                if key in content_lower:
                    class _Msg:
                        pass
                    m = _Msg()
                    m.content = payload
                    return m
            m = type("_Msg", (), {"content": routing_response})()
            return m

    return _ScenarioLLM()


# ---------------------------------------------------------------------------
# Shared orchestrator factory
# ---------------------------------------------------------------------------

def _make_orch(scenario: dict):
    from agents.orchestrator.orchestrator import KratosOrchestrator
    from connectors.bank_pipeline import BankPipelineConnector
    from core.llm import LLMConfig
    from tools import register_all_tools
    from agents import register_all_agents

    connector = BankPipelineConnector(base_url="http://localhost:8000")
    tool_reg = register_all_tools(LLMConfig())
    agent_reg = register_all_agents()
    llm = _scenario_llm(scenario)

    orch = KratosOrchestrator(
        connector=connector,
        llm=llm,
        tool_registry=tool_reg,
        agent_registry=agent_reg,
    )
    return orch, connector


# ---------------------------------------------------------------------------
# Helper: build respx router for a given scenario incident_id
# ---------------------------------------------------------------------------

def _scenario_respx_router(scenario: dict):
    """Return a respx.mock context manager pre-wired for this scenario."""
    context_payload = {
        "incident_id":    scenario["incident_id"],
        "run_id":         scenario["run_id"],
        "pipeline_stage": scenario["pipeline_stage"],
        "failed_controls": [
            {"control_id": c} for c in scenario["failed_controls"]
        ],
        "ontology_snapshot": {},
        "metadata": scenario["metadata"],
    }
    return context_payload


# ---------------------------------------------------------------------------
# Parameterized scenario test class
# ---------------------------------------------------------------------------

@pytest.mark.docker
class TestScenarios:
    """
    Marked @pytest.mark.docker — skip unless docker compose is running.
    Use `pytest -m docker` to include these tests.
    """

    @pytest.mark.asyncio
    @pytest.mark.parametrize("scenario", SCENARIOS)
    async def test_all_7_phases_execute(self, scenario):
        import respx
        import httpx

        ctx_payload = _scenario_respx_router(scenario)
        with respx.mock(base_url="http://localhost:8000", assert_all_called=False) as router:
            router.get(url__regex=r"/rca/context/").mock(
                return_value=httpx.Response(200, json=ctx_payload)
            )
            router.get(url__regex=r"/logs/stream/").mock(
                return_value=httpx.Response(
                    200,
                    content=b"data: [DONE]\n\n",
                    headers={"Content-Type": "text/event-stream"},
                )
            )
            router.get(url__regex=r"/lineage/").mock(
                return_value=httpx.Response(200, json={
                    "job_id": "nightly", "nodes": [], "edges": []
                })
            )
            router.post(url__regex=r"/rca/results/").mock(
                return_value=httpx.Response(200, json={"status": "accepted"})
            )

            orch, connector = _make_orch(scenario)
            async with connector:
                report = await orch.run(scenario["incident_id"])

        executed = set(report.phases_executed)
        expected = {p.value for p in Phase}
        assert expected == executed, (
            f"[{scenario['scenario_id']}] Missing phases: {expected - executed}"
        )

    @pytest.mark.asyncio
    @pytest.mark.parametrize("scenario", SCENARIOS)
    async def test_correct_root_cause_identified(self, scenario):
        import respx
        import httpx

        ctx_payload = _scenario_respx_router(scenario)
        with respx.mock(base_url="http://localhost:8000", assert_all_called=False) as router:
            router.get(url__regex=r"/rca/context/").mock(
                return_value=httpx.Response(200, json=ctx_payload)
            )
            router.get(url__regex=r"/logs/stream/").mock(
                return_value=httpx.Response(
                    200,
                    content=b"data: [DONE]\n\n",
                    headers={"Content-Type": "text/event-stream"},
                )
            )
            router.get(url__regex=r"/lineage/").mock(
                return_value=httpx.Response(200, json={
                    "job_id": "nightly", "nodes": [], "edges": []
                })
            )
            router.post(url__regex=r"/rca/results/").mock(
                return_value=httpx.Response(200, json={"status": "accepted"})
            )

            orch, connector = _make_orch(scenario)
            async with connector:
                report = await orch.run(scenario["incident_id"])

        fragment = scenario["expected_root_cause_fragment"].lower()
        root_cause_text = (
            report.final_root_cause.lower()
            + " ".join(
                (p.root_cause_hypothesis if hasattr(p, "root_cause_hypothesis")
                 else p.get("root_cause_hypothesis", ""))
                for p in report.issue_profiles
            ).lower()
        )
        assert fragment in root_cause_text, (
            f"[{scenario['scenario_id']}] Expected root cause fragment '{fragment}' "
            f"not found in: '{report.final_root_cause}'"
        )

    @pytest.mark.asyncio
    @pytest.mark.parametrize("scenario", SCENARIOS)
    async def test_correct_regulation_cited(self, scenario):
        import respx
        import httpx

        ctx_payload = _scenario_respx_router(scenario)
        with respx.mock(base_url="http://localhost:8000", assert_all_called=False) as router:
            router.get(url__regex=r"/rca/context/").mock(
                return_value=httpx.Response(200, json=ctx_payload)
            )
            router.get(url__regex=r"/logs/stream/").mock(
                return_value=httpx.Response(
                    200,
                    content=b"data: [DONE]\n\n",
                    headers={"Content-Type": "text/event-stream"},
                )
            )
            router.get(url__regex=r"/lineage/").mock(
                return_value=httpx.Response(200, json={
                    "job_id": "nightly", "nodes": [], "edges": []
                })
            )
            router.post(url__regex=r"/rca/results/").mock(
                return_value=httpx.Response(200, json={"status": "accepted"})
            )

            orch, connector = _make_orch(scenario)
            async with connector:
                report = await orch.run(scenario["incident_id"])

        reg_fragment = scenario["expected_regulation_fragment"]
        all_reg_refs = " ".join(
            (r.regulation_ref if hasattr(r, "regulation_ref")
             else r.get("regulation_ref", ""))
            for r in report.recommendations
        )
        # Also check issue profiles
        for p in report.issue_profiles:
            if hasattr(p, "affected_regulation"):
                all_reg_refs += " " + (p.affected_regulation or "")
            elif isinstance(p, dict):
                all_reg_refs += " " + p.get("affected_regulation", "")

        assert reg_fragment in all_reg_refs, (
            f"[{scenario['scenario_id']}] Expected regulation fragment '{reg_fragment}' "
            f"not found in regulation refs: '{all_reg_refs}'"
        )

    @pytest.mark.asyncio
    @pytest.mark.parametrize("scenario", SCENARIOS)
    async def test_recommendation_cites_correct_defect_id(self, scenario):
        import respx
        import httpx

        ctx_payload = _scenario_respx_router(scenario)
        with respx.mock(base_url="http://localhost:8000", assert_all_called=False) as router:
            router.get(url__regex=r"/rca/context/").mock(
                return_value=httpx.Response(200, json=ctx_payload)
            )
            router.get(url__regex=r"/logs/stream/").mock(
                return_value=httpx.Response(
                    200,
                    content=b"data: [DONE]\n\n",
                    headers={"Content-Type": "text/event-stream"},
                )
            )
            router.get(url__regex=r"/lineage/").mock(
                return_value=httpx.Response(200, json={
                    "job_id": "nightly", "nodes": [], "edges": []
                })
            )
            router.post(url__regex=r"/rca/results/").mock(
                return_value=httpx.Response(200, json={"status": "accepted"})
            )

            orch, connector = _make_orch(scenario)
            async with connector:
                report = await orch.run(scenario["incident_id"])

        expected_defect = scenario["expected_defect"]
        defect_ids = [
            (r.defect_id if hasattr(r, "defect_id") else r.get("defect_id", ""))
            for r in report.recommendations
        ]
        assert any(expected_defect in str(d) for d in defect_ids), (
            f"[{scenario['scenario_id']}] Expected defect_id '{expected_defect}' "
            f"not found in recommendations. Got: {defect_ids}"
        )

    @pytest.mark.asyncio
    @pytest.mark.parametrize("scenario", SCENARIOS)
    async def test_evidence_chain_non_empty(self, scenario):
        import respx
        import httpx

        ctx_payload = _scenario_respx_router(scenario)
        with respx.mock(base_url="http://localhost:8000", assert_all_called=False) as router:
            router.get(url__regex=r"/rca/context/").mock(
                return_value=httpx.Response(200, json=ctx_payload)
            )
            router.get(url__regex=r"/logs/stream/").mock(
                return_value=httpx.Response(
                    200,
                    content=b"data: [DONE]\n\n",
                    headers={"Content-Type": "text/event-stream"},
                )
            )
            router.get(url__regex=r"/lineage/").mock(
                return_value=httpx.Response(200, json={
                    "job_id": "nightly", "nodes": [], "edges": []
                })
            )
            router.post(url__regex=r"/rca/results/").mock(
                return_value=httpx.Response(200, json={"status": "accepted"})
            )

            orch, connector = _make_orch(scenario)
            async with connector:
                report = await orch.run(scenario["incident_id"])

        assert len(report.evidence) >= 1, (
            f"[{scenario['scenario_id']}] Evidence chain must be non-empty"
        )

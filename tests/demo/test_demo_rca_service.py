"""
tests/demo/test_demo_rca_service.py

Integration tests for DemoRcaService — 7-phase in-memory RCA.

Design:
  - Uses the real ScenarioRegistry (reads from scenarios/ folder).
  - No external APIs, no Neo4j, no LLM.
  - Each test runs the full pipeline via asyncio.
"""

from __future__ import annotations

import asyncio
from typing import List

import pytest
import pytest_asyncio

from causelink.state.investigation import InvestigationStatus, HypothesisStatus
from demo.scenario_registry import ScenarioRegistry
from demo.services.demo_rca_service import DemoRcaService, PhaseEvent

SCENARIO_IDS = [
    "deposit_aggregation_failure",
    "trust_irr_misclassification",
    "wire_mt202_drop",
]

# Expected log-signal strings per scenario
LOG_SIGNALS = {
    "deposit_aggregation_failure": "AGGRSTEP — skipped (disabled in JCL)",
    "trust_irr_misclassification": "fallback ORC=SGL (IRR not implemented)",
    "wire_mt202_drop":             "silently dropped (no handler)",
}


# ── Fixtures ─────────────────────────────────────────────────────────────────

@pytest.fixture(scope="module")
def registry() -> ScenarioRegistry:
    return ScenarioRegistry()


@pytest.fixture(scope="module")
def service(registry: ScenarioRegistry) -> DemoRcaService:
    return DemoRcaService(registry)


# Helper: run full investigation and collect all events

async def _run_full(service: DemoRcaService, scenario_id: str) -> tuple[str, List[PhaseEvent]]:
    pack = service._registry.get_pack(scenario_id)
    inv_id = await service.start_investigation(scenario_id, pack.job_id)
    events: List[PhaseEvent] = []
    async for ev in service.stream(inv_id):
        events.append(ev)
    return inv_id, events


# ── Phase count and structure ─────────────────────────────────────────────────

class TestPhaseStructure:

    @pytest.mark.asyncio
    @pytest.mark.parametrize("scenario_id", SCENARIO_IDS)
    async def test_all_seven_phases_emitted(
        self, service: DemoRcaService, scenario_id: str
    ) -> None:
        _, events = await _run_full(service, scenario_id)
        phase_names = {e.phase for e in events}
        expected = {"INTAKE", "LOGS_FIRST", "ROUTE", "BACKTRACK", "INCIDENT_CARD", "RECOMMEND", "PERSIST"}
        assert expected.issubset(phase_names), f"Missing phases: {expected - phase_names}"

    @pytest.mark.asyncio
    @pytest.mark.parametrize("scenario_id", SCENARIO_IDS)
    async def test_phase_numbers_sequential(
        self, service: DemoRcaService, scenario_id: str
    ) -> None:
        _, events = await _run_full(service, scenario_id)
        # Filter out ERROR phase if any
        numbered = sorted(
            [e for e in events if e.phase_number > 0], key=lambda e: e.phase_number
        )
        for i, ev in enumerate(numbered, start=1):
            assert ev.phase_number == i

    @pytest.mark.asyncio
    @pytest.mark.parametrize("scenario_id", SCENARIO_IDS)
    async def test_persist_phase_is_last(
        self, service: DemoRcaService, scenario_id: str
    ) -> None:
        _, events = await _run_full(service, scenario_id)
        last = events[-1]
        assert last.phase == "PERSIST"

    @pytest.mark.asyncio
    @pytest.mark.parametrize("scenario_id", SCENARIO_IDS)
    async def test_no_error_phases(
        self, service: DemoRcaService, scenario_id: str
    ) -> None:
        _, events = await _run_full(service, scenario_id)
        error_phases = [e for e in events if e.phase == "ERROR"]
        assert error_phases == [], f"Unexpected ERROR phase(s): {error_phases}"


# ── Final state correctness ───────────────────────────────────────────────────

class TestFinalState:

    @pytest.mark.asyncio
    @pytest.mark.parametrize("scenario_id", SCENARIO_IDS)
    async def test_state_completed(
        self, service: DemoRcaService, scenario_id: str
    ) -> None:
        inv_id, _ = await _run_full(service, scenario_id)
        state = service.get_state(inv_id)
        assert state is not None
        assert state.status == InvestigationStatus.COMPLETED

    @pytest.mark.asyncio
    @pytest.mark.parametrize("scenario_id", SCENARIO_IDS)
    async def test_root_cause_final_set(
        self, service: DemoRcaService, scenario_id: str
    ) -> None:
        inv_id, _ = await _run_full(service, scenario_id)
        state = service.get_state(inv_id)
        assert state is not None
        assert state.root_cause_final is not None

    @pytest.mark.asyncio
    @pytest.mark.parametrize("scenario_id", SCENARIO_IDS)
    async def test_root_cause_confirmed(
        self, service: DemoRcaService, scenario_id: str
    ) -> None:
        inv_id, _ = await _run_full(service, scenario_id)
        state = service.get_state(inv_id)
        assert state is not None
        rc = state.root_cause_final
        assert rc is not None
        assert rc.status == HypothesisStatus.CONFIRMED

    @pytest.mark.asyncio
    @pytest.mark.parametrize("scenario_id", SCENARIO_IDS)
    async def test_composite_score_above_threshold(
        self, service: DemoRcaService, scenario_id: str
    ) -> None:
        inv_id, _ = await _run_full(service, scenario_id)
        state = service.get_state(inv_id)
        assert state is not None
        rc = state.root_cause_final
        assert rc is not None
        assert rc.composite_score >= 0.70, (
            f"composite_score {rc.composite_score} < 0.70 threshold"
        )

    @pytest.mark.asyncio
    @pytest.mark.parametrize("scenario_id", SCENARIO_IDS)
    async def test_evidence_objects_populated(
        self, service: DemoRcaService, scenario_id: str
    ) -> None:
        inv_id, _ = await _run_full(service, scenario_id)
        state = service.get_state(inv_id)
        assert state is not None
        assert len(state.evidence_objects) >= 1

    @pytest.mark.asyncio
    @pytest.mark.parametrize("scenario_id", SCENARIO_IDS)
    async def test_hypotheses_populated(
        self, service: DemoRcaService, scenario_id: str
    ) -> None:
        inv_id, _ = await _run_full(service, scenario_id)
        state = service.get_state(inv_id)
        assert state is not None
        assert len(state.hypotheses) >= 1

    @pytest.mark.asyncio
    @pytest.mark.parametrize("scenario_id", SCENARIO_IDS)
    async def test_causal_edges_populated(
        self, service: DemoRcaService, scenario_id: str
    ) -> None:
        inv_id, _ = await _run_full(service, scenario_id)
        state = service.get_state(inv_id)
        assert state is not None
        assert len(state.causal_graph_edges) >= 1

    @pytest.mark.asyncio
    @pytest.mark.parametrize("scenario_id", SCENARIO_IDS)
    async def test_recommendations_populated(
        self, service: DemoRcaService, scenario_id: str
    ) -> None:
        inv_id, _ = await _run_full(service, scenario_id)
        state = service.get_state(inv_id)
        assert state is not None
        assert len(state.recommended_actions) >= 1

    @pytest.mark.asyncio
    @pytest.mark.parametrize("scenario_id", SCENARIO_IDS)
    async def test_audit_trace_populated(
        self, service: DemoRcaService, scenario_id: str
    ) -> None:
        inv_id, _ = await _run_full(service, scenario_id)
        state = service.get_state(inv_id)
        assert state is not None
        assert len(state.audit_trace) >= 7, (
            "Expected at least one audit entry per phase"
        )


# ── Log signal detection ───────────────────────────────────────────────────────

class TestLogSignalDetection:

    @pytest.mark.asyncio
    @pytest.mark.parametrize("scenario_id", SCENARIO_IDS)
    async def test_logs_first_phase_detects_signal(
        self, service: DemoRcaService, scenario_id: str
    ) -> None:
        _, events = await _run_full(service, scenario_id)
        log_phase = next(e for e in events if e.phase == "LOGS_FIRST")
        assert log_phase.status == "SIGNAL_DETECTED"

    @pytest.mark.asyncio
    @pytest.mark.parametrize("scenario_id", SCENARIO_IDS)
    async def test_route_phase_ok(
        self, service: DemoRcaService, scenario_id: str
    ) -> None:
        _, events = await _run_full(service, scenario_id)
        route_phase = next(e for e in events if e.phase == "ROUTE")
        assert route_phase.status == "OK"
        assert "evidence_id" in route_phase.details


# ── Pattern IDs ───────────────────────────────────────────────────────────────

class TestPatternIds:

    @pytest.mark.asyncio
    async def test_deposit_uses_agg_pattern(self, service: DemoRcaService) -> None:
        _, events = await _run_full(service, "deposit_aggregation_failure")
        bt = next(e for e in events if e.phase == "BACKTRACK")
        assert bt.details.get("pattern_id") == "DEMO-AGG-001"

    @pytest.mark.asyncio
    async def test_trust_uses_irr_pattern(self, service: DemoRcaService) -> None:
        _, events = await _run_full(service, "trust_irr_misclassification")
        bt = next(e for e in events if e.phase == "BACKTRACK")
        assert bt.details.get("pattern_id") == "DEMO-IRR-001"

    @pytest.mark.asyncio
    async def test_wire_uses_mt202_pattern(self, service: DemoRcaService) -> None:
        _, events = await _run_full(service, "wire_mt202_drop")
        bt = next(e for e in events if e.phase == "BACKTRACK")
        assert bt.details.get("pattern_id") == "DEMO-MT202-001"


# ── Error handling ────────────────────────────────────────────────────────────

class TestErrorHandling:

    @pytest.mark.asyncio
    async def test_unknown_scenario_raises(self, service: DemoRcaService) -> None:
        with pytest.raises(KeyError):
            await service.start_investigation("ghost_scenario", "JOB-001")

    @pytest.mark.asyncio
    async def test_stream_unknown_investigation_raises(
        self, service: DemoRcaService
    ) -> None:
        with pytest.raises(KeyError):
            async for _ in service.stream("investigation-does-not-exist"):
                pass

    def test_get_state_unknown_returns_none(self, service: DemoRcaService) -> None:
        assert service.get_state("investigation-does-not-exist") is None

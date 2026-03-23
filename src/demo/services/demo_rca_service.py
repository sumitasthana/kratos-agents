"""
src/demo/services/demo_rca_service.py

DemoRcaService — orchestrates the full 7-phase demo RCA run in-memory.

Design:
  - All reasoning is deterministic and pattern-based (no LLM, no Neo4j).
  - Each of the 7 phases appends to InvestigationState and yields one SSE event.
  - An asyncio.Queue per investigation drives the SSE stream.
  - Three demo scenarios each have a hard-coded log signal and pattern_id.

Phase flow:
  1. INTAKE          — validate scenario, seed InvestigationState
  2. LOGS_FIRST      — detect log signal, build EvidenceObject from log
  3. ROUTE           — resolve pattern from library, attach evidence
  4. BACKTRACK       — build Hypothesis + CausalEdge chain
  5. INCIDENT_CARD   — synthesize structured incident summary
  6. RECOMMEND       — generate grounded remediation actions
  7. PERSIST         — compute confidence, set root_cause_final, finalize

Usage::

    service = DemoRcaService(registry)
    inv_id  = await service.start_investigation("deposit_aggregation_failure", "DAILY-INSURANCE-JOB-20260316")
    async for event in service.stream(inv_id):
        print(event)  # PhaseEvent JSON
"""

from __future__ import annotations

import asyncio
import json
import logging
import time
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, AsyncIterator, Dict, List, Optional

# Observability — imported lazily so the service still starts if the
# observability package is not yet installed (e.g. during initial setup).
try:
    from src.observability.metrics import M as _M
    from src.observability.logger import get_logger as _get_logger, LogEvent
    from src.observability.events import emit as _emit, EventName
    from src.observability.tracer import get_tracer as _get_tracer, SpanAttr
    _OBS_AVAILABLE = True
except ImportError:  # pragma: no cover
    _OBS_AVAILABLE = False

from causelink.evidence.contracts import (
    EvidenceObject,
    EvidenceReliabilityTier,
    EvidenceType,
)
from causelink.ontology.models import OntologyPath
from causelink.patterns.library import HypothesisPattern, HypothesisPatternLibrary
from causelink.state.investigation import (
    AuditTraceEntry,
    CausalEdge,
    CausalEdgeStatus,
    Hypothesis,
    HypothesisStatus,
    InvestigationState,
    InvestigationStatus,
    RootCauseCandidate,
)

from ..loaders.operational_adapter import OperationalAdapter
from ..loaders.scenario_loader import ScenarioPack
from ..ontology.scenario_seeder import ScenarioSeeder
from ..scenario_registry import ScenarioRegistry
from .confidence_calculator import ConfidenceCalculator

# ---------------------------------------------------------------------------
# Lazy-load infrastructure adapter (optional — demo works without it)
# ---------------------------------------------------------------------------

def _load_default_infra_adapter():
    """Return a KratosDemoAdapter instance, or None if unavailable."""
    try:
        from src.infrastructure.adapters.kratos_demo_adapter import KratosDemoAdapter  # noqa: PLC0415
        return KratosDemoAdapter()
    except Exception as _exc:
        logger.warning("Could not load KratosDemoAdapter: %s", _exc)
        return None

# Use structured JSON logger when observability stack is available;
# fall back to standard stdlib logger otherwise.
if _OBS_AVAILABLE:
    logger = _get_logger(__name__)
else:
    logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Log signal registry — one entry per demo scenario
# ---------------------------------------------------------------------------

_LOG_SIGNALS: Dict[str, str] = {
    "deposit_aggregation_failure": "AGGRSTEP — skipped (disabled in JCL)",
    "trust_irr_misclassification": "fallback ORC=SGL (IRR not implemented)",
    "wire_mt202_drop":             "silently dropped (no handler)",
}

_PATTERN_IDS: Dict[str, str] = {
    "deposit_aggregation_failure": "DEMO-AGG-001",
    "trust_irr_misclassification": "DEMO-IRR-001",
    "wire_mt202_drop":             "DEMO-MT202-001",
}

# Root-cause node IDs (Script/Artifact nodes — leaf of the causal chain)
_ROOT_CAUSE_NODE_IDS: Dict[str, str] = {
    "deposit_aggregation_failure": "node-daf-art-jcl",
    "trust_irr_misclassification": "node-tim-art-bcj",
    "wire_mt202_drop":             "node-wmd-art-swp",
}

# All causal chain node IDs for each scenario (leaf → root, reversed for edges)
_CAUSAL_CHAIN_NODE_IDS: Dict[str, List[str]] = {
    "deposit_aggregation_failure": [
        "node-daf-ctl-c2",
        "node-daf-rul-agg",
        "node-daf-pip-dij",
        "node-daf-stp-agg",
        "node-daf-art-jcl",
    ],
    "trust_irr_misclassification": [
        "node-tim-ctl-a3",
        "node-tim-rul-irr",
        "node-tim-pip-tdb",
        "node-tim-art-cob",
        "node-tim-art-bcj",
    ],
    "wire_mt202_drop": [
        "node-wmd-ctl-b1",
        "node-wmd-rul-swf",
        "node-wmd-pip-wnr",
        "node-wmd-mod-swp",
        "node-wmd-art-swp",
    ],
}

# Confidence scores — these produce composite=0.898 (CONFIRMED, ≥ 0.80)
_CONFIDENCE_SCORES: Dict[str, dict] = {
    "deposit_aggregation_failure": {
        "evidence": 0.92, "temporal": 0.90, "depth": 0.85, "hypothesis": 0.90
    },
    "trust_irr_misclassification": {
        "evidence": 0.91, "temporal": 0.88, "depth": 0.85, "hypothesis": 0.88
    },
    "wire_mt202_drop": {
        "evidence": 0.94, "temporal": 0.92, "depth": 0.85, "hypothesis": 0.92
    },
}


# ---------------------------------------------------------------------------
# Phase event model
# ---------------------------------------------------------------------------

@dataclass
class PhaseEvent:
    """A single SSE event emitted after each phase completes."""

    phase: str
    phase_number: int
    investigation_id: str
    scenario_id: str
    status: str
    summary: str
    details: Dict[str, Any] = field(default_factory=dict)
    emitted_at: str = field(default_factory=lambda: datetime.utcnow().isoformat())
    # SSE event discriminator — consumers use this to route events.
    # Legacy consumers that pre-date this field treat all events as PHASE_COMPLETE.
    type: Optional[str] = field(default=None)

    def to_json(self) -> str:
        payload: Dict[str, Any] = {
            "phase":           self.phase,
            "phase_number":    self.phase_number,
            "investigation_id": self.investigation_id,
            "scenario_id":     self.scenario_id,
            "status":          self.status,
            "summary":         self.summary,
            "details":         self.details,
            "emitted_at":      self.emitted_at,
        }
        if self.type is not None:
            payload["type"] = self.type
        return json.dumps(payload)


@dataclass
class PhaseResult:
    """Full result after all 7 phases complete."""

    investigation_id: str
    scenario_id: str
    state: InvestigationState
    events: List[PhaseEvent]
    completed_at: str = field(default_factory=lambda: datetime.utcnow().isoformat())


# ---------------------------------------------------------------------------
# DemoRcaService
# ---------------------------------------------------------------------------

class DemoRcaService:
    """
    Orchestrates the 7-phase demo RCA run for a given scenario.

    Internally runs phases sequentially in a background coroutine,
    putting PhaseEvent objects into a per-investigation asyncio.Queue.
    The SSE endpoint consumes from this queue via stream().
    """

    def __init__(
        self,
        registry: ScenarioRegistry,
        library: Optional[HypothesisPatternLibrary] = None,
        adapter: Optional[OperationalAdapter] = None,
        calculator: Optional[ConfidenceCalculator] = None,
        infra_adapter: Optional[Any] = None,
    ) -> None:
        self._registry = registry
        self._library = library or HypothesisPatternLibrary()
        self._adapter = adapter or OperationalAdapter()
        self._calc = calculator or ConfidenceCalculator()
        self._seeder = ScenarioSeeder()
        # InfrastructureAdapter for LLM-powered agent reasoning.
        # Loaded lazily so the service starts even if the adapter package
        # is not yet installed.
        self._infra_adapter = infra_adapter if infra_adapter is not None else _load_default_infra_adapter()

        # investigation_id → InvestigationState
        self._states: Dict[str, InvestigationState] = {}
        # investigation_id → asyncio.Queue[Optional[PhaseEvent]]
        # None sentinel marks end-of-stream.
        self._queues: Dict[str, asyncio.Queue] = {}
        # investigation_id → scenario_id
        self._scenario_map: Dict[str, str] = {}

    # ------------------------------------------------------------------
    # Agent thought helpers
    # ------------------------------------------------------------------

    async def _drain_thoughts(
        self,
        thought_queue: asyncio.Queue,
        sse_queue: asyncio.Queue,
        inv_id: str,
        scenario_id: str,
        phase_name: str,
        phase_number: int,
    ) -> None:
        """Read ThoughtStep items from thought_queue and emit AGENT_THOUGHT events."""
        from causelink.reasoning.thought_trace import ThoughtStep as _TS  # noqa: PLC0415
        while True:
            item = await thought_queue.get()
            if item is None:
                break
            await sse_queue.put(PhaseEvent(
                phase=phase_name,
                phase_number=phase_number,
                investigation_id=inv_id,
                scenario_id=scenario_id,
                status="RUNNING",
                summary=f"{item.agent}: {item.thought_type}",
                details={
                    "agent":            item.agent,
                    "step_index":       item.step_index,
                    "thought_type":     item.thought_type,
                    "content":          item.content,
                    "evidence_refs":    item.evidence_refs,
                    "node_refs":        item.node_refs,
                    "confidence_delta": item.confidence_delta,
                },
                type="AGENT_THOUGHT",
            ))
            await asyncio.sleep(0)

    async def _run_agent_phase(
        self,
        agent_name: str,
        state: InvestigationState,
        context: dict,
        sse_queue: asyncio.Queue,
        inv_id: str,
        scenario_id: str,
        phase_number: int,
        phase_name: str,
    ) -> None:
        """
        Instantiate *agent_name*, run emit_thoughts(), drain to AGENT_THOUGHT SSE.

        Gracefully no-ops if the agent class cannot be imported or if no
        InfrastructureAdapter is available.
        """
        if self._infra_adapter is None:
            return  # no adapter — skip agent thoughts

        # Lazy-import the demo agent to avoid circular imports at module level
        _agent_map = {
            "DemoEvidenceAgent":     "src.demo.agents.demo_evidence_agent",
            "DemoRoutingAgent":      "src.demo.agents.demo_routing_agent",
            "DemoBacktrackingAgent": "src.demo.agents.demo_backtracking_agent",
            "DemoIncidentAgent":     "src.demo.agents.demo_incident_agent",
            "DemoRecommendAgent":    "src.demo.agents.demo_recommend_agent",
            "DemoRankerAgent":       "src.demo.agents.demo_ranker_agent",
        }
        module_path = _agent_map.get(agent_name)
        if module_path is None:
            return

        try:
            import importlib  # noqa: PLC0415
            mod = importlib.import_module(module_path)
            agent_cls = getattr(mod, agent_name)
            agent = agent_cls()
        except Exception as exc:
            logger.warning("Could not instantiate %s: %s", agent_name, exc)
            return

        thought_queue: asyncio.Queue = asyncio.Queue()
        drain_task = asyncio.create_task(
            self._drain_thoughts(
                thought_queue, sse_queue,
                inv_id, scenario_id, phase_name, phase_number,
            )
        )
        try:
            await agent.emit_thoughts(state, self._infra_adapter, context, thought_queue)
        except Exception as exc:
            logger.warning("Agent %s emit_thoughts failed: %s", agent_name, exc)
        finally:
            await thought_queue.put(None)  # sentinel to stop drain
            await drain_task

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    async def start_investigation(
        self, scenario_id: str, job_id: str
    ) -> str:
        """
        Start a new demo RCA investigation for *scenario_id* and *job_id*.

        Returns the investigation_id.  Phases run in a background task;
        use stream() to consume SSE events as they arrive.
        """
        if not self._registry.has_scenario(scenario_id):
            raise KeyError(
                f"Unknown scenario '{scenario_id}'. "
                f"Available: {self._registry.scenario_ids()}"
            )

        pack = self._registry.get_pack(scenario_id)
        state = self._seeder.seed(scenario_id, pack)
        investigation_id = state.investigation_input.investigation_id

        queue: asyncio.Queue = asyncio.Queue()
        self._states[investigation_id] = state
        self._queues[investigation_id] = queue
        self._scenario_map[investigation_id] = scenario_id

        # Observability: record start metrics + emit named event
        if _OBS_AVAILABLE:
            _M.investigations_started.labels(scenario_id=scenario_id).inc()
            _M.investigations_in_flight.inc()
            _emit(EventName.INVESTIGATION_STARTED,
                  investigation_id=investigation_id,
                  scenario_id=scenario_id,
                  job_id=job_id)

        # Launch phases as a background task
        asyncio.create_task(
            self._run_phases(investigation_id, scenario_id, pack, state, queue),
            name=f"demo-rca-{investigation_id[:8]}",
        )

        logger.info(
            "DemoRcaService: started investigation %s for scenario '%s'",
            investigation_id,
            scenario_id,
        )
        return investigation_id

    def get_state(self, investigation_id: str) -> Optional[InvestigationState]:
        """Return the current InvestigationState, or None if not found."""
        return self._states.get(investigation_id)

    def get_queue(self, investigation_id: str) -> asyncio.Queue:
        """Return the asyncio.Queue for a running investigation.

        Raises:
            KeyError: if the investigation_id is not known.
        """
        if investigation_id not in self._queues:
            raise KeyError(
                f"Investigation '{investigation_id}' not found. "
                "Start an investigation first with start_investigation()."
            )
        return self._queues[investigation_id]

    async def stream(
        self, investigation_id: str
    ) -> AsyncIterator[PhaseEvent]:
        """
        Async generator yielding PhaseEvents as each phase completes.

        Yields until the None sentinel is received (all 7 phases done).
        Raises KeyError if the investigation_id is not known.
        """
        if investigation_id not in self._queues:
            raise KeyError(
                f"Investigation '{investigation_id}' not found. "
                "Start an investigation first with start_investigation()."
            )
        queue = self._queues[investigation_id]
        while True:
            event = await queue.get()
            if event is None:
                break
            yield event

    # ------------------------------------------------------------------
    # Phase orchestration
    # ------------------------------------------------------------------

    async def _run_phases(
        self,
        investigation_id: str,
        scenario_id: str,
        pack: ScenarioPack,
        state: InvestigationState,
        queue: asyncio.Queue,
    ) -> None:
        try:
            # -- INTAKE --
            _t0 = time.perf_counter()
            await self._phase_intake(investigation_id, scenario_id, pack, state, queue)
            if _OBS_AVAILABLE:
                _M.phase_duration.labels(phase="INTAKE", scenario_id=scenario_id, status="PASS").observe((time.perf_counter() - _t0) * 1000)

            # -- LOGS_FIRST --
            await self._run_agent_phase(
                "DemoEvidenceAgent", state,
                {"scenario_id": scenario_id, "logs": pack.log_text[:3000], "job_run": pack.job_run},
                queue, investigation_id, scenario_id, 2, "LOGS_FIRST",
            )
            _t0 = time.perf_counter()
            await self._phase_logs_first(investigation_id, scenario_id, pack, state, queue)
            if _OBS_AVAILABLE:
                _M.phase_duration.labels(phase="LOGS_FIRST", scenario_id=scenario_id, status="PASS").observe((time.perf_counter() - _t0) * 1000)

            # -- ROUTE --
            await self._run_agent_phase(
                "DemoRoutingAgent", state,
                {"scenario_id": scenario_id},
                queue, investigation_id, scenario_id, 3, "ROUTE",
            )
            _t0 = time.perf_counter()
            evidence_id = await self._phase_route(
                investigation_id, scenario_id, pack, state, queue
            )
            if _OBS_AVAILABLE:
                _M.phase_duration.labels(phase="ROUTE", scenario_id=scenario_id, status="PASS").observe((time.perf_counter() - _t0) * 1000)
                _M.evidence_collected.labels(scenario_id=scenario_id, tier="SIGNAL").inc()

            # -- BACKTRACK --
            await self._run_agent_phase(
                "DemoBacktrackingAgent", state,
                {"scenario_id": scenario_id},
                queue, investigation_id, scenario_id, 4, "BACKTRACK",
            )
            _t0 = time.perf_counter()
            hypothesis_id = await self._phase_backtrack(
                investigation_id, scenario_id, pack, state, queue, evidence_id
            )
            if _OBS_AVAILABLE:
                _elapsed_bt = (time.perf_counter() - _t0) * 1000
                _M.phase_duration.labels(phase="BACKTRACK", scenario_id=scenario_id, status="PASS").observe(_elapsed_bt)
                _chain_len = len(_CAUSAL_CHAIN_NODE_IDS.get(scenario_id, []))
                _M.backtrack_hops.labels(scenario_id=scenario_id).observe(_chain_len)
                pattern_id = _PATTERN_IDS.get(scenario_id, "UNKNOWN")
                _M.hypotheses_created.labels(scenario_id=scenario_id, pattern_id=pattern_id).inc()
                _M.hypotheses_promoted.labels(scenario_id=scenario_id, pattern_id=pattern_id).inc()

            # -- INCIDENT_CARD --
            await self._run_agent_phase(
                "DemoIncidentAgent", state,
                {"scenario_id": scenario_id},
                queue, investigation_id, scenario_id, 5, "INCIDENT_CARD",
            )
            _t0 = time.perf_counter()
            await self._phase_incident_card(
                investigation_id, scenario_id, pack, state, queue
            )
            if _OBS_AVAILABLE:
                _M.phase_duration.labels(phase="INCIDENT_CARD", scenario_id=scenario_id, status="PASS").observe((time.perf_counter() - _t0) * 1000)

            # -- RECOMMEND --
            await self._run_agent_phase(
                "DemoRecommendAgent", state,
                {"scenario_id": scenario_id},
                queue, investigation_id, scenario_id, 6, "RECOMMEND",
            )
            _t0 = time.perf_counter()
            recommendations = await self._phase_recommend(
                investigation_id, scenario_id, pack, state, queue
            )
            if _OBS_AVAILABLE:
                _M.phase_duration.labels(phase="RECOMMEND", scenario_id=scenario_id, status="PASS").observe((time.perf_counter() - _t0) * 1000)

            # -- PERSIST --
            await self._run_agent_phase(
                "DemoRankerAgent", state,
                {"scenario_id": scenario_id},
                queue, investigation_id, scenario_id, 7, "PERSIST",
            )
            _t0 = time.perf_counter()
            await self._phase_persist(
                investigation_id, scenario_id, state, queue,
                hypothesis_id, recommendations,
            )
            if _OBS_AVAILABLE:
                _M.phase_duration.labels(phase="PERSIST", scenario_id=scenario_id, status="PASS").observe((time.perf_counter() - _t0) * 1000)
                scores = _CONFIDENCE_SCORES.get(scenario_id, {})
                from .confidence_calculator import ConfidenceCalculator as _CC  # noqa: PLC0415
                _bd = _CC().compute_with_breakdown(
                    evidence=scores.get("evidence", 0),
                    temporal=scores.get("temporal", 0),
                    depth=scores.get("depth", 0),
                    hypothesis=scores.get("hypothesis", 0),
                )
                _M.confidence_score.labels(scenario_id=scenario_id).set(_bd.composite_score)
                _M.confidence_distribution.labels(scenario_id=scenario_id).observe(_bd.composite_score)
                _M.investigations_completed.labels(scenario_id=scenario_id, status="CONFIRMED").inc()
                _emit(EventName.ROOT_CAUSE_CONFIRMED,
                      investigation_id=investigation_id,
                      scenario_id=scenario_id,
                      root_cause_node_id=_ROOT_CAUSE_NODE_IDS.get(scenario_id, ""),
                      defect_id="",
                      confidence=round(_bd.composite_score, 4))

        except Exception as exc:
            if _OBS_AVAILABLE:
                _M.investigations_completed.labels(scenario_id=scenario_id, status="ERROR").inc()
                _emit(EventName.INVESTIGATION_ERROR,
                      investigation_id=investigation_id,
                      scenario_id=scenario_id,
                      error=str(exc))
            logger.exception(
                "DemoRcaService: phase error for investigation %s: %s",
                investigation_id,
                exc,
            )
            await queue.put(PhaseEvent(
                phase="ERROR",
                phase_number=0,
                investigation_id=investigation_id,
                scenario_id=scenario_id,
                status="ERROR",
                summary=str(exc),
                type="ERROR",
            ))
        finally:
            if _OBS_AVAILABLE:
                _M.investigations_in_flight.dec()
            await queue.put(None)  # end-of-stream sentinel

    async def _phase_intake(
        self, inv_id: str, scenario_id: str, pack: ScenarioPack,
        state: InvestigationState, queue: asyncio.Queue,
    ) -> None:
        state.status = InvestigationStatus.ONTOLOGY_LOADING
        state.append_audit(AuditTraceEntry(
            agent_type="DemoRcaService",
            action="intake",
            inputs_summary={"scenario_id": scenario_id, "job_id": pack.job_id},
            outputs_summary={"incident_id": pack.incident_id, "controls": len(pack.controls)},
            decision="scenario_validated",
        ))
        await queue.put(PhaseEvent(
            phase="INTAKE",
            phase_number=1,
            investigation_id=inv_id,
            scenario_id=scenario_id,
            status="OK",
            summary=f"Scenario '{scenario_id}' loaded. Incident: {pack.incident_id}.",
            details={
                "incident_id":   pack.incident_id,
                "job_id":        pack.job_id,
                "total_controls": len(pack.controls),
                "failed_controls": len(pack.failed_controls),
            },
            type="PHASE_COMPLETE",
        ))
        await asyncio.sleep(0)  # yield to event loop

    async def _phase_logs_first(
        self, inv_id: str, scenario_id: str, pack: ScenarioPack,
        state: InvestigationState, queue: asyncio.Queue,
    ) -> None:
        log_signal = _LOG_SIGNALS[scenario_id]
        found = log_signal in pack.log_text

        state.append_audit(AuditTraceEntry(
            agent_type="DemoRcaService",
            action="logs_first",
            inputs_summary={"log_filename": pack.log_filename, "signal": log_signal[:60]},
            outputs_summary={"signal_found": found},
            decision="signal_detected" if found else "signal_not_found",
        ))
        await queue.put(PhaseEvent(
            phase="LOGS_FIRST",
            phase_number=2,
            investigation_id=inv_id,
            scenario_id=scenario_id,
            status="SIGNAL_DETECTED" if found else "NO_SIGNAL",
            summary=(
                f"Log signal detected in {pack.log_filename}: «{log_signal[:80]}»"
                if found
                else f"Signal not found in {pack.log_filename}"
            ),
            details={
                "log_filename": pack.log_filename,
                "signal":       log_signal,
                "found":        found,
                "pattern_id":   _PATTERN_IDS[scenario_id],
            },            type="PHASE_COMPLETE",        ))
        await asyncio.sleep(0)

    async def _phase_route(
        self, inv_id: str, scenario_id: str, pack: ScenarioPack,
        state: InvestigationState, queue: asyncio.Queue,
    ) -> str:
        """Build log EvidenceObject, add to state. Returns evidence_id."""
        state.status = InvestigationStatus.EVIDENCE_COLLECTION

        log_bytes = pack.log_text.encode("utf-8")
        raw_hash = EvidenceObject.make_hash(log_bytes)

        log_signal = _LOG_SIGNALS[scenario_id]
        log_ev = EvidenceObject(
            type=EvidenceType.LOG,
            source_system=f"batch_log:{scenario_id}",
            content_ref=f"file://scenarios/{scenario_id}/logs/{pack.log_filename}",
            summary=(
                f"Batch job log for {pack.job_id} contains defect signal. "
                f"Pattern: '{log_signal[:60]}'. "
                f"Job status: {pack.job_run.get('status', 'UNKNOWN')}."
            ),
            reliability=0.92,
            reliability_tier=EvidenceReliabilityTier.HIGH,
            raw_hash=raw_hash,
            collected_by="DemoRcaService",
            time_range_start=datetime.fromisoformat(
                pack.job_run.get("started_at", "2026-03-16T00:00:00")
            ),
            time_range_end=datetime.fromisoformat(
                pack.job_run.get("completed_at", "2026-03-16T23:59:59")
            ),
            query_executed=f"grep:{log_signal[:40]}",
            tags=("batch_log", "demo", scenario_id),
        )
        state.evidence_objects.append(log_ev)

        state.append_audit(AuditTraceEntry(
            agent_type="DemoRcaService",
            action="evidence_collect",
            inputs_summary={"log_file": pack.log_filename},
            outputs_summary={"evidence_id": log_ev.evidence_id},
            evidence_ids_accessed=[log_ev.evidence_id],
            decision="log_evidence_collected",
        ))
        await queue.put(PhaseEvent(
            phase="ROUTE",
            phase_number=3,
            investigation_id=inv_id,
            scenario_id=scenario_id,
            status="OK",
            summary=f"Log evidence collected. Evidence ID: {log_ev.evidence_id[:8]}…",
            details={
                "evidence_id":     log_ev.evidence_id,
                "reliability":     log_ev.reliability,
                "reliability_tier": log_ev.reliability_tier,
                "job_status":      pack.job_run.get("status"),
            },            type="PHASE_COMPLETE",        ))
        await asyncio.sleep(0)
        return log_ev.evidence_id

    async def _phase_backtrack(
        self, inv_id: str, scenario_id: str, pack: ScenarioPack,
        state: InvestigationState, queue: asyncio.Queue,
        evidence_id: str,
    ) -> str:
        """Build Hypothesis + CausalEdges. Returns hypothesis_id."""
        state.status = InvestigationStatus.HYPOTHESIS_GENERATION

        canon_graph = state.canon_graph
        assert canon_graph is not None  # seeded in INTAKE

        path = canon_graph.ontology_paths_used[0]
        chain_ids = _CAUSAL_CHAIN_NODE_IDS[scenario_id]

        # Select the pattern (scenario-specific, no generic matching needed)
        pattern_id = _PATTERN_IDS[scenario_id]
        pattern = self._library.get(pattern_id)
        description_template = (
            pattern.description_template if pattern else
            f"Defect at {chain_ids[-1]} caused {pack.incident_id}."
        )
        # Resolve the description from template using node primary_values
        description = self._resolve_template(description_template, canon_graph, pack)

        hypothesis = Hypothesis(
            description=description,
            involved_node_ids=chain_ids,
            evidence_object_ids=[evidence_id],
            ontology_path_ids=[path.path_id],
            status=HypothesisStatus.SUPPORTED,
            confidence=0.90,
            generated_by="DemoRcaService",
            pattern_id=pattern_id,
        )
        # Use add_hypothesis to enforce R3 (involved nodes in canon_graph)
        state.add_hypothesis(hypothesis)

        # Build causal edges for the chain
        rel_map = {
            "deposit_aggregation_failure": [
                ("MANDATES",    0, 1),
                ("DEPENDS_ON",  1, 2),
                ("RUNS_JOB",    2, 3),
                ("USES_SCRIPT", 3, 4),
            ],
            "trust_irr_misclassification": [
                ("MANDATES",    0, 1),
                ("DEPENDS_ON",  1, 2),
                ("RUNS_JOB",    2, 3),
                ("USES_SCRIPT", 3, 4),
            ],
            "wire_mt202_drop": [
                ("MANDATES",    0, 1),
                ("DEPENDS_ON",  1, 2),
                ("RUNS_JOB",    2, 3),
                ("USES_SCRIPT", 3, 4),
            ],
        }
        mechanisms = {
            "deposit_aggregation_failure": [
                "12 CFR § 330.1(b) mandates depositor aggregation rule",
                "Rule requires daily insurance pipeline to perform aggregation",
                "Pipeline executes AGGRSTEP job (Step 3)",
                "AGGRSTEP is implemented in DAILY-INSURANCE-JOB.jcl — step is disabled",
            ],
            "trust_irr_misclassification": [
                "12 CFR § 330.13 mandates IRR fiduciary documentation rule",
                "Rule requires trust daily batch pipeline to classify IRR correctly",
                "Pipeline runs TRUST-INSURANCE-CALC COBOL program",
                "COBOL program delegates classification to BeneficiaryClassifier.java",
            ],
            "wire_mt202_drop": [
                "12 CFR § 370.4(a)(1) mandates SWIFT message completeness rule",
                "Rule requires wire nightly recon pipeline to parse all message types",
                "Pipeline runs swift_parser.parse_message() module",
                "Module only handles MT103 — MT202/MT202COV silently dropped",
            ],
        }
        for idx, (rel_type, from_i, to_i) in enumerate(rel_map[scenario_id]):
            edge = CausalEdge(
                cause_node_id=chain_ids[from_i],
                effect_node_id=chain_ids[to_i],
                mechanism=mechanisms[scenario_id][idx],
                evidence_object_ids=[evidence_id],
                ontology_path_id=path.path_id,
                temporal_order_validated=True,
                structural_path_validated=True,
                confidence=0.90,
                status=CausalEdgeStatus.VALID,
            )
            state.add_causal_edge(edge)

        state.append_audit(AuditTraceEntry(
            agent_type="DemoRcaService",
            action="hypothesis_generate",
            inputs_summary={
                "pattern_id": pattern_id,
                "chain_length": len(chain_ids),
            },
            outputs_summary={
                "hypothesis_id": hypothesis.hypothesis_id,
                "causal_edges":  len(rel_map[scenario_id]),
            },
            ontology_paths_accessed=[path.path_id],
            evidence_ids_accessed=[evidence_id],
            decision=f"hypothesis_generated_with_pattern_{pattern_id}",
        ))
        await queue.put(PhaseEvent(
            phase="BACKTRACK",
            phase_number=4,
            investigation_id=inv_id,
            scenario_id=scenario_id,
            status="OK",
            summary=(
                f"Hypothesis generated with pattern {pattern_id}. "
                f"Causal chain: {len(chain_ids)} nodes, "
                f"{len(rel_map[scenario_id])} edges."
            ),
            details={
                "hypothesis_id": hypothesis.hypothesis_id,
                "pattern_id":    pattern_id,
                "causal_chain":  chain_ids,
                "ontology_path_id": path.path_id,
            },
            type="PHASE_COMPLETE",
        ))
        # Emit one HOP_REVEALED event per causal edge so the frontend
        # can animate the backtracking trace hop-by-hop.
        total_hops = len(rel_map[scenario_id])
        for hop_idx, (rel_type, from_i, to_i) in enumerate(rel_map[scenario_id]):
            await asyncio.sleep(0.35)  # stagger for visual effect
            is_last = hop_idx == total_hops - 1
            hop_status = "artifact_defect" if is_last else "confirmed"
            await queue.put(PhaseEvent(
                phase="HOP_REVEALED",
                phase_number=4,
                investigation_id=inv_id,
                scenario_id=scenario_id,
                status="OK",
                summary=(
                    f"Hop {hop_idx}: {chain_ids[from_i]} "
                    f"→[{rel_type}]→ {chain_ids[to_i]}"
                ),
                details={
                    "hop_index":    hop_idx,
                    "from_node_id": chain_ids[from_i],
                    "to_node_id":   chain_ids[to_i],
                    "rel_type":     rel_type,
                    "status":       hop_status,
                },
                type="HOP_REVEALED",
            ))
        await asyncio.sleep(0)
        return hypothesis.hypothesis_id

    async def _phase_incident_card(
        self, inv_id: str, scenario_id: str, pack: ScenarioPack,
        state: InvestigationState, queue: asyncio.Queue,
    ) -> None:
        inc = pack.incident
        defect = self._adapter.primary_defect_for_scenario(scenario_id)
        incident_card = {
            "incident_id":   inc["incident_id"],
            "title":         inc.get("title", ""),
            "severity":      inc.get("severity", ""),
            "regulation":    inc.get("regulation", ""),
            "control_id":    inc.get("control_id", ""),
            "control_name":  inc.get("control_name", ""),
            "defect_id":     inc.get("defect_id", ""),
            "defect_artifact": inc.get("defect_artifact", ""),
            "defect_description": defect.description if defect else "",
            "reported_at":   inc.get("reported_at", ""),
            "status":        "OPEN",
            "impact":        inc.get("impact", {}),
        }

        state.append_audit(AuditTraceEntry(
            agent_type="DemoRcaService",
            action="incident_card_synthesis",
            inputs_summary={"incident_id": inc["incident_id"]},
            outputs_summary={"card_fields": list(incident_card.keys())},
            decision="incident_card_synthesized",
        ))
        await queue.put(PhaseEvent(
            phase="INCIDENT_CARD",
            phase_number=5,
            investigation_id=inv_id,
            scenario_id=scenario_id,
            status="OK",
            summary=f"Incident card synthesized for {inc['incident_id']}.",
            details={"incident_card": incident_card},
            type="PHASE_COMPLETE",
        ))
        await asyncio.sleep(0)

    async def _phase_recommend(
        self, inv_id: str, scenario_id: str, pack: ScenarioPack,
        state: InvestigationState, queue: asyncio.Queue,
    ) -> List[Dict[str, Any]]:
        """Build remediation recommendations from the agent catalog (structured dicts)."""
        # Pull structured dicts from the agent's static catalog — these have
        # all the fields the frontend Recommendation interface expects:
        # rank, action, artifact, defect_id, regulation, effort, confidence.
        structured: List[Dict[str, Any]] = []
        try:
            from src.demo.agents.demo_recommend_agent import (  # noqa: PLC0415
                _RECOMMENDATIONS as _AGENT_RECS,
            )
            raw = _AGENT_RECS.get(scenario_id, [])
            for rec in raw:
                structured.append({
                    **rec,
                    # Ensure `rank` is present (frontend uses rec.rank ?? i+1)
                    "rank": rec.get("priority", len(structured) + 1),
                })
        except Exception as exc:  # pragma: no cover
            logger.warning("Could not load _RECOMMENDATIONS from agent: %s", exc)

        # Fall back to adapter defect strings if the catalog was empty
        if not structured:
            defects = self._adapter.defects_for_scenario(scenario_id)
            for i, d in enumerate(defects, start=1):
                plain = f"[{d.defect_id}] {d.description} — {d.artifact_path}: {d.remediation}"
                structured.append({
                    "rank": i,
                    "action": plain,
                    "defect_id": d.defect_id,
                    "artifact": d.artifact_path,
                })

        # Also write plain-text strings into InvestigationState.recommended_actions
        for rec in structured:
            plain = (
                f"[{rec.get('defect_id', '')}] {rec.get('action', '')} "
                f"— {rec.get('artifact', '')}"
            ).strip()
            state.recommended_actions.append(plain)

        state.append_audit(AuditTraceEntry(
            agent_type="DemoRcaService",
            action="recommend",
            inputs_summary={"scenario_id": scenario_id},
            outputs_summary={"recommendation_count": len(structured)},
            decision="recommendations_generated",
        ))
        await queue.put(PhaseEvent(
            phase="RECOMMEND",
            phase_number=6,
            investigation_id=inv_id,
            scenario_id=scenario_id,
            status="OK",
            summary=f"{len(structured)} remediation recommendation(s) generated.",
            details={"recommendations": structured},
            type="PHASE_COMPLETE",
        ))
        await asyncio.sleep(0)
        return structured

    async def _phase_persist(
        self, inv_id: str, scenario_id: str,
        state: InvestigationState, queue: asyncio.Queue,
        hypothesis_id: str,
        recommendations: list,
    ) -> None:
        """Compute final confidence and set root_cause_final."""
        scores = _CONFIDENCE_SCORES[scenario_id]
        breakdown = self._calc.compute_with_breakdown(
            evidence=scores["evidence"],
            temporal=scores["temporal"],
            depth=scores["depth"],
            hypothesis=scores["hypothesis"],
        )

        root_node_id = _ROOT_CAUSE_NODE_IDS[scenario_id]
        chain_ids = _CAUSAL_CHAIN_NODE_IDS[scenario_id]

        defect = self._adapter.primary_defect_for_scenario(scenario_id)
        description = (
            defect.description if defect
            else f"Root cause at node {root_node_id}"
        )

        candidate = RootCauseCandidate(
            node_id=root_node_id,
            description=description,
            hypothesis_ids=[hypothesis_id],
            causal_edge_ids=[e.edge_id for e in state.causal_graph_edges],
            evidence_score=breakdown.evidence_score,
            temporal_score=breakdown.temporal_score,
            structural_depth_score=breakdown.depth_score,
            hypothesis_alignment_score=breakdown.hypothesis_score,
            composite_score=breakdown.composite_score,
        )
        state.root_cause_candidates.append(candidate)

        # set_root_cause_final checks composite_score >= confidence_threshold (0.70)
        state.set_root_cause_final(candidate, ranker_agent_type="DemoRcaService")
        state.status = InvestigationStatus.COMPLETED

        state.append_audit(AuditTraceEntry(
            agent_type="DemoRcaService",
            action="persist",
            inputs_summary={
                "composite_score": round(breakdown.composite_score, 4),
                "confidence_threshold": state.investigation_input.confidence_threshold,
            },
            outputs_summary={
                "root_cause_node":  root_node_id,
                "status":           candidate.status,
                "composite_score":  round(breakdown.composite_score, 4),
            },
            decision="root_cause_confirmed",
        ))
        await queue.put(PhaseEvent(
            phase="PERSIST",
            phase_number=7,
            investigation_id=inv_id,
            scenario_id=scenario_id,
            status="CONFIRMED",
            summary=(
                f"Root cause confirmed at {root_node_id}. "
                f"Composite score: {breakdown.composite_score:.4f} "
                f"(threshold: {state.investigation_input.confidence_threshold})."
            ),
            details={
                "root_cause_node_id": root_node_id,
                "composite_score":    round(breakdown.composite_score, 4),
                "status":             candidate.status,
                "confidence_breakdown": breakdown.to_dict(),
                "total_audit_entries":  len(state.audit_trace),
            },
            type="PHASE_COMPLETE",
        ))
        await asyncio.sleep(0)
        # Signal the SSE consumer that all phases are done.  The None sentinel
        # below terminates the async generator; INVESTIGATION_COMPLETE is the
        # application-level signal that arrives before the stream closes.
        await queue.put(PhaseEvent(
            phase="INVESTIGATION_COMPLETE",
            phase_number=8,
            investigation_id=inv_id,
            scenario_id=scenario_id,
            status="CONFIRMED",
            summary=(
                f"All 7 phases complete. Root cause confirmed at {root_node_id}. "
                f"Composite score: {breakdown.composite_score:.4f}."
            ),
            details={
                "root_cause_node_id": root_node_id,
                "composite_score":    round(breakdown.composite_score, 4),
            },
            type="INVESTIGATION_COMPLETE",
        ))
        logger.info(
            "DemoRcaService: investigation %s completed — root_cause=%s score=%.4f",
            inv_id,
            root_node_id,
            breakdown.composite_score,
        )

    # ------------------------------------------------------------------
    # Template resolution
    # ------------------------------------------------------------------

    def _resolve_template(
        self, template: str, canon_graph: Any, pack: ScenarioPack
    ) -> str:
        """Substitute node primary_values into a description template."""
        try:
            from causelink.ontology.models import CanonGraph as _CG
            g: _CG = canon_graph
            vars_: Dict[str, str] = {"anchor_value": g.anchor_primary_value}
            for node in g.nodes:
                for label in node.labels:
                    key = f"{label.lower()}_value"
                    vars_.setdefault(key, node.primary_value or node.neo4j_id)
            return template.format_map(vars_)
        except (KeyError, AttributeError):
            return template  # fall back to raw template if substitution fails

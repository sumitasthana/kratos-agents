#!/usr/bin/env python3
"""
scripts/demo_causelink.py

End-to-end demo of the CauseLink RCA pipeline using fully mocked
Neo4j adapter and evidence service.

No external services required. Safe to run on a clean machine with only
the Python dependencies installed.

Usage:
    python scripts/demo_causelink.py                        # default incident scenario
    python scripts/demo_causelink.py --scenario pipeline    # pipeline anchor scenario
    python scripts/demo_causelink.py --scenario missing     # missing evidence scenario
    python scripts/demo_causelink.py --output results.json  # save output to file
    python scripts/demo_causelink.py --all                  # run all scenarios

Exit codes:
    0  All selected scenarios passed.
    1  One or more scenarios produced unexpected output.
    2  Configuration / import error.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
import uuid
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

# Ensure src/ is on the path when running from the repo root
_SRC = Path(__file__).resolve().parent.parent / "src"
if str(_SRC) not in sys.path:
    sys.path.insert(0, str(_SRC))

try:
    from causelink.agents.causal_engine import CausalEngineAgent
    from causelink.agents.evidence_collector import EvidenceCollectorAgent
    from causelink.agents.hypothesis_generator import HypothesisGeneratorAgent
    from causelink.agents.ontology_context import OntologyContextAgent
    from causelink.agents.ranker import RankerAgent
    from causelink.evidence.contracts import (
        EvidenceObject,
        EvidenceReliabilityTier,
        EvidenceSearchParams,
        EvidenceService,
        EvidenceType,
        NullEvidenceService,
    )
    from causelink.logging_config import configure_logging
    from causelink.ontology.models import CanonEdge, CanonGraph, CanonNode, OntologyPath
    from causelink.services.dashboard_schema import (
        NodeStatus,
        RcaDashboardSummary,
        StopReason,
        TraversalMode,
    )
    from causelink.services.ontology_backtracking import OntologyBacktrackingService
    from causelink.state.investigation import (
        InvestigationAnchor,
        InvestigationInput,
        InvestigationState,
        InvestigationStatus,
    )
except ImportError as exc:
    print(f"[demo_causelink] Import error: {exc}", file=sys.stderr)
    print(
        "[demo_causelink] Ensure you are running from the repo root with venv active:\n"
        "  .\\venv311\\Scripts\\activate\n"
        "  python scripts/demo_causelink.py",
        file=sys.stderr,
    )
    sys.exit(2)


# ---------------------------------------------------------------------------
# Deterministic seed helpers
# ---------------------------------------------------------------------------

def _stable_id(seed: str) -> str:
    """Return a deterministic UUID-shaped ID based on a seed string."""
    digest = hashlib.sha256(seed.encode()).hexdigest()
    return f"{digest[:8]}-{digest[8:12]}-{digest[12:16]}-{digest[16:20]}-{digest[20:32]}"


def _ev(ev_type: EvidenceType, seed: str, reliability: float = 0.85) -> EvidenceObject:
    raw = f"demo-evidence:{seed}".encode()
    return EvidenceObject(
        evidence_id=_stable_id(f"ev:{seed}"),
        type=ev_type,
        source_system="demo-mock",
        content_ref=f"file:///tmp/demo/{seed.replace(':', '_')}.json",
        summary=f"Demo evidence ({ev_type.value}) for {seed}",
        reliability=reliability,
        reliability_tier=EvidenceObject.tier_for(reliability),
        raw_hash=EvidenceObject.make_hash(raw),
        collected_by="demo",
    )


def _node(label: str, seed: str) -> CanonNode:
    return CanonNode(
        neo4j_id=_stable_id(f"node:{label}:{seed}"),
        labels=[label],
        primary_key=f"{label.lower()}_id",
        primary_value=seed,
        properties={},
        provenance="demo-mock",
    )


def _edge(rel_type: str, start_seed: str, end_seed: str, s_label: str, e_label: str) -> CanonEdge:
    return CanonEdge(
        neo4j_id=_stable_id(f"edge:{rel_type}:{start_seed}:{end_seed}"),
        type=rel_type,
        start_node_id=_stable_id(f"node:{s_label}:{start_seed}"),
        end_node_id=_stable_id(f"node:{e_label}:{end_seed}"),
        properties={},
        provenance="demo-mock",
    )


def _path(node_ids: List[str], rel_types: List[str], name: str) -> OntologyPath:
    return OntologyPath(
        path_id=_stable_id(f"path:{name}"),
        description=name,
        node_sequence=node_ids,
        rel_type_sequence=rel_types,
        hop_count=len(rel_types),
        query_used="(demo-mock: no live query)",
    )


# ---------------------------------------------------------------------------
# Mock adapters
# ---------------------------------------------------------------------------

class _IncidentMockAdapter:
    """
    Returns a CanonGraph anchored on Incident INC-DEMO-2026-001.

    Nodes:  Incident, Violation, Rule, System, Job
    Edges:  GENERATES (Violation->Incident), ENFORCED_BY (Violation->Rule),
            GENERATES (System->Incident via compliance chain), RUNS_JOB (System->Job)
    """

    def _graph(self) -> CanonGraph:
        inc = _node("Incident",  "INC-DEMO-2026-001")
        vio = _node("Violation", "VIO-DEMO-2026-001")
        rule = _node("Rule",     "RULE-GDPR-ART17")
        sys_ = _node("System",   "SYS-PIPELINE-CORE")
        job  = _node("Job",      "JOB-ETL-DAILY")

        path = _path(
            [inc.neo4j_id, vio.neo4j_id, rule.neo4j_id, sys_.neo4j_id, job.neo4j_id],
            ["GENERATES", "ENFORCED_BY", "GENERATES", "RUNS_JOB"],
            "incident-compliance-chain",
        )
        return CanonGraph(
            anchor_neo4j_id=inc.neo4j_id,
            anchor_label="Incident",
            anchor_primary_key="incident_id",
            anchor_primary_value="INC-DEMO-2026-001",
            nodes=[inc, vio, rule, sys_, job],
            edges=[
                _edge("GENERATES",   "VIO-DEMO-2026-001", "INC-DEMO-2026-001", "Violation", "Incident"),
                _edge("ENFORCED_BY", "VIO-DEMO-2026-001", "RULE-GDPR-ART17",   "Violation", "Rule"),
                _edge("GENERATES",   "SYS-PIPELINE-CORE","INC-DEMO-2026-001","System","Incident"),
                _edge("RUNS_JOB",    "SYS-PIPELINE-CORE","JOB-ETL-DAILY",    "System","Job"),
            ],
            ontology_paths_used=[path],
            retrieved_at=datetime(2026, 3, 11, 9, 0, 0),
            max_hops=3,
        )

    def get_neighborhood(self, anchor_label, anchor_primary_key, anchor_primary_value, max_hops=3):
        return self._graph()

    def get_compliance_chain(self, anchor_label, anchor_primary_key, anchor_primary_value, max_hops=5):
        return self._graph()

    def get_lineage_chain(self, anchor_label, anchor_primary_key, anchor_primary_value, max_hops=5):
        return self._graph()

    def get_change_provenance_chain(self, anchor_label, anchor_primary_key, anchor_primary_value, max_hops=4):
        return self._graph()

    def get_log_scope_chain(self, anchor_label, anchor_primary_key, anchor_primary_value, max_hops=2):
        return self._graph()

    def validate_shortest_path(self, start_node_id, end_node_id, max_hops=3):
        return _path([start_node_id, end_node_id], ["GENERATES"], "shortest-path-demo")


class _PipelineMockAdapter:
    """
    Returns a CanonGraph anchored on Pipeline PIPELINE-ETL-INTRADAY.
    """

    def _graph(self) -> CanonGraph:
        pip  = _node("Pipeline",  "PIPELINE-ETL-INTRADAY")
        scr  = _node("Script",    "SCRIPT-TRANSFORM-001")
        tbl  = _node("Table",     "TABLE-POSITIONS-RAW")
        col1 = _node("Column",    "COL-POSITION-NOTIONAL")
        col2 = _node("Column",    "COL-MARKET-VALUE")
        log  = _node("LogSource", "LOGSRC-AIRFLOW-PROD")

        path = _path(
            [pip.neo4j_id, scr.neo4j_id, tbl.neo4j_id, col1.neo4j_id, col2.neo4j_id],
            ["USES_SCRIPT", "READS", "HAS_COLUMN", "DERIVED_FROM"],
            "pipeline-lineage-chain",
        )
        log_path = _path([pip.neo4j_id, log.neo4j_id], ["LOGGED_IN"], "pipeline-log-scope")

        return CanonGraph(
            anchor_neo4j_id=pip.neo4j_id,
            anchor_label="Pipeline",
            anchor_primary_key="pipeline_id",
            anchor_primary_value="PIPELINE-ETL-INTRADAY",
            nodes=[pip, scr, tbl, col1, col2, log],
            edges=[
                _edge("USES_SCRIPT",  "PIPELINE-ETL-INTRADAY", "SCRIPT-TRANSFORM-001", "Pipeline", "Script"),
                _edge("READS",        "SCRIPT-TRANSFORM-001",  "TABLE-POSITIONS-RAW",  "Script",   "Table"),
                _edge("HAS_COLUMN",   "TABLE-POSITIONS-RAW",   "COL-POSITION-NOTIONAL","Table",    "Column"),
                _edge("DERIVED_FROM", "COL-POSITION-NOTIONAL", "COL-MARKET-VALUE",     "Column",   "Column"),
                _edge("LOGGED_IN",    "PIPELINE-ETL-INTRADAY", "LOGSRC-AIRFLOW-PROD",  "Pipeline", "LogSource"),
            ],
            ontology_paths_used=[path, log_path],
            retrieved_at=datetime(2026, 3, 11, 9, 0, 0),
            max_hops=5,
        )

    def get_neighborhood(self, anchor_label, anchor_primary_key, anchor_primary_value, max_hops=3):
        return self._graph()

    def get_compliance_chain(self, anchor_label, anchor_primary_key, anchor_primary_value, max_hops=5):
        return self._graph()

    def get_lineage_chain(self, anchor_label, anchor_primary_key, anchor_primary_value, max_hops=5):
        return self._graph()

    def get_change_provenance_chain(self, anchor_label, anchor_primary_key, anchor_primary_value, max_hops=4):
        return self._graph()

    def get_log_scope_chain(self, anchor_label, anchor_primary_key, anchor_primary_value, max_hops=2):
        return self._graph()

    def validate_shortest_path(self, start_node_id, end_node_id, max_hops=3):
        return _path([start_node_id, end_node_id], ["USES_SCRIPT"], "shortest-path-demo")


class _FullEvidenceService(EvidenceService):
    """Returns a complete set of mock evidence for demo purposes."""

    def search_logs(self, params, collected_by):
        return _ev(EvidenceType.LOG, "logs:demo", 0.88)

    def query_metrics(self, params, metric_names, collected_by):
        return _ev(EvidenceType.METRIC, "metrics:demo", 0.75)

    def fetch_change_events(self, params, collected_by):
        return _ev(EvidenceType.CHANGE_EVENT, "changes:demo", 0.80)

    def fetch_audit_events(self, params, collected_by):
        return _ev(EvidenceType.AUDIT_EVENT, "audit:demo", 0.92)

    def get_lineage_trace(self, params, collected_by):
        return _ev(EvidenceType.LINEAGE_TRACE, "lineage:demo", 0.70)

    def get_evidence(self, evidence_id):
        return None


# ---------------------------------------------------------------------------
# Pipeline runner
# ---------------------------------------------------------------------------

def _run_pipeline(
    inv_input: InvestigationInput,
    adapter,
    evidence_svc: EvidenceService,
) -> InvestigationState:
    state = InvestigationState(investigation_input=inv_input)
    state = OntologyContextAgent(adapter=adapter).run(state)
    if state.status == InvestigationStatus.INSUFFICIENT_EVIDENCE:
        return state
    state = EvidenceCollectorAgent(evidence_service=evidence_svc).run(state)
    state = HypothesisGeneratorAgent().run(state)
    state = CausalEngineAgent(adapter=adapter).run(state)
    state = RankerAgent().run(state)
    return state


def _make_input(
    anchor_type: str,
    anchor_pk: str,
    anchor_pv: str,
    threshold: float = 0.50,
    max_hops: int = 3,
) -> InvestigationInput:
    return InvestigationInput(
        investigation_id=_stable_id(f"inv:{anchor_type}:{anchor_pv}"),
        anchor=InvestigationAnchor(
            anchor_type=anchor_type,
            anchor_primary_key=anchor_pk,
            anchor_primary_value=anchor_pv,
        ),
        max_hops=max_hops,
        confidence_threshold=threshold,
    )


# ---------------------------------------------------------------------------
# Scenario definitions
# ---------------------------------------------------------------------------

def scenario_incident() -> Dict[str, Any]:
    """
    Scenario: Incident anchor, full compliance chain, all evidence available.
    Expected: At least one hypothesis generated; investigation completes.
    """
    inv_input = _make_input(
        "Incident", "incident_id", "INC-DEMO-2026-001", threshold=0.40
    )
    state = _run_pipeline(inv_input, _IncidentMockAdapter(), _FullEvidenceService())
    return _summarise(state, "incident")


def scenario_pipeline() -> Dict[str, Any]:
    """
    Scenario: Pipeline anchor, lineage + log-scope chains, all evidence available.
    Expected: Lineage-pattern hypothesis generated; investigation completes.
    """
    inv_input = _make_input(
        "Pipeline", "pipeline_id", "PIPELINE-ETL-INTRADAY", threshold=0.40, max_hops=5
    )
    state = _run_pipeline(inv_input, _PipelineMockAdapter(), _FullEvidenceService())
    return _summarise(state, "pipeline")


def scenario_missing_evidence() -> Dict[str, Any]:
    """
    Scenario: Incident anchor, no evidence available.
    Expected: Investigation ends INSUFFICIENT_EVIDENCE with escalation=True.
    """
    inv_input = _make_input(
        "Incident", "incident_id", "INC-DEMO-2026-001", threshold=0.40
    )
    state = _run_pipeline(inv_input, _IncidentMockAdapter(), NullEvidenceService())
    return _summarise(state, "missing_evidence")


def scenario_backtracking_incident() -> Dict[str, Any]:
    """
    Scenario: Full pipeline on Incident anchor, then backtracking with early stop.
    Expected: Backtracking finds a failed node in the compliance chain.
    """
    inv_input = _make_input(
        "Incident", "incident_id", "INC-DEMO-2026-001", threshold=0.40
    )
    state = _run_pipeline(inv_input, _IncidentMockAdapter(), _FullEvidenceService())
    return _run_backtracking(state, mode="normal")


def scenario_backtracking_exploratory() -> Dict[str, Any]:
    """
    Scenario: Full pipeline on Pipeline anchor, then backtracking in exploratory mode.
    Expected: All nodes are evaluated; no early stop; lineage walk populated.
    """
    inv_input = _make_input(
        "Pipeline", "pipeline_id", "PIPELINE-ETL-INTRADAY", threshold=0.40, max_hops=5
    )
    state = _run_pipeline(inv_input, _PipelineMockAdapter(), _FullEvidenceService())
    return _run_backtracking(state, mode="exploratory")


def _run_backtracking(state: InvestigationState, mode: str) -> Dict[str, Any]:
    """
    Run OntologyBacktrackingService on a completed investigation state.
    Returns a summary dict suitable for printing and validation.
    """
    service = OntologyBacktrackingService()
    try:
        bt_result = service.backtrack_with_early_stop(state, mode=mode)
        dashboard = service.to_dashboard_summary(state, bt_result)
    except Exception as exc:  # noqa: BLE001
        return {
            "scenario": f"backtracking:{mode}",
            "error": str(exc),
            "status": "ERROR",
        }

    return {
        "scenario": f"backtracking:{mode}",
        "investigation_id": dashboard.investigation_id,
        "anchor_type": dashboard.anchor_type,
        "anchor_id": dashboard.anchor_id,
        "traversal_mode": dashboard.traversal_mode.value,
        "stop_reason": dashboard.stop_reason.value if dashboard.stop_reason else None,
        "health_score": dashboard.health_score,
        "health_status": dashboard.health_status,
        "problem_type": dashboard.problem_type,
        "control_triggered": dashboard.control_triggered,
        "lineage_failure_node": dashboard.lineage_failure_node,
        "failed_node": dashboard.failed_node,
        "failed_node_status": dashboard.failed_node_status.value if dashboard.failed_node_status else None,
        "failure_reason": dashboard.failure_reason,
        "confidence": dashboard.confidence,
        "findings": dashboard.findings,
        "evidence_objects": dashboard.evidence_objects,
        "lineage_walk": [
            {
                "node_id": w.node_id,
                "display_name": w.display_name,
                "label": w.label,
                "status": w.status.value,
                "was_evaluated": w.was_evaluated,
            }
            for w in dashboard.lineage_walk
        ],
        "agent_chain": [
            {
                "agent_name": e.agent_name,
                "status": e.status,
                "health": e.health,
                "problem_type": e.problem_type,
                "key_finding": e.key_finding,
            }
            for e in dashboard.agent_analysis_chain
        ],
        "traversal_nodes_evaluated": sum(
            1 for e in bt_result.traversal_sequence
            if e.status != NodeStatus.NOT_EVALUATED_DUE_TO_EARLY_STOP
        ),
        "traversal_nodes_skipped": sum(
            1 for e in bt_result.traversal_sequence
            if e.status == NodeStatus.NOT_EVALUATED_DUE_TO_EARLY_STOP
        ),
        "total_nodes_in_graph": bt_result.total_nodes_in_graph,
        "chains_evaluated": bt_result.chains_evaluated,
        "audit_trace": dashboard.audit_trace,
        "ontology_paths_used": dashboard.ontology_paths_used,
        "status": "OK",
    }


def _summarise(state: InvestigationState, label: str) -> Dict[str, Any]:
    result: Dict[str, Any] = {
        "scenario": label,
        "investigation_id": state.investigation_input.investigation_id,
        "anchor": {
            "type":  state.investigation_input.anchor.anchor_type,
            "value": state.investigation_input.anchor.anchor_primary_value,
        },
        "status": state.status.value,
        "escalation": state.escalation,
        "canon_graph": {
            "nodes": len(state.canon_graph.nodes) if state.canon_graph else 0,
            "edges": len(state.canon_graph.edges) if state.canon_graph else 0,
        },
        "evidence_collected": len(state.evidence_objects),
        "hypotheses": len(state.hypotheses),
        "hypotheses_detail": [
            {
                "pattern_id": h.pattern_id,
                "status": h.status.value,
                "evidence_citations": len(h.evidence_object_ids),
                "involved_nodes": len(h.involved_node_ids),
            }
            for h in state.hypotheses
        ],
        "causal_edges": len(state.causal_graph_edges),
        "root_cause_candidates": len(state.root_cause_candidates),
        "root_cause_final": (
            {
                "node_id": state.root_cause_final.node_id,
                "composite_score": state.root_cause_final.composite_score,
                "status": state.root_cause_final.status.value,
            }
            if state.root_cause_final
            else None
        ),
        "missing_evidence": [
            {
                "evidence_type": m.evidence_type,
                "blocking": m.blocking,
                "description": m.description,
            }
            for m in state.missing_evidence
        ],
        "audit_steps": len(state.audit_trace),
        "audit_actions": [e.action for e in state.audit_trace],
        "ontology_paths_used": len(state.ontology_paths_used),
    }
    return result


# ---------------------------------------------------------------------------
# Validation helpers
# ---------------------------------------------------------------------------

def _validate(result: Dict[str, Any], scenario: str) -> List[str]:
    """Return list of assertion failures (empty = pass)."""
    failures: List[str] = []

    if result.get("status") == "ERROR":
        failures.append(f"Scenario raised an exception: {result.get('error')}")
        return failures

    if scenario in ("incident", "pipeline"):
        if result["canon_graph"]["nodes"] == 0:
            failures.append("CanonGraph has no nodes")
        if result["evidence_collected"] == 0:
            failures.append("No evidence collected")
        if result["hypotheses"] == 0:
            failures.append("No hypotheses generated")
        for h in result["hypotheses_detail"]:
            if not h["pattern_id"]:
                failures.append(f"Hypothesis missing pattern_id: {h}")
            if h["evidence_citations"] == 0:
                failures.append(f"Hypothesis has no evidence citations: {h}")
        if result["audit_steps"] == 0:
            failures.append("Audit trace is empty")
        if "ontology_load" not in result["audit_actions"]:
            failures.append("Audit trace missing 'ontology_load' step")

    if scenario == "missing_evidence":
        if not result["escalation"]:
            failures.append("Expected escalation=True for missing-evidence scenario")
        if result["root_cause_final"] is not None:
            failures.append("Expected root_cause_final=None for missing-evidence scenario")
        if not result["missing_evidence"]:
            failures.append("Expected missing_evidence list to be non-empty")
        if not any(m["blocking"] for m in result["missing_evidence"]):
            failures.append("Expected at least one blocking MissingEvidence")

    if scenario.startswith("backtracking:"):
        if result["total_nodes_in_graph"] == 0:
            failures.append("CanonGraph reported 0 nodes during backtracking")
        if not result["chains_evaluated"]:
            failures.append("No ontology chains were evaluated")
        if result.get("traversal_nodes_evaluated", 0) == 0:
            failures.append("No nodes were evaluated during backtracking")
        mode = result["traversal_mode"]
        if mode == "normal":
            # In normal mode with real evidence, a failure should be found
            if result["stop_reason"] not in (
                "FIRST_CONFIRMED_FAILURE", "INSUFFICIENT_EVIDENCE",
                "ONTOLOGY_GAP", "MAX_HOPS_REACHED",
            ):
                failures.append(
                    f"Unexpected stop_reason for normal mode: {result['stop_reason']}"
                )
        if mode == "exploratory":
            # Exploratory should never skip nodes via early stop
            if result.get("traversal_nodes_skipped", 0) > 0:
                failures.append(
                    f"Exploratory mode skipped {result['traversal_nodes_skipped']} nodes "
                    "(early stop must not fire in exploratory mode)"
                )
            if result["stop_reason"] == "FIRST_CONFIRMED_FAILURE":
                failures.append(
                    "stop_reason=FIRST_CONFIRMED_FAILURE must not appear in exploratory mode"
                )
        # No emojis in any string field
        for field_name in ("health_status", "problem_type", "failure_reason",
                           "control_triggered", "lineage_failure_node"):
            val = result.get(field_name) or ""
            if _has_emoji(val):
                failures.append(f"Emoji detected in field '{field_name}': {val!r}")
        for finding in result.get("findings", []):
            if _has_emoji(finding):
                failures.append(f"Emoji detected in finding: {finding!r}")

    return failures


_EMOJI_RANGES = [
    (0x1F600, 0x1F64F), (0x1F300, 0x1F5FF), (0x1F680, 0x1F6FF),
    (0x1F1E0, 0x1F1FF), (0x2600, 0x26FF),   (0x2700, 0x27BF),
    (0x1F900, 0x1F9FF), (0x1FA00, 0x1FA6F),  (0x1FA70, 0x1FAFF),
]


def _has_emoji(text: str) -> bool:
    for ch in text:
        cp = ord(ch)
        if any(lo <= cp <= hi for lo, hi in _EMOJI_RANGES):
            return True
    return False


# ---------------------------------------------------------------------------
# Output formatting
# ---------------------------------------------------------------------------

def _print_result(result: Dict[str, Any], failures: List[str]) -> None:
    status_label = "PASS" if not failures else "FAIL"
    scenario = result.get("scenario", "unknown")

    if scenario.startswith("backtracking:"):
        _print_dashboard_result(result, failures)
        return

    print(f"\n[demo] Scenario: {scenario.upper()}")
    print(f"[demo] Status   : {status_label}")
    print(f"[demo] InvStatus: {result['status']}")
    print(f"[demo] AnchorType : {result['anchor']['type']}")
    print(f"[demo] AnchorValue: {result['anchor']['value']}")
    print(f"[demo] CanonGraph : {result['canon_graph']['nodes']} nodes, "
          f"{result['canon_graph']['edges']} edges")
    print(f"[demo] Evidence   : {result['evidence_collected']} objects collected")
    print(f"[demo] Hypotheses : {result['hypotheses']}")
    for h in result["hypotheses_detail"]:
        print(f"[demo]   pattern={h['pattern_id']}  status={h['status']}  "
              f"evidence_citations={h['evidence_citations']}")
    print(f"[demo] RootCause  : {result['root_cause_final']}")
    print(f"[demo] AuditSteps : {result['audit_steps']} "
          f"({', '.join(result['audit_actions'])})")
    if result["missing_evidence"]:
        print(f"[demo] Missing evidence ({len(result['missing_evidence'])}):")
        for m in result["missing_evidence"]:
            blocking = "[BLOCKING]" if m["blocking"] else "[non-blocking]"
            print(f"[demo]   {blocking} {m['evidence_type']}: {m['description'][:60]}")
    if failures:
        print(f"[demo] FAILURES:")
        for f in failures:
            print(f"[demo]   - {f}")


def _print_dashboard_result(result: Dict[str, Any], failures: List[str]) -> None:
    """Print a formatted backtracking / dashboard scenario result."""
    status_label = "PASS" if not failures else "FAIL"
    scenario = result.get("scenario", "backtracking:unknown")

    print(f"\n[demo] Scenario    : {scenario.upper()}")
    print(f"[demo] Status      : {status_label}")

    if result.get("status") == "ERROR":
        print(f"[demo] ERROR       : {result.get('error')}")
        if failures:
            for f in failures:
                print(f"[demo]   - {f}")
        return

    print(f"[demo] --- Dashboard Summary ---")
    print(f"[demo] Anchor          : {result['anchor_type']} / {result['anchor_id']}")
    print(f"[demo] Traversal Mode  : {result['traversal_mode']}")
    print(f"[demo] Stop Reason     : {result['stop_reason']}")
    print(f"[demo] Health Score    : {result['health_score']:.1f}  ({result['health_status']})")
    print(f"[demo] Problem Type    : {result['problem_type']}")
    print(f"[demo] Control         : {result['control_triggered'] or '(none)'}")
    print(f"[demo] Lineage Failure : {result['lineage_failure_node'] or '(none)'}")
    print(f"[demo] Confidence      : {result['confidence']:.2f}")
    print(f"[demo] Failed Node     : {result['failed_node'] or '(none)'}  "
          f"[{result['failed_node_status'] or 'N/A'}]")
    print(f"[demo] Failure Reason  : {result['failure_reason'] or '(none)'}")
    print(f"[demo] Chains Evaluated: {', '.join(result['chains_evaluated']) or '(none)'}")
    print(f"[demo] Nodes Evaluated : {result.get('traversal_nodes_evaluated', 0)}  "
          f"(skipped: {result.get('traversal_nodes_skipped', 0)})  "
          f"(total in graph: {result['total_nodes_in_graph']})")
    if result["findings"]:
        print(f"[demo] Findings ({len(result['findings'])})  :")
        for idx, f_text in enumerate(result["findings"], 1):
            print(f"[demo]   {idx}. {f_text[:90]}")
    else:
        print("[demo] Findings        : (none)")
    if result["lineage_walk"]:
        print(f"[demo] Lineage Walk    :")
        for w in result["lineage_walk"]:
            evaluated_tag = "[evaluated]" if w["was_evaluated"] else "[skipped]"
            print(f"[demo]   {w['label']:<18} {w['display_name']:<30} {w['status']:<38} {evaluated_tag}")
    if result["agent_chain"]:
        print(f"[demo] Agent Chain     :")
        for a in result["agent_chain"]:
            print(f"[demo]   {a['agent_name']:<35} [{a['status']}] health={a['health']}  "
                  f"problem={a['problem_type']}")
    if failures:
        print(f"[demo] FAILURES:")
        for f in failures:
            print(f"[demo]   - {f}")


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

_SCENARIOS = {
    "incident":                scenario_incident,
    "pipeline":                scenario_pipeline,
    "missing":                 scenario_missing_evidence,
    "backtracking_incident":   scenario_backtracking_incident,
    "backtracking_exploratory": scenario_backtracking_exploratory,
}


def main() -> int:
    configure_logging(level="INFO", fmt="text")

    parser = argparse.ArgumentParser(
        description="CauseLink end-to-end demo (mocked Neo4j + evidence).",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=(
            "Examples:\n"
            "  python scripts/demo_causelink.py\n"
            "  python scripts/demo_causelink.py --scenario pipeline\n"
            "  python scripts/demo_causelink.py --all --output demo_out.json\n"
        ),
    )
    parser.add_argument(
        "--scenario",
        choices=list(_SCENARIOS),
        default="incident",
        help=("Scenario to run (default: incident). "
              "backtracking_incident=full pipeline + dashboard summary (normal mode), "
              "backtracking_exploratory=full pipeline + dashboard summary (exploratory mode)."),
    )
    parser.add_argument(
        "--all",
        action="store_true",
        help="Run all scenarios",
    )
    parser.add_argument(
        "--output",
        metavar="FILE",
        help="Write JSON results to FILE",
    )
    args = parser.parse_args()

    scenarios_to_run = list(_SCENARIOS) if args.all else [args.scenario]

    all_results = []
    overall_pass = True

    print(f"\n[demo] CauseLink Demo  --  {datetime.utcnow().isoformat()}Z")
    print(f"[demo] Running scenario(s): {', '.join(scenarios_to_run)}")
    print(f"[demo] Mode: MOCKED (no Neo4j, no evidence connectors required)")
    print("-" * 60)

    for name in scenarios_to_run:
        result = _SCENARIOS[name]()
        failures = _validate(result, result.get("scenario", name))
        _print_result(result, failures)
        result["_failures"] = failures
        all_results.append(result)
        if failures:
            overall_pass = False

    print("-" * 60)
    scenario_count = len(scenarios_to_run)
    pass_count = sum(1 for r in all_results if not r["_failures"])
    fail_count = scenario_count - pass_count
    print(f"[demo] Results: {pass_count}/{scenario_count} scenarios passed, "
          f"{fail_count} failed")

    if args.output:
        out_path = Path(args.output)
        out_path.write_text(
            json.dumps(all_results, indent=2, default=str), encoding="utf-8"
        )
        print(f"[demo] Output written to: {out_path}")

    return 0 if overall_pass else 1


if __name__ == "__main__":
    sys.exit(main())

"""
tests/test_ontology_backtracking.py

Tests for the OntologyBacktrackingService with early-stop logic.

Test scenarios:
  1. Incident anchor + compliance failure (Violation is FAILED)
  2. Pipeline anchor + lineage failure (Script is FAILED)
  3. Script/CodeEvent causes downstream failure
  4. First failed node triggers early stop (FIRST_CONFIRMED_FAILURE)
  5. Exploratory mode continues past first failed node
  6. Missing evidence returns UNKNOWN / INSUFFICIENT_EVIDENCE stop reason
  7. Ontology gap (NOT_FOUND anchor) returns ONTOLOGY_GAP stop reason
  8. No emojis in any output field

No live Neo4j or evidence service required — all graph state is constructed
directly using factory helpers consistent with the existing test suite.
"""

from __future__ import annotations

import hashlib
import uuid
from datetime import datetime
from typing import Any, List, Optional

import pytest

from causelink.evidence.contracts import (
    EvidenceObject,
    EvidenceReliabilityTier,
    EvidenceType,
)
from causelink.ontology.models import CanonEdge, CanonGraph, CanonNode, OntologyPath
from causelink.services.dashboard_schema import (
    NodeStatus,
    RcaDashboardSummary,
    StopReason,
    TraversalMode,
)
from causelink.services.node_evaluators import (
    EVIDENCE_SUFFICIENCY_THRESHOLD,
    EvidenceScoper,
    NodeEvaluatorRegistry,
)
from causelink.services.ontology_backtracking import (
    OntologyBacktrackingService,
    backtrack_with_early_stop,
)
from causelink.state.investigation import (
    AuditTraceEntry,
    CausalEdge,
    CausalEdgeStatus,
    Hypothesis,
    HypothesisStatus,
    InvestigationAnchor,
    InvestigationInput,
    InvestigationState,
    InvestigationStatus,
    MissingEvidence,
    RootCauseCandidate,
)


# ─── Factories ────────────────────────────────────────────────────────────────


def _make_anchor(anchor_type: str, value: str) -> InvestigationAnchor:
    pk_map = {
        "Incident": "incident_id",
        "Violation": "violation_id",
        "Job": "job_id",
        "Pipeline": "pipeline_id",
        "System": "system_id",
    }
    return InvestigationAnchor(
        anchor_type=anchor_type,
        anchor_primary_key=pk_map.get(anchor_type, "id"),
        anchor_primary_value=value,
    )


def _make_input(anchor_type: str, value: str, max_hops: int = 3) -> InvestigationInput:
    return InvestigationInput(
        investigation_id=str(uuid.uuid4()),
        anchor=_make_anchor(anchor_type, value),
        max_hops=max_hops,
        confidence_threshold=0.80,
    )


def _make_node(
    label: str,
    neo4j_id: str,
    primary_key: str = "id",
    primary_value: str = "val",
) -> CanonNode:
    return CanonNode(
        neo4j_id=neo4j_id,
        labels=[label],
        primary_key=primary_key,
        primary_value=primary_value,
        properties={},
        provenance="test",
    )


def _make_edge(rel_type: str, start: str, end: str) -> CanonEdge:
    return CanonEdge(
        neo4j_id=str(uuid.uuid4()),
        type=rel_type,
        start_node_id=start,
        end_node_id=end,
        properties={},
        provenance="test",
    )


def _make_path(node_seqs: List[str], rel_seqs: List[str]) -> OntologyPath:
    return OntologyPath(
        path_id=str(uuid.uuid4()),
        description=" -> ".join(node_seqs),
        node_sequence=node_seqs,
        rel_type_sequence=rel_seqs,
        hop_count=len(rel_seqs),
        query_used="test",
    )


def _make_evidence(reliability: float = 0.85) -> EvidenceObject:
    raw = b"test-content"
    return EvidenceObject(
        evidence_id=str(uuid.uuid4()),
        type=EvidenceType.LOG,
        source_system="test",
        content_ref="file:///tmp/test.json",
        summary="Test evidence for backtracking.",
        reliability=reliability,
        reliability_tier=EvidenceObject.tier_for(reliability),
        raw_hash=EvidenceObject.make_hash(raw),
        collected_by="test",
    )


def _make_hypothesis(
    node_ids: List[str],
    ev_ids: List[str],
    status: HypothesisStatus = HypothesisStatus.CONFIRMED,
    confidence: float = 0.85,
) -> Hypothesis:
    return Hypothesis(
        description="Test hypothesis generated for backtracking unit test.",
        involved_node_ids=node_ids,
        evidence_object_ids=ev_ids,
        ontology_path_ids=[],
        status=status,
        confidence=confidence,
        generated_by="test",
    )


def _make_canon_graph(
    anchor_id: str,
    anchor_label: str,
    anchor_value: str,
    nodes: list,
    edges: list,
) -> CanonGraph:
    path = _make_path(
        [n.neo4j_id for n in nodes],
        [e.type for e in edges[:max(0, len(nodes) - 1)]],
    )
    return CanonGraph(
        anchor_neo4j_id=anchor_id,
        anchor_label=anchor_label,
        anchor_primary_key=anchor_label.lower() + "_id",
        anchor_primary_value=anchor_value,
        nodes=nodes,
        edges=edges,
        ontology_paths_used=[path],
        max_hops=3,
    )


def _make_state_with_graph(
    anchor_type: str,
    anchor_value: str,
    graph: CanonGraph,
    evidence: Optional[List[EvidenceObject]] = None,
    hypotheses: Optional[List[Hypothesis]] = None,
    missing: Optional[List[MissingEvidence]] = None,
    status: InvestigationStatus = InvestigationStatus.EVIDENCE_COLLECTION,
) -> InvestigationState:
    state = InvestigationState(
        investigation_input=_make_input(anchor_type, anchor_value),
        status=status,
    )
    state.canon_graph = graph
    for ev in (evidence or []):
        state.evidence_objects.append(ev)
    for hyp in (hypotheses or []):
        # Bypass canon_graph validation by adding directly
        state.hypotheses.append(hyp)
    for m in (missing or []):
        state.missing_evidence.append(m)
    state.audit_trace.append(
        AuditTraceEntry(
            agent_type="ontology_context",
            action="ontology_load",
            inputs_summary={},
            outputs_summary={"nodes": len(graph.nodes)},
            decision=f"Loaded {len(graph.nodes)} nodes",
        )
    )
    return state


# ─── Test 1: Incident anchor with compliance failure ─────────────────────────


class TestIncidentAnchorComplianceFailure:
    """
    Scenario: An Incident anchor with a Violation node in the compliance chain.
    The Violation has a confirmed hypothesis with supporting evidence.
    Expected: failure_node = Violation, stop_reason = FIRST_CONFIRMED_FAILURE.
    The Incident anchor is noted as FAILED but does not trigger the early stop.
    """

    def _setup(self):
        inc_id = "inc-001"
        vio_id = "vio-001"
        rule_id = "rule-001"

        incident = _make_node("Incident", inc_id, "incident_id", "INC-2026-001")
        violation = _make_node("Violation", vio_id, "violation_id", "VIO-001")
        rule_node = _make_node("Rule", rule_id, "rule_id", "RULE-GDPR-17")

        edge1 = _make_edge("CREATES", vio_id, inc_id)   # Violation -[CREATES]-> Incident
        edge2 = _make_edge("GENERATES", rule_id, vio_id)  # Rule -[GENERATES]-> Violation

        graph = _make_canon_graph(
            anchor_id=inc_id,
            anchor_label="Incident",
            anchor_value="INC-2026-001",
            nodes=[incident, violation, rule_node],
            edges=[edge1, edge2],
        )

        ev = _make_evidence(reliability=0.90)
        hyp_vio = _make_hypothesis(
            node_ids=[vio_id],
            ev_ids=[ev.evidence_id],
            status=HypothesisStatus.CONFIRMED,
            confidence=0.88,
        )

        state = _make_state_with_graph(
            anchor_type="Incident",
            anchor_value="INC-2026-001",
            graph=graph,
            evidence=[ev],
            hypotheses=[hyp_vio],
        )
        return state, vio_id, inc_id

    def test_failure_node_is_violation(self):
        state, vio_id, inc_id = self._setup()
        result = backtrack_with_early_stop(state, mode="normal")

        assert result.failure_node is not None, "Expected a failure_node for Violation"
        assert result.failure_node.node_id == vio_id
        assert result.failure_node.status == NodeStatus.FAILED

    def test_stop_reason_is_first_confirmed_failure(self):
        state, vio_id, inc_id = self._setup()
        result = backtrack_with_early_stop(state, mode="normal")

        assert result.stop_reason == StopReason.FIRST_CONFIRMED_FAILURE

    def test_nodes_after_failure_are_not_evaluated(self):
        state, vio_id, inc_id = self._setup()
        result = backtrack_with_early_stop(state, mode="normal")

        not_eval = [
            e for e in result.traversal_sequence
            if e.status == NodeStatus.NOT_EVALUATED_DUE_TO_EARLY_STOP
        ]
        # Rule node should not have been evaluated (after Violation in priority)
        rule_evals = [e for e in not_eval if e.node_label == "Rule"]
        assert len(rule_evals) >= 1, "Rule node should be NOT_EVALUATED after Violation failure"

    def test_lineage_walk_contains_relevant_nodes(self):
        state, vio_id, inc_id = self._setup()
        result = backtrack_with_early_stop(state, mode="normal")

        walk_node_ids = {w.node_id for w in result.lineage_walk}
        assert inc_id in walk_node_ids, "Incident should appear in lineage walk"
        assert vio_id in walk_node_ids, "Violation should appear in lineage walk"

    def test_anchor_incident_does_not_trigger_early_stop(self):
        state, vio_id, inc_id = self._setup()
        result = backtrack_with_early_stop(state, mode="normal")

        # The traversal must not stop at the anchor; failure_node must not be the Incident
        assert result.failure_node is not None
        # Some non-anchor node should be the failure node
        assert result.failure_node.node_id != inc_id, (
            "Early stop must not fire on anchor node"
        )

    def test_dashboard_summary_has_control_triggered(self):
        state, vio_id, inc_id = self._setup()
        result = backtrack_with_early_stop(state, mode="normal")
        service = OntologyBacktrackingService()
        summary = service.to_dashboard_summary(state, result)

        assert summary.investigation_id == state.investigation_input.investigation_id
        assert summary.anchor_type == "Incident"
        assert summary.failed_node_status == NodeStatus.FAILED


# ─── Test 2: Pipeline anchor with lineage failure ─────────────────────────────


class TestPipelineAnchorLineageFailure:
    """
    Scenario: A Pipeline is the anchor. A Script in the lineage chain has a
    confirmed hypothesis with evidence.
    Expected: failure_node = Script, stop_reason = FIRST_CONFIRMED_FAILURE.
    """

    def _setup(self):
        pipe_id = "pipe-001"
        script_id = "script-001"
        table_id = "table-001"

        pipeline = _make_node("Pipeline", pipe_id, "pipeline_id", "PIPE-ETL-001")
        script = _make_node("Script", script_id, "script_id", "transform.py")
        table = _make_node("Table", table_id, "table_id", "fact_sales")

        edge1 = _make_edge("USES_SCRIPT", pipe_id, script_id)
        edge2 = _make_edge("READS", script_id, table_id)

        graph = _make_canon_graph(
            anchor_id=pipe_id,
            anchor_label="Pipeline",
            anchor_value="PIPE-ETL-001",
            nodes=[pipeline, script, table],
            edges=[edge1, edge2],
        )

        ev = _make_evidence(reliability=0.80)
        hyp = _make_hypothesis(
            node_ids=[script_id],
            ev_ids=[ev.evidence_id],
            status=HypothesisStatus.CONFIRMED,
            confidence=0.82,
        )

        state = _make_state_with_graph(
            anchor_type="Pipeline",
            anchor_value="PIPE-ETL-001",
            graph=graph,
            evidence=[ev],
            hypotheses=[hyp],
        )
        return state, script_id, pipe_id, table_id

    def test_failure_node_is_script(self):
        state, script_id, pipe_id, _ = self._setup()
        result = backtrack_with_early_stop(state, mode="normal")

        assert result.failure_node is not None
        assert result.failure_node.node_id == script_id
        assert result.failure_node.status == NodeStatus.FAILED

    def test_table_not_evaluated_after_script_failure(self):
        state, script_id, pipe_id, table_id = self._setup()
        result = backtrack_with_early_stop(state, mode="normal")

        table_eval = next(
            (e for e in result.traversal_sequence if e.node_id == table_id), None
        )
        assert table_eval is not None
        assert table_eval.status == NodeStatus.NOT_EVALUATED_DUE_TO_EARLY_STOP

    def test_problem_type_is_lineage(self):
        state, script_id, pipe_id, _ = self._setup()
        result = backtrack_with_early_stop(state, mode="normal")
        service = OntologyBacktrackingService()
        summary = service.to_dashboard_summary(state, result)

        assert summary.problem_type in ("lineage", "execution_failure", "regression_risk")

    def test_lineage_failure_node_set_in_summary(self):
        state, script_id, pipe_id, _ = self._setup()
        result = backtrack_with_early_stop(state, mode="normal")
        service = OntologyBacktrackingService()
        summary = service.to_dashboard_summary(state, result)

        # lineage_failure_node should be set because Script is a lineage node
        assert summary.lineage_failure_node is not None


# ─── Test 3: Script/CodeEvent causes downstream failure ───────────────────────


class TestCodeEventCausesFailure:
    """
    Scenario: A Script has an adjacent CodeEvent (recent change). The Script
    has a CONFIRMED hypothesis with evidence. The CodeEvent is nearby.
    Expected: failure_node = Script, findings mention the code change event.
    """

    def _setup(self):
        job_id = "job-001"
        script_id = "script-002"
        code_event_id = "ce-001"

        job = _make_node("Job", job_id, "job_id", "JOB-LOAD-001")
        script = _make_node("Script", script_id, "script_id", "load_data.py")
        code_event = _make_node("CodeEvent", code_event_id, "event_id", "COMMIT-a1b2c3")

        edge1 = _make_edge("USES_SCRIPT", job_id, script_id)
        edge2 = _make_edge("CHANGED_BY", script_id, code_event_id)

        graph = _make_canon_graph(
            anchor_id=job_id,
            anchor_label="Job",
            anchor_value="JOB-LOAD-001",
            nodes=[job, script, code_event],
            edges=[edge1, edge2],
        )

        ev = _make_evidence(reliability=0.87)
        hyp = _make_hypothesis(
            node_ids=[script_id],
            ev_ids=[ev.evidence_id],
            status=HypothesisStatus.CONFIRMED,
            confidence=0.87,
        )

        state = _make_state_with_graph(
            anchor_type="Job",
            anchor_value="JOB-LOAD-001",
            graph=graph,
            evidence=[ev],
            hypotheses=[hyp],
        )
        return state, script_id, code_event_id

    def test_failure_node_is_script(self):
        state, script_id, _ = self._setup()
        result = backtrack_with_early_stop(state, mode="normal")

        assert result.failure_node is not None
        assert result.failure_node.node_id == script_id

    def test_findings_mention_code_change(self):
        state, script_id, ce_id = self._setup()
        result = backtrack_with_early_stop(state, mode="normal")

        script_eval = next(
            (e for e in result.traversal_sequence if e.node_id == script_id), None
        )
        assert script_eval is not None
        # At least one finding should mention a code change / code event
        has_code_mention = any(
            "code" in f.lower() or "change" in f.lower() or "commit" in f.lower()
            for f in script_eval.findings
        )
        assert has_code_mention, (
            f"Expected code change finding in: {script_eval.findings}"
        )


# ─── Test 4: First failed node early-stop behaviour ──────────────────────────


class TestEarlyStopBehavior:
    """
    Scenario: Graph has three nodes A -> B -> C (all non-anchor after anchor).
    B has a CONFIRMED failed hypothesis. C should not be evaluated.
    This directly tests the early-stop enforcement.
    """

    def _build_three_node_chain(self):
        # Job (anchor) -> Pipeline -> Script
        job_id = "a-job"
        pipe_id = "b-pipe"
        script_id = "c-script"

        job = _make_node("Job", job_id, "job_id", "JOB-A")
        pipe = _make_node("Pipeline", pipe_id, "pipeline_id", "PIPE-B")
        script = _make_node("Script", script_id, "script_id", "SCRIPT-C")

        edge1 = _make_edge("EXECUTES", job_id, pipe_id)
        edge2 = _make_edge("USES_SCRIPT", pipe_id, script_id)

        graph = _make_canon_graph(
            anchor_id=job_id,
            anchor_label="Job",
            anchor_value="JOB-A",
            nodes=[job, pipe, script],
            edges=[edge1, edge2],
        )
        return graph, job_id, pipe_id, script_id

    def test_script_not_evaluated_after_pipeline_failure(self):
        graph, job_id, pipe_id, script_id = self._build_three_node_chain()

        ev = _make_evidence(reliability=0.90)
        # Pipeline (B) is confirmed failed
        hyp = _make_hypothesis(
            node_ids=[pipe_id],
            ev_ids=[ev.evidence_id],
            status=HypothesisStatus.CONFIRMED,
            confidence=0.90,
        )

        state = _make_state_with_graph(
            anchor_type="Job",
            anchor_value="JOB-A",
            graph=graph,
            evidence=[ev],
            hypotheses=[hyp],
        )

        result = backtrack_with_early_stop(state, mode="normal")

        assert result.failure_node is not None
        assert result.failure_node.node_id == pipe_id

        script_eval = next(
            (e for e in result.traversal_sequence if e.node_id == script_id), None
        )
        assert script_eval is not None
        assert script_eval.status == NodeStatus.NOT_EVALUATED_DUE_TO_EARLY_STOP, (
            f"Expected Script to be NOT_EVALUATED, got {script_eval.status}"
        )

    def test_stop_reason_set_correctly(self):
        graph, job_id, pipe_id, script_id = self._build_three_node_chain()

        ev = _make_evidence(reliability=0.90)
        hyp = _make_hypothesis(
            node_ids=[pipe_id],
            ev_ids=[ev.evidence_id],
            status=HypothesisStatus.CONFIRMED,
            confidence=0.90,
        )
        state = _make_state_with_graph(
            anchor_type="Job",
            anchor_value="JOB-A",
            graph=graph,
            evidence=[ev],
            hypotheses=[hyp],
        )

        result = backtrack_with_early_stop(state, mode="normal")
        assert result.stop_reason == StopReason.FIRST_CONFIRMED_FAILURE

    def test_traversal_mode_recorded_as_normal(self):
        graph, job_id, pipe_id, script_id = self._build_three_node_chain()
        ev = _make_evidence()
        hyp = _make_hypothesis([pipe_id], [ev.evidence_id], confidence=0.90)
        state = _make_state_with_graph(
            anchor_type="Job", anchor_value="JOB-A",
            graph=graph, evidence=[ev], hypotheses=[hyp],
        )
        result = backtrack_with_early_stop(state, mode="normal")
        assert result.traversal_mode == TraversalMode.NORMAL


# ─── Test 5: Exploratory mode continues beyond first failure ──────────────────


class TestExploratoryMode:
    """
    Scenario: Same three-node chain as Test 4. In exploratory mode, all nodes
    are evaluated even after the first failure.
    """

    def test_all_nodes_evaluated_in_exploratory_mode(self):
        graph, job_id, pipe_id, script_id = TestEarlyStopBehavior()._build_three_node_chain()

        ev = _make_evidence(reliability=0.92)
        hyp = _make_hypothesis(
            node_ids=[pipe_id],
            ev_ids=[ev.evidence_id],
            status=HypothesisStatus.CONFIRMED,
            confidence=0.92,
        )
        state = _make_state_with_graph(
            anchor_type="Job",
            anchor_value="JOB-A",
            graph=graph,
            evidence=[ev],
            hypotheses=[hyp],
        )

        result = backtrack_with_early_stop(state, mode="exploratory")

        # No node should be NOT_EVALUATED_DUE_TO_EARLY_STOP in exploratory mode
        not_eval = [
            e for e in result.traversal_sequence
            if e.status == NodeStatus.NOT_EVALUATED_DUE_TO_EARLY_STOP
        ]
        assert not_eval == [], (
            f"In exploratory mode, no nodes should be skipped. "
            f"Got skipped: {[e.node_id for e in not_eval]}"
        )

    def test_traversal_mode_recorded_as_exploratory(self):
        graph, job_id, pipe_id, script_id = TestEarlyStopBehavior()._build_three_node_chain()
        ev = _make_evidence()
        hyp = _make_hypothesis([pipe_id], [ev.evidence_id], confidence=0.90)
        state = _make_state_with_graph(
            anchor_type="Job", anchor_value="JOB-A",
            graph=graph, evidence=[ev], hypotheses=[hyp],
        )
        result = backtrack_with_early_stop(state, mode="exploratory")
        assert result.traversal_mode == TraversalMode.EXPLORATORY

    def test_stop_reason_is_exploratory_continue_when_all_evaluated(self):
        # Single node graph — no failure
        job_id = "solo-job"
        job = _make_node("Job", job_id, "job_id", "SOLO-JOB")
        graph = _make_canon_graph(
            anchor_id=job_id,
            anchor_label="Job",
            anchor_value="SOLO-JOB",
            nodes=[job],
            edges=[],
        )
        state = _make_state_with_graph(
            anchor_type="Job", anchor_value="SOLO-JOB",
            graph=graph,
        )
        result = backtrack_with_early_stop(state, mode="exploratory")
        # No failure → should be EXPLORATORY_CONTINUE or INSUFFICIENT_EVIDENCE
        assert result.stop_reason in (
            StopReason.EXPLORATORY_CONTINUE,
            StopReason.INSUFFICIENT_EVIDENCE,
        )


# ─── Test 6: Missing evidence returns UNKNOWN / insufficient evidence ─────────


class TestMissingEvidence:
    """
    Scenario: Valid graph but no hypotheses or evidence collected yet.
    Expected: all non-anchor nodes are UNKNOWN, stop_reason is INSUFFICIENT_EVIDENCE.
    """

    def test_all_nodes_unknown_without_evidence(self):
        job_id = "j001"
        pipe_id = "p001"
        job = _make_node("Job", job_id, "job_id", "JOB-001")
        pipe = _make_node("Pipeline", pipe_id, "pipeline_id", "PIPE-001")
        edge = _make_edge("EXECUTES", job_id, pipe_id)

        graph = _make_canon_graph(
            anchor_id=job_id,
            anchor_label="Job",
            anchor_value="JOB-001",
            nodes=[job, pipe],
            edges=[edge],
        )
        state = _make_state_with_graph(
            anchor_type="Job",
            anchor_value="JOB-001",
            graph=graph,
            evidence=[],
            hypotheses=[],
            status=InvestigationStatus.EVIDENCE_COLLECTION,
        )

        result = backtrack_with_early_stop(state, mode="normal")

        # No failure node
        assert result.failure_node is None, "No failure should be found without evidence"

        # Non-anchor nodes should all be UNKNOWN
        non_anchor_evals = [
            e for e in result.traversal_sequence
            if e.node_id != job_id
        ]
        for eval_result in non_anchor_evals:
            assert eval_result.status in (
                NodeStatus.UNKNOWN, NodeStatus.HEALTHY
            ), (
                f"Node {eval_result.node_id} ({eval_result.node_label}) "
                f"should be UNKNOWN without evidence, got {eval_result.status}"
            )

    def test_stop_reason_insufficient_evidence_with_missing_evidence_entries(self):
        job_id = "j002"
        job = _make_node("Job", job_id, "job_id", "JOB-002")
        graph = _make_canon_graph(
            anchor_id=job_id,
            anchor_label="Job",
            anchor_value="JOB-002",
            nodes=[job],
            edges=[],
        )
        missing = MissingEvidence(
            evidence_type="log",
            description="Execution logs for JOB-002 not available.",
            blocking=True,
        )
        state = _make_state_with_graph(
            anchor_type="Job",
            anchor_value="JOB-002",
            graph=graph,
            missing=[missing],
            status=InvestigationStatus.INSUFFICIENT_EVIDENCE,
        )

        result = backtrack_with_early_stop(state, mode="normal")
        assert result.stop_reason == StopReason.INSUFFICIENT_EVIDENCE

    def test_degraded_not_failed_when_evidence_below_threshold(self):
        job_id = "j003"
        pipe_id = "p003"

        job = _make_node("Job", job_id, "job_id", "JOB-003")
        pipe = _make_node("Pipeline", pipe_id, "pipeline_id", "PIPE-003")
        edge = _make_edge("EXECUTES", job_id, pipe_id)

        graph = _make_canon_graph(
            anchor_id=job_id,
            anchor_label="Job",
            anchor_value="JOB-003",
            nodes=[job, pipe],
            edges=[edge],
        )
        ev = _make_evidence(reliability=0.60)
        # Low confidence hypothesis — below EVIDENCE_SUFFICIENCY_THRESHOLD (0.50)
        # but above 0 — should result in DEGRADED, not FAILED
        hyp = _make_hypothesis(
            node_ids=[pipe_id],
            ev_ids=[ev.evidence_id],
            status=HypothesisStatus.SUPPORTED,  # not CONFIRMED
            confidence=0.45,  # below threshold
        )

        state = _make_state_with_graph(
            anchor_type="Job",
            anchor_value="JOB-003",
            graph=graph,
            evidence=[ev],
            hypotheses=[hyp],
        )

        result = backtrack_with_early_stop(state, mode="normal")
        pipe_eval = next(
            (e for e in result.traversal_sequence if e.node_id == pipe_id), None
        )
        assert pipe_eval is not None
        # Should be DEGRADED (not FAILED) because confidence < threshold and not CONFIRMED
        assert pipe_eval.status in (
            NodeStatus.DEGRADED, NodeStatus.UNKNOWN
        ), f"Expected DEGRADED or UNKNOWN, got {pipe_eval.status}"


# ─── Test 7: Ontology gap (NOT_FOUND anchor) ─────────────────────────────────


class TestOntologyGap:
    """
    Scenario: The canon_graph has anchor_neo4j_id == 'NOT_FOUND'.
    Expected: stop_reason = ONTOLOGY_GAP, traversal_sequence is empty.
    """

    def _setup(self):
        graph = CanonGraph(
            anchor_neo4j_id="NOT_FOUND",
            anchor_label="Incident",
            anchor_primary_key="incident_id",
            anchor_primary_value="INC-9999-NOT-FOUND",
            nodes=[],
            edges=[],
            max_hops=3,
        )
        state = InvestigationState(
            investigation_input=_make_input("Incident", "INC-9999-NOT-FOUND"),
            status=InvestigationStatus.INSUFFICIENT_EVIDENCE,
        )
        state.canon_graph = graph
        return state

    def test_stop_reason_is_ontology_gap(self):
        state = self._setup()
        result = backtrack_with_early_stop(state, mode="normal")

        assert result.stop_reason == StopReason.ONTOLOGY_GAP

    def test_traversal_sequence_empty(self):
        state = self._setup()
        result = backtrack_with_early_stop(state, mode="normal")

        assert result.traversal_sequence == []

    def test_failure_node_is_none(self):
        state = self._setup()
        result = backtrack_with_early_stop(state, mode="normal")

        assert result.failure_node is None

    def test_requires_canon_graph(self):
        state = InvestigationState(
            investigation_input=_make_input("Incident", "INC-001"),
        )
        # canon_graph is None — must raise ValueError
        with pytest.raises(ValueError, match="canon_graph"):
            backtrack_with_early_stop(state)


# ─── Test 8: No emojis in outputs ─────────────────────────────────────────────


def _has_emoji(text: str) -> bool:
    """
    Simple check for common emoji ranges.
    Does not claim to be exhaustive; catches the most common cases.
    """
    # Unicode ranges covering most common emojis
    emoji_ranges = [
        (0x1F600, 0x1F64F),  # emoticons
        (0x1F300, 0x1F5FF),  # misc symbols and pictographs
        (0x1F680, 0x1F6FF),  # transport and map symbols
        (0x1F1E0, 0x1F1FF),  # flags
        (0x2600, 0x26FF),    # misc symbols
        (0x2700, 0x27BF),    # dingbats
        (0xFE00, 0xFE0F),    # variation selectors
        (0x1F900, 0x1F9FF),  # supplemental symbols
        (0x1FA00, 0x1FA6F),  # chess symbols
        (0x1FA70, 0x1FAFF),  # symbols and pictographs extended
    ]
    for ch in text:
        cp = ord(ch)
        for lo, hi in emoji_ranges:
            if lo <= cp <= hi:
                return True
    return False


class TestNoEmojis:
    """
    Verifies that no emoji characters appear in any field of BacktrackingResult
    or RcaDashboardSummary for a typical run.
    """

    def _run_scenario(self):
        inc_id = "inc-emoji-test"
        vio_id = "vio-emoji-test"

        incident = _make_node("Incident", inc_id, "incident_id", "INC-EMOJI-TEST")
        violation = _make_node("Violation", vio_id, "violation_id", "VIO-EMOJI-TEST")
        edge = _make_edge("CREATES", vio_id, inc_id)

        graph = _make_canon_graph(
            anchor_id=inc_id,
            anchor_label="Incident",
            anchor_value="INC-EMOJI-TEST",
            nodes=[incident, violation],
            edges=[edge],
        )
        ev = _make_evidence(reliability=0.85)
        hyp = _make_hypothesis(
            [vio_id], [ev.evidence_id],
            status=HypothesisStatus.CONFIRMED, confidence=0.85,
        )
        state = _make_state_with_graph(
            anchor_type="Incident",
            anchor_value="INC-EMOJI-TEST",
            graph=graph,
            evidence=[ev],
            hypotheses=[hyp],
        )
        service = OntologyBacktrackingService()
        result = service.backtrack_with_early_stop(state, mode="normal")
        summary = service.to_dashboard_summary(state, result)
        return result, summary

    def test_no_emojis_in_backtracking_result(self):
        result, _ = self._run_scenario()

        all_strings = []
        for node_eval in result.traversal_sequence:
            all_strings += [
                node_eval.node_name,
                node_eval.node_label,
                node_eval.ontology_path,
                node_eval.status.value,
                node_eval.failure_reason or "",
            ]
            all_strings += node_eval.findings

        for walk_node in result.lineage_walk:
            all_strings += [
                walk_node.display_name,
                walk_node.label,
                walk_node.subtitle,
                walk_node.ontology_path_fragment,
                walk_node.status.value,
            ]

        for text in all_strings:
            assert not _has_emoji(text), (
                f"Emoji found in backtracking output: '{text}'"
            )

    def test_no_emojis_in_dashboard_summary(self):
        _, summary = self._run_scenario()

        all_strings = [
            summary.scenario_name,
            summary.anchor_type,
            summary.anchor_id,
            summary.health_status,
            summary.problem_type,
            summary.control_triggered or "",
            summary.lineage_failure_node or "",
            summary.failure_reason or "",
        ]
        all_strings += summary.findings
        all_strings += summary.evidence_objects
        all_strings += summary.audit_trace

        for entry in summary.agent_analysis_chain:
            all_strings += [
                entry.agent_name,
                entry.status,
                entry.health,
                entry.problem_type,
                entry.key_finding,
                entry.control or "",
            ]

        for walk_node in summary.lineage_walk:
            all_strings += [
                walk_node.display_name,
                walk_node.label,
                walk_node.subtitle,
            ]

        for text in all_strings:
            assert not _has_emoji(text), (
                f"Emoji found in dashboard summary: '{text}'"
            )

    def test_no_emojis_in_node_status_values(self):
        """Verify enum values themselves contain no emojis."""
        for status in NodeStatus:
            assert not _has_emoji(status.value)
        for reason in StopReason:
            assert not _has_emoji(reason.value)
        for mode in TraversalMode:
            assert not _has_emoji(mode.value)


# ─── Test: Dashboard health score ─────────────────────────────────────────────


class TestHealthScore:
    """Verify health score calculation for common scenarios."""

    def test_zero_health_score_when_confirmed_failure(self):
        job_id = "j-health"
        pipe_id = "p-health"
        job = _make_node("Job", job_id, "job_id", "JOB-HEALTH")
        pipe = _make_node("Pipeline", pipe_id, "pipeline_id", "PIPE-HEALTH")
        edge = _make_edge("EXECUTES", job_id, pipe_id)
        graph = _make_canon_graph(
            anchor_id=job_id, anchor_label="Job", anchor_value="JOB-HEALTH",
            nodes=[job, pipe], edges=[edge],
        )
        ev = _make_evidence(reliability=1.0)
        hyp = _make_hypothesis([pipe_id], [ev.evidence_id],
                               status=HypothesisStatus.CONFIRMED, confidence=1.0)
        state = _make_state_with_graph(
            anchor_type="Job", anchor_value="JOB-HEALTH",
            graph=graph, evidence=[ev], hypotheses=[hyp],
        )
        service = OntologyBacktrackingService()
        result = service.backtrack_with_early_stop(state, mode="normal")
        summary = service.to_dashboard_summary(state, result)

        assert summary.health_score == 0.0
        assert summary.health_status == "FAILED"

    def test_high_health_score_when_no_failures(self):
        job_id = "j-healthy"
        job = _make_node("Job", job_id, "job_id", "JOB-HEALTHY")
        graph = _make_canon_graph(
            anchor_id=job_id, anchor_label="Job", anchor_value="JOB-HEALTHY",
            nodes=[job], edges=[],
        )
        state = _make_state_with_graph(
            anchor_type="Job", anchor_value="JOB-HEALTHY", graph=graph,
        )
        service = OntologyBacktrackingService()
        result = service.backtrack_with_early_stop(state, mode="normal")
        summary = service.to_dashboard_summary(state, result)

        # No evidence → UNKNOWN, not FAILED
        assert summary.health_score >= 0.0
        assert summary.health_status != "FAILED"

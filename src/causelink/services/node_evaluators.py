"""
causelink/services/node_evaluators.py

Per-label node evaluators for the ontology backtracking traversal.

Each evaluator:
  - Consumes only evidence/hypotheses already present in InvestigationState.
  - Returns a typed NodeEvaluationResult.
  - Never fabricates evidence or invents ontology relationships.
  - Uses hypothesis-based signals as the primary failure indicator.

Evidence scoping:
  Evidence is connected to nodes via:
    node_id -> hypotheses (involved_node_ids) -> evidence_object_ids -> EvidenceObjects

A node can be marked FAILED only when ALL hold:
  1. structural path from anchor to node exists in the CanonGraph (checked by caller)
  2. At least one CONFIRMED or high-confidence PROBABLE hypothesis involves this node
  3. That hypothesis has at least one cited evidence_object_id
  4. confidence >= EVIDENCE_SUFFICIENCY_THRESHOLD

If evidence is partial: DEGRADED.
If no hypotheses reference the node: UNKNOWN.
If all referencing hypotheses are REFUTED: HEALTHY.
"""

from __future__ import annotations

import logging
from datetime import datetime
from typing import Any, Dict, List, Optional, Set, Tuple

from causelink.evidence.contracts import EvidenceObject
from causelink.ontology.models import CanonGraph, CanonNode
from causelink.services.dashboard_schema import NodeEvaluationResult, NodeStatus
from causelink.state.investigation import (
    HypothesisStatus,
    InvestigationState,
    RootCauseCandidate,
)

logger = logging.getLogger(__name__)

# A node is marked FAILED only when confidence reaches this threshold
EVIDENCE_SUFFICIENCY_THRESHOLD = 0.50

# Labels that belong to compliance chain — tighter rules apply
_COMPLIANCE_LABELS: frozenset = frozenset({
    "Incident", "Violation", "Rule", "ControlObjective", "Regulation",
    "Escalation", "Remediation",
})

# Labels that imply operational execution
_OPERATIONAL_LABELS: frozenset = frozenset({"System", "Job", "Pipeline"})

# Labels that belong to the lineage chain
_LINEAGE_LABELS: frozenset = frozenset({
    "Script", "Transformation", "DataSource", "Dataset", "Table", "Column",
})

# Labels in the change-provenance chain
_CHANGE_LABELS: frozenset = frozenset({"CodeEvent"})

# Log scope
_LOG_LABELS: frozenset = frozenset({"LogSource"})


# ─── EvidenceScoper ───────────────────────────────────────────────────────────


class EvidenceScoper:
    """
    Extracts evidence and hypothesis signals scoped to a single CanonNode.

    Uses only data already present in InvestigationState — never queries
    any external system.
    """

    def __init__(self, state: InvestigationState) -> None:
        self._state = state
        # Build index: evidence_id -> EvidenceObject
        self._evidence_index: Dict[str, Any] = {
            ev.evidence_id: ev
            for ev in state.evidence_objects
            if hasattr(ev, "evidence_id")
        }
        # Build index: node_id -> list of (hypothesis, [EvidenceObject])
        self._hyp_by_node: Dict[str, List[Any]] = {}
        for hyp in state.hypotheses:
            for nid in hyp.involved_node_ids:
                self._hyp_by_node.setdefault(nid, []).append(hyp)

        # Build set: node_ids that appear as cause in a VALID causal edge
        self._failing_cause_ids: Set[str] = {
            e.cause_node_id
            for e in state.causal_graph_edges
            if e.status.value == "VALID" and e.structural_path_validated
        }

        # Build index: node_id -> list of candidates that reference it
        self._candidates_by_node: Dict[str, List[RootCauseCandidate]] = {}
        for cand in state.root_cause_candidates:
            self._candidates_by_node.setdefault(cand.node_id, []).append(cand)

    def hypotheses_for_node(self, node_id: str) -> List[Any]:
        """Return hypotheses that involve the given node."""
        return self._hyp_by_node.get(node_id, [])

    def evidence_for_node(self, node_id: str) -> List[Any]:
        """Return EvidenceObjects cited in hypotheses that involve this node."""
        hyps = self.hypotheses_for_node(node_id)
        seen: Set[str] = set()
        result = []
        for hyp in hyps:
            for ev_id in hyp.evidence_object_ids:
                if ev_id not in seen:
                    seen.add(ev_id)
                    ev = self._evidence_index.get(ev_id)
                    if ev is not None:
                        result.append(ev)
        return result

    def is_confirmed_cause(self, node_id: str) -> bool:
        """True when a VALID causal edge has this node as its cause."""
        return node_id in self._failing_cause_ids

    def candidates_for_node(self, node_id: str) -> List[RootCauseCandidate]:
        """Return root cause candidates whose node_id matches."""
        return self._candidates_by_node.get(node_id, [])

    def root_cause_final_node_id(self) -> Optional[str]:
        """Return the node_id of state.root_cause_final if confirmed."""
        rc = self._state.root_cause_final
        return rc.node_id if rc is not None else None


# ─── Base evaluator ───────────────────────────────────────────────────────────


class NodeEvaluator:
    """
    Base class for all per-label node evaluators.

    Subclasses override evaluate() with label-specific logic.
    The evaluate() contract:
      - Never fabricate evidence.
      - Never mark FAILED without evidence_ids.
      - Return NOT_EVALUATED_DUE_TO_EARLY_STOP when order_index exceeds the
        stop index (caller responsibility to set this correctly).
    """

    def evaluate(
        self,
        node: CanonNode,
        scoper: EvidenceScoper,
        order_index: int,
        ontology_path: str,
        graph: CanonGraph,
    ) -> NodeEvaluationResult:
        raise NotImplementedError

    # ── Shared helpers ────────────────────────────────────────────────────────

    @staticmethod
    def _node_name(node: CanonNode) -> str:
        """Derive a display name from the node's primary_value."""
        if node.primary_value:
            return node.primary_value
        pid = node.properties.get("name") or node.properties.get("id")
        return str(pid) if pid is not None else node.neo4j_id

    @staticmethod
    def _derive_status(
        node_id: str,
        scoper: EvidenceScoper,
        is_anchor_incident_or_violation: bool = False,
    ) -> Tuple[NodeStatus, float, Optional[str], List[str], List[str]]:
        """
        Derive status, confidence, failure_reason, evidence_ids, findings from state.

        Returns: (status, confidence, failure_reason, evidence_ids, findings)
        """
        # Check if the final root cause points here
        final_node = scoper.root_cause_final_node_id()
        if final_node == node_id:
            candidates = scoper.candidates_for_node(node_id)
            ev_ids = []
            for cand in candidates:
                hyps = [
                    h for h in scoper._state.hypotheses
                    if h.hypothesis_id in cand.hypothesis_ids
                ]
                for hyp in hyps:
                    ev_ids.extend(hyp.evidence_object_ids)
            ev_ids = list(dict.fromkeys(ev_ids))  # deduplicate, preserve order
            return (
                NodeStatus.FAILED,
                max((c.composite_score for c in candidates), default=0.8),
                "Identified as root cause by ranking agent with confirmed composite score.",
                ev_ids,
                [f"Root cause confirmed by ranking agent for node {node_id}."],
            )

        # Check if it's a cause in a VALID causal edge
        if scoper.is_confirmed_cause(node_id):
            hyps = scoper.hypotheses_for_node(node_id)
            ev_ids = list(dict.fromkeys(
                eid for hyp in hyps for eid in hyp.evidence_object_ids
            ))
            if ev_ids:
                max_conf = max((h.confidence for h in hyps), default=0.6)
                return (
                    NodeStatus.FAILED if max_conf >= EVIDENCE_SUFFICIENCY_THRESHOLD
                    else NodeStatus.DEGRADED,
                    max_conf,
                    "Node appears as confirmed cause in validated causal edge.",
                    ev_ids,
                    ["Causal chain edge validated: this node is a confirmed cause."],
                )

        # Evaluate based on hypothesis status
        hyps = scoper.hypotheses_for_node(node_id)
        if not hyps:
            if is_anchor_incident_or_violation:
                # An Incident or Violation always represents a known failure
                return (
                    NodeStatus.FAILED,
                    1.0,
                    "Anchor is a known Incident or Violation - confirmed failure.",
                    [],
                    ["Incident or Violation anchor confirms failure at this node."],
                )
            return NodeStatus.UNKNOWN, 0.0, None, [], []

        # Gather evidence
        ev_ids = list(dict.fromkeys(
            eid for hyp in hyps for eid in hyp.evidence_object_ids
        ))
        max_confidence = max((h.confidence for h in hyps), default=0.0)

        # Check statuses
        statuses = {h.status for h in hyps}
        confirmed_hyps = [
            h for h in hyps
            if h.status in (HypothesisStatus.CONFIRMED, HypothesisStatus.PROBABLE)
        ]
        refuted_hyps = [h for h in hyps if h.status == HypothesisStatus.REFUTED]
        supported_hyps = [h for h in hyps if h.status == HypothesisStatus.SUPPORTED]
        possible_hyps = [h for h in hyps if h.status == HypothesisStatus.POSSIBLE]

        findings = []

        if confirmed_hyps:
            # Some hypotheses confirmed. Need evidence to call FAILED.
            if ev_ids and max_confidence >= EVIDENCE_SUFFICIENCY_THRESHOLD:
                reason = f"Hypothesis confirmed: {confirmed_hyps[0].description[:120]}"
                findings.append(
                    f"Hypothesis confirmed with confidence {max_confidence:.2f}: "
                    f"{confirmed_hyps[0].description[:80]}"
                )
                return NodeStatus.FAILED, max_confidence, reason, ev_ids, findings
            elif ev_ids:
                # Has evidence but below threshold → DEGRADED
                return (
                    NodeStatus.DEGRADED,
                    max_confidence,
                    f"Hypothesis supported but confidence {max_confidence:.2f} below threshold.",
                    ev_ids,
                    [f"Partial evidence: confidence {max_confidence:.2f}."],
                )
            else:
                # Confirmed hypothesis but no evidence_ids → cannot call FAILED
                return (
                    NodeStatus.DEGRADED,
                    max_confidence,
                    "Hypothesis confirmed but has no cited evidence objects.",
                    [],
                    ["Hypothesis present but lacks supporting evidence objects."],
                )

        if supported_hyps or possible_hyps:
            if ev_ids:
                return (
                    NodeStatus.DEGRADED,
                    max_confidence,
                    "Hypothesis supported but not yet confirmed.",
                    ev_ids,
                    [f"Unconfirmed hypothesis with {len(ev_ids)} evidence object(s)."],
                )
            return (
                NodeStatus.UNKNOWN,
                max_confidence,
                None,
                [],
                ["Hypothesis proposed but no evidence collected yet."],
            )

        if refuted_hyps and not confirmed_hyps and not supported_hyps:
            return NodeStatus.HEALTHY, max_confidence, None, ev_ids, [
                "All hypotheses for this node were refuted by evidence."
            ]

        return NodeStatus.UNKNOWN, 0.0, None, [], []


# ─── Compliance evaluator (Incident, Violation, Rule, ControlObjective, Regulation) ─


class ComplianceNodeEvaluator(NodeEvaluator):
    """
    Evaluates compliance chain nodes: Incident, Violation, Rule, ControlObjective, Regulation.

    Incident/Violation: Always FAILED (their existence IS the failure).
    Rule/ControlObjective: FAILED when hypothesis evidence supports a compliance gap.
    Regulation: Evaluated via hypothesis signals only.
    """

    def evaluate(
        self,
        node: CanonNode,
        scoper: EvidenceScoper,
        order_index: int,
        ontology_path: str,
        graph: CanonGraph,
    ) -> NodeEvaluationResult:
        label = node.labels[0] if node.labels else "Unknown"
        name = self._node_name(node)
        is_outcome = label in ("Incident", "Violation")

        status, confidence, failure_reason, ev_ids, findings = self._derive_status(
            node.neo4j_id,
            scoper,
            is_anchor_incident_or_violation=is_outcome,
        )

        # Collect compliance control IDs from adjacent Rule/ControlObjective nodes
        control_ids: List[str] = []
        if label in ("Rule", "ControlObjective") and node.primary_value:
            control_ids = [node.primary_value]
        elif label in ("Incident", "Violation"):
            # Find adjacent Rule/ControlObjective nodes
            for edge in graph.edges:
                neighbor_id = None
                if edge.start_node_id == node.neo4j_id:
                    neighbor_id = edge.end_node_id
                elif edge.end_node_id == node.neo4j_id:
                    neighbor_id = edge.start_node_id
                if neighbor_id:
                    nb = graph.get_node(neighbor_id)
                    if nb and any(
                        lbl in ("Rule", "ControlObjective") for lbl in nb.labels
                    ):
                        if nb.primary_value:
                            control_ids.append(nb.primary_value)

        return NodeEvaluationResult(
            node_id=node.neo4j_id,
            node_label=label,
            node_name=name,
            status=status,
            failure_reason=failure_reason,
            evidence_ids=ev_ids,
            ontology_path=ontology_path,
            confidence=confidence,
            control_ids=control_ids,
            findings=findings,
            order_index=order_index,
        )


# ─── Operational evaluator (System, Job, Pipeline) ────────────────────────────


class OperationalNodeEvaluator(NodeEvaluator):
    """
    Evaluates operational chain nodes: System, Job, Pipeline.

    Uses hypothesis signals and causal edge confirmation.
    """

    def evaluate(
        self,
        node: CanonNode,
        scoper: EvidenceScoper,
        order_index: int,
        ontology_path: str,
        graph: CanonGraph,
    ) -> NodeEvaluationResult:
        label = node.labels[0] if node.labels else "Unknown"
        name = self._node_name(node)

        status, confidence, failure_reason, ev_ids, findings = self._derive_status(
            node.neo4j_id, scoper
        )

        return NodeEvaluationResult(
            node_id=node.neo4j_id,
            node_label=label,
            node_name=name,
            status=status,
            failure_reason=failure_reason,
            evidence_ids=ev_ids,
            ontology_path=ontology_path,
            confidence=confidence,
            control_ids=[],
            findings=findings,
            order_index=order_index,
        )


# ─── Lineage evaluator (Script, Transformation, Table, Column, Dataset) ───────


class LineageNodeEvaluator(NodeEvaluator):
    """
    Evaluates lineage chain nodes: Script, Transformation, Table, Column,
    DataSource, Dataset.

    Additionally checks for CodeEvent neighbors (change provenance signal).
    """

    def evaluate(
        self,
        node: CanonNode,
        scoper: EvidenceScoper,
        order_index: int,
        ontology_path: str,
        graph: CanonGraph,
    ) -> NodeEvaluationResult:
        label = node.labels[0] if node.labels else "Unknown"
        name = self._node_name(node)

        status, confidence, failure_reason, ev_ids, findings = self._derive_status(
            node.neo4j_id, scoper
        )

        # Augment findings when a CodeEvent is adjacent (change provenance signal)
        code_events = [
            nb
            for nb in graph.neighbors(node.neo4j_id)
            if "CodeEvent" in nb.labels
        ]
        if code_events and status in (NodeStatus.FAILED, NodeStatus.DEGRADED):
            for ce in code_events[:3]:  # include up to 3 code events in findings
                ce_name = self._node_name(ce)
                findings.append(
                    f"Adjacent code change event detected: {ce_name}. "
                    "This may indicate a recent change introduced the failure."
                )

        return NodeEvaluationResult(
            node_id=node.neo4j_id,
            node_label=label,
            node_name=name,
            status=status,
            failure_reason=failure_reason,
            evidence_ids=ev_ids,
            ontology_path=ontology_path,
            confidence=confidence,
            control_ids=[],
            findings=findings,
            order_index=order_index,
        )


# ─── Change provenance evaluator (CodeEvent) ─────────────────────────────────


class CodeEventEvaluator(NodeEvaluator):
    """
    Evaluates change provenance nodes: CodeEvent.

    A CodeEvent is FAILED when it is cited in a CONFIRMED hypothesis
    that implicates the related script/pipeline in the failure.
    """

    def evaluate(
        self,
        node: CanonNode,
        scoper: EvidenceScoper,
        order_index: int,
        ontology_path: str,
        graph: CanonGraph,
    ) -> NodeEvaluationResult:
        label = node.labels[0] if node.labels else "Unknown"
        name = self._node_name(node)

        status, confidence, failure_reason, ev_ids, findings = self._derive_status(
            node.neo4j_id, scoper
        )

        return NodeEvaluationResult(
            node_id=node.neo4j_id,
            node_label=label,
            node_name=name,
            status=status,
            failure_reason=failure_reason,
            evidence_ids=ev_ids,
            ontology_path=ontology_path,
            confidence=confidence,
            control_ids=[],
            findings=findings,
            order_index=order_index,
        )


# ─── Log scope evaluator (LogSource) ─────────────────────────────────────────


class LogSourceEvaluator(NodeEvaluator):
    """
    Evaluates log scope nodes: LogSource.

    A LogSource is DEGRADED if there are missing_evidence entries referencing it,
    FAILED if a hypothesis explicitly implicates it, UNKNOWN otherwise.
    """

    def evaluate(
        self,
        node: CanonNode,
        scoper: EvidenceScoper,
        order_index: int,
        ontology_path: str,
        graph: CanonGraph,
    ) -> NodeEvaluationResult:
        label = node.labels[0] if node.labels else "Unknown"
        name = self._node_name(node)

        status, confidence, failure_reason, ev_ids, findings = self._derive_status(
            node.neo4j_id, scoper
        )

        # If no hypotheses but there are missing_evidence entries: DEGRADED
        if status == NodeStatus.UNKNOWN:
            node_val = node.primary_value or ""
            missing = [
                m for m in scoper._state.missing_evidence
                if node_val and node_val in m.description
            ]
            if missing:
                status = NodeStatus.DEGRADED
                failure_reason = (
                    f"Log source has {len(missing)} missing evidence entries. "
                    "Log data may be unavailable for this scope."
                )
                findings = [
                    f"Missing evidence: {m.description[:80]}" for m in missing[:3]
                ]

        return NodeEvaluationResult(
            node_id=node.neo4j_id,
            node_label=label,
            node_name=name,
            status=status,
            failure_reason=failure_reason,
            evidence_ids=ev_ids,
            ontology_path=ontology_path,
            confidence=confidence,
            control_ids=[],
            findings=findings,
            order_index=order_index,
        )


# ─── Generic fallback evaluator ───────────────────────────────────────────────


class GenericNodeEvaluator(NodeEvaluator):
    """
    Generic evaluator for any node label not covered by a specialised evaluator.

    Uses hypothesis signals only.
    """

    def evaluate(
        self,
        node: CanonNode,
        scoper: EvidenceScoper,
        order_index: int,
        ontology_path: str,
        graph: CanonGraph,
    ) -> NodeEvaluationResult:
        label = node.labels[0] if node.labels else "Unknown"
        name = self._node_name(node)

        status, confidence, failure_reason, ev_ids, findings = self._derive_status(
            node.neo4j_id, scoper
        )

        return NodeEvaluationResult(
            node_id=node.neo4j_id,
            node_label=label,
            node_name=name,
            status=status,
            failure_reason=failure_reason,
            evidence_ids=ev_ids,
            ontology_path=ontology_path,
            confidence=confidence,
            control_ids=[],
            findings=findings,
            order_index=order_index,
        )


# ─── Registry ─────────────────────────────────────────────────────────────────


class NodeEvaluatorRegistry:
    """
    Dispatches evaluation to the correct per-label evaluator.

    Falls back to GenericNodeEvaluator for unregistered labels.
    New specialised evaluators must be registered at initialisation.
    """

    def __init__(self) -> None:
        compliance_ev = ComplianceNodeEvaluator()
        operational_ev = OperationalNodeEvaluator()
        lineage_ev = LineageNodeEvaluator()
        code_ev = CodeEventEvaluator()
        log_ev = LogSourceEvaluator()
        generic_ev = GenericNodeEvaluator()

        self._registry: Dict[str, NodeEvaluator] = {
            # Compliance chain
            "Incident": compliance_ev,
            "Violation": compliance_ev,
            "Rule": compliance_ev,
            "ControlObjective": compliance_ev,
            "Regulation": compliance_ev,
            "Escalation": compliance_ev,
            "Remediation": compliance_ev,
            # Operational chain
            "System": operational_ev,
            "Job": operational_ev,
            "Pipeline": operational_ev,
            # Lineage chain
            "Script": lineage_ev,
            "Transformation": lineage_ev,
            "DataSource": lineage_ev,
            "Dataset": lineage_ev,
            "Table": lineage_ev,
            "Column": lineage_ev,
            # Change provenance
            "CodeEvent": code_ev,
            # Log scope
            "LogSource": log_ev,
            # Ownership/generic
            "Owner": generic_ev,
        }
        self._fallback = generic_ev

    def evaluate(
        self,
        node: CanonNode,
        scoper: EvidenceScoper,
        order_index: int,
        ontology_path: str,
        graph: CanonGraph,
    ) -> NodeEvaluationResult:
        """
        Evaluate a node using its label-specific evaluator.

        Uses the first label in node.labels for dispatch.
        Falls back to GenericNodeEvaluator for unknown labels.
        """
        primary_label = node.labels[0] if node.labels else ""
        evaluator = self._registry.get(primary_label, self._fallback)
        return evaluator.evaluate(
            node=node,
            scoper=scoper,
            order_index=order_index,
            ontology_path=ontology_path,
            graph=graph,
        )

    def mark_not_evaluated(
        self,
        node: CanonNode,
        order_index: int,
        ontology_path: str,
    ) -> NodeEvaluationResult:
        """
        Return a NOT_EVALUATED_DUE_TO_EARLY_STOP result for a node that was skipped.

        Called by the backtracking service for all nodes after the first confirmed
        failure in normal mode.
        """
        label = node.labels[0] if node.labels else "Unknown"
        name = node.primary_value or node.neo4j_id
        return NodeEvaluationResult(
            node_id=node.neo4j_id,
            node_label=label,
            node_name=name,
            status=NodeStatus.NOT_EVALUATED_DUE_TO_EARLY_STOP,
            failure_reason=None,
            evidence_ids=[],
            ontology_path=ontology_path,
            confidence=0.0,
            control_ids=[],
            findings=[],
            order_index=order_index,
        )

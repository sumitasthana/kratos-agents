"""
causelink/validation/gates.py

ValidationGate — enforces anti-hallucination rules before any claim is accepted.

Rules (all enforced at gate boundary, not trusting agent self-reporting):

    R1  All evidence_object_ids cited in a Hypothesis must exist in
        InvestigationState.evidence_objects.

    R2  All ontology_path_ids cited in a Hypothesis must exist in
        InvestigationState.ontology_paths_used OR in canon_graph.ontology_paths_used.

    R3  All involved_node_ids in a Hypothesis must exist in canon_graph.

    R4  A CausalEdge may only be VALID when structural_path_validated=True.

    R5  A RootCauseCandidate may only achieve CONFIRMED status through the
        RankerAgent; ValidationGate rejects CONFIRMED status set by any other agent.

    R6  A CanonGraph must have anchor_neo4j_id != "NOT_FOUND" before agents
        may proceed (ontology gap → stop).

    R7  No Hypothesis or CausalEdge may reference labels or relationship types
        outside the authoritative schema.

    R8  root_cause_final must be None when any blocking MissingEvidence exists.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import List, Optional

from causelink.ontology.models import CanonGraph
from causelink.ontology.schema import NODE_LABELS, RELATIONSHIP_TYPES
from causelink.state.investigation import (
    CausalEdge,
    CausalEdgeStatus,
    Hypothesis,
    HypothesisStatus,
    InvestigationState,
    RootCauseCandidate,
)

logger = logging.getLogger(__name__)


# ─── Result types ─────────────────────────────────────────────────────────────


@dataclass
class ValidationResult:
    """Result of a validation check — passed to audit trace."""

    passed: bool
    violations: List[str] = field(default_factory=list)
    warnings: List[str] = field(default_factory=list)

    def merge(self, other: "ValidationResult") -> "ValidationResult":
        return ValidationResult(
            passed=self.passed and other.passed,
            violations=self.violations + other.violations,
            warnings=self.warnings + other.warnings,
        )

    def __bool__(self) -> bool:
        return self.passed


# ─── ValidationGate ───────────────────────────────────────────────────────────


class ValidationGate:
    """
    Central validation authority for the CauseLink pipeline.

    All claim-acceptance decisions route through this class.
    Agents must not implement their own validation logic.
    """

    # ── Hypothesis validation ─────────────────────────────────────────────

    def validate_hypothesis(
        self, hypothesis: Hypothesis, state: InvestigationState
    ) -> ValidationResult:
        """
        Validate a Hypothesis against R1, R2, R3.

        Returns a failed ValidationResult (never raises) so callers can decide
        whether to reject or add to missing_evidence.
        """
        violations: List[str] = []
        warnings: List[str] = []

        # R3 — involved nodes must be in canon_graph
        if state.canon_graph is not None:
            for node_id in hypothesis.involved_node_ids:
                if not state.canon_graph.contains_node(node_id):
                    violations.append(
                        f"R3: involved_node_id '{node_id}' not found in CanonGraph "
                        f"(anchor={state.canon_graph.anchor_primary_value}). "
                        "Ontology gap — cannot fabricate node."
                    )
        else:
            violations.append(
                "R3: canon_graph is None — ontology context not loaded yet. "
                "OntologyContextAgent must run first."
            )

        # R1 — cited evidence must exist in state
        known_evidence_ids = {
            ev.evidence_id
            for ev in state.evidence_objects
            if hasattr(ev, "evidence_id")
        }
        for eid in hypothesis.evidence_object_ids:
            if eid not in known_evidence_ids:
                violations.append(
                    f"R1: evidence_object_id '{eid}' is not in "
                    "InvestigationState.evidence_objects. "
                    "Evidence must be collected before it can be cited."
                )

        # R2 — cited ontology paths must exist
        all_path_ids = {
            p.path_id for p in state.ontology_paths_used
        }
        if state.canon_graph is not None:
            all_path_ids |= {
                p.path_id for p in state.canon_graph.ontology_paths_used
            }
        for pid in hypothesis.ontology_path_ids:
            if pid not in all_path_ids:
                violations.append(
                    f"R2: ontology_path_id '{pid}' not found in investigation paths. "
                    "Structural validation must precede hypothesis submission."
                )

        # Warn if no ontology paths provided at all (allowed for PROPOSED only)
        if not hypothesis.ontology_path_ids and hypothesis.status != HypothesisStatus.PROPOSED:
            warnings.append(
                "R2-warn: Hypothesis has no ontology_path_ids but status is not PROPOSED. "
                "Structural validation is required for status ≥ SUPPORTED."
            )

        if violations:
            logger.warning(
                "Hypothesis %s failed validation: %s",
                hypothesis.hypothesis_id,
                violations,
            )

        return ValidationResult(
            passed=len(violations) == 0,
            violations=violations,
            warnings=warnings,
        )

    # ── Causal edge validation ────────────────────────────────────────────

    def validate_causal_edge(
        self, edge: CausalEdge, state: InvestigationState
    ) -> ValidationResult:
        """
        Validate a CausalEdge against R1, R3, R4.

        An edge with structural_path_validated=False is allowed as PENDING
        but must not become VALID until the flag is set.
        """
        violations: List[str] = []
        warnings: List[str] = []

        # R3 — nodes must exist in canon_graph
        if state.canon_graph is not None:
            for node_id in (edge.cause_node_id, edge.effect_node_id):
                if not state.canon_graph.contains_node(node_id):
                    violations.append(
                        f"R3: causal edge node '{node_id}' not in CanonGraph. "
                        "Cannot reference ontology nodes outside the scoped graph."
                    )
        else:
            violations.append("R3: canon_graph is None — cannot validate node IDs.")

        # R1 — cited evidence must exist
        known_ids = {
            ev.evidence_id
            for ev in state.evidence_objects
            if hasattr(ev, "evidence_id")
        }
        for eid in edge.evidence_object_ids:
            if eid not in known_ids:
                violations.append(
                    f"R1: CausalEdge cites unknown evidence_object_id '{eid}'."
                )

        # R4 — structural path required for VALID status
        if edge.status == CausalEdgeStatus.VALID and not edge.structural_path_validated:
            violations.append(
                "R4: CausalEdge is marked VALID but structural_path_validated=False. "
                "Call adapter.validate_shortest_path() before marking VALID."
            )

        if edge.status == CausalEdgeStatus.VALID and edge.ontology_path_id is None:
            violations.append(
                "R4: VALID CausalEdge must have an ontology_path_id. "
                "Set ontology_path_id to the OntologyPath.path_id returned by "
                "validate_shortest_path()."
            )

        return ValidationResult(
            passed=len(violations) == 0,
            violations=violations,
            warnings=warnings,
        )

    # ── Root cause candidate validation ──────────────────────────────────

    def validate_root_cause_candidate(
        self,
        candidate: RootCauseCandidate,
        state: InvestigationState,
        calling_agent: str,
        ranker_agent_type: str = "ranker",
    ) -> ValidationResult:
        """
        Validate a RootCauseCandidate before it may be set as root_cause_final.

        Enforces R5 (only RankerAgent may confirm) and R8 (no blocking items).
        """
        violations: List[str] = []

        # R5 — only ranker may set CONFIRMED
        if (
            candidate.status == HypothesisStatus.CONFIRMED
            and calling_agent != ranker_agent_type
        ):
            violations.append(
                f"R5: Root cause CONFIRMED may only be set by '{ranker_agent_type}', "
                f"not by '{calling_agent}'. "
                "Escalate to RankerAgent for final scoring."
            )

        # R8 — blocking missing evidence must be resolved
        blocking = [m for m in state.missing_evidence if m.blocking]
        if blocking and candidate.status == HypothesisStatus.CONFIRMED:
            violations.append(
                f"R8: {len(blocking)} blocking MissingEvidence item(s) remain. "
                "Root cause cannot be CONFIRMED until all blocking items are resolved. "
                "Set root_cause_final=None and status=INSUFFICIENT_EVIDENCE."
            )

        # Threshold check
        threshold = state.investigation_input.confidence_threshold
        if candidate.composite_score < threshold:
            violations.append(
                f"composite_score={candidate.composite_score:.3f} < "
                f"threshold={threshold:.3f}. "
                "Status must be PROBABLE or POSSIBLE, not CONFIRMED."
            )

        return ValidationResult(
            passed=len(violations) == 0, violations=violations
        )

    # ── CanonGraph validation ─────────────────────────────────────────────

    def validate_canon_graph(self, graph: CanonGraph) -> ValidationResult:
        """
        Validate a CanonGraph returned by the adapter (Rule R6 + schema drift check).
        """
        violations: List[str] = []
        warnings: List[str] = []

        # R6 — anchor must have been found
        if graph.anchor_neo4j_id == "NOT_FOUND":
            violations.append(
                f"R6: Anchor {graph.anchor_label}:{graph.anchor_primary_value} "
                "was not found in Neo4j. "
                "Ontology gap — add the anchor node before proceeding."
            )

        # Schema drift check on nodes
        for node in graph.nodes:
            unknown = [lbl for lbl in node.labels if lbl not in NODE_LABELS]
            if unknown:
                violations.append(
                    f"Schema drift: node {node.neo4j_id} has undeclared labels {unknown}."
                )

        # Schema drift check on edges
        for edge in graph.edges:
            if edge.type not in RELATIONSHIP_TYPES:
                violations.append(
                    f"Schema drift: edge {edge.neo4j_id} has undeclared type '{edge.type}'."
                )

        if graph.anchor_neo4j_id != "NOT_FOUND" and not graph.nodes:
            warnings.append(
                "CanonGraph has no nodes — neighborhood may be empty. "
                "Check max_hops or verify ontology population."
            )

        return ValidationResult(
            passed=len(violations) == 0,
            violations=violations,
            warnings=warnings,
        )

    # ── Investigation-level checks ────────────────────────────────────────

    def check_missing_citations(self, state: InvestigationState) -> List[str]:
        """
        Scan the full investigation state for uncited claims.

        Returns a list of violation strings (empty = no issues found).
        This is a non-blocking diagnostic used before finalising the report.
        """
        issues: List[str] = []
        known_evidence_ids = {
            ev.evidence_id
            for ev in state.evidence_objects
            if hasattr(ev, "evidence_id")
        }
        all_path_ids = {p.path_id for p in state.ontology_paths_used}
        if state.canon_graph:
            all_path_ids |= {p.path_id for p in state.canon_graph.ontology_paths_used}

        for h in state.hypotheses:
            if h.status not in (HypothesisStatus.PROPOSED,) and not h.evidence_object_ids:
                issues.append(
                    f"Hypothesis {h.hypothesis_id} (status={h.status}) "
                    "has no evidence citations."
                )
            for eid in h.evidence_object_ids:
                if eid not in known_evidence_ids:
                    issues.append(
                        f"Hypothesis {h.hypothesis_id} cites unknown evidence '{eid}'."
                    )

        for e in state.causal_graph_edges:
            if e.status == CausalEdgeStatus.VALID and not e.ontology_path_id:
                issues.append(
                    f"CausalEdge {e.edge_id} is VALID but has no ontology_path_id."
                )

        return issues

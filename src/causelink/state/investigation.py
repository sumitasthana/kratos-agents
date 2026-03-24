"""
causelink/state/investigation.py

InvestigationState — the single stateful object passed through all CauseLink agents.

This model functions as an append-only audit log + live reasoning context.
Agents receive the full InvestigationState and return partial updates only
(new evidence_objects, hypotheses, causal edges, etc.) — they never replace
the whole state.

Key design decisions:
  - root_cause_final is NULLABLE; it is set only when confidence >= threshold
    AND all evidence sufficiency checks pass.
  - Any hypothesis can be CONFIRMED only by the RankerAgent (Phase D constraint).
  - Every hypothesis and CausalEdge requires citations (evidence_object_ids +
    ontology_path_id) or is rejected by the ValidationGate.
  - Missing data is surfaced explicitly in missing_evidence, not silently ignored.
  - escalation=True when confidence < threshold AND blocking evidence is absent.
"""

from __future__ import annotations

import uuid
from datetime import datetime
from enum import Enum
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field, model_validator

from causelink.ontology.models import CanonGraph, OntologyPath
from causelink.ontology.schema import OntologySchemaSnapshot


# ─── Enums ────────────────────────────────────────────────────────────────────


class HypothesisStatus(str, Enum):
    PROPOSED  = "PROPOSED"   # initial — not yet assessed
    SUPPORTED = "SUPPORTED"  # has corroborating evidence, not yet confirmed
    REFUTED   = "REFUTED"    # contradicted by evidence
    # Evidence-weight tiers (set by RankerAgent only):
    POSSIBLE  = "POSSIBLE"   # composite_score < 0.50
    PROBABLE  = "PROBABLE"   # 0.50 ≤ composite_score < 0.80
    CONFIRMED = "CONFIRMED"  # composite_score ≥ 0.80 AND evidence sufficiency pass


class CausalEdgeStatus(str, Enum):
    PENDING                   = "PENDING"
    VALID                     = "VALID"
    REJECTED_NO_ONTOLOGY_PATH = "REJECTED_NO_ONTOLOGY_PATH"
    REJECTED_TEMPORAL         = "REJECTED_TEMPORAL"
    REJECTED_INSUFFICIENT_EVIDENCE = "REJECTED_INSUFFICIENT_EVIDENCE"


class InvestigationStatus(str, Enum):
    INITIALIZING          = "INITIALIZING"
    ONTOLOGY_LOADING      = "ONTOLOGY_LOADING"
    EVIDENCE_COLLECTION   = "EVIDENCE_COLLECTION"
    HYPOTHESIS_GENERATION = "HYPOTHESIS_GENERATION"
    CAUSAL_SCORING        = "CAUSAL_SCORING"
    COMPLETED             = "COMPLETED"
    INSUFFICIENT_EVIDENCE = "INSUFFICIENT_EVIDENCE"
    ESCALATED             = "ESCALATED"
    ERROR                 = "ERROR"


# ─── Sub-models ───────────────────────────────────────────────────────────────


class InvestigationAnchor(BaseModel):
    """The starting node for this investigation."""

    anchor_type: str = Field(
        ...,
        description=(
            "Ontology label of the anchor node. "
            "Must be one of: Incident, Violation, Job, Pipeline, System"
        ),
    )
    anchor_primary_key: str = Field(
        ..., description="Property name used to identify the anchor, e.g. 'incident_id'"
    )
    anchor_primary_value: str = Field(
        ..., description="Value of the anchor primary key, e.g. 'INC-2026-001'"
    )


class InvestigationInput(BaseModel):
    """Incoming request payload — immutable after creation."""

    investigation_id: str = Field(
        default_factory=lambda: str(uuid.uuid4()),
        description="Unique identifier for this investigation run",
    )
    idempotency_key: Optional[str] = Field(
        None,
        description=(
            "Caller-supplied idempotency key. "
            "Duplicate submissions with the same key return the existing investigation."
        ),
    )
    anchor: InvestigationAnchor
    max_hops: int = Field(
        default=3,
        ge=1,
        le=6,
        description="Max traversal depth for ontology neighborhood retrieval",
    )
    confidence_threshold: float = Field(
        default=0.80,
        ge=0.0,
        le=1.0,
        description="Minimum composite score required to mark root_cause_final CONFIRMED",
    )
    context: Dict[str, Any] = Field(
        default_factory=dict,
        description="Optional caller-provided context (time windows, environment, etc.)",
    )
    requested_by: Optional[str] = Field(
        None,
        description="Requesting principal — masked in all outputs (stored hashed if present)",
    )
    submitted_at: datetime = Field(default_factory=datetime.utcnow)


class Hypothesis(BaseModel):
    """
    A proposed causal explanation produced by HypothesisGenerator.

    Every field below is mandatory before a hypothesis may be assessed:
      - involved_node_ids    → must reference CanonGraph nodes
      - evidence_object_ids  → must reference InvestigationState.evidence_objects
      - ontology_path_ids    → must reference OntologyPath.path_id values

    A hypothesis may only be marked CONFIRMED by the RankerAgent (Phase D).
    """

    hypothesis_id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    description: str = Field(
        ..., description="Clear, falsifiable statement of the proposed cause"
    )
    involved_node_ids: List[str] = Field(
        ...,
        min_length=1,
        description=(
            "neo4j_ids of CanonGraph nodes involved in this hypothesis. "
            "Must all exist in InvestigationState.canon_graph."
        ),
    )
    evidence_object_ids: List[str] = Field(
        default_factory=list,
        description=(
            "IDs of EvidenceObjects supporting this hypothesis. "
            "Must all exist in InvestigationState.evidence_objects."
        ),
    )
    ontology_path_ids: List[str] = Field(
        default_factory=list,
        description=(
            "path_ids of OntologyPaths validating the structural link. "
            "At least one required for status ≥ SUPPORTED."
        ),
    )
    status: HypothesisStatus = Field(default=HypothesisStatus.PROPOSED)
    confidence: float = Field(
        default=0.0,
        ge=0.0,
        le=1.0,
        description="0–1 confidence assigned by RankerAgent",
    )
    generated_by: str = Field(
        ..., description="AgentType string that generated this hypothesis"
    )
    pattern_id: Optional[str] = Field(
        None,
        description="Pattern library entry used to generate this hypothesis (Phase E)",
    )
    generated_at: datetime = Field(default_factory=datetime.utcnow)
    notes: Optional[str] = None


class CausalEdge(BaseModel):
    """
    A directed causal link in the investigation DAG.

    structural_path_validated MUST be True (set by OntologyContextAgent after
    calling validate_shortest_path) before this edge can contribute to a
    CONFIRMED root cause.
    """

    edge_id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    cause_node_id: str = Field(
        ..., description="neo4j_id of the cause node (CanonNode)"
    )
    effect_node_id: str = Field(
        ..., description="neo4j_id of the effect node (CanonNode)"
    )
    mechanism: str = Field(
        ..., description="Human-readable description of the causal mechanism"
    )
    evidence_object_ids: List[str] = Field(
        default_factory=list,
        description="EvidenceObject IDs supporting this causal link",
    )
    ontology_path_id: Optional[str] = Field(
        None,
        description=(
            "path_id of the OntologyPath validating this link. "
            "Required before status can be VALID."
        ),
    )
    temporal_order_validated: bool = Field(
        default=False,
        description="True when cause timestamp precedes effect timestamp in evidence",
    )
    structural_path_validated: bool = Field(
        default=False,
        description="True when validate_shortest_path returned a non-null OntologyPath",
    )
    confidence: float = Field(default=0.0, ge=0.0, le=1.0)
    status: CausalEdgeStatus = Field(default=CausalEdgeStatus.PENDING)
    created_at: datetime = Field(default_factory=datetime.utcnow)


class RootCauseCandidate(BaseModel):
    """
    A ranked root cause candidate — produced by the RankerAgent only (Phase D).

    composite_score = weighted combination of:
      E (evidence_score)   × 0.40
      T (temporal_score)   × 0.25
      D (structural_depth_score) × 0.20
      H (hypothesis_alignment_score) × 0.15
    """

    candidate_id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    node_id: str = Field(
        ...,
        description="neo4j_id of the CanonNode identified as the root cause",
    )
    description: str
    hypothesis_ids: List[str] = Field(
        default_factory=list,
        description="Hypotheses that support this candidate",
    )
    causal_edge_ids: List[str] = Field(
        default_factory=list,
        description="CausalEdge IDs in the path leading to this candidate",
    )
    evidence_score: float = Field(default=0.0, ge=0.0, le=1.0)
    temporal_score: float = Field(default=0.0, ge=0.0, le=1.0)
    structural_depth_score: float = Field(default=0.0, ge=0.0, le=1.0)
    hypothesis_alignment_score: float = Field(default=0.0, ge=0.0, le=1.0)
    composite_score: float = Field(default=0.0, ge=0.0, le=1.0)
    status: HypothesisStatus = Field(default=HypothesisStatus.POSSIBLE)
    missing_evidence_ids: List[str] = Field(
        default_factory=list,
        description="MissingEvidence IDs that would increase confidence",
    )
    ranked_at: datetime = Field(default_factory=datetime.utcnow)

    @model_validator(mode="after")
    def _status_from_score(self) -> "RootCauseCandidate":
        """
        Enforce the three-tier confidence rule.
        Status is derived from composite_score; callers must not override this.
        CONFIRMED requires ≥0.80 AND is only set by RankerAgent (enforced in ValidationGate).
        """
        s = self.composite_score
        if s >= 0.80:
            object.__setattr__(self, "status", HypothesisStatus.CONFIRMED)
        elif s >= 0.50:
            object.__setattr__(self, "status", HypothesisStatus.PROBABLE)
        else:
            object.__setattr__(self, "status", HypothesisStatus.POSSIBLE)
        return self


class MissingEvidence(BaseModel):
    """
    Describes evidence required to confirm or refute a hypothesis.

    When blocking=True, the investigation CANNOT mark root_cause_final CONFIRMED
    until this evidence is provided.  The investigation transitions to
    INSUFFICIENT_EVIDENCE status.
    """

    missing_id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    evidence_type: str = Field(
        ...,
        description="Type of missing evidence: log|metric|change_event|audit_event|lineage_trace",
    )
    description: str = Field(
        ..., description="Clear description of what is needed and why"
    )
    query_template: Optional[str] = Field(
        None,
        description=(
            "Template query or search pattern that would retrieve this evidence. "
            "MUST be a template with placeholders, not a query with actual values."
        ),
    )
    required_for_hypothesis_ids: List[str] = Field(
        default_factory=list,
        description="Hypothesis IDs that this evidence would confirm or refute",
    )
    blocking: bool = Field(
        default=False,
        description=(
            "True when absence of this evidence prevents root cause confirmation. "
            "Set escalation=True in InvestigationState when any blocking item exists."
        ),
    )


class AuditTraceEntry(BaseModel):
    """
    A single step in the investigation audit trail.

    Every agent action, tool call, decision, and validation result must produce
    an AuditTraceEntry.  This makes investigations fully replayable.
    """

    step_id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    timestamp: datetime = Field(default_factory=datetime.utcnow)
    agent_type: str = Field(
        ..., description="AgentType string of the agent that performed this step"
    )
    action: str = Field(
        ..., description="Action category, e.g. 'ontology_load', 'evidence_fetch', 'hypothesis_propose'"
    )
    inputs_summary: Dict[str, Any] = Field(
        default_factory=dict,
        description="Non-sensitive summary of inputs (no raw content or credentials)",
    )
    outputs_summary: Dict[str, Any] = Field(
        default_factory=dict,
        description="Non-sensitive summary of outputs",
    )
    ontology_paths_accessed: List[str] = Field(
        default_factory=list,
        description="path_ids of OntologyPaths used in this step",
    )
    evidence_ids_accessed: List[str] = Field(
        default_factory=list,
        description="evidence_ids of EvidenceObjects read/written in this step",
    )
    decision: Optional[str] = Field(
        None, description="Key decision made, if any"
    )
    notes: Optional[str] = None


# ─── InvestigationState ───────────────────────────────────────────────────────


class InvestigationState(BaseModel):
    """
    The single stateful object passed through all CauseLink agents.

    Lifecycle:
        1. Created by OrchestratorAgent with investigation_input populated.
        2. OntologyContextAgent populates canon_graph + ontology_schema_snapshot.
        3. EvidenceCollectorAgent appends to evidence_objects.
        4. HypothesisGeneratorAgent appends to hypotheses.
        5. CausalEngineAgent builds causal_graph_edges.
        6. RankerAgent populates root_cause_candidates, sets root_cause_final.

    Constraints:
        - Agents append to lists; they never replace or truncate existing entries.
        - root_cause_final is set by RankerAgent only.
        - When root_cause_final is None, missing_evidence must be non-empty.
        - escalation is set to True automatically when any blocking MissingEvidence exists.
    """

    model_config = {"arbitrary_types_allowed": True}

    # ── Incoming payload ─────────────────────────────────────────────────────
    investigation_input: InvestigationInput
    status: InvestigationStatus = Field(default=InvestigationStatus.INITIALIZING)

    # ── Phase A: Ontology ────────────────────────────────────────────────────
    canon_graph: Optional[CanonGraph] = Field(
        None,
        description=(
            "Populated by OntologyContextAgent. "
            "Non-null before any other agent may proceed."
        ),
    )
    ontology_schema_snapshot: Optional[OntologySchemaSnapshot] = Field(
        None,
        description="Schema version active when this investigation was created",
    )
    ontology_paths_used: List[OntologyPath] = Field(
        default_factory=list,
        description="All OntologyPaths retrieved or validated during this investigation",
    )

    # ── Phase C: Evidence ────────────────────────────────────────────────────
    # EvidenceObject type is imported at runtime to avoid circular imports.
    # Stored as List[Dict] until Phase C module is loaded; typed properly below.
    evidence_objects: List[Any] = Field(
        default_factory=list,
        description="Immutable EvidenceObjects collected during investigation",
    )

    # ── Phase E: Hypotheses ──────────────────────────────────────────────────
    hypotheses: List[Hypothesis] = Field(default_factory=list)

    # ── Phase F: Causal Graph ────────────────────────────────────────────────
    causal_graph_node_ids: List[str] = Field(
        default_factory=list,
        description=(
            "Subset of CanonNode.neo4j_ids involved in the causal DAG. "
            "Must all exist in canon_graph."
        ),
    )
    causal_graph_edges: List[CausalEdge] = Field(default_factory=list)

    # ── Phase F: Root Cause ──────────────────────────────────────────────────
    root_cause_candidates: List[RootCauseCandidate] = Field(default_factory=list)
    root_cause_final: Optional[RootCauseCandidate] = Field(
        None,
        description=(
            "Set only when composite_score ≥ confidence_threshold "
            "AND no blocking MissingEvidence items remain. "
            "None → INSUFFICIENT_EVIDENCE; escalation must be set True."
        ),
    )

    # ── Missing evidence ─────────────────────────────────────────────────────
    missing_evidence: List[MissingEvidence] = Field(default_factory=list)
    recommended_actions: List[str] = Field(default_factory=list)

    # ── Audit trail ──────────────────────────────────────────────────────────
    audit_trace: List[AuditTraceEntry] = Field(default_factory=list)

    # ── Escalation ───────────────────────────────────────────────────────────
    escalation: bool = Field(
        default=False,
        description="True when root cause cannot be confirmed without additional evidence",
    )
    escalation_reason: Optional[str] = None

    # ── Timestamps ───────────────────────────────────────────────────────────
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)

    # ── Mutation helpers (agents call these, not direct list.append) ──────────

    def append_audit(self, entry: AuditTraceEntry) -> None:
        """Append an audit trace entry and update the timestamp."""
        self.audit_trace.append(entry)
        self.updated_at = datetime.utcnow()

    def add_ontology_path(self, path: OntologyPath) -> None:
        self.ontology_paths_used.append(path)
        self.updated_at = datetime.utcnow()

    def add_hypothesis(self, hypothesis: Hypothesis) -> None:
        """
        Add a hypothesis after basic citation checks.

        Raises ValueError if any involved_node_id is absent from canon_graph.
        Full citation validation is performed by ValidationGate.
        """
        if self.canon_graph is not None:
            missing_nodes = [
                nid
                for nid in hypothesis.involved_node_ids
                if not self.canon_graph.contains_node(nid)
            ]
            if missing_nodes:
                raise ValueError(
                    f"Hypothesis {hypothesis.hypothesis_id} references node IDs "
                    f"{missing_nodes} that are not in the CanonGraph. "
                    "Only nodes retrieved from Neo4j may be used."
                )
        self.hypotheses.append(hypothesis)
        self.updated_at = datetime.utcnow()

    def add_causal_edge(self, edge: CausalEdge) -> None:
        self.causal_graph_edges.append(edge)
        for node_id in (edge.cause_node_id, edge.effect_node_id):
            if node_id not in self.causal_graph_node_ids:
                self.causal_graph_node_ids.append(node_id)
        self.updated_at = datetime.utcnow()

    def add_missing_evidence(self, item: MissingEvidence) -> None:
        self.missing_evidence.append(item)
        if item.blocking and not self.escalation:
            self.escalation = True
            self.escalation_reason = (
                f"Blocking evidence missing: {item.description}"
            )
        self.updated_at = datetime.utcnow()

    def set_root_cause_final(
        self, candidate: RootCauseCandidate, ranker_agent_type: str
    ) -> None:
        """
        Assign the final root cause.

        Only callable by the RankerAgent.  Enforces the threshold rule:
        if composite_score < confidence_threshold, raises ValueError and
        the investigation must transition to INSUFFICIENT_EVIDENCE.
        """
        threshold = self.investigation_input.confidence_threshold
        if candidate.composite_score < threshold:
            raise ValueError(
                f"Cannot mark root cause CONFIRMED: composite_score="
                f"{candidate.composite_score:.3f} < threshold={threshold:.3f}. "
                "Set status=INSUFFICIENT_EVIDENCE and populate missing_evidence."
            )
        blocking = [m for m in self.missing_evidence if m.blocking]
        if blocking:
            raise ValueError(
                f"Cannot confirm root cause: {len(blocking)} blocking evidence "
                "item(s) remain. Resolve before confirming."
            )
        self.root_cause_final = candidate
        self.status = InvestigationStatus.COMPLETED
        self.updated_at = datetime.utcnow()

    def transition_to_insufficient(self, reason: str) -> None:
        """Mark the investigation as unable to confirm a root cause."""
        self.status = InvestigationStatus.INSUFFICIENT_EVIDENCE
        self.root_cause_final = None
        self.escalation = True
        self.escalation_reason = reason
        self.updated_at = datetime.utcnow()

    def insufficient_evidence_report(self) -> Dict[str, Any]:
        """
        Return the standard 'Insufficient evidence' output block.

        Called when root_cause_final is None after the causal engine has run.
        """
        return {
            "status": "Insufficient evidence",
            "investigation_id": self.investigation_input.investigation_id,
            "anchor": {
                "type": self.investigation_input.anchor.anchor_type,
                "key": self.investigation_input.anchor.anchor_primary_key,
                "value": self.investigation_input.anchor.anchor_primary_value,
            },
            "missing_evidence": [
                {
                    "missing_id": m.missing_id,
                    "evidence_type": m.evidence_type,
                    "description": m.description,
                    "blocking": m.blocking,
                    "query_template": m.query_template,
                    "required_for_hypothesis_ids": m.required_for_hypothesis_ids,
                }
                for m in self.missing_evidence
            ],
            "hypotheses_proposed": len(self.hypotheses),
            "hypotheses_confirmed": sum(
                1 for h in self.hypotheses if h.status == HypothesisStatus.CONFIRMED
            ),
            "escalation": self.escalation,
            "escalation_reason": self.escalation_reason,
        }

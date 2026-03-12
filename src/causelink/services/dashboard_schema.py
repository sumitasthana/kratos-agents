"""
causelink/services/dashboard_schema.py

UI-ready output models for the Kratos RCA dashboard.

These models are produced by OntologyBacktrackingService and consumed directly
by the dashboard API endpoint and front-end callers. All field names are
deterministic, typed, and serialisation-safe.

No emojis, no placeholder data, no hallucinated fields.
"""

from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field


# ─── Enums ────────────────────────────────────────────────────────────────────


class NodeStatus(str, Enum):
    """Status assigned to a node after evidence-based evaluation."""

    HEALTHY = "HEALTHY"
    DEGRADED = "DEGRADED"
    FAILED = "FAILED"
    UNKNOWN = "UNKNOWN"
    NOT_EVALUATED_DUE_TO_EARLY_STOP = "NOT_EVALUATED_DUE_TO_EARLY_STOP"


class StopReason(str, Enum):
    """Reason the backtracking traversal stopped."""

    FIRST_CONFIRMED_FAILURE = "FIRST_CONFIRMED_FAILURE"
    INSUFFICIENT_EVIDENCE = "INSUFFICIENT_EVIDENCE"
    ONTOLOGY_GAP = "ONTOLOGY_GAP"
    MAX_HOPS_REACHED = "MAX_HOPS_REACHED"
    EXPLORATORY_CONTINUE = "EXPLORATORY_CONTINUE"


class TraversalMode(str, Enum):
    """
    Backtracking traversal mode.

    NORMAL stops at the first confirmed failed node.
    EXPLORATORY continues beyond the first failure to map the full impact graph.
    """

    NORMAL = "normal"
    EXPLORATORY = "exploratory"


# ─── Node Evaluation Result ───────────────────────────────────────────────────


class NodeEvaluationResult(BaseModel):
    """
    The evaluation result for a single node visited during backtracking traversal.

    A node may be marked FAILED only when ALL of the following hold:
      - structural_path_exists is True (path from anchor verified in CanonGraph)
      - len(evidence_ids) > 0  (at least one evidence object supports this evaluation)
      - confidence meets the evidence sufficiency threshold (>= 0.50)

    If evidence is partial or below threshold, status is DEGRADED or UNKNOWN, never FAILED.
    """

    node_id: str = Field(..., description="neo4j_id of the evaluated CanonNode")
    node_label: str = Field(
        ..., description="Primary ontology label of the node, e.g. 'Job'"
    )
    node_name: str = Field(
        ...,
        description=(
            "Display name derived from the node's primary_value property. "
            "Falls back to node_id when primary_value is absent."
        ),
    )
    status: NodeStatus = Field(..., description="Evaluation outcome after evidence check")
    failure_reason: Optional[str] = Field(
        None,
        description=(
            "Human-readable explanation of why the node is FAILED or DEGRADED. "
            "None when status is HEALTHY, UNKNOWN, or NOT_EVALUATED_DUE_TO_EARLY_STOP."
        ),
    )
    evidence_ids: List[str] = Field(
        default_factory=list,
        description=(
            "IDs of EvidenceObjects that contributed to this node's status. "
            "Empty when status is UNKNOWN or NOT_EVALUATED_DUE_TO_EARLY_STOP."
        ),
    )
    ontology_path: str = Field(
        ...,
        description=(
            "Human-readable structural path from the anchor to this node, "
            "e.g. 'Incident-[TRIGGERS]->Job-[EXECUTES]->Pipeline'."
        ),
    )
    confidence: float = Field(
        default=0.0,
        ge=0.0,
        le=1.0,
        description="Confidence in the evaluated status (0.0 = no evidence, 1.0 = full confirmation)",
    )
    control_ids: List[str] = Field(
        default_factory=list,
        description=(
            "IDs of ControlObjective or Rule ontology nodes enforced at or by this node. "
            "Populated only for compliance chain nodes."
        ),
    )
    findings: List[str] = Field(
        default_factory=list,
        description=(
            "Ordered list of human-readable findings specific to this node. "
            "Each finding must reference evidence_ids or ontology_path."
        ),
    )
    order_index: int = Field(
        default=0,
        description="Zero-based position of this node in the deterministic traversal sequence.",
    )
    evaluated_at: datetime = Field(default_factory=datetime.utcnow)


# ─── Lineage Walk Node ────────────────────────────────────────────────────────


class LineageWalkNode(BaseModel):
    """
    A single step in the UI lineage walk visualisation.

    The visual pattern is: A -> B -> C -> D (left to right).
    Status drives the front-end colour code for each card.

    When was_evaluated=False, the node was skipped because an earlier node
    triggered an early stop; the UI should render it as downstream-not-evaluated.
    """

    node_id: str = Field(..., description="neo4j_id of the CanonNode")
    display_name: str = Field(..., description="Human-readable name shown on the card")
    label: str = Field(
        ..., description="Ontology label used as the subtitle type indicator"
    )
    status: NodeStatus = Field(
        ..., description="Evaluation status used by the UI for colour coding"
    )
    subtitle: str = Field(
        ..., description="Secondary line beneath display_name, e.g. 'Pipeline / PIPE-001'"
    )
    order_index: int = Field(
        ..., description="Zero-based left-to-right ordering position in the walk"
    )
    ontology_path_fragment: str = Field(
        ...,
        description=(
            "Relationship type label leading TO this node from the previous step, "
            "e.g. 'EXECUTES' or 'RUNS_JOB'. Empty string for the first node."
        ),
    )
    was_evaluated: bool = Field(
        default=True,
        description=(
            "True when the node was evaluated; False when skipped due to early stop. "
            "The UI renders skipped nodes differently from evaluated nodes."
        ),
    )


# ─── Agent Analysis Chain Entry ───────────────────────────────────────────────


class AgentAnalysisChainEntry(BaseModel):
    """
    One agent's contribution rendered in the Agent Analysis Chain sidebar panel.

    Maps to the right-hand panel in the Kratos RCA dashboard.
    """

    agent_name: str = Field(
        ..., description="Human-readable agent name, e.g. 'Ontology Context Agent'"
    )
    status: str = Field(
        ..., description="Agent run outcome: 'completed', 'skipped', 'error'"
    )
    health: str = Field(
        ...,
        description=(
            "Health assessment emitted by this agent, e.g. 'HEALTHY', 'DEGRADED', 'FAILED'"
        ),
    )
    problem_type: str = Field(
        ...,
        description=(
            "Problem classification from this agent, e.g. 'compliance_gap', "
            "'execution_failure', 'lineage'"
        ),
    )
    control: Optional[str] = Field(
        None,
        description=(
            "Control objective or rule ID triggered by this agent's findings. "
            "None when the agent is not a compliance agent."
        ),
    )
    key_finding: str = Field(
        ...,
        description="The single most important finding from this agent.",
    )
    duration_ms: int = Field(
        default=0,
        description="Approximate wall-clock duration of this agent step in milliseconds.",
    )


# ─── Backtracking Result (internal) ──────────────────────────────────────────


class BacktrackingResult(BaseModel):
    """
    Internal result type returned by OntologyBacktrackingService.

    Transformed into RcaDashboardSummary for API/UI consumption.
    """

    traversal_sequence: List[NodeEvaluationResult] = Field(
        default_factory=list,
        description=(
            "Nodes evaluated in deterministic order. Includes all evaluated nodes "
            "plus any marked NOT_EVALUATED_DUE_TO_EARLY_STOP."
        ),
    )
    failure_node: Optional[NodeEvaluationResult] = Field(
        None,
        description=(
            "First confirmed FAILED node in the traversal. "
            "None when no failure was found or evidence is insufficient."
        ),
    )
    stop_reason: StopReason = Field(
        ..., description="Why the traversal stopped"
    )
    traversal_mode: TraversalMode = Field(
        ..., description="Mode used for this traversal run"
    )
    lineage_walk: List[LineageWalkNode] = Field(
        default_factory=list,
        description="Ordered lineage walk nodes for dashboard visualisation.",
    )
    anchor_type: str = Field(..., description="Anchor node label")
    anchor_id: str = Field(..., description="Anchor primary key value")
    chains_evaluated: List[str] = Field(
        default_factory=list,
        description="Chain types evaluated during traversal: compliance, lineage, etc.",
    )
    total_nodes_in_graph: int = Field(
        default=0,
        description="Total nodes in the CanonGraph at traversal time.",
    )


# ─── RCA Dashboard Summary (public, UI-ready) ─────────────────────────────────


class RcaDashboardSummary(BaseModel):
    """
    Dashboard-ready RCA summary for a completed investigation.

    All fields are typed, deterministic, and UI-friendly. This model should
    be returned directly from the dashboard API endpoint.

    No emojis, no placeholder values, no markdown formatting in string fields.
    """

    investigation_id: str = Field(
        ..., description="UUID of the investigation this summary belongs to"
    )
    scenario_name: str = Field(
        ...,
        description=(
            "Human-readable scenario name for the dashboard card title, "
            "e.g. 'Incident INC-2026-001 RCA'."
        ),
    )
    anchor_type: str = Field(
        ...,
        description="Anchor node label: Incident, Violation, Job, Pipeline, or System",
    )
    anchor_id: str = Field(
        ..., description="Anchor primary key value, e.g. 'INC-2026-001'"
    )
    health_score: float = Field(
        default=0.0,
        ge=0.0,
        le=100.0,
        description=(
            "0-100 health score derived from traversal results. "
            "100 = fully healthy, 0 = fully failed."
        ),
    )
    health_status: str = Field(
        ...,
        description="Derived health status label: HEALTHY, DEGRADED, FAILED, or UNKNOWN",
    )
    problem_type: str = Field(
        ...,
        description=(
            "Problem classification based on failure node label and chain type. "
            "Examples: 'compliance_gap', 'execution_failure', 'lineage', 'general'."
        ),
    )
    control_triggered: Optional[str] = Field(
        None,
        description=(
            "Control objective or rule ID that was triggered, if the failure "
            "was detected in the compliance chain. None for operational failures."
        ),
    )
    lineage_failure_node: Optional[str] = Field(
        None,
        description=(
            "Display name of the failure node if it was found in the lineage chain. "
            "None when the failure is not lineage-related."
        ),
    )
    confidence: float = Field(
        default=0.0,
        ge=0.0,
        le=1.0,
        description="Overall confidence in the RCA conclusion (0.0-1.0).",
    )
    lineage_walk: List[LineageWalkNode] = Field(
        default_factory=list,
        description=(
            "Ordered left-to-right sequence of nodes for the lineage walk visualisation. "
            "Includes evaluated nodes and any early-stopped downstream nodes."
        ),
    )
    failed_node: Optional[str] = Field(
        None,
        description="neo4j_id of the first confirmed FAILED node, or None.",
    )
    failed_node_status: Optional[NodeStatus] = Field(
        None,
        description="Status value of the failed node.",
    )
    failure_reason: Optional[str] = Field(
        None,
        description=(
            "Human-readable failure reason from the failed node evaluation. "
            "None when no failure node was found."
        ),
    )
    findings: List[str] = Field(
        default_factory=list,
        description=(
            "Consolidated, ordered findings across all evaluated nodes. "
            "Each entry should be a self-contained, actionable statement."
        ),
    )
    agent_analysis_chain: List[AgentAnalysisChainEntry] = Field(
        default_factory=list,
        description="Agent chain entries for the right-hand sidebar panel.",
    )
    evidence_objects: List[str] = Field(
        default_factory=list,
        description="IDs of EvidenceObjects referenced in this RCA summary.",
    )
    ontology_paths_used: List[str] = Field(
        default_factory=list,
        description="path_ids of OntologyPaths that validated structural claims.",
    )
    audit_trace: List[str] = Field(
        default_factory=list,
        description=(
            "Human-readable one-line audit summary per traversal step. "
            "Suitable for display in a collapsible detail panel."
        ),
    )
    stop_reason: Optional[StopReason] = Field(
        None,
        description="Why the backtracking traversal stopped.",
    )
    traversal_mode: TraversalMode = Field(
        default=TraversalMode.NORMAL,
        description="Traversal mode used: 'normal' or 'exploratory'.",
    )
    generated_at: datetime = Field(
        default_factory=datetime.utcnow,
        description="UTC timestamp when this summary was generated.",
    )
    session_id: Optional[str] = Field(
        default=None,
        description="RCA workspace session ID that produced this summary.",
    )
    dashboard_url: str = Field(
        default="",
        description="Frontend hash route for this job's dashboard, e.g. '#jobs/JOB-123/dashboard'.",
    )
    incident_card_data: Optional[Dict[str, Any]] = Field(
        default=None,
        description="Serialised IncidentCard dict for the chat panel incident card section.",
    )

    def to_dict(self) -> Dict[str, Any]:
        """Return a JSON-serialisable dict for API responses."""
        return self.model_dump(mode="json")

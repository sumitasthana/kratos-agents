"""
core/models.py
Shared Pydantic v2 data models for the Kratos multi-agent RCA platform.

All agents, tools, and connectors share these types to ensure a uniform
evidence trail from log ingestion through to recommendations.

Regulatory traceability targets:
  - 12 CFR Part 330 (deposit insurance)
  - 12 CFR Part 370 (recordkeeping for timely deposit insurance determinations)
"""
from __future__ import annotations

import uuid
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Dict, List, Optional, Protocol, runtime_checkable

from pydantic import BaseModel, Field


# ============================================================================
# PRIORITY / SEVERITY SCALE
# ============================================================================

class Priority(str, Enum):
    """Unified priority scale used by EvidenceObject and Recommendation."""
    P1 = "P1"   # Critical — must be fixed immediately; pipeline is broken
    P2 = "P2"   # High     — fix in current sprint; data quality risk
    P3 = "P3"   # Medium   — schedule for next sprint; compliance gap
    P4 = "P4"   # Low      — technical debt / informational


# ============================================================================
# LOG SOURCE
# ============================================================================

class LogSource(str, Enum):
    """Origin system for a LogChunk."""
    SPARK   = "spark"
    AIRFLOW = "airflow"
    SYSTEM  = "system"


# ============================================================================
# LLM CLIENT PROTOCOL
# ============================================================================

@runtime_checkable
class LLMClient(Protocol):
    """
    Structural protocol satisfied by LangChain chat models (ChatOpenAI,
    ChatAnthropic, etc.) and any async-capable LLM wrapper.

    Any object that implements ainvoke() satisfies this protocol — no
    inheritance required (structural subtyping / duck typing).
    """

    async def ainvoke(self, messages: List[Any]) -> Any:  # noqa: D102
        ...


# ============================================================================
# CORE EVIDENCE AND CONTEXT MODELS
# ============================================================================

class EvidenceObject(BaseModel):
    """
    A single piece of RCA evidence produced by a Kratos tool.

    Cites a specific defect (defect_id) and optionally a regulation section
    (e.g. "12 CFR Part 370 §2(c)") for FDIC compliance traceability.
    Every piece of evidence flows from a named tool so the full audit chain
    is preserved: incident → tool → evidence → recommendation.
    """

    id:             str      = Field(
        default_factory=lambda: str(uuid.uuid4()),
        description="Unique evidence identifier (UUID)",
    )
    source_tool:    str      = Field(..., description="Name of the tool that produced this evidence")
    timestamp:      datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc),
        description="UTC timestamp when evidence was generated",
    )
    severity:       Priority = Field(..., description="P1 (critical) through P4 (informational)")
    description:    str      = Field(..., description="Human-readable description of the finding")
    defect_id:      Optional[str] = Field(
        None,
        description="Structured defect identifier, e.g. DEF-042",
    )
    regulation_ref: Optional[str] = Field(
        None,
        description="Regulation reference, e.g. '12 CFR Part 370 §2(c)'",
    )
    raw_payload:    Dict[str, Any] = Field(
        default_factory=dict,
        description="Full raw data from the tool that backs this evidence",
    )


class IncidentContext(BaseModel):
    """
    Shared context object passed through the entire RCA pipeline.

    Contains everything an agent or tool needs to understand what
    incident is being investigated and what the pipeline has found so far.
    Fingerprints, log paths, and other per-stage artifacts travel in
    the ``metadata`` dict so the schema stays stable.
    """

    incident_id:       str            = Field(..., description="Unique incident identifier")
    run_id:            str            = Field(..., description="Unique pipeline run identifier")
    pipeline_stage:    str            = Field(..., description="Current pipeline stage name")
    failed_controls:   List[str]      = Field(
        default_factory=list,
        description="Control IDs that are failing, e.g. ['CTRL-330-A', 'CTRL-370-B']",
    )
    ontology_snapshot: Dict[str, Any] = Field(
        default_factory=dict,
        description="Current Neo4j ontology snapshot (serialised subgraph)",
    )
    metadata:          Dict[str, Any] = Field(
        default_factory=dict,
        description="Arbitrary stage metadata, fingerprints, and analysis artefacts",
    )


# ============================================================================
# LOG STREAMING MODEL
# ============================================================================

class LogChunk(BaseModel):
    """A single log record yielded by a streaming connector."""

    source:    LogSource      = Field(..., description="Log origin system")
    timestamp: datetime       = Field(..., description="Log record timestamp (UTC)")
    level:     str            = Field(..., description="Log level: DEBUG / INFO / WARN / ERROR / FATAL")
    message:   str            = Field(..., description="Raw log message text")
    metadata:  Dict[str, Any] = Field(
        default_factory=dict,
        description="Structured fields extracted from the log line (task_id, stage_id, etc.)",
    )


# ============================================================================
# LINEAGE GRAPH MODELS
# ============================================================================

class LineageNode(BaseModel):
    """A single node in the data-lineage graph."""

    id:   str = Field(..., description="Unique node identifier within the graph")
    type: str = Field(..., description="Node type: 'table', 'job', 'column', 'dataset', 'api'")
    name: str = Field(..., description="Human-readable node name")


class LineageEdge(BaseModel):
    """A directed edge in the data-lineage graph."""

    source:   str = Field(..., description="Source LineageNode.id")
    target:   str = Field(..., description="Target LineageNode.id")
    relation: str = Field(..., description="Relationship type: 'READS', 'WRITES', 'TRANSFORMS', 'JOINS'")


class LineageGraph(BaseModel):
    """Complete data-lineage graph for a pipeline job."""

    job_id: str               = Field(..., description="Pipeline job identifier")
    nodes:  List[LineageNode] = Field(default_factory=list)
    edges:  List[LineageEdge] = Field(default_factory=list)


# ============================================================================
# ISSUE PROFILE  (triangulated root-cause hypothesis)
# ============================================================================

class IssueProfile(BaseModel):
    """
    Triangulated root-cause hypothesis produced by TriangulationAgent.

    Aggregates evidence from multiple analyzers into a single coherent
    root-cause explanation with a supporting evidence chain and an
    optional regulatory reference for FDIC compliance reporting.
    """

    id:                    str                  = Field(
        default_factory=lambda: str(uuid.uuid4()),
        description="Unique IssueProfile identifier",
    )
    root_cause_hypothesis: str                  = Field(..., description="Concise root-cause statement")
    supporting_evidence:   List[EvidenceObject] = Field(default_factory=list)
    confidence:            float                = Field(
        ..., ge=0.0, le=1.0,
        description="Confidence score in the hypothesis (0.0 = uncertain, 1.0 = certain)",
    )
    affected_regulation:   Optional[str]        = Field(
        None,
        description="Primary regulation implicated, e.g. '12 CFR Part 330'",
    )


# ============================================================================
# RECOMMENDATION
# ============================================================================

class Recommendation(BaseModel):
    """
    A prioritised, regulation-traceable fix produced by RecommendationAgent.

    Each recommendation is tied to a specific IssueProfile, a defect
    reference (defect_id), and a regulation section (regulation_ref) so
    the full audit chain — from raw log through to remediation — is intact.
    """

    id:               str      = Field(
        default_factory=lambda: str(uuid.uuid4()),
        description="Unique Recommendation identifier",
    )
    issue_profile_id: str      = Field(..., description="IssueProfile.id this recommendation addresses")
    action:           str      = Field(..., description="Specific action to take")
    priority:         Priority = Field(..., description="Implementation priority P1–P4")
    effort_estimate:  str      = Field(..., description="Effort estimate, e.g. '2h', '1 sprint', '1 day'")
    defect_id:        str      = Field(..., description="Defect identifier, e.g. DEF-042")
    regulation_ref:   str      = Field(..., description="Regulation reference, e.g. '12 CFR Part 370 §2(c)'")
    rationale:        str      = Field(..., description="Why this fix addresses the root cause")


# ============================================================================
# AUDIT EVENT
# ============================================================================

class AuditEvent(BaseModel):
    """
    Structured audit trail entry emitted after each pipeline phase.

    Provides an append-only record of what the orchestrator did, suitable
    for regulatory audit logs (12 CFR Part 370 §4(b)).
    """

    id: str = Field(
        default_factory=lambda: str(uuid.uuid4()),
        description="Unique AuditEvent identifier",
    )
    phase: str = Field(..., description="Pipeline phase name, e.g. 'route'")
    agent_name: Optional[str] = Field(None, description="Agent that ran this phase, if any")
    timestamp: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc),
        description="UTC timestamp when the phase completed",
    )
    outcome: str = Field(
        ...,
        description="Phase outcome: 'success' | 'failure' | 'skipped' | 'looped'",
    )
    duration_seconds: float = Field(0.0, description="Wall-clock seconds the phase took")
    message: str = Field("", description="Human-readable summary of what happened")
    metadata: Dict[str, Any] = Field(default_factory=dict, description="Arbitrary phase metadata")

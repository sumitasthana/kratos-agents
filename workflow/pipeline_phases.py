"""
workflow/pipeline_phases.py
Phase enum, PhaseResult, and RCAReport for the 7-phase Kratos pipeline.

Phase ordering (immutable):
  INTAKE → LOGS_FIRST → ROUTE → BACKTRACK → INCIDENT_CARD → RECOMMEND → PERSIST
"""
from __future__ import annotations

from enum import Enum
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field


# ============================================================================
# PHASE ENUM
# ============================================================================

class Phase(str, Enum):
    """
    Ordered enum of Kratos pipeline phases.

    The orchestrator iterates through these in :data:`PHASE_ORDER`.
    ``str`` mixin keeps JSON serialisation cheap.
    """
    INTAKE        = "intake"
    LOGS_FIRST    = "logs_first"
    ROUTE         = "route"
    BACKTRACK     = "backtrack"
    INCIDENT_CARD = "incident_card"
    RECOMMEND     = "recommend"
    PERSIST       = "persist"


#: Deterministic execution order (used as an iteration sentinel).
PHASE_ORDER: List[Phase] = [
    Phase.INTAKE,
    Phase.LOGS_FIRST,
    Phase.ROUTE,
    Phase.BACKTRACK,
    Phase.INCIDENT_CARD,
    Phase.RECOMMEND,
    Phase.PERSIST,
]


# ============================================================================
# PHASE RESULT
# ============================================================================

class PhaseResult(BaseModel):
    """
    Structured result produced after each pipeline phase.

    All lists use ``Any`` to avoid hard dependency on ``core.models`` types
    at this layer (avoids circular imports when workflow imports agents).
    """
    phase:            Phase
    success:          bool              = True
    evidence:         List[Any]         = Field(default_factory=list)
    issue_profiles:   List[Any]         = Field(default_factory=list)
    recommendations:  List[Any]         = Field(default_factory=list)
    next_phase:       Optional[Phase]   = None
    metadata:         Dict[str, Any]    = Field(default_factory=dict)
    error:            Optional[str]     = None
    duration_seconds: float             = 0.0


# ============================================================================
# RCA REPORT  (final output of KratosOrchestrator.run())
# ============================================================================

class RCAReport(BaseModel):
    """
    Complete RCA report returned when the pipeline reaches Phase.PERSIST.

    ``audit_trail`` is a list of serialised :class:`core.models.AuditEvent`
    dicts so that ``RCAReport`` itself has no direct dependency on
    ``core.models`` (avoids import cycles).
    """
    incident_id:      str              = Field(..., description="Incident identifier")
    phases_executed:  List[str]        = Field(
        default_factory=list,
        description="Ordered list of phase names actually executed",
    )
    evidence:         List[Any]        = Field(
        default_factory=list,
        description="All EvidenceObject instances collected across phases",
    )
    issue_profiles:   List[Any]        = Field(
        default_factory=list,
        description="IssueProfile(s) produced by TriangulationAgent",
    )
    recommendations:  List[Any]        = Field(
        default_factory=list,
        description="Recommendation(s) produced by RecommendationAgent",
    )
    audit_trail:      List[Any]        = Field(
        default_factory=list,
        description="Append-only list of AuditEvent dicts",
    )
    duration_seconds: float            = 0.0
    final_root_cause: str              = ""
    metadata:         Dict[str, Any]   = Field(default_factory=dict)


__all__ = ["Phase", "PHASE_ORDER", "PhaseResult", "RCAReport"]


"""causelink/rca/models.py

Domain models for the chat-driven RCA workspace.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field


class JobInvestigationRequest(BaseModel):
    """Request body for POST /rca/chat/investigate."""

    scenario_id: str = Field(..., description="One of the 5 registered scenario IDs")
    job_id: str = Field(..., description="Job identifier to investigate, e.g. 'JOB-12345'")
    user_query: str = Field(default="", description="Natural-language question from the user")
    mode: str = Field(default="normal", description="'normal' or 'exploratory'")
    max_hops: int = Field(default=3, ge=1, le=6)
    refresh: bool = Field(
        default=False,
        description="Force a fresh investigation even if a session already exists for this job",
    )
    session_id: Optional[str] = Field(
        default=None,
        description="Existing session_id for follow-up queries; None for new investigations",
    )


class JobStatusSummary(BaseModel):
    """Logs-first job status determination result."""

    job_id: str
    status: str  # "SUCCESS" | "FAILED" | "DEGRADED" | "UNKNOWN"
    source: str  # "logs" | "mock" | "ontology"
    confidence: float
    evidence_ids: List[str] = Field(default_factory=list)
    ontology_paths_used: List[str] = Field(default_factory=list)
    classification_rationale: str = ""


class IncidentCard(BaseModel):
    """Synthesized incident card generated after backtracking."""

    incident_id: Optional[str] = Field(
        default=None,
        description="None when the card is synthetic (not tied to an existing ontology incident)",
    )
    job_id: str
    scenario_id: str
    scenario_name: str
    job_status: str
    problem_type: str
    control_triggered: Optional[str] = None
    failed_node: Optional[str] = None
    failed_node_label: Optional[str] = None
    failure_reason: Optional[str] = None
    confidence: float = 0.0
    health_score: float = 0.0
    findings: List[str] = Field(default_factory=list)
    recommendations: List[str] = Field(default_factory=list)
    dashboard_url: str = ""
    created_at: datetime = Field(default_factory=datetime.utcnow)


class ChatRcaResponse(BaseModel):
    """Full response from POST /rca/chat/investigate."""

    session_id: str
    job_id: str
    scenario_id: str
    answer: str
    summary: Optional[Dict[str, Any]] = Field(
        default=None,
        description="RcaDashboardSummary serialised as dict",
    )
    job_status: str = "UNKNOWN"
    incident_card: Optional[IncidentCard] = None
    dashboard_url: str = ""
    suggested_followups: List[str] = Field(default_factory=list)
    audit_ref: str = ""

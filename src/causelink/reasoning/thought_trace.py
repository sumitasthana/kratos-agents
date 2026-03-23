"""
causelink/reasoning/thought_trace.py

ThoughtStep and ThoughtTrace — structured models for capturing agent
reasoning emitted during LLM calls.

Each ThoughtStep is one complete XML-tagged reasoning block from the model.
ThoughtTrace aggregates all steps for a single agent invocation.

These models stream to the frontend via AGENT_THOUGHT SSE events so the user
can watch the agent reason in real time.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Literal

from pydantic import BaseModel, Field, model_config


class ThoughtStep(BaseModel):
    """
    One reasoning step emitted by an agent during its LLM call.

    Generated when the streaming parser encounters a closed XML tag
    (<observe>...</observe> etc.) in the model's response.
    """

    model_config = model_config = {"frozen": True}  # type: ignore[assignment]

    step_index: int
    agent: str
    phase: str
    thought_type: Literal[
        "OBSERVING",      # agent describing what it sees in the evidence
        "HYPOTHESISING",  # agent forming a candidate explanation
        "TESTING",        # agent checking hypothesis against ontology / evidence
        "REJECTING",      # agent explaining why a hypothesis was discarded
        "ACCEPTING",      # agent explaining why a hypothesis was promoted
        "CONCLUDING",     # agent stating its final determination for this phase
        "WARNING",        # agent flagging an anomaly it noticed
    ]
    content: str
    evidence_refs: list[str] = Field(default_factory=list)
    node_refs: list[str] = Field(default_factory=list)
    confidence_delta: float = 0.0
    duration_ms: int = 0
    timestamp: str = Field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat()
    )


class ThoughtTrace(BaseModel):
    """Full chain of thought for one agent invocation."""

    agent: str
    phase: str
    investigation_id: str
    steps: list[ThoughtStep] = Field(default_factory=list)
    conclusion: str = ""
    total_duration_ms: int = 0
    tokens_used: int = 0

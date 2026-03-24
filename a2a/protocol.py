"""
a2a/protocol.py
Agent-to-Agent (A2A) message type definitions for the CauseLink RCA service.

Extracted from: src/causelink_api.py
Split rule: request/response Pydantic schemas (protocol types only).
            Server/handler logic lives in a2a/server.py.

These models define the HTTP contract for the CauseLink investigation API.
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field


# ─────────────────────────────────────────────────────────────────────────────
# In-memory investigation store (shared between protocol and server)
# ─────────────────────────────────────────────────────────────────────────────

import asyncio


class InvestigationStore:
    """Thread-safe in-memory store for investigation states."""

    def __init__(self) -> None:
        self._by_id: Dict[str, Any] = {}
        self._idempotency: Dict[str, str] = {}  # idempotency_key → investigation_id
        self._lock = asyncio.Lock()

    async def get(self, investigation_id: str) -> Optional[Any]:
        return self._by_id.get(investigation_id)

    async def put(self, state: Any) -> None:
        async with self._lock:
            inv_id = state.investigation_input.investigation_id
            self._by_id[inv_id] = state
            key = state.investigation_input.idempotency_key
            if key:
                self._idempotency[key] = inv_id

    async def find_by_idempotency_key(self, key: str) -> Optional[Any]:
        inv_id = self._idempotency.get(key)
        if inv_id:
            return self._by_id.get(inv_id)
        return None

    async def all_ids(self) -> List[str]:
        return list(self._by_id.keys())


# ─────────────────────────────────────────────────────────────────────────────
# Request schemas
# ─────────────────────────────────────────────────────────────────────────────


class StartInvestigationRequest(BaseModel):
    """POST /investigations request body."""

    anchor_type: str = Field(
        ...,
        description=(
            "Ontology label of the investigation anchor. "
            "Must be one of: Incident, Violation, Job, Pipeline, System"
        ),
    )
    anchor_primary_key: str = Field(
        ..., description="Primary key property name, e.g. 'incident_id'"
    )
    anchor_primary_value: str = Field(
        ..., description="Value of the anchor primary key, e.g. 'INC-2026-001'"
    )
    max_hops: int = Field(default=3, ge=1, le=6)
    confidence_threshold: float = Field(default=0.80, ge=0.0, le=1.0)
    context: Dict[str, Any] = Field(
        default_factory=dict,
        description=(
            "Optional context dictionary. "
            "Supported keys: time_range_start, time_range_end (ISO-8601 strings)."
        ),
    )
    idempotency_key: Optional[str] = Field(
        None,
        description=(
            "Caller-supplied idempotency key. "
            "Submitting the same key twice returns the existing investigation "
            "without re-running the pipeline."
        ),
    )


# ─────────────────────────────────────────────────────────────────────────────
# Response schemas
# ─────────────────────────────────────────────────────────────────────────────


class InvestigationSummaryResponse(BaseModel):
    """Lightweight status response for POST /investigations and listing."""

    investigation_id: str
    status: str
    anchor_type: str
    anchor_value: str
    created_at: str
    updated_at: str
    escalation: bool
    root_cause_confirmed: bool
    root_cause_summary: Optional[str] = None
    missing_evidence_count: int = 0
    hypothesis_count: int = 0


class InvestigationResultResponse(BaseModel):
    """Full investigation result returned by GET /investigations/{id}."""

    investigation_id: str
    status: str
    anchor_type: str
    anchor_value: str
    created_at: str
    updated_at: str
    escalation: bool
    escalation_reason: Optional[str]
    root_cause_final: Optional[Dict[str, Any]]
    root_cause_candidates: List[Dict[str, Any]]
    hypotheses: List[Dict[str, Any]]
    missing_evidence: List[Dict[str, Any]]
    recommended_actions: List[str]
    causal_graph_edges_count: int
    causal_graph_node_count: int
    ontology_paths_count: int
    insufficient_evidence_report: Optional[Dict[str, Any]]

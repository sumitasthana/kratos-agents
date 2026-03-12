"""
causelink/evidence/contracts.py

EvidenceObject — the immutable, traceable unit of all evidence in CauseLink.
EvidenceService — abstract interface that all evidence connector implementations must satisfy.

Design constraints:
  - EvidenceObjects are IMMUTABLE after construction (frozen Pydantic model).
  - Raw content is NEVER stored inline; only content_ref (URI/pointer) is stored.
  - raw_hash (SHA-256) provides integrity verification without storing content.
  - Summary fields are expected to be redacted/masked by the collecting agent.
  - EvidenceService implementations must never fabricate evidence; if a query
    returns no results, they must return None and populate MissingEvidence.
"""

from __future__ import annotations

import hashlib
from abc import ABC, abstractmethod
from datetime import datetime
from enum import Enum
from typing import Any, Dict, List, Optional, Tuple
import uuid

from pydantic import BaseModel, Field, model_validator


# ─── Enums ────────────────────────────────────────────────────────────────────


class EvidenceType(str, Enum):
    LOG             = "log"
    METRIC          = "metric"
    CHANGE_EVENT    = "change_event"
    AUDIT_EVENT     = "audit_event"
    LINEAGE_TRACE   = "lineage_trace"
    QUERY_RESULT    = "query_result"
    SCHEMA_SNAPSHOT = "schema_snapshot"


class EvidenceReliabilityTier(str, Enum):
    HIGH   = "high"    # 0.80–1.00 — authoritative source (signed audit log, snapshot)
    MEDIUM = "medium"  # 0.50–0.80 — derived from reliable source
    LOW    = "low"     # 0.00–0.50 — heuristic or inferred


# ─── EvidenceObject ───────────────────────────────────────────────────────────


class EvidenceObject(BaseModel):
    """
    An immutable, traceable unit of evidence.

    Never store raw evidence content in memory; use content_ref (a
    storage URI or file path) and provide a redacted summary only.
    raw_hash allows integrity verification without re-reading content.

    This model is frozen — it must not be modified after construction.
    """

    model_config = {"frozen": True}

    evidence_id: str = Field(
        default_factory=lambda: str(uuid.uuid4()),
        description="Unique identifier — used as citation key in hypotheses and causal edges",
    )
    type: EvidenceType = Field(..., description="Category of evidence")
    source_system: str = Field(
        ...,
        description=(
            "System that originated this evidence, e.g. 'splunk', 'datadog', "
            "'airflow', 'git'. Never include connection strings or credentials."
        ),
    )
    time_range_start: Optional[datetime] = Field(
        None, description="Start of the time window covered by this evidence"
    )
    time_range_end: Optional[datetime] = Field(
        None, description="End of the time window covered by this evidence"
    )
    query_executed: Optional[str] = Field(
        None,
        description=(
            "Query, search filter, or API call used to retrieve this evidence. "
            "Redact any credential or PII-like parameters before storing."
        ),
    )
    content_ref: str = Field(
        ...,
        description=(
            "URI or storage pointer to the raw evidence content. "
            "Must NOT be a plain-text dump of the content. "
            "Examples: 's3://bucket/evidence/abc.gz', 'file:///tmp/ev/abc.json'"
        ),
    )
    summary: str = Field(
        ...,
        description=(
            "Human-readable, redacted summary of what this evidence shows. "
            "Must not contain PII, credentials, or raw log lines."
        ),
    )
    reliability: float = Field(
        ...,
        ge=0.0,
        le=1.0,
        description="Reliability score 0–1; higher = more authoritative source",
    )
    reliability_tier: EvidenceReliabilityTier = Field(
        ..., description="Derived tier classification for the reliability score"
    )
    raw_hash: str = Field(
        ...,
        description=(
            "SHA-256 hex digest of the raw content at collection time. "
            "Used for integrity verification and deduplication. "
            "Format: 'sha256:<64-char-hex>'"
        ),
    )
    collected_at: datetime = Field(default_factory=datetime.utcnow)
    collected_by: str = Field(
        ..., description="AgentType string of the agent that collected this evidence"
    )
    tags: Tuple[str, ...] = Field(
        default_factory=tuple,
        description="Searchable tags, e.g. ('spark', 'executor', 'oom')",
    )

    @model_validator(mode="after")
    def _validate_hash_format(self) -> "EvidenceObject":
        if not self.raw_hash.startswith("sha256:"):
            raise ValueError(
                "raw_hash must be formatted as 'sha256:<64-char-hex-digest>'. "
                "Use EvidenceObject.make_hash(raw_bytes) to generate."
            )
        hex_part = self.raw_hash[len("sha256:"):]
        if len(hex_part) != 64 or not all(c in "0123456789abcdef" for c in hex_part):
            raise ValueError(
                "raw_hash hex portion must be exactly 64 lowercase hex characters."
            )
        return self

    @model_validator(mode="after")
    def _validate_reliability_tier_consistency(self) -> "EvidenceObject":
        expected_tier = EvidenceObject._tier_from_score(self.reliability)
        if self.reliability_tier != expected_tier:
            raise ValueError(
                f"reliability_tier={self.reliability_tier} is inconsistent with "
                f"reliability={self.reliability} (expected {expected_tier}). "
                "Use EvidenceObject.tier_for(score) to compute the correct tier."
            )
        return self

    # ── Helpers ───────────────────────────────────────────────────────────────

    @staticmethod
    def make_hash(raw_bytes: bytes) -> str:
        """
        Compute a correctly-formatted raw_hash from raw content bytes.

        Usage::

            hash_str = EvidenceObject.make_hash(file_bytes)
        """
        return "sha256:" + hashlib.sha256(raw_bytes).hexdigest()

    @staticmethod
    def tier_for(reliability: float) -> EvidenceReliabilityTier:
        if reliability >= 0.80:
            return EvidenceReliabilityTier.HIGH
        if reliability >= 0.50:
            return EvidenceReliabilityTier.MEDIUM
        return EvidenceReliabilityTier.LOW

    @staticmethod
    def _tier_from_score(score: float) -> EvidenceReliabilityTier:
        return EvidenceObject.tier_for(score)


# ─── EvidenceSearchParams ─────────────────────────────────────────────────────


class EvidenceSearchParams(BaseModel):
    """Common parameters shared by all EvidenceService calls."""

    entity_ids: List[str] = Field(
        ...,
        min_length=1,
        description=(
            "neo4j_ids of CanonGraph nodes to scope the search. "
            "Searches outside the scoped node set are not permitted."
        ),
    )
    time_range_start: Optional[datetime] = None
    time_range_end: Optional[datetime] = None
    max_results: int = Field(
        default=100,
        ge=1,
        le=10_000,
        description="Maximum number of raw results to retrieve",
    )
    tags: List[str] = Field(default_factory=list)
    context: Dict[str, Any] = Field(
        default_factory=dict,
        description="Additional source-specific search parameters",
    )


# ─── EvidenceService (abstract) ───────────────────────────────────────────────


class EvidenceService(ABC):
    """
    Abstract interface for all evidence connectors.

    Implementations MUST:
      1. Never fabricate evidence — return None if no results exist.
      2. Store raw content to a content_ref URI, never inline.
      3. Compute raw_hash from the actual content bytes.
      4. Redact/mask PII and credentials in summary and query_executed.
      5. Scope all queries to the entity_ids provided in params
         (no unconstrained searches).

    Stubs in this file raise NotImplementedError so tests can detect
    when a real connector is expected but not yet wired.
    """

    @abstractmethod
    def search_logs(
        self,
        params: EvidenceSearchParams,
        collected_by: str,
    ) -> Optional[EvidenceObject]:
        """
        Search log sources for entries related to *params.entity_ids*.
        Returns None and populates caller's MissingEvidence list if no logs found.
        """
        raise NotImplementedError

    @abstractmethod
    def query_metrics(
        self,
        params: EvidenceSearchParams,
        metric_names: List[str],
        collected_by: str,
    ) -> Optional[EvidenceObject]:
        """
        Query a metrics store (e.g. Prometheus, Datadog) for given metric_names
        scoped to params.entity_ids within the time range.
        """
        raise NotImplementedError

    @abstractmethod
    def fetch_change_events(
        self,
        params: EvidenceSearchParams,
        collected_by: str,
    ) -> Optional[EvidenceObject]:
        """
        Retrieve code/config change events (e.g. git commits, deploys)
        for the entities in scope.
        """
        raise NotImplementedError

    @abstractmethod
    def fetch_audit_events(
        self,
        params: EvidenceSearchParams,
        collected_by: str,
    ) -> Optional[EvidenceObject]:
        """
        Retrieve audit log entries from a compliance audit system.
        Must only access records for the scoped entities.
        """
        raise NotImplementedError

    @abstractmethod
    def get_lineage_trace(
        self,
        params: EvidenceSearchParams,
        collected_by: str,
    ) -> Optional[EvidenceObject]:
        """
        Retrieve data lineage trace for the scoped entities
        (e.g. OpenLineage, Marquez).
        """
        raise NotImplementedError

    @abstractmethod
    def get_evidence(self, evidence_id: str) -> Optional[EvidenceObject]:
        """
        Retrieve a previously-collected EvidenceObject by its evidence_id.
        Returns None if not found — callers must handle None explicitly.
        """
        raise NotImplementedError


# ─── NullEvidenceService (test/stub implementation) ──────────────────────────


class NullEvidenceService(EvidenceService):
    """
    No-op evidence service for unit testing and local development.

    All methods return None, indicating no evidence is available.
    Tests that require actual evidence should mock specific methods.
    """

    def search_logs(self, params: EvidenceSearchParams, collected_by: str) -> None:
        return None

    def query_metrics(
        self,
        params: EvidenceSearchParams,
        metric_names: List[str],
        collected_by: str,
    ) -> None:
        return None

    def fetch_change_events(
        self, params: EvidenceSearchParams, collected_by: str
    ) -> None:
        return None

    def fetch_audit_events(
        self, params: EvidenceSearchParams, collected_by: str
    ) -> None:
        return None

    def get_lineage_trace(
        self, params: EvidenceSearchParams, collected_by: str
    ) -> None:
        return None

    def get_evidence(self, evidence_id: str) -> None:
        return None

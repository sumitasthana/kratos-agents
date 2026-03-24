"""
causelink/ontology/schema.py

Authoritative CauseLink ontology schema.

DO NOT add node labels or relationship types here without schema governance approval.
This file is the single source of truth; all Cypher construction and validation
references these frozensets.  Any runtime path that deviates is rejected.

Node labels:
    System, Job, Pipeline, Script, Transformation, CodeEvent,
    DataSource, Dataset, Table, Column, LogSource, Regulation,
    ControlObjective, Rule, Owner, Violation, Incident, Escalation, Remediation

Relationship types:
    RUNS_JOB, DEPENDS_ON, EXECUTES, USES_SCRIPT, HAS_TRANSFORMATION,
    TYPICALLY_IMPLEMENTS, READS, WRITES, CONTAINS, HAS_COLUMN,
    DERIVED_FROM, SOURCED_FROM, CHANGED_BY, LOGGED_IN, MANDATES,
    IMPLEMENTED_BY, ENFORCED_BY, OWNS_PIPELINE, OWNS_JOB, OWNS_SYSTEM,
    OWNS_CONTROL, GENERATES, CREATES, TRIGGERS, ASSIGNED_TO, RESOLVED_BY

Anchor labels (valid investigation start-node types):
    Incident, Violation, Job, Pipeline, System
"""

from __future__ import annotations

from datetime import datetime
from typing import Dict, FrozenSet, List

from pydantic import BaseModel, Field

# ─── Node Labels ─────────────────────────────────────────────────────────────

NODE_LABELS: FrozenSet[str] = frozenset({
    "System",
    "Job",
    "Pipeline",
    "Script",
    "Transformation",
    "CodeEvent",
    "DataSource",
    "Dataset",
    "Table",
    "Column",
    "LogSource",
    "Regulation",
    "ControlObjective",
    "Rule",
    "Owner",
    "Violation",
    "Incident",
    "Escalation",
    "Remediation",
})

# ─── Relationship Types ───────────────────────────────────────────────────────

RELATIONSHIP_TYPES: FrozenSet[str] = frozenset({
    "RUNS_JOB",
    "DEPENDS_ON",
    "EXECUTES",
    "USES_SCRIPT",
    "HAS_TRANSFORMATION",
    "TYPICALLY_IMPLEMENTS",
    "READS",
    "WRITES",
    "CONTAINS",
    "HAS_COLUMN",
    "DERIVED_FROM",
    "SOURCED_FROM",
    "CHANGED_BY",
    "LOGGED_IN",
    "MANDATES",
    "IMPLEMENTED_BY",
    "ENFORCED_BY",
    "OWNS_PIPELINE",
    "OWNS_JOB",
    "OWNS_SYSTEM",
    "OWNS_CONTROL",
    "GENERATES",
    "CREATES",
    "TRIGGERS",
    "ASSIGNED_TO",
    "RESOLVED_BY",
})

# ─── Anchor Labels ────────────────────────────────────────────────────────────

ANCHOR_LABELS: FrozenSet[str] = frozenset({
    "Incident",
    "Violation",
    "Job",
    "Pipeline",
    "System",
})

# ─── Primary Key Map  (label → canonical ID property used in Cypher queries) ─

LABEL_PRIMARY_KEY: Dict[str, str] = {
    "System":           "system_id",
    "Job":              "job_id",
    "Pipeline":         "pipeline_id",
    "Script":           "script_id",
    "Transformation":   "transformation_id",
    "CodeEvent":        "event_id",
    "DataSource":       "source_id",
    "Dataset":          "dataset_id",
    "Table":            "table_id",
    "Column":           "column_id",
    "LogSource":        "log_source_id",
    "Regulation":       "regulation_id",
    "ControlObjective": "objective_id",
    "Rule":             "rule_id",
    "Owner":            "owner_id",
    "Violation":        "violation_id",
    "Incident":         "incident_id",
    "Escalation":       "escalation_id",
    "Remediation":      "remediation_id",
}

# ─── Schema Snapshot (embedded in InvestigationState for auditability) ────────


class OntologySchemaSnapshot(BaseModel):
    """
    Immutable snapshot of the ontology schema captured at investigation start.

    Embedded in every InvestigationState so that auditors can verify which schema
    version governed each investigation — independent of future schema changes.
    """

    schema_version: str = "1.0.0"
    snapshot_at: datetime = Field(default_factory=datetime.utcnow)
    node_labels: List[str] = Field(default_factory=list)
    relationship_types: List[str] = Field(default_factory=list)
    anchor_labels: List[str] = Field(default_factory=list)

    @classmethod
    def current(cls) -> "OntologySchemaSnapshot":
        """Return a snapshot of the currently authoritative schema."""
        return cls(
            snapshot_at=datetime.utcnow(),
            node_labels=sorted(NODE_LABELS),
            relationship_types=sorted(RELATIONSHIP_TYPES),
            anchor_labels=sorted(ANCHOR_LABELS),
        )

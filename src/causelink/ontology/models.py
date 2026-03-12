"""
causelink/ontology/models.py

CanonGraph — the structural memory of an investigation.

All nodes and edges are validated against the authoritative ontology schema (schema.py).
Agents may only reason about entities present in the CanonGraph; no global Neo4j
queries are permitted after graph construction.

Key types:
    CanonNode       — a validated neo4j node
    CanonEdge       — a validated neo4j relationship
    OntologyPath    — an explicit traversal path (required for every causal claim)
    CanonGraph      — bounded subgraph + lookup helpers
"""

from __future__ import annotations

import logging
from datetime import datetime
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field, model_validator

from .schema import NODE_LABELS, RELATIONSHIP_TYPES

logger = logging.getLogger(__name__)


# ─── CanonNode ────────────────────────────────────────────────────────────────


class CanonNode(BaseModel):
    """
    A Neo4j node retrieved during neighborhood expansion.

    All labels are validated against NODE_LABELS; nodes bearing unknown labels
    are rejected at construction time rather than silently included.
    neo4j_id is the driver's elementId() string — treat it as opaque.
    """

    neo4j_id: str = Field(
        ...,
        description=(
            "Neo4j elementId() — stable string key, never reuse as a business identifier. "
            "Always pass back to Neo4j as a parameter, never interpolated."
        ),
    )
    labels: List[str] = Field(
        ..., description="Node labels, validated against NODE_LABELS"
    )
    primary_key: Optional[str] = Field(
        None, description="Canonical ID property name, e.g. 'incident_id'"
    )
    primary_value: Optional[str] = Field(
        None, description="Value of the primary key property (stringified)"
    )
    properties: Dict[str, Any] = Field(
        default_factory=dict,
        description="Node properties — credential-like keys are redacted on ingestion",
    )
    provenance: str = Field(
        ...,
        description="How this node was discovered, e.g. 'neo4j:anchor:Incident' or 'neo4j:neighborhood:hop≤2'",
    )

    @model_validator(mode="after")
    def _validate_labels(self) -> "CanonNode":
        unknown = [lbl for lbl in self.labels if lbl not in NODE_LABELS]
        if unknown:
            raise ValueError(
                f"Ontology violation: unknown node label(s) {unknown}. "
                f"Allowed labels: {sorted(NODE_LABELS)}"
            )
        return self


# ─── CanonEdge ────────────────────────────────────────────────────────────────


class CanonEdge(BaseModel):
    """
    A Neo4j relationship retrieved during neighborhood expansion.

    type is validated against RELATIONSHIP_TYPES; unknown relationship types
    are rejected rather than silently included.
    """

    neo4j_id: Optional[str] = Field(
        None,
        description="Neo4j elementId() of the relationship - may be absent for synthesised edges",
    )
    type: str = Field(
        ..., description="Relationship type, validated against RELATIONSHIP_TYPES"
    )
    start_node_id: str = Field(
        ..., description="neo4j_id of the start node (matches CanonNode.neo4j_id)"
    )
    end_node_id: str = Field(
        ..., description="neo4j_id of the end node (matches CanonNode.neo4j_id)"
    )
    properties: Dict[str, Any] = Field(default_factory=dict)
    provenance: str = Field(
        ...,
        description="How this edge was retrieved, e.g. 'neo4j:neighborhood:hop≤2'",
    )

    @model_validator(mode="after")
    def _validate_type(self) -> "CanonEdge":
        if self.type not in RELATIONSHIP_TYPES:
            raise ValueError(
                f"Ontology violation: unknown relationship type '{self.type}'. "
                f"Allowed types: {sorted(RELATIONSHIP_TYPES)}"
            )
        return self


# ─── OntologyPath ─────────────────────────────────────────────────────────────


class OntologyPath(BaseModel):
    """
    An explicit traversal path from Neo4j.

    Every confirmed causal claim MUST reference at least one OntologyPath that
    structurally validates the link between cause and effect in the ontology.
    A claim without an OntologyPath must be rejected with
    status = REJECTED_NO_ONTOLOGY_PATH.
    """

    path_id: str = Field(..., description="UUID for this path record")
    description: str = Field(
        ...,
        description=(
            "Human-readable path summary, e.g. "
            "'Incident-[TRIGGERS]->Job-[RUNS_JOB]->Pipeline'"
        ),
    )
    node_sequence: List[str] = Field(
        ..., description="Ordered list of neo4j_ids (CanonNode.neo4j_id)"
    )
    rel_type_sequence: List[str] = Field(
        ..., description="Ordered list of relationship types between nodes"
    )
    hop_count: int = Field(..., description="Number of hops (len(rel_type_sequence))")
    query_used: str = Field(
        ...,
        description=(
            "Cypher query or SHA256 hash thereof that produced this path. "
            "Full Cypher stored only when it contains no sensitive parameters."
        ),
    )


# ─── CanonGraph ───────────────────────────────────────────────────────────────


class CanonGraph(BaseModel):
    """
    Bounded ontology subgraph centered on an investigation anchor.

    This is the ONLY source of structural truth for an investigation.
    Agents may only reference entities whose neo4j_id appears in this graph;
    no ad-hoc Neo4j queries are permitted after graph construction.

    Lookup helpers (get_node, neighbors, find_nodes_by_label, summary) are
    populated automatically after construction via model_post_init.
    """

    anchor_neo4j_id: str = Field(..., description="elementId() of the anchor node")
    anchor_label: str = Field(
        ..., description="Anchor node label — must be in ANCHOR_LABELS"
    )
    anchor_primary_key: str = Field(
        ..., description="Property name used as the investigation anchor key"
    )
    anchor_primary_value: str = Field(
        ..., description="Value of the anchor primary key (the investigation ID)"
    )

    nodes: List[CanonNode] = Field(default_factory=list)
    edges: List[CanonEdge] = Field(default_factory=list)
    ontology_paths_used: List[OntologyPath] = Field(
        default_factory=list,
        description="All paths returned or validated during graph construction",
    )

    retrieved_at: datetime = Field(default_factory=datetime.utcnow)
    max_hops: int = Field(
        default=3,
        description="Maximum traversal depth used when this graph was built",
    )

    # Internal indexes — populated in model_post_init, excluded from serialisation
    _node_index: Dict[str, CanonNode] = {}
    _adj: Dict[str, List[CanonEdge]] = {}

    def model_post_init(self, __context: Any) -> None:
        node_idx: Dict[str, CanonNode] = {n.neo4j_id: n for n in self.nodes}
        adj: Dict[str, List[CanonEdge]] = {}
        for edge in self.edges:
            adj.setdefault(edge.start_node_id, []).append(edge)
            adj.setdefault(edge.end_node_id, []).append(edge)
        # Use object.__setattr__ to bypass Pydantic's immutability for private attrs
        object.__setattr__(self, "_node_index", node_idx)
        object.__setattr__(self, "_adj", adj)

    # ── Lookup helpers ──────────────────────────────────────────────────────

    def get_node(self, neo4j_id: str) -> Optional[CanonNode]:
        """Return the CanonNode with the given elementId, or None."""
        return self._node_index.get(neo4j_id)

    def neighbors(self, neo4j_id: str) -> List[CanonNode]:
        """Return all nodes adjacent to the given node (undirected)."""
        edges = self._adj.get(neo4j_id, [])
        neighbor_ids = {
            e.end_node_id if e.start_node_id == neo4j_id else e.start_node_id
            for e in edges
        }
        return [
            self._node_index[nid]
            for nid in neighbor_ids
            if nid in self._node_index
        ]

    def find_nodes_by_label(self, label: str) -> List[CanonNode]:
        """
        Return all nodes bearing the given label.
        Raises ValueError for labels not in NODE_LABELS (fail-fast; never guess).
        """
        if label not in NODE_LABELS:
            raise ValueError(
                f"Unknown ontology label '{label}'. Allowed: {sorted(NODE_LABELS)}"
            )
        return [n for n in self.nodes if label in n.labels]

    def edges_between(self, node_id_a: str, node_id_b: str) -> List[CanonEdge]:
        """Return all direct edges between two nodes in either direction."""
        return [
            e
            for e in self._adj.get(node_id_a, [])
            if e.start_node_id == node_id_b or e.end_node_id == node_id_b
        ]

    def contains_node(self, neo4j_id: str) -> bool:
        return neo4j_id in self._node_index

    def summary(self) -> Dict[str, Any]:
        """Compact summary for logging and audit traces."""
        label_counts: Dict[str, int] = {}
        for node in self.nodes:
            for lbl in node.labels:
                label_counts[lbl] = label_counts.get(lbl, 0) + 1
        rel_counts: Dict[str, int] = {}
        for edge in self.edges:
            rel_counts[edge.type] = rel_counts.get(edge.type, 0) + 1
        return {
            "anchor": f"{self.anchor_label}:{self.anchor_primary_value}",
            "max_hops": self.max_hops,
            "node_count": len(self.nodes),
            "edge_count": len(self.edges),
            "label_counts": label_counts,
            "relationship_counts": rel_counts,
            "retrieved_at": self.retrieved_at.isoformat(),
        }

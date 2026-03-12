"""
causelink/ontology/adapter.py

Neo4jOntologyAdapter — retrieves bounded subgraphs and validates causal paths.

Connection configuration (NEVER hardcode credentials):
    NEO4J_URI       bolt://localhost:7687
    NEO4J_USER      neo4j
    NEO4J_PASSWORD  <from secret manager / env>

Requires Neo4j 5.0+ (uses elementId() Cypher function and driver .element_id attribute).

Security notes:
  - All user-supplied values (anchor_primary_value, node IDs) are always passed
    as Cypher parameters — never string-interpolated into queries.
  - Only anchor_label (validated against ANCHOR_LABELS) and max_hops (int, capped)
    are interpolated; both come from the authoritative schema frozenset, not from
    external callers.
  - Credential-looking node properties are redacted on ingestion.
  - The adapter never stores or logs credentials.
"""

from __future__ import annotations

import hashlib
import logging
import os
import uuid
from contextlib import contextmanager
from datetime import datetime
from typing import Any, Dict, Generator, List, Optional, Tuple

try:
    from neo4j import GraphDatabase
    from neo4j.exceptions import Neo4jError

    _NEO4J_AVAILABLE = True
except ImportError:  # pragma: no cover
    _NEO4J_AVAILABLE = False

from .models import CanonEdge, CanonGraph, CanonNode, OntologyPath
from .schema import (
    ANCHOR_LABELS,
    LABEL_PRIMARY_KEY,
    NODE_LABELS,
    RELATIONSHIP_TYPES,
    OntologySchemaSnapshot,
)

logger = logging.getLogger(__name__)

_DEFAULT_MAX_HOPS: int = 3
_HARD_MAX_HOPS: int = 6  # safety ceiling — prevents runaway traversals

# Properties that must never appear in outputs even if present in Neo4j
_SENSITIVE_PROPERTY_KEYS: frozenset = frozenset(
    {"password", "secret", "token", "api_key", "credential", "private_key", "auth"}
)


# ─── Exceptions ───────────────────────────────────────────────────────────────


class OntologyAdapterError(Exception):
    """Raised when the adapter cannot fulfil a request (driver missing, query failure, etc.)."""


class OntologyGap(Exception):
    """
    Raised when a requested entity or relationship does not exist in Neo4j.

    Callers MUST surface this as an 'Ontology gap' in the investigation output
    and specify the missing node/edge — never guess or fabricate.
    """

    def __init__(self, message: str, missing_spec: str) -> None:
        super().__init__(message)
        self.missing_spec = missing_spec


# ─── Adapter ──────────────────────────────────────────────────────────────────


class Neo4jOntologyAdapter:
    """
    Retrieves bounded ontology subgraphs from Neo4j and validates causal paths.

    All Cypher uses only the authoritative labels and relationship types from
    causelink.ontology.schema.  Any result that deviates is rejected at model
    validation.

    Usage::

        adapter = Neo4jOntologyAdapter.from_env()
        graph = adapter.get_neighborhood(
            anchor_label="Incident",
            anchor_primary_key="incident_id",
            anchor_primary_value="INC-2026-001",
            max_hops=2,
        )
        path = adapter.validate_shortest_path(
            start_node_id=cause_node.neo4j_id,
            end_node_id=incident_node.neo4j_id,
        )
        if path is None:
            # CausalEdge status = REJECTED_NO_ONTOLOGY_PATH
    """

    def __init__(self, uri: str, user: str, password: str) -> None:
        if not _NEO4J_AVAILABLE:
            raise OntologyAdapterError(
                "neo4j Python driver not installed. "
                "Run: pip install 'neo4j>=5.0'"
            )
        self._uri = uri
        # Driver holds a connection pool; credentials are never logged
        self._driver = GraphDatabase.driver(uri, auth=(user, password))
        logger.info("Neo4jOntologyAdapter initialised (uri=%s)", uri)

    # ── Construction ─────────────────────────────────────────────────────────

    @classmethod
    def from_env(cls) -> "Neo4jOntologyAdapter":
        """
        Build adapter from environment variables.

        Required env vars: NEO4J_URI, NEO4J_USER, NEO4J_PASSWORD
        """
        uri = os.environ.get("NEO4J_URI", "")
        user = os.environ.get("NEO4J_USER", "")
        password = os.environ.get("NEO4J_PASSWORD", "")
        if not (uri and user and password):
            raise OntologyAdapterError(
                "Missing required env vars for Neo4j connection. "
                "Set NEO4J_URI, NEO4J_USER, and NEO4J_PASSWORD."
            )
        return cls(uri=uri, user=user, password=password)

    def close(self) -> None:
        self._driver.close()

    def __enter__(self) -> "Neo4jOntologyAdapter":
        return self

    def __exit__(self, *_: Any) -> None:
        self.close()

    # ── Connectivity ─────────────────────────────────────────────────────────

    def verify_connectivity(self) -> bool:
        try:
            self._driver.verify_connectivity()
            return True
        except Exception as exc:
            logger.error("Neo4j connectivity check failed: %s", exc)
            return False

    # ── Public API ────────────────────────────────────────────────────────────

    def get_neighborhood(
        self,
        anchor_label: str,
        anchor_primary_key: str,
        anchor_primary_value: str,
        max_hops: int = _DEFAULT_MAX_HOPS,
    ) -> CanonGraph:
        """
        Retrieve a bounded neighborhood around an anchor node.

        Returns a CanonGraph containing all nodes reachable within *max_hops* of
        the anchor, plus all direct edges between those nodes.

        Raises OntologyAdapterError if:
          - anchor_label is not in ANCHOR_LABELS
          - Neo4j is unreachable or the query fails
          - Any returned label/type violates the authoritative schema

        If the anchor node does not exist, returns an empty CanonGraph
        (anchor_neo4j_id = "NOT_FOUND") — callers should treat this as an
        Ontology Gap and report missing_spec.
        """
        self._validate_anchor_label(anchor_label)
        max_hops = min(max(1, max_hops), _HARD_MAX_HOPS)

        # Step 1: fetch anchor + neighbor nodes
        anchor_node_raw, neighbor_nodes_raw = self._query_nodes(
            anchor_label=anchor_label,
            anchor_primary_key=anchor_primary_key,
            anchor_primary_value=anchor_primary_value,
            max_hops=max_hops,
        )

        if anchor_node_raw is None:
            logger.warning(
                "Anchor %s{%s=%r} not found in Neo4j — ontology gap.",
                anchor_label,
                anchor_primary_key,
                anchor_primary_value,
            )
            return CanonGraph(
                anchor_neo4j_id="NOT_FOUND",
                anchor_label=anchor_label,
                anchor_primary_key=anchor_primary_key,
                anchor_primary_value=anchor_primary_value,
                max_hops=max_hops,
            )

        anchor_id = self._element_id(anchor_node_raw)

        # Build CanonNode list
        nodes = self._build_canon_nodes(
            anchor_node_raw=anchor_node_raw,
            anchor_label=anchor_label,
            anchor_primary_key=anchor_primary_key,
            anchor_primary_value=anchor_primary_value,
            neighbor_nodes_raw=neighbor_nodes_raw,
            max_hops=max_hops,
        )
        all_ids = [n.neo4j_id for n in nodes]

        # Step 2: fetch all direct edges between neighborhood nodes
        edges = self._query_edges(all_ids, max_hops)

        # Build path description for audit trail
        path = self._build_neighborhood_path(nodes, edges, anchor_id, max_hops)

        return CanonGraph(
            anchor_neo4j_id=anchor_id,
            anchor_label=anchor_label,
            anchor_primary_key=anchor_primary_key,
            anchor_primary_value=anchor_primary_value,
            nodes=nodes,
            edges=edges,
            ontology_paths_used=[path],
            retrieved_at=datetime.utcnow(),
            max_hops=max_hops,
        )

    def validate_shortest_path(
        self,
        start_node_id: str,
        end_node_id: str,
        max_hops: int = _DEFAULT_MAX_HOPS,
    ) -> Optional[OntologyPath]:
        """
        Check whether a structural path exists between two CanonGraph nodes.

        Returns an OntologyPath if a path is found within *max_hops*, else None.

        A None return MUST be treated as
            status = REJECTED_NO_ONTOLOGY_PATH
        and reported as an ontology gap.  The caller must NOT invent an
        alternative path or skip this check.

        Raises OntologyAdapterError on query failure.
        """
        max_hops = min(max(1, max_hops), _HARD_MAX_HOPS)

        # Both IDs are passed as parameters — no interpolation of user data
        cypher = (
            "MATCH (a), (b) "
            "WHERE elementId(a) = $start_id AND elementId(b) = $end_id "
            f"MATCH p = shortestPath((a)-[*..{max_hops}]-(b)) "
            "RETURN "
            "  [n IN nodes(p) | elementId(n)]         AS node_ids, "
            "  [r IN relationships(p) | type(r)]       AS rel_types, "
            "  length(p)                               AS hop_count"
        )
        params: Dict[str, Any] = {
            "start_id": start_node_id,
            "end_id": end_node_id,
        }

        with self._session() as session:
            try:
                records = list(session.run(cypher, params))
            except Exception as exc:
                raise OntologyAdapterError(
                    f"Shortest-path query failed for "
                    f"start={start_node_id}, end={end_node_id}: {exc}"
                ) from exc

        if not records:
            return None

        rec = records[0]
        rel_types: List[str] = list(rec["rel_types"])
        node_ids: List[str] = list(rec["node_ids"])

        # Reject paths containing undeclared relationship types — possible schema drift
        unknown_rels = [r for r in rel_types if r not in RELATIONSHIP_TYPES]
        if unknown_rels:
            raise OntologyAdapterError(
                f"Shortest-path returned undeclared relationship types: {unknown_rels}. "
                "Possible schema drift — validate Neo4j against authoritative schema."
            )

        path_str = self._format_path_string(node_ids, rel_types)
        # Store a hash of the query, not the full string (may contain element IDs)
        cypher_hash = hashlib.sha256(cypher.encode()).hexdigest()[:16]

        return OntologyPath(
            path_id=str(uuid.uuid4()),
            description=path_str,
            node_sequence=node_ids,
            rel_type_sequence=rel_types,
            hop_count=int(rec["hop_count"]),
            query_used=f"sha256:{cypher_hash}",
        )

    # ── Private: queries ─────────────────────────────────────────────────────

    def _query_nodes(
        self,
        anchor_label: str,
        anchor_primary_key: str,
        anchor_primary_value: str,
        max_hops: int,
    ) -> Tuple[Optional[Any], List[Any]]:
        """
        Step 1: retrieve the anchor node and all nodes reachable within max_hops.

        anchor_label and max_hops are schema-validated before interpolation.
        anchor_primary_value is always passed as a Cypher parameter.
        """
        # Label comes from ANCHOR_LABELS (validated).
        # Property key comes from LABEL_PRIMARY_KEY (authoritative dict).
        # max_hops is an int capped at _HARD_MAX_HOPS.
        # anchor_primary_value is a parameter — no injection risk.
        pk = LABEL_PRIMARY_KEY[anchor_label]
        cypher = (
            f"MATCH (anchor:{anchor_label} {{`{pk}`: $val}}) "
            f"OPTIONAL MATCH (anchor)-[*1..{max_hops}]-(n) "
            "RETURN anchor, collect(DISTINCT n) AS neighbors"
        )
        params: Dict[str, Any] = {"val": anchor_primary_value}

        with self._session() as session:
            try:
                records = list(session.run(cypher, params))
            except Exception as exc:
                raise OntologyAdapterError(
                    f"Node neighborhood query failed for "
                    f"{anchor_label}:{anchor_primary_value}: {exc}"
                ) from exc

        if not records:
            return None, []

        rec = records[0]
        anchor_raw = rec.get("anchor")
        neighbors_raw: List[Any] = rec.get("neighbors") or []
        # Filter None entries that can arise from OPTIONAL MATCH with no matches
        neighbors_raw = [n for n in neighbors_raw if n is not None]
        return anchor_raw, neighbors_raw

    def _query_edges(
        self, node_ids: List[str], max_hops: int
    ) -> List[CanonEdge]:
        """
        Step 2: retrieve all directed edges between the given set of nodes.

        node_ids comes from CanonNode.neo4j_id values already validated by the
        driver — passed as a parameter list, never interpolated.
        """
        if not node_ids:
            return []

        cypher = (
            "MATCH (a)-[r]->(b) "
            "WHERE elementId(a) IN $ids AND elementId(b) IN $ids "
            "RETURN "
            "  elementId(r)          AS rel_id, "
            "  type(r)               AS rel_type, "
            "  elementId(startNode(r)) AS src, "
            "  elementId(endNode(r))   AS tgt, "
            "  properties(r)         AS props"
        )
        params: Dict[str, Any] = {"ids": node_ids}

        with self._session() as session:
            try:
                records = list(session.run(cypher, params))
            except Exception as exc:
                raise OntologyAdapterError(f"Edge query failed: {exc}") from exc

        edges: List[CanonEdge] = []
        seen: set = set()
        for rec in records:
            rel_type: str = rec["rel_type"]
            if rel_type not in RELATIONSHIP_TYPES:
                logger.warning(
                    "Relationship type '%s' not in authoritative schema — skipped.",
                    rel_type,
                )
                continue
            rel_id: str = str(rec["rel_id"])
            if rel_id in seen:
                continue
            seen.add(rel_id)
            edges.append(
                CanonEdge(
                    neo4j_id=rel_id,
                    type=rel_type,
                    start_node_id=str(rec["src"]),
                    end_node_id=str(rec["tgt"]),
                    properties=dict(rec["props"] or {}),
                    provenance=f"neo4j:neighborhood:hop≤{max_hops}",
                )
            )
        return edges

    # ── Private: builders ─────────────────────────────────────────────────────

    def _build_canon_nodes(
        self,
        anchor_node_raw: Any,
        anchor_label: str,
        anchor_primary_key: str,
        anchor_primary_value: str,
        neighbor_nodes_raw: List[Any],
        max_hops: int,
    ) -> List[CanonNode]:
        nodes: List[CanonNode] = []
        seen: set = set()

        # Anchor
        anchor_id = self._element_id(anchor_node_raw)
        anchor_labels = self._filter_labels(anchor_node_raw.labels, anchor_id)
        if anchor_labels and anchor_id not in seen:
            seen.add(anchor_id)
            nodes.append(
                CanonNode(
                    neo4j_id=anchor_id,
                    labels=anchor_labels,
                    primary_key=anchor_primary_key,
                    primary_value=anchor_primary_value,
                    properties=self._safe_properties(anchor_node_raw),
                    provenance=f"neo4j:anchor:{anchor_label}",
                )
            )

        # Neighbors
        for nb in neighbor_nodes_raw:
            nb_id = self._element_id(nb)
            if nb_id in seen:
                continue
            seen.add(nb_id)
            nb_labels = self._filter_labels(nb.labels, nb_id)
            if not nb_labels:
                continue
            pk = LABEL_PRIMARY_KEY.get(nb_labels[0])
            pv: Optional[str] = None
            if pk:
                raw_pv = nb.get(pk)
                pv = str(raw_pv) if raw_pv is not None else None
            nodes.append(
                CanonNode(
                    neo4j_id=nb_id,
                    labels=nb_labels,
                    primary_key=pk,
                    primary_value=pv,
                    properties=self._safe_properties(nb),
                    provenance=f"neo4j:neighborhood:hop≤{max_hops}",
                )
            )
        return nodes

    def _build_neighborhood_path(
        self,
        nodes: List[CanonNode],
        edges: List[CanonEdge],
        anchor_id: str,
        max_hops: int,
    ) -> OntologyPath:
        label_summary = ", ".join(sorted({lbl for n in nodes for lbl in n.labels}))
        rel_summary = ", ".join(sorted({e.type for e in edges}))
        desc = (
            f"Neighborhood(anchor_id={anchor_id}, hops≤{max_hops}): "
            f"labels=[{label_summary}], rels=[{rel_summary}]"
        )
        return OntologyPath(
            path_id=str(uuid.uuid4()),
            description=desc,
            node_sequence=[n.neo4j_id for n in nodes],
            rel_type_sequence=[e.type for e in edges],
            hop_count=max_hops,
            query_used="neighborhood-2step-apoc-free",
        )

    # ── Private: utilities ────────────────────────────────────────────────────

    @contextmanager
    def _session(self) -> Generator[Any, None, None]:
        session = self._driver.session()
        try:
            yield session
        finally:
            session.close()

    @staticmethod
    def _element_id(node_or_rel: Any) -> str:
        """
        Return the stable string element ID.

        neo4j driver ≥5.0: uses .element_id (string).
        Fallback for driver 4.x: str(node.id) (integer).
        """
        if hasattr(node_or_rel, "element_id"):
            return node_or_rel.element_id
        return str(node_or_rel.id)  # driver v4 fallback

    @staticmethod
    def _safe_properties(node_or_rel: Any) -> Dict[str, Any]:
        """
        Extract properties as a plain dict, redacting credential-like keys.
        This ensures credentials stored accidentally in Neo4j are never surfaced.
        """
        result: Dict[str, Any] = {}
        for k, v in node_or_rel.items():
            if k.lower() in _SENSITIVE_PROPERTY_KEYS:
                result[k] = "[REDACTED]"
            else:
                result[k] = v
        return result

    @staticmethod
    def _filter_labels(raw_labels: Any, node_id: str) -> List[str]:
        """
        Return only labels present in NODE_LABELS, warning on unknowns.
        """
        known = [lbl for lbl in raw_labels if lbl in NODE_LABELS]
        unknown = [lbl for lbl in raw_labels if lbl not in NODE_LABELS]
        if unknown:
            logger.warning(
                "Node %s has undeclared label(s) %s — skipped (ontology drift?).",
                node_id,
                unknown,
            )
        return known

    @staticmethod
    def _validate_anchor_label(label: str) -> None:
        if label not in ANCHOR_LABELS:
            raise OntologyAdapterError(
                f"Invalid anchor label '{label}'. "
                f"Must be one of: {sorted(ANCHOR_LABELS)}"
            )

    @staticmethod
    def _format_path_string(node_ids: List[str], rel_types: List[str]) -> str:
        if not rel_types:
            return node_ids[0] if node_ids else "(empty)"
        parts: List[str] = [node_ids[0]]
        for i, rel in enumerate(rel_types):
            parts.append(f"-[{rel}]->")
            if i + 1 < len(node_ids):
                parts.append(node_ids[i + 1])
        return "".join(parts)

    # ── Chain-specific backtracking traversals ────────────────────────────────

    # Relationship set definitions for each named backtracking chain.
    # These are used to filter traversal to chain-relevant edges only.
    _COMPLIANCE_CHAIN_RELS: frozenset = frozenset({
        "GENERATES", "ENFORCED_BY", "MANDATES", "IMPLEMENTED_BY",
        "HAS_TRANSFORMATION", "RUNS_JOB", "EXECUTES", "TYPICALLY_IMPLEMENTS",
        "OWNS_PIPELINE", "OWNS_JOB", "OWNS_SYSTEM", "OWNS_CONTROL",
    })
    _LINEAGE_CHAIN_RELS: frozenset = frozenset({
        "READS", "WRITES", "CONTAINS", "HAS_COLUMN",
        "DERIVED_FROM", "SOURCED_FROM", "USES_SCRIPT",
        "HAS_TRANSFORMATION", "DEPENDS_ON",
    })
    _CHANGE_PROVENANCE_RELS: frozenset = frozenset({
        "CHANGED_BY", "CREATES", "USES_SCRIPT",
    })
    _LOG_SCOPE_RELS: frozenset = frozenset({
        "LOGGED_IN",
    })

    def get_chain_neighborhood(
        self,
        anchor_label: str,
        anchor_primary_key: str,
        anchor_primary_value: str,
        chain_rel_types: List[str],
        max_hops: int = 5,
        chain_name: str = "custom",
    ) -> CanonGraph:
        """
        Retrieve a bounded neighborhood filtered to a specific set of relationship types.

        Used for named backtracking chains (compliance, lineage, change provenance,
        log scoping) to produce audit-traceable OntologyPaths per chain.

        chain_rel_types must be a subset of RELATIONSHIP_TYPES — unknown types are
        rejected to prevent schema drift.

        Returns an empty CanonGraph (anchor_neo4j_id="NOT_FOUND") when the anchor
        does not exist.  Returns a CanonGraph with only the anchor when no neighbors
        are reachable via the filtered relationship types.
        """
        self._validate_anchor_label(anchor_label)
        max_hops = min(max(1, max_hops), _HARD_MAX_HOPS)

        # Validate chain_rel_types against authoritative schema
        unknown = [r for r in chain_rel_types if r not in RELATIONSHIP_TYPES]
        if unknown:
            raise OntologyAdapterError(
                f"get_chain_neighborhood: unknown relationship types {unknown}. "
                "Only types in RELATIONSHIP_TYPES may be used."
            )

        pk = LABEL_PRIMARY_KEY[anchor_label]
        rel_filter = "|".join(chain_rel_types)  # safe: all validated above
        # Cypher: anchor_primary_value passed as $val — no injection risk.
        cypher = (
            f"MATCH (anchor:{anchor_label} {{`{pk}`: $val}}) "
            f"OPTIONAL MATCH (anchor)-[:{rel_filter}*1..{max_hops}]-(n) "
            "RETURN anchor, collect(DISTINCT n) AS neighbors"
        )
        params: Dict[str, Any] = {"val": anchor_primary_value}

        with self._session() as session:
            try:
                records = list(session.run(cypher, params))
            except Exception as exc:
                raise OntologyAdapterError(
                    f"Chain-neighborhood query failed for "
                    f"{anchor_label}:{anchor_primary_value} chain={chain_name}: {exc}"
                ) from exc

        if not records:
            return CanonGraph(
                anchor_neo4j_id="NOT_FOUND",
                anchor_label=anchor_label,
                anchor_primary_key=anchor_primary_key,
                anchor_primary_value=anchor_primary_value,
                max_hops=max_hops,
            )

        rec = records[0]
        anchor_raw = rec.get("anchor")
        if anchor_raw is None:
            return CanonGraph(
                anchor_neo4j_id="NOT_FOUND",
                anchor_label=anchor_label,
                anchor_primary_key=anchor_primary_key,
                anchor_primary_value=anchor_primary_value,
                max_hops=max_hops,
            )

        neighbors_raw: List[Any] = [n for n in (rec.get("neighbors") or []) if n is not None]
        anchor_id = self._element_id(anchor_raw)

        nodes = self._build_canon_nodes(
            anchor_node_raw=anchor_raw,
            anchor_label=anchor_label,
            anchor_primary_key=anchor_primary_key,
            anchor_primary_value=anchor_primary_value,
            neighbor_nodes_raw=neighbors_raw,
            max_hops=max_hops,
        )
        all_ids = [n.neo4j_id for n in nodes]
        edges = self._query_edges(all_ids, max_hops)
        # Keep only edges whose type is in the chain_rel_types set
        edges = [e for e in edges if e.type in chain_rel_types]

        label_summary = ", ".join(sorted({lbl for n in nodes for lbl in n.labels}))
        rel_summary = ", ".join(sorted({e.type for e in edges}))
        cypher_hash = hashlib.sha256(cypher.encode()).hexdigest()[:16]
        path = OntologyPath(
            path_id=str(uuid.uuid4()),
            description=(
                f"Chain:{chain_name}(anchor_id={anchor_id}, hops≤{max_hops}): "
                f"labels=[{label_summary}], rels=[{rel_summary}]"
            ),
            node_sequence=[n.neo4j_id for n in nodes],
            rel_type_sequence=[e.type for e in edges],
            hop_count=max_hops,
            query_used=f"sha256:{cypher_hash}",
        )

        return CanonGraph(
            anchor_neo4j_id=anchor_id,
            anchor_label=anchor_label,
            anchor_primary_key=anchor_primary_key,
            anchor_primary_value=anchor_primary_value,
            nodes=nodes,
            edges=edges,
            ontology_paths_used=[path],
            retrieved_at=datetime.utcnow(),
            max_hops=max_hops,
        )

    def get_compliance_chain(
        self,
        anchor_label: str,
        anchor_primary_key: str,
        anchor_primary_value: str,
        max_hops: int = 5,
    ) -> CanonGraph:
        """
        Backtrack compliance chain from anchor.

        Chain: Incident ← GENERATES ← Violation ← ENFORCED_BY ← Rule
               ← MANDATES ← Regulation; Rule ← IMPLEMENTED_BY ← Transformation
               ← HAS_TRANSFORMATION ← Pipeline ← RUNS_JOB ← System
        """
        return self.get_chain_neighborhood(
            anchor_label=anchor_label,
            anchor_primary_key=anchor_primary_key,
            anchor_primary_value=anchor_primary_value,
            chain_rel_types=sorted(self._COMPLIANCE_CHAIN_RELS),
            max_hops=max_hops,
            chain_name="compliance",
        )

    def get_lineage_chain(
        self,
        anchor_label: str,
        anchor_primary_key: str,
        anchor_primary_value: str,
        max_hops: int = 5,
    ) -> CanonGraph:
        """
        Traverse data lineage chain from anchor.

        Chain: Pipeline → USES_SCRIPT → Script → READS/WRITES → Table
               → HAS_COLUMN → Column → DERIVED_FROM → (upstream Column)
        """
        return self.get_chain_neighborhood(
            anchor_label=anchor_label,
            anchor_primary_key=anchor_primary_key,
            anchor_primary_value=anchor_primary_value,
            chain_rel_types=sorted(self._LINEAGE_CHAIN_RELS),
            max_hops=max_hops,
            chain_name="lineage",
        )

    def get_change_provenance_chain(
        self,
        anchor_label: str,
        anchor_primary_key: str,
        anchor_primary_value: str,
        max_hops: int = 4,
    ) -> CanonGraph:
        """
        Retrieve change provenance chain from anchor.

        Chain: Script → CHANGED_BY → CodeEvent; Pipeline → USES_SCRIPT → Script
        """
        return self.get_chain_neighborhood(
            anchor_label=anchor_label,
            anchor_primary_key=anchor_primary_key,
            anchor_primary_value=anchor_primary_value,
            chain_rel_types=sorted(self._CHANGE_PROVENANCE_RELS),
            max_hops=max_hops,
            chain_name="change_provenance",
        )

    def get_log_scope_chain(
        self,
        anchor_label: str,
        anchor_primary_key: str,
        anchor_primary_value: str,
        max_hops: int = 2,
    ) -> CanonGraph:
        """
        Retrieve log source scope for an operational anchor.

        Chain: System/Job/Pipeline → LOGGED_IN → LogSource
        """
        return self.get_chain_neighborhood(
            anchor_label=anchor_label,
            anchor_primary_key=anchor_primary_key,
            anchor_primary_value=anchor_primary_value,
            chain_rel_types=sorted(self._LOG_SCOPE_RELS),
            max_hops=max_hops,
            chain_name="log_scope",
        )

"""
causelink/agents/ontology_context.py

OntologyContextAgent — Phase D Agent 1.

Responsibilities:
  1. Call Neo4jOntologyAdapter.get_neighborhood() to load the bounded CanonGraph.
  2. Run four named backtracking chain traversals from the same anchor:
       - compliance chain   (Incident/Violation → Rule → Pipeline → System)
       - lineage chain      (Pipeline/Job → Script → Table → Column → DERIVED_FROM)
       - change provenance  (Script → CodeEvent)
       - log scope          (System/Job/Pipeline → LogSource)
  3. Validate the returned CanonGraph via ValidationGate (R6 + schema drift).
  4. Populate state.canon_graph, state.ontology_schema_snapshot, and
     state.ontology_paths_used.
  5. Transition state to INSUFFICIENT_EVIDENCE if anchor NOT_FOUND (R6).
  6. Append an AuditTraceEntry for every significant action.

This agent is SYNCHRONOUS — Neo4j queries are blocking I/O.
"""

from __future__ import annotations

import logging
from typing import List, Optional

from causelink.agents.base import CauseLinkAgent
from causelink.ontology.adapter import Neo4jOntologyAdapter, OntologyAdapterError, OntologyGap
from causelink.ontology.models import CanonGraph, OntologyPath
from causelink.ontology.schema import OntologySchemaSnapshot
from causelink.state.investigation import (
    InvestigationState,
    InvestigationStatus,
    MissingEvidence,
)
from causelink.validation.gates import ValidationGate

logger = logging.getLogger(__name__)


class OntologyContextAgent(CauseLinkAgent):
    """
    Loads the bounded ontology context for an investigation.

    Must be the FIRST agent in every pipeline run.
    No downstream agent may run until state.canon_graph is populated.
    """

    AGENT_TYPE = "ontology_context"

    # Anchor types that benefit from each chain traversal.
    _COMPLIANCE_ANCHORS = frozenset({"Incident", "Violation", "Pipeline", "Job", "System"})
    _LINEAGE_ANCHORS = frozenset({"Pipeline", "Job", "System"})
    _CHANGE_ANCHORS = frozenset({"Pipeline", "Job", "System", "Incident"})
    _LOG_SCOPE_ANCHORS = frozenset({"System", "Job", "Pipeline"})

    def __init__(
        self,
        adapter: Neo4jOntologyAdapter,
        gate: Optional[ValidationGate] = None,
    ) -> None:
        self.adapter = adapter
        self.gate = gate or ValidationGate()

    def run(self, state: InvestigationState) -> InvestigationState:
        """
        Load ontology context into the state.

        Side-effects on state:
          - state.status → ONTOLOGY_LOADING then EVIDENCE_COLLECTION (or INSUFFICIENT_EVIDENCE)
          - state.canon_graph populated
          - state.ontology_schema_snapshot populated
          - state.ontology_paths_used extended with up to 5 paths (general + 4 chains)
          - state.audit_trace extended
        """
        state.status = InvestigationStatus.ONTOLOGY_LOADING
        inv = state.investigation_input
        anchor = inv.anchor

        self._log(
            "Loading ontology context for %s:%s=%r (max_hops=%d)",
            anchor.anchor_type, anchor.anchor_primary_key,
            anchor.anchor_primary_value, inv.max_hops,
        )

        # ── Step 1: General neighborhood ─────────────────────────────────────
        try:
            graph = self.adapter.get_neighborhood(
                anchor_label=anchor.anchor_type,
                anchor_primary_key=anchor.anchor_primary_key,
                anchor_primary_value=anchor.anchor_primary_value,
                max_hops=inv.max_hops,
            )
        except OntologyAdapterError as exc:
            self._handle_adapter_error(state, str(exc))
            return state

        # Validate graph (R6 + schema drift)
        vr = self.gate.validate_canon_graph(graph)
        if not vr:
            reason = "; ".join(vr.violations)
            self._audit(
                state, "ontology_load",
                inputs_summary={"anchor": anchor.anchor_primary_value},
                decision=f"BLOCKED: {reason}",
            )
            state.add_missing_evidence(MissingEvidence(
                evidence_type="query_result",
                description=(
                    f"Anchor {anchor.anchor_type}:{anchor.anchor_primary_value} "
                    "not found in Neo4j ontology. "
                    "Add the anchor node before re-running this investigation."
                ),
                query_template=(
                    f"CREATE (:{anchor.anchor_type} "
                    f"{{`{anchor.anchor_primary_key}`: '{anchor.anchor_primary_value}'}})"
                ),
                blocking=True,
            ))
            state.transition_to_insufficient(reason)
            return state

        # ── Step 2: Chain-specific backtracking traversals ────────────────────
        chain_paths: List[OntologyPath] = []
        chain_counts: dict = {}

        if anchor.anchor_type in self._COMPLIANCE_ANCHORS:
            p = self._load_chain(state, "compliance", anchor)
            if p:
                chain_paths.append(p)
                chain_counts["compliance"] = len(p.node_sequence)

        if anchor.anchor_type in self._LINEAGE_ANCHORS:
            p = self._load_chain(state, "lineage", anchor)
            if p:
                chain_paths.append(p)
                chain_counts["lineage"] = len(p.node_sequence)

        if anchor.anchor_type in self._CHANGE_ANCHORS:
            p = self._load_chain(state, "change_provenance", anchor)
            if p:
                chain_paths.append(p)
                chain_counts["change_provenance"] = len(p.node_sequence)

        if anchor.anchor_type in self._LOG_SCOPE_ANCHORS:
            p = self._load_chain(state, "log_scope", anchor)
            if p:
                chain_paths.append(p)
                chain_counts["log_scope"] = len(p.node_sequence)

        # Merge chain paths into the graph's path list and state
        for cp in chain_paths:
            # Avoid duplicates (path_id is uuid, safe to append)
            graph.ontology_paths_used.append(cp)
            state.add_ontology_path(cp)

        # Also record the general neighborhood path
        if graph.ontology_paths_used:
            state.add_ontology_path(graph.ontology_paths_used[0])

        # ── Step 3: Commit graph to state ─────────────────────────────────────
        state.canon_graph = graph
        state.ontology_schema_snapshot = OntologySchemaSnapshot.current()
        state.status = InvestigationStatus.EVIDENCE_COLLECTION

        path_ids = [p.path_id for p in graph.ontology_paths_used]
        self._audit(
            state,
            action="ontology_load",
            inputs_summary={
                "anchor_type": anchor.anchor_type,
                "anchor_value": anchor.anchor_primary_value,
                "max_hops": inv.max_hops,
                "chains_loaded": list(chain_counts.keys()),
            },
            outputs_summary={
                "nodes": len(graph.nodes),
                "edges": len(graph.edges),
                "paths": len(graph.ontology_paths_used),
                "chain_node_counts": chain_counts,
            },
            ontology_paths_accessed=path_ids,
            decision=(
                f"Loaded {len(graph.nodes)} nodes, {len(graph.edges)} edges "
                f"across {len(chain_counts)} chains"
            ),
        )

        self._log(
            "Context loaded: %d nodes, %d edges, %d paths (%s)",
            len(graph.nodes), len(graph.edges),
            len(graph.ontology_paths_used),
            ", ".join(f"{k}:{v}" for k, v in chain_counts.items()),
        )

        return state

    # ── Private helpers ───────────────────────────────────────────────────────

    def _load_chain(
        self, state: InvestigationState, chain_name: str, anchor: object
    ) -> Optional[OntologyPath]:
        """
        Call the appropriate chain traversal on the adapter and return the path,
        or None on error (non-blocking — chain absences are not fatal).
        """
        try:
            if chain_name == "compliance":
                g = self.adapter.get_compliance_chain(
                    anchor.anchor_type, anchor.anchor_primary_key, anchor.anchor_primary_value
                )
            elif chain_name == "lineage":
                g = self.adapter.get_lineage_chain(
                    anchor.anchor_type, anchor.anchor_primary_key, anchor.anchor_primary_value
                )
            elif chain_name == "change_provenance":
                g = self.adapter.get_change_provenance_chain(
                    anchor.anchor_type, anchor.anchor_primary_key, anchor.anchor_primary_value
                )
            elif chain_name == "log_scope":
                g = self.adapter.get_log_scope_chain(
                    anchor.anchor_type, anchor.anchor_primary_key, anchor.anchor_primary_value
                )
            else:
                return None

            if g.anchor_neo4j_id == "NOT_FOUND" or not g.ontology_paths_used:
                return None
            return g.ontology_paths_used[0]

        except OntologyAdapterError as exc:
            self._warn("Chain '%s' traversal failed (non-fatal): %s", chain_name, exc)
            self._audit(
                state,
                action=f"chain_traversal:{chain_name}",
                decision=f"SKIPPED: {exc}",
                notes="Chain traversal error — investigation continues without this chain.",
            )
            return None

    def _handle_adapter_error(
        self, state: InvestigationState, message: str
    ) -> None:
        self._warn("Adapter error: %s", message)
        self._audit(
            state,
            action="ontology_load",
            decision=f"ERROR: {message}",
            notes="Neo4j adapter error — investigation cannot proceed.",
        )
        state.transition_to_insufficient(
            f"Neo4j adapter error: {message}. "
            "Verify NEO4J_URI, NEO4J_USER, NEO4J_PASSWORD and Neo4j connectivity."
        )

"""
causelink/agents/causal_engine.py

CausalEngineAgent — Phase D Agent 4 / Phase F.

Responsibilities:
  1. For each PROPOSED hypothesis in state, propose one CausalEdge per involved
     node pair (cause→effect) drawn from the CanonGraph.
  2. Call adapter.validate_shortest_path() for each edge to structurally validate
     the link in Neo4j.
  3. Set edge.structural_path_validated=True and edge.ontology_path_id if a path
     is found; otherwise set status=REJECTED_NO_ONTOLOGY_PATH.
  4. Validate each edge with ValidationGate (R1, R3, R4) before adding to state.
  5. Promote hypothesis status to SUPPORTED when at least one of its edges is VALID.
  6. Append AuditTraceEntry for every validation result.

The adapter may be None (test mode) — in that case, edges are left PENDING
without structural validation, which is acceptable in test fixtures.
"""

from __future__ import annotations

import logging
from typing import List, Optional, Tuple

from causelink.agents.base import CauseLinkAgent
from causelink.ontology.adapter import Neo4jOntologyAdapter, OntologyAdapterError
from causelink.ontology.models import OntologyPath
from causelink.state.investigation import (
    CausalEdge,
    CausalEdgeStatus,
    Hypothesis,
    HypothesisStatus,
    InvestigationState,
    InvestigationStatus,
)
from causelink.validation.gates import ValidationGate

logger = logging.getLogger(__name__)


class CausalEngineAgent(CauseLinkAgent):
    """
    Builds and structurally validates the causal DAG.

    Edge generation strategy:
      - For a hypothesis with N involved_node_ids, create edges for all
        adjacent pairs that have a direct CanonEdge in the graph
        (not all N² combinations — only structurally present edges).
    """

    AGENT_TYPE = "causal_engine"

    def __init__(
        self,
        adapter: Optional[Neo4jOntologyAdapter] = None,
        gate: Optional[ValidationGate] = None,
    ) -> None:
        self.adapter = adapter
        self.gate = gate or ValidationGate()

    def run(self, state: InvestigationState) -> InvestigationState:
        """
        Build causal DAG edges from hypotheses.

        Side-effects on state:
          - state.causal_graph_edges extended
          - state.causal_graph_node_ids extended
          - hypothesis.status may advance to SUPPORTED
          - state.ontology_paths_used extended with shortest-path results
          - state.audit_trace extended
          - state.status → CAUSAL_SCORING
        """
        if state.canon_graph is None:
            raise ValueError("CausalEngineAgent requires state.canon_graph")

        state.status = InvestigationStatus.CAUSAL_SCORING
        graph = state.canon_graph

        total_edges = 0
        valid_edges = 0
        rejected_edges = 0

        for hypothesis in state.hypotheses:
            if hypothesis.status not in (
                HypothesisStatus.PROPOSED, HypothesisStatus.SUPPORTED
            ):
                continue

            # Derive candidate edges from adjacent node pairs in the CanonGraph
            candidate_pairs = self._candidate_pairs(hypothesis, state)
            hyp_valid = 0

            for cause_id, effect_id, mechanism in candidate_pairs:
                total_edges += 1

                # Structurally validate via Neo4j shortestPath (if adapter available)
                path, validated = self._validate_path(
                    cause_id, effect_id, state.investigation_input.max_hops, state
                )

                path_id: Optional[str] = None
                if path is not None:
                    state.add_ontology_path(path)
                    path_id = path.path_id

                edge = CausalEdge(
                    cause_node_id=cause_id,
                    effect_node_id=effect_id,
                    mechanism=mechanism,
                    evidence_object_ids=list(hypothesis.evidence_object_ids),
                    ontology_path_id=path_id,
                    temporal_order_validated=False,  # Phase F extension
                    structural_path_validated=validated,
                    confidence=(
                        hypothesis.confidence * 0.9 if validated else hypothesis.confidence * 0.4
                    ),
                    status=(
                        CausalEdgeStatus.VALID if validated
                        else CausalEdgeStatus.REJECTED_NO_ONTOLOGY_PATH
                        if path is None and self.adapter is not None
                        else CausalEdgeStatus.PENDING
                    ),
                )

                # Gate check
                vr = self.gate.validate_causal_edge(edge, state)
                if vr:
                    state.add_causal_edge(edge)
                    if edge.status == CausalEdgeStatus.VALID:
                        valid_edges += 1
                        hyp_valid += 1
                    self._audit(
                        state,
                        action="causal_edge_added",
                        inputs_summary={
                            "cause": cause_id, "effect": effect_id,
                            "validated": validated,
                        },
                        outputs_summary={"edge_id": edge.edge_id, "status": edge.status.value},
                        ontology_paths_accessed=[path_id] if path_id else [],
                        evidence_ids_accessed=edge.evidence_object_ids,
                        decision=f"Edge status: {edge.status.value}",
                    )
                else:
                    rejected_edges += 1
                    self._warn(
                        "CausalEdge gate rejected: %s", vr.violations
                    )
                    self._audit(
                        state,
                        action="causal_edge_rejected",
                        inputs_summary={"cause": cause_id, "effect": effect_id},
                        decision=f"GATE_REJECTED: {'; '.join(vr.violations)}",
                    )

            # Promote hypothesis if at least one valid edge
            if hyp_valid > 0 and hypothesis.status == HypothesisStatus.PROPOSED:
                # Directly mutate via model copy (Pydantic v2: model_copy)
                idx = state.hypotheses.index(hypothesis)
                state.hypotheses[idx] = hypothesis.model_copy(
                    update={"status": HypothesisStatus.SUPPORTED}
                )

        self._audit(
            state,
            action="causal_dag_built",
            outputs_summary={
                "total_edges": total_edges,
                "valid_edges": valid_edges,
                "rejected_edges": rejected_edges,
            },
            decision=f"DAG: {valid_edges}/{total_edges} edges valid",
        )

        self._log(
            "Causal DAG: %d total, %d valid, %d rejected",
            total_edges, valid_edges, rejected_edges,
        )
        return state

    # ── Helpers ───────────────────────────────────────────────────────────────

    def _candidate_pairs(
        self, hypothesis: Hypothesis, state: InvestigationState
    ) -> List[Tuple[str, str, str]]:
        """
        Return (cause_id, effect_id, mechanism) tuples for the hypothesis.

        Only produce an edge when there is a direct CanonEdge between the nodes
        in the CanonGraph.  Never fabricate edges between unconnected nodes.
        """
        graph = state.canon_graph
        node_ids = hypothesis.involved_node_ids
        pairs: List[Tuple[str, str, str]] = []
        seen: set = set()

        for edge in graph.edges:
            if (
                edge.start_node_id in node_ids
                and edge.end_node_id in node_ids
                and (edge.start_node_id, edge.end_node_id) not in seen
            ):
                seen.add((edge.start_node_id, edge.end_node_id))
                start_node = graph.get_node(edge.start_node_id)
                end_node = graph.get_node(edge.end_node_id)
                mechanism = (
                    f"{edge.type}: "
                    f"{start_node.labels[0] if start_node else edge.start_node_id}"
                    f" → "
                    f"{end_node.labels[0] if end_node else edge.end_node_id}"
                )
                pairs.append((edge.start_node_id, edge.end_node_id, mechanism))

        return pairs

    def _validate_path(
        self,
        start_id: str,
        end_id: str,
        max_hops: int,
        state: InvestigationState,
    ) -> Tuple[Optional[OntologyPath], bool]:
        """
        Call adapter.validate_shortest_path().

        Returns (OntologyPath, True) on success, (None, False) if no path found,
        or (None, False) on adapter error (non-fatal).
        """
        if self.adapter is None:
            # Test mode — no Neo4j available; edges remain PENDING
            return None, False

        try:
            path = self.adapter.validate_shortest_path(
                start_node_id=start_id,
                end_node_id=end_id,
                max_hops=max_hops,
            )
            return path, path is not None
        except OntologyAdapterError as exc:
            self._warn("shortest_path validation failed (non-fatal): %s", exc)
            self._audit(
                state,
                action="shortest_path_error",
                inputs_summary={"start": start_id, "end": end_id},
                decision=f"ERROR: {exc}",
                notes="Structural path validation skipped — edge left PENDING.",
            )
            return None, False

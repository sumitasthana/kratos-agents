"""
causelink/agents/ranker.py

RankerAgent — Phase D Agent 5 / Phase F (Scoring).

Responsibilities:
  1. Build RootCauseCandidate objects from SUPPORTED/PROBABLE hypotheses.
  2. Score each candidate using the E×T×D×H composite formula:
       composite = E*0.40 + T*0.25 + D*0.20 + H*0.15
       where:
         E = evidence_score       (evidence count × reliability / max_possible)
         T = temporal_score       (fraction of edges with temporal_order_validated=True)
         D = structural_depth_score (average hop_count of validating OntologyPaths, normalised)
         H = hypothesis_alignment_score (fraction of candidate's hypotheses that are SUPPORTED+)
  3. Apply ValidationGate.validate_root_cause_candidate() before setting.
  4. Call state.set_root_cause_final() on the highest-scoring passing candidate.
  5. If no candidate reaches the threshold, call state.transition_to_insufficient().
  6. Append full audit trace.

Only THIS agent may set state.root_cause_final (enforced by ValidationGate R5).
"""

from __future__ import annotations

import logging
import uuid
from typing import List, Optional, Tuple

from causelink.agents.base import CauseLinkAgent
from causelink.state.investigation import (
    CausalEdge,
    CausalEdgeStatus,
    Hypothesis,
    HypothesisStatus,
    InvestigationState,
    InvestigationStatus,
    RootCauseCandidate,
)
from causelink.validation.gates import ValidationGate

logger = logging.getLogger(__name__)

_E_WEIGHT = 0.40
_T_WEIGHT = 0.25
_D_WEIGHT = 0.20
_H_WEIGHT = 0.15
_MAX_STRUCTURAL_HOPS = 6  # normalisation ceiling


class RankerAgent(CauseLinkAgent):
    """
    Scores root cause candidates using the E×T×D×H formula and confirms the winner.

    Only this agent calls state.set_root_cause_final().
    """

    AGENT_TYPE = "ranker"

    def __init__(self, gate: Optional[ValidationGate] = None) -> None:
        self.gate = gate or ValidationGate()

    def run(self, state: InvestigationState) -> InvestigationState:
        """
        Score candidates and confirm the root cause.

        Side-effects on state:
          - state.root_cause_candidates extended
          - state.root_cause_final set if threshold reached
          - state.status → COMPLETED or INSUFFICIENT_EVIDENCE
          - state.audit_trace extended
        """
        if state.canon_graph is None:
            raise ValueError("RankerAgent requires state.canon_graph")

        # Collect hypotheses eligible for ranking
        eligible = [
            h for h in state.hypotheses
            if h.status in (
                HypothesisStatus.PROPOSED,
                HypothesisStatus.SUPPORTED,
                HypothesisStatus.PROBABLE,
            )
        ]

        if not eligible:
            reason = (
                "No eligible hypotheses to rank. "
                "All hypotheses are REFUTED or none were generated."
            )
            state.transition_to_insufficient(reason)
            self._audit(state, "ranking_complete", decision=f"INSUFFICIENT: {reason}")
            return state

        # Build and score candidates
        candidates: List[Tuple[RootCauseCandidate, float]] = []

        for hyp in eligible:
            candidate = self._build_candidate(hyp, state)
            vr = self.gate.validate_root_cause_candidate(
                candidate=candidate,
                state=state,
                calling_agent=self.AGENT_TYPE,
                ranker_agent_type=self.AGENT_TYPE,
            )
            if not vr:
                self._warn(
                    "Candidate for hypothesis %s rejected: %s",
                    hyp.hypothesis_id, vr.violations,
                )
                self._audit(
                    state,
                    action="candidate_rejected",
                    inputs_summary={"hypothesis_id": hyp.hypothesis_id},
                    decision=f"GATE_REJECTED: {'; '.join(vr.violations)}",
                )
                continue

            state.root_cause_candidates.append(candidate)
            state.updated_at = __import__("datetime").datetime.utcnow()
            candidates.append((candidate, candidate.composite_score))

            self._audit(
                state,
                action="candidate_scored",
                inputs_summary={"hypothesis_id": hyp.hypothesis_id},
                outputs_summary={
                    "candidate_id": candidate.candidate_id,
                    "composite_score": candidate.composite_score,
                    "E": candidate.evidence_score,
                    "T": candidate.temporal_score,
                    "D": candidate.structural_depth_score,
                    "H": candidate.hypothesis_alignment_score,
                },
                decision=f"composite={candidate.composite_score:.3f} status={candidate.status.value}",
            )

        if not candidates:
            state.transition_to_insufficient(
                "All candidates rejected by ValidationGate."
            )
            self._audit(state, "ranking_complete", decision="INSUFFICIENT: all candidates rejected")
            return state

        # Sort descending by score; pick the best
        candidates.sort(key=lambda t: t[1], reverse=True)
        best_candidate, best_score = candidates[0]

        self._log(
            "Best candidate: %s score=%.3f status=%s",
            best_candidate.candidate_id, best_score, best_candidate.status.value,
        )

        threshold = state.investigation_input.confidence_threshold
        if best_score >= threshold:
            try:
                state.set_root_cause_final(best_candidate, ranker_agent_type=self.AGENT_TYPE)
                self._audit(
                    state,
                    action="root_cause_confirmed",
                    outputs_summary={
                        "candidate_id": best_candidate.candidate_id,
                        "score": best_score,
                    },
                    decision=f"CONFIRMED at score={best_score:.3f} ≥ threshold={threshold}",
                )
            except ValueError as exc:
                # Threshold met but blocking evidence remains
                state.transition_to_insufficient(str(exc))
                self._audit(
                    state, "ranking_complete",
                    decision=f"BLOCKED: {exc}",
                )
        else:
            state.transition_to_insufficient(
                f"Best composite_score={best_score:.3f} below threshold={threshold}. "
                "Collect additional evidence to increase confidence."
            )
            self._audit(
                state, "ranking_complete",
                outputs_summary={"best_score": best_score, "threshold": threshold},
                decision="INSUFFICIENT: below threshold",
            )

        self._log(
            "Ranking complete: %d candidates | status=%s",
            len(candidates), state.status.value,
        )
        return state

    # ── Scoring helpers ───────────────────────────────────────────────────────

    def _build_candidate(
        self, hypothesis: Hypothesis, state: InvestigationState
    ) -> RootCauseCandidate:
        """Build and score a RootCauseCandidate from a hypothesis."""
        # Identify causal edges that belong to this hypothesis
        hyp_edge_ids = self._edges_for_hypothesis(hypothesis, state)
        hyp_edges = [
            e for e in state.causal_graph_edges
            if e.edge_id in hyp_edge_ids
        ]

        e_score = self._evidence_score(hypothesis, state)
        t_score = self._temporal_score(hyp_edges)
        d_score = self._structural_depth_score(hyp_edges, state)
        h_score = self._hypothesis_alignment_score(hypothesis, state)

        composite = round(
            e_score * _E_WEIGHT
            + t_score * _T_WEIGHT
            + d_score * _D_WEIGHT
            + h_score * _H_WEIGHT,
            4,
        )

        # The anchor node is the primary root cause node
        node_id = (
            hypothesis.involved_node_ids[0]
            if hypothesis.involved_node_ids
            else state.canon_graph.anchor_neo4j_id
        )

        return RootCauseCandidate(
            candidate_id=str(uuid.uuid4()),
            node_id=node_id,
            description=hypothesis.description,
            hypothesis_ids=[hypothesis.hypothesis_id],
            causal_edge_ids=hyp_edge_ids,
            evidence_score=e_score,
            temporal_score=t_score,
            structural_depth_score=d_score,
            hypothesis_alignment_score=h_score,
            composite_score=composite,
            missing_evidence_ids=[m.missing_id for m in state.missing_evidence],
        )

    def _edges_for_hypothesis(
        self, hypothesis: Hypothesis, state: InvestigationState
    ) -> List[str]:
        """Return edge_ids whose both endpoints are in the hypothesis's involved_node_ids."""
        node_set = set(hypothesis.involved_node_ids)
        return [
            e.edge_id
            for e in state.causal_graph_edges
            if e.cause_node_id in node_set and e.effect_node_id in node_set
        ]

    def _evidence_score(
        self, hypothesis: Hypothesis, state: InvestigationState
    ) -> float:
        """
        E = weighted sum of reliability scores of cited evidence objects,
        normalised to 0–1.
        """
        if not hypothesis.evidence_object_ids:
            return 0.0
        ev_map = {ev.evidence_id: ev for ev in state.evidence_objects if hasattr(ev, "evidence_id")}
        total = 0.0
        count = 0
        for eid in hypothesis.evidence_object_ids:
            ev = ev_map.get(eid)
            if ev and hasattr(ev, "reliability"):
                total += ev.reliability
                count += 1
        if count == 0:
            return 0.0
        return min(total / count, 1.0)

    @staticmethod
    def _temporal_score(edges: List[CausalEdge]) -> float:
        """T = fraction of edges with temporal_order_validated=True."""
        if not edges:
            return 0.0
        validated = sum(1 for e in edges if e.temporal_order_validated)
        return validated / len(edges)

    def _structural_depth_score(
        self, edges: List[CausalEdge], state: InvestigationState
    ) -> float:
        """
        D = average hop_count of the OntologyPaths validating these edges,
        normalised by _MAX_STRUCTURAL_HOPS.
        Deeper structural paths → higher confidence in root cause distance.
        """
        if not edges:
            return 0.0
        path_map = {
            p.path_id: p
            for p in state.ontology_paths_used
        }
        if state.canon_graph:
            for p in state.canon_graph.ontology_paths_used:
                path_map[p.path_id] = p

        hop_counts = []
        for edge in edges:
            if edge.ontology_path_id and edge.ontology_path_id in path_map:
                hop_counts.append(path_map[edge.ontology_path_id].hop_count)
        if not hop_counts:
            return 0.0
        avg_hops = sum(hop_counts) / len(hop_counts)
        # Normalise: 1 hop → 1/_MAX, 6 hops → 1.0
        return min(avg_hops / _MAX_STRUCTURAL_HOPS, 1.0)

    @staticmethod
    def _hypothesis_alignment_score(
        hypothesis: Hypothesis, state: InvestigationState
    ) -> float:
        """
        H = fraction of all hypotheses that are SUPPORTED or above.
        A single well-supported hypothesis in a sea of PROPOSED ones scores lower.
        """
        if not state.hypotheses:
            return 0.0
        supported = sum(
            1 for h in state.hypotheses
            if h.status in (
                HypothesisStatus.SUPPORTED,
                HypothesisStatus.PROBABLE,
                HypothesisStatus.CONFIRMED,
            )
        )
        # Also weight by whether THIS hypothesis is supported
        this_supported = hypothesis.status in (
            HypothesisStatus.SUPPORTED,
            HypothesisStatus.PROBABLE,
            HypothesisStatus.CONFIRMED,
        )
        base = supported / len(state.hypotheses)
        return min(base + (0.10 if this_supported else 0.0), 1.0)

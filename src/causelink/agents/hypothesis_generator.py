"""
causelink/agents/hypothesis_generator.py

HypothesisGeneratorAgent — Phase D Agent 3 (Pattern-first).

Responsibilities:
  1. Use HypothesisPatternLibrary.match() to find all satisfied patterns.
  2. For each satisfied pattern, generate exactly one Hypothesis.
     - Structure (node IDs, rel types, evidence IDs) comes from the pattern.
     - Description text is filled from template_vars (no LLM structural fabrication).
  3. Validate each hypothesis with ValidationGate before adding to state.
  4. Log rejected hypotheses as AuditTraceEntries (not silently dropped).
  5. If no patterns are satisfied, add MissingEvidence for each unmet requirement.

NON-NEGOTIABLE: A Hypothesis may NEVER be generated without a satisfied pattern.
LLM (if used) fills only description text — it never determines structural shape.
"""

from __future__ import annotations

import logging
import uuid
from typing import List, Optional

from causelink.agents.base import CauseLinkAgent
from causelink.patterns.library import HypothesisPatternLibrary, PatternMatchResult
from causelink.state.investigation import (
    Hypothesis,
    HypothesisStatus,
    InvestigationState,
    InvestigationStatus,
    MissingEvidence,
)
from causelink.validation.gates import ValidationGate

logger = logging.getLogger(__name__)


class HypothesisGeneratorAgent(CauseLinkAgent):
    """
    Generates hypotheses from the pattern library — PATTERN-FIRST, not freeform.

    Every hypothesis references:
      - pattern_id matching the firing pattern
      - involved_node_ids from the CanonGraph
      - evidence_object_ids from collected evidence
    """

    AGENT_TYPE = "hypothesis_generator"

    def __init__(
        self,
        pattern_library: Optional[HypothesisPatternLibrary] = None,
        gate: Optional[ValidationGate] = None,
    ) -> None:
        self.pattern_library = pattern_library or HypothesisPatternLibrary()
        self.gate = gate or ValidationGate()

    def run(self, state: InvestigationState) -> InvestigationState:
        """
        Generate pattern-backed hypotheses into the state.

        Side-effects on state:
          - state.hypotheses extended with validated hypotheses
          - state.missing_evidence extended if no patterns satisfied
          - state.audit_trace extended
          - state.status → HYPOTHESIS_GENERATION while running
        """
        if state.canon_graph is None:
            raise ValueError(
                "HypothesisGeneratorAgent requires canon_graph. "
                "Run OntologyContextAgent first."
            )

        state.status = InvestigationStatus.HYPOTHESIS_GENERATION
        graph = state.canon_graph
        anchor_type = state.investigation_input.anchor.anchor_type

        # ── Pattern matching ─────────────────────────────────────────────────
        evidence_objects = list(state.evidence_objects)
        match_results: List[PatternMatchResult] = self.pattern_library.match(
            graph=graph,
            evidence_objects=evidence_objects,
            anchor_type=anchor_type,
        )

        satisfied = [r for r in match_results if r.satisfied]
        unsatisfied = [r for r in match_results if not r.satisfied]

        self._log(
            "%d/%d patterns satisfied for anchor_type=%s",
            len(satisfied), len(match_results), anchor_type,
        )

        generated = 0
        rejected = 0

        # ── Generate hypotheses for satisfied patterns ────────────────────────
        for result in satisfied:
            pattern = result.pattern
            description = self._render_description(pattern.description_template, result.template_vars)

            hypothesis = Hypothesis(
                hypothesis_id=str(uuid.uuid4()),
                description=description,
                involved_node_ids=result.matched_node_ids,
                evidence_object_ids=result.matched_evidence_ids,
                ontology_path_ids=self._extract_path_ids(state, result),
                status=HypothesisStatus.PROPOSED,
                confidence=pattern.confidence_prior,
                generated_by=self.AGENT_TYPE,
                pattern_id=pattern.pattern_id,
            )

            # Validate before adding (R1, R2, R3)
            vr = self.gate.validate_hypothesis(hypothesis, state)
            if vr:
                try:
                    state.add_hypothesis(hypothesis)
                    generated += 1
                    self._audit(
                        state,
                        action="hypothesis_proposed",
                        inputs_summary={"pattern_id": pattern.pattern_id},
                        outputs_summary={"hypothesis_id": hypothesis.hypothesis_id},
                        ontology_paths_accessed=hypothesis.ontology_path_ids,
                        evidence_ids_accessed=hypothesis.evidence_object_ids,
                        decision=(
                            f"ACCEPTED: pattern={pattern.pattern_id} "
                            f"prior={pattern.confidence_prior}"
                        ),
                    )
                except ValueError as exc:
                    rejected += 1
                    self._warn("Hypothesis rejected after validation: %s", exc)
                    self._audit(
                        state,
                        action="hypothesis_rejected",
                        inputs_summary={"pattern_id": pattern.pattern_id},
                        decision=f"REJECTED: {exc}",
                    )
            else:
                rejected += 1
                self._warn(
                    "Hypothesis for pattern %s failed gate: %s",
                    pattern.pattern_id, vr.violations,
                )
                self._audit(
                    state,
                    action="hypothesis_rejected",
                    inputs_summary={"pattern_id": pattern.pattern_id},
                    decision=f"GATE_REJECTED: {'; '.join(vr.violations)}",
                )

        # ── Record missing evidence for unmet patterns ────────────────────────
        # Only record once per unmet requirement type (avoid spam)
        recorded_unmet: set = set()
        for result in unsatisfied:
            for lbl in result.unmet_node_labels:
                if lbl not in recorded_unmet:
                    recorded_unmet.add(lbl)
                    state.add_missing_evidence(MissingEvidence(
                        evidence_type="query_result",
                        description=(
                            f"Pattern '{result.pattern.pattern_id}' requires node "
                            f"label '{lbl}' which is absent from the CanonGraph. "
                            "Expand max_hops or add this node to the ontology."
                        ),
                        query_template=(
                            f"MATCH (n:{lbl}) WHERE n IN neighborhood({{}}) RETURN n"
                        ),
                        blocking=False,
                    ))
            for ev_type in result.unmet_evidence_types:
                if ev_type not in recorded_unmet:
                    recorded_unmet.add(ev_type)
                    state.add_missing_evidence(MissingEvidence(
                        evidence_type=ev_type,
                        description=(
                            f"Pattern '{result.pattern.pattern_id}' requires "
                            f"evidence of type '{ev_type}' which was not collected. "
                        ),
                        query_template=f"collect(evidence_type={ev_type}, entity_ids={{entity_ids}})",
                        blocking=False,
                    ))

        # ── If no hypotheses at all — mark insufficient ───────────────────────
        if generated == 0:
            reason = (
                "No satisfied hypothesis patterns found. "
                f"Checked {len(match_results)} pattern(s). "
                "Collect additional evidence or expand the ontology neighborhood."
            )
            state.add_missing_evidence(MissingEvidence(
                evidence_type="query_result",
                description=reason,
                blocking=True,
            ))
            self._audit(
                state,
                action="hypothesis_generation_complete",
                outputs_summary={"generated": 0, "rejected": rejected},
                decision="BLOCKED: no satisfied patterns",
            )
        else:
            self._audit(
                state,
                action="hypothesis_generation_complete",
                outputs_summary={"generated": generated, "rejected": rejected},
                decision=f"Generated {generated} hypothesis/hypotheses from {len(satisfied)} pattern(s)",
            )

        self._log(
            "Done: generated=%d, rejected=%d, unsatisfied_patterns=%d",
            generated, rejected, len(unsatisfied),
        )
        return state

    # ── Helpers ───────────────────────────────────────────────────────────────

    @staticmethod
    def _render_description(template: str, template_vars: dict) -> str:
        """Fill description template with available vars; leave missing vars as-is."""
        try:
            return template.format(**template_vars)
        except (KeyError, IndexError):
            # partial substitution — acceptable
            result = template
            for k, v in template_vars.items():
                result = result.replace(f"{{{k}}}", str(v))
            return result

    @staticmethod
    def _extract_path_ids(
        state: InvestigationState, result: PatternMatchResult
    ) -> List[str]:
        """
        Find OntologyPaths in state whose chain aligns with the pattern's chain.

        Returns a list of path_ids to cite in the Hypothesis.
        """
        chain = result.pattern.chain
        path_ids = []
        for path in state.ontology_paths_used:
            if chain in path.description.lower():
                path_ids.append(path.path_id)
        # Also include paths from canon_graph
        if state.canon_graph:
            for path in state.canon_graph.ontology_paths_used:
                if path.path_id not in path_ids and chain in path.description.lower():
                    path_ids.append(path.path_id)
        return path_ids

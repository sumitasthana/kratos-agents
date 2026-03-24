"""
src/demo/services/confidence_calculator.py

ConfidenceCalculator — pure E×T×D×H composite confidence formula.

Weights are fixed per the platform specification and must never change:
  E (evidence score)            0.40
  T (temporal order score)       0.25
  D (structural depth score)     0.20
  H (hypothesis alignment score) 0.15

The composite threshold for CONFIRMED status in demo mode is 0.70.

This class is stateless and fully unit-testable without any mocks.

Usage::

    calc = ConfidenceCalculator()
    score = calc.compute(evidence=0.92, temporal=0.90, depth=0.85, hypothesis=0.90)
    # → 0.8965
"""

from __future__ import annotations

from dataclasses import dataclass

# Fixed weights — must never be modified
EVIDENCE_WEIGHT:    float = 0.40
TEMPORAL_WEIGHT:    float = 0.25
DEPTH_WEIGHT:       float = 0.20
HYPOTHESIS_WEIGHT:  float = 0.15

# Threshold for CONFIRMED status in demo mode
# (lower than production 0.80 because demo evidence is authoritative/hardcoded)
CONFIRMATION_THRESHOLD: float = 0.70


@dataclass(frozen=True)
class ConfidenceBreakdown:
    """Detailed per-dimension confidence breakdown."""

    evidence_score:    float
    temporal_score:    float
    depth_score:       float
    hypothesis_score:  float
    composite_score:   float

    def to_dict(self) -> dict:
        return {
            "evidence_score":            round(self.evidence_score, 4),
            "temporal_score":            round(self.temporal_score, 4),
            "depth_score":               round(self.depth_score, 4),
            "hypothesis_alignment_score": round(self.hypothesis_score, 4),
            "composite_score":           round(self.composite_score, 4),
            "weights": {
                "evidence":   EVIDENCE_WEIGHT,
                "temporal":   TEMPORAL_WEIGHT,
                "depth":      DEPTH_WEIGHT,
                "hypothesis": HYPOTHESIS_WEIGHT,
            },
        }


class ConfidenceCalculator:
    """
    Pure composite confidence calculator.

    No side effects, no I/O, no state.
    All inputs are [0.0, 1.0] floats; output is clamped to [0.0, 1.0].
    """

    def compute(
        self,
        evidence: float,
        temporal: float,
        depth: float,
        hypothesis: float,
    ) -> float:
        """
        Compute the weighted composite confidence score.

        Args:
            evidence:   E — fraction of relevant evidence items matched
            temporal:   T — temporal ordering confidence (cause before effect)
            depth:      D — structural depth in the ontology path
            hypothesis: H — hypothesis pattern alignment confidence

        Returns:
            Composite score in [0.0, 1.0].
        """
        _validate_score("evidence", evidence)
        _validate_score("temporal", temporal)
        _validate_score("depth", depth)
        _validate_score("hypothesis", hypothesis)

        composite = (
            EVIDENCE_WEIGHT   * evidence
            + TEMPORAL_WEIGHT   * temporal
            + DEPTH_WEIGHT      * depth
            + HYPOTHESIS_WEIGHT * hypothesis
        )
        return min(max(composite, 0.0), 1.0)

    def compute_with_breakdown(
        self,
        evidence: float,
        temporal: float,
        depth: float,
        hypothesis: float,
    ) -> ConfidenceBreakdown:
        """
        Compute the composite score and return a full breakdown.

        Useful for the ConfidenceGauge frontend component.
        """
        score = self.compute(evidence, temporal, depth, hypothesis)
        return ConfidenceBreakdown(
            evidence_score=evidence,
            temporal_score=temporal,
            depth_score=depth,
            hypothesis_score=hypothesis,
            composite_score=score,
        )

    def is_confirmed(self, score: float) -> bool:
        """Return True when *score* meets the CONFIRMATION_THRESHOLD."""
        return score >= CONFIRMATION_THRESHOLD


def _validate_score(name: str, value: float) -> None:
    if not (0.0 <= value <= 1.0):
        raise ValueError(
            f"ConfidenceCalculator: {name}={value!r} is out of range [0.0, 1.0]"
        )

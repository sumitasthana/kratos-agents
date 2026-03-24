"""
tests/demo/test_confidence_calculator.py

Unit tests for ConfidenceCalculator — pure function, no mocks needed.
"""

from __future__ import annotations

import pytest

from demo.services.confidence_calculator import (
    CONFIRMATION_THRESHOLD,
    DEPTH_WEIGHT,
    EVIDENCE_WEIGHT,
    HYPOTHESIS_WEIGHT,
    TEMPORAL_WEIGHT,
    ConfidenceBreakdown,
    ConfidenceCalculator,
)


@pytest.fixture
def calc() -> ConfidenceCalculator:
    return ConfidenceCalculator()


class TestWeights:
    def test_weights_sum_to_one(self) -> None:
        total = EVIDENCE_WEIGHT + TEMPORAL_WEIGHT + DEPTH_WEIGHT + HYPOTHESIS_WEIGHT
        assert abs(total - 1.0) < 1e-9, f"Weights sum to {total}, not 1.0"

    def test_evidence_weight(self) -> None:
        assert EVIDENCE_WEIGHT == pytest.approx(0.40)

    def test_temporal_weight(self) -> None:
        assert TEMPORAL_WEIGHT == pytest.approx(0.25)

    def test_depth_weight(self) -> None:
        assert DEPTH_WEIGHT == pytest.approx(0.20)

    def test_hypothesis_weight(self) -> None:
        assert HYPOTHESIS_WEIGHT == pytest.approx(0.15)

    def test_confirmation_threshold(self) -> None:
        assert CONFIRMATION_THRESHOLD == pytest.approx(0.70)


class TestCompute:
    def test_all_zeros(self, calc: ConfidenceCalculator) -> None:
        assert calc.compute(0.0, 0.0, 0.0, 0.0) == pytest.approx(0.0)

    def test_all_ones(self, calc: ConfidenceCalculator) -> None:
        assert calc.compute(1.0, 1.0, 1.0, 1.0) == pytest.approx(1.0)

    def test_demo_deposit_scores(self, calc: ConfidenceCalculator) -> None:
        # Demo hardcoded scores → 0.898
        score = calc.compute(
            evidence=0.92, temporal=0.90, depth=0.85, hypothesis=0.90
        )
        expected = 0.92 * 0.40 + 0.90 * 0.25 + 0.85 * 0.20 + 0.90 * 0.15
        assert score == pytest.approx(expected, abs=1e-6)
        assert score >= CONFIRMATION_THRESHOLD

    def test_below_threshold(self, calc: ConfidenceCalculator) -> None:
        score = calc.compute(0.50, 0.50, 0.50, 0.50)
        assert score == pytest.approx(0.50)
        assert score < CONFIRMATION_THRESHOLD

    def test_output_clamped_above_zero(self, calc: ConfidenceCalculator) -> None:
        assert calc.compute(0.1, 0.1, 0.0, 0.0) >= 0.0

    def test_output_not_above_one(self, calc: ConfidenceCalculator) -> None:
        assert calc.compute(1.0, 1.0, 1.0, 1.0) <= 1.0

    def test_formula_is_weighted_average(self, calc: ConfidenceCalculator) -> None:
        e, t, d, h = 0.80, 0.70, 0.60, 0.50
        expected = e * 0.40 + t * 0.25 + d * 0.20 + h * 0.15
        assert calc.compute(e, t, d, h) == pytest.approx(expected)

    @pytest.mark.parametrize("score,expected_above_threshold", [
        (0.0, False),
        (0.69, False),
        (0.70, True),
        (0.898, True),
        (1.0, True),
    ])
    def test_threshold_boundary(
        self,
        calc: ConfidenceCalculator,
        score: float,
        expected_above_threshold: bool,
    ) -> None:
        # Construct inputs that yield approximately the target score
        result = calc.compute(score, score, score, score)
        assert (result >= CONFIRMATION_THRESHOLD) == expected_above_threshold


class TestComputeWithBreakdown:
    def test_returns_breakdown_type(self, calc: ConfidenceCalculator) -> None:
        bd = calc.compute_with_breakdown(0.9, 0.85, 0.80, 0.88)
        assert isinstance(bd, ConfidenceBreakdown)

    def test_breakdown_fields_match_compute(self, calc: ConfidenceCalculator) -> None:
        e, t, d, h = 0.92, 0.90, 0.85, 0.90
        bd = calc.compute_with_breakdown(e, t, d, h)
        assert bd.evidence_score    == pytest.approx(e)
        assert bd.temporal_score    == pytest.approx(t)
        assert bd.depth_score       == pytest.approx(d)
        assert bd.hypothesis_score  == pytest.approx(h)
        assert bd.composite_score   == pytest.approx(calc.compute(e, t, d, h))

    def test_to_dict_keys(self, calc: ConfidenceCalculator) -> None:
        bd = calc.compute_with_breakdown(0.9, 0.9, 0.9, 0.9)
        d = bd.to_dict()
        required_keys = {
            "evidence_score",
            "temporal_score",
            "depth_score",
            "hypothesis_alignment_score",
            "composite_score",
            "weights",
        }
        assert required_keys.issubset(set(d.keys()))

    def test_to_dict_weights_correct(self, calc: ConfidenceCalculator) -> None:
        bd = calc.compute_with_breakdown(0.9, 0.9, 0.9, 0.9)
        w = bd.to_dict()["weights"]
        assert w["evidence"]   == pytest.approx(0.40)
        assert w["temporal"]   == pytest.approx(0.25)
        assert w["depth"]      == pytest.approx(0.20)
        assert w["hypothesis"] == pytest.approx(0.15)

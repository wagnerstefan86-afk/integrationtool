"""Tests for the harmonization scoring engine."""

import pytest

from harmonizer.models.assessment import (
    AlignmentDimension,
    Assessment,
    AssessedObjectType,
    AssessmentAnswer,
    HardConstraint,
    HarmonizationClassification,
)
from harmonizer.scoring.engine import (
    apply_hard_constraints,
    classify_score,
    compute_weighted_score,
    evaluate,
)


def _make_answers(scores: dict[AlignmentDimension, int]) -> list[AssessmentAnswer]:
    """Helper to create assessment answers from a dimension->score mapping."""
    return [
        AssessmentAnswer(dimension=dim, score=score, rationale=f"Test: {dim.value}={score}")
        for dim, score in scores.items()
    ]


def _uniform_answers(score: int) -> list[AssessmentAnswer]:
    """Create answers with the same score for all dimensions."""
    return _make_answers({dim: score for dim in AlignmentDimension})


class TestComputeWeightedScore:
    def test_all_fives_returns_one(self) -> None:
        answers = _uniform_answers(5)
        assert compute_weighted_score(answers) == pytest.approx(1.0)

    def test_all_ones_returns_zero(self) -> None:
        answers = _uniform_answers(1)
        assert compute_weighted_score(answers) == pytest.approx(0.0)

    def test_all_threes_returns_half(self) -> None:
        answers = _uniform_answers(3)
        assert compute_weighted_score(answers) == pytest.approx(0.5)

    def test_empty_answers_returns_zero(self) -> None:
        assert compute_weighted_score([]) == pytest.approx(0.0)

    def test_partial_dimensions(self) -> None:
        """Only regulatory and operational dimensions provided."""
        answers = _make_answers({
            AlignmentDimension.REGULATORY_ALIGNMENT: 5,
            AlignmentDimension.OPERATIONAL_ALIGNMENT: 1,
        })
        score = compute_weighted_score(answers)
        # regulatory weight=0.25, operational=0.20
        # normalized: reg=1.0, ops=0.0
        # weighted: (0.25*1.0 + 0.20*0.0) / (0.25+0.20) = 0.25/0.45
        expected = 0.25 / 0.45
        assert score == pytest.approx(expected, rel=1e-4)


class TestClassifyScore:
    @pytest.mark.parametrize("score,expected", [
        (1.0, HarmonizationClassification.FULLY_CENTRALIZABLE),
        (0.85, HarmonizationClassification.FULLY_CENTRALIZABLE),
        (0.84, HarmonizationClassification.CENTRAL_METHOD_LOCAL_EXECUTION),
        (0.70, HarmonizationClassification.CENTRAL_METHOD_LOCAL_EXECUTION),
        (0.69, HarmonizationClassification.PARTIALLY_HARMONIZABLE),
        (0.50, HarmonizationClassification.PARTIALLY_HARMONIZABLE),
        (0.49, HarmonizationClassification.MINIMUM_STANDARD_ONLY),
        (0.30, HarmonizationClassification.MINIMUM_STANDARD_ONLY),
        (0.29, HarmonizationClassification.CURRENTLY_NOT_HARMONIZABLE),
        (0.0, HarmonizationClassification.CURRENTLY_NOT_HARMONIZABLE),
    ])
    def test_thresholds(self, score: float, expected: HarmonizationClassification) -> None:
        assert classify_score(score) == expected


class TestHardConstraints:
    def test_no_constraints_no_change(self) -> None:
        cls, reasons = apply_hard_constraints(
            HarmonizationClassification.FULLY_CENTRALIZABLE, []
        )
        assert cls == HarmonizationClassification.FULLY_CENTRALIZABLE
        assert reasons == []

    def test_legal_constraint_caps_to_minimum_standard(self) -> None:
        cls, reasons = apply_hard_constraints(
            HarmonizationClassification.FULLY_CENTRALIZABLE,
            [HardConstraint.LEGAL_LOCAL_DIFFERENCE],
        )
        assert cls == HarmonizationClassification.MINIMUM_STANDARD_ONLY
        assert len(reasons) == 1

    def test_tenant_separation_caps_to_central_method(self) -> None:
        cls, reasons = apply_hard_constraints(
            HarmonizationClassification.FULLY_CENTRALIZABLE,
            [HardConstraint.TENANT_SEPARATION_BLOCKS_OPERATION],
        )
        assert cls == HarmonizationClassification.CENTRAL_METHOD_LOCAL_EXECUTION
        assert len(reasons) == 1

    def test_insufficient_docs_caps_to_not_harmonizable(self) -> None:
        cls, reasons = apply_hard_constraints(
            HarmonizationClassification.FULLY_CENTRALIZABLE,
            [HardConstraint.INSUFFICIENT_DOCUMENTATION],
        )
        assert cls == HarmonizationClassification.CURRENTLY_NOT_HARMONIZABLE
        assert len(reasons) == 1

    def test_multiple_constraints_strictest_wins(self) -> None:
        """When both legal and insufficient_documentation apply,
        the stricter one (not_harmonizable) should win."""
        cls, reasons = apply_hard_constraints(
            HarmonizationClassification.FULLY_CENTRALIZABLE,
            [HardConstraint.LEGAL_LOCAL_DIFFERENCE, HardConstraint.INSUFFICIENT_DOCUMENTATION],
        )
        assert cls == HarmonizationClassification.CURRENTLY_NOT_HARMONIZABLE
        assert len(reasons) == 2

    def test_constraint_below_current_level_no_effect(self) -> None:
        """A constraint that caps at a HIGHER level than current should not change anything."""
        cls, reasons = apply_hard_constraints(
            HarmonizationClassification.CURRENTLY_NOT_HARMONIZABLE,
            [HardConstraint.TENANT_SEPARATION_BLOCKS_OPERATION],
        )
        assert cls == HarmonizationClassification.CURRENTLY_NOT_HARMONIZABLE
        assert reasons == []


class TestEvaluate:
    def test_full_score_no_constraints(self) -> None:
        assessment = Assessment(
            assessed_object_type=AssessedObjectType.MAIN_PROCESS,
            assessed_object_id="test-stream",
            answers=_uniform_answers(5),
            hard_constraints=[],
        )
        result = evaluate(assessment)
        assert result.harmonization_score == pytest.approx(1.0)
        assert result.classification == HarmonizationClassification.FULLY_CENTRALIZABLE

    def test_low_score_yields_not_harmonizable(self) -> None:
        assessment = Assessment(
            assessed_object_type=AssessedObjectType.SUBPROCESS,
            assessed_object_id="test-sp",
            answers=_uniform_answers(1),
            hard_constraints=[],
        )
        result = evaluate(assessment)
        assert result.harmonization_score == pytest.approx(0.0)
        assert result.classification == HarmonizationClassification.CURRENTLY_NOT_HARMONIZABLE

    def test_high_score_capped_by_constraint(self) -> None:
        assessment = Assessment(
            assessed_object_type=AssessedObjectType.MAIN_PROCESS,
            assessed_object_id="test-stream",
            answers=_uniform_answers(5),
            hard_constraints=[HardConstraint.LEGAL_LOCAL_DIFFERENCE],
        )
        result = evaluate(assessment)
        assert result.harmonization_score == pytest.approx(1.0)
        assert result.classification == HarmonizationClassification.MINIMUM_STANDARD_ONLY

    def test_result_has_recommendation(self) -> None:
        assessment = Assessment(
            assessed_object_type=AssessedObjectType.MAIN_PROCESS,
            assessed_object_id="test-stream",
            answers=_uniform_answers(3),
            hard_constraints=[],
        )
        result = evaluate(assessment)
        assert result.recommendation
        assert len(result.recommendation) > 10

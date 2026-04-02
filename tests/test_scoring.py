"""Tests for the harmonization scoring engine."""

import pytest

from harmonizer.models.process import StreamType
from harmonizer.models.assessment import (
    AlignmentDimension,
    Assessment,
    AssessedObjectType,
    AssessmentAnswer,
    HardConstraint,
    HarmonizationClassification,
    HarmonizationPriority,
    PrioritizationInput,
)
from harmonizer.scoring.engine import (
    apply_hard_constraints,
    classify_score,
    compute_prioritization,
    compute_weighted_score,
    evaluate,
    get_weights_for_stream_type,
    STREAM_TYPE_WEIGHTS,
    DEFAULT_WEIGHTS,
)


def _make_answers(scores: dict[AlignmentDimension, int]) -> list[AssessmentAnswer]:
    return [
        AssessmentAnswer(dimension=dim, score=score, rationale=f"Test: {dim.value}={score}")
        for dim, score in scores.items()
    ]


def _uniform_answers(score: int) -> list[AssessmentAnswer]:
    return _make_answers({dim: score for dim in AlignmentDimension})


class TestStreamTypeWeights:
    def test_all_stream_types_have_weights(self) -> None:
        for st in StreamType:
            assert st in STREAM_TYPE_WEIGHTS

    def test_all_weights_sum_to_one(self) -> None:
        for st, weights in STREAM_TYPE_WEIGHTS.items():
            total = sum(weights.values())
            assert total == pytest.approx(1.0), f"{st.value} weights sum to {total}"

    def test_default_weights_sum_to_one(self) -> None:
        assert sum(DEFAULT_WEIGHTS.values()) == pytest.approx(1.0)

    def test_get_weights_for_none_returns_default(self) -> None:
        assert get_weights_for_stream_type(None) == DEFAULT_WEIGHTS

    def test_get_weights_for_process(self) -> None:
        w = get_weights_for_stream_type(StreamType.PROCESS)
        assert w == STREAM_TYPE_WEIGHTS[StreamType.PROCESS]
        # Process type should emphasize operational alignment
        assert w[AlignmentDimension.OPERATIONAL_ALIGNMENT] >= 0.25

    def test_governance_function_emphasizes_governance(self) -> None:
        w = get_weights_for_stream_type(StreamType.GOVERNANCE_FUNCTION)
        assert w[AlignmentDimension.GOVERNANCE_ALIGNMENT] >= 0.25
        assert w[AlignmentDimension.REGULATORY_ALIGNMENT] >= 0.25

    def test_support_function_emphasizes_operations_and_tooling(self) -> None:
        w = get_weights_for_stream_type(StreamType.SUPPORT_FUNCTION)
        assert w[AlignmentDimension.OPERATIONAL_ALIGNMENT] >= 0.25
        assert w[AlignmentDimension.TOOLING_ALIGNMENT] >= 0.20


class TestComputeWeightedScore:
    def test_all_fives_returns_one(self) -> None:
        assert compute_weighted_score(_uniform_answers(5)) == pytest.approx(1.0)

    def test_all_ones_returns_zero(self) -> None:
        assert compute_weighted_score(_uniform_answers(1)) == pytest.approx(0.0)

    def test_all_threes_returns_half(self) -> None:
        assert compute_weighted_score(_uniform_answers(3)) == pytest.approx(0.5)

    def test_empty_answers_returns_zero(self) -> None:
        assert compute_weighted_score([]) == pytest.approx(0.0)

    def test_stream_type_weights_change_result(self) -> None:
        """Same scores but different weights should produce different results."""
        answers = _make_answers({
            AlignmentDimension.REGULATORY_ALIGNMENT: 5,
            AlignmentDimension.OPERATIONAL_ALIGNMENT: 1,
            AlignmentDimension.TOOLING_ALIGNMENT: 1,
            AlignmentDimension.GOVERNANCE_ALIGNMENT: 5,
            AlignmentDimension.MATURITY: 3,
            AlignmentDimension.LOCAL_NECESSITY: 3,
        })
        score_gov = compute_weighted_score(
            answers, STREAM_TYPE_WEIGHTS[StreamType.GOVERNANCE_FUNCTION]
        )
        score_support = compute_weighted_score(
            answers, STREAM_TYPE_WEIGHTS[StreamType.SUPPORT_FUNCTION]
        )
        # Governance function weights reg + gov higher -> higher score
        assert score_gov > score_support


class TestClassifyScore:
    @pytest.mark.parametrize("score,expected", [
        (1.0, HarmonizationClassification.FULLY_CENTRALIZABLE),
        (0.85, HarmonizationClassification.FULLY_CENTRALIZABLE),
        (0.84, HarmonizationClassification.CENTRAL_METHOD_LOCAL_EXECUTION),
        (0.70, HarmonizationClassification.CENTRAL_METHOD_LOCAL_EXECUTION),
        (0.50, HarmonizationClassification.PARTIALLY_HARMONIZABLE),
        (0.30, HarmonizationClassification.MINIMUM_STANDARD_ONLY),
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

    def test_multiple_constraints_strictest_wins(self) -> None:
        cls, reasons = apply_hard_constraints(
            HarmonizationClassification.FULLY_CENTRALIZABLE,
            [HardConstraint.LEGAL_LOCAL_DIFFERENCE, HardConstraint.INSUFFICIENT_DOCUMENTATION],
        )
        assert cls == HarmonizationClassification.CURRENTLY_NOT_HARMONIZABLE
        assert len(reasons) == 2

    def test_constraint_below_current_level_no_effect(self) -> None:
        cls, reasons = apply_hard_constraints(
            HarmonizationClassification.CURRENTLY_NOT_HARMONIZABLE,
            [HardConstraint.TENANT_SEPARATION_BLOCKS_OPERATION],
        )
        assert cls == HarmonizationClassification.CURRENTLY_NOT_HARMONIZABLE
        assert reasons == []


class TestEvaluate:
    def test_full_score_no_constraints(self) -> None:
        assessment = Assessment(
            assessed_object_type=AssessedObjectType.STREAM,
            assessed_object_id="test-stream",
            answers=_uniform_answers(5),
        )
        result = evaluate(assessment)
        assert result.harmonization_score == pytest.approx(1.0)
        assert result.classification == HarmonizationClassification.FULLY_CENTRALIZABLE

    def test_low_score_yields_not_harmonizable(self) -> None:
        assessment = Assessment(
            assessed_object_type=AssessedObjectType.SUBPROCESS,
            assessed_object_id="test-sp",
            answers=_uniform_answers(1),
        )
        result = evaluate(assessment)
        assert result.harmonization_score == pytest.approx(0.0)
        assert result.classification == HarmonizationClassification.CURRENTLY_NOT_HARMONIZABLE

    def test_high_score_capped_by_constraint(self) -> None:
        assessment = Assessment(
            assessed_object_type=AssessedObjectType.STREAM,
            assessed_object_id="test-stream",
            answers=_uniform_answers(5),
            hard_constraints=[HardConstraint.LEGAL_LOCAL_DIFFERENCE],
        )
        result = evaluate(assessment)
        assert result.harmonization_score == pytest.approx(1.0)
        assert result.classification == HarmonizationClassification.MINIMUM_STANDARD_ONLY

    def test_stream_type_influences_result(self) -> None:
        """Different stream types with same scores should produce different results."""
        answers = _make_answers({
            AlignmentDimension.REGULATORY_ALIGNMENT: 5,
            AlignmentDimension.OPERATIONAL_ALIGNMENT: 1,
            AlignmentDimension.TOOLING_ALIGNMENT: 1,
            AlignmentDimension.GOVERNANCE_ALIGNMENT: 5,
            AlignmentDimension.MATURITY: 3,
            AlignmentDimension.LOCAL_NECESSITY: 3,
        })
        assessment = Assessment(
            assessed_object_type=AssessedObjectType.STREAM,
            assessed_object_id="test",
            answers=answers,
        )
        result_gov = evaluate(assessment, stream_type=StreamType.GOVERNANCE_FUNCTION)
        result_support = evaluate(assessment, stream_type=StreamType.SUPPORT_FUNCTION)
        assert result_gov.harmonization_score > result_support.harmonization_score

    def test_rationale_includes_stream_type(self) -> None:
        assessment = Assessment(
            assessed_object_type=AssessedObjectType.STREAM,
            assessed_object_id="test",
            answers=_uniform_answers(3),
        )
        result = evaluate(assessment, stream_type=StreamType.GOVERNANCE_FUNCTION)
        assert "governance function" in result.rationale

    def test_result_has_recommendation(self) -> None:
        assessment = Assessment(
            assessed_object_type=AssessedObjectType.STREAM,
            assessed_object_id="test",
            answers=_uniform_answers(3),
        )
        result = evaluate(assessment)
        assert result.recommendation
        assert len(result.recommendation) > 10


class TestPrioritization:
    def test_high_priority(self) -> None:
        pri = PrioritizationInput(
            harmonization_potential=5,
            operational_relevance=5,
            governance_compliance_benefit=5,
            implementation_effort=1,
            dependencies=1,
        )
        result = compute_prioritization(pri)
        assert result.priority == HarmonizationPriority.HIGH
        assert result.priority_score >= 0.65

    def test_low_priority(self) -> None:
        pri = PrioritizationInput(
            harmonization_potential=1,
            operational_relevance=1,
            governance_compliance_benefit=1,
            implementation_effort=5,
            dependencies=5,
        )
        result = compute_prioritization(pri)
        assert result.priority == HarmonizationPriority.LOW
        assert result.priority_score < 0.40

    def test_medium_priority(self) -> None:
        pri = PrioritizationInput(
            harmonization_potential=3,
            operational_relevance=3,
            governance_compliance_benefit=3,
            implementation_effort=3,
            dependencies=3,
        )
        result = compute_prioritization(pri)
        assert result.priority == HarmonizationPriority.MEDIUM

    def test_high_effort_reduces_priority(self) -> None:
        """Same potential but high effort should yield lower priority."""
        low_effort = PrioritizationInput(
            harmonization_potential=5,
            operational_relevance=4,
            governance_compliance_benefit=4,
            implementation_effort=1,
            dependencies=1,
        )
        high_effort = PrioritizationInput(
            harmonization_potential=5,
            operational_relevance=4,
            governance_compliance_benefit=4,
            implementation_effort=5,
            dependencies=5,
        )
        r1 = compute_prioritization(low_effort)
        r2 = compute_prioritization(high_effort)
        assert r1.priority_score > r2.priority_score

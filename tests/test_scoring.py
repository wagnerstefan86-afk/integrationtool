"""Tests for the harmonization scoring engine."""

import pytest

from harmonizer.models.process import StreamType
from harmonizer.models.assessment import (
    AlignmentDimension,
    Assessment,
    AssessedObjectType,
    AssessmentAnswer,
    ConfidenceLevel,
    HardConstraint,
    HarmonizationClassification,
    HarmonizationPriority,
    PrioritizationInput,
    TypeSpecificAnswer,
)
from harmonizer.scoring.engine import (
    apply_hard_constraints,
    classify_score,
    compute_blended_score,
    compute_completeness,
    compute_prioritization,
    compute_type_specific_score,
    compute_weighted_score,
    evaluate,
    aggregate_stream_assessment,
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
        assert score_gov > score_support


class TestTypeSpecificScore:
    def test_empty_returns_zero(self) -> None:
        assert compute_type_specific_score([]) == pytest.approx(0.0)

    def test_all_fives(self) -> None:
        answers = [
            TypeSpecificAnswer(question_id="q1", score=5, rationale="good"),
            TypeSpecificAnswer(question_id="q2", score=5, rationale="good"),
        ]
        assert compute_type_specific_score(answers) == pytest.approx(1.0)

    def test_all_ones(self) -> None:
        answers = [
            TypeSpecificAnswer(question_id="q1", score=1, rationale="bad"),
        ]
        assert compute_type_specific_score(answers) == pytest.approx(0.0)

    def test_mixed_scores(self) -> None:
        answers = [
            TypeSpecificAnswer(question_id="q1", score=5, rationale="r"),
            TypeSpecificAnswer(question_id="q2", score=1, rationale="r"),
        ]
        assert compute_type_specific_score(answers) == pytest.approx(0.5)


class TestBlendedScore:
    def test_no_type_specific_returns_base(self) -> None:
        assert compute_blended_score(0.8, 0.0, False) == pytest.approx(0.8)

    def test_with_type_specific_blends(self) -> None:
        # 85% base + 15% type-specific
        result = compute_blended_score(0.8, 1.0, True)
        expected = 0.8 * 0.85 + 1.0 * 0.15
        assert result == pytest.approx(expected)

    def test_type_specific_can_raise_or_lower(self) -> None:
        # High type-specific raises score
        high = compute_blended_score(0.5, 1.0, True)
        # Low type-specific lowers score
        low = compute_blended_score(0.5, 0.0, True)
        assert high > 0.5
        assert low < 0.5


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
        cls, _ = apply_hard_constraints(
            HarmonizationClassification.FULLY_CENTRALIZABLE,
            [HardConstraint.LEGAL_LOCAL_DIFFERENCE],
        )
        assert cls == HarmonizationClassification.MINIMUM_STANDARD_ONLY

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
        assert result.classification == HarmonizationClassification.MINIMUM_STANDARD_ONLY

    def test_stream_type_influences_result(self) -> None:
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

    def test_type_specific_answers_influence_score(self) -> None:
        base_assessment = Assessment(
            assessed_object_type=AssessedObjectType.STREAM,
            assessed_object_id="test",
            answers=_uniform_answers(3),
        )
        enhanced_assessment = Assessment(
            assessed_object_type=AssessedObjectType.STREAM,
            assessed_object_id="test",
            answers=_uniform_answers(3),
            type_specific_answers=[
                TypeSpecificAnswer(question_id="q1", score=5, rationale="r"),
                TypeSpecificAnswer(question_id="q2", score=5, rationale="r"),
            ],
        )
        r_base = evaluate(base_assessment)
        r_enhanced = evaluate(enhanced_assessment)
        # Type-specific all-5s should raise the score above base
        assert r_enhanced.harmonization_score > r_base.harmonization_score

    def test_rationale_includes_stream_type(self) -> None:
        assessment = Assessment(
            assessed_object_type=AssessedObjectType.STREAM,
            assessed_object_id="test",
            answers=_uniform_answers(3),
        )
        result = evaluate(assessment, stream_type=StreamType.GOVERNANCE_FUNCTION)
        assert "governance function" in result.rationale


class TestAggregation:
    def _make_assessment(self, obj_id: str, score: int,
                         constraints: list[HardConstraint] | None = None) -> Assessment:
        return Assessment(
            assessed_object_type=AssessedObjectType.SUBPROCESS,
            assessed_object_id=obj_id,
            answers=_uniform_answers(score),
            hard_constraints=constraints or [],
        )

    def test_no_data_returns_none(self) -> None:
        assert aggregate_stream_assessment(None, []) is None

    def test_only_subprocesses(self) -> None:
        sps = [
            self._make_assessment("sp1", 5),
            self._make_assessment("sp2", 5),
        ]
        result = aggregate_stream_assessment(None, sps)
        assert result is not None
        assert result.harmonization_score == pytest.approx(1.0)

    def test_only_stream_assessment(self) -> None:
        stream_a = Assessment(
            assessed_object_type=AssessedObjectType.STREAM,
            assessed_object_id="stream",
            answers=_uniform_answers(3),
        )
        result = aggregate_stream_assessment(stream_a, [])
        assert result is not None
        assert result.harmonization_score == pytest.approx(0.5)

    def test_blended_stream_and_subprocesses(self) -> None:
        stream_a = Assessment(
            assessed_object_type=AssessedObjectType.STREAM,
            assessed_object_id="stream",
            answers=_uniform_answers(5),  # score = 1.0
        )
        sps = [
            self._make_assessment("sp1", 1),  # score = 0.0
        ]
        result = aggregate_stream_assessment(stream_a, sps)
        assert result is not None
        # 40% * 1.0 + 60% * 0.0 = 0.4
        assert result.harmonization_score == pytest.approx(0.4)

    def test_hard_constraints_propagate_from_subprocesses(self) -> None:
        stream_a = Assessment(
            assessed_object_type=AssessedObjectType.STREAM,
            assessed_object_id="stream",
            answers=_uniform_answers(5),
        )
        sps = [
            self._make_assessment("sp1", 5, [HardConstraint.LEGAL_LOCAL_DIFFERENCE]),
        ]
        result = aggregate_stream_assessment(stream_a, sps)
        assert result is not None
        # Score is high but constraint caps it
        assert result.classification == HarmonizationClassification.MINIMUM_STANDARD_ONLY

    def test_rationale_mentions_aggregation(self) -> None:
        sps = [self._make_assessment("sp1", 3)]
        result = aggregate_stream_assessment(None, sps)
        assert "Aggregated from 1" in result.rationale

    def test_multiple_subprocess_average(self) -> None:
        sps = [
            self._make_assessment("sp1", 5),  # 1.0
            self._make_assessment("sp2", 1),  # 0.0
        ]
        result = aggregate_stream_assessment(None, sps)
        assert result is not None
        assert result.harmonization_score == pytest.approx(0.5)


class TestPrioritization:
    def test_high_priority(self) -> None:
        pri = PrioritizationInput(
            harmonization_potential=5, operational_relevance=5,
            governance_compliance_benefit=5, implementation_effort=1, dependencies=1,
        )
        result = compute_prioritization(pri)
        assert result.priority == HarmonizationPriority.HIGH

    def test_low_priority(self) -> None:
        pri = PrioritizationInput(
            harmonization_potential=1, operational_relevance=1,
            governance_compliance_benefit=1, implementation_effort=5, dependencies=5,
        )
        result = compute_prioritization(pri)
        assert result.priority == HarmonizationPriority.LOW

    def test_medium_priority(self) -> None:
        pri = PrioritizationInput(
            harmonization_potential=3, operational_relevance=3,
            governance_compliance_benefit=3, implementation_effort=3, dependencies=3,
        )
        result = compute_prioritization(pri)
        assert result.priority == HarmonizationPriority.MEDIUM

    def test_high_effort_reduces_priority(self) -> None:
        low_effort = PrioritizationInput(
            harmonization_potential=5, operational_relevance=4,
            governance_compliance_benefit=4, implementation_effort=1, dependencies=1,
        )
        high_effort = PrioritizationInput(
            harmonization_potential=5, operational_relevance=4,
            governance_compliance_benefit=4, implementation_effort=5, dependencies=5,
        )
        r1 = compute_prioritization(low_effort)
        r2 = compute_prioritization(high_effort)
        assert r1.priority_score > r2.priority_score


class TestCompleteness:
    def _stream_assessment(self, answers: list[AssessmentAnswer] | None = None,
                           type_specific: list[TypeSpecificAnswer] | None = None,
                           constraints: list[HardConstraint] | None = None,
                           prioritization: PrioritizationInput | None = None) -> Assessment:
        return Assessment(
            assessed_object_type=AssessedObjectType.STREAM,
            assessed_object_id="test-stream",
            answers=answers or [],
            type_specific_answers=type_specific or [],
            hard_constraints=constraints or [],
            prioritization=prioritization,
        )

    def test_full_assessment_high_confidence(self) -> None:
        """A fully populated assessment should yield high confidence."""
        from harmonizer.scoring.questions import get_required_question_ids
        req_ids = get_required_question_ids(StreamType.PROCESS)
        ts_answers = [
            TypeSpecificAnswer(question_id=qid, score=4, rationale="ok")
            for qid in req_ids
        ]
        a = self._stream_assessment(
            answers=_uniform_answers(4),
            type_specific=ts_answers,
            constraints=[HardConstraint.TENANT_SEPARATION_BLOCKS_OPERATION],
            prioritization=PrioritizationInput(
                harmonization_potential=4, operational_relevance=3,
                governance_compliance_benefit=4, implementation_effort=2, dependencies=2,
            ),
        )
        result = compute_completeness(
            a, stream_type=StreamType.PROCESS,
            subprocess_count=3, subprocess_assessed_count=3,
            interface_count=2, has_regulatory_context=True, has_tenant_scope=True,
        )
        assert result.confidence_level == ConfidenceLevel.HIGH
        assert result.completeness_score >= 75

    def test_empty_assessment_low_confidence(self) -> None:
        a = self._stream_assessment()
        result = compute_completeness(
            a, stream_type=StreamType.PROCESS,
            subprocess_count=5, subprocess_assessed_count=0,
            interface_count=0, has_regulatory_context=False, has_tenant_scope=True,
        )
        assert result.confidence_level == ConfidenceLevel.LOW
        assert result.completeness_score < 45
        assert len(result.missing_items) > 0

    def test_missing_base_dimensions_flagged(self) -> None:
        partial_answers = [
            AssessmentAnswer(dimension=AlignmentDimension.REGULATORY_ALIGNMENT,
                             score=3, rationale="test"),
        ]
        a = self._stream_assessment(answers=partial_answers)
        result = compute_completeness(
            a, stream_type=StreamType.PROCESS,
            subprocess_count=0, subprocess_assessed_count=0,
            interface_count=0, has_regulatory_context=True, has_tenant_scope=True,
        )
        assert any("Missing base dimensions" in m for m in result.missing_items)

    def test_missing_type_specific_flagged(self) -> None:
        a = self._stream_assessment(answers=_uniform_answers(3))
        result = compute_completeness(
            a, stream_type=StreamType.GOVERNANCE_FUNCTION,
            subprocess_count=2, subprocess_assessed_count=2,
            interface_count=1, has_regulatory_context=True, has_tenant_scope=True,
        )
        assert any("Missing type-specific" in m for m in result.missing_items)

    def test_partial_subprocess_coverage(self) -> None:
        a = self._stream_assessment(answers=_uniform_answers(3))
        result = compute_completeness(
            a, stream_type=StreamType.PROCESS,
            subprocess_count=5, subprocess_assessed_count=2,
            interface_count=1, has_regulatory_context=True, has_tenant_scope=True,
        )
        assert any("2/5" in m for m in result.missing_items)

    def test_subprocess_assessment_full_credit(self) -> None:
        """Subprocess-level assessments get full credit for subprocess coverage."""
        a = Assessment(
            assessed_object_type=AssessedObjectType.SUBPROCESS,
            assessed_object_id="sp-test",
            answers=_uniform_answers(4),
        )
        result = compute_completeness(
            a, stream_type=StreamType.PROCESS,
            subprocess_count=0, subprocess_assessed_count=0,
            interface_count=1, has_regulatory_context=True, has_tenant_scope=True,
        )
        # Subprocess gets full 20 points for subprocess coverage (not applicable)
        assert result.completeness_score >= 60

    def test_no_prioritization_flagged_for_stream(self) -> None:
        a = self._stream_assessment(answers=_uniform_answers(3))
        result = compute_completeness(
            a, stream_type=StreamType.PROCESS,
            subprocess_count=0, subprocess_assessed_count=0,
            interface_count=0, has_regulatory_context=True, has_tenant_scope=True,
        )
        assert any("Prioritization" in m for m in result.missing_items)

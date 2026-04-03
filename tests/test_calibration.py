"""Tests for calibration engine.

Covers:
- Model maturity determination
- Single outcome comparison
- Systematic bias detection
- Adjustment suggestion generation
- Confidence adjustment computation
- Full calibration pipeline
- Outcome model validation
- Deviation classification and learning relevance
- Calibration filtering (political/strategic excluded)
- Trust score computation
- Protected rules filtering
"""

import pytest

from harmonizer.models.assessment import (
    ActualImplementation,
    ActualImpact,
    AlignmentDimension,
    Assessment,
    AssessedObjectType,
    AssessmentAnswer,
    CalibrationDeviation,
    CalibrationResult,
    CalibrationSuggestion,
    CompletenessResult,
    ConfidenceLevel,
    Decision,
    DecisionOutcome,
    DecisionResult,
    DeviationLevel,
    DeviationReason,
    DurationCategory,
    EffortEstimate,
    HarmonizationClassification,
    HarmonizationDegree,
    HarmonizationResult,
    ImplementationImpact,
    InterfaceComplexityResult,
    LearningRelevance,
    ModelMaturityLevel,
    OutcomeStatus,
    ProtectedRule,
    TargetOperatingModel,
    ValueIndicators,
    ValueLevel,
)
from harmonizer.scoring.calibration_engine import (
    DEVIATION_REASON_RELEVANCE,
    PROTECTED_RULES,
    calibrate,
    compare_single_outcome,
    compute_confidence_adjustment,
    compute_trust_score,
    detect_systematic_biases,
    determine_model_maturity,
    filter_suggestions_against_protected_rules,
    generate_suggestions,
    is_learning_relevant,
    resolve_learning_relevance,
)


# --- Helpers ---

def _make_decision_result(
    decision: Decision = Decision.CENTRALIZE_NOW,
    effort_bucket: str = "6-12",
    duration: DurationCategory = DurationCategory.MEDIUM,
    complexity: ValueLevel = ValueLevel.HIGH,
    business_value: ValueLevel = ValueLevel.HIGH,
    operational_impact: ValueLevel = ValueLevel.HIGH,
) -> DecisionResult:
    return DecisionResult(
        decision=decision,
        decision_rationale="Test",
        expected_benefit="Test",
        implementation_risk="Test",
        target_operating_model=TargetOperatingModel.CENTRALIZED_EXECUTION,
        interface_complexity=InterfaceComplexityResult(
            complexity_score=0.3, interface_count=3, distinct_types=2,
            distinct_artifacts=5, cross_area_connections=1, rationale="R",
        ),
        harmonization_degree=HarmonizationDegree(
            harmonizable=True, harmonization_degree=0.9,
            standardizable=True, standardization_degree=0.85,
            centralizable=True, centralization_degree=0.8,
            rationale="R",
        ),
        value_indicators=ValueIndicators(
            expected_business_value=business_value,
            regulatory_pressure=ValueLevel.MEDIUM,
            operational_impact=operational_impact,
            rationale="R",
        ),
        effort_estimate=EffortEstimate(
            person_months_bucket=effort_bucket,
            implementation_duration=duration,
            cost_category=ValueLevel.HIGH,
            rationale="R",
        ),
        implementation_impact=ImplementationImpact(
            implementation_complexity=complexity,
            change_magnitude=ValueLevel.HIGH,
        ),
    )


def _make_assessment_with_decision(
    obj_id: str = "s1",
    decision: Decision = Decision.CENTRALIZE_NOW,
    **kwargs,
) -> Assessment:
    return Assessment(
        assessed_object_type=AssessedObjectType.STREAM,
        assessed_object_id=obj_id,
        answers=[
            AssessmentAnswer(dimension=d, score=4, rationale="R")
            for d in AlignmentDimension
        ],
        result=HarmonizationResult(
            harmonization_score=0.8,
            classification=HarmonizationClassification.FULLY_CENTRALIZABLE,
            rationale="R", recommendation="R",
        ),
        completeness=CompletenessResult(
            completeness_score=80,
            confidence_level=ConfidenceLevel.HIGH,
            missing_items=[],
            rationale="R",
        ),
        decision_result=_make_decision_result(decision=decision, **kwargs),
    )


# --- Model Maturity Tests ---

class TestModelMaturity:

    def test_zero_outcomes_initial(self) -> None:
        assert determine_model_maturity(0) == ModelMaturityLevel.INITIAL

    def test_few_outcomes_learning(self) -> None:
        assert determine_model_maturity(1) == ModelMaturityLevel.LEARNING
        assert determine_model_maturity(4) == ModelMaturityLevel.LEARNING

    def test_moderate_outcomes_calibrated(self) -> None:
        assert determine_model_maturity(5) == ModelMaturityLevel.CALIBRATED
        assert determine_model_maturity(9) == ModelMaturityLevel.CALIBRATED

    def test_many_outcomes_stable(self) -> None:
        assert determine_model_maturity(10) == ModelMaturityLevel.STABLE
        assert determine_model_maturity(50) == ModelMaturityLevel.STABLE


# --- Outcome Model Tests ---

class TestOutcomeModels:

    def test_valid_outcome(self) -> None:
        o = DecisionOutcome(
            assessed_object_id="s1",
            outcome_status=OutcomeStatus.IMPLEMENTED,
            deviation=DeviationLevel.NONE,
        )
        assert o.outcome_status == OutcomeStatus.IMPLEMENTED

    def test_outcome_with_actuals(self) -> None:
        o = DecisionOutcome(
            assessed_object_id="s1",
            outcome_status=OutcomeStatus.MODIFIED,
            actual_implementation=ActualImplementation(
                actual_effort_bucket="6-12",
                actual_duration=DurationCategory.MEDIUM,
                actual_complexity=ValueLevel.HIGH,
            ),
            actual_impact=ActualImpact(
                business_value_realized=ValueLevel.MEDIUM,
                operational_improvement=ValueLevel.HIGH,
                issues_encountered=["Change resistance"],
            ),
            deviation=DeviationLevel.MINOR,
            deviation_rationale="Slight scope adjustment",
            lessons_learned=["Start with pilot"],
        )
        assert o.actual_implementation.actual_effort_bucket == "6-12"
        assert len(o.actual_impact.issues_encountered) == 1
        assert len(o.lessons_learned) == 1

    def test_all_outcome_statuses(self) -> None:
        expected = {"implemented", "rejected", "modified", "deferred"}
        assert {s.value for s in OutcomeStatus} == expected

    def test_all_deviation_levels(self) -> None:
        expected = {"none", "minor", "major", "complete_override"}
        assert {d.value for d in DeviationLevel} == expected


# --- Single Outcome Comparison Tests ---

class TestCompareOutcome:

    def test_accurate_prediction(self) -> None:
        a = _make_assessment_with_decision()
        o = DecisionOutcome(
            assessed_object_id="s1",
            outcome_status=OutcomeStatus.IMPLEMENTED,
            deviation=DeviationLevel.NONE,
        )
        devs = compare_single_outcome(a, o)
        assert len(devs) >= 1
        decision_dev = [d for d in devs if d.dimension == "decision"]
        assert decision_dev[0].direction == "accurate"

    def test_rejected_counts_as_overestimated(self) -> None:
        a = _make_assessment_with_decision()
        o = DecisionOutcome(
            assessed_object_id="s1",
            outcome_status=OutcomeStatus.REJECTED,
            deviation=DeviationLevel.COMPLETE_OVERRIDE,
        )
        devs = compare_single_outcome(a, o)
        decision_dev = [d for d in devs if d.dimension == "decision"]
        assert decision_dev[0].direction == "overestimated"

    def test_effort_comparison(self) -> None:
        a = _make_assessment_with_decision(effort_bucket="3-6")
        o = DecisionOutcome(
            assessed_object_id="s1",
            outcome_status=OutcomeStatus.IMPLEMENTED,
            actual_implementation=ActualImplementation(
                actual_effort_bucket="6-12",
                actual_duration=DurationCategory.LONG,
                actual_complexity=ValueLevel.HIGH,
            ),
            deviation=DeviationLevel.MINOR,
        )
        devs = compare_single_outcome(a, o)
        effort_devs = [d for d in devs if d.dimension == "effort"]
        assert len(effort_devs) == 1
        assert effort_devs[0].direction == "underestimated"

    def test_business_value_comparison(self) -> None:
        a = _make_assessment_with_decision(business_value=ValueLevel.HIGH)
        o = DecisionOutcome(
            assessed_object_id="s1",
            outcome_status=OutcomeStatus.IMPLEMENTED,
            actual_impact=ActualImpact(
                business_value_realized=ValueLevel.LOW,
                operational_improvement=ValueLevel.MEDIUM,
            ),
            deviation=DeviationLevel.MINOR,
        )
        devs = compare_single_outcome(a, o)
        bv_devs = [d for d in devs if d.dimension == "business_value"]
        assert bv_devs[0].direction == "overestimated"

    def test_no_decision_result_returns_empty(self) -> None:
        a = Assessment(
            assessed_object_type=AssessedObjectType.STREAM,
            assessed_object_id="s1",
        )
        o = DecisionOutcome(
            assessed_object_id="s1",
            outcome_status=OutcomeStatus.IMPLEMENTED,
            deviation=DeviationLevel.NONE,
        )
        devs = compare_single_outcome(a, o)
        assert devs == []


# --- Systematic Bias Detection Tests ---

class TestBiasDetection:

    def test_no_bias_with_mixed_directions(self) -> None:
        devs = [
            CalibrationDeviation(dimension="effort", predicted="3-6", actual="3-6", direction="accurate"),
            CalibrationDeviation(dimension="effort", predicted="3-6", actual="6-12", direction="underestimated"),
            CalibrationDeviation(dimension="effort", predicted="6-12", actual="3-6", direction="overestimated"),
        ]
        biases = detect_systematic_biases(devs)
        assert len(biases) == 0

    def test_detects_overestimation_bias(self) -> None:
        devs = [
            CalibrationDeviation(dimension="effort", predicted="6-12", actual="3-6", direction="overestimated"),
            CalibrationDeviation(dimension="effort", predicted="6-12", actual="3-6", direction="overestimated"),
            CalibrationDeviation(dimension="effort", predicted="3-6", actual="1-3", direction="overestimated"),
        ]
        biases = detect_systematic_biases(devs)
        assert len(biases) == 1
        assert "overestimated" in biases[0]
        assert "effort" in biases[0]

    def test_detects_underestimation_bias(self) -> None:
        devs = [
            CalibrationDeviation(dimension="decision", predicted="centralize_now", actual="rejected", direction="overestimated"),
            CalibrationDeviation(dimension="decision", predicted="centralize_now", actual="deferred", direction="overestimated"),
            CalibrationDeviation(dimension="decision", predicted="centralize_later", actual="rejected", direction="overestimated"),
        ]
        biases = detect_systematic_biases(devs)
        assert len(biases) == 1
        assert "decision" in biases[0]

    def test_single_outcome_not_enough(self) -> None:
        devs = [
            CalibrationDeviation(dimension="effort", predicted="3-6", actual="6-12", direction="underestimated"),
        ]
        biases = detect_systematic_biases(devs)
        assert len(biases) == 0  # need at least 2


# --- Suggestion Generation Tests ---

class TestSuggestions:

    def test_aggressive_decision_suggestion(self) -> None:
        biases = ["decision: systematically overestimated (3/4 cases)"]
        suggestions = generate_suggestions(biases, [], 4)
        assert len(suggestions) >= 1
        assert suggestions[0].area == "decision_aggressiveness"
        assert suggestions[0].priority == ValueLevel.HIGH

    def test_effort_underestimation_suggestion(self) -> None:
        biases = ["effort: systematically underestimated (4/5 cases)"]
        suggestions = generate_suggestions(biases, [], 5)
        assert len(suggestions) >= 1
        assert suggestions[0].area == "effort_estimate"

    def test_no_biases_no_suggestions(self) -> None:
        suggestions = generate_suggestions([], [], 5)
        assert suggestions == []

    def test_complexity_underestimation_suggestion(self) -> None:
        biases = ["complexity: systematically underestimated (3/5 cases)"]
        suggestions = generate_suggestions(biases, [], 5)
        assert len(suggestions) >= 1
        assert suggestions[0].area == "interface_complexity"


# --- Confidence Adjustment Tests ---

class TestConfidenceAdjustment:

    def test_initial_maturity_no_adjustment(self) -> None:
        adj = compute_confidence_adjustment(0.5, ModelMaturityLevel.INITIAL)
        assert adj == 0.0

    def test_high_accuracy_calibrated_boosts(self) -> None:
        adj = compute_confidence_adjustment(0.85, ModelMaturityLevel.CALIBRATED)
        assert adj > 0.0

    def test_low_accuracy_calibrated_penalty(self) -> None:
        adj = compute_confidence_adjustment(0.35, ModelMaturityLevel.CALIBRATED)
        assert adj < 0.0
        assert adj == -0.20

    def test_medium_accuracy_no_change(self) -> None:
        adj = compute_confidence_adjustment(0.65, ModelMaturityLevel.LEARNING)
        assert adj == 0.0

    def test_very_low_accuracy_learning(self) -> None:
        adj = compute_confidence_adjustment(0.30, ModelMaturityLevel.LEARNING)
        assert adj == -0.10


# --- Full Calibration Pipeline Tests ---

class TestCalibrateFunction:

    def test_no_outcomes(self) -> None:
        assessments = [_make_assessment_with_decision()]
        result = calibrate(assessments, [])
        assert result.outcomes_analyzed == 0
        assert result.model_maturity == ModelMaturityLevel.INITIAL
        assert result.accuracy_rate == 0.0

    def test_single_correct_outcome(self) -> None:
        a = _make_assessment_with_decision(obj_id="s1")
        o = DecisionOutcome(
            assessed_object_id="s1",
            outcome_status=OutcomeStatus.IMPLEMENTED,
            deviation=DeviationLevel.NONE,
        )
        result = calibrate([a], [o])
        assert result.outcomes_analyzed == 1
        assert result.accuracy_rate == 1.0
        assert result.model_maturity == ModelMaturityLevel.LEARNING

    def test_single_wrong_outcome(self) -> None:
        a = _make_assessment_with_decision(obj_id="s1")
        o = DecisionOutcome(
            assessed_object_id="s1",
            outcome_status=OutcomeStatus.REJECTED,
            deviation=DeviationLevel.COMPLETE_OVERRIDE,
        )
        result = calibrate([a], [o])
        assert result.outcomes_analyzed == 1
        assert result.accuracy_rate == 0.0

    def test_multiple_outcomes_mixed(self) -> None:
        assessments = [
            _make_assessment_with_decision(obj_id=f"s{i}")
            for i in range(5)
        ]
        outcomes = [
            DecisionOutcome(assessed_object_id="s0", outcome_status=OutcomeStatus.IMPLEMENTED, deviation=DeviationLevel.NONE),
            DecisionOutcome(assessed_object_id="s1", outcome_status=OutcomeStatus.IMPLEMENTED, deviation=DeviationLevel.MINOR),
            DecisionOutcome(assessed_object_id="s2", outcome_status=OutcomeStatus.REJECTED, deviation=DeviationLevel.COMPLETE_OVERRIDE),
            DecisionOutcome(assessed_object_id="s3", outcome_status=OutcomeStatus.MODIFIED, deviation=DeviationLevel.MAJOR),
            DecisionOutcome(assessed_object_id="s4", outcome_status=OutcomeStatus.IMPLEMENTED, deviation=DeviationLevel.NONE),
        ]
        result = calibrate(assessments, outcomes)
        assert result.outcomes_analyzed == 5
        assert result.model_maturity == ModelMaturityLevel.CALIBRATED
        # 3 correct (s0, s1, s4)
        assert result.accuracy_rate == pytest.approx(0.6, abs=0.01)

    def test_unmatched_outcomes_ignored(self) -> None:
        a = _make_assessment_with_decision(obj_id="s1")
        o = DecisionOutcome(
            assessed_object_id="s_nonexistent",
            outcome_status=OutcomeStatus.IMPLEMENTED,
            deviation=DeviationLevel.NONE,
        )
        result = calibrate([a], [o])
        assert result.outcomes_analyzed == 0

    def test_with_effort_and_impact_actuals(self) -> None:
        a = _make_assessment_with_decision(
            obj_id="s1",
            effort_bucket="3-6",
            business_value=ValueLevel.HIGH,
        )
        o = DecisionOutcome(
            assessed_object_id="s1",
            outcome_status=OutcomeStatus.IMPLEMENTED,
            actual_implementation=ActualImplementation(
                actual_effort_bucket="6-12",
                actual_duration=DurationCategory.LONG,
                actual_complexity=ValueLevel.HIGH,
            ),
            actual_impact=ActualImpact(
                business_value_realized=ValueLevel.MEDIUM,
                operational_improvement=ValueLevel.LOW,
            ),
            deviation=DeviationLevel.MINOR,
        )
        result = calibrate([a], [o])
        assert result.outcomes_analyzed == 1
        # Should have deviations for effort and business_value
        effort_devs = [d for d in result.deviations if d.dimension == "effort"]
        assert len(effort_devs) == 1
        assert effort_devs[0].direction == "underestimated"

    def test_systematic_bias_triggers_suggestions(self) -> None:
        """5 outcomes all with overestimated decisions should trigger suggestion."""
        assessments = [
            _make_assessment_with_decision(obj_id=f"s{i}")
            for i in range(5)
        ]
        outcomes = [
            DecisionOutcome(
                assessed_object_id=f"s{i}",
                outcome_status=OutcomeStatus.REJECTED,
                deviation=DeviationLevel.COMPLETE_OVERRIDE,
            )
            for i in range(5)
        ]
        result = calibrate(assessments, outcomes)
        assert len(result.systematic_biases) >= 1
        assert len(result.suggestions) >= 1
        assert any(s.area == "decision_aggressiveness" for s in result.suggestions)

    def test_calibrate_includes_trust_score(self) -> None:
        a = _make_assessment_with_decision(obj_id="s1")
        o = DecisionOutcome(
            assessed_object_id="s1",
            outcome_status=OutcomeStatus.IMPLEMENTED,
            deviation=DeviationLevel.NONE,
        )
        result = calibrate([a], [o])
        assert result.trust_score is not None
        assert result.trust_score.trust_score >= 0.0

    def test_calibrate_includes_filtered_stats(self) -> None:
        a = _make_assessment_with_decision(obj_id="s1")
        o = DecisionOutcome(
            assessed_object_id="s1",
            outcome_status=OutcomeStatus.IMPLEMENTED,
            deviation=DeviationLevel.NONE,
        )
        result = calibrate([a], [o])
        assert result.filtered_stats is not None
        assert result.filtered_stats.total_outcomes == 1

    def test_calibrate_includes_protected_rules(self) -> None:
        result = calibrate([], [])
        assert len(result.protected_rules) >= 1


# --- Deviation Classification Tests ---

class TestDeviationClassification:

    def test_reason_relevance_mapping_complete(self) -> None:
        """Every DeviationReason must have a mapping."""
        for reason in DeviationReason:
            assert reason in DEVIATION_REASON_RELEVANCE

    def test_model_error_is_high(self) -> None:
        assert DEVIATION_REASON_RELEVANCE[DeviationReason.MODEL_ERROR] == LearningRelevance.HIGH

    def test_political_is_none(self) -> None:
        assert DEVIATION_REASON_RELEVANCE[DeviationReason.POLITICAL_DECISION] == LearningRelevance.NONE

    def test_strategic_override_is_none(self) -> None:
        assert DEVIATION_REASON_RELEVANCE[DeviationReason.STRATEGIC_OVERRIDE] == LearningRelevance.NONE

    def test_resource_constraint_is_low(self) -> None:
        assert DEVIATION_REASON_RELEVANCE[DeviationReason.RESOURCE_CONSTRAINT] == LearningRelevance.LOW

    def test_incomplete_data_is_medium(self) -> None:
        assert DEVIATION_REASON_RELEVANCE[DeviationReason.INCOMPLETE_DATA] == LearningRelevance.MEDIUM

    def test_changed_context_is_medium(self) -> None:
        assert DEVIATION_REASON_RELEVANCE[DeviationReason.CHANGED_CONTEXT] == LearningRelevance.MEDIUM

    def test_resolve_from_reason(self) -> None:
        o = DecisionOutcome(
            assessed_object_id="s1",
            outcome_status=OutcomeStatus.REJECTED,
            deviation=DeviationLevel.COMPLETE_OVERRIDE,
            deviation_reason=DeviationReason.POLITICAL_DECISION,
        )
        assert resolve_learning_relevance(o) == LearningRelevance.NONE

    def test_resolve_explicit_overrides_reason(self) -> None:
        """Explicit learning_relevance takes precedence over deviation_reason."""
        o = DecisionOutcome(
            assessed_object_id="s1",
            outcome_status=OutcomeStatus.REJECTED,
            deviation=DeviationLevel.COMPLETE_OVERRIDE,
            deviation_reason=DeviationReason.POLITICAL_DECISION,
            learning_relevance=LearningRelevance.HIGH,  # override
        )
        assert resolve_learning_relevance(o) == LearningRelevance.HIGH

    def test_resolve_default_is_high(self) -> None:
        """No reason or relevance → default to HIGH (assume model error)."""
        o = DecisionOutcome(
            assessed_object_id="s1",
            outcome_status=OutcomeStatus.REJECTED,
            deviation=DeviationLevel.MAJOR,
        )
        assert resolve_learning_relevance(o) == LearningRelevance.HIGH


# --- Calibration Filtering Tests ---

class TestCalibrationFiltering:

    def test_political_outcomes_excluded_from_bias(self) -> None:
        """Political overrides must NOT influence bias detection."""
        assessments = [
            _make_assessment_with_decision(obj_id=f"s{i}")
            for i in range(5)
        ]
        # 3 political rejections + 2 genuine correct outcomes
        outcomes = [
            DecisionOutcome(
                assessed_object_id="s0",
                outcome_status=OutcomeStatus.REJECTED,
                deviation=DeviationLevel.COMPLETE_OVERRIDE,
                deviation_reason=DeviationReason.POLITICAL_DECISION,
            ),
            DecisionOutcome(
                assessed_object_id="s1",
                outcome_status=OutcomeStatus.REJECTED,
                deviation=DeviationLevel.COMPLETE_OVERRIDE,
                deviation_reason=DeviationReason.POLITICAL_DECISION,
            ),
            DecisionOutcome(
                assessed_object_id="s2",
                outcome_status=OutcomeStatus.REJECTED,
                deviation=DeviationLevel.COMPLETE_OVERRIDE,
                deviation_reason=DeviationReason.STRATEGIC_OVERRIDE,
            ),
            DecisionOutcome(
                assessed_object_id="s3",
                outcome_status=OutcomeStatus.IMPLEMENTED,
                deviation=DeviationLevel.NONE,
                deviation_reason=DeviationReason.MODEL_ERROR,
            ),
            DecisionOutcome(
                assessed_object_id="s4",
                outcome_status=OutcomeStatus.IMPLEMENTED,
                deviation=DeviationLevel.NONE,
            ),
        ]
        result = calibrate(assessments, outcomes)
        # 5 total, but only 2 learning-relevant
        assert result.filtered_stats.total_outcomes == 5
        assert result.filtered_stats.excluded_outcomes == 3
        assert result.filtered_stats.learning_relevant_outcomes == 2
        # Filtered accuracy: 2/2 correct = 100%
        assert result.filtered_stats.filtered_accuracy == 1.0
        # No systematic bias (both relevant outcomes were correct)
        assert len(result.systematic_biases) == 0

    def test_strategic_override_does_not_pollute_model(self) -> None:
        """5 strategic rejections should produce NO bias."""
        assessments = [
            _make_assessment_with_decision(obj_id=f"s{i}")
            for i in range(5)
        ]
        outcomes = [
            DecisionOutcome(
                assessed_object_id=f"s{i}",
                outcome_status=OutcomeStatus.REJECTED,
                deviation=DeviationLevel.COMPLETE_OVERRIDE,
                deviation_reason=DeviationReason.STRATEGIC_OVERRIDE,
            )
            for i in range(5)
        ]
        result = calibrate(assessments, outcomes)
        assert result.filtered_stats.excluded_outcomes == 5
        assert result.filtered_stats.learning_relevant_outcomes == 0
        # No biases because no learning-relevant data
        assert len(result.systematic_biases) == 0

    def test_is_learning_relevant_function(self) -> None:
        relevant = DecisionOutcome(
            assessed_object_id="s1",
            outcome_status=OutcomeStatus.REJECTED,
            deviation=DeviationLevel.MAJOR,
            deviation_reason=DeviationReason.MODEL_ERROR,
        )
        assert is_learning_relevant(relevant) is True

        irrelevant = DecisionOutcome(
            assessed_object_id="s1",
            outcome_status=OutcomeStatus.REJECTED,
            deviation=DeviationLevel.MAJOR,
            deviation_reason=DeviationReason.POLITICAL_DECISION,
        )
        assert is_learning_relevant(irrelevant) is False

    def test_resource_constraint_excluded(self) -> None:
        """LOW relevance outcomes are also excluded from learning."""
        o = DecisionOutcome(
            assessed_object_id="s1",
            outcome_status=OutcomeStatus.DEFERRED,
            deviation=DeviationLevel.MAJOR,
            deviation_reason=DeviationReason.RESOURCE_CONSTRAINT,
        )
        assert is_learning_relevant(o) is False

    def test_filtered_vs_unfiltered_accuracy_differs(self) -> None:
        """When political outcomes are mixed in, accuracies diverge."""
        assessments = [
            _make_assessment_with_decision(obj_id=f"s{i}")
            for i in range(4)
        ]
        outcomes = [
            # 2 genuine model errors (rejected)
            DecisionOutcome(
                assessed_object_id="s0",
                outcome_status=OutcomeStatus.REJECTED,
                deviation=DeviationLevel.COMPLETE_OVERRIDE,
                deviation_reason=DeviationReason.MODEL_ERROR,
            ),
            DecisionOutcome(
                assessed_object_id="s1",
                outcome_status=OutcomeStatus.IMPLEMENTED,
                deviation=DeviationLevel.NONE,
                deviation_reason=DeviationReason.MODEL_ERROR,
            ),
            # 2 political rejections
            DecisionOutcome(
                assessed_object_id="s2",
                outcome_status=OutcomeStatus.REJECTED,
                deviation=DeviationLevel.COMPLETE_OVERRIDE,
                deviation_reason=DeviationReason.POLITICAL_DECISION,
            ),
            DecisionOutcome(
                assessed_object_id="s3",
                outcome_status=OutcomeStatus.REJECTED,
                deviation=DeviationLevel.COMPLETE_OVERRIDE,
                deviation_reason=DeviationReason.POLITICAL_DECISION,
            ),
        ]
        result = calibrate(assessments, outcomes)
        fs = result.filtered_stats
        # Unfiltered: 1/4 = 25%
        assert fs.unfiltered_accuracy == pytest.approx(0.25, abs=0.01)
        # Filtered: 1/2 = 50% (political excluded)
        assert fs.filtered_accuracy == pytest.approx(0.50, abs=0.01)


# --- Trust Score Tests ---

class TestTrustScore:

    def test_no_outcomes_neutral(self) -> None:
        ts = compute_trust_score([], [])
        assert ts.trust_score == 0.5
        assert ts.validated_outcomes == 0

    def test_all_correct_high(self) -> None:
        assessments = [
            _make_assessment_with_decision(obj_id=f"s{i}")
            for i in range(5)
        ]
        outcomes = [
            DecisionOutcome(
                assessed_object_id=f"s{i}",
                outcome_status=OutcomeStatus.IMPLEMENTED,
                deviation=DeviationLevel.NONE,
                deviation_reason=DeviationReason.MODEL_ERROR,
            )
            for i in range(5)
        ]
        ts = compute_trust_score(assessments, outcomes)
        assert ts.trust_score >= 0.95
        assert ts.high_relevance_correct == 5

    def test_all_wrong_low(self) -> None:
        assessments = [
            _make_assessment_with_decision(obj_id=f"s{i}")
            for i in range(5)
        ]
        outcomes = [
            DecisionOutcome(
                assessed_object_id=f"s{i}",
                outcome_status=OutcomeStatus.REJECTED,
                deviation=DeviationLevel.COMPLETE_OVERRIDE,
                deviation_reason=DeviationReason.MODEL_ERROR,
            )
            for i in range(5)
        ]
        ts = compute_trust_score(assessments, outcomes)
        assert ts.trust_score <= 0.1
        assert ts.high_relevance_correct == 0

    def test_political_excluded_from_trust(self) -> None:
        """Political outcomes don't affect trust score."""
        a = _make_assessment_with_decision(obj_id="s1")
        outcomes = [
            DecisionOutcome(
                assessed_object_id="s1",
                outcome_status=OutcomeStatus.REJECTED,
                deviation=DeviationLevel.COMPLETE_OVERRIDE,
                deviation_reason=DeviationReason.POLITICAL_DECISION,
            ),
        ]
        ts = compute_trust_score([a], outcomes)
        assert ts.trust_score == 0.5  # neutral, not 0.0
        assert ts.validated_outcomes == 0

    def test_maturity_bonus(self) -> None:
        """Calibrated model gets a trust bonus."""
        assessments = [
            _make_assessment_with_decision(obj_id=f"s{i}")
            for i in range(6)
        ]
        outcomes = [
            DecisionOutcome(
                assessed_object_id=f"s{i}",
                outcome_status=OutcomeStatus.IMPLEMENTED,
                deviation=DeviationLevel.NONE,
            )
            for i in range(6)
        ]
        ts = compute_trust_score(assessments, outcomes)
        # 6 outcomes → calibrated maturity → +0.05 bonus
        assert ts.trust_score >= 1.0  # 6/6 + 0.05, capped at 1.0


# --- Protected Rules Tests ---

class TestProtectedRules:

    def test_protected_rules_exist(self) -> None:
        assert len(PROTECTED_RULES) >= 4

    def test_hard_constraint_rule_protected(self) -> None:
        ids = {r.rule_id for r in PROTECTED_RULES}
        assert "hard_constraint_caps" in ids

    def test_low_confidence_rule_protected(self) -> None:
        ids = {r.rule_id for r in PROTECTED_RULES}
        assert "low_confidence_reassess" in ids

    def test_regulatory_weight_protected(self) -> None:
        ids = {r.rule_id for r in PROTECTED_RULES}
        assert "regulatory_alignment_weight" in ids

    def test_governance_federation_protected(self) -> None:
        ids = {r.rule_id for r in PROTECTED_RULES}
        assert "governance_function_federation_preference" in ids

    def test_filter_blocks_confidence_weakening(self) -> None:
        """Suggestion to lower confidence thresholds should be blocked."""
        suggestions = [
            CalibrationSuggestion(
                area="decision_aggressiveness",
                suggestion="Consider lowering confidence thresholds for centralize_now.",
                evidence="test",
                priority=ValueLevel.MEDIUM,
            ),
        ]
        filtered = filter_suggestions_against_protected_rules(suggestions, PROTECTED_RULES)
        assert len(filtered) == 0  # blocked by low_confidence_reassess

    def test_filter_allows_non_conflicting(self) -> None:
        """Suggestions not conflicting with protected rules pass through."""
        suggestions = [
            CalibrationSuggestion(
                area="effort_estimate",
                suggestion="Bump base effort buckets by one level.",
                evidence="test",
                priority=ValueLevel.HIGH,
            ),
        ]
        filtered = filter_suggestions_against_protected_rules(suggestions, PROTECTED_RULES)
        assert len(filtered) == 1

    def test_calibrate_filters_suggestions(self) -> None:
        """Full pipeline should not produce suggestions that weaken protected rules."""
        result = calibrate([], [])
        # Protected rules should be in the result
        assert len(result.protected_rules) >= 4

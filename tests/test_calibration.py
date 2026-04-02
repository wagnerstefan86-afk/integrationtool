"""Tests for calibration engine.

Covers:
- Model maturity determination
- Single outcome comparison
- Systematic bias detection
- Adjustment suggestion generation
- Confidence adjustment computation
- Full calibration pipeline
- Outcome model validation
- Report integration
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
    CompletenessResult,
    ConfidenceLevel,
    Decision,
    DecisionOutcome,
    DecisionResult,
    DeviationLevel,
    DurationCategory,
    EffortEstimate,
    HarmonizationClassification,
    HarmonizationDegree,
    HarmonizationResult,
    ImplementationImpact,
    InterfaceComplexityResult,
    ModelMaturityLevel,
    OutcomeStatus,
    TargetOperatingModel,
    ValueIndicators,
    ValueLevel,
)
from harmonizer.scoring.calibration_engine import (
    calibrate,
    compare_single_outcome,
    compute_confidence_adjustment,
    detect_systematic_biases,
    determine_model_maturity,
    generate_suggestions,
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

"""Calibration engine for comparing predicted decisions against actual outcomes.

Provides:
1. Per-stream predicted-vs-actual comparison
2. Systematic bias detection across all outcomes
3. Concrete adjustment suggestions for the decision engine
4. Model maturity assessment based on outcome count
5. Confidence adjustment factor derived from prediction accuracy

Design principles:
- Deterministic: same outcome data always produces same calibration
- Transparent: every comparison and suggestion has traceable evidence
- No statistical models — uses simple rule-based deviation detection
- Calibration adjustments are suggestions, not automatic changes

Assumption: Calibration requires at least 1 outcome to produce any
comparison, but meaningful bias detection requires 5+ outcomes.

Assumption: The effort bucket comparison uses ordinal mapping
("0-1"=0, "1-3"=1, "3-6"=2, "6-12"=3, "12+"=4) to detect systematic
over/underestimation.

Assumption: A "correct" decision is one where outcome_status is
"implemented" with deviation "none" or "minor". All other outcomes
indicate the model was partially or fully wrong for that case.
"""

from harmonizer.models.assessment import (
    Assessment,
    CalibrationDeviation,
    CalibrationResult,
    CalibrationSuggestion,
    CompletenessResult,
    ConfidenceLevel,
    Decision,
    DecisionOutcome,
    DeviationLevel,
    DurationCategory,
    ModelMaturityLevel,
    OutcomeStatus,
    ValueLevel,
)


# --- Effort Bucket Ordinal Mapping ---

_EFFORT_ORDINAL: dict[str, int] = {
    "0-1": 0,
    "1-3": 1,
    "3-6": 2,
    "6-12": 3,
    "12+": 4,
}

_DURATION_ORDINAL: dict[DurationCategory, int] = {
    DurationCategory.SHORT: 0,
    DurationCategory.MEDIUM: 1,
    DurationCategory.LONG: 2,
}

_VALUE_ORDINAL: dict[ValueLevel, int] = {
    ValueLevel.LOW: 0,
    ValueLevel.MEDIUM: 1,
    ValueLevel.HIGH: 2,
}


def _compare_ordinal(predicted: int, actual: int) -> str:
    if predicted > actual:
        return "overestimated"
    elif predicted < actual:
        return "underestimated"
    return "accurate"


# --- Model Maturity ---

def determine_model_maturity(outcome_count: int) -> ModelMaturityLevel:
    """Determine model maturity based on number of recorded outcomes.

    Thresholds:
    - 0 outcomes: initial
    - 1-4 outcomes: learning
    - 5-9 outcomes: calibrated
    - 10+ outcomes: stable
    """
    if outcome_count == 0:
        return ModelMaturityLevel.INITIAL
    elif outcome_count < 5:
        return ModelMaturityLevel.LEARNING
    elif outcome_count < 10:
        return ModelMaturityLevel.CALIBRATED
    return ModelMaturityLevel.STABLE


# --- Per-Outcome Comparison ---

def compare_single_outcome(
    assessment: Assessment,
    outcome: DecisionOutcome,
) -> list[CalibrationDeviation]:
    """Compare a single prediction against its actual outcome.

    Returns a list of deviations across dimensions.
    """
    deviations: list[CalibrationDeviation] = []
    dr = assessment.decision_result
    if dr is None:
        return deviations

    # Decision vs Outcome status
    if outcome.outcome_status == OutcomeStatus.IMPLEMENTED:
        if outcome.deviation in (DeviationLevel.NONE, DeviationLevel.MINOR):
            deviations.append(CalibrationDeviation(
                dimension="decision",
                predicted=dr.decision.value,
                actual=f"implemented ({outcome.deviation.value} deviation)",
                direction="accurate",
            ))
        else:
            deviations.append(CalibrationDeviation(
                dimension="decision",
                predicted=dr.decision.value,
                actual=f"implemented with {outcome.deviation.value} deviation",
                direction="overestimated" if dr.decision in (
                    Decision.CENTRALIZE_NOW, Decision.CENTRALIZE_LATER
                ) else "underestimated",
            ))
    elif outcome.outcome_status == OutcomeStatus.REJECTED:
        deviations.append(CalibrationDeviation(
            dimension="decision",
            predicted=dr.decision.value,
            actual="rejected",
            direction="overestimated",
        ))
    elif outcome.outcome_status == OutcomeStatus.DEFERRED:
        deviations.append(CalibrationDeviation(
            dimension="decision",
            predicted=dr.decision.value,
            actual="deferred",
            direction="overestimated",  # recommended action was too aggressive
        ))

    # Effort comparison
    if outcome.actual_implementation and dr.effort_estimate:
        pred_effort = _EFFORT_ORDINAL.get(dr.effort_estimate.person_months_bucket, 2)
        actual_effort = _EFFORT_ORDINAL.get(outcome.actual_implementation.actual_effort_bucket, 2)
        deviations.append(CalibrationDeviation(
            dimension="effort",
            predicted=dr.effort_estimate.person_months_bucket,
            actual=outcome.actual_implementation.actual_effort_bucket,
            direction=_compare_ordinal(pred_effort, actual_effort),
        ))

        # Duration comparison
        pred_dur = _DURATION_ORDINAL[dr.effort_estimate.implementation_duration]
        actual_dur = _DURATION_ORDINAL[outcome.actual_implementation.actual_duration]
        deviations.append(CalibrationDeviation(
            dimension="duration",
            predicted=dr.effort_estimate.implementation_duration.value,
            actual=outcome.actual_implementation.actual_duration.value,
            direction=_compare_ordinal(pred_dur, actual_dur),
        ))

        # Complexity comparison
        if dr.implementation_impact:
            pred_complex = _VALUE_ORDINAL[dr.implementation_impact.implementation_complexity]
            actual_complex = _VALUE_ORDINAL[outcome.actual_implementation.actual_complexity]
            deviations.append(CalibrationDeviation(
                dimension="complexity",
                predicted=dr.implementation_impact.implementation_complexity.value,
                actual=outcome.actual_implementation.actual_complexity.value,
                direction=_compare_ordinal(pred_complex, actual_complex),
            ))

    # Impact comparison
    if outcome.actual_impact and dr.value_indicators:
        pred_bv = _VALUE_ORDINAL[dr.value_indicators.expected_business_value]
        actual_bv = _VALUE_ORDINAL[outcome.actual_impact.business_value_realized]
        deviations.append(CalibrationDeviation(
            dimension="business_value",
            predicted=dr.value_indicators.expected_business_value.value,
            actual=outcome.actual_impact.business_value_realized.value,
            direction=_compare_ordinal(pred_bv, actual_bv),
        ))

        pred_op = _VALUE_ORDINAL[dr.value_indicators.operational_impact]
        actual_op = _VALUE_ORDINAL[outcome.actual_impact.operational_improvement]
        deviations.append(CalibrationDeviation(
            dimension="operational_impact",
            predicted=dr.value_indicators.operational_impact.value,
            actual=outcome.actual_impact.operational_improvement.value,
            direction=_compare_ordinal(pred_op, actual_op),
        ))

    return deviations


# --- Systematic Bias Detection ---

def detect_systematic_biases(
    all_deviations: list[CalibrationDeviation],
) -> list[str]:
    """Detect systematic biases from aggregated deviations.

    A bias is "systematic" if the same dimension is consistently
    over- or underestimated across multiple outcomes.

    Threshold: if >=60% of outcomes for a dimension deviate in
    the same direction, it's a systematic bias.
    """
    # Group deviations by dimension
    by_dimension: dict[str, list[str]] = {}
    for dev in all_deviations:
        by_dimension.setdefault(dev.dimension, []).append(dev.direction)

    biases: list[str] = []
    for dim, directions in by_dimension.items():
        total = len(directions)
        if total < 2:
            continue
        over_count = sum(1 for d in directions if d == "overestimated")
        under_count = sum(1 for d in directions if d == "underestimated")

        if over_count / total >= 0.6:
            biases.append(
                f"{dim}: systematically overestimated "
                f"({over_count}/{total} cases)"
            )
        elif under_count / total >= 0.6:
            biases.append(
                f"{dim}: systematically underestimated "
                f"({under_count}/{total} cases)"
            )

    return biases


# --- Adjustment Suggestions ---

def generate_suggestions(
    biases: list[str],
    all_deviations: list[CalibrationDeviation],
    outcome_count: int,
) -> list[CalibrationSuggestion]:
    """Generate concrete adjustment suggestions from detected biases.

    Maps known bias patterns to actionable suggestions.
    """
    suggestions: list[CalibrationSuggestion] = []

    for bias in biases:
        dim = bias.split(":")[0].strip()

        if dim == "decision" and "overestimated" in bias:
            suggestions.append(CalibrationSuggestion(
                area="decision_aggressiveness",
                suggestion=(
                    "Decision engine is too aggressive — recommends centralization "
                    "more often than warranted. Consider raising the centralizability "
                    "threshold from 0.50 to 0.55 or requiring high confidence for "
                    "centralize_now decisions."
                ),
                evidence=bias,
                priority=ValueLevel.HIGH,
            ))
        elif dim == "decision" and "underestimated" in bias:
            suggestions.append(CalibrationSuggestion(
                area="decision_aggressiveness",
                suggestion=(
                    "Decision engine is too conservative — organizations frequently "
                    "go beyond the recommended scope. Consider lowering thresholds "
                    "for centralization decisions."
                ),
                evidence=bias,
                priority=ValueLevel.MEDIUM,
            ))
        elif dim == "effort" and "underestimated" in bias:
            suggestions.append(CalibrationSuggestion(
                area="effort_estimate",
                suggestion=(
                    "Effort estimates are systematically too low. Consider bumping "
                    "base effort buckets by one level or increasing the interface "
                    "complexity penalty on effort."
                ),
                evidence=bias,
                priority=ValueLevel.HIGH,
            ))
        elif dim == "effort" and "overestimated" in bias:
            suggestions.append(CalibrationSuggestion(
                area="effort_estimate",
                suggestion=(
                    "Effort estimates are systematically too high. Consider reducing "
                    "base effort buckets or lowering the complexity penalty."
                ),
                evidence=bias,
                priority=ValueLevel.LOW,
            ))
        elif dim == "complexity" and "underestimated" in bias:
            suggestions.append(CalibrationSuggestion(
                area="interface_complexity",
                suggestion=(
                    "Interface complexity is consistently underestimated. Consider "
                    "increasing the cross-area weight or lowering the normalization "
                    "ceiling for interface count."
                ),
                evidence=bias,
                priority=ValueLevel.MEDIUM,
            ))
        elif dim == "complexity" and "overestimated" in bias:
            suggestions.append(CalibrationSuggestion(
                area="interface_complexity",
                suggestion=(
                    "Interface complexity is consistently overestimated. Consider "
                    "relaxing the normalization ceilings."
                ),
                evidence=bias,
                priority=ValueLevel.LOW,
            ))
        elif dim == "business_value" and "overestimated" in bias:
            suggestions.append(CalibrationSuggestion(
                area="value_indicators",
                suggestion=(
                    "Business value predictions are too optimistic. Consider "
                    "raising the threshold for 'high' business value or weighting "
                    "prioritization inputs more conservatively."
                ),
                evidence=bias,
                priority=ValueLevel.MEDIUM,
            ))
        elif dim == "business_value" and "underestimated" in bias:
            suggestions.append(CalibrationSuggestion(
                area="value_indicators",
                suggestion=(
                    "Business value predictions are too pessimistic. Consider "
                    "lowering the threshold for 'high' business value."
                ),
                evidence=bias,
                priority=ValueLevel.LOW,
            ))
        elif dim == "operational_impact":
            direction = "overestimated" if "overestimated" in bias else "underestimated"
            suggestions.append(CalibrationSuggestion(
                area="value_indicators",
                suggestion=(
                    f"Operational impact is systematically {direction}. "
                    "Review the weighting of operational_alignment and "
                    "maturity_gap in the value indicator computation."
                ),
                evidence=bias,
                priority=ValueLevel.MEDIUM,
            ))

    return suggestions


# --- Confidence Adjustment ---

def compute_confidence_adjustment(
    accuracy_rate: float,
    model_maturity: ModelMaturityLevel,
) -> float:
    """Compute a confidence adjustment factor based on calibration accuracy.

    Returns a value in [-0.5, +0.5] that can be applied to completeness
    scores to reflect historical model accuracy.

    Rules:
    - initial maturity: no adjustment (0.0)
    - accuracy >= 0.80 and maturity >= calibrated: boost +0.1
    - accuracy >= 0.60 and maturity >= learning: no change (0.0)
    - accuracy < 0.60 and maturity >= learning: penalty -0.1
    - accuracy < 0.40 and maturity >= calibrated: penalty -0.2

    Assumption: These adjustments are intentionally conservative.
    The goal is to flag potential issues, not to dramatically change
    the confidence system.
    """
    if model_maturity == ModelMaturityLevel.INITIAL:
        return 0.0

    if accuracy_rate >= 0.80 and model_maturity in (
        ModelMaturityLevel.CALIBRATED, ModelMaturityLevel.STABLE,
    ):
        return 0.10
    elif accuracy_rate >= 0.60:
        return 0.0
    elif accuracy_rate >= 0.40:
        return -0.10
    else:
        if model_maturity in (ModelMaturityLevel.CALIBRATED, ModelMaturityLevel.STABLE):
            return -0.20
        return -0.10


# --- Main Calibration Function ---

def calibrate(
    assessments: list[Assessment],
    outcomes: list[DecisionOutcome],
) -> CalibrationResult:
    """Run calibration by comparing all outcomes against their predictions.

    Steps:
    1. Match outcomes to assessments by assessed_object_id
    2. Compare each outcome against its prediction
    3. Detect systematic biases
    4. Generate adjustment suggestions
    5. Compute confidence adjustment factor

    Returns a CalibrationResult with all findings.
    """
    assessment_index = {a.assessed_object_id: a for a in assessments}

    all_deviations: list[CalibrationDeviation] = []
    correct_count = 0
    total_matched = 0

    for outcome in outcomes:
        assessment = assessment_index.get(outcome.assessed_object_id)
        if assessment is None or assessment.decision_result is None:
            continue

        total_matched += 1
        deviations = compare_single_outcome(assessment, outcome)
        all_deviations.extend(deviations)

        # Count as correct if implemented with none/minor deviation
        if (
            outcome.outcome_status == OutcomeStatus.IMPLEMENTED
            and outcome.deviation in (DeviationLevel.NONE, DeviationLevel.MINOR)
        ):
            correct_count += 1

    # Accuracy
    accuracy_rate = correct_count / total_matched if total_matched > 0 else 0.0
    accuracy_rate = round(accuracy_rate, 4)

    # Maturity
    model_maturity = determine_model_maturity(total_matched)

    # Biases
    biases = detect_systematic_biases(all_deviations)

    # Suggestions
    suggestions = generate_suggestions(biases, all_deviations, total_matched)

    # Confidence adjustment
    conf_adj = compute_confidence_adjustment(accuracy_rate, model_maturity)

    # Rationale
    parts = [f"Analyzed {total_matched} outcome(s)"]
    parts.append(f"Accuracy: {accuracy_rate:.0%} ({correct_count}/{total_matched} correct)")
    parts.append(f"Model maturity: {model_maturity.value}")
    if biases:
        parts.append(f"Systematic biases detected: {len(biases)}")
    if conf_adj != 0.0:
        direction = "boost" if conf_adj > 0 else "penalty"
        parts.append(f"Confidence {direction}: {conf_adj:+.2f}")

    return CalibrationResult(
        outcomes_analyzed=total_matched,
        accuracy_rate=accuracy_rate,
        deviations=all_deviations,
        systematic_biases=biases,
        suggestions=suggestions,
        model_maturity=model_maturity,
        confidence_adjustment=conf_adj,
        rationale=". ".join(parts) + ".",
    )

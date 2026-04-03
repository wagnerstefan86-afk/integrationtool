"""Calibration engine for comparing predicted decisions against actual outcomes.

Provides:
1. Per-stream predicted-vs-actual comparison
2. Systematic bias detection across all outcomes
3. Concrete adjustment suggestions for the decision engine
4. Model maturity assessment based on outcome count
5. Confidence adjustment factor derived from prediction accuracy
6. Learning relevance filtering (political/strategic overrides excluded)
7. Trust score based on validated high-relevance outcomes
8. Protected rules that cannot be weakened by calibration
9. Filtered vs unfiltered calibration statistics

Design principles:
- Deterministic: same outcome data always produces same calibration
- Transparent: every comparison and suggestion has traceable evidence
- No statistical models — uses simple rule-based deviation detection
- Calibration adjustments are suggestions, not automatic changes
- Political/strategic overrides NEVER influence model calibration

Assumption: Not every deviation is a model error. Deviations caused by
political decisions, strategic overrides, or resource constraints are
legitimate governance actions and must be separated from genuine model
errors before calibration.

Assumption: Only outcomes with learning_relevance high or medium should
influence bias detection. Low-relevance outcomes are recorded but do not
affect the model. None-relevance outcomes are fully excluded.

Assumption: Protected rules (regulatory constraints, hard constraint
handling, minimum confidence) must never be weakened even if calibration
data suggests otherwise. These are governance-mandated guardrails.
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
    DeviationReason,
    DurationCategory,
    FilteredCalibrationStats,
    LearningRelevance,
    ModelMaturityLevel,
    OutcomeStatus,
    ProtectedRule,
    TrustScoreResult,
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


# --- Learning Relevance Mapping ---

DEVIATION_REASON_RELEVANCE: dict[DeviationReason, LearningRelevance] = {
    DeviationReason.MODEL_ERROR: LearningRelevance.HIGH,
    DeviationReason.INCOMPLETE_DATA: LearningRelevance.MEDIUM,
    DeviationReason.CHANGED_CONTEXT: LearningRelevance.MEDIUM,
    DeviationReason.POLITICAL_DECISION: LearningRelevance.NONE,
    DeviationReason.STRATEGIC_OVERRIDE: LearningRelevance.NONE,
    DeviationReason.RESOURCE_CONSTRAINT: LearningRelevance.LOW,
}


def resolve_learning_relevance(outcome: DecisionOutcome) -> LearningRelevance:
    """Determine learning relevance for an outcome.

    If explicitly set on the outcome, use that value.
    If deviation_reason is set, derive from the mapping.
    Otherwise, default to HIGH (assume model error unless proven otherwise).
    """
    if outcome.learning_relevance is not None:
        return outcome.learning_relevance
    if outcome.deviation_reason is not None:
        return DEVIATION_REASON_RELEVANCE[outcome.deviation_reason]
    # Default: if no reason given, assume the deviation is learning-relevant
    return LearningRelevance.HIGH


def is_learning_relevant(outcome: DecisionOutcome) -> bool:
    """Check if an outcome should influence model calibration.

    Only outcomes with learning_relevance HIGH or MEDIUM are used
    for bias detection. LOW and NONE are excluded.
    """
    relevance = resolve_learning_relevance(outcome)
    return relevance in (LearningRelevance.HIGH, LearningRelevance.MEDIUM)


# --- Protected Rules ---

# These rules are governance-mandated and must not be weakened by calibration.
# Even if outcome data suggests these rules are "too strict", they remain
# because they serve regulatory, compliance, or risk management purposes.

PROTECTED_RULES: list[ProtectedRule] = [
    ProtectedRule(
        rule_id="hard_constraint_caps",
        description="Hard constraints always cap classification downward",
        reason="Regulatory and structural constraints are non-negotiable governance guardrails",
    ),
    ProtectedRule(
        rule_id="low_confidence_reassess",
        description="Low confidence always produces reassess_after_data_completion decision",
        reason="Decisions on insufficient data create false precision and unacceptable risk",
    ),
    ProtectedRule(
        rule_id="regulatory_alignment_weight",
        description="Regulatory alignment dimension weight must not drop below 0.10",
        reason="Regulatory requirements are legally binding and must always factor into scoring",
    ),
    ProtectedRule(
        rule_id="governance_function_federation_preference",
        description="Governance functions prefer federated model unless centralization degree > 0.80",
        reason="Governance inherently requires local accountability; premature centralization "
               "creates compliance gaps",
    ),
]


def filter_suggestions_against_protected_rules(
    suggestions: list[CalibrationSuggestion],
    protected: list[ProtectedRule],
) -> list[CalibrationSuggestion]:
    """Remove or flag suggestions that would weaken protected rules.

    Mapping from suggestion areas to protected rule IDs:
    - Suggestions targeting "decision_aggressiveness" that recommend LOWERING
      thresholds are checked against low_confidence_reassess
    - Suggestions targeting regulatory weights are checked against
      regulatory_alignment_weight
    """
    protected_ids = {r.rule_id for r in protected}
    filtered: list[CalibrationSuggestion] = []

    for sug in suggestions:
        blocked = False

        # Check if suggestion conflicts with protected rules
        if sug.area == "decision_aggressiveness" and "lower" in sug.suggestion.lower():
            if "low_confidence_reassess" in protected_ids:
                # Don't block all aggressiveness suggestions, only those
                # that would weaken the reassess-on-low-confidence rule
                if "confidence" in sug.suggestion.lower():
                    blocked = True

        if sug.area == "regulatory_alignment" and "reduce" in sug.suggestion.lower():
            if "regulatory_alignment_weight" in protected_ids:
                blocked = True

        if not blocked:
            filtered.append(sug)

    return filtered


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
            direction="overestimated",
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
    """Generate concrete adjustment suggestions from detected biases."""
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

    Returns a value in [-0.5, +0.5].
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


# --- Trust Score ---

def compute_trust_score(
    assessments: list[Assessment],
    outcomes: list[DecisionOutcome],
) -> TrustScoreResult:
    """Compute model trust score based on validated high-relevance outcomes.

    Trust is built on outcomes where:
    1. The deviation reason is model_error or incomplete_data (high/medium relevance)
    2. The model predicted correctly

    Score formula:
    - Base: high_relevance_correct / high_relevance_total
    - Bonus: +0.05 if maturity >= calibrated
    - Capped at 1.0

    If no high-relevance outcomes exist, trust defaults to 0.5 (neutral).
    """
    assessment_index = {a.assessed_object_id: a for a in assessments}

    high_correct = 0
    high_total = 0
    validated = 0

    for outcome in outcomes:
        assessment = assessment_index.get(outcome.assessed_object_id)
        if assessment is None or assessment.decision_result is None:
            continue

        relevance = resolve_learning_relevance(outcome)
        if relevance not in (LearningRelevance.HIGH, LearningRelevance.MEDIUM):
            continue

        validated += 1
        high_total += 1
        if (
            outcome.outcome_status == OutcomeStatus.IMPLEMENTED
            and outcome.deviation in (DeviationLevel.NONE, DeviationLevel.MINOR)
        ):
            high_correct += 1

    if high_total == 0:
        return TrustScoreResult(
            trust_score=0.5,
            validated_outcomes=0,
            high_relevance_correct=0,
            high_relevance_total=0,
            rationale="No high-relevance outcomes — trust score is neutral (0.50).",
        )

    base = high_correct / high_total
    maturity = determine_model_maturity(high_total)
    bonus = 0.05 if maturity in (ModelMaturityLevel.CALIBRATED, ModelMaturityLevel.STABLE) else 0.0
    score = round(min(1.0, base + bonus), 4)

    parts = [f"Trust score: {score:.2f}"]
    parts.append(f"{high_correct}/{high_total} high-relevance outcomes correct")
    if bonus > 0:
        parts.append(f"+{bonus:.2f} maturity bonus ({maturity.value})")

    return TrustScoreResult(
        trust_score=score,
        validated_outcomes=validated,
        high_relevance_correct=high_correct,
        high_relevance_total=high_total,
        rationale=". ".join(parts) + ".",
    )


# --- Deviation Reason Summary ---

def summarize_deviation_reasons(outcomes: list[DecisionOutcome]) -> list[str]:
    """Summarize why decisions deviated from recommendations."""
    reason_counts: dict[str, int] = {}
    for outcome in outcomes:
        if outcome.deviation in (DeviationLevel.NONE,):
            continue  # No deviation, no reason needed
        reason = outcome.deviation_reason
        if reason:
            label = reason.value
        else:
            label = "unclassified"
        reason_counts[label] = reason_counts.get(label, 0) + 1

    return [f"{reason}: {count} outcome(s)" for reason, count in sorted(reason_counts.items())]


# --- Main Calibration Function ---

def calibrate(
    assessments: list[Assessment],
    outcomes: list[DecisionOutcome],
) -> CalibrationResult:
    """Run calibration by comparing outcomes against predictions.

    Phase 7 filtering logic:
    1. ALL outcomes are compared for the full deviation picture
    2. Only learning-relevant outcomes (high/medium) influence bias detection
    3. Political/strategic overrides are recorded but excluded from learning
    4. Suggestions are filtered against protected rules
    5. Trust score is computed from high-relevance outcomes only
    """
    assessment_index = {a.assessed_object_id: a for a in assessments}

    # --- Pass 1: Compare ALL outcomes (unfiltered) ---
    all_deviations: list[CalibrationDeviation] = []
    unfiltered_correct = 0
    total_matched = 0

    # --- Pass 2: Filtered deviations (learning-relevant only) ---
    filtered_deviations: list[CalibrationDeviation] = []
    filtered_correct = 0
    filtered_total = 0

    excluded_count = 0
    excluded_reasons: list[str] = []

    for outcome in outcomes:
        assessment = assessment_index.get(outcome.assessed_object_id)
        if assessment is None or assessment.decision_result is None:
            continue

        total_matched += 1
        deviations = compare_single_outcome(assessment, outcome)
        all_deviations.extend(deviations)

        is_correct = (
            outcome.outcome_status == OutcomeStatus.IMPLEMENTED
            and outcome.deviation in (DeviationLevel.NONE, DeviationLevel.MINOR)
        )
        if is_correct:
            unfiltered_correct += 1

        # Filtering
        if is_learning_relevant(outcome):
            filtered_total += 1
            filtered_deviations.extend(deviations)
            if is_correct:
                filtered_correct += 1
        else:
            excluded_count += 1
            relevance = resolve_learning_relevance(outcome)
            reason = outcome.deviation_reason
            reason_str = reason.value if reason else "no_reason"
            excluded_reasons.append(
                f"{outcome.assessed_object_id}: {reason_str} "
                f"(learning_relevance={relevance.value})"
            )

    # Accuracy rates
    unfiltered_accuracy = round(
        unfiltered_correct / total_matched if total_matched > 0 else 0.0, 4,
    )
    filtered_accuracy = round(
        filtered_correct / filtered_total if filtered_total > 0 else 0.0, 4,
    )

    # Use FILTERED accuracy as the official accuracy rate
    accuracy_rate = filtered_accuracy if filtered_total > 0 else unfiltered_accuracy

    # Maturity based on learning-relevant outcomes
    model_maturity = determine_model_maturity(filtered_total)

    # Biases from FILTERED deviations only
    biases = detect_systematic_biases(filtered_deviations)

    # Suggestions from filtered biases, then filter against protected rules
    raw_suggestions = generate_suggestions(biases, filtered_deviations, filtered_total)
    suggestions = filter_suggestions_against_protected_rules(raw_suggestions, PROTECTED_RULES)

    # Confidence adjustment from filtered accuracy
    conf_adj = compute_confidence_adjustment(accuracy_rate, model_maturity)

    # Trust score
    trust = compute_trust_score(assessments, outcomes)

    # Filtered stats
    filtered_stats = FilteredCalibrationStats(
        total_outcomes=total_matched,
        learning_relevant_outcomes=filtered_total,
        excluded_outcomes=excluded_count,
        excluded_reasons=excluded_reasons,
        unfiltered_accuracy=unfiltered_accuracy,
        filtered_accuracy=filtered_accuracy,
        rationale=(
            f"{filtered_total}/{total_matched} outcomes used for calibration. "
            f"{excluded_count} excluded (political/strategic/low-relevance)."
        ),
    )

    # Deviation reason summary
    deviation_reasons = summarize_deviation_reasons(outcomes)

    # Rationale
    parts = [f"Analyzed {total_matched} outcome(s)"]
    if excluded_count > 0:
        parts.append(f"{excluded_count} excluded from learning (political/strategic)")
    parts.append(
        f"Filtered accuracy: {filtered_accuracy:.0%} "
        f"({filtered_correct}/{filtered_total} correct)"
        if filtered_total > 0 else f"Unfiltered accuracy: {unfiltered_accuracy:.0%}"
    )
    parts.append(f"Model maturity: {model_maturity.value}")
    parts.append(f"Trust score: {trust.trust_score:.2f}")
    if biases:
        parts.append(f"Systematic biases detected: {len(biases)}")
    if conf_adj != 0.0:
        direction = "boost" if conf_adj > 0 else "penalty"
        parts.append(f"Confidence {direction}: {conf_adj:+.2f}")

    return CalibrationResult(
        outcomes_analyzed=total_matched,
        accuracy_rate=accuracy_rate,
        deviations=all_deviations,  # ALL deviations for full picture
        systematic_biases=biases,
        suggestions=suggestions,
        model_maturity=model_maturity,
        confidence_adjustment=conf_adj,
        rationale=". ".join(parts) + ".",
        trust_score=trust,
        protected_rules=list(PROTECTED_RULES),
        filtered_stats=filtered_stats,
        deviation_reasons_summary=deviation_reasons,
    )

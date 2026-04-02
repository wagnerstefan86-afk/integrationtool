"""Deterministic scoring engine for harmonization assessment.

Provides:
1. Weighted scoring with stream-type-specific dimension weights
2. Hard constraint application
3. Stream-level aggregation from subprocess assessments
4. Completeness and confidence evaluation
5. Prioritization scoring
6. Type-specific question score modifier

Aggregation logic (stream from subprocesses):
- If a stream has subprocess assessments, the stream score is computed as
  the weighted average of subprocess scores (equal weight per subprocess),
  combined with any direct stream-level answers.
- Hard constraints from subprocesses propagate upward (union).
- The aggregated score is a blend: 40% direct stream assessment (if present)
  + 60% subprocess average. If no direct stream assessment exists,
  100% subprocess average is used.

Completeness factors:
- Base dimensions answered (6 expected)
- Type-specific questions answered
- Hard constraints explicitly evaluated
- Subprocess assessments present (for stream-level)
- Interface coverage
- Regulatory/tenant data populated on the process model

Confidence mapping:
- completeness >= 75 -> high
- completeness >= 45 -> medium
- completeness < 45  -> low
"""

from harmonizer.models.process import Stream, SubProcess, ProcessInterface, StreamType
from harmonizer.models.assessment import (
    AlignmentDimension,
    Assessment,
    AssessmentAnswer,
    AssessedObjectType,
    CompletenessResult,
    ConfidenceLevel,
    HardConstraint,
    HarmonizationClassification,
    HarmonizationPriority,
    HarmonizationResult,
    PrioritizationInput,
    PrioritizationResult,
    TypeSpecificAnswer,
)
from harmonizer.scoring.questions import get_required_question_ids


# --- Dimension weight profiles per stream type ---

STREAM_TYPE_WEIGHTS: dict[StreamType, dict[AlignmentDimension, float]] = {
    StreamType.PROCESS: {
        AlignmentDimension.REGULATORY_ALIGNMENT: 0.20,
        AlignmentDimension.OPERATIONAL_ALIGNMENT: 0.25,
        AlignmentDimension.TOOLING_ALIGNMENT: 0.20,
        AlignmentDimension.GOVERNANCE_ALIGNMENT: 0.15,
        AlignmentDimension.MATURITY: 0.10,
        AlignmentDimension.LOCAL_NECESSITY: 0.10,
    },
    StreamType.GOVERNANCE_FUNCTION: {
        AlignmentDimension.REGULATORY_ALIGNMENT: 0.30,
        AlignmentDimension.OPERATIONAL_ALIGNMENT: 0.10,
        AlignmentDimension.TOOLING_ALIGNMENT: 0.10,
        AlignmentDimension.GOVERNANCE_ALIGNMENT: 0.30,
        AlignmentDimension.MATURITY: 0.10,
        AlignmentDimension.LOCAL_NECESSITY: 0.10,
    },
    StreamType.SERVICE_DOMAIN: {
        AlignmentDimension.REGULATORY_ALIGNMENT: 0.15,
        AlignmentDimension.OPERATIONAL_ALIGNMENT: 0.25,
        AlignmentDimension.TOOLING_ALIGNMENT: 0.15,
        AlignmentDimension.GOVERNANCE_ALIGNMENT: 0.20,
        AlignmentDimension.MATURITY: 0.10,
        AlignmentDimension.LOCAL_NECESSITY: 0.15,
    },
    StreamType.SUPPORT_FUNCTION: {
        AlignmentDimension.REGULATORY_ALIGNMENT: 0.10,
        AlignmentDimension.OPERATIONAL_ALIGNMENT: 0.30,
        AlignmentDimension.TOOLING_ALIGNMENT: 0.25,
        AlignmentDimension.GOVERNANCE_ALIGNMENT: 0.10,
        AlignmentDimension.MATURITY: 0.15,
        AlignmentDimension.LOCAL_NECESSITY: 0.10,
    },
    StreamType.CAPABILITY_DOMAIN: {
        AlignmentDimension.REGULATORY_ALIGNMENT: 0.10,
        AlignmentDimension.OPERATIONAL_ALIGNMENT: 0.20,
        AlignmentDimension.TOOLING_ALIGNMENT: 0.25,
        AlignmentDimension.GOVERNANCE_ALIGNMENT: 0.15,
        AlignmentDimension.MATURITY: 0.20,
        AlignmentDimension.LOCAL_NECESSITY: 0.10,
    },
    StreamType.PROGRAM_DOMAIN: {
        AlignmentDimension.REGULATORY_ALIGNMENT: 0.15,
        AlignmentDimension.OPERATIONAL_ALIGNMENT: 0.15,
        AlignmentDimension.TOOLING_ALIGNMENT: 0.10,
        AlignmentDimension.GOVERNANCE_ALIGNMENT: 0.30,
        AlignmentDimension.MATURITY: 0.15,
        AlignmentDimension.LOCAL_NECESSITY: 0.15,
    },
}

DEFAULT_WEIGHTS: dict[AlignmentDimension, float] = {
    AlignmentDimension.REGULATORY_ALIGNMENT: 0.25,
    AlignmentDimension.OPERATIONAL_ALIGNMENT: 0.20,
    AlignmentDimension.TOOLING_ALIGNMENT: 0.15,
    AlignmentDimension.GOVERNANCE_ALIGNMENT: 0.20,
    AlignmentDimension.MATURITY: 0.10,
    AlignmentDimension.LOCAL_NECESSITY: 0.10,
}

CLASSIFICATION_THRESHOLDS: list[tuple[float, HarmonizationClassification]] = [
    (0.85, HarmonizationClassification.FULLY_CENTRALIZABLE),
    (0.70, HarmonizationClassification.CENTRAL_METHOD_LOCAL_EXECUTION),
    (0.50, HarmonizationClassification.PARTIALLY_HARMONIZABLE),
    (0.30, HarmonizationClassification.MINIMUM_STANDARD_ONLY),
    (0.00, HarmonizationClassification.CURRENTLY_NOT_HARMONIZABLE),
]

HARD_CONSTRAINT_CAPS: dict[HardConstraint, HarmonizationClassification] = {
    HardConstraint.LEGAL_LOCAL_DIFFERENCE: HarmonizationClassification.MINIMUM_STANDARD_ONLY,
    HardConstraint.TENANT_SEPARATION_BLOCKS_OPERATION: HarmonizationClassification.CENTRAL_METHOD_LOCAL_EXECUTION,
    HardConstraint.SEPARATE_CONTROL_OWNERSHIP: HarmonizationClassification.PARTIALLY_HARMONIZABLE,
    HardConstraint.INSUFFICIENT_DOCUMENTATION: HarmonizationClassification.CURRENTLY_NOT_HARMONIZABLE,
}

_CLASSIFICATION_ORDER: list[HarmonizationClassification] = [
    HarmonizationClassification.FULLY_CENTRALIZABLE,
    HarmonizationClassification.CENTRAL_METHOD_LOCAL_EXECUTION,
    HarmonizationClassification.PARTIALLY_HARMONIZABLE,
    HarmonizationClassification.MINIMUM_STANDARD_ONLY,
    HarmonizationClassification.CURRENTLY_NOT_HARMONIZABLE,
]

_STREAM_TYPE_LABELS: dict[StreamType, str] = {
    StreamType.PROCESS: "process",
    StreamType.GOVERNANCE_FUNCTION: "governance function",
    StreamType.SERVICE_DOMAIN: "service domain",
    StreamType.CAPABILITY_DOMAIN: "capability domain",
    StreamType.SUPPORT_FUNCTION: "support function",
    StreamType.PROGRAM_DOMAIN: "program domain",
}

PRIORITIZATION_WEIGHTS: dict[str, float] = {
    "harmonization_potential": 0.30,
    "operational_relevance": 0.20,
    "governance_compliance_benefit": 0.25,
    "implementation_effort": 0.15,
    "dependencies": 0.10,
}

# Type-specific answers contribute this fraction to the final score as a modifier.
# The base score (from 6 dimensions) has weight (1 - TYPE_SPECIFIC_WEIGHT).
TYPE_SPECIFIC_WEIGHT = 0.15

# Aggregation blend: direct stream assessment vs. subprocess average
STREAM_DIRECT_WEIGHT = 0.40
SUBPROCESS_AGG_WEIGHT = 0.60


def _classification_rank(c: HarmonizationClassification) -> int:
    return _CLASSIFICATION_ORDER.index(c)


def get_weights_for_stream_type(stream_type: StreamType | None) -> dict[AlignmentDimension, float]:
    if stream_type is None:
        return DEFAULT_WEIGHTS
    return STREAM_TYPE_WEIGHTS.get(stream_type, DEFAULT_WEIGHTS)


def compute_weighted_score(
    answers: list[AssessmentAnswer],
    weights: dict[AlignmentDimension, float] | None = None,
) -> float:
    """Compute normalized harmonization score from dimension answers.

    Returns a float in [0.0, 1.0].
    """
    w = weights or DEFAULT_WEIGHTS
    total_weight = 0.0
    weighted_sum = 0.0

    for answer in answers:
        dim_weight = w.get(answer.dimension, 0.0)
        normalized = (answer.score - 1) / 4.0
        weighted_sum += dim_weight * normalized
        total_weight += dim_weight

    if total_weight == 0.0:
        return 0.0

    return weighted_sum / total_weight


def compute_type_specific_score(answers: list[TypeSpecificAnswer]) -> float:
    """Compute average normalized score from type-specific answers.

    Returns 0.0 if no answers provided.
    """
    if not answers:
        return 0.0
    total = sum((a.score - 1) / 4.0 for a in answers)
    return total / len(answers)


def compute_blended_score(
    base_score: float,
    type_specific_score: float,
    has_type_specific: bool,
) -> float:
    """Blend base dimension score with type-specific question score.

    If no type-specific answers are present, returns base_score unchanged.
    """
    if not has_type_specific:
        return base_score
    return base_score * (1 - TYPE_SPECIFIC_WEIGHT) + type_specific_score * TYPE_SPECIFIC_WEIGHT


def classify_score(score: float) -> HarmonizationClassification:
    for threshold, classification in CLASSIFICATION_THRESHOLDS:
        if score >= threshold:
            return classification
    return HarmonizationClassification.CURRENTLY_NOT_HARMONIZABLE


def apply_hard_constraints(
    classification: HarmonizationClassification,
    constraints: list[HardConstraint],
) -> tuple[HarmonizationClassification, list[str]]:
    current = classification
    reasons: list[str] = []

    for constraint in constraints:
        cap = HARD_CONSTRAINT_CAPS.get(constraint)
        if cap is None:
            continue
        if _classification_rank(cap) > _classification_rank(current):
            reasons.append(
                f"Hard constraint '{constraint.value}' caps classification "
                f"from '{current.value}' to '{cap.value}'"
            )
            current = cap

    return current, reasons


def build_rationale(
    score: float,
    base_classification: HarmonizationClassification,
    final_classification: HarmonizationClassification,
    constraint_reasons: list[str],
    answers: list[AssessmentAnswer],
    stream_type: StreamType | None = None,
    is_aggregated: bool = False,
    subprocess_count: int = 0,
) -> str:
    lines = []
    if stream_type:
        label = _STREAM_TYPE_LABELS.get(stream_type, stream_type.value)
        lines.append(f"Stream type: {label} (type-specific weights applied).")
    if is_aggregated:
        lines.append(
            f"Aggregated from {subprocess_count} subprocess assessment(s)."
        )
    lines.append(
        f"Weighted harmonization score: {score:.2f} "
        f"(base classification: {base_classification.value}).",
    )
    if constraint_reasons:
        lines.append("Hard constraints applied:")
        for reason in constraint_reasons:
            lines.append(f"  - {reason}")
        lines.append(f"Final classification: {final_classification.value}.")
    else:
        lines.append("No hard constraints applied.")

    if answers:
        sorted_answers = sorted(answers, key=lambda a: a.score)
        weakest = sorted_answers[0]
        lines.append(
            f"Weakest dimension: {weakest.dimension.value} "
            f"(score {weakest.score}/5 — {weakest.rationale})."
        )
    return "\n".join(lines)


def compute_prioritization(pri: PrioritizationInput) -> PrioritizationResult:
    w = PRIORITIZATION_WEIGHTS
    raw = {
        "harmonization_potential": (pri.harmonization_potential - 1) / 4.0,
        "operational_relevance": (pri.operational_relevance - 1) / 4.0,
        "governance_compliance_benefit": (pri.governance_compliance_benefit - 1) / 4.0,
        "implementation_effort": (5 - pri.implementation_effort) / 4.0,
        "dependencies": (5 - pri.dependencies) / 4.0,
    }

    score = sum(w[k] * raw[k] for k in w)

    if score >= 0.65:
        priority = HarmonizationPriority.HIGH
    elif score >= 0.40:
        priority = HarmonizationPriority.MEDIUM
    else:
        priority = HarmonizationPriority.LOW

    parts = []
    if raw["harmonization_potential"] >= 0.75:
        parts.append("high harmonization potential")
    if raw["governance_compliance_benefit"] >= 0.75:
        parts.append("strong governance/compliance benefit")
    if raw["implementation_effort"] <= 0.25:
        parts.append("high implementation effort")
    if raw["dependencies"] <= 0.25:
        parts.append("many dependencies to resolve first")

    rationale = f"Priority score: {score:.2f}."
    if parts:
        rationale += " Key factors: " + "; ".join(parts) + "."

    return PrioritizationResult(
        priority=priority,
        priority_score=round(score, 4),
        rationale=rationale,
    )


def evaluate(
    assessment: Assessment,
    stream_type: StreamType | None = None,
) -> HarmonizationResult:
    """Run the full scoring pipeline on an assessment."""
    weights = get_weights_for_stream_type(stream_type)
    base_score = compute_weighted_score(assessment.answers, weights)
    ts_score = compute_type_specific_score(assessment.type_specific_answers)
    score = compute_blended_score(
        base_score, ts_score, bool(assessment.type_specific_answers)
    )
    base_classification = classify_score(score)
    final_classification, constraint_reasons = apply_hard_constraints(
        base_classification, assessment.hard_constraints
    )
    rationale = build_rationale(
        score, base_classification, final_classification,
        constraint_reasons, assessment.answers, stream_type,
    )

    recommendations = {
        HarmonizationClassification.FULLY_CENTRALIZABLE:
            "Proceed with full centralization. Define single process owner and unified SOP.",
        HarmonizationClassification.CENTRAL_METHOD_LOCAL_EXECUTION:
            "Define central methodology and templates. Local teams execute within the framework.",
        HarmonizationClassification.PARTIALLY_HARMONIZABLE:
            "Identify harmonizable sub-steps and unify those. Document local variants explicitly.",
        HarmonizationClassification.MINIMUM_STANDARD_ONLY:
            "Define minimum standards and controls. Allow local process design within guardrails.",
        HarmonizationClassification.CURRENTLY_NOT_HARMONIZABLE:
            "Maintain as separate local processes. Revisit after resolving blocking constraints.",
    }

    return HarmonizationResult(
        harmonization_score=round(score, 4),
        classification=final_classification,
        rationale=rationale,
        recommendation=recommendations[final_classification],
    )


# --- Aggregation: Stream from Subprocesses ---

def aggregate_stream_assessment(
    stream_assessment: Assessment | None,
    subprocess_assessments: list[Assessment],
    stream_type: StreamType | None = None,
) -> HarmonizationResult | None:
    """Aggregate subprocess assessments into a stream-level result.

    Blending:
    - If both stream-level and subprocess assessments exist:
      score = 40% stream-level + 60% subprocess average
    - If only subprocess assessments: 100% subprocess average
    - If only stream-level: 100% stream-level (standard evaluate)
    - If neither: returns None

    Hard constraints are the union of all sources.
    """
    if not subprocess_assessments and stream_assessment is None:
        return None

    weights = get_weights_for_stream_type(stream_type)

    # Compute subprocess average
    sp_scores: list[float] = []
    all_constraints: set[HardConstraint] = set()

    for sp_a in subprocess_assessments:
        base = compute_weighted_score(sp_a.answers, weights)
        ts = compute_type_specific_score(sp_a.type_specific_answers)
        blended = compute_blended_score(base, ts, bool(sp_a.type_specific_answers))
        sp_scores.append(blended)
        all_constraints.update(sp_a.hard_constraints)

    sp_avg = sum(sp_scores) / len(sp_scores) if sp_scores else 0.0

    # Compute stream-level score
    stream_score = 0.0
    if stream_assessment and stream_assessment.answers:
        base = compute_weighted_score(stream_assessment.answers, weights)
        ts = compute_type_specific_score(stream_assessment.type_specific_answers)
        stream_score = compute_blended_score(base, ts, bool(stream_assessment.type_specific_answers))
        all_constraints.update(stream_assessment.hard_constraints)

    # Blend
    if stream_assessment and stream_assessment.answers and sp_scores:
        final_score = STREAM_DIRECT_WEIGHT * stream_score + SUBPROCESS_AGG_WEIGHT * sp_avg
    elif sp_scores:
        final_score = sp_avg
    elif stream_assessment and stream_assessment.answers:
        final_score = stream_score
    else:
        return None

    base_classification = classify_score(final_score)
    final_classification, constraint_reasons = apply_hard_constraints(
        base_classification, list(all_constraints)
    )

    # Use stream assessment answers for rationale if available
    answers_for_rationale = (
        stream_assessment.answers if stream_assessment and stream_assessment.answers
        else (subprocess_assessments[0].answers if subprocess_assessments else [])
    )

    rationale = build_rationale(
        final_score, base_classification, final_classification,
        constraint_reasons, answers_for_rationale, stream_type,
        is_aggregated=bool(sp_scores),
        subprocess_count=len(sp_scores),
    )

    recommendations = {
        HarmonizationClassification.FULLY_CENTRALIZABLE:
            "Proceed with full centralization. Define single process owner and unified SOP.",
        HarmonizationClassification.CENTRAL_METHOD_LOCAL_EXECUTION:
            "Define central methodology and templates. Local teams execute within the framework.",
        HarmonizationClassification.PARTIALLY_HARMONIZABLE:
            "Identify harmonizable sub-steps and unify those. Document local variants explicitly.",
        HarmonizationClassification.MINIMUM_STANDARD_ONLY:
            "Define minimum standards and controls. Allow local process design within guardrails.",
        HarmonizationClassification.CURRENTLY_NOT_HARMONIZABLE:
            "Maintain as separate local processes. Revisit after resolving blocking constraints.",
    }

    return HarmonizationResult(
        harmonization_score=round(final_score, 4),
        classification=final_classification,
        rationale=rationale,
        recommendation=recommendations[final_classification],
    )


# --- Completeness and Confidence ---

def compute_completeness(
    assessment: Assessment,
    stream_type: StreamType | None,
    subprocess_count: int,
    subprocess_assessed_count: int,
    interface_count: int,
    has_regulatory_context: bool,
    has_tenant_scope: bool,
) -> CompletenessResult:
    """Evaluate how complete and reliable an assessment is.

    Returns a completeness score (0-100) and confidence level.
    Factors and their maximum contribution to the score:

    - Base dimensions answered:     30 points (6 dimensions)
    - Type-specific questions:      20 points (varies by type)
    - Hard constraints evaluated:   10 points (present = evaluated)
    - Subprocess coverage:          20 points (assessed / total)
    - Interface consideration:       5 points (interfaces exist)
    - Regulatory context populated:  5 points
    - Tenant scope populated:        5 points
    - Prioritization provided:       5 points
    """
    missing: list[str] = []
    score = 0

    # Base dimensions (30 points)
    answered_dims = {a.dimension for a in assessment.answers}
    all_dims = set(AlignmentDimension)
    dim_coverage = len(answered_dims) / len(all_dims) if all_dims else 0
    score += int(30 * dim_coverage)
    missing_dims = all_dims - answered_dims
    if missing_dims:
        missing.append(
            f"Missing base dimensions: {', '.join(d.value for d in missing_dims)}"
        )

    # Type-specific questions (20 points)
    if stream_type:
        required_qs = get_required_question_ids(stream_type)
        answered_qs = {a.question_id for a in assessment.type_specific_answers}
        if required_qs:
            ts_coverage = len(answered_qs & required_qs) / len(required_qs)
            score += int(20 * ts_coverage)
            missing_qs = required_qs - answered_qs
            if missing_qs:
                missing.append(
                    f"Missing type-specific questions: {', '.join(sorted(missing_qs))}"
                )
        else:
            score += 20  # No type-specific questions defined
    else:
        score += 10  # Partial credit when type is unknown

    # Hard constraints (10 points)
    # Evaluated = explicitly listed (even empty list means consciously evaluated)
    # We give full credit if the assessment exists (constraints field is always present)
    if assessment.hard_constraints or assessment.answers:
        score += 10
    else:
        missing.append("Hard constraints not evaluated")

    # Subprocess coverage (20 points, only for stream-level)
    if assessment.assessed_object_type == AssessedObjectType.STREAM:
        if subprocess_count == 0:
            missing.append("No subprocesses defined for this stream")
            # Still give partial credit — stream may legitimately have none
            score += 5
        elif subprocess_assessed_count == 0:
            missing.append(
                f"None of {subprocess_count} subprocesses have been assessed"
            )
        else:
            sp_coverage = subprocess_assessed_count / subprocess_count
            score += int(20 * sp_coverage)
            if subprocess_assessed_count < subprocess_count:
                missing.append(
                    f"Only {subprocess_assessed_count}/{subprocess_count} "
                    f"subprocesses assessed"
                )
    else:
        # Subprocess-level: full credit (not applicable)
        score += 20

    # Interface consideration (5 points)
    if interface_count > 0:
        score += 5
    else:
        missing.append("No interfaces modeled for this stream/subprocess")

    # Regulatory context (5 points)
    if has_regulatory_context:
        score += 5
    else:
        missing.append("Regulatory context not specified")

    # Tenant scope (5 points) — always populated in our model, so check is_present
    if has_tenant_scope:
        score += 5
    else:
        missing.append("Tenant scope not specified")

    # Prioritization (5 points)
    if assessment.prioritization:
        score += 5
    elif assessment.assessed_object_type == AssessedObjectType.STREAM:
        missing.append("Prioritization input not provided")

    # Clamp
    score = min(100, max(0, score))

    # Confidence
    if score >= 75:
        confidence = ConfidenceLevel.HIGH
    elif score >= 45:
        confidence = ConfidenceLevel.MEDIUM
    else:
        confidence = ConfidenceLevel.LOW

    rationale_parts = [f"Completeness: {score}/100."]
    if missing:
        rationale_parts.append(f"{len(missing)} gap(s) identified.")

    return CompletenessResult(
        completeness_score=score,
        confidence_level=confidence,
        missing_items=missing,
        rationale=" ".join(rationale_parts),
    )

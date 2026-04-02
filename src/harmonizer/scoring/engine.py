"""Deterministic scoring engine for harmonization assessment.

Scoring algorithm:
1. Compute weighted average of alignment dimension scores (each 1-5).
2. Normalize to 0.0-1.0 range.
3. Apply hard constraint penalties that cap or reduce the classification.
4. Map final score to a HarmonizationClassification.

Dimension weights (configurable, sensible defaults):
- regulatory_alignment:  0.25  (regulatory divergence is hardest to overcome)
- operational_alignment:  0.20
- tooling_alignment:      0.15
- governance_alignment:   0.20
- maturity:               0.10
- local_necessity:        0.10  (inverse: high local necessity = low score)

Hard constraint effects:
- legal_local_difference -> cap at minimum_standard_only
- tenant_separation_blocks_operation -> cap at central_method_local_execution
- separate_control_ownership -> cap at partially_harmonizable
- insufficient_documentation -> cap at currently_not_harmonizable

Score-to-classification mapping (before hard constraint caps):
- >= 0.85 -> fully_centralizable
- >= 0.70 -> central_method_local_execution
- >= 0.50 -> partially_harmonizable
- >= 0.30 -> minimum_standard_only
- <  0.30 -> currently_not_harmonizable
"""

from harmonizer.models.assessment import (
    AlignmentDimension,
    Assessment,
    AssessmentAnswer,
    HardConstraint,
    HarmonizationClassification,
    HarmonizationResult,
)

# Weights must sum to 1.0
DEFAULT_WEIGHTS: dict[AlignmentDimension, float] = {
    AlignmentDimension.REGULATORY_ALIGNMENT: 0.25,
    AlignmentDimension.OPERATIONAL_ALIGNMENT: 0.20,
    AlignmentDimension.TOOLING_ALIGNMENT: 0.15,
    AlignmentDimension.GOVERNANCE_ALIGNMENT: 0.20,
    AlignmentDimension.MATURITY: 0.10,
    AlignmentDimension.LOCAL_NECESSITY: 0.10,
}

# Score thresholds for classification (lower bound inclusive)
CLASSIFICATION_THRESHOLDS: list[tuple[float, HarmonizationClassification]] = [
    (0.85, HarmonizationClassification.FULLY_CENTRALIZABLE),
    (0.70, HarmonizationClassification.CENTRAL_METHOD_LOCAL_EXECUTION),
    (0.50, HarmonizationClassification.PARTIALLY_HARMONIZABLE),
    (0.30, HarmonizationClassification.MINIMUM_STANDARD_ONLY),
    (0.00, HarmonizationClassification.CURRENTLY_NOT_HARMONIZABLE),
]

# Hard constraints cap the classification at the specified maximum level.
# Ordering follows the enum ordering (most permissive -> least permissive).
HARD_CONSTRAINT_CAPS: dict[HardConstraint, HarmonizationClassification] = {
    HardConstraint.LEGAL_LOCAL_DIFFERENCE: HarmonizationClassification.MINIMUM_STANDARD_ONLY,
    HardConstraint.TENANT_SEPARATION_BLOCKS_OPERATION: HarmonizationClassification.CENTRAL_METHOD_LOCAL_EXECUTION,
    HardConstraint.SEPARATE_CONTROL_OWNERSHIP: HarmonizationClassification.PARTIALLY_HARMONIZABLE,
    HardConstraint.INSUFFICIENT_DOCUMENTATION: HarmonizationClassification.CURRENTLY_NOT_HARMONIZABLE,
}

# Ordered list of classifications from most to least harmonizable,
# used for cap comparisons.
_CLASSIFICATION_ORDER: list[HarmonizationClassification] = [
    HarmonizationClassification.FULLY_CENTRALIZABLE,
    HarmonizationClassification.CENTRAL_METHOD_LOCAL_EXECUTION,
    HarmonizationClassification.PARTIALLY_HARMONIZABLE,
    HarmonizationClassification.MINIMUM_STANDARD_ONLY,
    HarmonizationClassification.CURRENTLY_NOT_HARMONIZABLE,
]


def _classification_rank(c: HarmonizationClassification) -> int:
    """Lower rank = more harmonizable. Used for cap comparisons."""
    return _CLASSIFICATION_ORDER.index(c)


def compute_weighted_score(
    answers: list[AssessmentAnswer],
    weights: dict[AlignmentDimension, float] | None = None,
) -> float:
    """Compute normalized harmonization score from dimension answers.

    Returns a float in [0.0, 1.0]. Missing dimensions are ignored and
    weights are re-normalized over present dimensions.
    """
    w = weights or DEFAULT_WEIGHTS
    total_weight = 0.0
    weighted_sum = 0.0

    for answer in answers:
        dim_weight = w.get(answer.dimension, 0.0)
        # Normalize score from 1-5 to 0.0-1.0
        normalized = (answer.score - 1) / 4.0
        weighted_sum += dim_weight * normalized
        total_weight += dim_weight

    if total_weight == 0.0:
        return 0.0

    return weighted_sum / total_weight


def classify_score(score: float) -> HarmonizationClassification:
    """Map a normalized score to a harmonization classification."""
    for threshold, classification in CLASSIFICATION_THRESHOLDS:
        if score >= threshold:
            return classification
    return HarmonizationClassification.CURRENTLY_NOT_HARMONIZABLE


def apply_hard_constraints(
    classification: HarmonizationClassification,
    constraints: list[HardConstraint],
) -> tuple[HarmonizationClassification, list[str]]:
    """Apply hard constraints that may cap the classification downward.

    Returns the (possibly reduced) classification and a list of
    human-readable reasons for any applied caps.
    """
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
) -> str:
    """Generate a human-readable rationale for the assessment result."""
    lines = [
        f"Weighted harmonization score: {score:.2f} "
        f"(base classification: {base_classification.value}).",
    ]
    if constraint_reasons:
        lines.append("Hard constraints applied:")
        for reason in constraint_reasons:
            lines.append(f"  - {reason}")
        lines.append(f"Final classification: {final_classification.value}.")
    else:
        lines.append("No hard constraints applied.")

    # Highlight lowest-scoring dimensions
    if answers:
        sorted_answers = sorted(answers, key=lambda a: a.score)
        weakest = sorted_answers[0]
        lines.append(
            f"Weakest dimension: {weakest.dimension.value} "
            f"(score {weakest.score}/5 — {weakest.rationale})."
        )
    return "\n".join(lines)


def evaluate(assessment: Assessment) -> HarmonizationResult:
    """Run the full scoring pipeline on an assessment and return the result.

    This is the main entry point for the scoring engine.
    """
    score = compute_weighted_score(assessment.answers)
    base_classification = classify_score(score)
    final_classification, constraint_reasons = apply_hard_constraints(
        base_classification, assessment.hard_constraints
    )
    rationale = build_rationale(
        score, base_classification, final_classification,
        constraint_reasons, assessment.answers,
    )

    # Derive recommendation from classification
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

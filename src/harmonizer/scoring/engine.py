"""Deterministic scoring engine for harmonization assessment.

Scoring algorithm:
1. Determine dimension weights based on stream_type (or use defaults).
2. Compute weighted average of alignment dimension scores (each 1-5).
3. Normalize to 0.0-1.0 range.
4. Apply hard constraint penalties that cap or reduce the classification.
5. Map final score to a HarmonizationClassification.

Stream-type-specific weight profiles reflect what matters most for each type:
- process: operational flow, roles, tooling
- governance_function: mandates, policies, control model
- service_domain: delivery model, customer interface, contracts
- support_function: standardization, efficiency, reuse
- capability_domain: enablement, methods, platforms
- program_domain: steering, coordination, transformation

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

from harmonizer.models.process import StreamType
from harmonizer.models.assessment import (
    AlignmentDimension,
    Assessment,
    AssessmentAnswer,
    HardConstraint,
    HarmonizationClassification,
    HarmonizationPriority,
    HarmonizationResult,
    PrioritizationInput,
    PrioritizationResult,
)


# --- Dimension weight profiles per stream type ---
# Each profile sums to 1.0. The weights reflect which dimensions
# are most relevant for assessing harmonization of that stream type.

STREAM_TYPE_WEIGHTS: dict[StreamType, dict[AlignmentDimension, float]] = {
    # process: Focus on workflow, roles, inputs/outputs, tooling
    StreamType.PROCESS: {
        AlignmentDimension.REGULATORY_ALIGNMENT: 0.20,
        AlignmentDimension.OPERATIONAL_ALIGNMENT: 0.25,
        AlignmentDimension.TOOLING_ALIGNMENT: 0.20,
        AlignmentDimension.GOVERNANCE_ALIGNMENT: 0.15,
        AlignmentDimension.MATURITY: 0.10,
        AlignmentDimension.LOCAL_NECESSITY: 0.10,
    },
    # governance_function: Focus on mandates, policies, control model, evidence
    StreamType.GOVERNANCE_FUNCTION: {
        AlignmentDimension.REGULATORY_ALIGNMENT: 0.30,
        AlignmentDimension.OPERATIONAL_ALIGNMENT: 0.10,
        AlignmentDimension.TOOLING_ALIGNMENT: 0.10,
        AlignmentDimension.GOVERNANCE_ALIGNMENT: 0.30,
        AlignmentDimension.MATURITY: 0.10,
        AlignmentDimension.LOCAL_NECESSITY: 0.10,
    },
    # service_domain: Focus on delivery model, customer interface, contracts
    StreamType.SERVICE_DOMAIN: {
        AlignmentDimension.REGULATORY_ALIGNMENT: 0.15,
        AlignmentDimension.OPERATIONAL_ALIGNMENT: 0.25,
        AlignmentDimension.TOOLING_ALIGNMENT: 0.15,
        AlignmentDimension.GOVERNANCE_ALIGNMENT: 0.20,
        AlignmentDimension.MATURITY: 0.10,
        AlignmentDimension.LOCAL_NECESSITY: 0.15,
    },
    # support_function: Focus on standardization, efficiency, reusability
    StreamType.SUPPORT_FUNCTION: {
        AlignmentDimension.REGULATORY_ALIGNMENT: 0.10,
        AlignmentDimension.OPERATIONAL_ALIGNMENT: 0.30,
        AlignmentDimension.TOOLING_ALIGNMENT: 0.25,
        AlignmentDimension.GOVERNANCE_ALIGNMENT: 0.10,
        AlignmentDimension.MATURITY: 0.15,
        AlignmentDimension.LOCAL_NECESSITY: 0.10,
    },
    # capability_domain: Focus on enablement, methods, platforms, know-how
    StreamType.CAPABILITY_DOMAIN: {
        AlignmentDimension.REGULATORY_ALIGNMENT: 0.10,
        AlignmentDimension.OPERATIONAL_ALIGNMENT: 0.20,
        AlignmentDimension.TOOLING_ALIGNMENT: 0.25,
        AlignmentDimension.GOVERNANCE_ALIGNMENT: 0.15,
        AlignmentDimension.MATURITY: 0.20,
        AlignmentDimension.LOCAL_NECESSITY: 0.10,
    },
    # program_domain: Focus on steering, initiatives, transformation, coordination
    StreamType.PROGRAM_DOMAIN: {
        AlignmentDimension.REGULATORY_ALIGNMENT: 0.15,
        AlignmentDimension.OPERATIONAL_ALIGNMENT: 0.15,
        AlignmentDimension.TOOLING_ALIGNMENT: 0.10,
        AlignmentDimension.GOVERNANCE_ALIGNMENT: 0.30,
        AlignmentDimension.MATURITY: 0.15,
        AlignmentDimension.LOCAL_NECESSITY: 0.15,
    },
}

# Fallback weights used when no stream type is provided (e.g., subprocess-level)
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

# --- Stream-type-specific recommendation templates ---
_STREAM_TYPE_LABELS: dict[StreamType, str] = {
    StreamType.PROCESS: "process",
    StreamType.GOVERNANCE_FUNCTION: "governance function",
    StreamType.SERVICE_DOMAIN: "service domain",
    StreamType.CAPABILITY_DOMAIN: "capability domain",
    StreamType.SUPPORT_FUNCTION: "support function",
    StreamType.PROGRAM_DOMAIN: "program domain",
}

# --- Prioritization weights ---
# harmonization_potential and governance_compliance_benefit drive priority up;
# implementation_effort and dependencies drive it down (inverted).
PRIORITIZATION_WEIGHTS: dict[str, float] = {
    "harmonization_potential": 0.30,
    "operational_relevance": 0.20,
    "governance_compliance_benefit": 0.25,
    "implementation_effort": 0.15,   # inverted: high effort = low score
    "dependencies": 0.10,            # inverted: many dependencies = low score
}


def _classification_rank(c: HarmonizationClassification) -> int:
    return _CLASSIFICATION_ORDER.index(c)


def get_weights_for_stream_type(stream_type: StreamType | None) -> dict[AlignmentDimension, float]:
    """Return the appropriate dimension weights for a given stream type."""
    if stream_type is None:
        return DEFAULT_WEIGHTS
    return STREAM_TYPE_WEIGHTS.get(stream_type, DEFAULT_WEIGHTS)


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
    """Apply hard constraints that may cap the classification downward."""
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
) -> str:
    """Generate a human-readable rationale for the assessment result."""
    lines = []
    if stream_type:
        label = _STREAM_TYPE_LABELS.get(stream_type, stream_type.value)
        lines.append(f"Stream type: {label} (type-specific weights applied).")
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
    """Compute a prioritization result from input factors.

    Factors harmonization_potential, operational_relevance, and
    governance_compliance_benefit contribute positively.
    Factors implementation_effort and dependencies are inverted
    (high effort/dependencies = lower priority score).
    """
    w = PRIORITIZATION_WEIGHTS
    # Normalize each factor from 1-5 to 0.0-1.0
    raw = {
        "harmonization_potential": (pri.harmonization_potential - 1) / 4.0,
        "operational_relevance": (pri.operational_relevance - 1) / 4.0,
        "governance_compliance_benefit": (pri.governance_compliance_benefit - 1) / 4.0,
        # Inverted: effort 5 -> 0.0 (bad), effort 1 -> 1.0 (good)
        "implementation_effort": (5 - pri.implementation_effort) / 4.0,
        # Inverted: many dependencies -> lower priority
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
    """Run the full scoring pipeline on an assessment.

    Args:
        assessment: The assessment to evaluate.
        stream_type: If provided, use stream-type-specific dimension weights.
            Typically passed for stream-level assessments; subprocess
            assessments inherit the parent stream's type.
    """
    weights = get_weights_for_stream_type(stream_type)
    score = compute_weighted_score(assessment.answers, weights)
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

"""Option comparison decision engine for DE/AT harmonization.

Compares up to 3 target option assessments (de_standard, at_standard, central)
for a single stream and produces a recommendation.

Decision logic:
1. Score each option using the existing scoring engine
2. Exclude options blocked by hard constraints
3. Among remaining options, prefer highest classification
4. Use delta penalties (regulatory_gap, structural_diff) as tiebreakers
5. Produce rationale, blockers, prerequisites, and discarded options
"""

from harmonizer.models.assessment import (
    AlignmentDimension,
    AssessmentAnswer,
    HardConstraint,
    HarmonizationClassification,
    TypeSpecificAnswer,
)
from harmonizer.models.process import GapLevel, StreamType
from harmonizer.scoring.engine import (
    apply_hard_constraints,
    classify_score,
    compute_blended_score,
    compute_type_specific_score,
    compute_weighted_score,
    get_weights_for_stream_type,
    _classification_rank,
)
from harmonizer.scoring.delta import compute_delta, delta_penalty_from_computed

TARGET_OPTION_LABELS = {
    "de_standard": "DE standard (AT adopts DE)",
    "at_standard": "AT standard (DE adopts AT)",
    "central": "Central (new unified process)",
}

GAP_PENALTY = {
    GapLevel.LOW: 0.0,
    GapLevel.MEDIUM: 0.03,
    GapLevel.HIGH: 0.06,
}

# Classification order (lower index = better)
_CLASS_ORDER = list(HarmonizationClassification)


def _score_option(assessment: dict, stream_type: StreamType | None) -> dict:
    """Score a single option assessment. Returns score + classification."""
    answers = []
    for a in assessment.get("answers", []):
        try:
            answers.append(AssessmentAnswer(
                dimension=AlignmentDimension(a["dimension"]),
                score=a["score"],
                rationale=a.get("rationale", ""),
            ))
        except (KeyError, ValueError):
            continue

    ts_answers = []
    for a in assessment.get("type_specific_answers", []):
        try:
            ts_answers.append(TypeSpecificAnswer(
                question_id=a["question_id"],
                score=a["score"],
                rationale=a.get("rationale", ""),
            ))
        except (KeyError, ValueError):
            continue

    hc_list = []
    for hc in assessment.get("hard_constraints", []):
        try:
            hc_list.append(HardConstraint(hc))
        except ValueError:
            continue

    weights = get_weights_for_stream_type(stream_type)
    base = compute_weighted_score(answers, weights)
    ts = compute_type_specific_score(ts_answers)
    blended = compute_blended_score(base, ts, bool(ts_answers))
    base_classification = classify_score(blended)

    final_classification, constraint_reasons = apply_hard_constraints(
        base_classification, hc_list
    )

    blocked = final_classification == HarmonizationClassification.CURRENTLY_NOT_HARMONIZABLE

    return {
        "score": blended,
        "classification": final_classification,
        "hard_constraints": [hc.value for hc in hc_list],
        "constraint_reasons": constraint_reasons,
        "blocked": blocked,
        "status": assessment.get("status", "draft"),
    }


def _apply_delta_penalty(score: float, delta: dict, option: str) -> float:
    """Apply penalty based on delta gap levels.

    Higher gaps = harder to harmonize = lower adjusted score.
    """
    penalty = 0.0
    for key in ("structural_diff", "tooling_gap", "regulatory_gap", "role_model_diff"):
        gap_str = delta.get(key, "low")
        try:
            gap = GapLevel(gap_str)
        except ValueError:
            gap = GapLevel.LOW
        penalty += GAP_PENALTY.get(gap, 0.0)

    # regulatory_gap penalizes adoption options more than central
    reg_gap_str = delta.get("regulatory_gap", "low")
    try:
        reg_gap = GapLevel(reg_gap_str)
    except ValueError:
        reg_gap = GapLevel.LOW
    if option != "central" and reg_gap == GapLevel.HIGH:
        penalty += 0.05

    return max(0.0, score - penalty)


def compare_options(stream: dict, option_assessments: list[dict]) -> dict:
    """Compare target option assessments and recommend the best one.

    Args:
        stream: Full stream dict (with optional as_is, delta).
        option_assessments: List of assessment dicts with target_option set.

    Returns:
        Decision result with recommended_option, rationale, scores, discarded.
    """
    stream_type = None
    try:
        stream_type = StreamType(stream.get("stream_type", ""))
    except ValueError:
        pass

    # Compute real delta from AS-IS data (replaces abstract gap levels)
    as_is = stream.get("as_is", {})
    de_asis = as_is.get("de", {})
    at_asis = as_is.get("at", {})
    has_asis = bool(de_asis.get("description", "").strip() or at_asis.get("description", "").strip())
    computed_delta = compute_delta(de_asis, at_asis) if has_asis else None

    # Fallback: abstract delta for backward compat when no AS-IS exists
    abstract_delta = stream.get("delta", {})

    # Group assessments by target_option
    by_option = {}
    for a in option_assessments:
        opt = a.get("target_option")
        if opt:
            by_option[opt] = a
        elif not by_option:
            # Legacy assessment without target_option — treat as central
            by_option["central"] = a

    if not by_option:
        return {
            "recommended_option": None,
            "rationale": "No option assessments available.",
            "blockers": ["No assessments with target_option found"],
            "prerequisites": [],
            "option_scores": {},
            "option_classifications": {},
            "discarded_options": [],
        }

    # Score each option
    scored = {}
    for opt, assessment in by_option.items():
        result = _score_option(assessment, stream_type)
        # Use computed delta when available, fall back to abstract
        if computed_delta:
            penalty = delta_penalty_from_computed(computed_delta, opt)
        else:
            penalty = _apply_delta_penalty(result["score"], abstract_delta, opt) - result["score"]
            penalty = abs(penalty)
        result["adjusted_score"] = max(0.0, result["score"] - penalty)
        result["delta_penalty"] = round(penalty, 4)
        scored[opt] = result

    # Separate viable from blocked
    viable = {opt: r for opt, r in scored.items() if not r["blocked"]}
    blocked = {opt: r for opt, r in scored.items() if r["blocked"]}

    discarded = []
    for opt, r in blocked.items():
        discarded.append({
            "option": opt,
            "label": TARGET_OPTION_LABELS.get(opt, opt),
            "reason": f"Blocked by hard constraints: {', '.join(r['constraint_reasons'])}",
            "score": round(r["score"], 4),
            "classification": r["classification"].value,
        })

    if not viable:
        # All options blocked
        best_blocked = min(
            scored.items(),
            key=lambda x: _classification_rank(x[1]["classification"]),
        )
        return {
            "recommended_option": None,
            "rationale": (
                "All target options are blocked by hard constraints. "
                "Address the constraints before making a harmonization decision."
            ),
            "blockers": [
                f"{TARGET_OPTION_LABELS.get(opt, opt)}: {', '.join(r['constraint_reasons'])}"
                for opt, r in scored.items()
            ],
            "prerequisites": [
                "Resolve hard constraints on at least one target option"
            ],
            "option_scores": {opt: round(r["score"], 4) for opt, r in scored.items()},
            "option_classifications": {opt: r["classification"].value for opt, r in scored.items()},
            "discarded_options": discarded,
        }

    # Select best: highest classification first, then adjusted score as tiebreaker
    ranked = sorted(
        viable.items(),
        key=lambda x: (
            _classification_rank(x[1]["classification"]),  # lower = better
            -x[1]["adjusted_score"],                       # higher = better
        ),
    )
    best_opt, best_result = ranked[0]

    # Build rationale
    rationale_parts = [
        f"Recommended: {TARGET_OPTION_LABELS.get(best_opt, best_opt)}.",
        f"Classification: {best_result['classification'].value.replace('_', ' ')}.",
        f"Score: {best_result['score']:.2f} (adjusted: {best_result['adjusted_score']:.2f}).",
    ]
    if len(viable) > 1:
        runner_up_opt, runner_up = ranked[1]
        rationale_parts.append(
            f"Runner-up: {TARGET_OPTION_LABELS.get(runner_up_opt, runner_up_opt)} "
            f"(score: {runner_up['score']:.2f})."
        )

    # Discard non-best viable options
    for opt, r in viable.items():
        if opt == best_opt:
            continue
        reason = (
            f"Lower classification ({r['classification'].value.replace('_', ' ')})"
            if _classification_rank(r["classification"]) > _classification_rank(best_result["classification"])
            else f"Lower adjusted score ({r['adjusted_score']:.2f} vs {best_result['adjusted_score']:.2f})"
        )
        discarded.append({
            "option": opt,
            "label": TARGET_OPTION_LABELS.get(opt, opt),
            "reason": reason,
            "score": round(r["score"], 4),
            "classification": r["classification"].value,
        })

    # Prerequisites — derived from computed delta items
    prerequisites = []
    if best_opt in ("de_standard", "at_standard"):
        adopting = "AT" if best_opt == "de_standard" else "DE"
        prerequisites.append(f"{adopting} must align processes to the selected standard")

    if computed_delta:
        for item in computed_delta.get("items", []):
            if item["impact"] == "high" and item["difference_type"] in ("different", "missing"):
                prerequisites.append(f"{item['category']}: {item['description']}")
    else:
        if abstract_delta.get("tooling_gap") == "high":
            prerequisites.append("Significant tooling gap must be addressed")
        if abstract_delta.get("role_model_diff") == "high":
            prerequisites.append("Role model differences must be reconciled")

    # Incomplete assessments warning
    expected = {"de_standard", "at_standard", "central"}
    missing = expected - set(by_option.keys())
    blockers = []
    if missing:
        blockers.append(
            f"Missing option assessments: {', '.join(sorted(missing))}. "
            "Decision may change when all options are evaluated."
        )

    return {
        "recommended_option": best_opt,
        "rationale": " ".join(rationale_parts),
        "blockers": blockers,
        "prerequisites": prerequisites,
        "option_scores": {opt: round(r["score"], 4) for opt, r in scored.items()},
        "option_classifications": {opt: r["classification"].value for opt, r in scored.items()},
        "option_details": {
            opt: {
                "score": round(r["score"], 4),
                "adjusted_score": round(r["adjusted_score"], 4),
                "classification": r["classification"].value,
                "delta_penalty": r.get("delta_penalty", 0),
                "hard_constraints": r["hard_constraints"],
                "blocked": r["blocked"],
                "status": r["status"],
            }
            for opt, r in scored.items()
        },
        "discarded_options": discarded,
        "delta": abstract_delta,
        "computed_delta": computed_delta,
    }

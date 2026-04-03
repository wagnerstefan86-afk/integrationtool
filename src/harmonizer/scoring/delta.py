"""Computed delta between DE and AT AS-IS process descriptions.

Produces a structured, field-by-field comparison with:
- Difference type (identical, partial, different, missing)
- Impact level (low, medium, high)
- Human-readable description

Used by the decision engine to replace abstract gap-level flags
with concrete, auditable difference data.
"""

from __future__ import annotations

COMPARED_CATEGORIES = [
    ("triggers", "Triggers", False),
    ("inputs", "Inputs", False),
    ("outputs", "Outputs", False),
    ("steps", "Process Steps", True),      # critical
    ("roles", "Roles", True),              # critical
    ("tools", "Tools / Systems", True),    # critical
    ("controls", "Controls / Regulatory", True),  # critical
    ("evidence", "Evidence", False),
    ("responsibilities", "Responsibilities", False),
]


def _normalize_set(items: list[str]) -> set[str]:
    """Normalize list entries for comparison (lowercase, stripped)."""
    return {s.strip().lower() for s in items if s.strip()}


def _compare_lists(
    de_items: list[str],
    at_items: list[str],
    category_label: str,
    is_critical: bool,
) -> dict | None:
    """Compare two string lists and return a DeltaItem dict, or None if both empty."""
    de_set = _normalize_set(de_items)
    at_set = _normalize_set(at_items)

    # Both empty → skip
    if not de_set and not at_set:
        return None

    # One side empty → missing
    if de_set and not at_set:
        return {
            "category": category_label,
            "de_value": [s for s in de_items if s.strip()],
            "at_value": [],
            "difference_type": "missing",
            "impact": "high" if is_critical else "medium",
            "description": f"{category_label} missing in AT (DE has {len(de_set)})",
        }
    if at_set and not de_set:
        return {
            "category": category_label,
            "de_value": [],
            "at_value": [s for s in at_items if s.strip()],
            "difference_type": "missing",
            "impact": "high" if is_critical else "medium",
            "description": f"{category_label} missing in DE (AT has {len(at_set)})",
        }

    # Both have entries — compute overlap
    intersection = de_set & at_set
    union = de_set | at_set
    overlap_ratio = len(intersection) / len(union) if union else 1.0

    de_clean = [s for s in de_items if s.strip()]
    at_clean = [s for s in at_items if s.strip()]

    if overlap_ratio == 1.0:
        return {
            "category": category_label,
            "de_value": de_clean,
            "at_value": at_clean,
            "difference_type": "identical",
            "impact": "low",
            "description": f"{category_label} identical across DE and AT",
        }

    if overlap_ratio >= 0.5:
        de_only = sorted(de_set - at_set)
        at_only = sorted(at_set - de_set)
        desc_parts = [f"{category_label} partially aligned"]
        if de_only:
            desc_parts.append(f"DE-only: {', '.join(de_only)}")
        if at_only:
            desc_parts.append(f"AT-only: {', '.join(at_only)}")
        return {
            "category": category_label,
            "de_value": de_clean,
            "at_value": at_clean,
            "difference_type": "partial",
            "impact": "medium",
            "description": "; ".join(desc_parts),
        }

    # No meaningful overlap
    return {
        "category": category_label,
        "de_value": de_clean,
        "at_value": at_clean,
        "difference_type": "different",
        "impact": "high" if is_critical else "medium",
        "description": f"{category_label} differ completely (DE: {', '.join(sorted(de_set))}; AT: {', '.join(sorted(at_set))})",
    }


def compute_delta(de: dict, at: dict) -> dict:
    """Compute structured delta between DE and AT AS-IS dicts.

    Returns a DeltaResult dict with items list and summary.
    """
    items = []
    for field_key, label, is_critical in COMPARED_CATEGORIES:
        de_list = de.get(field_key, [])
        at_list = at.get(field_key, [])
        item = _compare_lists(de_list, at_list, label, is_critical)
        if item:
            items.append(item)

    high = sum(1 for i in items if i["impact"] == "high")
    medium = sum(1 for i in items if i["impact"] == "medium")
    low = sum(1 for i in items if i["impact"] == "low")

    return {
        "items": items,
        "summary": {
            "total_items": len(items),
            "high_impact": high,
            "medium_impact": medium,
            "low_impact": low,
        },
    }


def delta_penalty_from_computed(delta_result: dict, option: str) -> float:
    """Compute score penalty from a computed DeltaResult.

    Replaces the old abstract GAP_PENALTY logic with concrete
    item-level penalties based on actual DE/AT differences.

    Rules:
    - Each high-impact item: -0.04
    - Each medium-impact item: -0.015
    - Missing critical categories (roles, controls, tools): extra -0.03 each
    - Adoption options (de_standard, at_standard) get extra penalty
      for "different" items since one side must fully change
    """
    items = delta_result.get("items", [])
    if not items:
        return 0.0

    penalty = 0.0

    for item in items:
        impact = item.get("impact", "low")
        diff_type = item.get("difference_type", "identical")

        if impact == "high":
            penalty += 0.04
        elif impact == "medium":
            penalty += 0.015

        # Adoption options penalized more for "different" critical categories
        if option != "central" and diff_type == "different" and impact == "high":
            penalty += 0.02

        # Missing on either side is especially bad for adoption options
        if option != "central" and diff_type == "missing" and impact == "high":
            penalty += 0.03

    return min(penalty, 0.5)  # cap at 0.5

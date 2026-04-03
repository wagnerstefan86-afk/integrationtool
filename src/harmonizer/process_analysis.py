"""Structured process analysis model and logic.

Provides the step-anchored process analysis layer:
- Fixed process phases (intake, triage, processing, escalation, closure, reporting)
- Per-entity variants under each step (DE, AT, or any future entity)
- Guided interview questions per phase
- Completeness and quality scoring with WHY quality & evidence strength
- Step-level delta computation with dimension/nature/constraint classification
- Review workflow per variant (draft -> captured -> challenged -> reviewed -> approved)
- Rule-based recommendation engine
- Management-level summary with decision support counters
"""

from __future__ import annotations
from datetime import datetime

# ─── Default process phases ───────────────────────────────────────────────────

DEFAULT_PROCESS_PHASES = [
    {"step_id": "intake", "step_name": "Intake / Eingang", "sort_order": 1},
    {"step_id": "triage", "step_name": "Klassifizierung / Triage", "sort_order": 2},
    {"step_id": "processing", "step_name": "Bearbeitung", "sort_order": 3},
    {"step_id": "escalation", "step_name": "Eskalation", "sort_order": 4},
    {"step_id": "closure", "step_name": "Abschluss / Dokumentation", "sort_order": 5},
    {"step_id": "reporting", "step_name": "Reporting / Monitoring", "sort_order": 6},
]

# ─── Guided interview questions per phase ─────────────────────────────────────

GUIDE_QUESTIONS: dict[str, list[dict]] = {
    "intake": [
        {"id": "q_intake_channels", "text": "Über welche Kanäle kommen Requests rein?", "maps_to": "input_channels"},
        {"id": "q_intake_systems", "text": "Welche Systeme nehmen Requests entgegen?", "maps_to": "systems_used"},
        {"id": "q_intake_triggers", "text": "Gibt es automatische Trigger (z.B. SOC-Alerts, Monitoring)?", "maps_to": "trigger"},
        {"id": "q_intake_multi", "text": "Gibt es mehrere parallele Eingangskanäle? Wenn ja, warum?", "maps_to": "variants"},
        {"id": "q_intake_why", "text": "Warum wurde dieser Eingang so aufgebaut?", "maps_to": "why_is_it_done_this_way"},
    ],
    "triage": [
        {"id": "q_triage_who", "text": "Wer bewertet eingehende Requests?", "maps_to": "roles_involved"},
        {"id": "q_triage_criteria", "text": "Nach welchen Kriterien wird klassifiziert?", "maps_to": "description"},
        {"id": "q_triage_auto", "text": "Erfolgt die Triage manuell oder automatisiert?", "maps_to": "variants"},
        {"id": "q_triage_why", "text": "Warum ist der Ablauf so organisiert?", "maps_to": "why_is_it_done_this_way"},
    ],
    "processing": [
        {"id": "q_proc_who", "text": "Wer bearbeitet die Requests?", "maps_to": "roles_involved"},
        {"id": "q_proc_special", "text": "Gibt es Spezialisierungen oder Teams?", "maps_to": "variants"},
        {"id": "q_proc_systems", "text": "Welche Systeme werden zur Bearbeitung genutzt?", "maps_to": "systems_used"},
        {"id": "q_proc_sla", "text": "Gibt es SLAs oder Zielzeiten?", "maps_to": "sla_or_target"},
        {"id": "q_proc_why", "text": "Warum ist die Bearbeitung lokal/zentral so organisiert?", "maps_to": "why_is_it_done_this_way"},
    ],
    "escalation": [
        {"id": "q_esc_when", "text": "Wann wird eskaliert?", "maps_to": "trigger"},
        {"id": "q_esc_to", "text": "An wen wird eskaliert?", "maps_to": "roles_involved"},
        {"id": "q_esc_paths", "text": "Gibt es definierte Eskalationspfade?", "maps_to": "description"},
        {"id": "q_esc_why", "text": "Warum wird so eskaliert?", "maps_to": "why_is_it_done_this_way"},
    ],
    "closure": [
        {"id": "q_close_done", "text": "Wann gilt ein Request als abgeschlossen?", "maps_to": "description"},
        {"id": "q_close_doc", "text": "Wo wird dokumentiert?", "maps_to": "systems_used"},
        {"id": "q_close_qc", "text": "Gibt es Qualitätskontrollen vor Abschluss?", "maps_to": "variants"},
        {"id": "q_close_why", "text": "Warum ist der Abschlussprozess so definiert?", "maps_to": "why_is_it_done_this_way"},
    ],
    "reporting": [
        {"id": "q_rep_kpi", "text": "Welche KPIs gibt es?", "maps_to": "output"},
        {"id": "q_rep_who", "text": "Wer schaut auf die Daten?", "maps_to": "roles_involved"},
        {"id": "q_rep_systems", "text": "Welche Systeme liefern Reporting?", "maps_to": "systems_used"},
        {"id": "q_rep_why", "text": "Warum wird Reporting so gemacht?", "maps_to": "why_is_it_done_this_way"},
    ],
}

# ─── WHY quality constants ───────────────────────────────────────────────────

WHY_CATEGORIES = [
    "regulatory_requirement",
    "legal_constraint",
    "customer_specific_requirement",
    "technical_constraint",
    "tooling_or_license_limitation",
    "capacity_or_staffing",
    "temporary_transition_state",
    "historical_growth",
    "deliberate_local_optimization",
    "unknown_or_unclear",
]

WHY_QUALITY_LEVELS = ["strong", "medium", "weak"]

# Categories that alone do NOT constitute a strong rationale
_WEAK_WHY_CATEGORIES = {"historical_growth", "unknown_or_unclear"}

# ─── Evidence constants ──────────────────────────────────────────────────────

EVIDENCE_TYPES = [
    "interview",
    "document",
    "ticket_example",
    "sop",
    "policy",
    "system_screenshot",
    "other",
]

EVIDENCE_CONFIDENCE = ["high", "medium", "low"]

# ─── Review workflow constants ───────────────────────────────────────────────

REVIEW_STATUSES = ["draft", "captured", "challenged", "reviewed", "approved"]

# ─── Delta classification constants ──────────────────────────────────────────

DELTA_DIMENSIONS = [
    "tooling",
    "channel",
    "role_model",
    "governance",
    "documentation",
    "escalation",
    "reporting",
    "capacity",
    "control_design",
]

DELTA_NATURES = [
    "cosmetic",
    "procedural",
    "operationally_significant",
    "control_relevant",
    "potentially_blocking",
]

CONSTRAINT_TYPES = [
    "none",
    "legal",
    "regulatory",
    "contractual",
    "technical",
    "organizational",
    "economic",
    "unclear",
]

# ─── Recommendation constants ────────────────────────────────────────────────

# Legacy English types (kept for backward compat in stored data)
RECOMMENDATION_TYPES_LEGACY = [
    "keep_local", "harmonize", "centralize",
    "investigate_further", "remediate_control_gap",
]

# Current German operational types
RECOMMENDATION_TYPES = [
    "fehlende_information_erfassen",
    "begründung_klären",
    "evidenz_nachziehen",
    "kontrolllücke_beheben",
    "harmonisierung_prüfen",
    "lokal_beibehalten",
    "management_entscheidung_herbeiführen",
]

RECOMMENDATION_LABELS_DE = {
    "fehlende_information_erfassen": "Informationen erfassen",
    "begründung_klären": "Begründung klären",
    "evidenz_nachziehen": "Evidenz nachziehen",
    "kontrolllücke_beheben": "Kontrolllücke beheben",
    "harmonisierung_prüfen": "Harmonisierung prüfen",
    "lokal_beibehalten": "Lokal beibehalten",
    "management_entscheidung_herbeiführen": "Management-Entscheidung herbeiführen",
}

# ─── Maturity model constants ────────────────────────────────────────────────

MATURITY_LEVELS = [
    "nicht_begonnen",
    "grundlegend_erfasst",
    "strukturiert_erfasst",
    "begründet",
    "nachgewiesen",
    "reviewfähig",
    "freigegeben",
]

MATURITY_LABELS_DE = {
    "nicht_begonnen": "Nicht begonnen",
    "grundlegend_erfasst": "Grundlegend erfasst",
    "strukturiert_erfasst": "Strukturiert erfasst",
    "begründet": "Begründet",
    "nachgewiesen": "Nachgewiesen",
    "reviewfähig": "Reviewfähig",
    "freigegeben": "Freigegeben",
}

MATURITY_NEXT_STEP_DE = {
    "nicht_begonnen": "Beschreibung, Systeme und Rollen erfassen",
    "grundlegend_erfasst": "Systeme und Rollen ergänzen",
    "strukturiert_erfasst": "Begründung dokumentieren (WHY-Feld ausfüllen)",
    "begründet": "Evidenznachweise hinzufügen",
    "nachgewiesen": "Review vorbereiten: Pflichtfelder prüfen",
    "reviewfähig": "Review abschließen und freigeben",
    "freigegeben": "Keine weiteren Schritte erforderlich",
}

# ─── Task engine constants ────────────────────────────────────────────────────

TASK_TYPES = [
    "missing_description",
    "missing_systems",
    "missing_roles",
    "missing_why",
    "weak_why",
    "missing_evidence",
    "missing_output",
    "review_blocker",
    "harmonization_check",
    "control_gap_remediation",
    "management_decision_needed",
]

TASK_PRIORITIES = ["hoch", "mittel", "niedrig"]
TASK_STATUSES = ["offen", "in_bearbeitung", "erledigt", "verworfen"]

# ─── WHY quality assessment ──────────────────────────────────────────────────


def assess_why_quality(variant: dict) -> dict:
    """Assess the WHY quality of a variant based on categories and freetext.

    Returns dict with quality level, warnings, and whether categories are present.
    """
    why_text = variant.get("why_is_it_done_this_way", [])
    if isinstance(why_text, str):
        why_text = [why_text]
    has_freetext = any(str(w).strip() for w in (why_text or []))

    cats = variant.get("why_categories", [])
    if isinstance(cats, str):
        cats = [cats]
    cats = [c for c in (cats or []) if c in WHY_CATEGORIES]

    explicit_quality = variant.get("why_quality", "")
    warnings = []

    # If freetext present but no categories → warning
    if has_freetext and not cats:
        warnings.append("WHY freetext present but no why_category selected")

    # If only weak categories → warning
    if cats and all(c in _WEAK_WHY_CATEGORIES for c in cats):
        warnings.append("WHY based only on historical_growth/unknown_or_unclear — weak rationale")

    # Determine quality
    if explicit_quality in WHY_QUALITY_LEVELS:
        quality = explicit_quality
    elif not has_freetext and not cats:
        quality = "weak"
    elif cats and all(c in _WEAK_WHY_CATEGORIES for c in cats):
        quality = "weak"
    elif cats and any(c in ("regulatory_requirement", "legal_constraint", "technical_constraint") for c in cats):
        quality = "strong"
    elif cats:
        quality = "medium"
    elif has_freetext:
        quality = "medium"
    else:
        quality = "weak"

    return {
        "quality": quality,
        "categories": cats,
        "has_freetext": has_freetext,
        "warnings": warnings,
    }


# ─── Evidence assessment ─────────────────────────────────────────────────────


def assess_evidence_strength(variant: dict) -> dict:
    """Assess evidence strength of a variant.

    Returns dict with strength level, count, and warnings.
    """
    refs = variant.get("evidence_references", [])
    warnings = []

    if not refs:
        # Fall back to legacy evidence_or_examples field
        legacy = variant.get("evidence_or_examples", [])
        if legacy:
            return {
                "strength": "low",
                "count": len(legacy),
                "has_structured": False,
                "warnings": ["Only legacy evidence_or_examples present — no structured EvidenceReferences"],
            }
        return {"strength": "low", "count": 0, "has_structured": False, "warnings": ["No evidence references"]}

    # Check types
    types_present = {r.get("type", "other") for r in refs}
    interview_only = types_present == {"interview"} or types_present <= {"interview", "other"}

    if interview_only and len(refs) > 0:
        warnings.append("Evidence based on interviews only — consider adding documents/tickets")

    # Use explicit field if set
    explicit = variant.get("evidence_strength", "")
    if explicit in EVIDENCE_CONFIDENCE:
        return {"strength": explicit, "count": len(refs), "has_structured": True, "warnings": warnings}

    # Derive strength
    high_conf = sum(1 for r in refs if r.get("confidence") == "high")
    if len(refs) >= 2 and not interview_only and high_conf >= 1:
        strength = "high"
    elif len(refs) >= 1 and not interview_only:
        strength = "medium"
    elif interview_only:
        strength = "low"
    else:
        strength = "medium"

    return {"strength": strength, "count": len(refs), "has_structured": True, "warnings": warnings}


# ─── Review workflow validation ──────────────────────────────────────────────


def validate_review_status(variant: dict, new_status: str) -> dict:
    """Check if a review status transition is valid.

    Returns dict with valid (bool), reason, and current_status.
    """
    current = variant.get("review_status", "draft")
    if new_status not in REVIEW_STATUSES:
        return {"valid": False, "reason": f"Invalid status: {new_status}", "current_status": current}

    # approved requires: required fields + WHY + >=1 evidence
    if new_status == "approved":
        missing = []
        if not variant.get("description", "").strip():
            missing.append("description")
        if not variant.get("systems_used"):
            missing.append("systems_used")
        if not variant.get("roles_involved"):
            missing.append("roles_involved")
        why_q = assess_why_quality(variant)
        if not why_q["has_freetext"] and not why_q["categories"]:
            missing.append("why_is_it_done_this_way")
        ev = assess_evidence_strength(variant)
        if ev["count"] == 0:
            missing.append("evidence_references (at least 1 required)")
        if missing:
            return {
                "valid": False,
                "reason": f"Cannot approve: missing {', '.join(missing)}",
                "current_status": current,
            }

    return {"valid": True, "reason": "", "current_status": current}


# ─── Completeness & quality scoring ──────────────────────────────────────────

def score_variant_completeness(variant: dict) -> dict:
    """Score completeness of a single entity variant (0-100).

    Factors in: required fields (50%), bonus fields (15%), WHY quality (20%), evidence (15%).
    Returns dict with score, missing fields, warnings, why_quality, and evidence_strength.
    """
    required = ["description", "systems_used", "roles_involved", "why_is_it_done_this_way"]
    missing = []
    warnings = []

    for field in required:
        v = variant.get(field)
        if not v or (isinstance(v, list) and not any(str(x).strip() for x in v)):
            missing.append(field)
        elif isinstance(v, str) and not v.strip():
            missing.append(field)

    # Bonus fields that improve quality
    bonus_fields = ["trigger", "input_channels", "output", "sla_or_target",
                    "evidence_or_examples", "pain_points"]
    filled_bonus = sum(1 for f in bonus_fields
                       if variant.get(f) and (not isinstance(variant[f], list) or variant[f]))

    # WHY quality assessment
    why_q = assess_why_quality(variant)
    warnings.extend(why_q["warnings"])

    # Evidence assessment
    ev = assess_evidence_strength(variant)
    warnings.extend(ev["warnings"])

    # General warnings
    channels = variant.get("input_channels", [])
    if len(channels) > 2 and not variant.get("why_is_it_done_this_way"):
        warnings.append("Multiple input channels without WHY explanation")
    if not variant.get("why_is_it_done_this_way"):
        warnings.append("Missing WHY — cannot assess standardization rationale")
    if not variant.get("output"):
        warnings.append("No output defined")
    if variant.get("performed_in") in (None, "", "unknown"):
        warnings.append("Entity assignment unclear")

    # Score composition: required 50% + bonus 15% + WHY quality 20% + evidence 15%
    req_score = ((len(required) - len(missing)) / len(required)) * 50
    bonus_score = (filled_bonus / max(len(bonus_fields), 1)) * 15

    why_score_map = {"strong": 20, "medium": 12, "weak": 4}
    why_score = why_score_map.get(why_q["quality"], 0)

    ev_score_map = {"high": 15, "medium": 10, "low": 5}
    ev_score = ev_score_map.get(ev["strength"], 0) if ev["count"] > 0 else 0

    total = round(req_score + bonus_score + why_score + ev_score)

    return {
        "score": min(total, 100),
        "missing_fields": missing,
        "warnings": warnings,
        "why_quality": why_q["quality"],
        "evidence_strength": ev["strength"] if ev["count"] > 0 else "none",
        "evidence_count": ev["count"],
        "review_status": variant.get("review_status", "draft"),
    }


def score_step_completeness(step: dict) -> dict:
    """Score completeness of a process step across all entity variants."""
    variants = step.get("entity_variants", [])
    if not variants:
        return {"score": 0, "entity_scores": {}, "warnings": ["No entity variants defined"]}

    entity_scores = {}
    for v in variants:
        eid = v.get("entity_id", "unknown")
        entity_scores[eid] = score_variant_completeness(v)

    avg = round(sum(s["score"] for s in entity_scores.values()) / len(entity_scores))
    warnings = []
    for eid, s in entity_scores.items():
        if s["score"] < 50:
            warnings.append(f"{eid}: incomplete ({s['score']}%)")
    return {"score": avg, "entity_scores": entity_scores, "warnings": warnings}


def score_analysis_completeness(analysis: dict) -> dict:
    """Score overall analysis completeness."""
    steps = analysis.get("process_steps", [])
    if not steps:
        return {"score": 0, "step_scores": {}, "warnings": ["No process steps defined"]}

    step_scores = {}
    for step in steps:
        sid = step.get("step_id", "unknown")
        step_scores[sid] = score_step_completeness(step)

    avg = round(sum(s["score"] for s in step_scores.values()) / len(step_scores)) if step_scores else 0

    # Count missing WHYs
    missing_whys = 0
    total_variants = 0
    for step in steps:
        for v in step.get("entity_variants", []):
            total_variants += 1
            why = v.get("why_is_it_done_this_way")
            if not why or (isinstance(why, list) and not any(str(x).strip() for x in why)):
                missing_whys += 1

    warnings = []
    if missing_whys > 0:
        warnings.append(f"{missing_whys}/{total_variants} variants missing WHY explanation")

    return {"score": avg, "step_scores": step_scores, "missing_whys": missing_whys,
            "total_variants": total_variants, "warnings": warnings}


# ─── Step-level delta computation ─────────────────────────────────────────────

def _norm_set(items):
    """Normalize a list to a comparable set."""
    if isinstance(items, str):
        items = [items]
    return {str(x).strip().lower() for x in (items or []) if str(x).strip()}


def compute_step_delta(step: dict) -> list[dict]:
    """Compute deltas between entity variants within a single process step.

    Returns list of delta items.
    """
    variants = step.get("entity_variants", [])
    if len(variants) < 2:
        return []

    deltas = []
    step_id = step.get("step_id", "")
    step_name = step.get("step_name", step_id)

    # Compare all pairs — for DE/AT this is just one pair
    compared = set()
    for i, va in enumerate(variants):
        for j, vb in enumerate(variants):
            if i >= j:
                continue
            pair = (va.get("entity_id", ""), vb.get("entity_id", ""))
            if pair in compared:
                continue
            compared.add(pair)
            deltas.extend(_compare_variants(step_id, step_name, va, vb))

    return deltas


def _compare_variants(step_id: str, step_name: str, va: dict, vb: dict) -> list[dict]:
    """Compare two entity variants and produce delta items."""
    ea = va.get("entity_id", "?")
    eb = vb.get("entity_id", "?")
    entities = [ea, eb]
    deltas = []

    comparisons = [
        ("systems_used", "system_difference", True),
        ("input_channels", "channel_difference", True),
        ("roles_involved", "role_difference", True),
        ("variants", "variant_difference", False),
    ]

    for field, delta_type, is_critical in comparisons:
        set_a = _norm_set(va.get(field, []))
        set_b = _norm_set(vb.get(field, []))

        # Extract role names if roles are dicts
        if field == "roles_involved":
            set_a = {(r.get("role", r) if isinstance(r, dict) else str(r)).strip().lower()
                     for r in (va.get(field) or [])}
            set_b = {(r.get("role", r) if isinstance(r, dict) else str(r)).strip().lower()
                     for r in (vb.get(field) or [])}

        if not set_a and not set_b:
            continue
        if set_a == set_b:
            continue

        # Determine overlap
        if not set_a or not set_b:
            impact = "high" if is_critical else "medium"
            desc = f"{field.replace('_', ' ').title()} missing in {'both' if not set_a and not set_b else ea if not set_a else eb}"
            std_relevance = "high"
        else:
            overlap = len(set_a & set_b) / len(set_a | set_b) if set_a | set_b else 1
            if overlap == 0:
                impact = "high" if is_critical else "medium"
                desc = f"{field.replace('_', ' ').title()} completely different ({ea}: {', '.join(sorted(set_a))}; {eb}: {', '.join(sorted(set_b))})"
                std_relevance = "high"
            else:
                impact = "medium"
                only_a = sorted(set_a - set_b)
                only_b = sorted(set_b - set_a)
                desc = f"{field.replace('_', ' ').title()} partially aligned"
                if only_a:
                    desc += f"; {ea}-only: {', '.join(only_a)}"
                if only_b:
                    desc += f"; {eb}-only: {', '.join(only_b)}"
                std_relevance = "medium"

        # Classify delta dimension and nature
        dim, nature, ctype = _classify_delta_fields(field, step_id, impact, va, vb)

        deltas.append({
            "step_id": step_id,
            "step_name": step_name,
            "delta_type": delta_type,
            "description": desc,
            "entities_involved": entities,
            "impact": impact,
            "standardization_relevance": std_relevance,
            "hard_constraint_flag": False,
            "rationale": "",
            "delta_dimension": dim,
            "delta_nature": nature,
            "constraint_type": ctype,
            "constraint_evidence": "",
            "needs_management_decision": nature in ("operationally_significant", "control_relevant", "potentially_blocking"),
        })

    # Check for missing WHY
    why_a = bool(_norm_set(va.get("why_is_it_done_this_way", [])))
    why_b = bool(_norm_set(vb.get("why_is_it_done_this_way", [])))
    if not why_a or not why_b:
        missing_in = []
        if not why_a:
            missing_in.append(ea)
        if not why_b:
            missing_in.append(eb)
        deltas.append({
            "step_id": step_id,
            "step_name": step_name,
            "delta_type": "missing_rationale",
            "description": f"WHY explanation missing in {', '.join(missing_in)} — cannot assess standardization rationale",
            "entities_involved": entities,
            "impact": "high",
            "standardization_relevance": "high",
            "hard_constraint_flag": False,
            "rationale": "Missing WHY blocks informed standardization decision",
            "delta_dimension": "governance",
            "delta_nature": "control_relevant",
            "constraint_type": "none",
            "constraint_evidence": "",
            "needs_management_decision": False,
        })

    # Check for missing escalation/documentation/reporting (control gaps)
    for check_field, dim_label in [("escalation", "escalation"), ("closure", "documentation"), ("reporting", "reporting")]:
        if step_id == check_field:
            for ent_variant in [va, vb]:
                eid = ent_variant.get("entity_id", "?")
                desc_text = (ent_variant.get("description") or "").lower()
                if any(kw in desc_text for kw in ("no formal", "informal", "ad-hoc", "ad hoc", "no defined", "no systematic")):
                    deltas.append({
                        "step_id": step_id,
                        "step_name": step_name,
                        "delta_type": "control_gap",
                        "description": f"Control gap: {dim_label} process is informal/missing in {eid}",
                        "entities_involved": [eid],
                        "impact": "high",
                        "standardization_relevance": "high",
                        "hard_constraint_flag": False,
                        "rationale": f"Missing formal {dim_label} represents a control gap",
                        "delta_dimension": dim_label,
                        "delta_nature": "control_relevant",
                        "constraint_type": "none",
                        "constraint_evidence": "",
                        "needs_management_decision": True,
                    })

    return deltas


def _classify_delta_fields(field: str, step_id: str, impact: str,
                           va: dict, vb: dict) -> tuple[str, str, str]:
    """Derive delta_dimension, delta_nature, and constraint_type from a field comparison."""

    # Map field to dimension
    dim_map = {
        "systems_used": "tooling",
        "input_channels": "channel",
        "roles_involved": "role_model",
        "variants": "governance",
    }
    dimension = dim_map.get(field, "governance")

    # Override dimension for specific steps
    step_dim = {
        "escalation": "escalation",
        "reporting": "reporting",
        "closure": "documentation",
    }
    if step_id in step_dim and field in ("systems_used", "variants"):
        dimension = step_dim[step_id]

    # Determine nature
    if field == "systems_used" and step_id in ("intake", "processing"):
        nature = "operationally_significant"
    elif field == "systems_used" and impact == "high":
        nature = "operationally_significant"
    elif step_id in ("escalation", "reporting", "closure") and impact == "high":
        nature = "control_relevant"
    elif impact == "high":
        nature = "procedural"
    else:
        nature = "cosmetic"

    # Determine constraint type from WHY categories
    constraint = "none"
    for v in [va, vb]:
        cats = v.get("why_categories", [])
        if isinstance(cats, str):
            cats = [cats]
        for c in (cats or []):
            if c == "regulatory_requirement":
                constraint = "regulatory"
                break
            elif c == "legal_constraint":
                constraint = "legal"
                break
            elif c == "technical_constraint":
                constraint = "technical"
                break
            elif c == "tooling_or_license_limitation":
                constraint = "technical"
                break
            elif c == "customer_specific_requirement":
                constraint = "contractual"
                break
            elif c == "capacity_or_staffing":
                constraint = "organizational"
                break
            elif c == "unknown_or_unclear":
                constraint = "unclear"
        if constraint != "none":
            break

    return dimension, nature, constraint


def compute_analysis_deltas(analysis: dict) -> list[dict]:
    """Compute all deltas across all process steps in an analysis."""
    all_deltas = []
    for step in analysis.get("process_steps", []):
        all_deltas.extend(compute_step_delta(step))
    return all_deltas


# ─── Recommendation engine ───────────────────────────────────────────────────

_REC_COUNTER = 0


def _next_rec_id() -> str:
    global _REC_COUNTER
    _REC_COUNTER += 1
    return f"rec_{_REC_COUNTER:04d}"


def generate_recommendations(analysis: dict, deltas: list[dict] | None = None) -> list[dict]:
    """Generate rule-based recommendations from analysis and deltas.

    Returns list of recommendation dicts.
    """
    if deltas is None:
        deltas = compute_analysis_deltas(analysis)

    recs = []
    steps = {s["step_id"]: s for s in analysis.get("process_steps", [])}

    # Group deltas by step
    deltas_by_step: dict[str, list[dict]] = {}
    for d in deltas:
        deltas_by_step.setdefault(d["step_id"], []).append(d)

    for step_id, step_deltas in deltas_by_step.items():
        step = steps.get(step_id, {})
        variants = step.get("entity_variants", [])
        variant_map = {v.get("entity_id", ""): v for v in variants}

        for d in step_deltas:
            rec = _rule_based_recommendation(d, step_id, step, variant_map)
            if rec:
                recs.append(rec)

    # Deduplicate by combining recommendations of same type for same step
    return _deduplicate_recommendations(recs)


def _rule_based_recommendation(delta: dict, step_id: str, step: dict,
                               variant_map: dict) -> dict | None:
    """Apply rules to a single delta to produce a recommendation (German types)."""
    d_type = delta.get("delta_type", "")
    nature = delta.get("delta_nature", "procedural")
    constraint = delta.get("constraint_type", "none")
    impact = delta.get("impact", "medium")
    dimension = delta.get("delta_dimension", "")
    delta_id = f"{step_id}:{d_type}"

    dim_de = {
        "tooling": "System/Werkzeug", "channel": "Kanal", "role_model": "Rollenmodell",
        "governance": "Governance", "documentation": "Dokumentation",
        "escalation": "Eskalation", "reporting": "Reporting",
        "capacity": "Kapazität", "control_design": "Kontrolldesign",
    }.get(dimension, dimension)

    # Kontrolllücke beheben
    if d_type == "control_gap":
        return {
            "id": _next_rec_id(),
            "title": f"Kontrolllücke beheben: {dim_de} in Schritt '{step_id}'",
            "recommendation_type": "kontrolllücke_beheben",
            "rationale": delta.get("description", ""),
            "based_on_step_ids": [step_id],
            "based_on_delta_ids": [delta_id],
            "priority": "hoch",
            "assumptions": [],
            "blockers": [],
            "expected_benefit": f"Kontrolllücke im Bereich {dim_de} schließen",
            "implementation_complexity": "mittel",
        }

    # Begründung klären (fehlende WHY)
    if d_type == "missing_rationale":
        return {
            "id": _next_rec_id(),
            "title": f"Begründung klären: Schritt '{step_id}'",
            "recommendation_type": "begründung_klären",
            "rationale": "Ohne Begründung ist keine fundierte Harmonisierungsentscheidung möglich.",
            "based_on_step_ids": [step_id],
            "based_on_delta_ids": [delta_id],
            "priority": "hoch",
            "assumptions": ["Begründung kann in Follow-up-Gespräch erhoben werden"],
            "blockers": [],
            "expected_benefit": "Fundierte Entscheidungsgrundlage schaffen",
            "implementation_complexity": "niedrig",
        }

    # Lokal beibehalten (harter Constraint)
    if constraint in ("legal", "regulatory", "technical"):
        constraint_de = {"legal": "rechtlich", "regulatory": "regulatorisch", "technical": "technisch"}[constraint]
        return {
            "id": _next_rec_id(),
            "title": f"Lokal beibehalten: {dim_de} ({constraint_de} begründet)",
            "recommendation_type": "lokal_beibehalten",
            "rationale": f"Harter {constraint_de}er Constraint rechtfertigt lokale Variante.",
            "based_on_step_ids": [step_id],
            "based_on_delta_ids": [delta_id],
            "priority": "niedrig",
            "assumptions": [f"Der {constraint_de}e Constraint ist validiert"],
            "blockers": [],
            "expected_benefit": "Dokumentierte Akzeptanz der begründeten lokalen Abweichung",
            "implementation_complexity": "niedrig",
        }

    # Harmonisierung prüfen (operativ signifikant, kein harter Constraint)
    if nature == "operationally_significant" and constraint in ("none", "organizational", "unclear"):
        has_weak = any(
            assess_why_quality(v)["quality"] == "weak" or assess_evidence_strength(v)["strength"] == "low"
            for v in variant_map.values()
        )
        if has_weak:
            return {
                "id": _next_rec_id(),
                "title": f"Evidenz nachziehen: {dim_de} in Schritt '{step_id}' (schwache Begründung/Evidenz)",
                "recommendation_type": "evidenz_nachziehen",
                "rationale": "Operativ bedeutsame Abweichung, aber Begründung oder Evidenz zu schwach für Entscheidung.",
                "based_on_step_ids": [step_id],
                "based_on_delta_ids": [delta_id],
                "priority": "hoch",
                "assumptions": ["Zusätzliche Evidenz kann Empfehlung verändern"],
                "blockers": ["Schwache Begründung oder fehlende Evidenz"],
                "expected_benefit": "Fundierte Entscheidung nach Nacherhebung",
                "implementation_complexity": "niedrig",
            }
        return {
            "id": _next_rec_id(),
            "title": f"Harmonisierung prüfen: {dim_de} in Schritt '{step_id}'",
            "recommendation_type": "harmonisierung_prüfen",
            "rationale": "Operativ bedeutsame Abweichung ohne harten Constraint — Harmonisierungskandidat.",
            "based_on_step_ids": [step_id],
            "based_on_delta_ids": [delta_id],
            "priority": "hoch",
            "assumptions": ["Keine unentdeckten harten Constraints vorhanden"],
            "blockers": [],
            "expected_benefit": f"Standardisiertes {dim_de} über alle Einheiten",
            "implementation_complexity": "hoch" if dimension == "tooling" else "mittel",
        }

    # Management-Entscheidung herbeiführen
    if constraint == "organizational":
        return {
            "id": _next_rec_id(),
            "title": f"Management-Entscheidung: {dim_de} in Schritt '{step_id}'",
            "recommendation_type": "management_entscheidung_herbeiführen",
            "rationale": "Abweichung durch Kapazitäts-/Ressourcenengpass bedingt — Klärung auf Managementebene erforderlich.",
            "based_on_step_ids": [step_id],
            "based_on_delta_ids": [delta_id],
            "priority": "mittel",
            "assumptions": ["Ressourcenengpass kann behoben werden"],
            "blockers": ["Budget-/Personalentscheidung erforderlich"],
            "expected_benefit": "Harmonisierung bei Behebung des Engpasses möglich",
            "implementation_complexity": "mittel",
        }

    # Begründung klären (unklarer Constraint)
    if constraint == "unclear":
        return {
            "id": _next_rec_id(),
            "title": f"Begründung klären: unklarer Constraint für {dim_de} in '{step_id}'",
            "recommendation_type": "begründung_klären",
            "rationale": "Constraint-Basis unklar — Validierung vor Entscheidung erforderlich.",
            "based_on_step_ids": [step_id],
            "based_on_delta_ids": [delta_id],
            "priority": "mittel",
            "assumptions": [],
            "blockers": ["Constraint-Validierung ausstehend"],
            "expected_benefit": "Klarheit, ob lokale Variante begründet ist",
            "implementation_complexity": "niedrig",
        }

    # Harmonisierung prüfen (kosmetisch/prozedural)
    if nature == "cosmetic":
        return {
            "id": _next_rec_id(),
            "title": f"Harmonisierung prüfen: Benennung {dim_de} in '{step_id}'",
            "recommendation_type": "harmonisierung_prüfen",
            "rationale": "Kosmetische Abweichung — unterschiedliche Benennung ohne Prozessauswirkung.",
            "based_on_step_ids": [step_id],
            "based_on_delta_ids": [delta_id],
            "priority": "niedrig",
            "assumptions": ["Keine versteckte Prozessabweichung hinter der Benennung"],
            "blockers": [],
            "expected_benefit": "Einheitliche Terminologie über alle Einheiten",
            "implementation_complexity": "niedrig",
        }

    if nature == "procedural" and impact != "low":
        return {
            "id": _next_rec_id(),
            "title": f"Harmonisierung prüfen: {dim_de}-Vorgehen in '{step_id}'",
            "recommendation_type": "harmonisierung_prüfen",
            "rationale": "Prozessuale Abweichung ohne harten Constraint.",
            "based_on_step_ids": [step_id],
            "based_on_delta_ids": [delta_id],
            "priority": "mittel",
            "assumptions": [],
            "blockers": [],
            "expected_benefit": f"Einheitliches {dim_de}-Vorgehen",
            "implementation_complexity": "mittel",
        }

    return None


def _deduplicate_recommendations(recs: list[dict]) -> list[dict]:
    """Merge recommendations of same type targeting same step."""
    seen: dict[str, dict] = {}
    result = []
    for r in recs:
        key = f"{r['recommendation_type']}::{','.join(sorted(r['based_on_step_ids']))}"
        if key in seen:
            existing = seen[key]
            for did in r["based_on_delta_ids"]:
                if did not in existing["based_on_delta_ids"]:
                    existing["based_on_delta_ids"].append(did)
            for a in r.get("assumptions", []):
                if a not in existing["assumptions"]:
                    existing["assumptions"].append(a)
            for b in r.get("blockers", []):
                if b not in existing["blockers"]:
                    existing["blockers"].append(b)
            # Keep higher priority
            prio_order = {"hoch": 0, "mittel": 1, "niedrig": 2}
            if prio_order.get(r["priority"], 1) < prio_order.get(existing["priority"], 1):
                existing["priority"] = r["priority"]
        else:
            seen[key] = r
            result.append(r)
    return result


# ─── Management summary ──────────────────────────────────────────────────────


def compute_analysis_summary(analysis: dict) -> dict:
    """Compute management-level summary with decision support counters."""
    completeness = score_analysis_completeness(analysis)
    deltas = compute_analysis_deltas(analysis)
    recs = generate_recommendations(analysis, deltas)

    high_deltas = sum(1 for d in deltas if d["impact"] == "high")
    medium_deltas = sum(1 for d in deltas if d["impact"] == "medium")

    steps = analysis.get("process_steps", [])
    entities = set()
    all_variants = []
    review_counts: dict[str, int] = {s: 0 for s in REVIEW_STATUSES}
    weak_why_count = 0
    evidence_gap_count = 0

    for step in steps:
        for v in step.get("entity_variants", []):
            entities.add(v.get("entity_id", ""))
            all_variants.append(v)
            # Review status count
            rs = v.get("review_status", "draft")
            review_counts[rs] = review_counts.get(rs, 0) + 1
            # WHY quality
            wq = assess_why_quality(v)
            if wq["quality"] == "weak":
                weak_why_count += 1
            # Evidence gaps
            ev = assess_evidence_strength(v)
            if ev["count"] == 0:
                evidence_gap_count += 1

    # Steps with strong differences
    steps_with_high = set()
    for d in deltas:
        if d["impact"] == "high":
            steps_with_high.add(d["step_id"])

    # Recommendation type counts
    rec_type_counts = {}
    for r in recs:
        rt = r["recommendation_type"]
        rec_type_counts[rt] = rec_type_counts.get(rt, 0) + 1

    standardization_candidates = rec_type_counts.get("harmonisierung_prüfen", 0)
    likely_keep_local = rec_type_counts.get("lokal_beibehalten", 0)
    control_gaps = sum(1 for d in deltas if d.get("delta_type") == "control_gap")
    mgmt_decisions = sum(1 for d in deltas if d.get("needs_management_decision"))

    # Top 5 key differences (high impact)
    top_differences = sorted(
        [d for d in deltas if d["impact"] == "high"],
        key=lambda d: d.get("step_name", ""),
    )[:5]

    # Top 5 open evidence/review gaps
    open_gaps = []
    for step in steps:
        for v in step.get("entity_variants", []):
            eid = v.get("entity_id", "?")
            ev = assess_evidence_strength(v)
            wq = assess_why_quality(v)
            rs = v.get("review_status", "draft")
            issues = []
            if ev["count"] == 0:
                issues.append("no evidence")
            if wq["quality"] == "weak":
                issues.append("weak WHY")
            if rs in ("draft", "captured"):
                issues.append(f"review: {rs}")
            if issues:
                open_gaps.append({
                    "step_id": step["step_id"],
                    "step_name": step.get("step_name", step["step_id"]),
                    "entity_id": eid,
                    "issues": issues,
                })
    open_gaps = open_gaps[:5]

    # Maturity distribution across all variants
    maturity_distribution: dict[str, int] = {lvl: 0 for lvl in MATURITY_LEVELS}
    for step in steps:
        for v in step.get("entity_variants", []):
            m = assess_variant_maturity(v)
            maturity_distribution[m["level"]] = maturity_distribution.get(m["level"], 0) + 1

    # Task counts
    tasks = generate_tasks(analysis)
    task_counts = {
        "total": len(tasks),
        "hoch": sum(1 for t in tasks if t["priority"] == "hoch"),
        "mittel": sum(1 for t in tasks if t["priority"] == "mittel"),
        "niedrig": sum(1 for t in tasks if t["priority"] == "niedrig"),
        "blocking": sum(1 for t in tasks if t["blocking_flag"]),
    }

    # Overall tendency
    if completeness["score"] < 40 or evidence_gap_count > len(all_variants) * 0.5:
        tendency = "insufficiently_captured"
    elif standardization_candidates == 0 and likely_keep_local > 0:
        tendency = "strongly_local"
    elif standardization_candidates > 0 and likely_keep_local > 0:
        tendency = "partially_harmonizable"
    elif standardization_candidates > 0:
        tendency = "harmonizable"
    else:
        tendency = "insufficiently_captured"

    return {
        "total_steps": len(steps),
        "entities": sorted(entities),
        "completeness_score": completeness["score"],
        "missing_whys": completeness.get("missing_whys", 0),
        "total_variants": completeness.get("total_variants", 0),
        "total_deltas": len(deltas),
        "high_impact_deltas": high_deltas,
        "medium_impact_deltas": medium_deltas,
        "steps_with_high_differences": sorted(steps_with_high),
        "step_scores": completeness.get("step_scores", {}),
        # New decision support counters
        "standardization_candidates_count": standardization_candidates,
        "likely_keep_local_count": likely_keep_local,
        "control_gaps_count": control_gaps,
        "evidence_gaps_count": evidence_gap_count,
        "weak_why_count": weak_why_count,
        "management_decisions_needed_count": mgmt_decisions,
        "review_status_counts": review_counts,
        "recommendation_type_counts": rec_type_counts,
        "top_differences": [{"step_id": d["step_id"], "step_name": d["step_name"],
                             "delta_type": d["delta_type"], "description": d["description"]}
                            for d in top_differences],
        "open_gaps": open_gaps,
        "tendency": tendency,
        "recommendations": recs,
        "maturity_distribution": maturity_distribution,
        "task_counts": task_counts,
    }


def scaffold_analysis(stream_id: str, stream_name: str, entities: list[str]) -> dict:
    """Create a new process analysis scaffold with default phases."""
    steps = []
    for phase in DEFAULT_PROCESS_PHASES:
        step = {
            "step_id": phase["step_id"],
            "step_name": phase["step_name"],
            "sort_order": phase["sort_order"],
            "entity_variants": [
                _empty_variant(eid) for eid in entities
            ],
        }
        steps.append(step)

    return {
        "stream_id": stream_id,
        "stream_name": stream_name,
        "status": "draft",
        "entities": entities,
        "process_steps": steps,
    }


def _empty_variant(entity_id: str) -> dict:
    return {
        "entity_id": entity_id,
        "entity_name": entity_id,
        "description": "",
        "trigger": "",
        "input_channels": [],
        "systems_used": [],
        "roles_involved": [],
        "output": "",
        "sla_or_target": "",
        "approx_volume": "",
        "variants": [],
        "pain_points": [],
        "why_is_it_done_this_way": [],
        "why_categories": [],
        "why_quality": "",
        "why_review_note": "",
        "evidence_or_examples": [],
        "evidence_references": [],
        "evidence_strength": "",
        "review_status": "draft",
        "review_comment": "",
        "reviewed_by": "",
        "reviewed_at": "",
        "performed_in": entity_id,
        "maturity_notes": "",
    }


# ─── Maturity model ──────────────────────────────────────────────────────────


def assess_variant_maturity(variant: dict) -> dict:
    """Compute maturity level for a single entity variant.

    Returns dict with level, label, next_step, and index (0-based).
    """
    review_status = variant.get("review_status", "draft")

    # Level 6: freigegeben — approved in review
    if review_status == "approved":
        level = "freigegeben"
        return {
            "level": level,
            "label": MATURITY_LABELS_DE[level],
            "next_step": MATURITY_NEXT_STEP_DE[level],
            "index": MATURITY_LEVELS.index(level),
        }

    # Check required fields
    has_description = bool((variant.get("description") or "").strip())
    systems = variant.get("systems_used") or []
    roles = variant.get("roles_involved") or []
    has_systems = bool(systems if not isinstance(systems, str) else systems.strip())
    has_roles = bool(roles if not isinstance(roles, str) else roles.strip())

    why_q = assess_why_quality(variant)
    has_why = why_q["has_freetext"] or bool(why_q["categories"])

    ev = assess_evidence_strength(variant)
    has_evidence = ev["count"] > 0

    # Level 5: reviewfähig — all required fields + evidence, not yet approved
    if has_description and has_systems and has_roles and has_why and has_evidence and review_status in ("reviewed", "challenged"):
        level = "reviewfähig"
        return {
            "level": level,
            "label": MATURITY_LABELS_DE[level],
            "next_step": MATURITY_NEXT_STEP_DE[level],
            "index": MATURITY_LEVELS.index(level),
        }

    # Level 4: nachgewiesen — all required + evidence, but not ready for review
    if has_description and has_systems and has_roles and has_why and has_evidence:
        level = "nachgewiesen"
        return {
            "level": level,
            "label": MATURITY_LABELS_DE[level],
            "next_step": MATURITY_NEXT_STEP_DE[level],
            "index": MATURITY_LEVELS.index(level),
        }

    # Level 3: begründet — required fields present + WHY, but no evidence
    if has_description and has_systems and has_roles and has_why:
        level = "begründet"
        return {
            "level": level,
            "label": MATURITY_LABELS_DE[level],
            "next_step": MATURITY_NEXT_STEP_DE[level],
            "index": MATURITY_LEVELS.index(level),
        }

    # Level 2: strukturiert_erfasst — description + systems + roles
    if has_description and has_systems and has_roles:
        level = "strukturiert_erfasst"
        return {
            "level": level,
            "label": MATURITY_LABELS_DE[level],
            "next_step": MATURITY_NEXT_STEP_DE[level],
            "index": MATURITY_LEVELS.index(level),
        }

    # Level 1: grundlegend_erfasst — at least description present
    if has_description:
        level = "grundlegend_erfasst"
        return {
            "level": level,
            "label": MATURITY_LABELS_DE[level],
            "next_step": MATURITY_NEXT_STEP_DE[level],
            "index": MATURITY_LEVELS.index(level),
        }

    # Level 0: nicht_begonnen
    level = "nicht_begonnen"
    return {
        "level": level,
        "label": MATURITY_LABELS_DE[level],
        "next_step": MATURITY_NEXT_STEP_DE[level],
        "index": MATURITY_LEVELS.index(level),
    }


# ─── Task engine ─────────────────────────────────────────────────────────────

_TASK_COUNTER = 0


def _next_task_id() -> str:
    global _TASK_COUNTER
    _TASK_COUNTER += 1
    return f"task_{_TASK_COUNTER:04d}"


def generate_tasks(analysis: dict) -> list[dict]:
    """Generate computed GuidanceTask objects from analysis data gaps and deltas.

    Tasks are read-only and fully computed from the current state of the analysis.
    """
    tasks: list[dict] = []
    stream_id = analysis.get("stream_id", "")

    for step in analysis.get("process_steps", []):
        step_id = step.get("step_id", "")
        for variant in step.get("entity_variants", []):
            entity_id = variant.get("entity_id", "")
            tasks.extend(_tasks_for_variant(stream_id, step_id, variant, entity_id))

    # Generate cross-variant tasks from deltas
    deltas = compute_analysis_deltas(analysis)
    steps = {s["step_id"]: s for s in analysis.get("process_steps", [])}
    for delta in deltas:
        step_id = delta.get("step_id", "")
        d_type = delta.get("delta_type", "")
        nature = delta.get("delta_nature", "")
        step = steps.get(step_id, {})
        step_name = step.get("step_name", step_id)

        if d_type == "control_gap":
            entities_involved = delta.get("entities_involved", [])
            entity_id = entities_involved[0] if entities_involved else "?"
            tasks.append({
                "id": _next_task_id(),
                "stream_id": stream_id,
                "step_id": step_id,
                "entity_id": entity_id,
                "task_type": "control_gap_remediation",
                "priority": "hoch",
                "title": f"Kontrolllücke beheben: {step_name}",
                "description": delta.get("description", ""),
                "rationale": "Eine formale Kontrolle fehlt — dies stellt ein Kontrolldefizit dar.",
                "based_on": f"delta:{step_id}:{d_type}",
                "status": "offen",
                "suggested_owner_role": "Process Owner",
                "blocking_flag": True,
            })

        elif d_type == "missing_rationale":
            for entity_id in delta.get("entities_involved", []):
                entity_variant = next(
                    (v for v in step.get("entity_variants", []) if v.get("entity_id") == entity_id),
                    {}
                )
                why_q = assess_why_quality(entity_variant)
                if why_q["has_freetext"] or why_q["categories"]:
                    continue  # already has WHY
                tasks.append({
                    "id": _next_task_id(),
                    "stream_id": stream_id,
                    "step_id": step_id,
                    "entity_id": entity_id,
                    "task_type": "missing_why",
                    "priority": "hoch",
                    "title": f"WHY-Begründung erfassen: {step_name} ({entity_id})",
                    "description": "Begründung fehlt — ohne WHY ist keine Harmonisierungsentscheidung möglich.",
                    "rationale": "Fehlende Begründung blockiert Standardisierungsanalyse.",
                    "based_on": f"delta:{step_id}:missing_rationale",
                    "status": "offen",
                    "suggested_owner_role": "Process Owner",
                    "blocking_flag": True,
                })

        elif nature in ("operationally_significant", "control_relevant") and d_type not in ("control_gap", "missing_rationale"):
            needs_mgmt = delta.get("needs_management_decision", False)
            if needs_mgmt:
                tasks.append({
                    "id": _next_task_id(),
                    "stream_id": stream_id,
                    "step_id": step_id,
                    "entity_id": "",
                    "task_type": "management_decision_needed",
                    "priority": "mittel",
                    "title": f"Management-Entscheidung: {step_name}",
                    "description": delta.get("description", ""),
                    "rationale": "Operativ bedeutsame Abweichung erfordert Entscheidung auf Managementebene.",
                    "based_on": f"delta:{step_id}:{d_type}",
                    "status": "offen",
                    "suggested_owner_role": "Management",
                    "blocking_flag": False,
                })
            else:
                tasks.append({
                    "id": _next_task_id(),
                    "stream_id": stream_id,
                    "step_id": step_id,
                    "entity_id": "",
                    "task_type": "harmonization_check",
                    "priority": "mittel",
                    "title": f"Harmonisierung prüfen: {step_name}",
                    "description": delta.get("description", ""),
                    "rationale": "Operativ bedeutsame Abweichung ohne harten Constraint — Harmonisierungspotenzial prüfen.",
                    "based_on": f"delta:{step_id}:{d_type}",
                    "status": "offen",
                    "suggested_owner_role": "Process Owner",
                    "blocking_flag": False,
                })

    # Sort: blocking first, then by priority
    prio_order = {"hoch": 0, "mittel": 1, "niedrig": 2}
    tasks.sort(key=lambda t: (0 if t["blocking_flag"] else 1, prio_order.get(t["priority"], 1)))
    return tasks


def _tasks_for_variant(stream_id: str, step_id: str, variant: dict, entity_id: str) -> list[dict]:
    """Generate tasks for a single entity variant based on data gaps."""
    tasks = []
    maturity = assess_variant_maturity(variant)
    maturity_index = maturity["index"]

    # missing_description (priority: hoch)
    if not (variant.get("description") or "").strip():
        tasks.append({
            "id": _next_task_id(),
            "stream_id": stream_id,
            "step_id": step_id,
            "entity_id": entity_id,
            "task_type": "missing_description",
            "priority": "hoch",
            "title": f"Beschreibung erfassen: Schritt '{step_id}' ({entity_id})",
            "description": "Keine Beschreibung vorhanden. Bitte den Prozessschritt beschreiben.",
            "rationale": "Ohne Beschreibung kann der Prozessschritt nicht analysiert werden.",
            "based_on": f"variant:{step_id}:{entity_id}:description",
            "status": "offen",
            "suggested_owner_role": "Process Owner",
            "blocking_flag": True,
        })

    # missing_systems (priority: hoch if no description yet, else mittel)
    systems = variant.get("systems_used") or []
    if not systems:
        tasks.append({
            "id": _next_task_id(),
            "stream_id": stream_id,
            "step_id": step_id,
            "entity_id": entity_id,
            "task_type": "missing_systems",
            "priority": "hoch" if maturity_index < 2 else "mittel",
            "title": f"Systeme ergänzen: Schritt '{step_id}' ({entity_id})",
            "description": "Keine genutzten Systeme angegeben.",
            "rationale": "Systemangaben sind für die Technologieanalyse und Harmonisierung erforderlich.",
            "based_on": f"variant:{step_id}:{entity_id}:systems_used",
            "status": "offen",
            "suggested_owner_role": "Process Owner",
            "blocking_flag": False,
        })

    # missing_roles (priority: mittel)
    roles = variant.get("roles_involved") or []
    if not roles:
        tasks.append({
            "id": _next_task_id(),
            "stream_id": stream_id,
            "step_id": step_id,
            "entity_id": entity_id,
            "task_type": "missing_roles",
            "priority": "mittel",
            "title": f"Rollen erfassen: Schritt '{step_id}' ({entity_id})",
            "description": "Keine beteiligten Rollen angegeben.",
            "rationale": "Rollen sind für Verantwortlichkeitsanalyse und Governance erforderlich.",
            "based_on": f"variant:{step_id}:{entity_id}:roles_involved",
            "status": "offen",
            "suggested_owner_role": "Process Owner",
            "blocking_flag": False,
        })

    # missing_why / weak_why (priority: hoch)
    why_q = assess_why_quality(variant)
    if not why_q["has_freetext"] and not why_q["categories"]:
        tasks.append({
            "id": _next_task_id(),
            "stream_id": stream_id,
            "step_id": step_id,
            "entity_id": entity_id,
            "task_type": "missing_why",
            "priority": "hoch",
            "title": f"Begründung erfassen (WHY): Schritt '{step_id}' ({entity_id})",
            "description": "Keine Begründung (WHY) vorhanden.",
            "rationale": "Ohne Begründung ist keine fundierte Harmonisierungsentscheidung möglich.",
            "based_on": f"variant:{step_id}:{entity_id}:why_is_it_done_this_way",
            "status": "offen",
            "suggested_owner_role": "Process Owner",
            "blocking_flag": True,
        })
    elif why_q["quality"] == "weak":
        tasks.append({
            "id": _next_task_id(),
            "stream_id": stream_id,
            "step_id": step_id,
            "entity_id": entity_id,
            "task_type": "weak_why",
            "priority": "mittel",
            "title": f"Begründung stärken: Schritt '{step_id}' ({entity_id})",
            "description": "WHY-Begründung vorhanden, aber schwach (nur 'historisch gewachsen' oder 'unklar').",
            "rationale": "Schwache Begründung reicht für fundierte Standardisierungsentscheidung nicht aus.",
            "based_on": f"variant:{step_id}:{entity_id}:why_quality",
            "status": "offen",
            "suggested_owner_role": "Process Owner",
            "blocking_flag": False,
        })

    # missing_evidence (priority: mittel)
    ev = assess_evidence_strength(variant)
    if ev["count"] == 0:
        tasks.append({
            "id": _next_task_id(),
            "stream_id": stream_id,
            "step_id": step_id,
            "entity_id": entity_id,
            "task_type": "missing_evidence",
            "priority": "mittel",
            "title": f"Evidenz hinzufügen: Schritt '{step_id}' ({entity_id})",
            "description": "Keine Evidenznachweise vorhanden.",
            "rationale": "Evidenz ist für reviewfähige Dokumentation erforderlich.",
            "based_on": f"variant:{step_id}:{entity_id}:evidence_references",
            "status": "offen",
            "suggested_owner_role": "Process Owner",
            "blocking_flag": False,
        })

    # missing_output (priority: niedrig)
    if not (variant.get("output") or "").strip():
        tasks.append({
            "id": _next_task_id(),
            "stream_id": stream_id,
            "step_id": step_id,
            "entity_id": entity_id,
            "task_type": "missing_output",
            "priority": "niedrig",
            "title": f"Output definieren: Schritt '{step_id}' ({entity_id})",
            "description": "Kein Output definiert.",
            "rationale": "Output-Definition ist für vollständige Prozessdokumentation erforderlich.",
            "based_on": f"variant:{step_id}:{entity_id}:output",
            "status": "offen",
            "suggested_owner_role": "Process Owner",
            "blocking_flag": False,
        })

    # review_blocker (priority: mittel, only if review_status in draft/captured)
    rs = variant.get("review_status", "draft")
    if rs in ("draft", "captured"):
        vr_check = validate_review_status(variant, "approved")
        if not vr_check["valid"]:
            tasks.append({
                "id": _next_task_id(),
                "stream_id": stream_id,
                "step_id": step_id,
                "entity_id": entity_id,
                "task_type": "review_blocker",
                "priority": "niedrig",
                "title": f"Review vorbereiten: Schritt '{step_id}' ({entity_id})",
                "description": f"Review-Status: {rs}. Blocker: {vr_check.get('reason', '')}",
                "rationale": "Review-Freigabe ist für abgeschlossene Analyse erforderlich.",
                "based_on": f"variant:{step_id}:{entity_id}:review_status",
                "status": "offen",
                "suggested_owner_role": "Reviewer",
                "blocking_flag": False,
            })

    return tasks

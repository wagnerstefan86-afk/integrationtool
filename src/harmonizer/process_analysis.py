"""Structured process analysis model and logic.

Provides the step-anchored process analysis layer:
- Fixed process phases (intake, triage, processing, escalation, closure, reporting)
- Per-entity variants under each step (DE, AT, or any future entity)
- Guided interview questions per phase
- Completeness and quality scoring
- Step-level delta computation between entities
"""

from __future__ import annotations

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

# ─── Completeness & quality scoring ──────────────────────────────────────────

def score_variant_completeness(variant: dict) -> dict:
    """Score completeness of a single entity variant (0-100).

    Returns dict with score, missing fields, and warnings.
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

    # Warnings
    channels = variant.get("input_channels", [])
    if len(channels) > 2 and not variant.get("why_is_it_done_this_way"):
        warnings.append("Multiple input channels without WHY explanation")
    if not variant.get("why_is_it_done_this_way"):
        warnings.append("Missing WHY — cannot assess standardization rationale")
    if not variant.get("output"):
        warnings.append("No output defined")
    if variant.get("performed_in") in (None, "", "unknown"):
        warnings.append("Entity assignment unclear")

    # Score: 70% from required fields, 30% from bonus
    req_score = ((len(required) - len(missing)) / len(required)) * 70
    bonus_score = (filled_bonus / max(len(bonus_fields), 1)) * 30
    total = round(req_score + bonus_score)

    return {
        "score": min(total, 100),
        "missing_fields": missing,
        "warnings": warnings,
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
        })

    return deltas


def compute_analysis_deltas(analysis: dict) -> list[dict]:
    """Compute all deltas across all process steps in an analysis."""
    all_deltas = []
    for step in analysis.get("process_steps", []):
        all_deltas.extend(compute_step_delta(step))
    return all_deltas


def compute_analysis_summary(analysis: dict) -> dict:
    """Compute management-level summary of a process analysis."""
    completeness = score_analysis_completeness(analysis)
    deltas = compute_analysis_deltas(analysis)

    high_deltas = sum(1 for d in deltas if d["impact"] == "high")
    medium_deltas = sum(1 for d in deltas if d["impact"] == "medium")

    steps = analysis.get("process_steps", [])
    entities = set()
    for step in steps:
        for v in step.get("entity_variants", []):
            entities.add(v.get("entity_id", ""))

    # Steps with strong differences
    steps_with_high = set()
    for d in deltas:
        if d["impact"] == "high":
            steps_with_high.add(d["step_id"])

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
        "evidence_or_examples": [],
        "performed_in": entity_id,
        "maturity_notes": "",
    }

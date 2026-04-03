"""FastAPI backend for the harmonization analysis tool.

Provides:
- Full CRUD for areas, streams, subprocesses, interfaces, assessments, outcomes
- Analysis pipeline execution
- Calibration
- Dashboard statistics
- Live scoring for assessments
- Report management
"""

import logging
import os
import subprocess as sp_mod
from datetime import datetime
from pathlib import Path
from typing import Any, Optional

from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import PlainTextResponse
from pydantic import BaseModel

from harmonizer.pipeline import run_analysis, run_analysis_and_report, run_calibration, run_single_stream_decision
from harmonizer.store import YAMLStore
from harmonizer.scoring.engine import (
    compute_weighted_score,
    compute_type_specific_score,
    compute_blended_score,
    classify_score,
    apply_hard_constraints,
    get_weights_for_stream_type,
)
from harmonizer.scoring.questions import get_required_questions
from harmonizer.models.process import StreamType, TargetOption, GapLevel, is_as_is_complete, get_as_is_errors
from harmonizer.models.assessment import (
    AlignmentDimension,
    AssessmentAnswer,
    HardConstraint,
    TypeSpecificAnswer,
)

# --- Configuration ---

DATA_PATH = Path(os.environ.get("DATA_PATH", "/data"))
REPORT_PATH = Path(os.environ.get("REPORT_PATH", "/reports"))
LOG_PATH = Path(os.environ.get("LOG_PATH", "/logs"))
APP_VERSION = os.environ.get("APP_VERSION", "0.9.0")
GIT_COMMIT = os.environ.get("GIT_COMMIT", "")
BUILD_DATE = os.environ.get("BUILD_DATE", "")

# --- Logging ---

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    handlers=[logging.StreamHandler()],
)
logger = logging.getLogger("harmonizer.api")
if LOG_PATH.exists():
    fh = logging.FileHandler(LOG_PATH / "harmonizer.log")
    fh.setFormatter(logging.Formatter("%(asctime)s [%(levelname)s] %(name)s: %(message)s"))
    logging.getLogger().addHandler(fh)

# --- Ensure dirs ---

def _ensure_dirs() -> None:
    for sub in ["examples", "pilot", "outcomes", "archive"]:
        (DATA_PATH / sub).mkdir(parents=True, exist_ok=True)
    for sub in ["generated", "reviewed"]:
        (REPORT_PATH / sub).mkdir(parents=True, exist_ok=True)
    LOG_PATH.mkdir(parents=True, exist_ok=True)

_ensure_dirs()

# --- Helpers ---

def _get_store(data_dir: str = "examples") -> YAMLStore:
    path = DATA_PATH / data_dir
    if not path.exists():
        raise HTTPException(404, f"Data directory not found: {data_dir}")
    return YAMLStore(path)

def _get_git_commit() -> str:
    try:
        r = sp_mod.run(["git", "rev-parse", "--short", "HEAD"],
                       capture_output=True, text=True, timeout=5)
        if r.returncode == 0:
            return r.stdout.strip()
    except (FileNotFoundError, sp_mod.TimeoutExpired):
        pass
    return ""

# --- App ---

app = FastAPI(title="Harmonizer API", version=APP_VERSION)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

# ===================== Health =====================

@app.get("/health")
def health():
    commit = GIT_COMMIT or _get_git_commit()
    return {
        "status": "ok",
        "version": APP_VERSION,
        "git_commit": commit,
        "build_date": BUILD_DATE,
        "app_env": os.environ.get("APP_ENV", ""),
        "data_path": str(DATA_PATH),
        "report_path": str(REPORT_PATH),
    }

# ===================== Dashboard =====================

@app.get("/api/dashboard")
def dashboard(dataset: str = "examples"):
    store = _get_store(dataset)
    stats = store.get_dashboard_stats()
    stats["dataset"] = dataset
    stats["available_datasets"] = [
        d.name for d in DATA_PATH.iterdir() if d.is_dir()
    ]
    return stats

# ===================== Director Overview =====================

@app.get("/api/director/overview")
def director_overview(dataset: str = "examples"):
    """Aggregated management view across all streams.

    Computes per-stream status for: AS-IS, delta, option assessments,
    recommendation, review, and flags streams needing management action.
    """
    from harmonizer.scoring.delta import compute_delta
    from harmonizer.scoring.option_decision import compare_options

    store = _get_store(dataset)
    streams = store.list_streams()
    assessments = store.list_assessments()
    reviews = store.list_reviews()

    review_map = {r["stream_id"]: r for r in reviews}

    # Pre-index assessments by stream
    stream_assessments: dict[str, list[dict]] = {}
    for a in assessments:
        if a.get("assessed_object_type") == "stream":
            stream_assessments.setdefault(a["assessed_object_id"], []).append(a)

    stream_rows = []
    rec_dist = {"de_standard": 0, "at_standard": 0, "central": 0, "none": 0}
    summary = {
        "total_streams": len(streams),
        "as_is_complete": 0,
        "delta_ready": 0,
        "options_complete": 0,
        "recommendations_ready": 0,
        "reviewed": 0,
        "blocked": 0,
    }

    for s in streams:
        sid = s["id"]
        as_is = s.get("as_is", {})
        de = as_is.get("de", {})
        at = as_is.get("at", {})
        de_ok = is_as_is_complete(de)
        at_ok = is_as_is_complete(at)
        asis_complete = de_ok and at_ok

        # Delta
        has_de = bool(de.get("description", "").strip())
        has_at = bool(at.get("description", "").strip())
        delta_result = None
        delta_summary = {"high": 0, "medium": 0, "low": 0}
        if has_de and has_at:
            delta_result = compute_delta(de, at)
            ds = delta_result.get("summary", {})
            delta_summary = {
                "high": ds.get("high_impact", 0),
                "medium": ds.get("medium_impact", 0),
                "low": ds.get("low_impact", 0),
            }
        delta_ready = delta_result is not None

        # Option assessments
        opt_assessments = stream_assessments.get(sid, [])
        option_set = {a.get("target_option") for a in opt_assessments if a.get("target_option")}
        options_complete = {"de_standard", "at_standard", "central"} <= option_set

        # Recommendation
        recommended_option = None
        has_recommendation = False
        if opt_assessments:
            try:
                cmp = compare_options(s, opt_assessments)
                recommended_option = cmp.get("recommended_option")
                has_recommendation = recommended_option is not None
            except Exception:
                pass

        # Review
        review = review_map.get(sid)
        review_status = review.get("review_status", "not_started") if review else "not_started"
        reviewed_decision = review.get("reviewed_decision") if review else None
        override_applied = review.get("override_applied", False) if review else False

        # Hard constraints
        hc_active = any(
            bool(a.get("hard_constraints"))
            for a in opt_assessments
        )

        # Action reasons
        action_reasons = []
        if not asis_complete:
            action_reasons.append("AS-IS incomplete")
        if not delta_ready and (has_de or has_at):
            action_reasons.append("Delta not computable (asymmetric AS-IS)")
        if not delta_ready and not has_de and not has_at:
            action_reasons.append("No AS-IS documentation")
        if len(option_set) < 3 and len(option_set) > 0:
            action_reasons.append(f"Only {len(option_set)}/3 option assessments")
        if len(option_set) == 0:
            action_reasons.append("No option assessments")
        if not has_recommendation and len(option_set) > 0:
            action_reasons.append("No recommendation possible")
        if delta_summary["high"] >= 3:
            action_reasons.append(f"{delta_summary['high']} high-impact differences")
        if hc_active:
            action_reasons.append("Hard constraints active")
        if override_applied and reviewed_decision and reviewed_decision != recommended_option:
            action_reasons.append("Reviewed decision differs from recommendation")
        if options_complete and review_status == "not_started":
            action_reasons.append("Assessments complete but no review started")

        needs_action = len(action_reasons) > 0

        # Update summary
        if asis_complete:
            summary["as_is_complete"] += 1
        if delta_ready:
            summary["delta_ready"] += 1
        if options_complete:
            summary["options_complete"] += 1
        if has_recommendation:
            summary["recommendations_ready"] += 1
        if review_status == "reviewed":
            summary["reviewed"] += 1
        if needs_action:
            summary["blocked"] += 1

        # Recommendation distribution — use reviewed decision if available, else computed
        effective = reviewed_decision if reviewed_decision else recommended_option
        rec_dist[effective if effective in rec_dist else "none"] += 1

        stream_rows.append({
            "stream_id": sid,
            "stream_name": s.get("name", sid),
            "area_id": s.get("area_id", ""),
            "stream_type": s.get("stream_type", ""),
            "as_is_complete": asis_complete,
            "delta_summary": delta_summary,
            "option_count": len(option_set),
            "recommended_option": recommended_option,
            "reviewed_decision": reviewed_decision,
            "review_status": review_status,
            "high_impact_differences": delta_summary["high"],
            "hard_constraints_active": hc_active,
            "needs_action": needs_action,
            "action_reasons": action_reasons,
        })

    return {
        "summary": summary,
        "recommendation_distribution": rec_dist,
        "streams": stream_rows,
    }

# ===================== Process Analysis =====================

@app.get("/api/process-analysis")
def list_analyses(dataset: str = "examples"):
    return _get_store(dataset).list_analyses()


@app.get("/api/process-analysis/{stream_id}")
def get_analysis(stream_id: str, dataset: str = "examples"):
    a = _get_store(dataset).get_analysis(stream_id)
    if not a:
        raise HTTPException(404, f"Process analysis not found for stream: {stream_id}")
    return a


@app.post("/api/process-analysis/{stream_id}/scaffold")
def scaffold_stream_analysis(stream_id: str, dataset: str = "examples"):
    """Create a new process analysis with default phases for a stream."""
    from harmonizer.process_analysis import scaffold_analysis
    store = _get_store(dataset)
    stream = store.get_stream(stream_id)
    if not stream:
        raise HTTPException(404, f"Stream not found: {stream_id}")
    existing = store.get_analysis(stream_id)
    if existing:
        raise HTTPException(400, f"Analysis already exists for stream '{stream_id}'. Use PUT to update.")
    entities = ["DE", "AT"]
    analysis = scaffold_analysis(stream_id, stream.get("name", stream_id), entities)
    return store.save_analysis(analysis)


@app.put("/api/process-analysis/{stream_id}")
def save_analysis(stream_id: str, body: dict, dataset: str = "examples"):
    """Save or update a process analysis."""
    store = _get_store(dataset)
    if not store.get_stream(stream_id):
        raise HTTPException(404, f"Stream not found: {stream_id}")
    body["stream_id"] = stream_id
    return store.save_analysis(body)


@app.put("/api/process-analysis/{stream_id}/steps/{step_id}/variants/{entity_id}")
def save_variant(stream_id: str, step_id: str, entity_id: str, body: dict, dataset: str = "examples"):
    """Save a single entity variant within a process step."""
    store = _get_store(dataset)
    analysis = store.get_analysis(stream_id)
    if not analysis:
        raise HTTPException(404, f"Process analysis not found for stream: {stream_id}")

    step = None
    for s in analysis.get("process_steps", []):
        if s.get("step_id") == step_id:
            step = s
            break
    if not step:
        raise HTTPException(404, f"Step not found: {step_id}")

    body["entity_id"] = entity_id
    variants = step.setdefault("entity_variants", [])
    for i, v in enumerate(variants):
        if v.get("entity_id") == entity_id:
            variants[i] = body
            store.save_analysis(analysis)
            return body
    variants.append(body)
    store.save_analysis(analysis)
    return body


@app.get("/api/process-analysis/{stream_id}/completeness")
def get_analysis_completeness(stream_id: str, dataset: str = "examples"):
    """Return completeness and quality scores for a process analysis."""
    from harmonizer.process_analysis import score_analysis_completeness
    store = _get_store(dataset)
    analysis = store.get_analysis(stream_id)
    if not analysis:
        raise HTTPException(404, f"Process analysis not found for stream: {stream_id}")
    return score_analysis_completeness(analysis)


@app.get("/api/process-analysis/{stream_id}/deltas")
def get_analysis_deltas(stream_id: str, dataset: str = "examples"):
    """Compute and return all step-level deltas for a process analysis."""
    from harmonizer.process_analysis import compute_analysis_deltas
    store = _get_store(dataset)
    analysis = store.get_analysis(stream_id)
    if not analysis:
        raise HTTPException(404, f"Process analysis not found for stream: {stream_id}")
    return compute_analysis_deltas(analysis)


@app.get("/api/process-analysis/{stream_id}/summary")
def get_analysis_summary(stream_id: str, dataset: str = "examples"):
    """Return management-level summary of a process analysis."""
    from harmonizer.process_analysis import compute_analysis_summary
    store = _get_store(dataset)
    analysis = store.get_analysis(stream_id)
    if not analysis:
        raise HTTPException(404, f"Process analysis not found for stream: {stream_id}")
    return compute_analysis_summary(analysis)


@app.delete("/api/process-analysis/{stream_id}")
def delete_analysis(stream_id: str, dataset: str = "examples"):
    if not _get_store(dataset).delete_analysis(stream_id):
        raise HTTPException(404, f"Process analysis not found for stream: {stream_id}")
    return {"deleted": stream_id}


@app.get("/api/process-analysis/{stream_id}/tasks")
def get_analysis_tasks(stream_id: str, dataset: str = "examples"):
    """Return computed GuidanceTask list for a process analysis.

    Response: list of task objects, each with:
      id, stream_id, step_id, entity_id, task_type, priority,
      title, description, rationale, based_on, status,
      suggested_owner_role, blocking_flag
    """
    from harmonizer.process_analysis import generate_tasks
    store = _get_store(dataset)
    analysis = store.get_analysis(stream_id)
    if not analysis:
        raise HTTPException(404, f"Process analysis not found for stream: {stream_id}")
    return generate_tasks(analysis)


@app.get("/api/process-analysis/{stream_id}/progress")
def get_analysis_progress(stream_id: str, dataset: str = "examples"):
    """Return per-variant maturity levels and overall progress for a process analysis.

    Response: {
      steps: [{step_id, step_name, variants: [{entity_id, maturity: {level, label, next_step, index}}]}],
      maturity_distribution: {level: count},
      overall_completeness: int
    }
    """
    from harmonizer.process_analysis import assess_variant_maturity, score_analysis_completeness, MATURITY_LEVELS
    store = _get_store(dataset)
    analysis = store.get_analysis(stream_id)
    if not analysis:
        raise HTTPException(404, f"Process analysis not found for stream: {stream_id}")

    steps_out = []
    maturity_distribution = {lvl: 0 for lvl in MATURITY_LEVELS}
    for step in analysis.get("process_steps", []):
        variants_out = []
        for v in step.get("entity_variants", []):
            m = assess_variant_maturity(v)
            maturity_distribution[m["level"]] = maturity_distribution.get(m["level"], 0) + 1
            variants_out.append({"entity_id": v.get("entity_id", ""), "maturity": m})
        steps_out.append({
            "step_id": step.get("step_id", ""),
            "step_name": step.get("step_name", step.get("step_id", "")),
            "variants": variants_out,
        })

    completeness = score_analysis_completeness(analysis)
    return {
        "steps": steps_out,
        "maturity_distribution": maturity_distribution,
        "overall_completeness": completeness["score"],
    }


@app.get("/api/process-analysis/{stream_id}/recommendations")
def get_analysis_recommendations(stream_id: str, dataset: str = "examples"):
    """Return rule-based recommendations for a process analysis.

    Response: list of recommendation objects, each with:
      id, title, recommendation_type, rationale, based_on_step_ids[],
      based_on_delta_ids[], priority, assumptions[], blockers[],
      expected_benefit, implementation_complexity
    """
    from harmonizer.process_analysis import generate_recommendations
    store = _get_store(dataset)
    analysis = store.get_analysis(stream_id)
    if not analysis:
        raise HTTPException(404, f"Process analysis not found for stream: {stream_id}")
    return generate_recommendations(analysis)


class ReviewStatusRequest(BaseModel):
    step_id: str
    entity_id: str
    new_status: str
    review_comment: str = ""
    reviewed_by: str = ""


@app.post("/api/process-analysis/{stream_id}/validate-review-status")
def validate_review_status_endpoint(stream_id: str, body: ReviewStatusRequest, dataset: str = "examples"):
    """Validate whether a review status transition is allowed for a variant.

    Input: { step_id, entity_id, new_status }
    Response: { allowed, reasons[], missing_prerequisites[], current_status }
    """
    from harmonizer.process_analysis import validate_review_status
    store = _get_store(dataset)
    analysis = store.get_analysis(stream_id)
    if not analysis:
        raise HTTPException(404, f"Process analysis not found for stream: {stream_id}")

    variant = _find_variant(analysis, body.step_id, body.entity_id)
    if variant is None:
        raise HTTPException(404, f"Variant not found: step={body.step_id}, entity={body.entity_id}")

    result = validate_review_status(variant, body.new_status)
    reasons = [result["reason"]] if result["reason"] else []
    missing = []
    if not result["valid"] and "missing" in result.get("reason", "").lower():
        reason_text = result.get("reason", "")
        if "missing" in reason_text.lower():
            after_missing = reason_text.split("missing ", 1)[-1] if "missing " in reason_text else ""
            missing = [f.strip() for f in after_missing.split(",") if f.strip()]

    return {
        "allowed": result["valid"],
        "reasons": reasons,
        "missing_prerequisites": missing,
        "current_status": result["current_status"],
    }


@app.post("/api/process-analysis/{stream_id}/apply-review-status")
def apply_review_status_endpoint(stream_id: str, body: ReviewStatusRequest, dataset: str = "examples"):
    """Validate and persist a review status transition for a variant.

    Input: { step_id, entity_id, new_status, review_comment?, reviewed_by? }
    Response: { applied, new_status, review_comment, reviewed_by, reviewed_at, reasons[] }

    Returns 400 if transition is blocked (with reasons).
    """
    from harmonizer.process_analysis import validate_review_status
    store = _get_store(dataset)
    analysis = store.get_analysis(stream_id)
    if not analysis:
        raise HTTPException(404, f"Process analysis not found for stream: {stream_id}")

    # Find variant (mutable reference within analysis dict)
    variant = _find_variant(analysis, body.step_id, body.entity_id)
    if variant is None:
        raise HTTPException(404, f"Variant not found: step={body.step_id}, entity={body.entity_id}")

    result = validate_review_status(variant, body.new_status)
    if not result["valid"]:
        raise HTTPException(400, result["reason"])

    # Apply transition
    now = datetime.utcnow().strftime("%Y-%m-%d %H:%M")
    variant["review_status"] = body.new_status
    variant["review_comment"] = body.review_comment or variant.get("review_comment", "")
    variant["reviewed_by"] = body.reviewed_by or variant.get("reviewed_by", "")
    variant["reviewed_at"] = now

    store.save_analysis(analysis)

    return {
        "applied": True,
        "new_status": body.new_status,
        "review_comment": variant["review_comment"],
        "reviewed_by": variant["reviewed_by"],
        "reviewed_at": now,
    }


def _find_variant(analysis: dict, step_id: str, entity_id: str):
    """Find a variant dict within an analysis (returns mutable reference)."""
    for step in analysis.get("process_steps", []):
        if step.get("step_id") == step_id:
            for v in step.get("entity_variants", []):
                if v.get("entity_id") == entity_id:
                    return v
            break
    return None


@app.get("/api/process-analysis-guide/{step_id}")
def get_guide_questions(step_id: str):
    """Return guided interview questions for a process phase."""
    from harmonizer.process_analysis import GUIDE_QUESTIONS
    questions = GUIDE_QUESTIONS.get(step_id)
    if questions is None:
        raise HTTPException(404, f"No guide questions for step: {step_id}")
    return questions


# ===================== Areas CRUD =====================

@app.get("/api/areas")
def list_areas(dataset: str = "examples"):
    return _get_store(dataset).list_areas()

@app.get("/api/areas/{area_id}")
def get_area(area_id: str, dataset: str = "examples"):
    a = _get_store(dataset).get_area(area_id)
    if not a:
        raise HTTPException(404, f"Area not found: {area_id}")
    return a

@app.put("/api/areas")
def save_area(area: dict, dataset: str = "examples"):
    if "id" not in area or "name" not in area:
        raise HTTPException(400, "Area requires 'id' and 'name'")
    area_id = area["id"].strip()
    if not area_id:
        raise HTTPException(400, "Area ID must not be empty")
    area["id"] = area_id
    return _get_store(dataset).save_area(area)

@app.delete("/api/areas/{area_id}")
def delete_area(area_id: str, dataset: str = "examples"):
    store = _get_store(dataset)
    # Prevent deleting areas with dependent streams
    dependent = [s["id"] for s in store.list_streams() if s.get("area_id") == area_id]
    if dependent:
        raise HTTPException(
            409,
            f"Cannot delete area '{area_id}': {len(dependent)} stream(s) still reference it: "
            + ", ".join(dependent[:5]),
        )
    if not store.delete_area(area_id):
        raise HTTPException(404, f"Area not found: {area_id}")
    return {"deleted": area_id}

# ===================== Streams CRUD =====================

@app.get("/api/streams")
def list_streams(dataset: str = "examples"):
    return _get_store(dataset).list_streams()

@app.get("/api/streams/{stream_id}")
def get_stream(stream_id: str, dataset: str = "examples"):
    s = _get_store(dataset).get_stream(stream_id)
    if not s:
        raise HTTPException(404, f"Stream not found: {stream_id}")
    return s

@app.put("/api/streams")
def save_stream(stream: dict, dataset: str = "examples"):
    if "id" not in stream or "name" not in stream:
        raise HTTPException(400, "Stream requires 'id' and 'name'")
    stream_id = stream["id"].strip()
    if not stream_id:
        raise HTTPException(400, "Stream ID must not be empty")
    stream["id"] = stream_id
    # Validate area_id reference
    store = _get_store(dataset)
    area_id = stream.get("area_id", "").strip()
    if area_id and not store.get_area(area_id):
        raise HTTPException(400, f"Referenced area not found: '{area_id}'")
    return store.save_stream(stream)

@app.delete("/api/streams/{stream_id}")
def delete_stream(stream_id: str, dataset: str = "examples"):
    store = _get_store(dataset)
    dependent = [sp["id"] for sp in store.list_subprocesses() if sp.get("stream_id") == stream_id]
    if dependent:
        raise HTTPException(
            409,
            f"Cannot delete stream '{stream_id}': {len(dependent)} subprocess(es) still reference it: "
            + ", ".join(dependent[:5]),
        )
    if not store.delete_stream(stream_id):
        raise HTTPException(404, f"Stream not found: {stream_id}")
    return {"deleted": stream_id}

# ===================== Subprocesses CRUD =====================

@app.get("/api/subprocesses")
def list_subprocesses(dataset: str = "examples"):
    return _get_store(dataset).list_subprocesses()

@app.get("/api/subprocesses/{sp_id}")
def get_subprocess(sp_id: str, dataset: str = "examples"):
    sp = _get_store(dataset).get_subprocess(sp_id)
    if not sp:
        raise HTTPException(404, f"Subprocess not found: {sp_id}")
    return sp

@app.put("/api/subprocesses")
def save_subprocess(sp: dict, dataset: str = "examples"):
    if "id" not in sp or "name" not in sp:
        raise HTTPException(400, "Subprocess requires 'id' and 'name'")
    sp_id = sp["id"].strip()
    if not sp_id:
        raise HTTPException(400, "Subprocess ID must not be empty")
    sp["id"] = sp_id
    # Validate stream_id reference
    store = _get_store(dataset)
    stream_id = sp.get("stream_id", "").strip()
    if stream_id and not store.get_stream(stream_id):
        raise HTTPException(400, f"Referenced stream not found: '{stream_id}'")
    return store.save_subprocess(sp)

@app.delete("/api/subprocesses/{sp_id}")
def delete_subprocess(sp_id: str, dataset: str = "examples"):
    store = _get_store(dataset)
    # Check if any interface references this subprocess
    dependent = [
        i["id"] for i in store.list_interfaces()
        if i.get("source_process_id") == sp_id or i.get("target_process_id") == sp_id
    ]
    if dependent:
        raise HTTPException(
            409,
            f"Cannot delete subprocess '{sp_id}': {len(dependent)} interface(s) reference it: "
            + ", ".join(dependent[:5]),
        )
    if not store.delete_subprocess(sp_id):
        raise HTTPException(404, f"Subprocess not found: {sp_id}")
    return {"deleted": sp_id}

# ===================== Interfaces CRUD =====================

@app.get("/api/interfaces")
def list_interfaces(dataset: str = "examples"):
    return _get_store(dataset).list_interfaces()

@app.get("/api/interfaces/{iface_id}")
def get_interface(iface_id: str, dataset: str = "examples"):
    i = _get_store(dataset).get_interface(iface_id)
    if not i:
        raise HTTPException(404, f"Interface not found: {iface_id}")
    return i

@app.put("/api/interfaces")
def save_interface(iface: dict, dataset: str = "examples"):
    if "id" not in iface:
        raise HTTPException(400, "Interface requires 'id'")
    iface_id = iface["id"].strip()
    if not iface_id:
        raise HTTPException(400, "Interface ID must not be empty")
    iface["id"] = iface_id
    # Validate source/target references exist (subprocess or stream)
    store = _get_store(dataset)
    all_sp_ids = {sp["id"] for sp in store.list_subprocesses()}
    all_stream_ids = {s["id"] for s in store.list_streams()}
    valid_ids = all_sp_ids | all_stream_ids
    src = iface.get("source_process_id", "").strip()
    tgt = iface.get("target_process_id", "").strip()
    if src and src not in valid_ids:
        raise HTTPException(400, f"Source process not found: '{src}'")
    if tgt and tgt not in valid_ids:
        raise HTTPException(400, f"Target process not found: '{tgt}'")
    return store.save_interface(iface)

@app.delete("/api/interfaces/{iface_id}")
def delete_interface(iface_id: str, dataset: str = "examples"):
    if not _get_store(dataset).delete_interface(iface_id):
        raise HTTPException(404, f"Interface not found: {iface_id}")
    return {"deleted": iface_id}

# ===================== Assessments CRUD =====================

VALID_TARGET_OPTIONS = {t.value for t in TargetOption}

@app.get("/api/assessments")
def list_assessments(dataset: str = "examples", target_option: Optional[str] = None):
    assessments = _get_store(dataset).list_assessments()
    if target_option:
        assessments = [a for a in assessments if a.get("target_option") == target_option]
    return assessments

@app.get("/api/assessments/{obj_id}")
def get_assessment(obj_id: str, dataset: str = "examples", target_option: Optional[str] = None):
    a = _get_store(dataset).get_assessment(obj_id, target_option=target_option)
    if not a:
        label = f"{obj_id}" + (f" (option={target_option})" if target_option else "")
        raise HTTPException(404, f"Assessment not found: {label}")
    return a

VALID_DIMENSIONS = {d.value for d in AlignmentDimension}
VALID_HARD_CONSTRAINTS = {c.value for c in HardConstraint}
VALID_STATUSES = {"not_started", "draft", "completed", "reviewed"}

@app.put("/api/assessments")
def save_assessment(assessment: dict, dataset: str = "examples"):
    obj_id = assessment.get("assessed_object_id", "").strip()
    if not obj_id:
        raise HTTPException(400, "Assessment requires 'assessed_object_id'")
    assessment["assessed_object_id"] = obj_id

    obj_type = assessment.get("assessed_object_type", "").strip()
    if obj_type not in ("stream", "subprocess"):
        raise HTTPException(400, "assessed_object_type must be 'stream' or 'subprocess'")

    # Validate target_option for stream assessments
    target_option = assessment.get("target_option")
    if target_option:
        if target_option not in VALID_TARGET_OPTIONS:
            raise HTTPException(400, f"Invalid target_option: '{target_option}'. Must be one of: {', '.join(sorted(VALID_TARGET_OPTIONS))}")
        if obj_type != "stream":
            raise HTTPException(400, "target_option is only valid for stream assessments")

    # Validate the referenced object exists
    store = _get_store(dataset)
    if obj_type == "stream" and not store.get_stream(obj_id):
        raise HTTPException(400, f"Stream not found: '{obj_id}'")
    if obj_type == "subprocess" and not store.get_subprocess(obj_id):
        raise HTTPException(400, f"Subprocess not found: '{obj_id}'")

    # Validate dimension scores
    for ans in assessment.get("answers", []):
        dim = ans.get("dimension", "")
        if dim and dim not in VALID_DIMENSIONS:
            raise HTTPException(400, f"Invalid dimension: '{dim}'")
        score = ans.get("score")
        if score is not None and (not isinstance(score, int) or score < 1 or score > 5):
            raise HTTPException(400, f"Dimension score must be integer 1-5, got: {score}")

    # Validate hard constraints
    for hc in assessment.get("hard_constraints", []):
        if hc not in VALID_HARD_CONSTRAINTS:
            raise HTTPException(400, f"Invalid hard constraint: '{hc}'")

    # Validate status
    status = assessment.get("status", "draft")
    if status not in VALID_STATUSES:
        raise HTTPException(400, f"Invalid status: '{status}'. Must be one of: {', '.join(sorted(VALID_STATUSES))}")

    # Status 'completed' requires all 6 base dimensions
    if status == "completed":
        answered = {a.get("dimension") for a in assessment.get("answers", [])}
        missing = VALID_DIMENSIONS - answered
        if missing:
            raise HTTPException(
                400,
                f"Cannot set status to 'completed': missing dimensions: {', '.join(sorted(missing))}"
            )

    # Hard gate: stream assessments with target_option require complete AS-IS DE+AT
    if obj_type == "stream" and target_option:
        stream = store.get_stream(obj_id)
        as_is = stream.get("as_is", {}) if stream else {}
        de_ok = is_as_is_complete(as_is.get("de", {}))
        at_ok = is_as_is_complete(as_is.get("at", {}))
        if not (de_ok and at_ok):
            missing = []
            if not de_ok:
                missing.append(f"DE: {', '.join(get_as_is_errors(as_is.get('de', {})))}")
            if not at_ok:
                missing.append(f"AT: {', '.join(get_as_is_errors(as_is.get('at', {})))}")
            raise HTTPException(
                400,
                "AS-IS documentation incomplete for DE/AT. "
                f"Complete the AS-IS before creating option assessments. {'; '.join(missing)}"
            )

    assessment["status"] = status
    return store.save_assessment(assessment)

@app.delete("/api/assessments/{obj_id}")
def delete_assessment(obj_id: str, dataset: str = "examples", target_option: Optional[str] = None):
    if not _get_store(dataset).delete_assessment(obj_id, target_option=target_option):
        raise HTTPException(404, f"Assessment not found: {obj_id}")
    return {"deleted": obj_id, "target_option": target_option}

# ===================== Outcomes CRUD =====================

@app.get("/api/outcomes")
def list_outcomes(dataset: str = "examples"):
    return _get_store(dataset).list_outcomes()

@app.get("/api/outcomes/{obj_id}")
def get_outcome(obj_id: str, dataset: str = "examples"):
    o = _get_store(dataset).get_outcome(obj_id)
    if not o:
        raise HTTPException(404, f"Outcome not found: {obj_id}")
    return o

@app.put("/api/outcomes")
def save_outcome(outcome: dict, dataset: str = "examples"):
    if "assessed_object_id" not in outcome:
        raise HTTPException(400, "Outcome requires 'assessed_object_id'")
    return _get_store(dataset).save_outcome(outcome)

# ===================== Live Scoring =====================

class LiveScoreRequest(BaseModel):
    answers: list[dict]  # [{dimension, score}]
    type_specific_answers: list[dict] = []  # [{question_id, score}]
    hard_constraints: list[str] = []
    stream_type: Optional[str] = None

@app.post("/api/score")
def live_score(req: LiveScoreRequest):
    """Compute harmonization score live from assessment answers."""
    st = None
    if req.stream_type:
        try:
            st = StreamType(req.stream_type)
        except ValueError:
            pass
    weights = get_weights_for_stream_type(st)

    parsed = []
    for a in req.answers:
        try:
            parsed.append(AssessmentAnswer(
                dimension=AlignmentDimension(a["dimension"]),
                score=int(a["score"]),
                rationale=a.get("rationale", ""),
            ))
        except (KeyError, ValueError):
            continue

    ts_parsed = []
    for ts in req.type_specific_answers:
        try:
            ts_parsed.append(TypeSpecificAnswer(
                question_id=ts["question_id"],
                score=int(ts["score"]),
                rationale=ts.get("rationale", ""),
            ))
        except (KeyError, ValueError):
            continue

    # Parse hard constraints
    hc_parsed = []
    for hc in req.hard_constraints:
        try:
            hc_parsed.append(HardConstraint(hc))
        except ValueError:
            continue

    base = compute_weighted_score(parsed, weights)
    ts_score = compute_type_specific_score(ts_parsed)
    blended = compute_blended_score(base, ts_score, bool(ts_parsed))
    base_classification = classify_score(blended)

    # Apply hard constraint caps
    final_classification, constraint_reasons = apply_hard_constraints(
        base_classification, hc_parsed
    )

    dims_answered = len({a.dimension for a in parsed})
    ts_expected = len(get_required_questions(st)) if st else 0
    # Better completeness estimate
    dim_pct = (dims_answered / 6) * 40
    ts_pct = (len(ts_parsed) / max(ts_expected, 1)) * 25 if ts_expected else 15
    hc_pct = 15 if req.hard_constraints is not None else 0
    base_pct = 20
    completeness_est = int(min(100, dim_pct + ts_pct + hc_pct + base_pct))

    # Confidence
    if completeness_est >= 75:
        confidence = "high"
    elif completeness_est >= 45:
        confidence = "medium"
    else:
        confidence = "low"

    # Missing dimensions
    answered_dims = {a.dimension.value for a in parsed}
    missing_dims = sorted(set(d.value for d in AlignmentDimension) - answered_dims)

    return {
        "base_score": round(base, 4),
        "type_specific_score": round(ts_score, 4),
        "blended_score": round(blended, 4),
        "base_classification": base_classification.value,
        "classification": final_classification.value,
        "constraint_reasons": constraint_reasons,
        "dimensions_answered": dims_answered,
        "missing_dimensions": missing_dims,
        "completeness_estimate": completeness_est,
        "confidence": confidence,
    }

# ===================== Type-Specific Questions =====================

@app.get("/api/questions/{stream_type}")
def get_questions(stream_type: str):
    """Return type-specific questions for a given stream type."""
    try:
        st = StreamType(stream_type)
    except ValueError:
        raise HTTPException(400, f"Invalid stream type: '{stream_type}'")
    questions = get_required_questions(st)
    return [{"id": q.id, "text": q.text, "focus": q.focus} for q in questions]

# ===================== Stream AS-IS & Delta =====================

VALID_GAP_LEVELS = {g.value for g in GapLevel}

@app.get("/api/streams/{stream_id}/as-is")
def get_stream_as_is(stream_id: str, dataset: str = "examples"):
    """Return AS-IS DE/AT process descriptions and delta for a stream."""
    store = _get_store(dataset)
    stream = store.get_stream(stream_id)
    if not stream:
        raise HTTPException(404, f"Stream not found: {stream_id}")
    return {
        "stream_id": stream_id,
        "as_is": stream.get("as_is", {"de": {}, "at": {}}),
        "delta": stream.get("delta", {}),
    }


@app.put("/api/streams/{stream_id}/as-is")
def save_stream_as_is(stream_id: str, body: dict, dataset: str = "examples"):
    """Save AS-IS DE/AT process descriptions and optional delta."""
    store = _get_store(dataset)
    stream = store.get_stream(stream_id)
    if not stream:
        raise HTTPException(404, f"Stream not found: {stream_id}")

    as_is = body.get("as_is", {})
    for country in ("de", "at"):
        entry = as_is.get(country, {})
        if not isinstance(entry, dict):
            raise HTTPException(400, f"as_is.{country} must be an object")

    # Asymmetry check: if one country has content, the other must too
    de = as_is.get("de", {})
    at = as_is.get("at", {})
    de_has_content = bool(de.get("description", "").strip())
    at_has_content = bool(at.get("description", "").strip())
    if de_has_content != at_has_content:
        filled = "DE" if de_has_content else "AT"
        empty = "AT" if de_has_content else "DE"
        raise HTTPException(400, f"AS-IS {filled} is filled but {empty} is empty. Both countries must be documented together.")

    # Validate delta if provided
    delta = body.get("delta", {})
    for key in ("structural_diff", "tooling_gap", "regulatory_gap", "role_model_diff"):
        v = delta.get(key)
        if v and v not in VALID_GAP_LEVELS:
            raise HTTPException(400, f"Invalid gap level for delta.{key}: '{v}'")

    # Compute completeness status
    de_complete = is_as_is_complete(de)
    at_complete = is_as_is_complete(at)
    de_errors = get_as_is_errors(de) if de_has_content and not de_complete else []
    at_errors = get_as_is_errors(at) if at_has_content and not at_complete else []

    stream["as_is"] = as_is
    if delta:
        stream["delta"] = delta
    store.save_stream(stream)
    return {
        "stream_id": stream_id,
        "as_is": as_is,
        "delta": delta,
        "completeness": {
            "de_complete": de_complete,
            "at_complete": at_complete,
            "de_errors": de_errors,
            "at_errors": at_errors,
        },
    }


@app.get("/api/streams/{stream_id}/as-is/status")
def get_stream_as_is_status(stream_id: str, dataset: str = "examples"):
    """Return AS-IS completeness status for a stream."""
    store = _get_store(dataset)
    stream = store.get_stream(stream_id)
    if not stream:
        raise HTTPException(404, f"Stream not found: {stream_id}")
    as_is = stream.get("as_is", {})
    de = as_is.get("de", {})
    at = as_is.get("at", {})
    return {
        "stream_id": stream_id,
        "de_complete": is_as_is_complete(de),
        "at_complete": is_as_is_complete(at),
        "complete": is_as_is_complete(de) and is_as_is_complete(at),
        "de_errors": get_as_is_errors(de),
        "at_errors": get_as_is_errors(at),
    }


@app.get("/api/streams/{stream_id}/delta")
def get_stream_delta(stream_id: str, dataset: str = "examples"):
    """Compute and return structured delta between DE and AT AS-IS."""
    store = _get_store(dataset)
    stream = store.get_stream(stream_id)
    if not stream:
        raise HTTPException(404, f"Stream not found: {stream_id}")

    as_is = stream.get("as_is", {})
    de = as_is.get("de", {})
    at = as_is.get("at", {})

    if not (de.get("description", "").strip() or at.get("description", "").strip()):
        raise HTTPException(400, "AS-IS not documented for this stream. Fill in DE and AT first.")

    from harmonizer.scoring.delta import compute_delta
    result = compute_delta(de, at)
    result["stream_id"] = stream_id
    return result


# ===================== Option Assessments (stream-level) =====================

@app.get("/api/streams/{stream_id}/option-assessments")
def get_option_assessments(stream_id: str, dataset: str = "examples"):
    """Return all target option assessments for a stream."""
    store = _get_store(dataset)
    if not store.get_stream(stream_id):
        raise HTTPException(404, f"Stream not found: {stream_id}")
    return store.get_assessments_for_stream(stream_id)


# ===================== Option Comparison Decision =====================

@app.post("/api/decisions/compare/{stream_id}")
def compare_stream_options(stream_id: str, dataset: str = "examples"):
    """Compare 3 target options for a stream and recommend the best one.

    Requires at least one option assessment. Ideally all three
    (de_standard, at_standard, central) should exist.
    """
    store = _get_store(dataset)
    stream = store.get_stream(stream_id)
    if not stream:
        raise HTTPException(404, f"Stream not found: {stream_id}")

    # Hard gate: AS-IS must be complete before comparing options
    as_is = stream.get("as_is", {})
    de_ok = is_as_is_complete(as_is.get("de", {}))
    at_ok = is_as_is_complete(as_is.get("at", {}))
    if not (de_ok and at_ok):
        raise HTTPException(
            400,
            "AS-IS documentation incomplete for DE/AT. "
            "Complete the AS-IS before comparing target options."
        )

    option_assessments = store.get_assessments_for_stream(stream_id)
    if not option_assessments:
        raise HTTPException(
            400,
            f"No option assessments found for stream '{stream_id}'. "
            "Create assessments with target_option set."
        )

    from harmonizer.scoring.option_decision import compare_options
    try:
        result = compare_options(stream, option_assessments)
    except Exception as e:
        logger.error("Option comparison failed for %s: %s", stream_id, e, exc_info=True)
        raise HTTPException(500, f"Option comparison failed: {e}")
    return result


# ===================== Decisions (computed) =====================

@app.post("/api/decisions/compute/{stream_id}")
def compute_stream_decision(stream_id: str, dataset: str = "examples"):
    """Run the analysis pipeline for a single stream and return its decision."""
    store = _get_store(dataset)
    if not store.get_stream(stream_id):
        raise HTTPException(404, f"Stream not found: {stream_id}")
    if not store.get_assessment(stream_id):
        raise HTTPException(400, f"No assessment found for stream '{stream_id}'. Create an assessment first.")
    try:
        result = run_single_stream_decision(DATA_PATH / dataset, stream_id)
    except Exception as e:
        logger.error("Decision computation failed for %s: %s", stream_id, e, exc_info=True)
        raise HTTPException(500, f"Decision computation failed: {e}")
    if result is None:
        raise HTTPException(400, f"Could not compute decision for '{stream_id}'. Assessment may lack required data.")
    return result


@app.get("/api/decisions/{stream_id}")
def get_decision(stream_id: str, dataset: str = "examples"):
    """Get computed decision + review state for a stream."""
    store = _get_store(dataset)
    if not store.get_stream(stream_id):
        raise HTTPException(404, f"Stream not found: {stream_id}")
    review = store.get_review(stream_id)
    return {
        "stream_id": stream_id,
        "review": review,
    }


# ===================== Reviews =====================

VALID_REVIEW_STATUSES = {"draft", "completed", "reviewed"}
VALID_DECISIONS = {
    "centralize_now", "centralize_later", "harmonize_only",
    "standardize_only", "keep_local", "reassess_after_data_completion",
}
VALID_OPERATING_MODELS = {
    "centralized_execution", "central_method_local_execution",
    "federated_standardized", "local_independent",
}

@app.get("/api/reviews")
def list_reviews(dataset: str = "examples"):
    return _get_store(dataset).list_reviews()

@app.get("/api/reviews/{stream_id}")
def get_review(stream_id: str, dataset: str = "examples"):
    r = _get_store(dataset).get_review(stream_id)
    if not r:
        raise HTTPException(404, f"Review not found for stream: {stream_id}")
    return r

@app.put("/api/reviews")
def save_review(review: dict, dataset: str = "examples"):
    stream_id = review.get("stream_id", "").strip()
    if not stream_id:
        raise HTTPException(400, "Review requires 'stream_id'")

    store = _get_store(dataset)
    if not store.get_stream(stream_id):
        raise HTTPException(400, f"Stream not found: '{stream_id}'")

    # Validate review status
    status = review.get("review_status", "draft")
    if status not in VALID_REVIEW_STATUSES:
        raise HTTPException(400, f"Invalid review_status: '{status}'")

    # Override requires rationale
    override = review.get("override_applied", False)
    if override:
        rationale = (review.get("override_rationale") or "").strip()
        if not rationale:
            raise HTTPException(400, "Override requires 'override_rationale'")
        reviewed_decision = review.get("reviewed_decision", "")
        if reviewed_decision and reviewed_decision not in VALID_DECISIONS:
            raise HTTPException(400, f"Invalid reviewed_decision: '{reviewed_decision}'")
        reviewed_tom = review.get("reviewed_operating_model", "")
        if reviewed_tom and reviewed_tom not in VALID_OPERATING_MODELS:
            raise HTTPException(400, f"Invalid reviewed_operating_model: '{reviewed_tom}'")

    # Reviewed status requires reviewer name
    if status == "reviewed":
        reviewer = (review.get("reviewer_name") or "").strip()
        if not reviewer:
            raise HTTPException(400, "Reviewed status requires 'reviewer_name'")
        # Reviewed requires completed assessment
        assessment = store.get_assessment(stream_id)
        if not assessment or assessment.get("status") != "completed":
            raise HTTPException(
                400,
                "Cannot set review to 'reviewed': stream assessment must exist and be 'completed'"
            )

    review["stream_id"] = stream_id
    review["review_status"] = status
    return store.save_review(review)

@app.delete("/api/reviews/{stream_id}")
def delete_review(stream_id: str, dataset: str = "examples"):
    if not _get_store(dataset).delete_review(stream_id):
        raise HTTPException(404, f"Review not found for stream: {stream_id}")
    return {"deleted": stream_id}


# ===================== Analysis =====================

class AnalyzeRequest(BaseModel):
    data_dir: str = "examples"

@app.post("/api/analyze")
def analyze(request: AnalyzeRequest):
    data_dir = DATA_PATH / request.data_dir
    if not data_dir.exists():
        raise HTTPException(404, f"Data directory not found: {request.data_dir}")
    yaml_files = list(data_dir.glob("*.yaml"))
    if not yaml_files:
        raise HTTPException(400, f"No YAML files in {request.data_dir}")

    git_commit = _get_git_commit()
    timestamp = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
    data_source = f"{request.data_dir} ({len(yaml_files)} files)"

    logger.info("Starting analysis for %s", data_dir)
    try:
        report = run_analysis_and_report(data_dir, data_source, git_commit)
    except Exception as e:
        logger.error("Analysis failed: %s", e, exc_info=True)
        raise HTTPException(500, f"Analysis failed: {e}")

    report_name = f"report_{request.data_dir}_{timestamp}.md"
    (REPORT_PATH / "generated" / report_name).write_text(report, encoding="utf-8")

    # Also return structured results
    area_count = 0
    stream_count = 0
    stream_results = []
    try:
        areas, streams, sps, ifaces, assessments, cal = run_analysis(data_dir)
        area_count = len(areas)
        stream_count = len(streams)
        for a in assessments:
            if a.assessed_object_type.value == "stream" and a.result:
                sr = {
                    "id": a.assessed_object_id,
                    "score": a.result.harmonization_score,
                    "classification": a.result.classification.value,
                }
                if a.decision_result:
                    sr["decision"] = a.decision_result.decision.value
                    sr["target_operating_model"] = a.decision_result.target_operating_model.value
                if a.completeness:
                    sr["confidence"] = a.completeness.confidence_level.value
                    sr["completeness_score"] = a.completeness.completeness_score
                if a.prioritization_result:
                    sr["priority"] = a.prioritization_result.priority.value
                    sr["priority_score"] = a.prioritization_result.priority_score
                stream_results.append(sr)
    except Exception:
        pass

    return {
        "report_name": report_name,
        "timestamp": timestamp,
        "data_source": data_source,
        "git_commit": git_commit,
        "areas": area_count,
        "streams": stream_count,
        "stream_results": stream_results,
    }

# Keep legacy endpoint
@app.post("/analyze")
def analyze_legacy(request: AnalyzeRequest):
    return analyze(request)

# ===================== Calibration =====================

class CalibrateRequest(BaseModel):
    data_dir: str = "examples"

@app.post("/api/calibrate")
def calibrate_endpoint(request: CalibrateRequest):
    data_dir = DATA_PATH / request.data_dir
    if not data_dir.exists():
        raise HTTPException(404, f"Data directory not found: {request.data_dir}")
    try:
        result = run_calibration(data_dir)
    except Exception as e:
        logger.error("Calibration failed: %s", e, exc_info=True)
        raise HTTPException(500, f"Calibration failed: {e}")
    if result is None:
        raise HTTPException(400, "No outcome files found. Nothing to calibrate.")
    return {
        "outcomes_analyzed": result.outcomes_analyzed,
        "accuracy_rate": result.accuracy_rate,
        "model_maturity": result.model_maturity.value,
        "confidence_adjustment": result.confidence_adjustment,
        "systematic_biases": result.systematic_biases,
        "trust_score": result.trust_score.trust_score if result.trust_score else None,
    }

# Keep legacy
@app.post("/calibrate")
def calibrate_legacy(request: CalibrateRequest):
    return calibrate_endpoint(request)

# ===================== Reports =====================

@app.get("/api/reports")
def list_reports():
    reports = []
    for sub in ["generated", "reviewed"]:
        d = REPORT_PATH / sub
        if d.exists():
            for f in sorted(d.glob("*.md"), key=lambda p: p.stat().st_mtime, reverse=True):
                st = f.stat()
                reports.append({
                    "name": f.name,
                    "category": sub,
                    "size_bytes": st.st_size,
                    "created": datetime.fromtimestamp(st.st_mtime).strftime("%Y-%m-%d %H:%M:%S"),
                })
    return reports

@app.get("/api/reports/{name}", response_class=PlainTextResponse)
def get_report(name: str):
    for sub in ["generated", "reviewed"]:
        f = REPORT_PATH / sub / name
        if f.exists():
            return f.read_text(encoding="utf-8")
    raise HTTPException(404, f"Report not found: {name}")

# Keep legacy endpoints
@app.get("/reports")
def list_reports_legacy():
    return list_reports()

@app.get("/reports/{name}", response_class=PlainTextResponse)
def get_report_legacy(name: str):
    return get_report(name)

# ===================== Enum/Reference Data =====================

@app.get("/api/enums")
def get_enums():
    """Return all enum values for form dropdowns."""
    return {
        "stream_types": [t.value for t in StreamType],
        "country_scopes": ["DE", "AT", "BOTH"],
        "tenant_scopes": ["DE", "AT", "BOTH", "SEPARATE"],
        "interface_types": ["data_flow", "trigger", "escalation", "approval", "notification", "handover"],
        "alignment_dimensions": [d.value for d in AlignmentDimension],
        "hard_constraints": [
            "legal_local_difference",
            "tenant_separation_blocks_operation",
            "separate_control_ownership",
            "insufficient_documentation",
        ],
        "outcome_statuses": ["implemented", "rejected", "modified", "deferred"],
        "deviation_levels": ["none", "minor", "major", "complete_override"],
        "deviation_reasons": [
            "model_error", "incomplete_data", "changed_context",
            "political_decision", "resource_constraint", "strategic_override",
        ],
        "decisions": [
            "centralize_now", "centralize_later", "harmonize_only",
            "standardize_only", "keep_local", "reassess_after_data_completion",
        ],
        "operating_models": [
            "centralized_execution", "central_method_local_execution",
            "federated_standardized", "local_independent",
        ],
        "target_options": [t.value for t in TargetOption],
        "gap_levels": [g.value for g in GapLevel],
    }

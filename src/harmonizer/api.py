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

from harmonizer.pipeline import run_analysis, run_analysis_and_report, run_calibration
from harmonizer.store import YAMLStore
from harmonizer.scoring.engine import (
    compute_weighted_score,
    compute_type_specific_score,
    compute_blended_score,
    classify_score,
    get_weights_for_stream_type,
)
from harmonizer.models.process import StreamType
from harmonizer.models.assessment import (
    AlignmentDimension,
    AssessmentAnswer,
    TypeSpecificAnswer,
)

# --- Configuration ---

DATA_PATH = Path(os.environ.get("DATA_PATH", "/data"))
REPORT_PATH = Path(os.environ.get("REPORT_PATH", "/reports"))
LOG_PATH = Path(os.environ.get("LOG_PATH", "/logs"))
APP_VERSION = "0.8.0"

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
    return {"status": "ok", "version": APP_VERSION,
            "data_path": str(DATA_PATH), "report_path": str(REPORT_PATH)}

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
    return _get_store(dataset).save_area(area)

@app.delete("/api/areas/{area_id}")
def delete_area(area_id: str, dataset: str = "examples"):
    if not _get_store(dataset).delete_area(area_id):
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
    return _get_store(dataset).save_stream(stream)

@app.delete("/api/streams/{stream_id}")
def delete_stream(stream_id: str, dataset: str = "examples"):
    if not _get_store(dataset).delete_stream(stream_id):
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
    return _get_store(dataset).save_subprocess(sp)

@app.delete("/api/subprocesses/{sp_id}")
def delete_subprocess(sp_id: str, dataset: str = "examples"):
    if not _get_store(dataset).delete_subprocess(sp_id):
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
    return _get_store(dataset).save_interface(iface)

@app.delete("/api/interfaces/{iface_id}")
def delete_interface(iface_id: str, dataset: str = "examples"):
    if not _get_store(dataset).delete_interface(iface_id):
        raise HTTPException(404, f"Interface not found: {iface_id}")
    return {"deleted": iface_id}

# ===================== Assessments CRUD =====================

@app.get("/api/assessments")
def list_assessments(dataset: str = "examples"):
    return _get_store(dataset).list_assessments()

@app.get("/api/assessments/{obj_id}")
def get_assessment(obj_id: str, dataset: str = "examples"):
    a = _get_store(dataset).get_assessment(obj_id)
    if not a:
        raise HTTPException(404, f"Assessment not found: {obj_id}")
    return a

@app.put("/api/assessments")
def save_assessment(assessment: dict, dataset: str = "examples"):
    if "assessed_object_id" not in assessment:
        raise HTTPException(400, "Assessment requires 'assessed_object_id'")
    return _get_store(dataset).save_assessment(assessment)

@app.delete("/api/assessments/{obj_id}")
def delete_assessment(obj_id: str, dataset: str = "examples"):
    if not _get_store(dataset).delete_assessment(obj_id):
        raise HTTPException(404, f"Assessment not found: {obj_id}")
    return {"deleted": obj_id}

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

    base = compute_weighted_score(parsed, weights)
    ts_score = compute_type_specific_score(ts_parsed)
    blended = compute_blended_score(base, ts_score, bool(ts_parsed))
    classification = classify_score(blended)

    dims_answered = len({a.dimension for a in parsed})
    completeness_est = int(min(100, (dims_answered / 6) * 50 + (len(ts_parsed) / 4) * 30 + 20))

    return {
        "base_score": round(base, 4),
        "type_specific_score": round(ts_score, 4),
        "blended_score": round(blended, 4),
        "classification": classification.value,
        "dimensions_answered": dims_answered,
        "completeness_estimate": completeness_est,
    }

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
    }

"""FastAPI backend for the harmonization analysis tool.

Provides REST endpoints wrapping the existing analysis pipeline.
No duplication of logic — all endpoints delegate to pipeline.py.

Endpoints:
  POST /analyze          — run analysis on a data directory
  GET  /reports          — list generated reports
  GET  /reports/{name}   — retrieve a specific report
  POST /calibrate        — run calibration
  GET  /health           — health check
"""

import logging
import os
import subprocess
from datetime import datetime
from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.responses import PlainTextResponse
from pydantic import BaseModel

from harmonizer.pipeline import run_analysis_and_report, run_calibration

# --- Configuration from environment ---

DATA_PATH = Path(os.environ.get("DATA_PATH", "/data"))
REPORT_PATH = Path(os.environ.get("REPORT_PATH", "/reports"))
LOG_PATH = Path(os.environ.get("LOG_PATH", "/logs"))
APP_VERSION = "0.7.0"

# --- Logging ---

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    handlers=[
        logging.StreamHandler(),
    ],
)
logger = logging.getLogger("harmonizer.api")

# Add file handler if log path exists
if LOG_PATH.exists():
    file_handler = logging.FileHandler(LOG_PATH / "harmonizer.log")
    file_handler.setFormatter(logging.Formatter(
        "%(asctime)s [%(levelname)s] %(name)s: %(message)s"
    ))
    logging.getLogger().addHandler(file_handler)

# --- Helpers ---


def _get_git_commit() -> str:
    """Try to get current git commit hash."""
    try:
        result = subprocess.run(
            ["git", "rev-parse", "--short", "HEAD"],
            capture_output=True, text=True, timeout=5,
        )
        if result.returncode == 0:
            return result.stdout.strip()
    except (FileNotFoundError, subprocess.TimeoutExpired):
        pass
    return ""


def _ensure_dirs() -> None:
    """Ensure required directories exist."""
    for subdir in ["examples", "pilot", "outcomes", "archive"]:
        (DATA_PATH / subdir).mkdir(parents=True, exist_ok=True)
    for subdir in ["generated", "reviewed"]:
        (REPORT_PATH / subdir).mkdir(parents=True, exist_ok=True)
    LOG_PATH.mkdir(parents=True, exist_ok=True)


_ensure_dirs()


# --- FastAPI App ---

app = FastAPI(
    title="Harmonizer API",
    description="InfoSec Process Harmonization Analysis Tool",
    version=APP_VERSION,
)


# --- Request / Response Models ---

class AnalyzeRequest(BaseModel):
    data_dir: str = "examples"  # subdirectory under DATA_PATH


class AnalyzeResponse(BaseModel):
    report_name: str
    report_path: str
    data_source: str
    timestamp: str
    git_commit: str
    areas: int
    streams: int
    subprocesses: int
    assessments: int


class CalibrateRequest(BaseModel):
    data_dir: str = "examples"


class CalibrateResponse(BaseModel):
    outcomes_analyzed: int
    accuracy_rate: float
    model_maturity: str
    confidence_adjustment: float
    systematic_biases: list[str]
    trust_score: float | None


class ReportListItem(BaseModel):
    name: str
    size_bytes: int
    created: str


class HealthResponse(BaseModel):
    status: str
    version: str
    data_path: str
    report_path: str


# --- Endpoints ---

@app.get("/health", response_model=HealthResponse)
def health() -> HealthResponse:
    """Health check endpoint."""
    return HealthResponse(
        status="ok",
        version=APP_VERSION,
        data_path=str(DATA_PATH),
        report_path=str(REPORT_PATH),
    )


@app.post("/analyze", response_model=AnalyzeResponse)
def analyze(request: AnalyzeRequest) -> AnalyzeResponse:
    """Run harmonization analysis on a data directory."""
    data_dir = DATA_PATH / request.data_dir
    if not data_dir.exists():
        raise HTTPException(
            status_code=404,
            detail=f"Data directory not found: {request.data_dir}. "
                   f"Available: {[d.name for d in DATA_PATH.iterdir() if d.is_dir()]}",
        )

    yaml_files = list(data_dir.glob("*.yaml"))
    if not yaml_files:
        raise HTTPException(
            status_code=400,
            detail=f"No YAML files found in {request.data_dir}",
        )

    git_commit = _get_git_commit()
    data_source = f"{request.data_dir} ({len(yaml_files)} files)"
    timestamp = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")

    logger.info("Starting analysis for %s", data_dir)

    try:
        report = run_analysis_and_report(
            data_dir=data_dir,
            data_source=data_source,
            git_commit=git_commit,
        )
    except Exception as e:
        logger.error("Analysis failed: %s", e, exc_info=True)
        raise HTTPException(status_code=500, detail=f"Analysis failed: {e}")

    # Save report
    report_name = f"report_{request.data_dir}_{timestamp}.md"
    report_file = REPORT_PATH / "generated" / report_name
    report_file.write_text(report, encoding="utf-8")
    logger.info("Report saved: %s", report_file)

    # Count entities from the report header for the response
    lines = report.split("\n")
    area_count = sum(1 for l in lines if l.startswith("## Area:"))
    stream_count = sum(1 for l in lines if l.startswith("### Stream:"))
    sp_count = sum(1 for l in lines if l.startswith("#### Subprocess:"))
    assessment_count = sum(1 for l in lines if "Assessment:" in l and "Not yet assessed" not in l)

    return AnalyzeResponse(
        report_name=report_name,
        report_path=str(report_file),
        data_source=data_source,
        timestamp=timestamp,
        git_commit=git_commit,
        areas=area_count,
        streams=stream_count,
        subprocesses=sp_count,
        assessments=assessment_count,
    )


@app.get("/reports", response_model=list[ReportListItem])
def list_reports() -> list[ReportListItem]:
    """List all generated reports."""
    generated_dir = REPORT_PATH / "generated"
    reports = []
    for f in sorted(generated_dir.glob("*.md"), key=lambda p: p.stat().st_mtime, reverse=True):
        stat = f.stat()
        reports.append(ReportListItem(
            name=f.name,
            size_bytes=stat.st_size,
            created=datetime.fromtimestamp(stat.st_mtime).strftime("%Y-%m-%d %H:%M:%S"),
        ))
    return reports


@app.get("/reports/{name}", response_class=PlainTextResponse)
def get_report(name: str) -> str:
    """Retrieve a specific report by name."""
    # Check both generated and reviewed
    for subdir in ["generated", "reviewed"]:
        report_file = REPORT_PATH / subdir / name
        if report_file.exists():
            return report_file.read_text(encoding="utf-8")
    raise HTTPException(status_code=404, detail=f"Report not found: {name}")


@app.post("/calibrate", response_model=CalibrateResponse)
def calibrate_endpoint(request: CalibrateRequest) -> CalibrateResponse:
    """Run calibration comparing predictions against actual outcomes."""
    data_dir = DATA_PATH / request.data_dir
    if not data_dir.exists():
        raise HTTPException(status_code=404, detail=f"Data directory not found: {request.data_dir}")

    logger.info("Starting calibration for %s", data_dir)

    try:
        result = run_calibration(data_dir)
    except Exception as e:
        logger.error("Calibration failed: %s", e, exc_info=True)
        raise HTTPException(status_code=500, detail=f"Calibration failed: {e}")

    if result is None:
        raise HTTPException(
            status_code=400,
            detail="No outcome files found (*outcome*.yaml). Nothing to calibrate.",
        )

    return CalibrateResponse(
        outcomes_analyzed=result.outcomes_analyzed,
        accuracy_rate=result.accuracy_rate,
        model_maturity=result.model_maturity.value,
        confidence_adjustment=result.confidence_adjustment,
        systematic_biases=result.systematic_biases,
        trust_score=result.trust_score.trust_score if result.trust_score else None,
    )

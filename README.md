# Harmonizer — InfoSec Process Harmonization Analysis Tool

Internal CLI + API tool for analyzing and documenting the harmonization potential of information security processes across DE/AT organizational units.

## Quick Start

### CLI

```bash
pip install -e ".[dev]"
harmonizer analyze --data-dir data/examples -o report.md
pytest
```

### Docker (Production)

```bash
cp .env.example .env
# Copy your YAML data into deploy/data/examples/
cp data/examples/*.yaml deploy/data/examples/
docker-compose up -d
# API at http://localhost:8001
# Report Viewer at http://localhost:3001
```

## Project Structure

```
src/harmonizer/
├── models/
│   ├── process.py        # Area, Stream, StreamType, SubProcess, ProcessInterface
│   └── assessment.py     # Assessment, scoring models, completeness, confidence
├── scoring/
│   ├── engine.py         # Stream-type-aware scoring, aggregation, completeness
│   ├── decision_engine.py # Decision engine, interface complexity, H/S/C, operating model
│   ├── calibration_engine.py # Calibration, trust score, protected rules
│   ├── questions.py      # Stream-type-specific supplementary question catalog
│   └── loader.py         # YAML data loader
├── reporting/
│   └── markdown.py       # Markdown + Mermaid report with full decision context
├── pipeline.py           # Reusable analysis pipeline (used by CLI + API)
├── api.py                # FastAPI REST backend
└── cli.py                # Click-based CLI entry point (v0.7.0)

data/examples/
├── processes.yaml        # 4 areas, 15 streams, 42 subprocesses, 16 interfaces
└── assessments.yaml      # 15 stream + 16 subprocess assessments

tests/
├── test_models.py        # Model validation tests (19 tests)
├── test_scoring.py       # Scoring, aggregation, completeness, prioritization (41 tests)
├── test_questions.py     # Question catalog tests (9 tests)
├── test_loader.py        # YAML loader tests (8 tests)
└── test_report.py        # Report generation tests (9 tests)
```

## Architecture

### Three-Tier Hierarchy

```
Area (organizational grouping)
  └── Stream (functional domain, typed)
        └── SubProcess (process step)
```

- **Area:** "Definition & Design", "Check & Execute", etc.
- **Stream:** A functional domain with a `stream_type` that influences scoring
- **SubProcess:** Belongs to exactly one stream
- **ProcessInterface:** Directed relationship between any two processes (NOT parent-child)

### Stream Types

| Type | Focus for Harmonization Assessment |
|---|---|
| `process` | Workflow, roles, inputs/outputs, tooling |
| `governance_function` | Mandates, policies, control model, evidence |
| `service_domain` | Delivery model, customer interface, contracts |
| `support_function` | Standardization, efficiency, reusability |
| `capability_domain` | Enablement, methods, platforms, know-how |
| `program_domain` | Steering, initiatives, transformation, coordination |

### Harmonization Classification

| Level | Meaning |
|---|---|
| `fully_centralizable` | Can be run identically across DE/AT |
| `central_method_local_execution` | Central methodology, local execution |
| `partially_harmonizable` | Some parts unifiable, others remain local |
| `minimum_standard_only` | Only central minimum standards feasible |
| `currently_not_harmonizable` | Must remain fully local for now |

### Two-Level Assessment & Aggregation

Assessments can be made at both **stream** and **subprocess** levels. Stream-level results are computed by blending:

- **40%** direct stream assessment score
- **60%** average of subprocess assessment scores

If only one level has data, that level is used at 100%. Hard constraints from subprocesses propagate upward.

### Stream-Type-Aware Scoring

Six dimensions (1-5 each), with weights varying by stream type:

| Dimension | process | governance | service | support | capability | program |
|---|---|---|---|---|---|---|
| regulatory_alignment | 0.20 | **0.30** | 0.15 | 0.10 | 0.10 | 0.15 |
| operational_alignment | **0.25** | 0.10 | 0.25 | **0.30** | 0.20 | 0.15 |
| tooling_alignment | 0.20 | 0.10 | 0.15 | 0.25 | **0.25** | 0.10 |
| governance_alignment | 0.15 | **0.30** | 0.20 | 0.10 | 0.15 | **0.30** |
| maturity | 0.10 | 0.10 | 0.10 | 0.15 | **0.20** | 0.15 |
| local_necessity | 0.10 | 0.10 | 0.15 | 0.10 | 0.10 | 0.15 |

Hard constraints cap the classification downward regardless of score.

### Type-Specific Supplementary Questions

Each StreamType has 4-5 supplementary questions that probe domain-specific harmonization factors. These contribute **15%** to the blended score (base dimensions contribute 85%).

| StreamType | Question ID prefix | Example question focus |
|---|---|---|
| process | `proc_*` | Trigger uniformity, workflow steps, handover points |
| governance_function | `gov_*` | Mandate sharing, policy model, evidence catalog |
| service_domain | `svc_*` | Service catalog, SLA harmonization, delivery model |
| support_function | `sup_*` | Process standards, tool consolidation, capacity sharing |
| capability_domain | `cap_*` | Method sharing, platform integration, competency model |
| program_domain | `prg_*` | Steering unification, initiative sync, transformation model |

### Completeness & Confidence

Each assessment receives a **completeness score** (0-100) based on 8 factors:

| Factor | Max Points |
|---|---|
| Base dimension answers | 30 |
| Type-specific answers | 20 |
| Hard constraints documented | 10 |
| Subprocess coverage | 20 |
| Interface documentation | 5 |
| Regulatory dimension scored | 5 |
| Tenant scope considered | 5 |
| Prioritization provided | 5 |

Confidence levels derived from completeness:
- **High:** ≥75 points
- **Medium:** ≥45 points
- **Low:** <45 points

The report shows confidence badges next to each assessment and filters the "Recommended First Movers" list to medium+ confidence only.

### Prioritization

Five factors determine harmonization initiative priority:

| Factor | Direction | Weight |
|---|---|---|
| harmonization_potential | positive | 0.30 |
| operational_relevance | positive | 0.20 |
| governance_compliance_benefit | positive | 0.25 |
| implementation_effort | **inverted** | 0.15 |
| dependencies | **inverted** | 0.10 |

Result: `high_priority`, `medium_priority`, or `low_priority`.

### Report Features

- **Executive summary** with classification distribution
- **Process overview** as Mermaid diagram (areas, streams, subprocesses, interfaces)
- **Per-stream detail** with subprocess counts, interface counts, dimension scores
- **Confidence badges** showing assessment reliability
- **Assessment Gaps section** identifying missing data (unassessed subprocesses, missing dimensions, etc.)
- **Management view** with prioritization table filtered by confidence level

## CLI Pipeline

The `analyze` command runs a 3-phase pipeline:

1. **Evaluate:** Score all individual assessments using stream-type-aware weights
2. **Aggregate:** Compute stream-level results from subprocess assessments (40/60 blend)
3. **Completeness:** Calculate completeness scores and confidence levels for all assessments

## Assumptions

1. Two ISMS tenants (DE/AT) are the primary organizational boundary.
2. Stream type determines dimension weight profiles for scoring.
3. Subprocess assessments inherit the parent stream's type for weight selection.
4. Hard constraints are binary and always reduce harmonizability.
5. The `local_necessity` dimension uses inverted semantics: 1 = high local necessity.
6. Prioritization factors are scored independently of alignment dimensions.
7. Assessment is per-object (one assessment per stream or subprocess).
8. Completeness scoring prevents false precision on thin assessment data.

## Deployment (Docker)

### Prerequisites

- Docker >= 20.10
- Docker Compose >= 2.0

### Directory Structure

```
deploy/
├── data/
│   ├── examples/    # Example/demo data (shipped with the tool)
│   ├── pilot/       # Pilot assessment data
│   ├── outcomes/    # Decision outcome YAML files for calibration
│   └── archive/     # Archived assessment cycles
├── reports/
│   ├── generated/   # Auto-generated analysis reports
│   └── reviewed/    # Reviewed/approved reports
└── logs/            # Application logs
```

Data and code are strictly separated. All persistent data lives under `deploy/` on the host.

### Configuration

Copy `.env.example` to `.env` and adjust:

```bash
cp .env.example .env
```

| Variable | Default | Description |
|---|---|---|
| `APP_ENV` | production | Environment identifier |
| `BACKEND_PORT` | 8001 | API port |
| `FRONTEND_PORT` | 3001 | Report viewer port |
| `DATA_PATH` | ./deploy/data | Host path for YAML data |
| `REPORT_PATH` | ./deploy/reports | Host path for generated reports |
| `LOG_PATH` | ./deploy/logs | Host path for logs |

### Start

```bash
# Copy example data for initial setup
cp data/examples/*.yaml deploy/data/examples/

# Build and start
docker-compose up -d

# Verify
curl http://localhost:8001/health
```

### Stop

```bash
docker-compose down
```

### Logs

```bash
# All services
docker-compose logs -f

# Backend only
docker-compose logs -f backend

# Persistent log file
tail -f deploy/logs/harmonizer.log
```

### API Endpoints

| Method | Endpoint | Description |
|---|---|---|
| `GET` | `/health` | Health check |
| `POST` | `/analyze` | Run analysis (`{"data_dir": "examples"}`) |
| `GET` | `/reports` | List generated reports |
| `GET` | `/reports/{name}` | Retrieve a report |
| `POST` | `/calibrate` | Run calibration (`{"data_dir": "examples"}`) |

### Example: Run Analysis via API

```bash
curl -X POST http://localhost:8001/analyze \
  -H "Content-Type: application/json" \
  -d '{"data_dir": "examples"}'
```

### Example: Pilot Deployment

1. Place your YAML files in `deploy/data/pilot/`
2. Run analysis:
   ```bash
   curl -X POST http://localhost:8001/analyze \
     -H "Content-Type: application/json" \
     -d '{"data_dir": "pilot"}'
   ```
3. View report at http://localhost:3001
4. After implementation, record outcomes in `deploy/data/pilot/outcomes.yaml`
5. Run calibration:
   ```bash
   curl -X POST http://localhost:8001/calibrate \
     -H "Content-Type: application/json" \
     -d '{"data_dir": "pilot"}'
   ```

### Report Traceability

Every generated report contains:
- **Timestamp** (ISO 8601)
- **App Version** (e.g. 0.7.0)
- **Git Commit** (short hash, if available)
- **Data Source** (which directory was analyzed)

### CLI Still Available

The CLI remains fully functional inside the container:

```bash
docker-compose exec backend harmonizer analyze --data-dir /data/examples -o /reports/generated/manual.md
```

## Future Extensions

- Activity/procedure step level (fourth hierarchy tier)
- Gap analysis between DE and AT process variants
- LLM-assisted assessment suggestions
- Web UI for collaborative assessment
- Export to BPMN 2.0
- Integration with ISMS tooling APIs

# Harmonizer — InfoSec Process Harmonization Analysis Tool

Internal CLI tool for analyzing and documenting the harmonization potential of information security processes across DE/AT organizational units.

## Quick Start

```bash
pip install -e ".[dev]"
harmonizer analyze --data-dir data/examples -o report.md
pytest
```

## Project Structure

```
src/harmonizer/
├── models/
│   ├── process.py        # Area, Stream, StreamType, SubProcess, ProcessInterface
│   └── assessment.py     # Assessment, scoring models, prioritization
├── scoring/
│   ├── engine.py         # Stream-type-aware scoring + prioritization logic
│   └── loader.py         # YAML data loader
├── reporting/
│   └── markdown.py       # Markdown + Mermaid report with management view
└── cli.py                # Click-based CLI entry point

data/examples/
├── processes.yaml        # 4 areas, 15 streams, subprocesses, interfaces
└── assessments.yaml      # Stream and subprocess assessments with prioritization

tests/
├── test_models.py        # Model validation tests
├── test_scoring.py       # Scoring engine + prioritization tests
├── test_loader.py        # YAML loader tests
└── test_report.py        # Report generation tests
```

## Breaking Changes from v0.1.0

- `MainProcess` replaced by `Area` + `Stream` (three-tier hierarchy)
- `main_process_id` on SubProcess replaced by `stream_id`
- `AssessedObjectType.MAIN_PROCESS` replaced by `AssessedObjectType.STREAM`
- YAML structure changed: `main_processes` replaced by `areas` + `streams`
- Scoring is now stream-type-aware (different weights per StreamType)
- New: Prioritization logic and management view in reports

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

## Assumptions

1. Two ISMS tenants (DE/AT) are the primary organizational boundary.
2. Stream type determines dimension weight profiles for scoring.
3. Subprocess assessments inherit the parent stream's type for weight selection.
4. Hard constraints are binary and always reduce harmonizability.
5. The `local_necessity` dimension uses inverted semantics: 1 = high local necessity.
6. Prioritization factors are scored independently of alignment dimensions.
7. Assessment is per-object (one assessment per stream or subprocess).

## Future Extensions

- Activity/procedure step level (fourth hierarchy tier)
- Gap analysis between DE and AT process variants
- LLM-assisted assessment suggestions
- Web UI for collaborative assessment
- Export to BPMN 2.0
- Integration with ISMS tooling APIs

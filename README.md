# Harmonizer — InfoSec Process Harmonization Analysis Tool

Internal CLI tool for analyzing and documenting the harmonization potential of information security processes across DE/AT organizational units.

## Quick Start

```bash
# Install dependencies
pip install -e ".[dev]"

# Run analysis on example data
harmonizer analyze --data-dir data/examples -o report.md

# Run tests
pytest
```

## Project Structure

```
src/harmonizer/
├── models/
│   ├── process.py        # MainProcess, SubProcess, ProcessInterface
│   └── assessment.py     # Assessment, scoring models, classifications
├── scoring/
│   ├── engine.py         # Deterministic scoring logic
│   └── loader.py         # YAML data loader
├── reporting/
│   └── markdown.py       # Markdown + Mermaid report generator
└── cli.py                # Click-based CLI entry point

data/examples/
├── processes.yaml        # Example process definitions (2 streams)
└── assessments.yaml      # Example assessment data

tests/
├── test_models.py        # Model validation tests
├── test_scoring.py       # Scoring engine tests
├── test_loader.py        # YAML loader tests
└── test_report.py        # Report generation tests
```

## Architecture Decisions

- **Pydantic v2** for data validation and type safety
- **YAML** for human-readable configuration and process data
- **Click** for CLI framework
- **Deterministic scoring** — no ML/LLM dependency in the core assessment pipeline
- **Mermaid** for diagrams (renderable in any Markdown viewer)

## Key Concepts

### Process Hierarchy

- **MainProcess (Stream):** Top-level InfoSec domain (e.g., Incident Management)
- **SubProcess:** A step within a stream (e.g., Incident Triage)
- **ProcessInterface:** A directed relationship between processes (NOT parent-child)

A SubProcess belongs to exactly one MainProcess. Interfaces to other processes are modeled separately.

### Harmonization Classification

| Level | Meaning |
|---|---|
| `fully_centralizable` | Can be run identically across DE/AT |
| `central_method_local_execution` | Central methodology, local execution |
| `partially_harmonizable` | Some parts unifiable, others remain local |
| `minimum_standard_only` | Only central minimum standards feasible |
| `currently_not_harmonizable` | Must remain fully local for now |

### Scoring

Six dimensions (1-5 each), weighted and normalized to 0.0-1.0:

| Dimension | Weight |
|---|---|
| regulatory_alignment | 0.25 |
| operational_alignment | 0.20 |
| governance_alignment | 0.20 |
| tooling_alignment | 0.15 |
| maturity | 0.10 |
| local_necessity | 0.10 |

Hard constraints can cap the classification downward regardless of score.

## Assumptions

1. Two ISMS tenants (DE/AT) are the primary organizational boundary.
2. Regulatory context is captured as a list of references, not parsed.
3. Dimension weights are configurable but sensible defaults are provided.
4. Hard constraints are binary (present or absent) and always reduce harmonizability.
5. The `local_necessity` dimension uses inverted semantics: score 1 = high local necessity (bad for harmonization), score 5 = no local necessity.
6. Process interfaces are directed (source → target) and typed.
7. Assessment is per-object (one assessment per main process or subprocess).

## Future Extensions

- Activity/procedure step level (third hierarchy tier)
- Gap analysis between DE and AT process variants
- LLM-assisted assessment suggestions
- Web UI for collaborative assessment
- Export to BPMN 2.0
- Integration with ISMS tooling APIs

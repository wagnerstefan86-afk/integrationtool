"""CLI entry point for the harmonization analysis tool.

Usage:
    harmonizer analyze --data-dir ./data/examples --output report.md
    harmonizer analyze --data-dir ./data/examples  # prints to stdout
"""

from pathlib import Path

import click

from harmonizer.scoring.loader import load_all_from_directory
from harmonizer.scoring.engine import evaluate, compute_prioritization
from harmonizer.models.assessment import AssessedObjectType
from harmonizer.reporting.markdown import generate_report


@click.group()
@click.version_option(version="0.2.0")
def main() -> None:
    """InfoSec Process Harmonization Analysis Tool."""


@main.command()
@click.option(
    "--data-dir",
    type=click.Path(exists=True, file_okay=False, path_type=Path),
    required=True,
    help="Directory containing process and assessment YAML files.",
)
@click.option(
    "--output",
    "-o",
    type=click.Path(dir_okay=False, path_type=Path),
    default=None,
    help="Output file path for the Markdown report. Defaults to stdout.",
)
def analyze(data_dir: Path, output: Path | None) -> None:
    """Load process data, run harmonization scoring, and generate a report."""
    click.echo(f"Loading data from {data_dir} ...", err=True)
    areas, streams, subprocesses, interfaces, assessments = load_all_from_directory(data_dir)

    click.echo(
        f"Loaded: {len(areas)} areas, {len(streams)} streams, "
        f"{len(subprocesses)} subprocesses, {len(interfaces)} interfaces, "
        f"{len(assessments)} assessments.",
        err=True,
    )

    # Build stream lookup for type-aware scoring
    stream_index = {s.id: s for s in streams}
    # Map subprocess IDs to their parent stream's type
    sp_to_stream: dict[str, str] = {sp.id: sp.stream_id for sp in subprocesses}

    # Run scoring with stream-type-aware weights
    for assessment in assessments:
        stream_type = None
        if assessment.assessed_object_type == AssessedObjectType.STREAM:
            stream = stream_index.get(assessment.assessed_object_id)
            if stream:
                stream_type = stream.stream_type
        elif assessment.assessed_object_type == AssessedObjectType.SUBPROCESS:
            parent_stream_id = sp_to_stream.get(assessment.assessed_object_id)
            if parent_stream_id:
                stream = stream_index.get(parent_stream_id)
                if stream:
                    stream_type = stream.stream_type

        assessment.result = evaluate(assessment, stream_type=stream_type)

        if assessment.prioritization:
            assessment.prioritization_result = compute_prioritization(assessment.prioritization)

    scored = sum(1 for a in assessments if a.result is not None)
    prioritized = sum(1 for a in assessments if a.prioritization_result is not None)
    click.echo(f"Scored {scored} assessments, {prioritized} with prioritization.", err=True)

    report = generate_report(areas, streams, subprocesses, interfaces, assessments)

    if output:
        output.write_text(report, encoding="utf-8")
        click.echo(f"Report written to {output}", err=True)
    else:
        click.echo(report)


if __name__ == "__main__":
    main()

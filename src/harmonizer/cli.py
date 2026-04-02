"""CLI entry point for the harmonization analysis tool.

Usage:
    harmonizer analyze --data-dir ./data/examples --output report.md
    harmonizer analyze --data-dir ./data/examples  # prints to stdout
"""

import sys
from pathlib import Path

import click

from harmonizer.scoring.loader import load_all_from_directory
from harmonizer.scoring.engine import evaluate
from harmonizer.reporting.markdown import generate_report


@click.group()
@click.version_option(version="0.1.0")
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
    # Load data
    click.echo(f"Loading data from {data_dir} ...", err=True)
    main_processes, subprocesses, interfaces, assessments = load_all_from_directory(data_dir)

    click.echo(
        f"Loaded: {len(main_processes)} streams, {len(subprocesses)} subprocesses, "
        f"{len(interfaces)} interfaces, {len(assessments)} assessments.",
        err=True,
    )

    # Run scoring
    for assessment in assessments:
        assessment.result = evaluate(assessment)

    scored = sum(1 for a in assessments if a.result is not None)
    click.echo(f"Scored {scored} assessments.", err=True)

    # Generate report
    report = generate_report(main_processes, subprocesses, interfaces, assessments)

    if output:
        output.write_text(report, encoding="utf-8")
        click.echo(f"Report written to {output}", err=True)
    else:
        click.echo(report)


if __name__ == "__main__":
    main()

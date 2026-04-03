"""CLI entry point for the harmonization analysis tool.

Usage:
    harmonizer analyze --data-dir ./data/examples --output report.md
    harmonizer analyze --data-dir ./data/examples  # prints to stdout
    harmonizer calibrate --data-dir ./data/examples
"""

from pathlib import Path

import click

from harmonizer.pipeline import run_analysis_and_report, run_calibration
from harmonizer.scoring.loader import load_all_from_directory, load_outcomes_from_directory
from harmonizer.scoring.calibration_engine import calibrate


@click.group()
@click.version_option(version="0.7.0")
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

    report = run_analysis_and_report(
        data_dir=data_dir,
        data_source=str(data_dir),
    )

    if output:
        output.write_text(report, encoding="utf-8")
        click.echo(f"Report written to {output}", err=True)
    else:
        click.echo(report)


@main.command()
@click.option(
    "--data-dir",
    type=click.Path(exists=True, file_okay=False, path_type=Path),
    required=True,
    help="Directory containing assessment and outcome YAML files.",
)
def calibrate_cmd(data_dir: Path) -> None:
    """Run calibration analysis comparing predictions against actual outcomes."""
    _, _, _, _, assessments = load_all_from_directory(data_dir)
    outcomes = load_outcomes_from_directory(data_dir)

    if not outcomes:
        click.echo("No outcome files found (*outcome*.yaml). Nothing to calibrate.", err=True)
        return

    result = calibrate(assessments, outcomes)
    click.echo(f"Outcomes analyzed: {result.outcomes_analyzed}")
    click.echo(f"Accuracy rate: {result.accuracy_rate:.0%}")
    click.echo(f"Model maturity: {result.model_maturity.value}")
    click.echo(f"Confidence adjustment: {result.confidence_adjustment:+.2f}")

    if result.systematic_biases:
        click.echo("\nSystematic biases:")
        for bias in result.systematic_biases:
            click.echo(f"  - {bias}")

    if result.suggestions:
        click.echo("\nAdjustment suggestions:")
        for s in result.suggestions:
            click.echo(f"  [{s.priority.value}] {s.area}: {s.suggestion}")


if __name__ == "__main__":
    main()

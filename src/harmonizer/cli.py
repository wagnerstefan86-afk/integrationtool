"""CLI entry point for the harmonization analysis tool.

Usage:
    harmonizer analyze --data-dir ./data/examples --output report.md
    harmonizer analyze --data-dir ./data/examples  # prints to stdout
"""

from pathlib import Path

import click

from harmonizer.scoring.loader import load_all_from_directory, load_outcomes_from_directory
from harmonizer.scoring.engine import (
    evaluate,
    compute_prioritization,
    aggregate_stream_assessment,
    compute_completeness,
)
from harmonizer.scoring.decision_engine import compute_decision
from harmonizer.scoring.calibration_engine import calibrate
from harmonizer.models.assessment import AssessedObjectType, CalibrationResult
from harmonizer.reporting.markdown import generate_report


@click.group()
@click.version_option(version="0.6.0")
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

    # Build indices
    stream_index = {s.id: s for s in streams}
    sp_to_stream: dict[str, str] = {sp.id: sp.stream_id for sp in subprocesses}
    sps_by_stream: dict[str, list[str]] = {}
    for sp in subprocesses:
        sps_by_stream.setdefault(sp.stream_id, []).append(sp.id)
    assessment_index = {a.assessed_object_id: a for a in assessments}

    # Count interfaces per stream (including subprocess interfaces)
    def _interface_count(stream_id: str) -> int:
        sp_ids = set(sps_by_stream.get(stream_id, []))
        relevant = sp_ids | {stream_id}
        return sum(
            1 for iface in interfaces
            if iface.source_process_id in relevant or iface.target_process_id in relevant
        )

    # Phase 1: Evaluate all individual assessments
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

    # Phase 2: Aggregate stream-level results from subprocesses
    for stream in streams:
        stream_assessment = assessment_index.get(stream.id)
        sp_ids = sps_by_stream.get(stream.id, [])
        sp_assessments = [assessment_index[sp_id] for sp_id in sp_ids if sp_id in assessment_index]

        if sp_assessments:
            aggregated = aggregate_stream_assessment(
                stream_assessment, sp_assessments, stream.stream_type
            )
            if aggregated and stream_assessment:
                # Replace stream result with aggregated version
                stream_assessment.result = aggregated

    # Phase 3: Compute completeness for all assessments
    for assessment in assessments:
        stream_type = None
        subprocess_count = 0
        subprocess_assessed_count = 0
        iface_count = 0
        has_regulatory = False
        has_tenant = True  # always populated in model

        if assessment.assessed_object_type == AssessedObjectType.STREAM:
            stream = stream_index.get(assessment.assessed_object_id)
            if stream:
                stream_type = stream.stream_type
                sp_ids = sps_by_stream.get(stream.id, [])
                subprocess_count = len(sp_ids)
                subprocess_assessed_count = sum(1 for sp_id in sp_ids if sp_id in assessment_index)
                iface_count = _interface_count(stream.id)
                has_regulatory = bool(stream.regulatory_context)
        elif assessment.assessed_object_type == AssessedObjectType.SUBPROCESS:
            parent_stream_id = sp_to_stream.get(assessment.assessed_object_id)
            if parent_stream_id:
                stream = stream_index.get(parent_stream_id)
                if stream:
                    stream_type = stream.stream_type
            # Find interfaces involving this subprocess
            sp_id = assessment.assessed_object_id
            iface_count = sum(
                1 for iface in interfaces
                if iface.source_process_id == sp_id or iface.target_process_id == sp_id
            )
            # Check if subprocess has regulatory context
            sp_obj = next((sp for sp in subprocesses if sp.id == sp_id), None)
            if sp_obj:
                has_regulatory = bool(sp_obj.regulatory_context)

        assessment.completeness = compute_completeness(
            assessment,
            stream_type=stream_type,
            subprocess_count=subprocess_count,
            subprocess_assessed_count=subprocess_assessed_count,
            interface_count=iface_count,
            has_regulatory_context=has_regulatory,
            has_tenant_scope=has_tenant,
        )

    # Phase 4: Decision engine for stream-level assessments
    decided = 0
    for assessment in assessments:
        if assessment.assessed_object_type != AssessedObjectType.STREAM:
            continue
        stream = stream_index.get(assessment.assessed_object_id)
        if not stream or assessment.result is None:
            continue
        has_regulatory = bool(stream.regulatory_context)
        assessment.decision_result = compute_decision(
            assessment=assessment,
            stream=stream,
            subprocesses=subprocesses,
            interfaces=interfaces,
            all_streams=streams,
            has_regulatory_context=has_regulatory,
        )
        decided += 1

    scored = sum(1 for a in assessments if a.result is not None)
    prioritized = sum(1 for a in assessments if a.prioritization_result is not None)
    click.echo(
        f"Scored {scored} assessments, {prioritized} with prioritization, "
        f"{decided} with decisions.",
        err=True,
    )

    # Phase 5: Calibration (if outcome data exists)
    outcomes = load_outcomes_from_directory(data_dir)
    calibration_result = None
    if outcomes:
        calibration_result = calibrate(assessments, outcomes)
        click.echo(
            f"Calibration: {calibration_result.outcomes_analyzed} outcome(s), "
            f"accuracy {calibration_result.accuracy_rate:.0%}, "
            f"maturity: {calibration_result.model_maturity.value}.",
            err=True,
        )

    report = generate_report(
        areas, streams, subprocesses, interfaces, assessments,
        calibration=calibration_result,
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

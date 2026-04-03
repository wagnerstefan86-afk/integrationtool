"""Core analysis pipeline.

Extracts the analysis logic from the CLI so it can be reused by
both the CLI and the API layer without duplication.
"""

from pathlib import Path
from typing import Optional

from harmonizer.scoring.loader import load_all_from_directory, load_outcomes_from_directory
from harmonizer.scoring.engine import (
    evaluate,
    compute_prioritization,
    aggregate_stream_assessment,
    compute_completeness,
)
from harmonizer.scoring.decision_engine import compute_decision
from harmonizer.scoring.calibration_engine import calibrate
from harmonizer.models.process import Area, Stream, SubProcess, ProcessInterface
from harmonizer.models.assessment import (
    Assessment,
    AssessedObjectType,
    CalibrationResult,
    DecisionOutcome,
)
from harmonizer.reporting.markdown import generate_report


def run_analysis(
    data_dir: Path,
) -> tuple[
    list[Area],
    list[Stream],
    list[SubProcess],
    list[ProcessInterface],
    list[Assessment],
    Optional[CalibrationResult],
]:
    """Run the full analysis pipeline on a data directory.

    Returns the loaded structures, scored assessments, and calibration result.
    """
    areas, streams, subprocesses, interfaces, assessments = load_all_from_directory(data_dir)

    stream_index = {s.id: s for s in streams}
    sp_to_stream: dict[str, str] = {sp.id: sp.stream_id for sp in subprocesses}
    sps_by_stream: dict[str, list[str]] = {}
    for sp in subprocesses:
        sps_by_stream.setdefault(sp.stream_id, []).append(sp.id)
    assessment_index = {a.assessed_object_id: a for a in assessments}

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
                stream_assessment.result = aggregated

    # Phase 3: Compute completeness
    for assessment in assessments:
        stream_type = None
        subprocess_count = 0
        subprocess_assessed_count = 0
        iface_count = 0
        has_regulatory = False
        has_tenant = True

        if assessment.assessed_object_type == AssessedObjectType.STREAM:
            stream = stream_index.get(assessment.assessed_object_id)
            if stream:
                stream_type = stream.stream_type
                sp_ids = sps_by_stream.get(stream.id, [])
                subprocess_count = len(sp_ids)
                subprocess_assessed_count = sum(1 for sp_id in sp_ids if sp_id in assessment_index)
                sp_id_set = set(sp_ids)
                relevant = sp_id_set | {stream.id}
                iface_count = sum(
                    1 for iface in interfaces
                    if iface.source_process_id in relevant or iface.target_process_id in relevant
                )
                has_regulatory = bool(stream.regulatory_context)
        elif assessment.assessed_object_type == AssessedObjectType.SUBPROCESS:
            parent_stream_id = sp_to_stream.get(assessment.assessed_object_id)
            if parent_stream_id:
                stream = stream_index.get(parent_stream_id)
                if stream:
                    stream_type = stream.stream_type
            sp_id = assessment.assessed_object_id
            iface_count = sum(
                1 for iface in interfaces
                if iface.source_process_id == sp_id or iface.target_process_id == sp_id
            )
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

    # Phase 4: Decision engine
    for assessment in assessments:
        if assessment.assessed_object_type != AssessedObjectType.STREAM:
            continue
        stream = stream_index.get(assessment.assessed_object_id)
        if not stream or assessment.result is None:
            continue
        assessment.decision_result = compute_decision(
            assessment=assessment,
            stream=stream,
            subprocesses=subprocesses,
            interfaces=interfaces,
            all_streams=streams,
            has_regulatory_context=bool(stream.regulatory_context),
        )

    # Phase 5: Calibration
    outcomes = load_outcomes_from_directory(data_dir)
    calibration_result = None
    if outcomes:
        calibration_result = calibrate(assessments, outcomes)

    return areas, streams, subprocesses, interfaces, assessments, calibration_result


def run_analysis_and_report(
    data_dir: Path,
    data_source: str = "",
    git_commit: str = "",
) -> str:
    """Run analysis and return the Markdown report."""
    areas, streams, subprocesses, interfaces, assessments, calibration = run_analysis(data_dir)
    return generate_report(
        areas, streams, subprocesses, interfaces, assessments,
        calibration=calibration,
        data_source=data_source,
        git_commit=git_commit,
    )


def run_single_stream_decision(data_dir: Path, stream_id: str) -> Optional[dict]:
    """Run the pipeline for a single stream and return its decision result as a dict.

    Returns None if the stream has no assessment or no result can be computed.
    """
    areas, streams, subprocesses, interfaces, assessments, _ = run_analysis(data_dir)

    assessment_index = {a.assessed_object_id: a for a in assessments}
    assessment = assessment_index.get(stream_id)
    if not assessment or assessment.result is None:
        return None

    dr = assessment.decision_result
    if dr is None:
        return None

    # Serialize DecisionResult to a clean dict
    result = {
        "stream_id": stream_id,
        "decision": dr.decision.value,
        "decision_rationale": dr.decision_rationale,
        "target_operating_model": dr.target_operating_model.value,
        "blocking_factors": dr.blocking_factors,
        "prerequisites": dr.prerequisites,
        "expected_benefit": dr.expected_benefit,
        "implementation_risk": dr.implementation_risk,
        "interface_complexity": dr.interface_complexity.complexity_score,
        "harmonization_degree": {
            "harmonizable": dr.harmonization_degree.harmonizable,
            "standardizable": dr.harmonization_degree.standardizable,
            "centralizable": dr.harmonization_degree.centralizable,
            "harmonization_degree": dr.harmonization_degree.harmonization_degree,
            "standardization_degree": dr.harmonization_degree.standardization_degree,
            "centralization_degree": dr.harmonization_degree.centralization_degree,
        },
        "score": assessment.result.harmonization_score,
        "classification": assessment.result.classification.value,
    }

    # Optional Phase 5 fields
    if dr.alternative_options:
        result["alternative_options"] = [
            {
                "label": ao.label,
                "description": ao.description,
                "is_recommended": ao.is_recommended,
                "pros": ao.pros,
                "cons": ao.cons,
                "risks": ao.risks,
            }
            for ao in dr.alternative_options
        ]
    if dr.no_action_impact:
        nai = dr.no_action_impact
        result["no_action_impact"] = {
            "regulatory_risk": nai.regulatory_risk.value,
            "operational_risk": nai.operational_risk.value,
            "inefficiency_cost": nai.inefficiency_cost.value,
            "audit_exposure": nai.audit_exposure.value,
            "rationale": nai.rationale,
        }
    if dr.governance:
        result["governance"] = {
            "decision_owner": dr.governance.decision_owner,
            "involved_stakeholders": dr.governance.involved_stakeholders,
            "required_approvals": dr.governance.required_approvals,
            "decision_type": dr.governance.decision_type.value,
        }
    if dr.effort_estimate:
        result["effort_estimate"] = {
            "person_months_bucket": dr.effort_estimate.person_months_bucket,
            "implementation_duration": dr.effort_estimate.implementation_duration.value,
            "cost_category": dr.effort_estimate.cost_category.value,
            "rationale": dr.effort_estimate.rationale,
        }
    if dr.decision_trace:
        dt = dr.decision_trace
        result["decision_trace"] = {
            "input_factors": dt.input_factors,
            "rules_triggered": dt.rules_triggered,
            "constraints_applied": dt.constraints_applied,
            "confidence_basis": dt.confidence_basis,
        }

    # Completeness/confidence
    if assessment.completeness:
        result["completeness_score"] = assessment.completeness.completeness_score
        result["confidence"] = assessment.completeness.confidence_level.value
    if assessment.prioritization_result:
        result["priority"] = assessment.prioritization_result.priority.value
        result["priority_score"] = assessment.prioritization_result.priority_score

    return result


def run_calibration(data_dir: Path) -> Optional[CalibrationResult]:
    """Run calibration only and return the result."""
    _, _, _, _, assessments = load_all_from_directory(data_dir)
    outcomes = load_outcomes_from_directory(data_dir)
    if not outcomes:
        return None
    # Need to evaluate assessments first
    areas, streams, subprocesses, interfaces, assessments, _ = run_analysis(data_dir)
    outcomes = load_outcomes_from_directory(data_dir)
    if not outcomes:
        return None
    return calibrate(assessments, outcomes)

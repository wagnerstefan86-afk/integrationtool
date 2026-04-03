"""Markdown report generator.

Produces a structured Markdown report from the three-tier organizational
model (Area -> Stream -> SubProcess), assessments, harmonization results,
prioritization, and completeness/confidence data.

Includes: Mermaid diagrams, management view, assessment gaps analysis.
"""

from datetime import date

from harmonizer.models.process import Area, Stream, StreamType, SubProcess, ProcessInterface
from typing import Optional

from harmonizer.models.assessment import (
    Assessment,
    AssessedObjectType,
    CalibrationResult,
    ConfidenceLevel,
    Decision,
    HarmonizationClassification,
    HarmonizationPriority,
    ModelMaturityLevel,
    TargetOperatingModel,
    ValueLevel,
)


_CLASSIFICATION_LABELS: dict[HarmonizationClassification, str] = {
    HarmonizationClassification.FULLY_CENTRALIZABLE: "Fully Centralizable",
    HarmonizationClassification.CENTRAL_METHOD_LOCAL_EXECUTION: "Central Method, Local Execution",
    HarmonizationClassification.PARTIALLY_HARMONIZABLE: "Partially Harmonizable",
    HarmonizationClassification.MINIMUM_STANDARD_ONLY: "Minimum Standard Only",
    HarmonizationClassification.CURRENTLY_NOT_HARMONIZABLE: "Currently Not Harmonizable",
}

_PRIORITY_LABELS: dict[HarmonizationPriority, str] = {
    HarmonizationPriority.HIGH: "High",
    HarmonizationPriority.MEDIUM: "Medium",
    HarmonizationPriority.LOW: "Low",
}

_CONFIDENCE_LABELS: dict[ConfidenceLevel, str] = {
    ConfidenceLevel.HIGH: "High",
    ConfidenceLevel.MEDIUM: "Medium",
    ConfidenceLevel.LOW: "Low",
}

_STREAM_TYPE_LABELS: dict[StreamType, str] = {
    StreamType.PROCESS: "Process",
    StreamType.GOVERNANCE_FUNCTION: "Governance Function",
    StreamType.SERVICE_DOMAIN: "Service Domain",
    StreamType.SUPPORT_FUNCTION: "Support Function",
    StreamType.CAPABILITY_DOMAIN: "Capability Domain",
    StreamType.PROGRAM_DOMAIN: "Program Domain",
}

_DECISION_LABELS: dict[Decision, str] = {
    Decision.CENTRALIZE_NOW: "Centralize Now",
    Decision.CENTRALIZE_LATER: "Centralize Later",
    Decision.HARMONIZE_ONLY: "Harmonize Only",
    Decision.STANDARDIZE_ONLY: "Standardize Only",
    Decision.KEEP_LOCAL: "Keep Local",
    Decision.REASSESS_AFTER_DATA_COMPLETION: "Reassess After Data Completion",
}

_TOM_LABELS: dict[TargetOperatingModel, str] = {
    TargetOperatingModel.CENTRALIZED_EXECUTION: "Centralized Execution",
    TargetOperatingModel.CENTRAL_METHOD_LOCAL_EXECUTION: "Central Method, Local Execution",
    TargetOperatingModel.FEDERATED_STANDARDIZED: "Federated Standardized",
    TargetOperatingModel.LOCAL_INDEPENDENT: "Local Independent",
}

_VALUE_LABELS: dict[ValueLevel, str] = {
    ValueLevel.LOW: "Low",
    ValueLevel.MEDIUM: "Medium",
    ValueLevel.HIGH: "High",
}


def _build_indices(
    areas: list[Area],
    streams: list[Stream],
    subprocesses: list[SubProcess],
) -> tuple[
    dict[str, Area],
    dict[str, Stream],
    dict[str, SubProcess],
    dict[str, list[Stream]],
    dict[str, list[SubProcess]],
]:
    area_index = {a.id: a for a in areas}
    stream_index = {s.id: s for s in streams}
    sp_index = {sp.id: sp for sp in subprocesses}
    streams_by_area: dict[str, list[Stream]] = {a.id: [] for a in areas}
    for s in streams:
        if s.area_id in streams_by_area:
            streams_by_area[s.area_id].append(s)
    sps_by_stream: dict[str, list[SubProcess]] = {s.id: [] for s in streams}
    for sp in subprocesses:
        if sp.stream_id in sps_by_stream:
            sps_by_stream[sp.stream_id].append(sp)
    return area_index, stream_index, sp_index, streams_by_area, sps_by_stream


def _resolve_name(
    process_id: str,
    stream_index: dict[str, Stream],
    sp_index: dict[str, SubProcess],
) -> str:
    if process_id in stream_index:
        return stream_index[process_id].name
    if process_id in sp_index:
        return sp_index[process_id].name
    return process_id


def _count_interfaces_for(
    process_id: str,
    interfaces: list[ProcessInterface],
    sp_ids_in_stream: set[str],
) -> int:
    """Count interfaces involving a stream or its subprocesses."""
    relevant_ids = sp_ids_in_stream | {process_id}
    count = 0
    for iface in interfaces:
        if iface.source_process_id in relevant_ids or iface.target_process_id in relevant_ids:
            count += 1
    return count


def generate_mermaid_diagram(
    areas: list[Area],
    streams: list[Stream],
    subprocesses: list[SubProcess],
    interfaces: list[ProcessInterface],
) -> str:
    lines = ["```mermaid", "graph TD"]

    streams_by_area: dict[str, list[Stream]] = {a.id: [] for a in areas}
    for s in streams:
        if s.area_id in streams_by_area:
            streams_by_area[s.area_id].append(s)

    sps_by_stream: dict[str, list[SubProcess]] = {s.id: [] for s in streams}
    for sp in subprocesses:
        if sp.stream_id in sps_by_stream:
            sps_by_stream[sp.stream_id].append(sp)

    for area in areas:
        area_safe = area.id.replace("-", "_")
        lines.append(f"    subgraph {area_safe}[\"{area.name}\"]")
        for stream in streams_by_area.get(area.id, []):
            stream_safe = stream.id.replace("-", "_")
            children = sps_by_stream.get(stream.id, [])
            if children:
                lines.append(f"        subgraph {stream_safe}[\"{stream.name}\"]")
                for sp in children:
                    sp_safe = sp.id.replace("-", "_")
                    lines.append(f"            {sp_safe}[\"{sp.name}\"]")
                lines.append("        end")
            else:
                lines.append(f"        {stream_safe}[\"{stream.name}\"]")
        lines.append("    end")

    for iface in interfaces:
        src = iface.source_process_id.replace("-", "_")
        tgt = iface.target_process_id.replace("-", "_")
        label = iface.interface_type.value
        lines.append(f"    {src} -->|{label}| {tgt}")

    lines.append("```")
    return "\n".join(lines)


def generate_report(
    areas: list[Area],
    streams: list[Stream],
    subprocesses: list[SubProcess],
    interfaces: list[ProcessInterface],
    assessments: list[Assessment],
    calibration: Optional[CalibrationResult] = None,
) -> str:
    area_index, stream_index, sp_index, streams_by_area, sps_by_stream = _build_indices(
        areas, streams, subprocesses
    )
    assessment_index = {a.assessed_object_id: a for a in assessments}

    s: list[str] = []

    # --- Header ---
    s.append("# InfoSec Process Harmonization Report")
    s.append(f"**Generated:** {date.today().isoformat()}")
    s.append("")

    # --- Executive Summary ---
    s.append("## Executive Summary")
    s.append("")
    stream_assessments = [
        a for a in assessments
        if a.result is not None and a.assessed_object_type == AssessedObjectType.STREAM
    ]
    all_assessed = [a for a in assessments if a.result is not None]

    s.append(f"**Streams assessed:** {len(stream_assessments)} / {len(streams)}")
    s.append(f"**Total assessed objects (streams + subprocesses):** {len(all_assessed)}")
    s.append("")

    if stream_assessments:
        by_class: dict[HarmonizationClassification, list[str]] = {}
        for a in stream_assessments:
            cls = a.result.classification
            name = _resolve_name(a.assessed_object_id, stream_index, sp_index)
            by_class.setdefault(cls, []).append(name)

        s.append("| Classification | Count | Streams |")
        s.append("|---|---|---|")
        for cls in HarmonizationClassification:
            names = by_class.get(cls, [])
            if names:
                label = _CLASSIFICATION_LABELS[cls]
                s.append(f"| {label} | {len(names)} | {', '.join(names)} |")
        s.append("")

    # Confidence overview
    with_completeness = [a for a in stream_assessments if a.completeness is not None]
    if with_completeness:
        low_conf = [
            a for a in with_completeness
            if a.completeness.confidence_level == ConfidenceLevel.LOW
        ]
        if low_conf:
            names = [_resolve_name(a.assessed_object_id, stream_index, sp_index) for a in low_conf]
            s.append(f"**Low confidence assessments ({len(low_conf)}):** {', '.join(names)}")
            s.append("")

    # --- Area Overview ---
    s.append("## Area Overview")
    s.append("")
    s.append("| Area | Streams | Subprocesses | Stream Types |")
    s.append("|---|---|---|---|")
    for area in areas:
        area_streams = streams_by_area.get(area.id, [])
        sp_count = sum(len(sps_by_stream.get(st.id, [])) for st in area_streams)
        type_counts: dict[str, int] = {}
        for st in area_streams:
            label = _STREAM_TYPE_LABELS.get(st.stream_type, st.stream_type.value)
            type_counts[label] = type_counts.get(label, 0) + 1
        types_str = ", ".join(f"{k} ({v})" for k, v in sorted(type_counts.items()))
        s.append(f"| {area.name} | {len(area_streams)} | {sp_count} | {types_str} |")
    s.append("")

    # --- Process Overview Diagram ---
    s.append("## Process Overview")
    s.append("")
    s.append(generate_mermaid_diagram(areas, streams, subprocesses, interfaces))
    s.append("")

    # --- Detailed Results per Area / Stream ---
    for area in areas:
        s.append(f"## Area: {area.name}")
        s.append("")
        if area.description:
            s.append(f"{area.description.strip()}")
            s.append("")

        for stream in streams_by_area.get(area.id, []):
            type_label = _STREAM_TYPE_LABELS.get(stream.stream_type, stream.stream_type.value)
            stream_sps = sps_by_stream.get(stream.id, [])
            sp_ids_in_stream = {sp.id for sp in stream_sps}
            iface_count = _count_interfaces_for(stream.id, interfaces, sp_ids_in_stream)

            s.append(f"### Stream: {stream.name}")
            s.append("")
            s.append(f"- **ID:** `{stream.id}`")
            s.append(f"- **Type:** {type_label}")
            s.append(f"- **Owner:** {stream.owner_role}")
            s.append(f"- **Country Scope:** {stream.country_scope.value}")
            s.append(f"- **Tenant Scope:** {stream.tenant_scope.value}")
            s.append(f"- **Subprocesses:** {len(stream_sps)}")
            s.append(f"- **Interfaces:** {iface_count}")
            if stream.regulatory_context:
                s.append(f"- **Regulatory Context:** {', '.join(stream.regulatory_context)}")
            if stream.notes:
                s.append(f"- **Notes:** {stream.notes.strip()}")
            s.append("")

            # Stream-level assessment
            stream_assessment = assessment_index.get(stream.id)
            if stream_assessment and stream_assessment.result:
                r = stream_assessment.result
                label = _CLASSIFICATION_LABELS[r.classification]

                # Confidence badge
                conf_str = ""
                if stream_assessment.completeness:
                    c = stream_assessment.completeness
                    conf_label = _CONFIDENCE_LABELS[c.confidence_level]
                    conf_str = f" | Confidence: {conf_label} ({c.completeness_score}%)"

                s.append(f"**Assessment: {label}** (Score: {r.harmonization_score:.2f}{conf_str})")
                s.append("")
                s.append("| Dimension | Score | Rationale |")
                s.append("|---|---|---|")
                for ans in stream_assessment.answers:
                    s.append(
                        f"| {ans.dimension.value} | {ans.score}/5 | {ans.rationale.strip()} |"
                    )
                s.append("")

                # Type-specific answers
                if stream_assessment.type_specific_answers:
                    s.append("**Type-Specific Assessment:**")
                    s.append("")
                    s.append("| Question | Score | Rationale |")
                    s.append("|---|---|---|")
                    for tsa in stream_assessment.type_specific_answers:
                        s.append(f"| {tsa.question_id} | {tsa.score}/5 | {tsa.rationale.strip()} |")
                    s.append("")

                if stream_assessment.hard_constraints:
                    s.append("**Hard Constraints:**")
                    for hc in stream_assessment.hard_constraints:
                        s.append(f"- {hc.value}")
                    s.append("")

                s.append(f"**Recommendation:** {r.recommendation}")
                s.append("")

                if stream_assessment.prioritization_result:
                    pr = stream_assessment.prioritization_result
                    pri_label = _PRIORITY_LABELS.get(pr.priority, pr.priority.value)
                    s.append(f"**Harmonization Priority: {pri_label}** (Score: {pr.priority_score:.2f})")
                    s.append(f"  {pr.rationale}")
                    s.append("")

                # Decision Engine output
                if stream_assessment.decision_result:
                    dr = stream_assessment.decision_result
                    dec_label = _DECISION_LABELS.get(dr.decision, dr.decision.value)
                    tom_label = _TOM_LABELS.get(dr.target_operating_model, dr.target_operating_model.value)

                    s.append(f"**Decision: {dec_label}**")
                    s.append(f"  {dr.decision_rationale}")
                    s.append("")
                    s.append(f"**Target Operating Model:** {tom_label}")
                    s.append("")

                    # H/S/C Breakdown
                    hsc = dr.harmonization_degree
                    s.append("**Harmonization / Standardization / Centralization:**")
                    s.append("")
                    s.append("| Dimension | Feasible | Degree |")
                    s.append("|---|---|---|")
                    s.append(f"| Harmonizable | {'Yes' if hsc.harmonizable else 'No'} | {hsc.harmonization_degree:.2f} |")
                    s.append(f"| Standardizable | {'Yes' if hsc.standardizable else 'No'} | {hsc.standardization_degree:.2f} |")
                    s.append(f"| Centralizable | {'Yes' if hsc.centralizable else 'No'} | {hsc.centralization_degree:.2f} |")
                    s.append("")

                    # Interface Complexity
                    ic = dr.interface_complexity
                    s.append(f"**Interface Complexity:** {ic.complexity_score:.2f}")
                    s.append(f"  {ic.rationale}")
                    s.append("")

                    # Value Indicators
                    vi = dr.value_indicators
                    s.append("**Value Indicators:**")
                    s.append(f"  Business Value: {_VALUE_LABELS[vi.expected_business_value]} | "
                             f"Regulatory Pressure: {_VALUE_LABELS[vi.regulatory_pressure]} | "
                             f"Operational Impact: {_VALUE_LABELS[vi.operational_impact]}")
                    s.append("")

                    if dr.blocking_factors:
                        s.append("**Blocking Factors:**")
                        for bf in dr.blocking_factors:
                            s.append(f"- {bf}")
                        s.append("")

                    if dr.prerequisites:
                        s.append("**Prerequisites:**")
                        for p in dr.prerequisites:
                            s.append(f"- {p}")
                        s.append("")

                    s.append(f"**Expected Benefit:** {dr.expected_benefit}")
                    s.append(f"**Implementation Risk:** {dr.implementation_risk}")
                    s.append("")

                    # Alternative Options
                    if dr.alternative_options:
                        s.append("**Decision Alternatives:**")
                        s.append("")
                        for opt in dr.alternative_options:
                            rec = " *(recommended)*" if opt.is_recommended else ""
                            s.append(f"- **{opt.label}**{rec}: {opt.description}")
                            if opt.pros:
                                s.append(f"  - Pros: {'; '.join(opt.pros)}")
                            if opt.cons:
                                s.append(f"  - Cons: {'; '.join(opt.cons)}")
                            if opt.risks:
                                s.append(f"  - Risks: {'; '.join(opt.risks)}")
                        s.append("")

                    # No-Action Impact
                    if dr.no_action_impact:
                        nai = dr.no_action_impact
                        s.append("**If We Do Nothing:**")
                        s.append("")
                        s.append("| Risk Category | Level |")
                        s.append("|---|---|")
                        s.append(f"| Regulatory Risk | {_VALUE_LABELS[nai.regulatory_risk]} |")
                        s.append(f"| Operational Risk | {_VALUE_LABELS[nai.operational_risk]} |")
                        s.append(f"| Inefficiency Cost | {_VALUE_LABELS[nai.inefficiency_cost]} |")
                        s.append(f"| Audit Exposure | {_VALUE_LABELS[nai.audit_exposure]} |")
                        s.append("")
                        s.append(f"  {nai.rationale}")
                        s.append("")

                    # Implementation Impact
                    if dr.implementation_impact:
                        imp = dr.implementation_impact
                        s.append(f"**Implementation Complexity:** {_VALUE_LABELS[imp.implementation_complexity]}")
                        s.append(f"**Change Magnitude:** {_VALUE_LABELS[imp.change_magnitude]}")
                        s.append("")
                        changes = []
                        if imp.process_changes:
                            changes.append(("Processes", imp.process_changes))
                        if imp.role_changes:
                            changes.append(("Roles", imp.role_changes))
                        if imp.tool_changes:
                            changes.append(("Tools", imp.tool_changes))
                        if imp.governance_changes:
                            changes.append(("Governance", imp.governance_changes))
                        if changes:
                            s.append("**Required Changes:**")
                            s.append("")
                            for category, items in changes:
                                s.append(f"- **{category}:** {'; '.join(items)}")
                            s.append("")
                        if imp.affected_roles:
                            s.append(f"**Affected Roles:** {', '.join(imp.affected_roles)}")
                            s.append("")

                    # Effort Estimate
                    if dr.effort_estimate:
                        eff = dr.effort_estimate
                        s.append(
                            f"**Effort Estimate:** ~{eff.person_months_bucket} PM | "
                            f"Duration: {eff.implementation_duration.value} | "
                            f"Cost: {_VALUE_LABELS[eff.cost_category]}"
                        )
                        s.append(f"  {eff.rationale}")
                        s.append("")

                    # Governance
                    if dr.governance:
                        gov = dr.governance
                        s.append(f"**Decision Owner:** {gov.decision_owner}")
                        s.append(f"**Decision Type:** {gov.decision_type.value}")
                        if gov.involved_stakeholders:
                            s.append(f"**Stakeholders:** {', '.join(gov.involved_stakeholders)}")
                        if gov.required_approvals:
                            s.append(f"**Required Approvals:** {', '.join(gov.required_approvals)}")
                        s.append("")

            else:
                s.append("**Assessment: Not yet assessed**")
                s.append("")

            # Subprocess details
            for sp in stream_sps:
                s.append(f"#### Subprocess: {sp.name}")
                s.append("")
                s.append(f"- **ID:** `{sp.id}`")
                s.append(f"- **Purpose:** {sp.purpose}")
                s.append(f"- **Country Scope:** {sp.country_scope.value}")
                s.append(f"- **Tenant Scope:** {sp.tenant_scope.value}")
                if sp.interfaces_with:
                    iface_names = [
                        _resolve_name(pid, stream_index, sp_index) for pid in sp.interfaces_with
                    ]
                    s.append(f"- **Interfaces with:** {', '.join(iface_names)}")
                s.append("")

                sp_assessment = assessment_index.get(sp.id)
                if sp_assessment and sp_assessment.result:
                    r = sp_assessment.result
                    label = _CLASSIFICATION_LABELS[r.classification]

                    conf_str = ""
                    if sp_assessment.completeness:
                        c = sp_assessment.completeness
                        conf_label = _CONFIDENCE_LABELS[c.confidence_level]
                        conf_str = f" | Confidence: {conf_label} ({c.completeness_score}%)"

                    s.append(f"**Assessment: {label}** (Score: {r.harmonization_score:.2f}{conf_str})")
                    s.append("")
                    s.append("| Dimension | Score | Rationale |")
                    s.append("|---|---|---|")
                    for ans in sp_assessment.answers:
                        s.append(
                            f"| {ans.dimension.value} | {ans.score}/5 | {ans.rationale.strip()} |"
                        )
                    s.append("")

                    if sp_assessment.hard_constraints:
                        s.append("**Hard Constraints:**")
                        for hc in sp_assessment.hard_constraints:
                            s.append(f"- {hc.value}")
                        s.append("")

                    s.append(f"**Recommendation:** {r.recommendation}")
                    s.append("")
                else:
                    s.append("*Not yet assessed*")
                    s.append("")

    # --- Process Interfaces ---
    if interfaces:
        s.append("## Process Interfaces")
        s.append("")
        s.append("| ID | Source | Target | Type | Description |")
        s.append("|---|---|---|---|---|")
        for iface in interfaces:
            src_name = _resolve_name(iface.source_process_id, stream_index, sp_index)
            tgt_name = _resolve_name(iface.target_process_id, stream_index, sp_index)
            s.append(
                f"| `{iface.id}` | {src_name} | {tgt_name} "
                f"| {iface.interface_type.value} | {iface.description.strip()} |"
            )
        s.append("")

    # --- Management View ---
    prioritized = [
        a for a in assessments
        if a.prioritization_result is not None and a.result is not None
    ]
    if prioritized:
        prioritized.sort(key=lambda a: a.prioritization_result.priority_score, reverse=True)

        s.append("## Management View: Harmonization Roadmap")
        s.append("")
        s.append("Streams ranked by harmonization priority, with confidence indicators.")
        s.append("")
        s.append("| Priority | Stream | Type | Classification | Score | Confidence | Priority Score |")
        s.append("|---|---|---|---|---|---|---|")
        for a in prioritized:
            name = _resolve_name(a.assessed_object_id, stream_index, sp_index)
            stream_obj = stream_index.get(a.assessed_object_id)
            type_label = _STREAM_TYPE_LABELS.get(stream_obj.stream_type, "") if stream_obj else ""
            cls_label = _CLASSIFICATION_LABELS[a.result.classification]
            pri_label = _PRIORITY_LABELS.get(
                a.prioritization_result.priority,
                a.prioritization_result.priority.value,
            )
            conf_str = "N/A"
            if a.completeness:
                conf_label = _CONFIDENCE_LABELS[a.completeness.confidence_level]
                conf_str = f"{conf_label} ({a.completeness.completeness_score}%)"
            s.append(
                f"| **{pri_label}** | {name} | {type_label} | {cls_label} "
                f"| {a.result.harmonization_score:.2f} "
                f"| {conf_str} "
                f"| {a.prioritization_result.priority_score:.2f} |"
            )
        s.append("")

        high_pri = [a for a in prioritized if a.prioritization_result.priority == HarmonizationPriority.HIGH]
        if high_pri:
            # Only recommend those with at least medium confidence
            reliable_high = [
                a for a in high_pri
                if not a.completeness or a.completeness.confidence_level != ConfidenceLevel.LOW
            ]
            if reliable_high:
                s.append("### Recommended First Movers")
                s.append("")
                s.append("The following streams should be prioritized for harmonization")
                s.append("(filtered for medium or high confidence):")
                s.append("")
                for a in reliable_high:
                    name = _resolve_name(a.assessed_object_id, stream_index, sp_index)
                    s.append(f"1. **{name}** -- {a.result.recommendation}")
                s.append("")

    # --- Decision Overview ---
    decided = [
        a for a in assessments
        if a.decision_result is not None and a.assessed_object_type == AssessedObjectType.STREAM
    ]
    if decided:
        s.append("## Decision Overview")
        s.append("")
        s.append("| Stream | Decision | Operating Model | H | S | C | Interface Complexity |")
        s.append("|---|---|---|---|---|---|---|")
        for a in decided:
            name = _resolve_name(a.assessed_object_id, stream_index, sp_index)
            dr = a.decision_result
            dec_label = _DECISION_LABELS.get(dr.decision, dr.decision.value)
            tom_label = _TOM_LABELS.get(dr.target_operating_model, dr.target_operating_model.value)
            hsc = dr.harmonization_degree
            s.append(
                f"| {name} | {dec_label} | {tom_label} "
                f"| {hsc.harmonization_degree:.2f} "
                f"| {hsc.standardization_degree:.2f} "
                f"| {hsc.centralization_degree:.2f} "
                f"| {dr.interface_complexity.complexity_score:.2f} |"
            )
        s.append("")

    # --- Why NOT Centralized? ---
    not_centralized = [
        a for a in decided
        if a.decision_result.decision not in (Decision.CENTRALIZE_NOW, Decision.CENTRALIZE_LATER)
        and a.decision_result.decision != Decision.REASSESS_AFTER_DATA_COMPLETION
    ]
    if not_centralized:
        s.append("## Why NOT Centralized?")
        s.append("")
        s.append("This section explains why streams are not recommended for centralization.")
        s.append("")
        for a in not_centralized:
            name = _resolve_name(a.assessed_object_id, stream_index, sp_index)
            dr = a.decision_result
            dec_label = _DECISION_LABELS.get(dr.decision, dr.decision.value)
            hsc = dr.harmonization_degree
            s.append(f"### {name} → {dec_label}")
            s.append("")
            reasons = []
            if not hsc.centralizable:
                reasons.append(
                    f"Centralization degree too low ({hsc.centralization_degree:.2f} < 0.50)"
                )
            if dr.interface_complexity.complexity_score >= 0.5:
                reasons.append(
                    f"High interface complexity ({dr.interface_complexity.complexity_score:.2f})"
                )
            for bf in dr.blocking_factors:
                if "Hard constraint" in bf:
                    reasons.append(bf)
            if not reasons:
                reasons.append(
                    "Alignment scores insufficient for centralization "
                    f"(harmonization score: {a.result.harmonization_score:.2f})"
                )
            for reason in reasons:
                s.append(f"- {reason}")
            s.append("")

    # --- If We Do Nothing (Global Summary) ---
    with_no_action = [
        a for a in decided
        if a.decision_result.no_action_impact is not None
    ] if decided else []
    if with_no_action:
        s.append("## If We Do Nothing — Inaction Risk Summary")
        s.append("")
        s.append("| Stream | Regulatory Risk | Operational Risk | Inefficiency Cost | Audit Exposure |")
        s.append("|---|---|---|---|---|")
        for a in with_no_action:
            name = _resolve_name(a.assessed_object_id, stream_index, sp_index)
            nai = a.decision_result.no_action_impact
            s.append(
                f"| {name} "
                f"| {_VALUE_LABELS[nai.regulatory_risk]} "
                f"| {_VALUE_LABELS[nai.operational_risk]} "
                f"| {_VALUE_LABELS[nai.inefficiency_cost]} "
                f"| {_VALUE_LABELS[nai.audit_exposure]} |"
            )
        s.append("")
        # Highlight high-risk streams
        high_risk = [
            a for a in with_no_action
            if a.decision_result.no_action_impact.regulatory_risk == ValueLevel.HIGH
            or a.decision_result.no_action_impact.audit_exposure == ValueLevel.HIGH
        ]
        if high_risk:
            s.append("**Streams with high inaction risk:**")
            for a in high_risk:
                name = _resolve_name(a.assessed_object_id, stream_index, sp_index)
                s.append(f"- {name}: {a.decision_result.no_action_impact.rationale}")
            s.append("")

    # --- Governance & Ownership ---
    with_governance = [
        a for a in decided
        if a.decision_result.governance is not None
    ] if decided else []
    if with_governance:
        s.append("## Governance & Ownership")
        s.append("")
        s.append("| Stream | Decision Type | Decision Owner | Required Approvals |")
        s.append("|---|---|---|---|")
        for a in with_governance:
            name = _resolve_name(a.assessed_object_id, stream_index, sp_index)
            gov = a.decision_result.governance
            approvals = ", ".join(gov.required_approvals) if gov.required_approvals else "None"
            s.append(
                f"| {name} | {gov.decision_type.value} "
                f"| {gov.decision_owner} "
                f"| {approvals} |"
            )
        s.append("")

    # --- Audit Trace Summary ---
    with_trace = [
        a for a in decided
        if a.decision_result.decision_trace is not None
    ] if decided else []
    if with_trace:
        s.append("## Audit Trace Summary")
        s.append("")
        s.append("Each decision is fully traceable. Key rule triggers per stream:")
        s.append("")
        for a in with_trace:
            name = _resolve_name(a.assessed_object_id, stream_index, sp_index)
            trace = a.decision_result.decision_trace
            dec_label = _DECISION_LABELS.get(a.decision_result.decision, a.decision_result.decision.value)
            s.append(f"**{name}** → {dec_label}")
            if trace.rules_triggered:
                for rule in trace.rules_triggered:
                    s.append(f"- {rule}")
            if trace.constraints_applied:
                s.append(f"- Constraints: {', '.join(trace.constraints_applied)}")
            s.append(f"- {trace.confidence_basis}")
            s.append("")

    # --- Assessment Gaps ---
    s.append("## Assessment Gaps / Required Next Inputs")
    s.append("")
    s.append("This section identifies streams where additional data is needed")
    s.append("for a reliable harmonization assessment.")
    s.append("")

    has_gaps = False
    for stream in streams:
        stream_assessment = assessment_index.get(stream.id)
        stream_sps = sps_by_stream.get(stream.id, [])

        gaps: list[str] = []

        if not stream_assessment:
            gaps.append("Stream-level assessment missing entirely")
        elif stream_assessment.completeness and stream_assessment.completeness.missing_items:
            gaps.extend(stream_assessment.completeness.missing_items)

        # Check subprocess coverage
        sp_assessed = sum(1 for sp in stream_sps if sp.id in assessment_index)
        if stream_sps and sp_assessed == 0:
            gaps.append(f"None of {len(stream_sps)} subprocesses assessed")
        elif stream_sps and sp_assessed < len(stream_sps):
            unassessed = [sp.name for sp in stream_sps if sp.id not in assessment_index]
            gaps.append(f"Unassessed subprocesses: {', '.join(unassessed)}")

        if gaps:
            has_gaps = True
            conf_str = ""
            if stream_assessment and stream_assessment.completeness:
                c = stream_assessment.completeness
                conf_label = _CONFIDENCE_LABELS[c.confidence_level]
                conf_str = f" (Confidence: {conf_label}, {c.completeness_score}%)"
            s.append(f"### {stream.name}{conf_str}")
            s.append("")
            for gap in gaps:
                s.append(f"- {gap}")
            s.append("")

    if not has_gaps:
        s.append("No significant assessment gaps identified.")
        s.append("")

    # --- Calibration & Model Accuracy ---
    if calibration and calibration.outcomes_analyzed > 0:
        _MATURITY_LABELS = {
            ModelMaturityLevel.INITIAL: "Initial (no outcome data)",
            ModelMaturityLevel.LEARNING: "Learning (1-4 outcomes)",
            ModelMaturityLevel.CALIBRATED: "Calibrated (5-9 outcomes)",
            ModelMaturityLevel.STABLE: "Stable (10+ outcomes)",
        }

        s.append("## Decision Accuracy & Calibration")
        s.append("")
        s.append(
            f"**Model Maturity:** "
            f"{_MATURITY_LABELS.get(calibration.model_maturity, calibration.model_maturity.value)}"
        )

        # Trust Score
        if calibration.trust_score:
            ts = calibration.trust_score
            s.append(f"**Trust Score:** {ts.trust_score:.2f}")
            s.append(f"  {ts.rationale}")
            s.append("")

        s.append(
            f"**Prediction Accuracy (filtered):** {calibration.accuracy_rate:.0%} "
            f"({calibration.outcomes_analyzed} outcome(s) analyzed)"
        )
        if calibration.confidence_adjustment != 0.0:
            direction = "boost" if calibration.confidence_adjustment > 0 else "penalty"
            s.append(
                f"**Confidence Adjustment:** {calibration.confidence_adjustment:+.2f} "
                f"({direction} based on historical accuracy)"
            )
        s.append("")

        # Filtered vs Unfiltered
        if calibration.filtered_stats:
            fs = calibration.filtered_stats
            s.append("### Filtered vs Unfiltered Calibration")
            s.append("")
            s.append("| Metric | Value |")
            s.append("|---|---|")
            s.append(f"| Total outcomes | {fs.total_outcomes} |")
            s.append(f"| Learning-relevant outcomes | {fs.learning_relevant_outcomes} |")
            s.append(f"| Excluded (political/strategic) | {fs.excluded_outcomes} |")
            s.append(f"| Unfiltered accuracy | {fs.unfiltered_accuracy:.0%} |")
            s.append(f"| Filtered accuracy | {fs.filtered_accuracy:.0%} |")
            s.append("")
            if fs.excluded_reasons:
                s.append("**Excluded outcomes:**")
                for reason in fs.excluded_reasons:
                    s.append(f"- {reason}")
                s.append("")

        # Why decisions deviated
        if calibration.deviation_reasons_summary:
            s.append("### Why Decisions Deviated")
            s.append("")
            for reason_line in calibration.deviation_reasons_summary:
                s.append(f"- {reason_line}")
            s.append("")

        # Deviation summary table
        if calibration.deviations:
            s.append("### Prediction vs Actual")
            s.append("")
            s.append("| Dimension | Predicted | Actual | Direction |")
            s.append("|---|---|---|---|")
            for dev in calibration.deviations:
                s.append(
                    f"| {dev.dimension} | {dev.predicted} | {dev.actual} | {dev.direction} |"
                )
            s.append("")

        # Systematic biases (model vs reality gap)
        if calibration.systematic_biases:
            s.append("### Model vs Reality Gap")
            s.append("")
            s.append("Systematic biases detected from learning-relevant outcomes only "
                     "(political/strategic overrides excluded):")
            s.append("")
            for bias in calibration.systematic_biases:
                s.append(f"- {bias}")
            s.append("")

        # Adjustment suggestions
        if calibration.suggestions:
            s.append("### Improvement Suggestions")
            s.append("")
            s.append("| Priority | Area | Suggestion |")
            s.append("|---|---|---|")
            for sug in calibration.suggestions:
                s.append(
                    f"| {_VALUE_LABELS[sug.priority]} | {sug.area} | {sug.suggestion} |"
                )
            s.append("")

        # Protected rules
        if calibration.protected_rules:
            s.append("### Protected Rules (Not Subject to Calibration)")
            s.append("")
            s.append("The following rules are governance-mandated and will not be "
                     "weakened regardless of calibration findings:")
            s.append("")
            s.append("| Rule | Description | Reason |")
            s.append("|---|---|---|")
            for rule in calibration.protected_rules:
                s.append(f"| {rule.rule_id} | {rule.description} | {rule.reason} |")
            s.append("")

    # --- Footer ---
    s.append("---")
    s.append("*Report generated by harmonizer v0.7.0*")

    return "\n".join(s)

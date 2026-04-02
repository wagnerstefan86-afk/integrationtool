"""Markdown report generator.

Produces a structured Markdown report from the three-tier organizational
model (Area -> Stream -> SubProcess), assessments, harmonization results,
and prioritization. Includes Mermaid diagrams and a management view.
"""

from datetime import date

from harmonizer.models.process import Area, Stream, StreamType, SubProcess, ProcessInterface
from harmonizer.models.assessment import (
    Assessment,
    HarmonizationClassification,
    HarmonizationPriority,
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

_STREAM_TYPE_LABELS: dict[StreamType, str] = {
    StreamType.PROCESS: "Process",
    StreamType.GOVERNANCE_FUNCTION: "Governance Function",
    StreamType.SERVICE_DOMAIN: "Service Domain",
    StreamType.SUPPORT_FUNCTION: "Support Function",
    StreamType.CAPABILITY_DOMAIN: "Capability Domain",
    StreamType.PROGRAM_DOMAIN: "Program Domain",
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


def generate_mermaid_diagram(
    areas: list[Area],
    streams: list[Stream],
    subprocesses: list[SubProcess],
    interfaces: list[ProcessInterface],
) -> str:
    """Generate a Mermaid flowchart showing the three-tier hierarchy and interfaces."""
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
) -> str:
    """Generate the full Markdown harmonization report."""
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
    assessed = [a for a in assessments if a.result is not None]
    if assessed:
        by_class: dict[HarmonizationClassification, list[str]] = {}
        for a in assessed:
            cls = a.result.classification
            name = _resolve_name(a.assessed_object_id, stream_index, sp_index)
            by_class.setdefault(cls, []).append(name)

        s.append(f"**Total assessed objects:** {len(assessed)}")
        s.append("")
        s.append("| Classification | Count | Streams / Subprocesses |")
        s.append("|---|---|---|")
        for cls in HarmonizationClassification:
            names = by_class.get(cls, [])
            if names:
                label = _CLASSIFICATION_LABELS[cls]
                s.append(f"| {label} | {len(names)} | {', '.join(names)} |")
        s.append("")

    # --- Area Overview ---
    s.append("## Area Overview")
    s.append("")
    s.append("| Area | Streams | Stream Types |")
    s.append("|---|---|---|")
    for area in areas:
        area_streams = streams_by_area.get(area.id, [])
        type_counts: dict[str, int] = {}
        for st in area_streams:
            label = _STREAM_TYPE_LABELS.get(st.stream_type, st.stream_type.value)
            type_counts[label] = type_counts.get(label, 0) + 1
        types_str = ", ".join(f"{k} ({v})" for k, v in sorted(type_counts.items()))
        s.append(f"| {area.name} | {len(area_streams)} | {types_str} |")
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
            s.append(f"### Stream: {stream.name}")
            s.append("")
            s.append(f"- **ID:** `{stream.id}`")
            s.append(f"- **Type:** {type_label}")
            s.append(f"- **Owner:** {stream.owner_role}")
            s.append(f"- **Country Scope:** {stream.country_scope.value}")
            s.append(f"- **Tenant Scope:** {stream.tenant_scope.value}")
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
                s.append(f"**Assessment: {label}** (Score: {r.harmonization_score:.2f})")
                s.append("")
                s.append("| Dimension | Score | Rationale |")
                s.append("|---|---|---|")
                for ans in stream_assessment.answers:
                    s.append(
                        f"| {ans.dimension.value} | {ans.score}/5 | {ans.rationale.strip()} |"
                    )
                s.append("")

                if stream_assessment.hard_constraints:
                    s.append("**Hard Constraints:**")
                    for hc in stream_assessment.hard_constraints:
                        s.append(f"- {hc.value}")
                    s.append("")

                s.append(f"**Recommendation:** {r.recommendation}")
                s.append("")

                # Prioritization
                if stream_assessment.prioritization_result:
                    pr = stream_assessment.prioritization_result
                    pri_label = _PRIORITY_LABELS.get(pr.priority, pr.priority.value)
                    s.append(f"**Harmonization Priority: {pri_label}** (Score: {pr.priority_score:.2f})")
                    s.append(f"  {pr.rationale}")
                    s.append("")

            # Subprocess details
            for sp in sps_by_stream.get(stream.id, []):
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
                    s.append(f"**Assessment: {label}** (Score: {r.harmonization_score:.2f})")
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

    # --- Management View: Harmonization Prioritization ---
    prioritized = [
        a for a in assessments
        if a.prioritization_result is not None and a.result is not None
    ]
    if prioritized:
        # Sort by priority score descending
        prioritized.sort(key=lambda a: a.prioritization_result.priority_score, reverse=True)

        s.append("## Management View: Harmonization Roadmap")
        s.append("")
        s.append("Streams and subprocesses ranked by harmonization priority.")
        s.append("High-priority items offer the best combination of harmonization potential,")
        s.append("operational relevance, and governance benefit relative to effort and dependencies.")
        s.append("")
        s.append("| Priority | Stream / Subprocess | Classification | Score | Priority Score |")
        s.append("|---|---|---|---|---|")
        for a in prioritized:
            name = _resolve_name(a.assessed_object_id, stream_index, sp_index)
            cls_label = _CLASSIFICATION_LABELS[a.result.classification]
            pri_label = _PRIORITY_LABELS.get(
                a.prioritization_result.priority,
                a.prioritization_result.priority.value,
            )
            s.append(
                f"| **{pri_label}** | {name} | {cls_label} "
                f"| {a.result.harmonization_score:.2f} "
                f"| {a.prioritization_result.priority_score:.2f} |"
            )
        s.append("")

        # Top recommendations
        high_pri = [a for a in prioritized if a.prioritization_result.priority == HarmonizationPriority.HIGH]
        if high_pri:
            s.append("### Recommended First Movers")
            s.append("")
            s.append("The following streams should be prioritized for harmonization:")
            s.append("")
            for a in high_pri:
                name = _resolve_name(a.assessed_object_id, stream_index, sp_index)
                s.append(f"1. **{name}** -- {a.result.recommendation}")
            s.append("")

    # --- Footer ---
    s.append("---")
    s.append("*Report generated by harmonizer v0.2.0*")

    return "\n".join(s)

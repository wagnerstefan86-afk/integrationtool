"""Markdown report generator.

Produces a structured Markdown report from process definitions,
assessments, and computed harmonization results. Includes a
Mermaid diagram of process relationships.
"""

from datetime import date

from harmonizer.models.process import MainProcess, SubProcess, ProcessInterface
from harmonizer.models.assessment import Assessment, HarmonizationClassification


# Emoji-free classification labels for enterprise readability
_CLASSIFICATION_LABELS: dict[HarmonizationClassification, str] = {
    HarmonizationClassification.FULLY_CENTRALIZABLE: "Fully Centralizable",
    HarmonizationClassification.CENTRAL_METHOD_LOCAL_EXECUTION: "Central Method, Local Execution",
    HarmonizationClassification.PARTIALLY_HARMONIZABLE: "Partially Harmonizable",
    HarmonizationClassification.MINIMUM_STANDARD_ONLY: "Minimum Standard Only",
    HarmonizationClassification.CURRENTLY_NOT_HARMONIZABLE: "Currently Not Harmonizable",
}


def _build_index(
    main_processes: list[MainProcess],
    subprocesses: list[SubProcess],
) -> tuple[dict[str, MainProcess], dict[str, SubProcess], dict[str, list[SubProcess]]]:
    """Build lookup indices for report generation."""
    mp_index = {mp.id: mp for mp in main_processes}
    sp_index = {sp.id: sp for sp in subprocesses}
    children: dict[str, list[SubProcess]] = {mp.id: [] for mp in main_processes}
    for sp in subprocesses:
        if sp.main_process_id in children:
            children[sp.main_process_id].append(sp)
    return mp_index, sp_index, children


def _resolve_name(
    process_id: str,
    mp_index: dict[str, MainProcess],
    sp_index: dict[str, SubProcess],
) -> str:
    """Resolve a process ID to its display name."""
    if process_id in mp_index:
        return mp_index[process_id].name
    if process_id in sp_index:
        return sp_index[process_id].name
    return process_id


def generate_mermaid_diagram(
    main_processes: list[MainProcess],
    subprocesses: list[SubProcess],
    interfaces: list[ProcessInterface],
) -> str:
    """Generate a Mermaid flowchart showing process hierarchy and interfaces."""
    lines = ["```mermaid", "graph TD"]

    for mp in main_processes:
        safe_id = mp.id.replace("-", "_")
        lines.append(f"    subgraph {safe_id}[\"{mp.name}\"]")
        children = [sp for sp in subprocesses if sp.main_process_id == mp.id]
        for sp in children:
            sp_safe = sp.id.replace("-", "_")
            lines.append(f"        {sp_safe}[\"{sp.name}\"]")
        lines.append("    end")

    for iface in interfaces:
        src = iface.source_process_id.replace("-", "_")
        tgt = iface.target_process_id.replace("-", "_")
        label = iface.interface_type.value
        lines.append(f"    {src} -->|{label}| {tgt}")

    lines.append("```")
    return "\n".join(lines)


def generate_report(
    main_processes: list[MainProcess],
    subprocesses: list[SubProcess],
    interfaces: list[ProcessInterface],
    assessments: list[Assessment],
) -> str:
    """Generate the full Markdown harmonization report."""
    mp_index, sp_index, children = _build_index(main_processes, subprocesses)
    assessment_index = {a.assessed_object_id: a for a in assessments}

    sections: list[str] = []

    # --- Header ---
    sections.append(f"# InfoSec Process Harmonization Report")
    sections.append(f"**Generated:** {date.today().isoformat()}")
    sections.append("")

    # --- Executive Summary ---
    sections.append("## Executive Summary")
    sections.append("")
    assessed = [a for a in assessments if a.result is not None]
    if assessed:
        by_class: dict[HarmonizationClassification, list[str]] = {}
        for a in assessed:
            cls = a.result.classification
            name = _resolve_name(a.assessed_object_id, mp_index, sp_index)
            by_class.setdefault(cls, []).append(name)

        sections.append(f"**Total assessed processes:** {len(assessed)}")
        sections.append("")
        sections.append("| Classification | Count | Processes |")
        sections.append("|---|---|---|")
        for cls in HarmonizationClassification:
            names = by_class.get(cls, [])
            if names:
                label = _CLASSIFICATION_LABELS[cls]
                sections.append(f"| {label} | {len(names)} | {', '.join(names)} |")
        sections.append("")
    else:
        sections.append("No assessments with computed results found.")
        sections.append("")

    # --- Process Overview Diagram ---
    sections.append("## Process Overview")
    sections.append("")
    sections.append(generate_mermaid_diagram(main_processes, subprocesses, interfaces))
    sections.append("")

    # --- Detailed Results per Stream ---
    for mp in main_processes:
        sections.append(f"## Stream: {mp.name}")
        sections.append("")
        sections.append(f"- **ID:** `{mp.id}`")
        sections.append(f"- **Owner:** {mp.owner_role}")
        sections.append(f"- **Country Scope:** {mp.country_scope.value}")
        sections.append(f"- **Tenant Scope:** {mp.tenant_scope.value}")
        if mp.regulatory_context:
            sections.append(f"- **Regulatory Context:** {', '.join(mp.regulatory_context)}")
        if mp.notes:
            sections.append(f"- **Notes:** {mp.notes.strip()}")
        sections.append("")

        # Stream-level assessment
        mp_assessment = assessment_index.get(mp.id)
        if mp_assessment and mp_assessment.result:
            r = mp_assessment.result
            label = _CLASSIFICATION_LABELS[r.classification]
            sections.append(f"### Stream Assessment: {label}")
            sections.append("")
            sections.append(f"**Score:** {r.harmonization_score:.2f} / 1.00")
            sections.append("")
            sections.append("**Dimension Scores:**")
            sections.append("")
            sections.append("| Dimension | Score | Rationale |")
            sections.append("|---|---|---|")
            for ans in mp_assessment.answers:
                sections.append(
                    f"| {ans.dimension.value} | {ans.score}/5 | {ans.rationale.strip()} |"
                )
            sections.append("")

            if mp_assessment.hard_constraints:
                sections.append("**Hard Constraints:**")
                for hc in mp_assessment.hard_constraints:
                    sections.append(f"- {hc.value}")
                sections.append("")

            sections.append(f"**Rationale:**")
            sections.append(f"```")
            sections.append(r.rationale)
            sections.append(f"```")
            sections.append("")
            sections.append(f"**Recommendation:** {r.recommendation}")
            sections.append("")

        # Subprocess assessments
        for sp in children.get(mp.id, []):
            sections.append(f"### Subprocess: {sp.name}")
            sections.append("")
            sections.append(f"- **ID:** `{sp.id}`")
            sections.append(f"- **Purpose:** {sp.purpose}")
            sections.append(f"- **Country Scope:** {sp.country_scope.value}")
            sections.append(f"- **Tenant Scope:** {sp.tenant_scope.value}")
            if sp.interfaces_with:
                iface_names = [
                    _resolve_name(pid, mp_index, sp_index) for pid in sp.interfaces_with
                ]
                sections.append(f"- **Interfaces with:** {', '.join(iface_names)}")
            sections.append("")

            sp_assessment = assessment_index.get(sp.id)
            if sp_assessment and sp_assessment.result:
                r = sp_assessment.result
                label = _CLASSIFICATION_LABELS[r.classification]
                sections.append(f"**Assessment: {label}** (Score: {r.harmonization_score:.2f})")
                sections.append("")
                sections.append("| Dimension | Score | Rationale |")
                sections.append("|---|---|---|")
                for ans in sp_assessment.answers:
                    sections.append(
                        f"| {ans.dimension.value} | {ans.score}/5 | {ans.rationale.strip()} |"
                    )
                sections.append("")

                if sp_assessment.hard_constraints:
                    sections.append("**Hard Constraints:**")
                    for hc in sp_assessment.hard_constraints:
                        sections.append(f"- {hc.value}")
                    sections.append("")

                sections.append(f"**Recommendation:** {r.recommendation}")
                sections.append("")

    # --- Interfaces ---
    if interfaces:
        sections.append("## Process Interfaces")
        sections.append("")
        sections.append("| ID | Source | Target | Type | Description |")
        sections.append("|---|---|---|---|---|")
        for iface in interfaces:
            src_name = _resolve_name(iface.source_process_id, mp_index, sp_index)
            tgt_name = _resolve_name(iface.target_process_id, mp_index, sp_index)
            sections.append(
                f"| `{iface.id}` | {src_name} | {tgt_name} "
                f"| {iface.interface_type.value} | {iface.description.strip()} |"
            )
        sections.append("")

    # --- Footer ---
    sections.append("---")
    sections.append("*Report generated by harmonizer v0.1.0*")

    return "\n".join(sections)

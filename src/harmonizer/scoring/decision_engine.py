"""Decision engine for deriving management-ready decisions from assessment data.

Transforms harmonization scores, classifications, priorities, and completeness
into concrete, actionable decisions with clear rationale.

Key design principles:
- Deterministic: same inputs always produce same outputs
- Transparent: every decision has traceable rationale
- No 1:1 mapping between classification and operating model
- Interface complexity influences decisions and priority
- Harmonization, standardization, centralization are independent dimensions

Assumption: Interface complexity penalizes centralization more than
harmonization, because centralization requires tighter operational coupling
whereas harmonization can tolerate loose coupling.

Assumption: Low confidence assessments should not produce "centralize_now"
decisions — insufficient data means the decision defaults to "reassess".

Assumption: Hard constraints block centralization but may still allow
standardization (common methods without central execution).
"""

from harmonizer.models.process import (
    Area,
    Stream,
    StreamType,
    SubProcess,
    ProcessInterface,
    InterfaceType,
)
from harmonizer.models.assessment import (
    Assessment,
    AssessedObjectType,
    ConfidenceLevel,
    Decision,
    DecisionResult,
    HardConstraint,
    HarmonizationClassification,
    HarmonizationDegree,
    HarmonizationPriority,
    InterfaceComplexityResult,
    PrioritizationResult,
    TargetOperatingModel,
    ValueIndicators,
    ValueLevel,
)


# --- Interface Complexity ---
# Maximum values for normalization (empirically reasonable ceilings)
_MAX_INTERFACES = 10
_MAX_TYPES = len(InterfaceType)  # 6
_MAX_ARTIFACTS = 20
_MAX_CROSS_AREA = 5

# Weights for interface complexity sub-factors
_IC_WEIGHTS = {
    "count": 0.30,       # raw number of interfaces
    "type_diversity": 0.20,  # how many different interface types
    "artifact_diversity": 0.20,  # distinct exchanged artifacts
    "cross_area": 0.30,  # interfaces crossing area boundaries (highest impact)
}


def compute_interface_complexity(
    stream: Stream,
    subprocesses: list[SubProcess],
    interfaces: list[ProcessInterface],
    all_streams: list[Stream],
) -> InterfaceComplexityResult:
    """Compute interface complexity score for a stream.

    Factors:
    - Number of interfaces involving this stream or its subprocesses
    - Number of distinct interface types used
    - Number of distinct exchanged artifacts across all interfaces
    - Number of cross-area connections (interfaces to streams in other areas)

    Returns a score in [0.0, 1.0] where higher = more complex.
    """
    sp_ids = {sp.id for sp in subprocesses if sp.stream_id == stream.id}
    relevant_ids = sp_ids | {stream.id}

    # Find all interfaces involving this stream
    relevant_ifaces = [
        iface for iface in interfaces
        if iface.source_process_id in relevant_ids
        or iface.target_process_id in relevant_ids
    ]

    interface_count = len(relevant_ifaces)
    distinct_types = len({iface.interface_type for iface in relevant_ifaces})

    # Collect all distinct artifacts
    all_artifacts: set[str] = set()
    for iface in relevant_ifaces:
        all_artifacts.update(iface.exchanged_artifacts)
    distinct_artifacts = len(all_artifacts)

    # Cross-area connections: find streams in different areas
    stream_area_map = {s.id: s.area_id for s in all_streams}
    sp_stream_map = {sp.id: sp.stream_id for sp in subprocesses}

    def _area_of(process_id: str) -> str | None:
        if process_id in stream_area_map:
            return stream_area_map[process_id]
        parent = sp_stream_map.get(process_id)
        if parent:
            return stream_area_map.get(parent)
        return None

    cross_area = 0
    this_area = stream.area_id
    for iface in relevant_ifaces:
        other_id = (
            iface.target_process_id
            if iface.source_process_id in relevant_ids
            else iface.source_process_id
        )
        other_area = _area_of(other_id)
        if other_area and other_area != this_area:
            cross_area += 1

    # Normalize and compute weighted score
    norm_count = min(interface_count / _MAX_INTERFACES, 1.0)
    norm_types = min(distinct_types / _MAX_TYPES, 1.0) if _MAX_TYPES > 0 else 0.0
    norm_artifacts = min(distinct_artifacts / _MAX_ARTIFACTS, 1.0)
    norm_cross = min(cross_area / _MAX_CROSS_AREA, 1.0)

    score = (
        _IC_WEIGHTS["count"] * norm_count
        + _IC_WEIGHTS["type_diversity"] * norm_types
        + _IC_WEIGHTS["artifact_diversity"] * norm_artifacts
        + _IC_WEIGHTS["cross_area"] * norm_cross
    )
    score = round(min(1.0, max(0.0, score)), 4)

    # Rationale
    parts = []
    parts.append(f"{interface_count} interface(s)")
    if distinct_types > 1:
        parts.append(f"{distinct_types} distinct types")
    if distinct_artifacts > 0:
        parts.append(f"{distinct_artifacts} exchanged artifact(s)")
    if cross_area > 0:
        parts.append(f"{cross_area} cross-area connection(s)")
    rationale = f"Interface complexity {score:.2f}: {', '.join(parts)}."

    return InterfaceComplexityResult(
        complexity_score=score,
        interface_count=interface_count,
        distinct_types=distinct_types,
        distinct_artifacts=distinct_artifacts,
        cross_area_connections=cross_area,
        rationale=rationale,
    )


# --- Harmonization / Standardization / Centralization Degrees ---

# Assumption: The base harmonization_score reflects overall alignment.
# Centralizability is stricter: requires high score AND low interface complexity
# AND no blocking hard constraints.
# Standardizability is more lenient: common methods possible even with local execution.
# Harmonizability sits between the two.

_CENTRALIZATION_PENALTY_CONSTRAINTS = {
    HardConstraint.LEGAL_LOCAL_DIFFERENCE,
    HardConstraint.TENANT_SEPARATION_BLOCKS_OPERATION,
    HardConstraint.SEPARATE_CONTROL_OWNERSHIP,
}

_STANDARDIZATION_PENALTY_CONSTRAINTS = {
    HardConstraint.LEGAL_LOCAL_DIFFERENCE,
}


def compute_harmonization_degree(
    harmonization_score: float,
    hard_constraints: list[HardConstraint],
    interface_complexity: float,
    stream_type: StreamType | None = None,
) -> HarmonizationDegree:
    """Compute separate harmonizable/standardizable/centralizable degrees.

    Assumption: harmonization_score is the base alignment measure (0-1).

    Harmonization degree: base score, slightly reduced by interface complexity.
    Standardization degree: base score with moderate constraint penalty.
      Governance functions and capability domains get a standardization bonus
      because their nature lends itself to common methods.
    Centralization degree: base score heavily reduced by interface complexity
      and blocked by structural hard constraints.
    """
    # --- Harmonization ---
    # Interface complexity reduces harmonization slightly (max -0.15)
    harm_degree = max(0.0, harmonization_score - interface_complexity * 0.15)
    harmonizable = harm_degree >= 0.3

    # --- Standardization ---
    # More lenient: constraint penalty is smaller, type bonus possible
    std_penalty = 0.0
    for c in hard_constraints:
        if c in _STANDARDIZATION_PENALTY_CONSTRAINTS:
            std_penalty += 0.10  # only legal differences reduce standardizability
    type_bonus = 0.0
    if stream_type in (StreamType.GOVERNANCE_FUNCTION, StreamType.CAPABILITY_DOMAIN):
        type_bonus = 0.08  # these types are naturally standardizable
    elif stream_type == StreamType.PROGRAM_DOMAIN:
        type_bonus = 0.05
    std_degree = max(0.0, min(1.0, harmonization_score - std_penalty + type_bonus))
    standardizable = std_degree >= 0.3

    # --- Centralization ---
    # Strictest: high penalty from constraints and interface complexity
    central_penalty = 0.0
    blocking_constraints = []
    for c in hard_constraints:
        if c in _CENTRALIZATION_PENALTY_CONSTRAINTS:
            central_penalty += 0.20
            blocking_constraints.append(c.value)
    # Interface complexity penalty: high complexity strongly reduces centralizability
    # (max penalty -0.30 at complexity=1.0)
    ic_penalty = interface_complexity * 0.30
    central_degree = max(0.0, min(1.0, harmonization_score - central_penalty - ic_penalty))
    centralizable = central_degree >= 0.5  # higher bar for centralization

    # Rationale
    parts = []
    parts.append(f"Base alignment: {harmonization_score:.2f}")
    if blocking_constraints:
        parts.append(f"Centralization blocked by: {', '.join(blocking_constraints)}")
    if interface_complexity > 0.3:
        parts.append(f"High interface complexity ({interface_complexity:.2f}) reduces centralizability")
    if type_bonus > 0:
        parts.append(f"Stream type bonus for standardization: +{type_bonus:.2f}")

    return HarmonizationDegree(
        harmonizable=harmonizable,
        harmonization_degree=round(harm_degree, 4),
        standardizable=standardizable,
        standardization_degree=round(std_degree, 4),
        centralizable=centralizable,
        centralization_degree=round(central_degree, 4),
        rationale="; ".join(parts),
    )


# --- Target Operating Model ---

def derive_target_operating_model(
    classification: HarmonizationClassification,
    hsc: HarmonizationDegree,
    interface_complexity: float,
    stream_type: StreamType | None = None,
) -> TargetOperatingModel:
    """Derive target operating model from classification and H/S/C degrees.

    This is NOT a 1:1 mapping from classification. The operating model
    considers the separate H/S/C dimensions and interface complexity.

    Rules (evaluated in order):
    1. If centralizable AND classification is fully_centralizable
       AND interface_complexity < 0.5 → centralized_execution
    2. If centralizable AND classification in top 2
       BUT interface_complexity >= 0.5 → central_method_local_execution
       (complex interfaces mean central method but local execution is safer)
    3. If standardizable but not centralizable → federated_standardized
    4. If only harmonizable (not standardizable, not centralizable)
       → federated_standardized (lightweight)
    5. Otherwise → local_independent

    Governance functions prefer federated_standardized over centralized_execution
    unless centralization degree is very high (>0.8), because governance
    inherently requires local accountability.
    """
    # Governance function override: prefer federation unless very high centralizability
    if (
        stream_type == StreamType.GOVERNANCE_FUNCTION
        and hsc.centralization_degree <= 0.80
    ):
        if hsc.standardizable:
            return TargetOperatingModel.FEDERATED_STANDARDIZED
        if hsc.harmonizable:
            return TargetOperatingModel.FEDERATED_STANDARDIZED
        return TargetOperatingModel.LOCAL_INDEPENDENT

    # Rule 1: Full centralization
    if (
        hsc.centralizable
        and classification == HarmonizationClassification.FULLY_CENTRALIZABLE
        and interface_complexity < 0.5
    ):
        return TargetOperatingModel.CENTRALIZED_EXECUTION

    # Rule 2: High alignment but complex interfaces → central method, local execution
    if hsc.centralizable and classification in (
        HarmonizationClassification.FULLY_CENTRALIZABLE,
        HarmonizationClassification.CENTRAL_METHOD_LOCAL_EXECUTION,
    ):
        return TargetOperatingModel.CENTRAL_METHOD_LOCAL_EXECUTION

    # Rule 3: Standardizable
    if hsc.standardizable:
        return TargetOperatingModel.FEDERATED_STANDARDIZED

    # Rule 4: Only harmonizable
    if hsc.harmonizable:
        return TargetOperatingModel.FEDERATED_STANDARDIZED

    # Rule 5: Nothing feasible
    return TargetOperatingModel.LOCAL_INDEPENDENT


# --- Value Indicators ---

def compute_value_indicators(
    assessment: Assessment,
    stream_type: StreamType | None = None,
    has_regulatory_context: bool = False,
) -> ValueIndicators:
    """Derive economic/strategic value indicators from assessment data.

    Uses existing assessment dimensions and prioritization to infer value:
    - expected_business_value: from operational_relevance + harmonization_potential
    - regulatory_pressure: from regulatory_alignment score + regulatory context
    - operational_impact: from operational_alignment + maturity gap

    These are deterministic derivations, not independent inputs.
    """
    # Extract dimension scores
    dim_scores: dict[str, int] = {}
    for ans in assessment.answers:
        dim_scores[ans.dimension.value] = ans.score

    pri = assessment.prioritization

    # --- Expected Business Value ---
    # Based on harmonization potential and operational relevance from prioritization,
    # or inferred from operational + governance alignment if no prioritization
    bv_score = 0.0
    if pri:
        # Normalize: (potential + relevance) / 2, on 1-5 scale → 0-1
        bv_score = ((pri.harmonization_potential - 1) + (pri.operational_relevance - 1)) / 8.0
    else:
        op = dim_scores.get("operational_alignment", 3)
        gov = dim_scores.get("governance_alignment", 3)
        bv_score = ((op - 1) + (gov - 1)) / 8.0

    if bv_score >= 0.65:
        business_value = ValueLevel.HIGH
    elif bv_score >= 0.35:
        business_value = ValueLevel.MEDIUM
    else:
        business_value = ValueLevel.LOW

    # --- Regulatory Pressure ---
    reg_score = 0.0
    reg_dim = dim_scores.get("regulatory_alignment", 3)
    # High regulatory alignment score means HIGH existing alignment (less pressure).
    # We want pressure = how much regulation forces harmonization.
    # Invert: low alignment + regulatory context = high pressure
    reg_gap = (5 - reg_dim) / 4.0  # 0 = fully aligned, 1 = not aligned
    reg_score = reg_gap * 0.6 + (0.4 if has_regulatory_context else 0.0)
    if pri and pri.governance_compliance_benefit >= 4:
        reg_score = min(1.0, reg_score + 0.2)

    if reg_score >= 0.55:
        regulatory_pressure = ValueLevel.HIGH
    elif reg_score >= 0.30:
        regulatory_pressure = ValueLevel.MEDIUM
    else:
        regulatory_pressure = ValueLevel.LOW

    # --- Operational Impact ---
    # How much operational benefit harmonization would bring
    op_align = dim_scores.get("operational_alignment", 3)
    tool_align = dim_scores.get("tooling_alignment", 3)
    maturity = dim_scores.get("maturity", 3)
    # Higher alignment scores = more potential for operational benefit from centralizing
    # Low maturity = more room for improvement
    maturity_gap = (5 - maturity) / 4.0
    op_score = ((op_align - 1) / 4.0) * 0.4 + ((tool_align - 1) / 4.0) * 0.3 + maturity_gap * 0.3

    if op_score >= 0.60:
        operational_impact = ValueLevel.HIGH
    elif op_score >= 0.35:
        operational_impact = ValueLevel.MEDIUM
    else:
        operational_impact = ValueLevel.LOW

    # Rationale
    parts = []
    parts.append(f"Business value: {business_value.value} (score {bv_score:.2f})")
    parts.append(f"Regulatory pressure: {regulatory_pressure.value} (score {reg_score:.2f})")
    parts.append(f"Operational impact: {operational_impact.value} (score {op_score:.2f})")

    return ValueIndicators(
        expected_business_value=business_value,
        regulatory_pressure=regulatory_pressure,
        operational_impact=operational_impact,
        rationale="; ".join(parts),
    )


# --- Decision Engine ---

def compute_decision(
    assessment: Assessment,
    stream: Stream,
    subprocesses: list[SubProcess],
    interfaces: list[ProcessInterface],
    all_streams: list[Stream],
    has_regulatory_context: bool = False,
) -> DecisionResult:
    """Derive a concrete management decision from all available assessment data.

    Decision rules (evaluated in order):

    1. If confidence is LOW → reassess_after_data_completion
       Rationale: Decisions on thin data create false precision.

    2. If classification is currently_not_harmonizable
       AND no centralization/standardization possible → keep_local

    3. If centralizable AND high priority AND low interface complexity
       → centralize_now

    4. If centralizable AND (medium priority OR high interface complexity)
       → centralize_later

    5. If standardizable but not centralizable → standardize_only

    6. If harmonizable but not standardizable → harmonize_only

    7. Fallback → keep_local

    Additional modifiers:
    - Value indicators influence decision confidence but not the decision itself
    - Blocking factors are explicitly listed
    - Prerequisites are derived from completeness gaps and constraints
    """
    # Require an evaluated result
    result = assessment.result
    if result is None:
        raise ValueError(
            f"Assessment {assessment.assessed_object_id} has no result. "
            "Run evaluate() before compute_decision()."
        )

    # Step 1: Compute interface complexity
    ic = compute_interface_complexity(
        stream, subprocesses, interfaces, all_streams
    )

    # Step 2: Compute H/S/C degrees
    hsc = compute_harmonization_degree(
        harmonization_score=result.harmonization_score,
        hard_constraints=assessment.hard_constraints,
        interface_complexity=ic.complexity_score,
        stream_type=stream.stream_type,
    )

    # Step 3: Derive target operating model
    tom = derive_target_operating_model(
        classification=result.classification,
        hsc=hsc,
        interface_complexity=ic.complexity_score,
        stream_type=stream.stream_type,
    )

    # Step 4: Compute value indicators
    vi = compute_value_indicators(
        assessment,
        stream_type=stream.stream_type,
        has_regulatory_context=has_regulatory_context,
    )

    # Step 5: Determine decision
    confidence = (
        assessment.completeness.confidence_level
        if assessment.completeness
        else ConfidenceLevel.LOW
    )
    priority = (
        assessment.prioritization_result.priority
        if assessment.prioritization_result
        else HarmonizationPriority.LOW
    )

    blocking_factors: list[str] = []
    prerequisites: list[str] = []

    # Collect blocking factors
    for c in assessment.hard_constraints:
        blocking_factors.append(f"Hard constraint: {c.value}")
    if ic.complexity_score >= 0.5:
        blocking_factors.append(
            f"High interface complexity ({ic.complexity_score:.2f}) — "
            "requires interface harmonization before centralization"
        )
    if confidence == ConfidenceLevel.LOW:
        blocking_factors.append("Low assessment confidence — insufficient data for reliable decision")

    # Collect prerequisites from completeness
    if assessment.completeness and assessment.completeness.missing_items:
        for item in assessment.completeness.missing_items:
            prerequisites.append(f"Complete assessment gap: {item}")
    if ic.cross_area_connections > 0:
        prerequisites.append(
            f"Resolve {ic.cross_area_connections} cross-area interface(s) before proceeding"
        )

    # Decision rules
    if confidence == ConfidenceLevel.LOW:
        decision = Decision.REASSESS_AFTER_DATA_COMPLETION
        decision_rationale = (
            "Assessment data is insufficient for a reliable decision. "
            f"Completeness: {assessment.completeness.completeness_score}/100. "
            "Complete the identified gaps before deciding."
        )
    elif result.classification == HarmonizationClassification.CURRENTLY_NOT_HARMONIZABLE:
        if not hsc.standardizable and not hsc.harmonizable:
            decision = Decision.KEEP_LOCAL
            decision_rationale = (
                "No viable harmonization, standardization, or centralization path identified. "
                "Maintain as independent local processes."
            )
        elif hsc.standardizable:
            decision = Decision.STANDARDIZE_ONLY
            decision_rationale = (
                "Classification blocks harmonization, but common standards are achievable. "
                "Define minimum standards without requiring process unification."
            )
        else:
            decision = Decision.HARMONIZE_ONLY
            decision_rationale = (
                "Limited harmonization possible despite overall low alignment. "
                "Focus on aligning specific sub-aspects."
            )
    elif hsc.centralizable and priority == HarmonizationPriority.HIGH and ic.complexity_score < 0.5:
        decision = Decision.CENTRALIZE_NOW
        decision_rationale = (
            f"High alignment ({result.harmonization_score:.2f}), high priority, "
            f"manageable interface complexity ({ic.complexity_score:.2f}). "
            "Proceed with centralization."
        )
    elif hsc.centralizable:
        decision = Decision.CENTRALIZE_LATER
        if ic.complexity_score >= 0.5:
            decision_rationale = (
                f"Centralization is feasible (degree: {hsc.centralization_degree:.2f}), "
                f"but interface complexity ({ic.complexity_score:.2f}) requires "
                "preparatory interface harmonization first."
            )
        else:
            decision_rationale = (
                f"Centralization is feasible (degree: {hsc.centralization_degree:.2f}), "
                f"but priority is {priority.value}. Plan for a later phase."
            )
    elif hsc.standardizable:
        decision = Decision.STANDARDIZE_ONLY
        decision_rationale = (
            f"Standardization degree: {hsc.standardization_degree:.2f}. "
            f"Centralization not viable (degree: {hsc.centralization_degree:.2f}). "
            "Establish common standards and templates."
        )
    elif hsc.harmonizable:
        decision = Decision.HARMONIZE_ONLY
        decision_rationale = (
            f"Harmonization degree: {hsc.harmonization_degree:.2f}. "
            "Neither standardization nor centralization are currently achievable. "
            "Align where possible, accept local variants."
        )
    else:
        decision = Decision.KEEP_LOCAL
        decision_rationale = (
            "No viable path to harmonization, standardization, or centralization. "
            "Maintain local processes."
        )

    # Expected benefit
    benefit_parts = []
    if vi.expected_business_value == ValueLevel.HIGH:
        benefit_parts.append("High business value from unification")
    elif vi.expected_business_value == ValueLevel.MEDIUM:
        benefit_parts.append("Moderate business value expected")
    if vi.regulatory_pressure == ValueLevel.HIGH:
        benefit_parts.append("Addresses significant regulatory requirements")
    if vi.operational_impact == ValueLevel.HIGH:
        benefit_parts.append("Major operational efficiency gains likely")
    expected_benefit = ". ".join(benefit_parts) if benefit_parts else "Limited direct benefit expected"

    # Implementation risk
    risk_parts = []
    if ic.complexity_score >= 0.5:
        risk_parts.append("High interface complexity increases integration risk")
    if len(assessment.hard_constraints) >= 2:
        risk_parts.append(f"{len(assessment.hard_constraints)} hard constraints to manage")
    if priority == HarmonizationPriority.LOW:
        risk_parts.append("Low priority may lead to resource competition")
    if not risk_parts:
        if decision in (Decision.CENTRALIZE_NOW, Decision.CENTRALIZE_LATER):
            risk_parts.append("Standard centralization risks (change management, stakeholder alignment)")
        else:
            risk_parts.append("Low implementation risk")
    implementation_risk = ". ".join(risk_parts)

    return DecisionResult(
        decision=decision,
        decision_rationale=decision_rationale,
        blocking_factors=blocking_factors,
        prerequisites=prerequisites,
        expected_benefit=expected_benefit,
        implementation_risk=implementation_risk,
        target_operating_model=tom,
        interface_complexity=ic,
        harmonization_degree=hsc,
        value_indicators=vi,
    )

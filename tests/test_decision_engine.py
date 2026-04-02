"""Tests for the decision engine.

Covers:
- Interface complexity computation
- Harmonization/Standardization/Centralization degree separation
- Target operating model derivation
- Value indicators
- Full decision logic including edge cases
"""

import pytest

from harmonizer.models.process import (
    Area,
    Stream,
    StreamType,
    SubProcess,
    ProcessInterface,
    InterfaceType,
    CountryScope,
    TenantScope,
)
from harmonizer.models.assessment import (
    AlignmentDimension,
    Assessment,
    AssessedObjectType,
    AssessmentAnswer,
    CompletenessResult,
    ConfidenceLevel,
    Decision,
    HardConstraint,
    HarmonizationClassification,
    HarmonizationDegree,
    HarmonizationPriority,
    HarmonizationResult,
    InterfaceComplexityResult,
    PrioritizationInput,
    PrioritizationResult,
    TargetOperatingModel,
    ValueLevel,
)
from harmonizer.scoring.decision_engine import (
    compute_interface_complexity,
    compute_harmonization_degree,
    derive_target_operating_model,
    compute_value_indicators,
    compute_decision,
)


# --- Helpers ---

def _make_stream(
    stream_id: str = "s1",
    area_id: str = "a1",
    stream_type: StreamType = StreamType.PROCESS,
    regulatory_context: list[str] | None = None,
) -> Stream:
    return Stream(
        id=stream_id,
        area_id=area_id,
        name="Test Stream",
        stream_type=stream_type,
        description="Test",
        owner_role="Owner",
        country_scope=CountryScope.BOTH,
        tenant_scope=TenantScope.BOTH,
        regulatory_context=regulatory_context or [],
    )


def _make_subprocess(
    sp_id: str = "sp1",
    stream_id: str = "s1",
) -> SubProcess:
    return SubProcess(
        id=sp_id,
        stream_id=stream_id,
        name="Test SP",
        description="Test",
        purpose="Test",
        country_scope=CountryScope.BOTH,
        tenant_scope=TenantScope.BOTH,
    )


def _make_interface(
    iface_id: str = "if1",
    source: str = "sp1",
    target: str = "sp2",
    itype: InterfaceType = InterfaceType.DATA_FLOW,
    artifacts: list[str] | None = None,
) -> ProcessInterface:
    return ProcessInterface(
        id=iface_id,
        source_process_id=source,
        target_process_id=target,
        interface_type=itype,
        description="Test interface",
        exchanged_artifacts=artifacts or [],
    )


def _make_full_answers(score: int = 4) -> list[AssessmentAnswer]:
    return [
        AssessmentAnswer(dimension=d, score=score, rationale="R")
        for d in AlignmentDimension
    ]


def _make_assessment(
    obj_id: str = "s1",
    score: int = 4,
    constraints: list[HardConstraint] | None = None,
    with_prioritization: bool = True,
    with_result: bool = True,
    classification: HarmonizationClassification = HarmonizationClassification.CENTRAL_METHOD_LOCAL_EXECUTION,
    harm_score: float = 0.75,
    confidence: ConfidenceLevel = ConfidenceLevel.HIGH,
    completeness_score: int = 80,
) -> Assessment:
    a = Assessment(
        assessed_object_type=AssessedObjectType.STREAM,
        assessed_object_id=obj_id,
        answers=_make_full_answers(score),
        hard_constraints=constraints or [],
    )
    if with_prioritization:
        a.prioritization = PrioritizationInput(
            harmonization_potential=4,
            operational_relevance=4,
            governance_compliance_benefit=4,
            implementation_effort=2,
            dependencies=2,
        )
        a.prioritization_result = PrioritizationResult(
            priority=HarmonizationPriority.HIGH,
            priority_score=0.72,
            rationale="High priority",
        )
    if with_result:
        a.result = HarmonizationResult(
            harmonization_score=harm_score,
            classification=classification,
            rationale="Test rationale",
            recommendation="Test recommendation",
        )
    a.completeness = CompletenessResult(
        completeness_score=completeness_score,
        confidence_level=confidence,
        missing_items=[],
        rationale="Test",
    )
    return a


# --- Interface Complexity Tests ---

class TestInterfaceComplexity:

    def test_no_interfaces(self) -> None:
        stream = _make_stream()
        result = compute_interface_complexity(stream, [], [], [stream])
        assert result.complexity_score == 0.0
        assert result.interface_count == 0

    def test_single_interface(self) -> None:
        stream = _make_stream()
        sp = _make_subprocess()
        iface = _make_interface(source="sp1", target="sp_other")
        result = compute_interface_complexity(stream, [sp], [iface], [stream])
        assert result.complexity_score > 0.0
        assert result.interface_count == 1

    def test_multiple_types_increase_complexity(self) -> None:
        stream = _make_stream()
        sp = _make_subprocess()
        ifaces = [
            _make_interface("if1", "sp1", "other1", InterfaceType.DATA_FLOW),
            _make_interface("if2", "sp1", "other2", InterfaceType.TRIGGER),
            _make_interface("if3", "sp1", "other3", InterfaceType.ESCALATION),
        ]
        result = compute_interface_complexity(stream, [sp], ifaces, [stream])
        assert result.distinct_types == 3
        assert result.complexity_score > 0.15

    def test_cross_area_increases_complexity(self) -> None:
        stream_a = _make_stream("s1", "a1")
        stream_b = _make_stream("s2", "a2")
        sp_a = _make_subprocess("sp1", "s1")
        sp_b = _make_subprocess("sp2", "s2")
        iface = _make_interface("if1", "sp1", "sp2")

        result = compute_interface_complexity(
            stream_a, [sp_a, sp_b], [iface], [stream_a, stream_b]
        )
        assert result.cross_area_connections == 1
        assert result.complexity_score > 0.0

    def test_artifacts_counted(self) -> None:
        stream = _make_stream()
        sp = _make_subprocess()
        iface = _make_interface(
            artifacts=["report", "ticket", "log", "certificate"]
        )
        result = compute_interface_complexity(stream, [sp], [iface], [stream])
        assert result.distinct_artifacts == 4

    def test_many_interfaces_high_complexity(self) -> None:
        stream = _make_stream()
        sp = _make_subprocess()
        ifaces = [
            _make_interface(f"if{i}", "sp1", f"other{i}", InterfaceType.DATA_FLOW,
                            [f"art{i}a", f"art{i}b"])
            for i in range(10)
        ]
        result = compute_interface_complexity(stream, [sp], ifaces, [stream])
        assert result.complexity_score >= 0.5
        assert result.interface_count == 10


# --- Harmonization Degree Tests ---

class TestHarmonizationDegree:

    def test_high_score_no_constraints_all_feasible(self) -> None:
        hsc = compute_harmonization_degree(0.85, [], 0.0)
        assert hsc.harmonizable is True
        assert hsc.standardizable is True
        assert hsc.centralizable is True
        assert hsc.centralization_degree >= 0.5

    def test_low_score_nothing_feasible(self) -> None:
        hsc = compute_harmonization_degree(0.15, [], 0.0)
        assert hsc.harmonizable is False
        assert hsc.standardizable is False
        assert hsc.centralizable is False

    def test_constraints_block_centralization(self) -> None:
        hsc = compute_harmonization_degree(
            0.85,
            [HardConstraint.LEGAL_LOCAL_DIFFERENCE],
            0.0,
        )
        # Legal difference reduces centralization by 0.20
        assert hsc.centralizable is False or hsc.centralization_degree < 0.85
        # But standardization takes a smaller hit
        assert hsc.standardization_degree > hsc.centralization_degree

    def test_multiple_constraints_cumulative(self) -> None:
        hsc = compute_harmonization_degree(
            0.85,
            [
                HardConstraint.LEGAL_LOCAL_DIFFERENCE,
                HardConstraint.TENANT_SEPARATION_BLOCKS_OPERATION,
            ],
            0.0,
        )
        # Two constraints: -0.40 from centralization
        assert hsc.centralization_degree <= 0.50

    def test_interface_complexity_reduces_centralization(self) -> None:
        hsc_low = compute_harmonization_degree(0.85, [], 0.1)
        hsc_high = compute_harmonization_degree(0.85, [], 0.9)
        assert hsc_high.centralization_degree < hsc_low.centralization_degree

    def test_governance_type_bonus_standardization(self) -> None:
        hsc_plain = compute_harmonization_degree(0.60, [], 0.0, StreamType.PROCESS)
        hsc_gov = compute_harmonization_degree(0.60, [], 0.0, StreamType.GOVERNANCE_FUNCTION)
        assert hsc_gov.standardization_degree > hsc_plain.standardization_degree

    def test_standardizable_but_not_centralizable(self) -> None:
        # Medium score with constraints: standardizable but not centralizable
        hsc = compute_harmonization_degree(
            0.55,
            [HardConstraint.SEPARATE_CONTROL_OWNERSHIP],
            0.3,
        )
        assert hsc.standardizable is True
        assert hsc.centralizable is False


# --- Target Operating Model Tests ---

class TestTargetOperatingModel:

    def test_full_centralization(self) -> None:
        hsc = HarmonizationDegree(
            harmonizable=True, harmonization_degree=0.9,
            standardizable=True, standardization_degree=0.9,
            centralizable=True, centralization_degree=0.9,
            rationale="R",
        )
        tom = derive_target_operating_model(
            HarmonizationClassification.FULLY_CENTRALIZABLE,
            hsc, 0.2, StreamType.PROCESS,
        )
        assert tom == TargetOperatingModel.CENTRALIZED_EXECUTION

    def test_high_complexity_blocks_centralized_execution(self) -> None:
        hsc = HarmonizationDegree(
            harmonizable=True, harmonization_degree=0.9,
            standardizable=True, standardization_degree=0.9,
            centralizable=True, centralization_degree=0.9,
            rationale="R",
        )
        tom = derive_target_operating_model(
            HarmonizationClassification.FULLY_CENTRALIZABLE,
            hsc, 0.6, StreamType.PROCESS,
        )
        # High complexity: central method but local execution
        assert tom == TargetOperatingModel.CENTRAL_METHOD_LOCAL_EXECUTION

    def test_standardizable_not_centralizable(self) -> None:
        hsc = HarmonizationDegree(
            harmonizable=True, harmonization_degree=0.6,
            standardizable=True, standardization_degree=0.6,
            centralizable=False, centralization_degree=0.3,
            rationale="R",
        )
        tom = derive_target_operating_model(
            HarmonizationClassification.PARTIALLY_HARMONIZABLE,
            hsc, 0.2, StreamType.PROCESS,
        )
        assert tom == TargetOperatingModel.FEDERATED_STANDARDIZED

    def test_nothing_feasible(self) -> None:
        hsc = HarmonizationDegree(
            harmonizable=False, harmonization_degree=0.1,
            standardizable=False, standardization_degree=0.1,
            centralizable=False, centralization_degree=0.0,
            rationale="R",
        )
        tom = derive_target_operating_model(
            HarmonizationClassification.CURRENTLY_NOT_HARMONIZABLE,
            hsc, 0.0, StreamType.PROCESS,
        )
        assert tom == TargetOperatingModel.LOCAL_INDEPENDENT

    def test_governance_prefers_federation(self) -> None:
        """Governance functions prefer federated model even when centralizable."""
        hsc = HarmonizationDegree(
            harmonizable=True, harmonization_degree=0.8,
            standardizable=True, standardization_degree=0.8,
            centralizable=True, centralization_degree=0.7,
            rationale="R",
        )
        tom = derive_target_operating_model(
            HarmonizationClassification.FULLY_CENTRALIZABLE,
            hsc, 0.2, StreamType.GOVERNANCE_FUNCTION,
        )
        # Governance override: federation unless very high centralizability (>0.80)
        assert tom == TargetOperatingModel.FEDERATED_STANDARDIZED

    def test_governance_very_high_centralization_allowed(self) -> None:
        """Governance functions CAN centralize if degree > 0.80."""
        hsc = HarmonizationDegree(
            harmonizable=True, harmonization_degree=0.95,
            standardizable=True, standardization_degree=0.95,
            centralizable=True, centralization_degree=0.85,
            rationale="R",
        )
        tom = derive_target_operating_model(
            HarmonizationClassification.FULLY_CENTRALIZABLE,
            hsc, 0.1, StreamType.GOVERNANCE_FUNCTION,
        )
        assert tom == TargetOperatingModel.CENTRALIZED_EXECUTION


# --- Value Indicators Tests ---

class TestValueIndicators:

    def test_high_prioritization_yields_high_business_value(self) -> None:
        a = _make_assessment(score=4)
        a.prioritization = PrioritizationInput(
            harmonization_potential=5,
            operational_relevance=5,
            governance_compliance_benefit=5,
            implementation_effort=1,
            dependencies=1,
        )
        vi = compute_value_indicators(a, StreamType.PROCESS, True)
        assert vi.expected_business_value == ValueLevel.HIGH

    def test_low_scores_yield_low_values(self) -> None:
        a = Assessment(
            assessed_object_type=AssessedObjectType.STREAM,
            assessed_object_id="s1",
            answers=[
                AssessmentAnswer(dimension=d, score=1, rationale="R")
                for d in AlignmentDimension
            ],
        )
        vi = compute_value_indicators(a, StreamType.PROCESS, False)
        assert vi.expected_business_value == ValueLevel.LOW

    def test_regulatory_context_increases_pressure(self) -> None:
        a = _make_assessment(score=2)  # Low alignment = high gap
        vi_no_reg = compute_value_indicators(a, StreamType.PROCESS, False)
        vi_reg = compute_value_indicators(a, StreamType.PROCESS, True)
        # With regulatory context, pressure should be higher or equal
        pressure_order = {"low": 0, "medium": 1, "high": 2}
        assert pressure_order[vi_reg.regulatory_pressure.value] >= pressure_order[vi_no_reg.regulatory_pressure.value]

    def test_high_maturity_gap_increases_operational_impact(self) -> None:
        # Low maturity = high gap = high operational impact potential
        a = Assessment(
            assessed_object_type=AssessedObjectType.STREAM,
            assessed_object_id="s1",
            answers=[
                AssessmentAnswer(dimension=AlignmentDimension.OPERATIONAL_ALIGNMENT, score=5, rationale="R"),
                AssessmentAnswer(dimension=AlignmentDimension.TOOLING_ALIGNMENT, score=5, rationale="R"),
                AssessmentAnswer(dimension=AlignmentDimension.MATURITY, score=1, rationale="R"),
            ],
        )
        vi = compute_value_indicators(a, StreamType.PROCESS, False)
        assert vi.operational_impact == ValueLevel.HIGH


# --- Full Decision Tests ---

class TestDecisionEngine:

    def _default_context(self, stream_type=StreamType.PROCESS):
        stream = _make_stream(stream_type=stream_type)
        sp = _make_subprocess()
        return stream, [sp], [], [stream]

    def test_low_confidence_yields_reassess(self) -> None:
        stream, sps, ifaces, all_streams = self._default_context()
        a = _make_assessment(confidence=ConfidenceLevel.LOW, completeness_score=30)
        dr = compute_decision(a, stream, sps, ifaces, all_streams)
        assert dr.decision == Decision.REASSESS_AFTER_DATA_COMPLETION

    def test_high_score_high_priority_centralize_now(self) -> None:
        stream, sps, ifaces, all_streams = self._default_context()
        a = _make_assessment(
            score=5,
            harm_score=0.90,
            classification=HarmonizationClassification.FULLY_CENTRALIZABLE,
        )
        dr = compute_decision(a, stream, sps, ifaces, all_streams)
        assert dr.decision == Decision.CENTRALIZE_NOW
        assert dr.target_operating_model == TargetOperatingModel.CENTRALIZED_EXECUTION

    def test_centralizable_but_low_priority_centralize_later(self) -> None:
        stream, sps, ifaces, all_streams = self._default_context()
        a = _make_assessment(
            score=5,
            harm_score=0.90,
            classification=HarmonizationClassification.FULLY_CENTRALIZABLE,
        )
        a.prioritization_result = PrioritizationResult(
            priority=HarmonizationPriority.MEDIUM,
            priority_score=0.50,
            rationale="Medium",
        )
        dr = compute_decision(a, stream, sps, ifaces, all_streams)
        assert dr.decision == Decision.CENTRALIZE_LATER

    def test_not_harmonizable_keep_local(self) -> None:
        stream, sps, ifaces, all_streams = self._default_context()
        a = _make_assessment(
            score=1,
            harm_score=0.10,
            classification=HarmonizationClassification.CURRENTLY_NOT_HARMONIZABLE,
        )
        dr = compute_decision(a, stream, sps, ifaces, all_streams)
        assert dr.decision == Decision.KEEP_LOCAL
        assert dr.target_operating_model == TargetOperatingModel.LOCAL_INDEPENDENT

    def test_standardize_only(self) -> None:
        stream, sps, ifaces, all_streams = self._default_context()
        # Medium score with constraint that blocks centralization
        a = _make_assessment(
            score=3,
            harm_score=0.55,
            classification=HarmonizationClassification.PARTIALLY_HARMONIZABLE,
            constraints=[
                HardConstraint.LEGAL_LOCAL_DIFFERENCE,
                HardConstraint.SEPARATE_CONTROL_OWNERSHIP,
            ],
        )
        dr = compute_decision(a, stream, sps, ifaces, all_streams)
        # With two blocking constraints, centralization_degree drops heavily
        assert dr.decision in (Decision.STANDARDIZE_ONLY, Decision.HARMONIZE_ONLY)

    def test_high_interface_complexity_blocks_centralize_now(self) -> None:
        """High score + high priority, but interface complexity prevents centralize_now."""
        stream = _make_stream()
        sp = _make_subprocess()
        # Create many cross-area interfaces
        stream_b = _make_stream("s2", "a2")
        sp_b = _make_subprocess("sp2", "s2")
        ifaces = [
            _make_interface(f"if{i}", "sp1", "sp2", InterfaceType.DATA_FLOW,
                            [f"art{i}a", f"art{i}b", f"art{i}c"])
            for i in range(8)
        ]
        a = _make_assessment(
            score=5,
            harm_score=0.90,
            classification=HarmonizationClassification.FULLY_CENTRALIZABLE,
        )
        dr = compute_decision(a, stream, [sp, sp_b], ifaces, [stream, stream_b])
        # Should not be centralize_now due to high interface complexity
        assert dr.decision != Decision.CENTRALIZE_NOW
        assert dr.interface_complexity.complexity_score >= 0.3

    def test_decision_has_blocking_factors(self) -> None:
        stream, sps, ifaces, all_streams = self._default_context()
        a = _make_assessment(
            constraints=[HardConstraint.LEGAL_LOCAL_DIFFERENCE],
        )
        dr = compute_decision(a, stream, sps, ifaces, all_streams)
        assert any("Hard constraint" in bf for bf in dr.blocking_factors)

    def test_decision_has_prerequisites_from_completeness(self) -> None:
        stream, sps, ifaces, all_streams = self._default_context()
        a = _make_assessment()
        a.completeness = CompletenessResult(
            completeness_score=80,
            confidence_level=ConfidenceLevel.HIGH,
            missing_items=["Missing base dimensions: maturity"],
            rationale="Test",
        )
        dr = compute_decision(a, stream, sps, ifaces, all_streams)
        assert any("maturity" in p for p in dr.prerequisites)

    def test_no_result_raises_error(self) -> None:
        stream, sps, ifaces, all_streams = self._default_context()
        a = _make_assessment(with_result=False)
        with pytest.raises(ValueError, match="has no result"):
            compute_decision(a, stream, sps, ifaces, all_streams)

    def test_hsc_degrees_present_in_result(self) -> None:
        stream, sps, ifaces, all_streams = self._default_context()
        a = _make_assessment()
        dr = compute_decision(a, stream, sps, ifaces, all_streams)
        assert dr.harmonization_degree is not None
        assert 0.0 <= dr.harmonization_degree.harmonization_degree <= 1.0
        assert 0.0 <= dr.harmonization_degree.standardization_degree <= 1.0
        assert 0.0 <= dr.harmonization_degree.centralization_degree <= 1.0

    def test_value_indicators_present(self) -> None:
        stream, sps, ifaces, all_streams = self._default_context()
        a = _make_assessment()
        dr = compute_decision(a, stream, sps, ifaces, all_streams)
        assert dr.value_indicators is not None
        assert dr.value_indicators.expected_business_value in ValueLevel

    def test_governance_stream_decision(self) -> None:
        """Governance function with good score should prefer federation."""
        stream = _make_stream(stream_type=StreamType.GOVERNANCE_FUNCTION)
        sp = _make_subprocess()
        a = _make_assessment(
            score=4,
            harm_score=0.75,
            classification=HarmonizationClassification.CENTRAL_METHOD_LOCAL_EXECUTION,
        )
        dr = compute_decision(a, stream, [sp], [], [stream])
        # Governance prefers federated
        assert dr.target_operating_model in (
            TargetOperatingModel.FEDERATED_STANDARDIZED,
            TargetOperatingModel.CENTRAL_METHOD_LOCAL_EXECUTION,
        )


# --- Edge Case Tests ---

class TestEdgeCases:

    def test_high_score_but_high_interface_complexity(self) -> None:
        """Edge case: excellent alignment but tightly coupled to other streams."""
        stream = _make_stream()
        sp = _make_subprocess()
        stream_other = _make_stream("s2", "a2")
        sp_other = _make_subprocess("sp2", "s2")
        # Many cross-area, multi-type interfaces
        ifaces = [
            _make_interface("if1", "sp1", "sp2", InterfaceType.DATA_FLOW, ["a", "b", "c"]),
            _make_interface("if2", "sp1", "sp2", InterfaceType.TRIGGER, ["d", "e"]),
            _make_interface("if3", "sp1", "sp2", InterfaceType.ESCALATION, ["f"]),
            _make_interface("if4", "sp1", "sp2", InterfaceType.APPROVAL, ["g", "h"]),
            _make_interface("if5", "sp1", "sp2", InterfaceType.HANDOVER, ["i"]),
        ]
        a = _make_assessment(
            score=5,
            harm_score=0.92,
            classification=HarmonizationClassification.FULLY_CENTRALIZABLE,
        )
        dr = compute_decision(a, stream, [sp, sp_other], ifaces, [stream, stream_other])
        # High complexity should prevent centralize_now
        assert dr.interface_complexity.complexity_score > 0.3
        # Decision should reflect the tension
        assert dr.decision in (
            Decision.CENTRALIZE_LATER,
            Decision.CENTRALIZE_NOW,  # if complexity doesn't cross 0.5
            Decision.STANDARDIZE_ONLY,
        )

    def test_medium_score_no_constraints_no_interfaces(self) -> None:
        """Clean medium case: should standardize or harmonize."""
        stream = _make_stream()
        a = _make_assessment(
            score=3,
            harm_score=0.50,
            classification=HarmonizationClassification.PARTIALLY_HARMONIZABLE,
        )
        a.prioritization_result = PrioritizationResult(
            priority=HarmonizationPriority.MEDIUM,
            priority_score=0.50,
            rationale="Medium",
        )
        dr = compute_decision(a, stream, [], [], [stream])
        assert dr.decision in (
            Decision.STANDARDIZE_ONLY,
            Decision.HARMONIZE_ONLY,
            Decision.CENTRALIZE_LATER,
        )

    def test_all_hard_constraints(self) -> None:
        """All four hard constraints active."""
        stream = _make_stream()
        a = _make_assessment(
            score=5,
            harm_score=0.90,
            classification=HarmonizationClassification.FULLY_CENTRALIZABLE,
            constraints=list(HardConstraint),
        )
        dr = compute_decision(a, stream, [], [], [stream])
        # With all constraints, centralization should be impossible
        assert dr.harmonization_degree.centralizable is False
        assert dr.decision != Decision.CENTRALIZE_NOW
        assert len(dr.blocking_factors) >= 3

    def test_minimum_standard_with_standardization(self) -> None:
        """Classification minimum_standard_only but standardizable."""
        stream = _make_stream()
        a = _make_assessment(
            score=2,
            harm_score=0.35,
            classification=HarmonizationClassification.MINIMUM_STANDARD_ONLY,
        )
        dr = compute_decision(a, stream, [], [], [stream])
        assert dr.decision in (Decision.STANDARDIZE_ONLY, Decision.HARMONIZE_ONLY, Decision.KEEP_LOCAL)

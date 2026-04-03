"""Tests for Markdown report generation."""

from harmonizer.models.process import (
    Area,
    CountryScope,
    InterfaceType,
    ProcessInterface,
    Stream,
    StreamType,
    SubProcess,
    TenantScope,
)
from harmonizer.models.assessment import (
    AlignmentDimension,
    AlternativeOption,
    AssessedObjectType,
    Assessment,
    AssessmentAnswer,
    CalibrationDeviation,
    CalibrationResult,
    CalibrationSuggestion,
    FilteredCalibrationStats,
    CompletenessResult,
    ConfidenceLevel,
    Decision,
    DecisionResult,
    DecisionTrace,
    DecisionType,
    DurationCategory,
    EffortEstimate,
    GovernanceMapping,
    HarmonizationClassification,
    HarmonizationDegree,
    HarmonizationPriority,
    HarmonizationResult,
    ImplementationImpact,
    InterfaceComplexityResult,
    ModelMaturityLevel,
    NoActionImpact,
    PrioritizationResult,
    ProtectedRule,
    TrustScoreResult,
    TargetOperatingModel,
    ValueIndicators,
    ValueLevel,
)
from harmonizer.reporting.markdown import generate_report, generate_mermaid_diagram


def _minimal_data() -> tuple[list[Area], list[Stream], list[SubProcess], list[ProcessInterface]]:
    area = Area(id="area-test", name="Test Area", description="Test area desc")
    stream = Stream(
        id="stream-test", area_id="area-test", name="Test Stream",
        stream_type=StreamType.PROCESS, description="Test", owner_role="Owner",
        country_scope=CountryScope.BOTH, tenant_scope=TenantScope.BOTH,
    )
    sp = SubProcess(
        id="sp-test", stream_id="stream-test", name="Test Sub",
        description="Test", purpose="Test",
        country_scope=CountryScope.BOTH, tenant_scope=TenantScope.BOTH,
    )
    return [area], [stream], [sp], []


class TestMermaidDiagram:
    def test_contains_subgraph_for_area(self) -> None:
        areas, streams, sps, ifaces = _minimal_data()
        diagram = generate_mermaid_diagram(areas, streams, sps, ifaces)
        assert "Test Area" in diagram
        assert "Test Stream" in diagram

    def test_interface_arrow(self) -> None:
        areas, streams, sps, _ = _minimal_data()
        iface = ProcessInterface(
            id="iface-test", source_process_id="sp-test",
            target_process_id="stream-test",
            interface_type=InterfaceType.ESCALATION, description="Test",
        )
        diagram = generate_mermaid_diagram(areas, streams, sps, [iface])
        assert "-->|escalation|" in diagram


class TestGenerateReport:
    def test_report_contains_header(self) -> None:
        areas, streams, sps, ifaces = _minimal_data()
        report = generate_report(areas, streams, sps, ifaces, [])
        assert "# InfoSec Process Harmonization Report" in report

    def test_report_contains_area_overview(self) -> None:
        areas, streams, sps, ifaces = _minimal_data()
        report = generate_report(areas, streams, sps, ifaces, [])
        assert "## Area Overview" in report
        assert "Test Area" in report

    def test_report_shows_subprocess_count(self) -> None:
        areas, streams, sps, ifaces = _minimal_data()
        report = generate_report(areas, streams, sps, ifaces, [])
        assert "**Subprocesses:** 1" in report

    def test_report_shows_not_yet_assessed(self) -> None:
        areas, streams, sps, ifaces = _minimal_data()
        report = generate_report(areas, streams, sps, ifaces, [])
        assert "Not yet assessed" in report

    def test_report_with_assessment_and_confidence(self) -> None:
        areas, streams, sps, ifaces = _minimal_data()
        assessment = Assessment(
            assessed_object_type=AssessedObjectType.STREAM,
            assessed_object_id="stream-test",
            answers=[
                AssessmentAnswer(
                    dimension=AlignmentDimension.REGULATORY_ALIGNMENT,
                    score=4, rationale="Good",
                ),
            ],
            result=HarmonizationResult(
                harmonization_score=0.75,
                classification=HarmonizationClassification.CENTRAL_METHOD_LOCAL_EXECUTION,
                rationale="Test rationale",
                recommendation="Test recommendation",
            ),
            completeness=CompletenessResult(
                completeness_score=65,
                confidence_level=ConfidenceLevel.MEDIUM,
                missing_items=["Missing type-specific questions"],
                rationale="65/100.",
            ),
            prioritization_result=PrioritizationResult(
                priority=HarmonizationPriority.HIGH,
                priority_score=0.80,
                rationale="High potential.",
            ),
        )
        report = generate_report(areas, streams, sps, ifaces, [assessment])
        assert "Central Method, Local Execution" in report
        assert "Confidence: Medium (65%)" in report
        assert "Management View" in report

    def test_assessment_gaps_section(self) -> None:
        areas, streams, sps, ifaces = _minimal_data()
        assessment = Assessment(
            assessed_object_type=AssessedObjectType.STREAM,
            assessed_object_id="stream-test",
            result=HarmonizationResult(
                harmonization_score=0.5,
                classification=HarmonizationClassification.PARTIALLY_HARMONIZABLE,
                rationale="R", recommendation="Rec",
            ),
            completeness=CompletenessResult(
                completeness_score=40,
                confidence_level=ConfidenceLevel.LOW,
                missing_items=["Missing base dimensions: maturity, local_necessity"],
                rationale="40/100.",
            ),
        )
        report = generate_report(areas, streams, sps, ifaces, [assessment])
        assert "Assessment Gaps" in report
        assert "Missing base dimensions" in report

    def test_gaps_show_unassessed_subprocesses(self) -> None:
        areas, streams, sps, ifaces = _minimal_data()
        # Stream assessed but subprocess not
        assessment = Assessment(
            assessed_object_type=AssessedObjectType.STREAM,
            assessed_object_id="stream-test",
            result=HarmonizationResult(
                harmonization_score=0.5,
                classification=HarmonizationClassification.PARTIALLY_HARMONIZABLE,
                rationale="R", recommendation="Rec",
            ),
        )
        report = generate_report(areas, streams, sps, ifaces, [assessment])
        assert "Assessment Gaps" in report
        assert "None of 1 subprocesses assessed" in report

    def test_report_shows_decision(self) -> None:
        areas, streams, sps, ifaces = _minimal_data()
        dr = DecisionResult(
            decision=Decision.CENTRALIZE_NOW,
            decision_rationale="High alignment, proceed.",
            blocking_factors=[],
            prerequisites=[],
            expected_benefit="Major efficiency gains",
            implementation_risk="Standard risks",
            target_operating_model=TargetOperatingModel.CENTRALIZED_EXECUTION,
            interface_complexity=InterfaceComplexityResult(
                complexity_score=0.15, interface_count=2, distinct_types=1,
                distinct_artifacts=3, cross_area_connections=0, rationale="Low complexity",
            ),
            harmonization_degree=HarmonizationDegree(
                harmonizable=True, harmonization_degree=0.9,
                standardizable=True, standardization_degree=0.85,
                centralizable=True, centralization_degree=0.8,
                rationale="High alignment",
            ),
            value_indicators=ValueIndicators(
                expected_business_value=ValueLevel.HIGH,
                regulatory_pressure=ValueLevel.MEDIUM,
                operational_impact=ValueLevel.HIGH,
                rationale="Good value",
            ),
        )
        assessment = Assessment(
            assessed_object_type=AssessedObjectType.STREAM,
            assessed_object_id="stream-test",
            result=HarmonizationResult(
                harmonization_score=0.9,
                classification=HarmonizationClassification.FULLY_CENTRALIZABLE,
                rationale="R", recommendation="Rec",
            ),
            decision_result=dr,
        )
        report = generate_report(areas, streams, sps, ifaces, [assessment])
        assert "**Decision: Centralize Now**" in report
        assert "Centralized Execution" in report
        assert "Harmonizable" in report
        assert "Standardizable" in report
        assert "Centralizable" in report
        assert "Decision Overview" in report

    def test_report_shows_why_not_centralized(self) -> None:
        areas, streams, sps, ifaces = _minimal_data()
        dr = DecisionResult(
            decision=Decision.STANDARDIZE_ONLY,
            decision_rationale="Centralization not viable.",
            blocking_factors=["Hard constraint: legal_local_difference"],
            prerequisites=[],
            expected_benefit="Moderate",
            implementation_risk="Low",
            target_operating_model=TargetOperatingModel.FEDERATED_STANDARDIZED,
            interface_complexity=InterfaceComplexityResult(
                complexity_score=0.3, interface_count=3, distinct_types=2,
                distinct_artifacts=5, cross_area_connections=1, rationale="Moderate",
            ),
            harmonization_degree=HarmonizationDegree(
                harmonizable=True, harmonization_degree=0.6,
                standardizable=True, standardization_degree=0.55,
                centralizable=False, centralization_degree=0.2,
                rationale="Constraints block centralization",
            ),
            value_indicators=ValueIndicators(
                expected_business_value=ValueLevel.MEDIUM,
                regulatory_pressure=ValueLevel.HIGH,
                operational_impact=ValueLevel.MEDIUM,
                rationale="Mixed",
            ),
        )
        assessment = Assessment(
            assessed_object_type=AssessedObjectType.STREAM,
            assessed_object_id="stream-test",
            result=HarmonizationResult(
                harmonization_score=0.55,
                classification=HarmonizationClassification.PARTIALLY_HARMONIZABLE,
                rationale="R", recommendation="Rec",
            ),
            decision_result=dr,
        )
        report = generate_report(areas, streams, sps, ifaces, [assessment])
        assert "Why NOT Centralized?" in report
        assert "Standardize Only" in report
        assert "Centralization degree too low" in report

    def test_report_shows_value_indicators(self) -> None:
        areas, streams, sps, ifaces = _minimal_data()
        dr = DecisionResult(
            decision=Decision.HARMONIZE_ONLY,
            decision_rationale="Limited scope.",
            blocking_factors=[],
            prerequisites=[],
            expected_benefit="Limited",
            implementation_risk="Low",
            target_operating_model=TargetOperatingModel.FEDERATED_STANDARDIZED,
            interface_complexity=InterfaceComplexityResult(
                complexity_score=0.1, interface_count=1, distinct_types=1,
                distinct_artifacts=1, cross_area_connections=0, rationale="Low",
            ),
            harmonization_degree=HarmonizationDegree(
                harmonizable=True, harmonization_degree=0.4,
                standardizable=False, standardization_degree=0.2,
                centralizable=False, centralization_degree=0.1,
                rationale="Low",
            ),
            value_indicators=ValueIndicators(
                expected_business_value=ValueLevel.LOW,
                regulatory_pressure=ValueLevel.LOW,
                operational_impact=ValueLevel.MEDIUM,
                rationale="Low overall",
            ),
        )
        assessment = Assessment(
            assessed_object_type=AssessedObjectType.STREAM,
            assessed_object_id="stream-test",
            result=HarmonizationResult(
                harmonization_score=0.4,
                classification=HarmonizationClassification.MINIMUM_STANDARD_ONLY,
                rationale="R", recommendation="Rec",
            ),
            decision_result=dr,
        )
        report = generate_report(areas, streams, sps, ifaces, [assessment])
        assert "Business Value: Low" in report
        assert "Operational Impact: Medium" in report

    def test_report_shows_alternatives(self) -> None:
        areas, streams, sps, ifaces = _minimal_data()
        dr = DecisionResult(
            decision=Decision.CENTRALIZE_NOW,
            decision_rationale="Proceed.",
            blocking_factors=[], prerequisites=[],
            expected_benefit="High", implementation_risk="Low",
            target_operating_model=TargetOperatingModel.CENTRALIZED_EXECUTION,
            interface_complexity=InterfaceComplexityResult(
                complexity_score=0.1, interface_count=1, distinct_types=1,
                distinct_artifacts=1, cross_area_connections=0, rationale="R",
            ),
            harmonization_degree=HarmonizationDegree(
                harmonizable=True, harmonization_degree=0.9,
                standardizable=True, standardization_degree=0.85,
                centralizable=True, centralization_degree=0.8,
                rationale="R",
            ),
            value_indicators=ValueIndicators(
                expected_business_value=ValueLevel.HIGH,
                regulatory_pressure=ValueLevel.MEDIUM,
                operational_impact=ValueLevel.HIGH,
                rationale="R",
            ),
            alternative_options=[
                AlternativeOption(
                    label="Centralize Now", description="Full centralization.",
                    is_recommended=True, pros=["Efficiency"], cons=["Effort"], risks=["Resistance"],
                ),
                AlternativeOption(
                    label="Phased", description="Phased approach.",
                    pros=["Lower risk"], cons=["Slower"],
                ),
            ],
            no_action_impact=NoActionImpact(
                regulatory_risk=ValueLevel.HIGH,
                operational_risk=ValueLevel.MEDIUM,
                inefficiency_cost=ValueLevel.HIGH,
                audit_exposure=ValueLevel.LOW,
                rationale="Compliance gaps remain.",
            ),
            implementation_impact=ImplementationImpact(
                implementation_complexity=ValueLevel.HIGH,
                process_changes=["Merge processes"],
                role_changes=["Central owner"],
                tool_changes=["Consolidate tools"],
                governance_changes=["Central board"],
                affected_roles=["Owner", "CISO"],
                change_magnitude=ValueLevel.HIGH,
            ),
            effort_estimate=EffortEstimate(
                person_months_bucket="6-12",
                implementation_duration=DurationCategory.MEDIUM,
                cost_category=ValueLevel.HIGH,
                rationale="Standard centralization.",
            ),
            governance=GovernanceMapping(
                decision_owner="CISO / Head of InfoSec",
                involved_stakeholders=["Owner", "CISO", "Director DE"],
                required_approvals=["CISO Approval"],
                decision_type=DecisionType.STRATEGIC,
            ),
            decision_trace=DecisionTrace(
                input_factors=["harmonization_score=0.90"],
                rules_triggered=["Rule 3: centralize_now"],
                constraints_applied=[],
                confidence_basis="Completeness 80/100 → high confidence.",
            ),
        )
        assessment = Assessment(
            assessed_object_type=AssessedObjectType.STREAM,
            assessed_object_id="stream-test",
            result=HarmonizationResult(
                harmonization_score=0.9,
                classification=HarmonizationClassification.FULLY_CENTRALIZABLE,
                rationale="R", recommendation="Rec",
            ),
            decision_result=dr,
        )
        report = generate_report(areas, streams, sps, ifaces, [assessment])
        # Alternative options
        assert "Decision Alternatives" in report
        assert "*(recommended)*" in report
        assert "Phased" in report
        # No-action impact
        assert "If We Do Nothing" in report
        assert "Regulatory Risk" in report
        # Implementation impact
        assert "Implementation Complexity" in report
        assert "Change Magnitude" in report
        assert "Required Changes" in report
        assert "Affected Roles" in report
        # Effort estimate
        assert "Effort Estimate" in report
        assert "6-12 PM" in report
        # Governance
        assert "Decision Owner" in report
        assert "CISO" in report
        assert "strategic" in report
        # Audit trace summary
        assert "Audit Trace Summary" in report
        assert "Rule 3" in report
        # Governance & Ownership global section
        assert "Governance & Ownership" in report

    def test_report_no_action_summary(self) -> None:
        areas, streams, sps, ifaces = _minimal_data()
        dr = DecisionResult(
            decision=Decision.STANDARDIZE_ONLY,
            decision_rationale="Std only.",
            blocking_factors=[], prerequisites=[],
            expected_benefit="Mod", implementation_risk="Low",
            target_operating_model=TargetOperatingModel.FEDERATED_STANDARDIZED,
            interface_complexity=InterfaceComplexityResult(
                complexity_score=0.2, interface_count=2, distinct_types=1,
                distinct_artifacts=3, cross_area_connections=0, rationale="R",
            ),
            harmonization_degree=HarmonizationDegree(
                harmonizable=True, harmonization_degree=0.6,
                standardizable=True, standardization_degree=0.55,
                centralizable=False, centralization_degree=0.2,
                rationale="R",
            ),
            value_indicators=ValueIndicators(
                expected_business_value=ValueLevel.MEDIUM,
                regulatory_pressure=ValueLevel.HIGH,
                operational_impact=ValueLevel.MEDIUM,
                rationale="R",
            ),
            no_action_impact=NoActionImpact(
                regulatory_risk=ValueLevel.HIGH,
                operational_risk=ValueLevel.MEDIUM,
                inefficiency_cost=ValueLevel.MEDIUM,
                audit_exposure=ValueLevel.HIGH,
                rationale="Audit findings likely.",
            ),
        )
        assessment = Assessment(
            assessed_object_type=AssessedObjectType.STREAM,
            assessed_object_id="stream-test",
            result=HarmonizationResult(
                harmonization_score=0.55,
                classification=HarmonizationClassification.PARTIALLY_HARMONIZABLE,
                rationale="R", recommendation="Rec",
            ),
            decision_result=dr,
        )
        report = generate_report(areas, streams, sps, ifaces, [assessment])
        assert "Inaction Risk Summary" in report
        assert "Streams with high inaction risk" in report

    def test_management_view_shows_confidence(self) -> None:
        areas, streams, sps, ifaces = _minimal_data()
        assessment = Assessment(
            assessed_object_type=AssessedObjectType.STREAM,
            assessed_object_id="stream-test",
            result=HarmonizationResult(
                harmonization_score=0.8,
                classification=HarmonizationClassification.CENTRAL_METHOD_LOCAL_EXECUTION,
                rationale="R", recommendation="Rec",
            ),
            completeness=CompletenessResult(
                completeness_score=80,
                confidence_level=ConfidenceLevel.HIGH,
                missing_items=[],
                rationale="80/100.",
            ),
            prioritization_result=PrioritizationResult(
                priority=HarmonizationPriority.HIGH,
                priority_score=0.85,
                rationale="Good.",
            ),
        )
        report = generate_report(areas, streams, sps, ifaces, [assessment])
        assert "High (80%)" in report
        assert "Recommended First Movers" in report

    def test_report_shows_calibration(self) -> None:
        areas, streams, sps, ifaces = _minimal_data()
        cal = CalibrationResult(
            outcomes_analyzed=5,
            accuracy_rate=0.6,
            deviations=[
                CalibrationDeviation(
                    dimension="effort", predicted="3-6",
                    actual="6-12", direction="underestimated",
                ),
            ],
            systematic_biases=["effort: systematically underestimated (3/5 cases)"],
            suggestions=[
                CalibrationSuggestion(
                    area="effort_estimate",
                    suggestion="Bump base effort buckets.",
                    evidence="effort: systematically underestimated",
                    priority=ValueLevel.HIGH,
                ),
            ],
            model_maturity=ModelMaturityLevel.CALIBRATED,
            confidence_adjustment=-0.10,
            rationale="Test calibration.",
            trust_score=TrustScoreResult(
                trust_score=0.75,
                validated_outcomes=3,
                high_relevance_correct=2,
                high_relevance_total=3,
                rationale="Good.",
            ),
            protected_rules=[
                ProtectedRule(
                    rule_id="hard_constraint_caps",
                    description="Hard constraints always cap",
                    reason="Governance guardrail",
                ),
            ],
            filtered_stats=FilteredCalibrationStats(
                total_outcomes=5,
                learning_relevant_outcomes=3,
                excluded_outcomes=2,
                excluded_reasons=["s2: political_decision"],
                unfiltered_accuracy=0.4,
                filtered_accuracy=0.6,
                rationale="3/5 used.",
            ),
            deviation_reasons_summary=["model_error: 2 outcome(s)", "political_decision: 2 outcome(s)"],
        )
        report = generate_report(areas, streams, sps, ifaces, [], calibration=cal)
        assert "Decision Accuracy & Calibration" in report
        assert "Calibrated" in report
        assert "60%" in report
        assert "Model vs Reality Gap" in report
        assert "Improvement Suggestions" in report
        assert "effort_estimate" in report
        assert "Prediction vs Actual" in report
        # Phase 7 sections
        assert "Trust Score" in report
        assert "0.75" in report
        assert "Filtered vs Unfiltered" in report
        assert "Learning-relevant outcomes" in report
        assert "Why Decisions Deviated" in report
        assert "model_error" in report
        assert "Protected Rules" in report
        assert "hard_constraint_caps" in report

    def test_report_no_calibration_when_none(self) -> None:
        areas, streams, sps, ifaces = _minimal_data()
        report = generate_report(areas, streams, sps, ifaces, [])
        assert "Decision Accuracy & Calibration" not in report

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
    AssessedObjectType,
    Assessment,
    AssessmentAnswer,
    CompletenessResult,
    ConfidenceLevel,
    HarmonizationClassification,
    HarmonizationPriority,
    HarmonizationResult,
    PrioritizationResult,
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

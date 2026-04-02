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
    HarmonizationClassification,
    HarmonizationPriority,
    HarmonizationResult,
    PrioritizationResult,
)
from harmonizer.reporting.markdown import generate_report, generate_mermaid_diagram


def _minimal_data() -> tuple[list[Area], list[Stream], list[SubProcess], list[ProcessInterface]]:
    area = Area(id="area-test", name="Test Area", description="Test area desc")
    stream = Stream(
        id="stream-test",
        area_id="area-test",
        name="Test Stream",
        stream_type=StreamType.PROCESS,
        description="Test",
        owner_role="Owner",
        country_scope=CountryScope.BOTH,
        tenant_scope=TenantScope.BOTH,
    )
    sp = SubProcess(
        id="sp-test",
        stream_id="stream-test",
        name="Test Sub",
        description="Test",
        purpose="Test",
        country_scope=CountryScope.BOTH,
        tenant_scope=TenantScope.BOTH,
    )
    return [area], [stream], [sp], []


class TestMermaidDiagram:
    def test_contains_subgraph_for_area(self) -> None:
        areas, streams, sps, ifaces = _minimal_data()
        diagram = generate_mermaid_diagram(areas, streams, sps, ifaces)
        assert "Test Area" in diagram
        assert "Test Stream" in diagram
        assert "Test Sub" in diagram

    def test_interface_arrow(self) -> None:
        areas, streams, sps, _ = _minimal_data()
        iface = ProcessInterface(
            id="iface-test",
            source_process_id="sp-test",
            target_process_id="stream-test",
            interface_type=InterfaceType.ESCALATION,
            description="Test",
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

    def test_report_contains_stream_with_type(self) -> None:
        areas, streams, sps, ifaces = _minimal_data()
        report = generate_report(areas, streams, sps, ifaces, [])
        assert "### Stream: Test Stream" in report
        assert "Process" in report

    def test_report_with_assessment_and_prioritization(self) -> None:
        areas, streams, sps, ifaces = _minimal_data()
        assessment = Assessment(
            assessed_object_type=AssessedObjectType.STREAM,
            assessed_object_id="stream-test",
            answers=[
                AssessmentAnswer(
                    dimension=AlignmentDimension.REGULATORY_ALIGNMENT,
                    score=4,
                    rationale="Good",
                ),
            ],
            result=HarmonizationResult(
                harmonization_score=0.75,
                classification=HarmonizationClassification.CENTRAL_METHOD_LOCAL_EXECUTION,
                rationale="Test rationale",
                recommendation="Test recommendation",
            ),
            prioritization_result=PrioritizationResult(
                priority=HarmonizationPriority.HIGH,
                priority_score=0.80,
                rationale="High potential.",
            ),
        )
        report = generate_report(areas, streams, sps, ifaces, [assessment])
        assert "Central Method, Local Execution" in report
        assert "0.75" in report
        assert "Management View" in report
        assert "High" in report

    def test_report_management_view_sorted(self) -> None:
        """Management view should sort by priority score descending."""
        areas, streams, sps, ifaces = _minimal_data()
        # Add a second stream
        stream2 = Stream(
            id="stream-test-2",
            area_id="area-test",
            name="Second Stream",
            stream_type=StreamType.SUPPORT_FUNCTION,
            description="Test2",
            owner_role="Owner2",
            country_scope=CountryScope.BOTH,
            tenant_scope=TenantScope.BOTH,
        )
        streams.append(stream2)

        a1 = Assessment(
            assessed_object_type=AssessedObjectType.STREAM,
            assessed_object_id="stream-test",
            result=HarmonizationResult(
                harmonization_score=0.50,
                classification=HarmonizationClassification.PARTIALLY_HARMONIZABLE,
                rationale="R1",
                recommendation="Rec1",
            ),
            prioritization_result=PrioritizationResult(
                priority=HarmonizationPriority.MEDIUM,
                priority_score=0.50,
                rationale="Medium.",
            ),
        )
        a2 = Assessment(
            assessed_object_type=AssessedObjectType.STREAM,
            assessed_object_id="stream-test-2",
            result=HarmonizationResult(
                harmonization_score=0.90,
                classification=HarmonizationClassification.FULLY_CENTRALIZABLE,
                rationale="R2",
                recommendation="Rec2",
            ),
            prioritization_result=PrioritizationResult(
                priority=HarmonizationPriority.HIGH,
                priority_score=0.85,
                rationale="High.",
            ),
        )
        report = generate_report(areas, streams, sps, ifaces, [a1, a2])
        # Second Stream should appear before Test Stream in management view
        idx1 = report.index("Second Stream")
        idx2 = report.index("Test Stream")
        # Find positions within the management view section
        mgmt_start = report.index("Management View")
        mgmt_idx1 = report.index("Second Stream", mgmt_start)
        mgmt_idx2 = report.index("Test Stream", mgmt_start)
        assert mgmt_idx1 < mgmt_idx2

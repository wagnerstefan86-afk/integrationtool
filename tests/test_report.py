"""Tests for Markdown report generation."""

from harmonizer.models.process import (
    CountryScope,
    MainProcess,
    SubProcess,
    ProcessInterface,
    InterfaceType,
    TenantScope,
)
from harmonizer.models.assessment import (
    AlignmentDimension,
    AssessedObjectType,
    Assessment,
    AssessmentAnswer,
    HarmonizationClassification,
    HarmonizationResult,
)
from harmonizer.reporting.markdown import generate_report, generate_mermaid_diagram


def _minimal_process_set() -> tuple[list[MainProcess], list[SubProcess], list[ProcessInterface]]:
    mp = MainProcess(
        id="stream-test",
        name="Test Stream",
        description="Test",
        owner_role="Owner",
        country_scope=CountryScope.BOTH,
        tenant_scope=TenantScope.BOTH,
    )
    sp = SubProcess(
        id="sp-test",
        main_process_id="stream-test",
        name="Test Sub",
        description="Test",
        purpose="Test",
        country_scope=CountryScope.BOTH,
        tenant_scope=TenantScope.BOTH,
    )
    return [mp], [sp], []


class TestMermaidDiagram:
    def test_contains_subgraph(self) -> None:
        mps, sps, ifaces = _minimal_process_set()
        diagram = generate_mermaid_diagram(mps, sps, ifaces)
        assert "subgraph" in diagram
        assert "Test Stream" in diagram
        assert "Test Sub" in diagram

    def test_interface_arrow(self) -> None:
        mps, sps, _ = _minimal_process_set()
        iface = ProcessInterface(
            id="iface-test",
            source_process_id="sp-test",
            target_process_id="stream-test",
            interface_type=InterfaceType.ESCALATION,
            description="Test",
        )
        diagram = generate_mermaid_diagram(mps, sps, [iface])
        assert "-->|escalation|" in diagram


class TestGenerateReport:
    def test_report_contains_header(self) -> None:
        mps, sps, ifaces = _minimal_process_set()
        report = generate_report(mps, sps, ifaces, [])
        assert "# InfoSec Process Harmonization Report" in report

    def test_report_contains_stream(self) -> None:
        mps, sps, ifaces = _minimal_process_set()
        report = generate_report(mps, sps, ifaces, [])
        assert "## Stream: Test Stream" in report

    def test_report_with_assessment(self) -> None:
        mps, sps, ifaces = _minimal_process_set()
        assessment = Assessment(
            assessed_object_type=AssessedObjectType.MAIN_PROCESS,
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
        )
        report = generate_report(mps, sps, ifaces, [assessment])
        assert "Central Method, Local Execution" in report
        assert "0.75" in report

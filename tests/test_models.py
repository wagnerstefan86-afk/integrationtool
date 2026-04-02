"""Tests for data model validation."""

import pytest
from pydantic import ValidationError

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
    AssessmentAnswer,
    ConfidenceLevel,
    CompletenessResult,
    HarmonizationPriority,
    PrioritizationInput,
    TypeSpecificAnswer,
)


class TestArea:
    def test_valid_creation(self) -> None:
        a = Area(id="test-area", name="Test Area")
        assert a.id == "test-area"

    def test_with_description(self) -> None:
        a = Area(id="a", name="A", description="Desc", notes="Note")
        assert a.notes == "Note"


class TestStream:
    def test_valid_creation(self) -> None:
        s = Stream(
            id="stream-test", area_id="area-test", name="Test Stream",
            stream_type=StreamType.PROCESS, description="A test stream.",
            owner_role="Test Owner", country_scope=CountryScope.BOTH,
            tenant_scope=TenantScope.SEPARATE,
        )
        assert s.stream_type == StreamType.PROCESS

    def test_all_stream_types(self) -> None:
        for st in StreamType:
            s = Stream(
                id=f"stream-{st.value}", area_id="area", name=st.value,
                stream_type=st, description="Test", owner_role="Owner",
                country_scope=CountryScope.BOTH, tenant_scope=TenantScope.BOTH,
            )
            assert s.stream_type == st

    def test_missing_required_field(self) -> None:
        with pytest.raises(ValidationError):
            Stream(
                id="stream-test", area_id="area-test", name="Test",
                stream_type=StreamType.PROCESS, owner_role="Owner",
                country_scope=CountryScope.BOTH, tenant_scope=TenantScope.SEPARATE,
            )


class TestSubProcess:
    def test_valid_creation(self) -> None:
        sp = SubProcess(
            id="sp-test", stream_id="stream-test", name="Test Subprocess",
            description="A test subprocess.", purpose="Testing.",
            country_scope=CountryScope.DE, tenant_scope=TenantScope.DE,
        )
        assert sp.stream_id == "stream-test"

    def test_interfaces_with_does_not_imply_parent(self) -> None:
        sp = SubProcess(
            id="sp-test", stream_id="stream-a", name="Test",
            description="Test", purpose="Test",
            country_scope=CountryScope.BOTH, tenant_scope=TenantScope.BOTH,
            interfaces_with=["stream-b", "sp-other"],
        )
        assert sp.stream_id == "stream-a"
        assert "stream-b" in sp.interfaces_with


class TestAssessmentAnswer:
    def test_score_range_valid(self) -> None:
        a = AssessmentAnswer(
            dimension=AlignmentDimension.REGULATORY_ALIGNMENT, score=3, rationale="Test",
        )
        assert a.score == 3

    def test_score_below_range(self) -> None:
        with pytest.raises(ValidationError):
            AssessmentAnswer(
                dimension=AlignmentDimension.REGULATORY_ALIGNMENT, score=0, rationale="Test",
            )

    def test_score_above_range(self) -> None:
        with pytest.raises(ValidationError):
            AssessmentAnswer(
                dimension=AlignmentDimension.REGULATORY_ALIGNMENT, score=6, rationale="Test",
            )


class TestTypeSpecificAnswer:
    def test_valid(self) -> None:
        a = TypeSpecificAnswer(question_id="proc_trigger_uniform", score=4, rationale="ok")
        assert a.question_id == "proc_trigger_uniform"

    def test_score_range(self) -> None:
        with pytest.raises(ValidationError):
            TypeSpecificAnswer(question_id="q1", score=0, rationale="bad")


class TestPrioritizationInput:
    def test_valid(self) -> None:
        p = PrioritizationInput(
            harmonization_potential=4, operational_relevance=3,
            governance_compliance_benefit=5, implementation_effort=2, dependencies=2,
        )
        assert p.harmonization_potential == 4

    def test_out_of_range(self) -> None:
        with pytest.raises(ValidationError):
            PrioritizationInput(
                harmonization_potential=6, operational_relevance=3,
                governance_compliance_benefit=5, implementation_effort=2, dependencies=2,
            )


class TestCompletenessResult:
    def test_valid(self) -> None:
        c = CompletenessResult(
            completeness_score=75, confidence_level=ConfidenceLevel.HIGH,
            missing_items=[], rationale="All good.",
        )
        assert c.confidence_level == ConfidenceLevel.HIGH

    def test_score_range(self) -> None:
        with pytest.raises(ValidationError):
            CompletenessResult(
                completeness_score=101, confidence_level=ConfidenceLevel.HIGH,
                rationale="bad",
            )


class TestProcessInterface:
    def test_valid_interface(self) -> None:
        pi = ProcessInterface(
            id="iface-test", source_process_id="sp-a", target_process_id="sp-b",
            interface_type=InterfaceType.TRIGGER, description="Test interface",
        )
        assert pi.interface_type == InterfaceType.TRIGGER


class TestAssessedObjectType:
    def test_stream_type(self) -> None:
        assert AssessedObjectType.STREAM == "stream"

    def test_subprocess_type(self) -> None:
        assert AssessedObjectType.SUBPROCESS == "subprocess"

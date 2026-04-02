"""Tests for data model validation."""

import pytest
from pydantic import ValidationError

from harmonizer.models.process import (
    CountryScope,
    InterfaceType,
    MainProcess,
    ProcessInterface,
    SubProcess,
    TenantScope,
)
from harmonizer.models.assessment import (
    AlignmentDimension,
    AssessedObjectType,
    Assessment,
    AssessmentAnswer,
    HarmonizationClassification,
)


class TestMainProcess:
    def test_valid_creation(self) -> None:
        mp = MainProcess(
            id="stream-test",
            name="Test Stream",
            description="A test stream.",
            owner_role="Test Owner",
            country_scope=CountryScope.BOTH,
            tenant_scope=TenantScope.SEPARATE,
        )
        assert mp.id == "stream-test"
        assert mp.country_scope == CountryScope.BOTH

    def test_missing_required_field(self) -> None:
        with pytest.raises(ValidationError):
            MainProcess(
                id="stream-test",
                name="Test Stream",
                # description missing
                owner_role="Test Owner",
                country_scope=CountryScope.BOTH,
                tenant_scope=TenantScope.SEPARATE,
            )


class TestSubProcess:
    def test_valid_creation(self) -> None:
        sp = SubProcess(
            id="sp-test",
            main_process_id="stream-test",
            name="Test Subprocess",
            description="A test subprocess.",
            purpose="Testing.",
            country_scope=CountryScope.DE,
            tenant_scope=TenantScope.DE,
        )
        assert sp.main_process_id == "stream-test"
        assert sp.interfaces_with == []

    def test_interfaces_with_does_not_imply_parent(self) -> None:
        """Verify that interfaces_with is a list of IDs, not parent references."""
        sp = SubProcess(
            id="sp-test",
            main_process_id="stream-a",
            name="Test",
            description="Test",
            purpose="Test",
            country_scope=CountryScope.BOTH,
            tenant_scope=TenantScope.BOTH,
            interfaces_with=["stream-b", "sp-other"],
        )
        # main_process_id is the ONLY parent relationship
        assert sp.main_process_id == "stream-a"
        # interfaces_with is separate
        assert "stream-b" in sp.interfaces_with


class TestAssessmentAnswer:
    def test_score_range_valid(self) -> None:
        a = AssessmentAnswer(
            dimension=AlignmentDimension.REGULATORY_ALIGNMENT,
            score=3,
            rationale="Test",
        )
        assert a.score == 3

    def test_score_below_range(self) -> None:
        with pytest.raises(ValidationError):
            AssessmentAnswer(
                dimension=AlignmentDimension.REGULATORY_ALIGNMENT,
                score=0,
                rationale="Test",
            )

    def test_score_above_range(self) -> None:
        with pytest.raises(ValidationError):
            AssessmentAnswer(
                dimension=AlignmentDimension.REGULATORY_ALIGNMENT,
                score=6,
                rationale="Test",
            )


class TestProcessInterface:
    def test_valid_interface(self) -> None:
        pi = ProcessInterface(
            id="iface-test",
            source_process_id="sp-a",
            target_process_id="sp-b",
            interface_type=InterfaceType.TRIGGER,
            description="Test interface",
        )
        assert pi.interface_type == InterfaceType.TRIGGER

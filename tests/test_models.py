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
    ActualImplementation,
    ActualImpact,
    AlignmentDimension,
    AssessedObjectType,
    AssessmentAnswer,
    CalibrationResult,
    ConfidenceLevel,
    CompletenessResult,
    Decision,
    DecisionOutcome,
    DeviationLevel,
    DeviationReason,
    DurationCategory,
    HarmonizationDegree,
    HarmonizationPriority,
    InterfaceComplexityResult,
    LearningRelevance,
    ModelMaturityLevel,
    OutcomeStatus,
    PrioritizationInput,
    TargetOperatingModel,
    TrustScoreResult,
    TypeSpecificAnswer,
    ValueIndicators,
    ValueLevel,
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


class TestDecisionEnum:
    def test_all_decisions(self) -> None:
        expected = {
            "centralize_now", "centralize_later", "harmonize_only",
            "standardize_only", "keep_local", "reassess_after_data_completion",
        }
        assert {d.value for d in Decision} == expected


class TestTargetOperatingModelEnum:
    def test_all_models(self) -> None:
        expected = {
            "centralized_execution", "central_method_local_execution",
            "federated_standardized", "local_independent",
        }
        assert {t.value for t in TargetOperatingModel} == expected


class TestHarmonizationDegree:
    def test_valid(self) -> None:
        hd = HarmonizationDegree(
            harmonizable=True, harmonization_degree=0.8,
            standardizable=True, standardization_degree=0.7,
            centralizable=False, centralization_degree=0.3,
            rationale="Test",
        )
        assert hd.harmonizable is True
        assert hd.centralizable is False

    def test_degree_range(self) -> None:
        with pytest.raises(ValidationError):
            HarmonizationDegree(
                harmonizable=True, harmonization_degree=1.5,
                standardizable=True, standardization_degree=0.5,
                centralizable=True, centralization_degree=0.5,
                rationale="bad",
            )


class TestInterfaceComplexityResult:
    def test_valid(self) -> None:
        ic = InterfaceComplexityResult(
            complexity_score=0.45,
            interface_count=5,
            distinct_types=3,
            distinct_artifacts=8,
            cross_area_connections=2,
            rationale="Test",
        )
        assert ic.complexity_score == 0.45

    def test_score_range(self) -> None:
        with pytest.raises(ValidationError):
            InterfaceComplexityResult(
                complexity_score=1.5,
                interface_count=0, distinct_types=0,
                distinct_artifacts=0, cross_area_connections=0,
                rationale="bad",
            )


class TestValueIndicators:
    def test_valid(self) -> None:
        vi = ValueIndicators(
            expected_business_value=ValueLevel.HIGH,
            regulatory_pressure=ValueLevel.MEDIUM,
            operational_impact=ValueLevel.LOW,
            rationale="Test",
        )
        assert vi.expected_business_value == ValueLevel.HIGH

    def test_all_value_levels(self) -> None:
        assert {v.value for v in ValueLevel} == {"low", "medium", "high"}


class TestOutcomeStatus:
    def test_all_statuses(self) -> None:
        assert {s.value for s in OutcomeStatus} == {
            "implemented", "rejected", "modified", "deferred",
        }


class TestDeviationLevel:
    def test_all_levels(self) -> None:
        assert {d.value for d in DeviationLevel} == {
            "none", "minor", "major", "complete_override",
        }


class TestModelMaturityLevel:
    def test_all_levels(self) -> None:
        assert {m.value for m in ModelMaturityLevel} == {
            "initial", "learning", "calibrated", "stable",
        }


class TestDecisionOutcome:
    def test_valid_minimal(self) -> None:
        o = DecisionOutcome(
            assessed_object_id="s1",
            outcome_status=OutcomeStatus.IMPLEMENTED,
            deviation=DeviationLevel.NONE,
        )
        assert o.outcome_status == OutcomeStatus.IMPLEMENTED

    def test_with_actuals(self) -> None:
        o = DecisionOutcome(
            assessed_object_id="s1",
            outcome_status=OutcomeStatus.MODIFIED,
            actual_implementation=ActualImplementation(
                actual_effort_bucket="3-6",
                actual_duration=DurationCategory.MEDIUM,
                actual_complexity=ValueLevel.MEDIUM,
            ),
            actual_impact=ActualImpact(
                business_value_realized=ValueLevel.HIGH,
                operational_improvement=ValueLevel.MEDIUM,
                issues_encountered=["Delay"],
            ),
            deviation=DeviationLevel.MINOR,
            lessons_learned=["Plan more buffer"],
        )
        assert o.actual_implementation.actual_effort_bucket == "3-6"
        assert len(o.lessons_learned) == 1


class TestCalibrationResult:
    def test_valid(self) -> None:
        cr = CalibrationResult(
            outcomes_analyzed=5,
            accuracy_rate=0.8,
            model_maturity=ModelMaturityLevel.CALIBRATED,
            confidence_adjustment=0.1,
            rationale="Good accuracy.",
        )
        assert cr.accuracy_rate == 0.8

    def test_confidence_adjustment_range(self) -> None:
        with pytest.raises(ValidationError):
            CalibrationResult(
                outcomes_analyzed=1,
                accuracy_rate=0.5,
                model_maturity=ModelMaturityLevel.LEARNING,
                confidence_adjustment=0.6,  # exceeds 0.5
                rationale="bad",
            )


class TestDeviationReason:
    def test_all_reasons(self) -> None:
        expected = {
            "model_error", "incomplete_data", "changed_context",
            "political_decision", "resource_constraint", "strategic_override",
        }
        assert {r.value for r in DeviationReason} == expected


class TestLearningRelevance:
    def test_all_levels(self) -> None:
        assert {l.value for l in LearningRelevance} == {"high", "medium", "low", "none"}


class TestDecisionOutcomeWithReason:
    def test_with_deviation_reason(self) -> None:
        o = DecisionOutcome(
            assessed_object_id="s1",
            outcome_status=OutcomeStatus.REJECTED,
            deviation=DeviationLevel.COMPLETE_OVERRIDE,
            deviation_reason=DeviationReason.POLITICAL_DECISION,
            learning_relevance=LearningRelevance.NONE,
        )
        assert o.deviation_reason == DeviationReason.POLITICAL_DECISION
        assert o.learning_relevance == LearningRelevance.NONE


class TestTrustScoreResult:
    def test_valid(self) -> None:
        ts = TrustScoreResult(
            trust_score=0.85,
            validated_outcomes=10,
            high_relevance_correct=8,
            high_relevance_total=10,
            rationale="Good.",
        )
        assert ts.trust_score == 0.85

    def test_score_range(self) -> None:
        with pytest.raises(ValidationError):
            TrustScoreResult(
                trust_score=1.5,
                validated_outcomes=0,
                high_relevance_correct=0,
                high_relevance_total=0,
                rationale="bad",
            )

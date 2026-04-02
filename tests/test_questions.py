"""Tests for stream-type-specific question definitions."""

from harmonizer.models.process import StreamType
from harmonizer.scoring.questions import (
    STREAM_TYPE_QUESTIONS,
    get_required_questions,
    get_required_question_ids,
)


class TestQuestionCatalog:
    def test_all_stream_types_have_questions(self) -> None:
        for st in StreamType:
            questions = get_required_questions(st)
            assert len(questions) >= 3, f"{st.value} should have at least 3 questions"

    def test_question_ids_unique_within_type(self) -> None:
        for st in StreamType:
            ids = get_required_question_ids(st)
            questions = get_required_questions(st)
            assert len(ids) == len(questions), f"{st.value} has duplicate question IDs"

    def test_question_ids_unique_globally(self) -> None:
        all_ids: set[str] = set()
        for st in StreamType:
            ids = get_required_question_ids(st)
            overlap = all_ids & ids
            assert not overlap, f"Duplicate question IDs across types: {overlap}"
            all_ids.update(ids)

    def test_process_questions_focus(self) -> None:
        questions = get_required_questions(StreamType.PROCESS)
        ids = {q.id for q in questions}
        assert "proc_trigger_uniform" in ids
        assert "proc_workflow_steps" in ids

    def test_governance_questions_focus(self) -> None:
        questions = get_required_questions(StreamType.GOVERNANCE_FUNCTION)
        ids = {q.id for q in questions}
        assert "gov_mandate_shared" in ids
        assert "gov_policy_model" in ids

    def test_service_domain_questions(self) -> None:
        questions = get_required_questions(StreamType.SERVICE_DOMAIN)
        ids = {q.id for q in questions}
        assert "svc_service_catalog" in ids

    def test_support_function_questions(self) -> None:
        questions = get_required_questions(StreamType.SUPPORT_FUNCTION)
        ids = {q.id for q in questions}
        assert "sup_process_standard" in ids

    def test_capability_domain_questions(self) -> None:
        questions = get_required_questions(StreamType.CAPABILITY_DOMAIN)
        ids = {q.id for q in questions}
        assert "cap_method_shared" in ids

    def test_program_domain_questions(self) -> None:
        questions = get_required_questions(StreamType.PROGRAM_DOMAIN)
        ids = {q.id for q in questions}
        assert "prg_steering_unified" in ids

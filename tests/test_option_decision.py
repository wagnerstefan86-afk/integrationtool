"""Tests for the option comparison decision engine and AS-IS completeness."""

import pytest

from harmonizer.models.process import is_as_is_complete, get_as_is_errors
from harmonizer.scoring.option_decision import compare_options, _score_option, _apply_delta_penalty


class TestAsIsCompleteness:
    def test_complete(self):
        assert is_as_is_complete({
            "description": "Process X",
            "steps": ["step 1", "step 2", "step 3"],
            "roles": ["CISO"],
            "tools": ["JIRA"],
        }) is True

    def test_missing_description(self):
        assert is_as_is_complete({
            "description": "",
            "steps": ["s1", "s2", "s3"],
            "roles": ["R"], "tools": ["T"],
        }) is False

    def test_too_few_steps(self):
        assert is_as_is_complete({
            "description": "X",
            "steps": ["s1", "s2"],
            "roles": ["R"], "tools": ["T"],
        }) is False

    def test_no_roles(self):
        assert is_as_is_complete({
            "description": "X",
            "steps": ["s1", "s2", "s3"],
            "roles": [], "tools": ["T"],
        }) is False

    def test_no_tools(self):
        assert is_as_is_complete({
            "description": "X",
            "steps": ["s1", "s2", "s3"],
            "roles": ["R"], "tools": [],
        }) is False

    def test_empty_dict(self):
        assert is_as_is_complete({}) is False

    def test_whitespace_ignored(self):
        assert is_as_is_complete({
            "description": "X",
            "steps": ["s1", " ", "s2", "s3"],  # whitespace-only entry skipped
            "roles": ["R"], "tools": ["T"],
        }) is True

    def test_errors_list(self):
        errors = get_as_is_errors({"description": "", "steps": ["s1"], "roles": [], "tools": []})
        assert len(errors) == 4
        assert any("description" in e for e in errors)
        assert any("steps" in e for e in errors)
        assert any("roles" in e for e in errors)
        assert any("tools" in e for e in errors)

    def test_no_errors_when_complete(self):
        errors = get_as_is_errors({
            "description": "X",
            "steps": ["s1", "s2", "s3"],
            "roles": ["R"], "tools": ["T"],
        })
        assert errors == []

    def test_backward_compatible_missing_fields(self):
        """Old data with only description still loads (incomplete but no crash)."""
        assert is_as_is_complete({"description": "Old data"}) is False
        errors = get_as_is_errors({"description": "Old data"})
        assert any("steps" in e for e in errors)
from harmonizer.models.process import StreamType


def _make_stream(stream_type="governance_function", delta=None, as_is=None):
    s = {
        "id": "test_stream",
        "area_id": "test_area",
        "name": "Test Stream",
        "stream_type": stream_type,
        "description": "test",
        "owner_role": "test",
        "country_scope": "BOTH",
        "tenant_scope": "BOTH",
    }
    if delta:
        s["delta"] = delta
    if as_is:
        s["as_is"] = as_is
    return s


def _make_assessment(option, scores, constraints=None):
    return {
        "assessed_object_id": "test_stream",
        "assessed_object_type": "stream",
        "target_option": option,
        "answers": [
            {"dimension": d, "score": s, "rationale": "test"}
            for d, s in scores.items()
        ],
        "hard_constraints": constraints or [],
        "status": "draft",
    }


ALL_DIMS_HIGH = {
    "regulatory_alignment": 5,
    "operational_alignment": 5,
    "tooling_alignment": 5,
    "governance_alignment": 5,
    "maturity": 5,
    "local_necessity": 5,
}

ALL_DIMS_LOW = {
    "regulatory_alignment": 1,
    "operational_alignment": 1,
    "tooling_alignment": 1,
    "governance_alignment": 1,
    "maturity": 1,
    "local_necessity": 1,
}

ALL_DIMS_MED = {
    "regulatory_alignment": 3,
    "operational_alignment": 3,
    "tooling_alignment": 3,
    "governance_alignment": 3,
    "maturity": 3,
    "local_necessity": 3,
}


class TestScoreOption:
    def test_high_scores(self):
        result = _score_option(
            _make_assessment("de_standard", ALL_DIMS_HIGH),
            StreamType.GOVERNANCE_FUNCTION,
        )
        assert result["score"] == 1.0
        assert not result["blocked"]

    def test_low_scores(self):
        result = _score_option(
            _make_assessment("de_standard", ALL_DIMS_LOW),
            StreamType.GOVERNANCE_FUNCTION,
        )
        assert result["score"] == 0.0

    def test_blocked_by_constraint(self):
        result = _score_option(
            _make_assessment("de_standard", ALL_DIMS_HIGH, ["insufficient_documentation"]),
            StreamType.GOVERNANCE_FUNCTION,
        )
        assert result["blocked"]


class TestDeltaPenalty:
    def test_no_delta(self):
        assert _apply_delta_penalty(0.8, {}, "de_standard") == 0.8

    def test_high_delta(self):
        delta = {
            "structural_diff": "high",
            "tooling_gap": "high",
            "regulatory_gap": "high",
            "role_model_diff": "high",
        }
        adjusted = _apply_delta_penalty(0.8, delta, "de_standard")
        assert adjusted < 0.8
        # Extra penalty for adoption options with high reg gap
        adjusted_central = _apply_delta_penalty(0.8, delta, "central")
        assert adjusted_central > adjusted

    def test_floor_at_zero(self):
        delta = {
            "structural_diff": "high",
            "tooling_gap": "high",
            "regulatory_gap": "high",
            "role_model_diff": "high",
        }
        assert _apply_delta_penalty(0.1, delta, "de_standard") >= 0.0


class TestCompareOptions:
    def test_selects_highest_scoring(self):
        stream = _make_stream()
        assessments = [
            _make_assessment("de_standard", ALL_DIMS_HIGH),
            _make_assessment("at_standard", ALL_DIMS_MED),
            _make_assessment("central", ALL_DIMS_MED),
        ]
        result = compare_options(stream, assessments)
        assert result["recommended_option"] == "de_standard"
        assert len(result["option_scores"]) == 3
        assert len(result["discarded_options"]) == 2

    def test_all_blocked(self):
        stream = _make_stream()
        assessments = [
            _make_assessment("de_standard", ALL_DIMS_HIGH, ["insufficient_documentation"]),
            _make_assessment("at_standard", ALL_DIMS_HIGH, ["insufficient_documentation"]),
        ]
        result = compare_options(stream, assessments)
        assert result["recommended_option"] is None
        assert len(result["blockers"]) > 0

    def test_skips_blocked_selects_next(self):
        stream = _make_stream()
        assessments = [
            _make_assessment("de_standard", ALL_DIMS_HIGH, ["insufficient_documentation"]),
            _make_assessment("at_standard", ALL_DIMS_HIGH),
            _make_assessment("central", ALL_DIMS_MED),
        ]
        result = compare_options(stream, assessments)
        assert result["recommended_option"] == "at_standard"
        blocked = [d["option"] for d in result["discarded_options"]
                   if "constraint" in d.get("reason", "").lower() or "blocked" in d.get("reason", "").lower()]
        assert "de_standard" in blocked

    def test_delta_influences_recommendation(self):
        stream = _make_stream(delta={
            "structural_diff": "high",
            "tooling_gap": "high",
            "regulatory_gap": "high",
            "role_model_diff": "high",
        })
        # All options have same raw score
        assessments = [
            _make_assessment("de_standard", ALL_DIMS_HIGH),
            _make_assessment("at_standard", ALL_DIMS_HIGH),
            _make_assessment("central", ALL_DIMS_HIGH),
        ]
        result = compare_options(stream, assessments)
        details = result["option_details"]
        # Central should have higher adjusted score (less reg gap penalty)
        assert details["central"]["adjusted_score"] > details["de_standard"]["adjusted_score"]

    def test_empty_assessments(self):
        stream = _make_stream()
        result = compare_options(stream, [])
        assert result["recommended_option"] is None

    def test_legacy_assessment_treated_as_central(self):
        stream = _make_stream()
        legacy = {
            "assessed_object_id": "test_stream",
            "assessed_object_type": "stream",
            "answers": [
                {"dimension": d, "score": s, "rationale": "test"}
                for d, s in ALL_DIMS_HIGH.items()
            ],
            "hard_constraints": [],
            "status": "draft",
        }
        result = compare_options(stream, [legacy])
        assert result["recommended_option"] == "central"

    def test_missing_options_warning(self):
        stream = _make_stream()
        assessments = [
            _make_assessment("de_standard", ALL_DIMS_HIGH),
        ]
        result = compare_options(stream, assessments)
        assert result["recommended_option"] == "de_standard"
        assert any("missing" in b.lower() for b in result["blockers"])

    def test_prerequisites_for_adoption(self):
        stream = _make_stream(delta={"tooling_gap": "high", "role_model_diff": "high"})
        assessments = [
            _make_assessment("de_standard", ALL_DIMS_HIGH),
            _make_assessment("at_standard", ALL_DIMS_MED),
        ]
        result = compare_options(stream, assessments)
        assert result["recommended_option"] == "de_standard"
        assert any("tooling" in p.lower() for p in result["prerequisites"])
        assert any("role" in p.lower() for p in result["prerequisites"])

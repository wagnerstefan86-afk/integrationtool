"""Tests for the structured process analysis module and API."""

import pytest

from harmonizer.process_analysis import (
    DEFAULT_PROCESS_PHASES,
    GUIDE_QUESTIONS,
    WHY_CATEGORIES,
    EVIDENCE_TYPES,
    REVIEW_STATUSES,
    DELTA_DIMENSIONS,
    DELTA_NATURES,
    CONSTRAINT_TYPES,
    RECOMMENDATION_TYPES,
    scaffold_analysis,
    score_variant_completeness,
    score_step_completeness,
    score_analysis_completeness,
    compute_step_delta,
    compute_analysis_deltas,
    compute_analysis_summary,
    assess_why_quality,
    assess_evidence_strength,
    validate_review_status,
    generate_recommendations,
)


# ─── Unit tests: model and logic ─────────────────────────────────────────────

class TestDefaultPhases:
    def test_six_phases(self):
        assert len(DEFAULT_PROCESS_PHASES) == 6

    def test_sorted(self):
        orders = [p["sort_order"] for p in DEFAULT_PROCESS_PHASES]
        assert orders == sorted(orders)

    def test_each_has_guide_questions(self):
        for phase in DEFAULT_PROCESS_PHASES:
            assert phase["step_id"] in GUIDE_QUESTIONS
            assert len(GUIDE_QUESTIONS[phase["step_id"]]) >= 3

    def test_every_phase_has_why_question(self):
        for step_id, qs in GUIDE_QUESTIONS.items():
            why_qs = [q for q in qs if q["maps_to"] == "why_is_it_done_this_way"]
            assert len(why_qs) >= 1, f"Phase {step_id} missing WHY question"


class TestScaffold:
    def test_creates_structure(self):
        a = scaffold_analysis("test_stream", "Test", ["DE", "AT"])
        assert a["stream_id"] == "test_stream"
        assert a["status"] == "draft"
        assert len(a["process_steps"]) == 6
        assert a["entities"] == ["DE", "AT"]

    def test_each_step_has_variants(self):
        a = scaffold_analysis("s", "S", ["DE", "AT", "CH"])
        for step in a["process_steps"]:
            assert len(step["entity_variants"]) == 3
            eids = {v["entity_id"] for v in step["entity_variants"]}
            assert eids == {"DE", "AT", "CH"}


class TestVariantCompleteness:
    def test_empty_variant(self):
        result = score_variant_completeness({})
        # Empty variant scores low (weak WHY gives 4 pts baseline)
        assert result["score"] <= 10
        assert "description" in result["missing_fields"]
        assert any("WHY" in w for w in result["warnings"])
        assert result["why_quality"] == "weak"
        assert result["evidence_strength"] == "none"
        assert result["review_status"] == "draft"

    def test_complete_variant(self):
        v = {
            "description": "Full description",
            "systems_used": ["ServiceNow"],
            "roles_involved": [{"role": "CISO"}],
            "why_is_it_done_this_way": ["Regulatory requirement from NIS2"],
            "why_categories": ["regulatory_requirement"],
            "trigger": "Alert",
            "input_channels": ["email"],
            "output": "Ticket",
            "sla_or_target": "4h",
            "evidence_or_examples": ["doc"],
            "evidence_references": [
                {"id": "ev1", "type": "document", "title": "NIS2 policy", "confidence": "high"},
            ],
            "pain_points": ["slow"],
        }
        result = score_variant_completeness(v)
        assert result["score"] >= 80
        assert result["missing_fields"] == []
        assert result["why_quality"] == "strong"
        assert result["evidence_strength"] == "medium"  # 1 doc, not interview-only

    def test_missing_why_flagged(self):
        v = {
            "description": "Desc",
            "systems_used": ["SN"],
            "roles_involved": [{"role": "R"}],
            "why_is_it_done_this_way": [],
        }
        result = score_variant_completeness(v)
        assert "why_is_it_done_this_way" in result["missing_fields"]
        assert any("WHY" in w for w in result["warnings"])

    def test_multiple_channels_without_why_warns(self):
        v = {
            "description": "D",
            "systems_used": ["S"],
            "roles_involved": [{"role": "R"}],
            "input_channels": ["email", "phone", "portal"],
            "why_is_it_done_this_way": [],
        }
        result = score_variant_completeness(v)
        assert any("channel" in w.lower() for w in result["warnings"])


class TestStepDelta:
    def _step(self, variants):
        return {
            "step_id": "intake",
            "step_name": "Intake",
            "entity_variants": variants,
        }

    def test_no_variants(self):
        assert compute_step_delta(self._step([])) == []

    def test_single_variant(self):
        assert compute_step_delta(self._step([{"entity_id": "DE"}])) == []

    def test_identical_variants(self):
        v = {"entity_id": "DE", "systems_used": ["SN"], "roles_involved": ["R"],
             "why_is_it_done_this_way": ["reason"]}
        v2 = {**v, "entity_id": "AT"}
        deltas = compute_step_delta(self._step([v, v2]))
        # No system/role/channel deltas, no missing WHY
        assert len(deltas) == 0

    def test_different_systems_detected(self):
        de = {"entity_id": "DE", "systems_used": ["ServiceNow"],
              "why_is_it_done_this_way": ["legacy"]}
        at = {"entity_id": "AT", "systems_used": ["Navision"],
              "why_is_it_done_this_way": ["local"]}
        deltas = compute_step_delta(self._step([de, at]))
        sys_deltas = [d for d in deltas if d["delta_type"] == "system_difference"]
        assert len(sys_deltas) == 1
        assert sys_deltas[0]["impact"] == "high"
        assert "servicenow" in sys_deltas[0]["description"].lower()
        # New fields present
        assert sys_deltas[0]["delta_dimension"] == "tooling"
        assert sys_deltas[0]["delta_nature"] in DELTA_NATURES
        assert sys_deltas[0]["constraint_type"] in CONSTRAINT_TYPES
        assert "needs_management_decision" in sys_deltas[0]

    def test_missing_why_detected(self):
        de = {"entity_id": "DE", "why_is_it_done_this_way": ["reason"]}
        at = {"entity_id": "AT", "why_is_it_done_this_way": []}
        deltas = compute_step_delta(self._step([de, at]))
        why_deltas = [d for d in deltas if d["delta_type"] == "missing_rationale"]
        assert len(why_deltas) == 1
        assert "AT" in why_deltas[0]["description"]

    def test_partial_role_overlap(self):
        de = {"entity_id": "DE",
              "roles_involved": [{"role": "CISO"}, {"role": "DPO"}],
              "why_is_it_done_this_way": ["r"]}
        at = {"entity_id": "AT",
              "roles_involved": [{"role": "CISO"}, {"role": "Local ISO"}],
              "why_is_it_done_this_way": ["r"]}
        deltas = compute_step_delta(self._step([de, at]))
        role_deltas = [d for d in deltas if d["delta_type"] == "role_difference"]
        assert len(role_deltas) == 1
        assert role_deltas[0]["impact"] == "medium"


class TestAnalysisSummary:
    def test_seed_data_loads(self):
        """Verify the seed data produces a valid summary with new decision support fields."""
        import yaml
        from pathlib import Path
        data_path = Path(__file__).parent.parent / "data" / "examples" / "process_analyses.yaml"
        with open(data_path) as f:
            data = yaml.safe_load(f)
        analysis = data["analyses"][0]
        assert analysis["stream_id"] == "request_incident_mgmt"

        summary = compute_analysis_summary(analysis)
        assert summary["total_steps"] == 6
        assert set(summary["entities"]) == {"DE", "AT"}
        assert summary["completeness_score"] > 0
        assert summary["total_deltas"] > 0
        assert summary["high_impact_deltas"] > 0  # ServiceNow vs Navision
        # New decision support fields
        assert "standardization_candidates_count" in summary
        assert "likely_keep_local_count" in summary
        assert "control_gaps_count" in summary
        assert "evidence_gaps_count" in summary
        assert "weak_why_count" in summary
        assert "management_decisions_needed_count" in summary
        assert "tendency" in summary
        assert summary["tendency"] in ("harmonizable", "partially_harmonizable", "strongly_local", "insufficiently_captured")
        assert "recommendations" in summary
        assert isinstance(summary["recommendations"], list)
        assert "review_status_counts" in summary
        assert "top_differences" in summary
        assert "open_gaps" in summary

    def test_seed_data_deltas(self):
        import yaml
        from pathlib import Path
        data_path = Path(__file__).parent.parent / "data" / "examples" / "process_analyses.yaml"
        with open(data_path) as f:
            data = yaml.safe_load(f)
        analysis = data["analyses"][0]
        deltas = compute_analysis_deltas(analysis)
        assert len(deltas) > 5
        # Should detect system differences (ServiceNow vs Navision)
        sys_deltas = [d for d in deltas if d["delta_type"] == "system_difference"]
        assert len(sys_deltas) >= 4  # Different in most steps


# ─── WHY quality tests ───────────────────────────────────────────────────────

class TestWhyQuality:
    def test_no_why_at_all(self):
        result = assess_why_quality({})
        assert result["quality"] == "weak"
        assert not result["has_freetext"]
        assert result["categories"] == []

    def test_strong_regulatory(self):
        v = {
            "why_is_it_done_this_way": ["Required by NIS2"],
            "why_categories": ["regulatory_requirement"],
        }
        result = assess_why_quality(v)
        assert result["quality"] == "strong"

    def test_strong_legal(self):
        v = {
            "why_is_it_done_this_way": ["DSGVO mandates this"],
            "why_categories": ["legal_constraint"],
        }
        assert assess_why_quality(v)["quality"] == "strong"

    def test_strong_technical(self):
        v = {
            "why_is_it_done_this_way": ["Legacy API limitation"],
            "why_categories": ["technical_constraint"],
        }
        assert assess_why_quality(v)["quality"] == "strong"

    def test_weak_historical_only(self):
        v = {
            "why_is_it_done_this_way": ["War schon immer so"],
            "why_categories": ["historical_growth"],
        }
        result = assess_why_quality(v)
        assert result["quality"] == "weak"
        assert any("historical_growth" in w for w in result["warnings"])

    def test_weak_unknown_only(self):
        v = {
            "why_is_it_done_this_way": ["Keine Ahnung"],
            "why_categories": ["unknown_or_unclear"],
        }
        result = assess_why_quality(v)
        assert result["quality"] == "weak"

    def test_medium_with_freetext_no_categories(self):
        v = {"why_is_it_done_this_way": ["Some reason given"]}
        result = assess_why_quality(v)
        assert result["quality"] == "medium"
        assert any("no why_category" in w.lower() for w in result["warnings"])

    def test_medium_capacity(self):
        v = {
            "why_is_it_done_this_way": ["Not enough staff"],
            "why_categories": ["capacity_or_staffing"],
        }
        assert assess_why_quality(v)["quality"] == "medium"

    def test_explicit_override(self):
        v = {
            "why_is_it_done_this_way": ["Reason"],
            "why_categories": ["historical_growth"],
            "why_quality": "strong",  # explicit override
        }
        assert assess_why_quality(v)["quality"] == "strong"

    def test_mixed_strong_and_weak_categories(self):
        v = {
            "why_is_it_done_this_way": ["Mix"],
            "why_categories": ["historical_growth", "regulatory_requirement"],
        }
        result = assess_why_quality(v)
        assert result["quality"] == "strong"  # regulatory trumps historical

    def test_invalid_category_ignored(self):
        v = {
            "why_is_it_done_this_way": ["X"],
            "why_categories": ["made_up_category", "regulatory_requirement"],
        }
        result = assess_why_quality(v)
        assert result["categories"] == ["regulatory_requirement"]


# ─── Evidence strength tests ─────────────────────────────────────────────────

class TestEvidenceStrength:
    def test_no_evidence(self):
        result = assess_evidence_strength({})
        assert result["strength"] == "low"
        assert result["count"] == 0
        assert not result["has_structured"]

    def test_legacy_evidence_only(self):
        v = {"evidence_or_examples": ["ticket SN-123", "email thread"]}
        result = assess_evidence_strength(v)
        assert result["strength"] == "low"
        assert result["count"] == 2
        assert not result["has_structured"]
        assert any("legacy" in w.lower() for w in result["warnings"])

    def test_single_interview(self):
        v = {"evidence_references": [
            {"id": "e1", "type": "interview", "title": "Team lead", "confidence": "medium"},
        ]}
        result = assess_evidence_strength(v)
        assert result["strength"] == "low"  # interview-only = low
        assert any("interview" in w.lower() for w in result["warnings"])

    def test_document_plus_interview(self):
        v = {"evidence_references": [
            {"id": "e1", "type": "interview", "title": "Lead", "confidence": "medium"},
            {"id": "e2", "type": "document", "title": "SOP v2", "confidence": "high"},
        ]}
        result = assess_evidence_strength(v)
        assert result["strength"] == "high"  # 2 refs, not interview-only, 1 high confidence

    def test_single_document(self):
        v = {"evidence_references": [
            {"id": "e1", "type": "document", "title": "Policy doc", "confidence": "medium"},
        ]}
        result = assess_evidence_strength(v)
        assert result["strength"] == "medium"  # 1 ref, not interview-only

    def test_explicit_strength_override(self):
        v = {
            "evidence_references": [{"id": "e1", "type": "interview", "title": "X"}],
            "evidence_strength": "high",
        }
        result = assess_evidence_strength(v)
        assert result["strength"] == "high"


# ─── Review status validation tests ─────────────────────────────────────────

class TestReviewValidation:
    def test_invalid_status_rejected(self):
        result = validate_review_status({}, "bogus")
        assert not result["valid"]

    def test_draft_to_captured_allowed(self):
        result = validate_review_status({"review_status": "draft"}, "captured")
        assert result["valid"]

    def test_approved_needs_description(self):
        v = {"description": "", "systems_used": ["S"], "roles_involved": [{"role": "R"}],
             "why_is_it_done_this_way": ["reason"],
             "evidence_references": [{"id": "e1", "type": "document", "title": "doc"}]}
        result = validate_review_status(v, "approved")
        assert not result["valid"]
        assert "description" in result["reason"]

    def test_approved_needs_evidence(self):
        v = {"description": "D", "systems_used": ["S"], "roles_involved": [{"role": "R"}],
             "why_is_it_done_this_way": ["reason"]}
        result = validate_review_status(v, "approved")
        assert not result["valid"]
        assert "evidence" in result["reason"].lower()

    def test_approved_needs_why(self):
        v = {"description": "D", "systems_used": ["S"], "roles_involved": [{"role": "R"}],
             "why_is_it_done_this_way": [],
             "evidence_references": [{"id": "e1", "type": "document", "title": "doc"}]}
        result = validate_review_status(v, "approved")
        assert not result["valid"]
        assert "why" in result["reason"].lower()

    def test_approved_succeeds_when_complete(self):
        v = {"description": "Full desc", "systems_used": ["SN"], "roles_involved": [{"role": "CISO"}],
             "why_is_it_done_this_way": ["regulatory reason"],
             "why_categories": ["regulatory_requirement"],
             "evidence_references": [{"id": "e1", "type": "document", "title": "Policy"}]}
        result = validate_review_status(v, "approved")
        assert result["valid"]

    def test_challenged_always_allowed(self):
        result = validate_review_status({"review_status": "captured"}, "challenged")
        assert result["valid"]


# ─── Delta classification tests ──────────────────────────────────────────────

class TestDeltaClassification:
    def _step(self, step_id, variants):
        return {"step_id": step_id, "step_name": step_id.title(), "entity_variants": variants}

    def test_system_delta_has_dimension(self):
        de = {"entity_id": "DE", "systems_used": ["ServiceNow"],
              "why_is_it_done_this_way": ["r"]}
        at = {"entity_id": "AT", "systems_used": ["Navision"],
              "why_is_it_done_this_way": ["r"]}
        deltas = compute_step_delta(self._step("intake", [de, at]))
        sys_d = [d for d in deltas if d["delta_type"] == "system_difference"]
        assert len(sys_d) == 1
        assert sys_d[0]["delta_dimension"] == "tooling"
        # intake with different systems → operationally_significant
        assert sys_d[0]["delta_nature"] == "operationally_significant"

    def test_channel_delta_dimension(self):
        de = {"entity_id": "DE", "input_channels": ["portal", "email"],
              "why_is_it_done_this_way": ["r"]}
        at = {"entity_id": "AT", "input_channels": ["phone"],
              "why_is_it_done_this_way": ["r"]}
        deltas = compute_step_delta(self._step("intake", [de, at]))
        ch_d = [d for d in deltas if d["delta_type"] == "channel_difference"]
        assert ch_d[0]["delta_dimension"] == "channel"

    def test_regulatory_constraint_detected(self):
        de = {"entity_id": "DE", "systems_used": ["PagerDuty"],
              "why_is_it_done_this_way": ["NIS2 mandates it"],
              "why_categories": ["regulatory_requirement"]}
        at = {"entity_id": "AT", "systems_used": ["email"],
              "why_is_it_done_this_way": ["r"]}
        deltas = compute_step_delta(self._step("escalation", [de, at]))
        sys_d = [d for d in deltas if d["delta_type"] == "system_difference"]
        assert sys_d[0]["constraint_type"] == "regulatory"

    def test_control_gap_detected_escalation(self):
        de = {"entity_id": "DE", "description": "Formal escalation via PagerDuty",
              "systems_used": ["PagerDuty"], "why_is_it_done_this_way": ["r"]}
        at = {"entity_id": "AT", "description": "No formal escalation process, ad-hoc calls",
              "systems_used": ["email"], "why_is_it_done_this_way": ["r"]}
        deltas = compute_step_delta(self._step("escalation", [de, at]))
        gaps = [d for d in deltas if d["delta_type"] == "control_gap"]
        assert len(gaps) >= 1
        assert gaps[0]["delta_nature"] == "control_relevant"
        assert gaps[0]["needs_management_decision"] is True

    def test_needs_management_decision_flag(self):
        de = {"entity_id": "DE", "systems_used": ["ServiceNow"],
              "why_is_it_done_this_way": ["r"]}
        at = {"entity_id": "AT", "systems_used": ["Navision"],
              "why_is_it_done_this_way": ["r"]}
        deltas = compute_step_delta(self._step("processing", [de, at]))
        sys_d = [d for d in deltas if d["delta_type"] == "system_difference"]
        # processing + system diff → operationally_significant → needs mgmt decision
        assert sys_d[0]["needs_management_decision"] is True


# ─── Recommendation engine tests ─────────────────────────────────────────────

class TestRecommendations:
    def _analysis(self, steps):
        return {"stream_id": "test", "process_steps": steps, "entities": ["DE", "AT"]}

    def _step(self, step_id, de_variant, at_variant):
        return {"step_id": step_id, "step_name": step_id.title(), "sort_order": 1,
                "entity_variants": [de_variant, at_variant]}

    def test_control_gap_generates_remediate(self):
        de = {"entity_id": "DE", "description": "Formal reporting via PowerBI",
              "systems_used": ["PowerBI"], "why_is_it_done_this_way": ["governance"]}
        at = {"entity_id": "AT", "description": "No formal reporting at all, ad-hoc Excel",
              "systems_used": ["Excel"], "why_is_it_done_this_way": ["r"]}
        analysis = self._analysis([self._step("reporting", de, at)])
        recs = generate_recommendations(analysis)
        remediate = [r for r in recs if r["recommendation_type"] == "remediate_control_gap"]
        assert len(remediate) >= 1
        assert remediate[0]["priority"] == "high"

    def test_missing_why_generates_investigate(self):
        de = {"entity_id": "DE", "why_is_it_done_this_way": ["reason"]}
        at = {"entity_id": "AT", "why_is_it_done_this_way": []}
        analysis = self._analysis([self._step("intake", de, at)])
        recs = generate_recommendations(analysis)
        investigate = [r for r in recs if r["recommendation_type"] == "investigate_further"]
        assert len(investigate) >= 1

    def test_hard_constraint_generates_keep_local(self):
        de = {"entity_id": "DE", "systems_used": ["PagerDuty"],
              "why_is_it_done_this_way": ["NIS2"],
              "why_categories": ["regulatory_requirement"]}
        at = {"entity_id": "AT", "systems_used": ["email"],
              "why_is_it_done_this_way": ["r"]}
        analysis = self._analysis([self._step("intake", de, at)])
        recs = generate_recommendations(analysis)
        keep = [r for r in recs if r["recommendation_type"] == "keep_local"]
        assert len(keep) >= 1
        assert keep[0]["priority"] == "low"

    def test_operational_diff_no_constraint_generates_harmonize(self):
        de = {"entity_id": "DE", "systems_used": ["ServiceNow"],
              "why_is_it_done_this_way": ["standard tool"],
              "why_categories": ["deliberate_local_optimization"]}
        at = {"entity_id": "AT", "systems_used": ["Navision"],
              "why_is_it_done_this_way": ["only system available"],
              "why_categories": ["tooling_or_license_limitation"]}
        analysis = self._analysis([self._step("intake", de, at)])
        recs = generate_recommendations(analysis)
        # Should produce harmonize or keep_local (technical constraint)
        types = {r["recommendation_type"] for r in recs}
        assert "harmonize" in types or "keep_local" in types

    def test_recommendation_has_required_fields(self):
        de = {"entity_id": "DE", "systems_used": ["SN"],
              "why_is_it_done_this_way": ["r"]}
        at = {"entity_id": "AT", "systems_used": ["Nav"],
              "why_is_it_done_this_way": ["r"]}
        analysis = self._analysis([self._step("intake", de, at)])
        recs = generate_recommendations(analysis)
        assert len(recs) > 0
        for r in recs:
            assert "id" in r
            assert "title" in r
            assert r["recommendation_type"] in RECOMMENDATION_TYPES
            assert "rationale" in r
            assert "based_on_step_ids" in r
            assert "based_on_delta_ids" in r
            assert r["priority"] in ("high", "medium", "low")
            assert "assumptions" in r
            assert "blockers" in r
            assert "expected_benefit" in r
            assert r["implementation_complexity"] in ("low", "medium", "high")

    def test_deduplication(self):
        de = {"entity_id": "DE", "systems_used": ["SN"], "input_channels": ["portal"],
              "why_is_it_done_this_way": ["r"]}
        at = {"entity_id": "AT", "systems_used": ["Nav"], "input_channels": ["email"],
              "why_is_it_done_this_way": ["r"]}
        analysis = self._analysis([self._step("intake", de, at)])
        recs = generate_recommendations(analysis)
        # Same type + same step should be deduplicated
        keys = [f"{r['recommendation_type']}::{','.join(r['based_on_step_ids'])}" for r in recs]
        assert len(keys) == len(set(keys)), "Duplicate recommendations found"


# ─── Scaffold new fields tests ───────────────────────────────────────────────

class TestScaffoldNewFields:
    def test_variant_has_new_fields(self):
        a = scaffold_analysis("s", "S", ["DE"])
        v = a["process_steps"][0]["entity_variants"][0]
        assert v["why_categories"] == []
        assert v["why_quality"] == ""
        assert v["why_review_note"] == ""
        assert v["evidence_references"] == []
        assert v["evidence_strength"] == ""
        assert v["review_status"] == "draft"
        assert v["review_comment"] == ""
        assert v["reviewed_by"] == ""
        assert v["reviewed_at"] == ""


# ─── API tests ────────────────────────────────────────────────────────────────

import os
import tempfile
import shutil
from fastapi.testclient import TestClient


@pytest.fixture
def client(tmp_path):
    data_path = tmp_path / "data"
    (data_path / "examples").mkdir(parents=True)
    (tmp_path / "reports" / "generated").mkdir(parents=True)
    (tmp_path / "reports" / "reviewed").mkdir(parents=True)
    (tmp_path / "logs").mkdir(parents=True)

    src_examples = os.path.join(os.path.dirname(__file__), "..", "data", "examples")
    for f in os.listdir(src_examples):
        if f.endswith(".yaml"):
            shutil.copy(os.path.join(src_examples, f), data_path / "examples" / f)

    os.environ["DATA_PATH"] = str(data_path)
    os.environ["REPORT_PATH"] = str(tmp_path / "reports")
    os.environ["LOG_PATH"] = str(tmp_path / "logs")

    import importlib
    import harmonizer.api
    importlib.reload(harmonizer.api)
    from harmonizer.api import app
    yield TestClient(app)

    os.environ.pop("DATA_PATH", None)
    os.environ.pop("REPORT_PATH", None)
    os.environ.pop("LOG_PATH", None)


class TestProcessAnalysisAPI:
    def test_list_analyses(self, client):
        resp = client.get("/api/process-analysis")
        assert resp.status_code == 200
        data = resp.json()
        assert isinstance(data, list)
        # Seed data should have one analysis
        assert len(data) >= 1

    def test_get_analysis(self, client):
        resp = client.get("/api/process-analysis/request_incident_mgmt")
        assert resp.status_code == 200
        data = resp.json()
        assert data["stream_id"] == "request_incident_mgmt"
        assert len(data["process_steps"]) == 6
        assert data["entities"] == ["DE", "AT"]

    def test_get_analysis_not_found(self, client):
        resp = client.get("/api/process-analysis/nonexistent")
        assert resp.status_code == 404

    def test_scaffold_creates_analysis(self, client):
        resp = client.post("/api/process-analysis/policies_processes/scaffold")
        assert resp.status_code == 200
        data = resp.json()
        assert data["stream_id"] == "policies_processes"
        assert len(data["process_steps"]) == 6
        for step in data["process_steps"]:
            assert len(step["entity_variants"]) == 2

    def test_scaffold_duplicate_rejected(self, client):
        # request_incident_mgmt already has an analysis from seed data
        resp = client.post("/api/process-analysis/request_incident_mgmt/scaffold")
        assert resp.status_code == 400

    def test_save_variant(self, client):
        resp = client.put(
            "/api/process-analysis/request_incident_mgmt/steps/intake/variants/DE",
            json={
                "entity_id": "DE",
                "description": "Updated intake description",
                "systems_used": ["ServiceNow", "Splunk"],
                "roles_involved": [{"role": "Analyst", "responsibility": "review"}],
                "why_is_it_done_this_way": ["updated reason"],
            },
        )
        assert resp.status_code == 200
        assert resp.json()["description"] == "Updated intake description"

    def test_completeness_endpoint(self, client):
        resp = client.get("/api/process-analysis/request_incident_mgmt/completeness")
        assert resp.status_code == 200
        data = resp.json()
        assert "score" in data
        assert "step_scores" in data
        assert data["score"] > 0

    def test_deltas_endpoint(self, client):
        resp = client.get("/api/process-analysis/request_incident_mgmt/deltas")
        assert resp.status_code == 200
        data = resp.json()
        assert isinstance(data, list)
        assert len(data) > 0
        # Should find system differences
        sys_d = [d for d in data if d["delta_type"] == "system_difference"]
        assert len(sys_d) >= 1

    def test_summary_endpoint(self, client):
        resp = client.get("/api/process-analysis/request_incident_mgmt/summary")
        assert resp.status_code == 200
        data = resp.json()
        assert data["total_steps"] == 6
        assert "DE" in data["entities"]
        assert "AT" in data["entities"]
        assert data["high_impact_deltas"] > 0
        # New decision support fields from API
        assert "standardization_candidates_count" in data
        assert "tendency" in data
        assert "recommendations" in data

    def test_guide_questions(self, client):
        resp = client.get("/api/process-analysis-guide/intake")
        assert resp.status_code == 200
        data = resp.json()
        assert len(data) >= 3
        assert any("Kanäle" in q["text"] for q in data)

    def test_guide_questions_not_found(self, client):
        resp = client.get("/api/process-analysis-guide/nonexistent")
        assert resp.status_code == 404

    # ─── Enriched deltas endpoint ───────────────────────────────────────────

    def test_deltas_have_enriched_fields(self, client):
        resp = client.get("/api/process-analysis/request_incident_mgmt/deltas")
        assert resp.status_code == 200
        data = resp.json()
        assert len(data) > 0
        for d in data:
            assert "delta_dimension" in d, f"Missing delta_dimension in delta: {d['delta_type']}"
            assert "delta_nature" in d
            assert "constraint_type" in d
            assert "constraint_evidence" in d
            assert "needs_management_decision" in d
            assert isinstance(d["needs_management_decision"], bool)

    def test_deltas_contain_control_gaps(self, client):
        resp = client.get("/api/process-analysis/request_incident_mgmt/deltas")
        data = resp.json()
        gaps = [d for d in data if d["delta_type"] == "control_gap"]
        assert len(gaps) >= 1, "Seed data should have control gaps in escalation/reporting"
        for g in gaps:
            assert g["delta_nature"] == "control_relevant"
            assert g["needs_management_decision"] is True

    # ─── Enriched summary endpoint ───────────────────────────────────────

    def test_summary_has_decision_support_fields(self, client):
        resp = client.get("/api/process-analysis/request_incident_mgmt/summary")
        assert resp.status_code == 200
        data = resp.json()
        # New decision support counters
        assert isinstance(data["standardization_candidates_count"], int)
        assert isinstance(data["likely_keep_local_count"], int)
        assert isinstance(data["control_gaps_count"], int)
        assert data["control_gaps_count"] >= 1
        assert isinstance(data["evidence_gaps_count"], int)
        assert data["evidence_gaps_count"] >= 1  # AT has evidence gaps
        assert isinstance(data["weak_why_count"], int)
        assert data["weak_why_count"] >= 1  # AT has weak WHYs
        assert isinstance(data["management_decisions_needed_count"], int)
        # Review status counts
        assert isinstance(data["review_status_counts"], dict)
        assert "draft" in data["review_status_counts"]
        assert "approved" in data["review_status_counts"]
        # Tendency
        assert data["tendency"] in ("harmonizable", "partially_harmonizable",
                                     "strongly_local", "insufficiently_captured")
        # Top differences and open gaps
        assert isinstance(data["top_differences"], list)
        assert isinstance(data["open_gaps"], list)
        assert len(data["open_gaps"]) >= 1
        # Recommendations embedded
        assert isinstance(data["recommendations"], list)
        assert len(data["recommendations"]) >= 1

    # ─── Recommendations endpoint ────────────────────────────────────────

    def test_recommendations_endpoint(self, client):
        resp = client.get("/api/process-analysis/request_incident_mgmt/recommendations")
        assert resp.status_code == 200
        data = resp.json()
        assert isinstance(data, list)
        assert len(data) >= 1

    def test_recommendations_have_required_fields(self, client):
        resp = client.get("/api/process-analysis/request_incident_mgmt/recommendations")
        data = resp.json()
        valid_types = {"keep_local", "harmonize", "centralize",
                       "investigate_further", "remediate_control_gap"}
        for r in data:
            assert "id" in r
            assert "title" in r
            assert r["recommendation_type"] in valid_types
            assert "rationale" in r
            assert isinstance(r["based_on_step_ids"], list)
            assert isinstance(r["based_on_delta_ids"], list)
            assert r["priority"] in ("high", "medium", "low")
            assert isinstance(r["assumptions"], list)
            assert isinstance(r["blockers"], list)
            assert "expected_benefit" in r
            assert r["implementation_complexity"] in ("low", "medium", "high")

    def test_recommendations_contain_expected_types(self, client):
        resp = client.get("/api/process-analysis/request_incident_mgmt/recommendations")
        data = resp.json()
        types = {r["recommendation_type"] for r in data}
        # Seed data should produce at least these types
        assert "remediate_control_gap" in types, "Seed should have control gap remediation"
        assert "keep_local" in types, "Seed should have keep_local (regulatory constraints)"

    def test_recommendations_not_found(self, client):
        resp = client.get("/api/process-analysis/nonexistent/recommendations")
        assert resp.status_code == 404

    # ─── Review status validation endpoint ───────────────────────────────

    def test_validate_review_approved_missing_evidence(self, client):
        """AT triage has no evidence — approval should be blocked."""
        resp = client.post(
            "/api/process-analysis/request_incident_mgmt/validate-review-status",
            json={"step_id": "triage", "entity_id": "AT", "new_status": "approved"},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["allowed"] is False
        assert len(data["reasons"]) >= 1
        assert len(data["missing_prerequisites"]) >= 1

    def test_validate_review_approved_complete_variant(self, client):
        """DE escalation has everything — approval should be allowed."""
        resp = client.post(
            "/api/process-analysis/request_incident_mgmt/validate-review-status",
            json={"step_id": "escalation", "entity_id": "DE", "new_status": "approved"},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["allowed"] is True
        assert data["reasons"] == []
        assert data["missing_prerequisites"] == []

    def test_validate_review_challenged_always_allowed(self, client):
        resp = client.post(
            "/api/process-analysis/request_incident_mgmt/validate-review-status",
            json={"step_id": "intake", "entity_id": "DE", "new_status": "challenged"},
        )
        assert resp.status_code == 200
        assert resp.json()["allowed"] is True

    def test_validate_review_invalid_status(self, client):
        resp = client.post(
            "/api/process-analysis/request_incident_mgmt/validate-review-status",
            json={"step_id": "intake", "entity_id": "DE", "new_status": "bogus"},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["allowed"] is False

    def test_validate_review_variant_not_found(self, client):
        resp = client.post(
            "/api/process-analysis/request_incident_mgmt/validate-review-status",
            json={"step_id": "intake", "entity_id": "NONEXISTENT", "new_status": "captured"},
        )
        assert resp.status_code == 404

    def test_validate_review_analysis_not_found(self, client):
        resp = client.post(
            "/api/process-analysis/nonexistent/validate-review-status",
            json={"step_id": "intake", "entity_id": "DE", "new_status": "captured"},
        )
        assert resp.status_code == 404

    # ─── Delete (moved to end to avoid interfering with other tests) ─────

    def test_delete_analysis(self, client):
        resp = client.delete("/api/process-analysis/request_incident_mgmt")
        assert resp.status_code == 200
        resp = client.get("/api/process-analysis/request_incident_mgmt")
        assert resp.status_code == 404

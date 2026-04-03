"""Tests for the FastAPI backend."""

import os
import tempfile
import shutil

import pytest
from fastapi.testclient import TestClient


@pytest.fixture(autouse=True)
def _set_env(tmp_path):
    """Set up temp directories for API tests."""
    data_path = tmp_path / "data"
    report_path = tmp_path / "reports"
    log_path = tmp_path / "logs"

    # Create directory structure
    (data_path / "examples").mkdir(parents=True)
    (report_path / "generated").mkdir(parents=True)
    (report_path / "reviewed").mkdir(parents=True)
    log_path.mkdir(parents=True)

    # Copy example data
    src_examples = os.path.join(os.path.dirname(__file__), "..", "data", "examples")
    for f in os.listdir(src_examples):
        if f.endswith(".yaml"):
            shutil.copy(os.path.join(src_examples, f), data_path / "examples" / f)

    os.environ["DATA_PATH"] = str(data_path)
    os.environ["REPORT_PATH"] = str(report_path)
    os.environ["LOG_PATH"] = str(log_path)

    # Re-import to pick up new env vars
    import importlib
    import harmonizer.api
    importlib.reload(harmonizer.api)

    yield

    # Clean up env
    os.environ.pop("DATA_PATH", None)
    os.environ.pop("REPORT_PATH", None)
    os.environ.pop("LOG_PATH", None)


@pytest.fixture
def client():
    from harmonizer.api import app
    return TestClient(app)


class TestHealthEndpoint:
    def test_health(self, client) -> None:
        resp = client.get("/health")
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "ok"
        assert "version" in data


class TestAnalyzeEndpoint:
    def test_analyze_examples(self, client) -> None:
        resp = client.post("/analyze", json={"data_dir": "examples"})
        assert resp.status_code == 200
        data = resp.json()
        assert "report_name" in data
        assert data["areas"] > 0
        assert data["streams"] > 0
        assert data["timestamp"] != ""

    def test_analyze_nonexistent_dir(self, client) -> None:
        resp = client.post("/analyze", json={"data_dir": "nonexistent"})
        assert resp.status_code == 404

    def test_analyze_creates_report_file(self, client) -> None:
        resp = client.post("/analyze", json={"data_dir": "examples"})
        assert resp.status_code == 200
        report_name = resp.json()["report_name"]
        # Verify report is listed
        resp2 = client.get("/reports")
        assert resp2.status_code == 200
        names = [r["name"] for r in resp2.json()]
        assert report_name in names


class TestReportsEndpoint:
    def test_list_reports_empty(self, client) -> None:
        resp = client.get("/reports")
        assert resp.status_code == 200
        assert resp.json() == []

    def test_get_report_after_analyze(self, client) -> None:
        # Generate a report first
        resp = client.post("/analyze", json={"data_dir": "examples"})
        report_name = resp.json()["report_name"]
        # Retrieve it
        resp2 = client.get(f"/reports/{report_name}")
        assert resp2.status_code == 200
        assert "InfoSec Process Harmonization Report" in resp2.text

    def test_get_nonexistent_report(self, client) -> None:
        resp = client.get("/reports/nonexistent.md")
        assert resp.status_code == 404


class TestCRUDValidation:
    """Tests for reference validation and dependency checks."""

    def test_save_area_and_get(self, client) -> None:
        area = {"id": "test_area", "name": "Test Area", "description": "A test"}
        resp = client.put("/api/areas", json=area)
        assert resp.status_code == 200
        assert resp.json()["id"] == "test_area"
        # Get it back
        resp2 = client.get("/api/areas/test_area")
        assert resp2.status_code == 200
        assert resp2.json()["name"] == "Test Area"

    def test_save_area_requires_id_and_name(self, client) -> None:
        resp = client.put("/api/areas", json={"id": "x"})
        assert resp.status_code == 400
        resp = client.put("/api/areas", json={"name": "x"})
        assert resp.status_code == 400

    def test_save_area_empty_id_rejected(self, client) -> None:
        resp = client.put("/api/areas", json={"id": "  ", "name": "x"})
        assert resp.status_code == 400

    def test_delete_area_with_streams_fails(self, client) -> None:
        # definition_design has streams in example data
        resp = client.delete("/api/areas/definition_design")
        assert resp.status_code == 409
        assert "stream" in resp.json()["detail"].lower()

    def test_save_stream_validates_area_id(self, client) -> None:
        stream = {"id": "s1", "name": "S1", "area_id": "nonexistent_area"}
        resp = client.put("/api/streams", json=stream)
        assert resp.status_code == 400
        assert "area" in resp.json()["detail"].lower()

    def test_save_stream_valid_area_id(self, client) -> None:
        stream = {"id": "test_stream", "name": "TS", "area_id": "definition_design"}
        resp = client.put("/api/streams", json=stream)
        assert resp.status_code == 200

    def test_delete_stream_with_subprocesses_fails(self, client) -> None:
        # policies_processes has subprocesses in example data
        resp = client.delete("/api/streams/policies_processes")
        assert resp.status_code == 409
        assert "subprocess" in resp.json()["detail"].lower()

    def test_save_subprocess_validates_stream_id(self, client) -> None:
        sp = {"id": "sp1", "name": "SP1", "stream_id": "nonexistent_stream"}
        resp = client.put("/api/subprocesses", json=sp)
        assert resp.status_code == 400
        assert "stream" in resp.json()["detail"].lower()

    def test_delete_subprocess_with_interfaces_fails(self, client) -> None:
        # sp-risk-identify is referenced by interface iface-risk-to-incident
        resp = client.delete("/api/subprocesses/sp-risk-identify")
        assert resp.status_code == 409
        assert "interface" in resp.json()["detail"].lower()

    def test_save_interface_validates_source_target(self, client) -> None:
        iface = {"id": "if1", "source_process_id": "nonexistent_sp", "target_process_id": "sp-inc-intake"}
        resp = client.put("/api/interfaces", json=iface)
        assert resp.status_code == 400
        assert "source" in resp.json()["detail"].lower()

    def test_save_interface_valid_references(self, client) -> None:
        iface = {"id": "if-test", "source_process_id": "sp-inc-intake",
                 "target_process_id": "sp-inc-communication", "interface_type": "data_flow"}
        resp = client.put("/api/interfaces", json=iface)
        assert resp.status_code == 200

    def test_delete_interface_success(self, client) -> None:
        # First create one
        iface = {"id": "if-del-test", "source_process_id": "sp-inc-intake",
                 "target_process_id": "sp-inc-communication", "interface_type": "data_flow"}
        client.put("/api/interfaces", json=iface)
        resp = client.delete("/api/interfaces/if-del-test")
        assert resp.status_code == 200

    def test_delete_area_success_when_no_dependents(self, client) -> None:
        # Create area with no streams
        client.put("/api/areas", json={"id": "orphan_area", "name": "Orphan"})
        resp = client.delete("/api/areas/orphan_area")
        assert resp.status_code == 200


class TestAssessmentValidation:
    """Tests for assessment save validation."""

    def test_save_assessment_requires_object_type(self, client) -> None:
        resp = client.put("/api/assessments", json={
            "assessed_object_id": "policies_processes",
        })
        assert resp.status_code == 400
        assert "assessed_object_type" in resp.json()["detail"]

    def test_save_assessment_validates_stream_exists(self, client) -> None:
        resp = client.put("/api/assessments", json={
            "assessed_object_id": "nonexistent",
            "assessed_object_type": "stream",
            "answers": [],
        })
        assert resp.status_code == 400
        assert "not found" in resp.json()["detail"].lower()

    def test_save_assessment_validates_dimension(self, client) -> None:
        resp = client.put("/api/assessments", json={
            "assessed_object_id": "policies_processes",
            "assessed_object_type": "stream",
            "answers": [{"dimension": "bogus_dimension", "score": 3}],
        })
        assert resp.status_code == 400
        assert "dimension" in resp.json()["detail"].lower()

    def test_save_assessment_validates_score_range(self, client) -> None:
        resp = client.put("/api/assessments", json={
            "assessed_object_id": "policies_processes",
            "assessed_object_type": "stream",
            "answers": [{"dimension": "maturity", "score": 9}],
        })
        assert resp.status_code == 400
        assert "score" in resp.json()["detail"].lower()

    def test_save_assessment_validates_hard_constraint(self, client) -> None:
        resp = client.put("/api/assessments", json={
            "assessed_object_id": "policies_processes",
            "assessed_object_type": "stream",
            "answers": [],
            "hard_constraints": ["bogus_constraint"],
        })
        assert resp.status_code == 400
        assert "constraint" in resp.json()["detail"].lower()

    def test_completed_requires_all_dimensions(self, client) -> None:
        resp = client.put("/api/assessments", json={
            "assessed_object_id": "policies_processes",
            "assessed_object_type": "stream",
            "answers": [{"dimension": "maturity", "score": 3}],
            "status": "completed",
        })
        assert resp.status_code == 400
        assert "missing" in resp.json()["detail"].lower()

    def test_save_draft_assessment_success(self, client) -> None:
        resp = client.put("/api/assessments", json={
            "assessed_object_id": "it_bcm",
            "assessed_object_type": "stream",
            "answers": [{"dimension": "maturity", "score": 4, "rationale": "test"}],
            "status": "draft",
        })
        assert resp.status_code == 200
        assert resp.json()["status"] == "draft"


class TestLiveScoreEndpoint:
    """Tests for the enhanced live scoring endpoint."""

    def test_basic_score(self, client) -> None:
        resp = client.post("/api/score", json={
            "answers": [{"dimension": d, "score": 4} for d in [
                "regulatory_alignment", "operational_alignment",
                "tooling_alignment", "governance_alignment",
                "maturity", "local_necessity",
            ]],
        })
        assert resp.status_code == 200
        data = resp.json()
        assert data["blended_score"] > 0
        assert data["classification"]
        assert data["confidence"]
        assert data["missing_dimensions"] == []

    def test_hard_constraint_caps_classification(self, client) -> None:
        resp = client.post("/api/score", json={
            "answers": [{"dimension": d, "score": 5} for d in [
                "regulatory_alignment", "operational_alignment",
                "tooling_alignment", "governance_alignment",
                "maturity", "local_necessity",
            ]],
            "hard_constraints": ["legal_local_difference"],
        })
        assert resp.status_code == 200
        data = resp.json()
        # legal_local_difference should cap classification
        assert len(data["constraint_reasons"]) > 0

    def test_missing_dimensions_reported(self, client) -> None:
        resp = client.post("/api/score", json={
            "answers": [{"dimension": "maturity", "score": 3}],
        })
        assert resp.status_code == 200
        data = resp.json()
        assert data["dimensions_answered"] == 1
        assert len(data["missing_dimensions"]) == 5


class TestQuestionsEndpoint:
    """Tests for the type-specific questions endpoint."""

    def test_get_process_questions(self, client) -> None:
        resp = client.get("/api/questions/process")
        assert resp.status_code == 200
        data = resp.json()
        assert len(data) == 5
        assert data[0]["id"] == "proc_trigger_uniform"

    def test_get_governance_questions(self, client) -> None:
        resp = client.get("/api/questions/governance_function")
        assert resp.status_code == 200
        assert len(resp.json()) == 5

    def test_invalid_stream_type(self, client) -> None:
        resp = client.get("/api/questions/nonexistent")
        assert resp.status_code == 400


class TestDecisionEndpoints:
    """Tests for decision computation and review endpoints."""

    def test_compute_decision_for_stream(self, client) -> None:
        resp = client.post("/api/decisions/compute/policies_processes")
        assert resp.status_code == 200
        data = resp.json()
        assert data["stream_id"] == "policies_processes"
        assert data["decision"] in [
            "centralize_now", "centralize_later", "harmonize_only",
            "standardize_only", "keep_local", "reassess_after_data_completion",
        ]
        assert "target_operating_model" in data
        assert "blocking_factors" in data
        assert "harmonization_degree" in data

    def test_compute_decision_nonexistent_stream(self, client) -> None:
        resp = client.post("/api/decisions/compute/nonexistent")
        assert resp.status_code == 404

    def test_compute_decision_no_assessment(self, client) -> None:
        # Create a stream without assessment
        client.put("/api/areas", json={"id": "tmp_area", "name": "Tmp"})
        client.put("/api/streams", json={"id": "tmp_no_ass", "name": "No Ass", "area_id": "tmp_area"})
        resp = client.post("/api/decisions/compute/tmp_no_ass")
        assert resp.status_code == 400

    def test_save_review_basic(self, client) -> None:
        resp = client.put("/api/reviews", json={
            "stream_id": "policies_processes",
            "review_status": "draft",
            "review_notes": "Initial review",
        })
        assert resp.status_code == 200
        assert resp.json()["review_status"] == "draft"

    def test_save_review_override_requires_rationale(self, client) -> None:
        resp = client.put("/api/reviews", json={
            "stream_id": "policies_processes",
            "override_applied": True,
        })
        assert resp.status_code == 400
        assert "rationale" in resp.json()["detail"].lower()

    def test_save_review_reviewed_requires_reviewer(self, client) -> None:
        resp = client.put("/api/reviews", json={
            "stream_id": "policies_processes",
            "review_status": "reviewed",
        })
        assert resp.status_code == 400
        assert "reviewer" in resp.json()["detail"].lower()

    def test_save_review_reviewed_requires_completed_assessment(self, client) -> None:
        # Save a draft assessment
        client.put("/api/assessments", json={
            "assessed_object_id": "it_risk",
            "assessed_object_type": "stream",
            "answers": [{"dimension": "maturity", "score": 3}],
            "status": "draft",
        })
        resp = client.put("/api/reviews", json={
            "stream_id": "it_risk",
            "review_status": "reviewed",
            "reviewer_name": "Tester",
        })
        assert resp.status_code == 400
        assert "completed" in resp.json()["detail"].lower()

    def test_list_reviews(self, client) -> None:
        client.put("/api/reviews", json={
            "stream_id": "policies_processes",
            "review_status": "draft",
        })
        resp = client.get("/api/reviews")
        assert resp.status_code == 200
        assert any(r["stream_id"] == "policies_processes" for r in resp.json())


class TestAsIsAndDelta:
    """Tests for stream AS-IS DE/AT and delta endpoints."""

    def test_get_as_is_empty(self, client) -> None:
        resp = client.get("/api/streams/policies_processes/as-is")
        assert resp.status_code == 200
        data = resp.json()
        assert data["stream_id"] == "policies_processes"
        assert "as_is" in data

    def test_save_and_get_as_is(self, client) -> None:
        body = {
            "as_is": {
                "de": {
                    "description": "DE process: central policy management",
                    "steps": ["draft policy", "review", "approve", "publish"],
                    "tools": ["Confluence", "JIRA"],
                    "roles": ["Policy Owner", "CISO"],
                    "controls": ["C-001", "C-002"],
                },
                "at": {
                    "description": "AT process: local policy creation",
                    "steps": ["draft", "local review", "publish"],
                    "tools": ["SharePoint"],
                    "roles": ["Local ISO"],
                    "controls": ["C-001"],
                },
            },
            "delta": {
                "structural_diff": "medium",
                "tooling_gap": "high",
                "regulatory_gap": "low",
                "role_model_diff": "medium",
            },
        }
        resp = client.put("/api/streams/policies_processes/as-is", json=body)
        assert resp.status_code == 200
        data = resp.json()
        assert data["as_is"]["de"]["description"] == "DE process: central policy management"
        assert data["delta"]["tooling_gap"] == "high"

        # Verify it persists
        resp2 = client.get("/api/streams/policies_processes/as-is")
        assert resp2.json()["as_is"]["at"]["tools"] == ["SharePoint"]

    def test_save_as_is_with_extended_fields(self, client) -> None:
        """New fields (triggers, inputs, outputs, responsibilities, evidence, notes) persist."""
        body = {
            "as_is": {
                "de": {
                    "description": "DE process",
                    "triggers": ["quarterly review", "policy change"],
                    "inputs": ["risk register", "previous audit"],
                    "outputs": ["updated policy", "audit report"],
                    "steps": ["gather data", "analyze", "draft"],
                    "roles": ["CISO"],
                    "responsibilities": ["CISO approves final version"],
                    "tools": ["Confluence"],
                    "controls": ["C-001"],
                    "evidence": ["audit log", "approval ticket"],
                    "notes": "Note for DE",
                },
                "at": {
                    "description": "AT process",
                    "triggers": ["annual review"],
                    "inputs": ["local regs"],
                    "outputs": ["local policy"],
                    "steps": ["review", "adapt", "publish"],
                    "roles": ["Local ISO"],
                    "responsibilities": ["ISO owns local variant"],
                    "tools": ["SharePoint"],
                    "controls": ["C-001"],
                    "evidence": ["review record"],
                    "notes": "Note for AT",
                },
            },
        }
        resp = client.put("/api/streams/policies_processes/as-is", json=body)
        assert resp.status_code == 200
        data = resp.json()
        assert data["as_is"]["de"]["triggers"] == ["quarterly review", "policy change"]
        assert data["as_is"]["at"]["evidence"] == ["review record"]
        assert data["completeness"]["de_complete"] is True
        assert data["completeness"]["at_complete"] is True

    def test_save_as_is_returns_completeness_errors(self, client) -> None:
        """Saving partial AS-IS returns completeness errors."""
        body = {
            "as_is": {
                "de": {"description": "DE process", "steps": ["one"], "roles": [], "tools": []},
                "at": {"description": "AT process", "steps": ["a", "b", "c"], "roles": ["ISO"], "tools": ["JIRA"]},
            },
        }
        resp = client.put("/api/streams/policies_processes/as-is", json=body)
        assert resp.status_code == 200
        data = resp.json()
        assert data["completeness"]["de_complete"] is False
        assert data["completeness"]["at_complete"] is True
        assert any("steps" in e for e in data["completeness"]["de_errors"])

    def test_asymmetric_as_is_rejected(self, client) -> None:
        """One country filled, other empty → rejected."""
        resp = client.put("/api/streams/policies_processes/as-is", json={
            "as_is": {
                "de": {"description": "DE only", "steps": ["a", "b", "c"], "roles": ["R"], "tools": ["T"]},
                "at": {},
            },
        })
        assert resp.status_code == 400
        assert "empty" in resp.json()["detail"].lower()

    def test_as_is_status_endpoint(self, client) -> None:
        """GET /api/streams/{id}/as-is/status returns completeness."""
        _setup_complete_as_is(client)
        resp = client.get("/api/streams/policies_processes/as-is/status")
        assert resp.status_code == 200
        data = resp.json()
        assert data["complete"] is True
        assert data["de_complete"] is True
        assert data["at_complete"] is True
        assert data["de_errors"] == []

    def test_save_as_is_invalid_gap(self, client) -> None:
        resp = client.put("/api/streams/policies_processes/as-is", json={
            "as_is": {"de": {}, "at": {}},
            "delta": {"structural_diff": "extreme"},
        })
        assert resp.status_code == 400

    def test_save_as_is_nonexistent_stream(self, client) -> None:
        resp = client.put("/api/streams/nonexistent/as-is", json={"as_is": {}})
        assert resp.status_code == 404


class TestComputedDeltaEndpoint:
    """Tests for GET /api/streams/{id}/delta."""

    def test_delta_without_as_is(self, client) -> None:
        resp = client.get("/api/streams/policies_processes/delta")
        assert resp.status_code == 400

    def test_delta_nonexistent_stream(self, client) -> None:
        resp = client.get("/api/streams/nonexistent/delta")
        assert resp.status_code == 404

    def test_delta_with_identical_processes(self, client) -> None:
        client.put("/api/streams/policies_processes/as-is", json={
            "as_is": {
                "de": {
                    "description": "Same process",
                    "steps": ["s1", "s2", "s3"],
                    "roles": ["CISO"],
                    "tools": ["JIRA"],
                },
                "at": {
                    "description": "Same process",
                    "steps": ["s1", "s2", "s3"],
                    "roles": ["CISO"],
                    "tools": ["JIRA"],
                },
            },
        })
        resp = client.get("/api/streams/policies_processes/delta")
        assert resp.status_code == 200
        data = resp.json()
        assert "items" in data
        assert "summary" in data
        assert data["summary"]["high_impact"] == 0
        assert all(i["difference_type"] == "identical" for i in data["items"])

    def test_delta_with_different_processes(self, client) -> None:
        client.put("/api/streams/policies_processes/as-is", json={
            "as_is": {
                "de": {
                    "description": "DE process",
                    "steps": ["gather", "analyze", "decide"],
                    "roles": ["CISO", "DPO"],
                    "tools": ["ServiceNow"],
                    "controls": ["ISO-27001"],
                },
                "at": {
                    "description": "AT process",
                    "steps": ["collect", "review", "approve"],
                    "roles": ["Local ISO"],
                    "tools": ["JIRA"],
                    "controls": ["BSI-Grundschutz"],
                },
            },
        })
        resp = client.get("/api/streams/policies_processes/delta")
        assert resp.status_code == 200
        data = resp.json()
        assert data["summary"]["high_impact"] >= 2
        # Check items have proper structure
        for item in data["items"]:
            assert "category" in item
            assert "de_value" in item
            assert "at_value" in item
            assert "difference_type" in item
            assert "impact" in item
            assert "description" in item

    def test_delta_returned_in_decision_compare(self, client) -> None:
        """Decision comparison should include computed_delta."""
        _setup_complete_as_is(client)
        # Create option assessment
        client.put("/api/assessments", json={
            "assessed_object_id": "policies_processes",
            "assessed_object_type": "stream",
            "target_option": "de_standard",
            "answers": [
                {"dimension": d, "score": 4, "rationale": "ok"}
                for d in ("regulatory_alignment", "operational_alignment",
                          "tooling_alignment", "governance_alignment",
                          "maturity", "local_necessity")
            ],
            "status": "draft",
        })
        resp = client.post("/api/decisions/compare/policies_processes")
        assert resp.status_code == 200
        data = resp.json()
        assert "computed_delta" in data
        assert data["computed_delta"] is not None
        assert "items" in data["computed_delta"]
        assert "summary" in data["computed_delta"]


class TestAsIsHardGates:
    """Tests that incomplete AS-IS blocks downstream operations."""

    def test_option_assessment_blocked_without_as_is(self, client) -> None:
        resp = client.put("/api/assessments", json={
            "assessed_object_id": "policies_processes",
            "assessed_object_type": "stream",
            "target_option": "de_standard",
            "answers": [{"dimension": "maturity", "score": 3, "rationale": "ok"}],
            "status": "draft",
        })
        assert resp.status_code == 400
        assert "as-is" in resp.json()["detail"].lower()

    def test_decision_compare_blocked_without_as_is(self, client) -> None:
        resp = client.post("/api/decisions/compare/policies_processes")
        assert resp.status_code == 400
        assert "as-is" in resp.json()["detail"].lower()

    def test_legacy_assessment_still_works_without_as_is(self, client) -> None:
        """Legacy assessments (no target_option) are NOT blocked by AS-IS."""
        resp = client.put("/api/assessments", json={
            "assessed_object_id": "policies_processes",
            "assessed_object_type": "stream",
            "answers": [{"dimension": "maturity", "score": 3, "rationale": "ok"}],
            "status": "draft",
        })
        assert resp.status_code == 200


def _setup_complete_as_is(client, stream_id="policies_processes"):
    """Set up complete AS-IS data for DE and AT on a stream (shared test helper)."""
    resp = client.put(f"/api/streams/{stream_id}/as-is", json={
        "as_is": {
            "de": {
                "description": "DE process",
                "steps": ["step 1", "step 2", "step 3"],
                "roles": ["CISO"],
                "tools": ["JIRA"],
            },
            "at": {
                "description": "AT process",
                "steps": ["step A", "step B", "step C"],
                "roles": ["Local ISO"],
                "tools": ["SharePoint"],
            },
        },
    })
    assert resp.status_code == 200
    return resp


class TestOptionAssessments:
    """Tests for target option-based assessments."""

    def _full_answers(self):
        return [
            {"dimension": "regulatory_alignment", "score": 4, "rationale": "good"},
            {"dimension": "operational_alignment", "score": 4, "rationale": "good"},
            {"dimension": "tooling_alignment", "score": 3, "rationale": "ok"},
            {"dimension": "governance_alignment", "score": 4, "rationale": "good"},
            {"dimension": "maturity", "score": 3, "rationale": "ok"},
            {"dimension": "local_necessity", "score": 4, "rationale": "low"},
        ]

    def test_save_option_assessment(self, client) -> None:
        _setup_complete_as_is(client)
        resp = client.put("/api/assessments", json={
            "assessed_object_id": "policies_processes",
            "assessed_object_type": "stream",
            "target_option": "de_standard",
            "answers": [{"dimension": "maturity", "score": 4, "rationale": "ok"}],
            "status": "draft",
        })
        assert resp.status_code == 200
        assert resp.json()["target_option"] == "de_standard"

    def test_save_three_options(self, client) -> None:
        _setup_complete_as_is(client)
        for opt in ("de_standard", "at_standard", "central"):
            resp = client.put("/api/assessments", json={
                "assessed_object_id": "policies_processes",
                "assessed_object_type": "stream",
                "target_option": opt,
                "answers": self._full_answers(),
                "status": "draft",
            })
            assert resp.status_code == 200

        # Should now have 3 option assessments + the original
        resp = client.get("/api/streams/policies_processes/option-assessments")
        assert resp.status_code == 200
        opts = {a["target_option"] for a in resp.json() if a.get("target_option")}
        assert opts == {"de_standard", "at_standard", "central"}

    def test_filter_by_target_option(self, client) -> None:
        _setup_complete_as_is(client)
        client.put("/api/assessments", json={
            "assessed_object_id": "policies_processes",
            "assessed_object_type": "stream",
            "target_option": "de_standard",
            "answers": [{"dimension": "maturity", "score": 4, "rationale": "ok"}],
            "status": "draft",
        })
        resp = client.get("/api/assessments?target_option=de_standard")
        assert resp.status_code == 200
        for a in resp.json():
            assert a.get("target_option") == "de_standard"

    def test_invalid_target_option(self, client) -> None:
        resp = client.put("/api/assessments", json={
            "assessed_object_id": "policies_processes",
            "assessed_object_type": "stream",
            "target_option": "invalid_option",
            "answers": [],
            "status": "draft",
        })
        assert resp.status_code == 400
        assert "target_option" in resp.json()["detail"].lower()

    def test_target_option_only_for_streams(self, client) -> None:
        resp = client.put("/api/assessments", json={
            "assessed_object_id": "sp_policy_creation",
            "assessed_object_type": "subprocess",
            "target_option": "de_standard",
            "answers": [],
            "status": "draft",
        })
        assert resp.status_code == 400
        assert "stream" in resp.json()["detail"].lower()

    def test_option_assessment_requires_complete_as_is(self, client) -> None:
        """Option assessment (any status) requires complete AS-IS DE+AT on stream."""
        resp = client.put("/api/assessments", json={
            "assessed_object_id": "policies_processes",
            "assessed_object_type": "stream",
            "target_option": "de_standard",
            "answers": self._full_answers(),
            "status": "draft",
        })
        assert resp.status_code == 400
        assert "as-is" in resp.json()["detail"].lower()

    def test_incomplete_as_is_blocks_option_assessment(self, client) -> None:
        """Partial AS-IS (description only, no steps/roles/tools) still blocks."""
        client.put("/api/streams/policies_processes/as-is", json={
            "as_is": {
                "de": {"description": "DE policy process"},
                "at": {"description": "AT policy process"},
            },
        })
        resp = client.put("/api/assessments", json={
            "assessed_object_id": "policies_processes",
            "assessed_object_type": "stream",
            "target_option": "de_standard",
            "answers": self._full_answers(),
            "status": "draft",
        })
        assert resp.status_code == 400
        assert "as-is" in resp.json()["detail"].lower()

    def test_completed_with_complete_as_is(self, client) -> None:
        """Can complete target_option assessment when AS-IS is fully filled."""
        _setup_complete_as_is(client)
        resp = client.put("/api/assessments", json={
            "assessed_object_id": "policies_processes",
            "assessed_object_type": "stream",
            "target_option": "de_standard",
            "answers": self._full_answers(),
            "status": "completed",
        })
        assert resp.status_code == 200
        assert resp.json()["status"] == "completed"


class TestOptionComparison:
    """Tests for the option comparison decision engine."""

    def _make_assessment(self, stream_id, option, scores, constraints=None, status="draft"):
        answers = [
            {"dimension": d, "score": s, "rationale": "test"}
            for d, s in scores.items()
        ]
        return {
            "assessed_object_id": stream_id,
            "assessed_object_type": "stream",
            "target_option": option,
            "answers": answers,
            "hard_constraints": constraints or [],
            "status": status,
        }

    def _setup_options(self, client, stream_id="policies_processes"):
        """Create 3 option assessments with varying scores (draft status)."""
        _setup_complete_as_is(client, stream_id)
        dims = {
            "regulatory_alignment": 4, "operational_alignment": 4,
            "tooling_alignment": 4, "governance_alignment": 4,
            "maturity": 4, "local_necessity": 4,
        }
        # DE: high scores
        resp = client.put("/api/assessments", json=self._make_assessment(
            stream_id, "de_standard", dims, [],
        ))
        assert resp.status_code == 200, resp.json()
        # AT: medium scores
        at_dims = {**dims, "tooling_alignment": 2, "maturity": 2}
        resp = client.put("/api/assessments", json=self._make_assessment(
            stream_id, "at_standard", at_dims, [],
        ))
        assert resp.status_code == 200, resp.json()
        # Central: slightly lower than DE
        central_dims = {**dims, "operational_alignment": 3}
        resp = client.put("/api/assessments", json=self._make_assessment(
            stream_id, "central", central_dims, [],
        ))
        assert resp.status_code == 200, resp.json()

    def test_compare_recommends_best(self, client) -> None:
        self._setup_options(client)
        resp = client.post("/api/decisions/compare/policies_processes")
        assert resp.status_code == 200
        data = resp.json()
        assert data["recommended_option"] is not None
        assert "option_scores" in data
        assert len(data["option_scores"]) == 3
        assert "discarded_options" in data

    def test_compare_blocked_option(self, client) -> None:
        """Option with insufficient_documentation is blocked."""
        _setup_complete_as_is(client)
        dims = {
            "regulatory_alignment": 4, "operational_alignment": 4,
            "tooling_alignment": 4, "governance_alignment": 4,
            "maturity": 4, "local_necessity": 4,
        }
        # DE: good scores but blocked by insufficient_documentation
        resp = client.put("/api/assessments", json=self._make_assessment(
            "policies_processes", "de_standard", dims,
            ["insufficient_documentation"],
        ))
        assert resp.status_code == 200
        # AT: good
        resp = client.put("/api/assessments", json=self._make_assessment(
            "policies_processes", "at_standard", dims, [],
        ))
        assert resp.status_code == 200
        resp = client.post("/api/decisions/compare/policies_processes")
        assert resp.status_code == 200
        data = resp.json()
        # DE should be discarded, AT or central selected
        assert data["recommended_option"] != "de_standard"
        blocked_opts = [d["option"] for d in data["discarded_options"]
                        if "blocked" in d.get("reason", "").lower() or "constraint" in d.get("reason", "").lower()]
        assert "de_standard" in blocked_opts

    def test_compare_no_assessments(self, client) -> None:
        # Create fresh stream
        client.put("/api/areas", json={"id": "tmp_area", "name": "Tmp"})
        client.put("/api/streams", json={"id": "tmp_empty", "name": "Empty", "area_id": "tmp_area"})
        resp = client.post("/api/decisions/compare/tmp_empty")
        assert resp.status_code == 400

    def test_compare_nonexistent_stream(self, client) -> None:
        resp = client.post("/api/decisions/compare/nonexistent")
        assert resp.status_code == 404

    def test_compare_with_delta_penalty(self, client) -> None:
        """Delta penalties should affect adjusted scores."""
        # Set high delta
        resp = client.put("/api/streams/policies_processes/as-is", json={
            "as_is": {"de": {"description": "DE"}, "at": {"description": "AT"}},
            "delta": {
                "structural_diff": "high",
                "tooling_gap": "high",
                "regulatory_gap": "high",
                "role_model_diff": "high",
            },
        })
        assert resp.status_code == 200
        self._setup_options(client)
        resp = client.post("/api/decisions/compare/policies_processes")
        assert resp.status_code == 200
        data = resp.json()
        assert "option_details" in data
        details = data["option_details"]
        # With high delta, adjusted scores should be lower than raw scores
        for opt, detail in details.items():
            assert detail["adjusted_score"] <= detail["score"]


class TestEnumsExtended:
    """Test that new enum values are exposed."""

    def test_enums_include_target_options(self, client) -> None:
        resp = client.get("/api/enums")
        data = resp.json()
        assert "target_options" in data
        assert set(data["target_options"]) == {"de_standard", "at_standard", "central"}
        assert "gap_levels" in data
        assert set(data["gap_levels"]) == {"low", "medium", "high"}


class TestCalibrateEndpoint:
    def test_calibrate_no_outcomes(self, client) -> None:
        resp = client.post("/calibrate", json={"data_dir": "examples"})
        assert resp.status_code == 400
        assert "outcome" in resp.json()["detail"].lower()

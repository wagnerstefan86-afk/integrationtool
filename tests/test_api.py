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


class TestCalibrateEndpoint:
    def test_calibrate_no_outcomes(self, client) -> None:
        resp = client.post("/calibrate", json={"data_dir": "examples"})
        assert resp.status_code == 400
        assert "outcome" in resp.json()["detail"].lower()

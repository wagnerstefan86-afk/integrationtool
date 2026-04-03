"""Tests for the structured process analysis module and API."""

import pytest

from harmonizer.process_analysis import (
    DEFAULT_PROCESS_PHASES,
    GUIDE_QUESTIONS,
    scaffold_analysis,
    score_variant_completeness,
    score_step_completeness,
    score_analysis_completeness,
    compute_step_delta,
    compute_analysis_deltas,
    compute_analysis_summary,
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
        assert result["score"] == 0
        assert "description" in result["missing_fields"]
        assert any("WHY" in w for w in result["warnings"])

    def test_complete_variant(self):
        v = {
            "description": "Full description",
            "systems_used": ["ServiceNow"],
            "roles_involved": [{"role": "CISO"}],
            "why_is_it_done_this_way": ["Historical reason"],
            "trigger": "Alert",
            "input_channels": ["email"],
            "output": "Ticket",
            "sla_or_target": "4h",
            "evidence_or_examples": ["doc"],
            "pain_points": ["slow"],
        }
        result = score_variant_completeness(v)
        assert result["score"] >= 80
        assert result["missing_fields"] == []

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
        """Verify the seed data produces a valid summary."""
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

    def test_guide_questions(self, client):
        resp = client.get("/api/process-analysis-guide/intake")
        assert resp.status_code == 200
        data = resp.json()
        assert len(data) >= 3
        assert any("Kanäle" in q["text"] for q in data)

    def test_guide_questions_not_found(self, client):
        resp = client.get("/api/process-analysis-guide/nonexistent")
        assert resp.status_code == 404

    def test_delete_analysis(self, client):
        resp = client.delete("/api/process-analysis/request_incident_mgmt")
        assert resp.status_code == 200
        resp = client.get("/api/process-analysis/request_incident_mgmt")
        assert resp.status_code == 404

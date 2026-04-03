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


class TestCalibrateEndpoint:
    def test_calibrate_no_outcomes(self, client) -> None:
        resp = client.post("/calibrate", json={"data_dir": "examples"})
        assert resp.status_code == 400
        assert "outcome" in resp.json()["detail"].lower()

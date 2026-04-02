"""Tests for YAML data loading."""

from pathlib import Path

import pytest

from harmonizer.scoring.loader import load_all_from_directory, load_processes, load_assessments


EXAMPLE_DIR = Path(__file__).parent.parent / "data" / "examples"


class TestLoadProcesses:
    def test_load_example_processes(self) -> None:
        mp, sp, iface = load_processes(EXAMPLE_DIR / "processes.yaml")
        assert len(mp) == 2
        assert len(sp) >= 4
        assert len(iface) >= 1

    def test_subprocess_belongs_to_main(self) -> None:
        mp, sp, _ = load_processes(EXAMPLE_DIR / "processes.yaml")
        mp_ids = {m.id for m in mp}
        for s in sp:
            assert s.main_process_id in mp_ids, (
                f"Subprocess {s.id} references unknown main_process_id {s.main_process_id}"
            )


class TestLoadAssessments:
    def test_load_example_assessments(self) -> None:
        assessments = load_assessments(EXAMPLE_DIR / "assessments.yaml")
        assert len(assessments) >= 4

    def test_all_assessments_have_answers(self) -> None:
        assessments = load_assessments(EXAMPLE_DIR / "assessments.yaml")
        for a in assessments:
            assert len(a.answers) == 6, (
                f"Assessment for {a.assessed_object_id} should have 6 dimension answers"
            )


class TestLoadAllFromDirectory:
    def test_load_example_directory(self) -> None:
        mp, sp, iface, assessments = load_all_from_directory(EXAMPLE_DIR)
        assert len(mp) == 2
        assert len(sp) >= 4
        assert len(assessments) >= 4

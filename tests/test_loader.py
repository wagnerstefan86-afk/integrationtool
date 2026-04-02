"""Tests for YAML data loading."""

from pathlib import Path

from harmonizer.scoring.loader import load_all_from_directory, load_structure, load_assessments


EXAMPLE_DIR = Path(__file__).parent.parent / "data" / "examples"


class TestLoadStructure:
    def test_load_example_structure(self) -> None:
        areas, streams, sp, iface = load_structure(EXAMPLE_DIR / "processes.yaml")
        assert len(areas) == 4
        assert len(streams) >= 10
        assert len(sp) >= 4
        assert len(iface) >= 2

    def test_stream_belongs_to_area(self) -> None:
        areas, streams, _, _ = load_structure(EXAMPLE_DIR / "processes.yaml")
        area_ids = {a.id for a in areas}
        for s in streams:
            assert s.area_id in area_ids, (
                f"Stream {s.id} references unknown area_id {s.area_id}"
            )

    def test_subprocess_belongs_to_stream(self) -> None:
        _, streams, sps, _ = load_structure(EXAMPLE_DIR / "processes.yaml")
        stream_ids = {s.id for s in streams}
        for sp in sps:
            assert sp.stream_id in stream_ids, (
                f"Subprocess {sp.id} references unknown stream_id {sp.stream_id}"
            )

    def test_all_streams_have_type(self) -> None:
        _, streams, _, _ = load_structure(EXAMPLE_DIR / "processes.yaml")
        for s in streams:
            assert s.stream_type is not None


class TestLoadAssessments:
    def test_load_example_assessments(self) -> None:
        assessments = load_assessments(EXAMPLE_DIR / "assessments.yaml")
        assert len(assessments) >= 10

    def test_all_assessments_have_answers(self) -> None:
        assessments = load_assessments(EXAMPLE_DIR / "assessments.yaml")
        for a in assessments:
            assert len(a.answers) == 6, (
                f"Assessment for {a.assessed_object_id} should have 6 dimension answers"
            )


class TestLoadAllFromDirectory:
    def test_load_example_directory(self) -> None:
        areas, streams, sp, iface, assessments = load_all_from_directory(EXAMPLE_DIR)
        assert len(areas) == 4
        assert len(streams) >= 10
        assert len(sp) >= 4
        assert len(assessments) >= 10

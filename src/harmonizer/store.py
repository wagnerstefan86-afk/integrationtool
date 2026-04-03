"""YAML-based data store with CRUD operations.

Provides a clean abstraction layer for reading and writing YAML data.
Designed so the storage backend can later be swapped to SQLite/Postgres
without changing the API layer.

All write operations are atomic: read full file, modify, write back.
"""

import copy
import logging
from pathlib import Path
from typing import Any, Optional

import yaml

logger = logging.getLogger("harmonizer.store")


class YAMLStore:
    """File-based store managing process and assessment YAML data.

    A dataset lives in a directory containing:
    - processes.yaml (areas, streams, subprocesses, interfaces)
    - assessments.yaml (assessments)
    - outcomes.yaml (decision outcomes, optional)
    """

    def __init__(self, data_dir: Path) -> None:
        self.data_dir = data_dir
        self.data_dir.mkdir(parents=True, exist_ok=True)
        self._process_file = data_dir / "processes.yaml"
        self._assessment_file = data_dir / "assessments.yaml"
        self._outcome_file = data_dir / "outcomes.yaml"
        self._analysis_file = data_dir / "process_analyses.yaml"

    # --- Low-level I/O ---

    def _read_yaml(self, path: Path) -> dict:
        if not path.exists():
            return {}
        with open(path, "r", encoding="utf-8") as f:
            data = yaml.safe_load(f)
        return data if isinstance(data, dict) else {}

    def _write_yaml(self, path: Path, data: dict) -> None:
        with open(path, "w", encoding="utf-8") as f:
            yaml.dump(data, f, default_flow_style=False, allow_unicode=True, sort_keys=False)
        logger.info("Written %s", path)

    def _read_processes(self) -> dict:
        return self._read_yaml(self._process_file)

    def _write_processes(self, data: dict) -> None:
        self._write_yaml(self._process_file, data)

    def _read_assessments_data(self) -> dict:
        return self._read_yaml(self._assessment_file)

    def _write_assessments_data(self, data: dict) -> None:
        self._write_yaml(self._assessment_file, data)

    def _read_outcomes_data(self) -> dict:
        return self._read_yaml(self._outcome_file)

    def _write_outcomes_data(self, data: dict) -> None:
        self._write_yaml(self._outcome_file, data)

    # --- Areas ---

    def list_areas(self) -> list[dict]:
        return self._read_processes().get("areas", [])

    def get_area(self, area_id: str) -> Optional[dict]:
        for a in self.list_areas():
            if a.get("id") == area_id:
                return a
        return None

    def save_area(self, area: dict) -> dict:
        data = self._read_processes()
        areas = data.setdefault("areas", [])
        for i, a in enumerate(areas):
            if a.get("id") == area.get("id"):
                areas[i] = area
                self._write_processes(data)
                return area
        areas.append(area)
        self._write_processes(data)
        return area

    def delete_area(self, area_id: str) -> bool:
        data = self._read_processes()
        areas = data.get("areas", [])
        new = [a for a in areas if a.get("id") != area_id]
        if len(new) == len(areas):
            return False
        data["areas"] = new
        self._write_processes(data)
        return True

    # --- Streams ---

    def list_streams(self) -> list[dict]:
        return self._read_processes().get("streams", [])

    def get_stream(self, stream_id: str) -> Optional[dict]:
        for s in self.list_streams():
            if s.get("id") == stream_id:
                return s
        return None

    def save_stream(self, stream: dict) -> dict:
        data = self._read_processes()
        streams = data.setdefault("streams", [])
        for i, s in enumerate(streams):
            if s.get("id") == stream.get("id"):
                streams[i] = stream
                self._write_processes(data)
                return stream
        streams.append(stream)
        self._write_processes(data)
        return stream

    def delete_stream(self, stream_id: str) -> bool:
        data = self._read_processes()
        streams = data.get("streams", [])
        new = [s for s in streams if s.get("id") != stream_id]
        if len(new) == len(streams):
            return False
        data["streams"] = new
        self._write_processes(data)
        return True

    # --- Subprocesses ---

    def list_subprocesses(self) -> list[dict]:
        return self._read_processes().get("subprocesses", [])

    def get_subprocess(self, sp_id: str) -> Optional[dict]:
        for sp in self.list_subprocesses():
            if sp.get("id") == sp_id:
                return sp
        return None

    def save_subprocess(self, sp: dict) -> dict:
        data = self._read_processes()
        sps = data.setdefault("subprocesses", [])
        for i, s in enumerate(sps):
            if s.get("id") == sp.get("id"):
                sps[i] = sp
                self._write_processes(data)
                return sp
        sps.append(sp)
        self._write_processes(data)
        return sp

    def delete_subprocess(self, sp_id: str) -> bool:
        data = self._read_processes()
        sps = data.get("subprocesses", [])
        new = [s for s in sps if s.get("id") != sp_id]
        if len(new) == len(sps):
            return False
        data["subprocesses"] = new
        self._write_processes(data)
        return True

    # --- Interfaces ---

    def list_interfaces(self) -> list[dict]:
        return self._read_processes().get("interfaces", [])

    def get_interface(self, iface_id: str) -> Optional[dict]:
        for i in self.list_interfaces():
            if i.get("id") == iface_id:
                return i
        return None

    def save_interface(self, iface: dict) -> dict:
        data = self._read_processes()
        ifaces = data.setdefault("interfaces", [])
        for i, existing in enumerate(ifaces):
            if existing.get("id") == iface.get("id"):
                ifaces[i] = iface
                self._write_processes(data)
                return iface
        ifaces.append(iface)
        self._write_processes(data)
        return iface

    def delete_interface(self, iface_id: str) -> bool:
        data = self._read_processes()
        ifaces = data.get("interfaces", [])
        new = [i for i in ifaces if i.get("id") != iface_id]
        if len(new) == len(ifaces):
            return False
        data["interfaces"] = new
        self._write_processes(data)
        return True

    # --- Assessments ---
    # Assessments are keyed by (assessed_object_id, target_option).
    # For subprocess assessments and legacy data, target_option may be None.
    # Stream assessments can have up to 3 records (de_standard, at_standard, central).

    @staticmethod
    def _assessment_key(a: dict) -> tuple:
        return (a.get("assessed_object_id"), a.get("target_option"))

    def list_assessments(self) -> list[dict]:
        return self._read_assessments_data().get("assessments", [])

    def get_assessment(self, obj_id: str, target_option: Optional[str] = None) -> Optional[dict]:
        for a in self.list_assessments():
            if a.get("assessed_object_id") == obj_id:
                if target_option is None or a.get("target_option") == target_option:
                    return a
        return None

    def get_assessments_for_stream(self, stream_id: str) -> list[dict]:
        """Return all option assessments for a stream."""
        return [
            a for a in self.list_assessments()
            if a.get("assessed_object_id") == stream_id
            and a.get("assessed_object_type") == "stream"
        ]

    def save_assessment(self, assessment: dict) -> dict:
        data = self._read_assessments_data()
        assessments = data.setdefault("assessments", [])
        key = self._assessment_key(assessment)
        for i, a in enumerate(assessments):
            if self._assessment_key(a) == key:
                assessments[i] = assessment
                self._write_assessments_data(data)
                return assessment
        assessments.append(assessment)
        self._write_assessments_data(data)
        return assessment

    def delete_assessment(self, obj_id: str, target_option: Optional[str] = None) -> bool:
        data = self._read_assessments_data()
        assessments = data.get("assessments", [])
        new = [
            a for a in assessments
            if not (
                a.get("assessed_object_id") == obj_id
                and (target_option is None or a.get("target_option") == target_option)
            )
        ]
        if len(new) == len(assessments):
            return False
        data["assessments"] = new
        self._write_assessments_data(data)
        return True

    # --- Outcomes ---

    def list_outcomes(self) -> list[dict]:
        return self._read_outcomes_data().get("outcomes", [])

    def get_outcome(self, obj_id: str) -> Optional[dict]:
        for o in self.list_outcomes():
            if o.get("assessed_object_id") == obj_id:
                return o
        return None

    def save_outcome(self, outcome: dict) -> dict:
        data = self._read_outcomes_data()
        outcomes = data.setdefault("outcomes", [])
        obj_id = outcome.get("assessed_object_id")
        for i, o in enumerate(outcomes):
            if o.get("assessed_object_id") == obj_id:
                outcomes[i] = outcome
                self._write_outcomes_data(data)
                return outcome
        outcomes.append(outcome)
        self._write_outcomes_data(data)
        return outcome

    # --- Reviews ---

    def _read_reviews_data(self) -> dict:
        return self._read_yaml(self.data_dir / "reviews.yaml")

    def _write_reviews_data(self, data: dict) -> None:
        self._write_yaml(self.data_dir / "reviews.yaml", data)

    def list_reviews(self) -> list[dict]:
        return self._read_reviews_data().get("reviews", [])

    def get_review(self, stream_id: str) -> Optional[dict]:
        for r in self.list_reviews():
            if r.get("stream_id") == stream_id:
                return r
        return None

    def save_review(self, review: dict) -> dict:
        data = self._read_reviews_data()
        reviews = data.setdefault("reviews", [])
        sid = review.get("stream_id")
        for i, r in enumerate(reviews):
            if r.get("stream_id") == sid:
                reviews[i] = review
                self._write_reviews_data(data)
                return review
        reviews.append(review)
        self._write_reviews_data(data)
        return review

    def delete_review(self, stream_id: str) -> bool:
        data = self._read_reviews_data()
        reviews = data.get("reviews", [])
        new = [r for r in reviews if r.get("stream_id") != stream_id]
        if len(new) == len(reviews):
            return False
        data["reviews"] = new
        self._write_reviews_data(data)
        return True

    # --- Process Analyses ---

    def _read_analyses_data(self) -> dict:
        return self._read_yaml(self._analysis_file)

    def _write_analyses_data(self, data: dict) -> None:
        self._write_yaml(self._analysis_file, data)

    def list_analyses(self) -> list[dict]:
        return self._read_analyses_data().get("analyses", [])

    def get_analysis(self, stream_id: str) -> Optional[dict]:
        for a in self.list_analyses():
            if a.get("stream_id") == stream_id:
                return a
        return None

    def save_analysis(self, analysis: dict) -> dict:
        data = self._read_analyses_data()
        analyses = data.setdefault("analyses", [])
        sid = analysis.get("stream_id")
        for i, a in enumerate(analyses):
            if a.get("stream_id") == sid:
                analyses[i] = analysis
                self._write_analyses_data(data)
                return analysis
        analyses.append(analysis)
        self._write_analyses_data(data)
        return analysis

    def delete_analysis(self, stream_id: str) -> bool:
        data = self._read_analyses_data()
        analyses = data.get("analyses", [])
        new = [a for a in analyses if a.get("stream_id") != stream_id]
        if len(new) == len(analyses):
            return False
        data["analyses"] = new
        self._write_analyses_data(data)
        return True

    # --- Dashboard Stats ---

    def get_dashboard_stats(self) -> dict:
        areas = self.list_areas()
        streams = self.list_streams()
        sps = self.list_subprocesses()
        ifaces = self.list_interfaces()
        assessments = self.list_assessments()
        outcomes = self.list_outcomes()

        stream_assessments = [
            a for a in assessments
            if a.get("assessed_object_type") == "stream"
        ]
        assessed_stream_ids = {a["assessed_object_id"] for a in stream_assessments}
        unassessed_streams = [s for s in streams if s["id"] not in assessed_stream_ids]

        # Count streams with full 3-option assessment coverage
        option_coverage = {}
        for a in stream_assessments:
            sid = a["assessed_object_id"]
            option_coverage.setdefault(sid, set()).add(a.get("target_option", "central"))
        fully_assessed = sum(
            1 for opts in option_coverage.values()
            if {"de_standard", "at_standard", "central"} <= opts
        )

        return {
            "area_count": len(areas),
            "stream_count": len(streams),
            "subprocess_count": len(sps),
            "interface_count": len(ifaces),
            "assessment_count": len(assessments),
            "stream_assessment_count": len(stream_assessments),
            "fully_assessed_streams": fully_assessed,
            "outcome_count": len(outcomes),
            "unassessed_streams": [s["id"] for s in unassessed_streams],
        }

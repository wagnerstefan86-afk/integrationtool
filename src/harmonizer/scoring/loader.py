"""YAML data loader for process and assessment data.

Loads area, stream, subprocess, interface, and assessment definitions
from YAML files and validates them against the Pydantic models.
"""

from pathlib import Path
from typing import Any

import yaml

from harmonizer.models.process import Area, Stream, SubProcess, ProcessInterface
from harmonizer.models.assessment import Assessment


def _load_yaml(path: Path) -> Any:
    """Load a single YAML file and return parsed content."""
    with open(path, "r", encoding="utf-8") as f:
        return yaml.safe_load(f)


def load_structure(path: Path) -> tuple[list[Area], list[Stream], list[SubProcess], list[ProcessInterface]]:
    """Load organizational structure from a YAML file.

    Expected structure:
        areas: [...]
        streams: [...]
        subprocesses: [...]
        interfaces: [...]
    """
    data = _load_yaml(path)
    areas = [Area(**a) for a in data.get("areas", [])]
    streams = [Stream(**s) for s in data.get("streams", [])]
    subprocesses = [SubProcess(**sp) for sp in data.get("subprocesses", [])]
    interfaces = [ProcessInterface(**pi) for pi in data.get("interfaces", [])]
    return areas, streams, subprocesses, interfaces


def load_assessments(path: Path) -> list[Assessment]:
    """Load assessment records from a YAML file.

    Expected structure:
        assessments: [...]
    """
    data = _load_yaml(path)
    return [Assessment(**a) for a in data.get("assessments", [])]


def load_all_from_directory(directory: Path) -> tuple[
    list[Area],
    list[Stream],
    list[SubProcess],
    list[ProcessInterface],
    list[Assessment],
]:
    """Load all YAML files from a directory.

    Files named *assessment* are treated as assessment data.
    All other YAML files are treated as structure definitions.
    """
    all_areas: list[Area] = []
    all_streams: list[Stream] = []
    all_sub: list[SubProcess] = []
    all_iface: list[ProcessInterface] = []
    all_assess: list[Assessment] = []

    for yaml_file in sorted(directory.glob("*.yaml")):
        name = yaml_file.stem.lower()
        if "assessment" in name:
            all_assess.extend(load_assessments(yaml_file))
        else:
            areas, streams, sp, pi = load_structure(yaml_file)
            all_areas.extend(areas)
            all_streams.extend(streams)
            all_sub.extend(sp)
            all_iface.extend(pi)

    return all_areas, all_streams, all_sub, all_iface, all_assess

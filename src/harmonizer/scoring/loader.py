"""YAML data loader for process and assessment data.

Loads process definitions and assessments from YAML files and
validates them against the Pydantic models.
"""

from pathlib import Path
from typing import Any

import yaml

from harmonizer.models.process import MainProcess, SubProcess, ProcessInterface
from harmonizer.models.assessment import Assessment


def _load_yaml(path: Path) -> Any:
    """Load a single YAML file and return parsed content."""
    with open(path, "r", encoding="utf-8") as f:
        return yaml.safe_load(f)


def load_processes(path: Path) -> tuple[list[MainProcess], list[SubProcess], list[ProcessInterface]]:
    """Load process definitions from a YAML file.

    Expected structure:
        main_processes: [...]
        subprocesses: [...]
        interfaces: [...]
    """
    data = _load_yaml(path)
    main_processes = [MainProcess(**mp) for mp in data.get("main_processes", [])]
    subprocesses = [SubProcess(**sp) for sp in data.get("subprocesses", [])]
    interfaces = [ProcessInterface(**pi) for pi in data.get("interfaces", [])]
    return main_processes, subprocesses, interfaces


def load_assessments(path: Path) -> list[Assessment]:
    """Load assessment records from a YAML file.

    Expected structure:
        assessments: [...]
    """
    data = _load_yaml(path)
    return [Assessment(**a) for a in data.get("assessments", [])]


def load_all_from_directory(directory: Path) -> tuple[
    list[MainProcess],
    list[SubProcess],
    list[ProcessInterface],
    list[Assessment],
]:
    """Load all YAML files from a directory.

    Files named *processes* are treated as process definitions.
    Files named *assessment* are treated as assessment data.
    Other YAML files are attempted as process definitions first,
    then as assessments.
    """
    all_main: list[MainProcess] = []
    all_sub: list[SubProcess] = []
    all_iface: list[ProcessInterface] = []
    all_assess: list[Assessment] = []

    for yaml_file in sorted(directory.glob("*.yaml")):
        name = yaml_file.stem.lower()
        if "assessment" in name:
            all_assess.extend(load_assessments(yaml_file))
        else:
            mp, sp, pi = load_processes(yaml_file)
            all_main.extend(mp)
            all_sub.extend(sp)
            all_iface.extend(pi)

    return all_main, all_sub, all_iface, all_assess

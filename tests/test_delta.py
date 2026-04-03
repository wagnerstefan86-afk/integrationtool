"""Tests for the computed delta module."""

import pytest

from harmonizer.scoring.delta import compute_delta, delta_penalty_from_computed, _compare_lists


class TestCompareLists:
    def test_both_empty(self):
        assert _compare_lists([], [], "Tools", True) is None

    def test_identical(self):
        r = _compare_lists(["JIRA", "Confluence"], ["Confluence", "JIRA"], "Tools", True)
        assert r["difference_type"] == "identical"
        assert r["impact"] == "low"

    def test_partial_overlap(self):
        # 3/4 overlap = 75% > 50% → partial
        r = _compare_lists(["JIRA", "Confluence", "Git"], ["JIRA", "Confluence", "ServiceNow"], "Tools", True)
        assert r["difference_type"] == "partial"
        assert r["impact"] == "medium"
        assert "partial" in r["description"].lower()

    def test_no_overlap(self):
        r = _compare_lists(["ServiceNow"], ["JIRA"], "Tools", True)
        assert r["difference_type"] == "different"
        assert r["impact"] == "high"
        assert "servicenow" in r["description"].lower()
        assert "jira" in r["description"].lower()

    def test_missing_at(self):
        r = _compare_lists(["CISO", "DPO"], [], "Roles", True)
        assert r["difference_type"] == "missing"
        assert r["impact"] == "high"
        assert "AT" in r["description"]

    def test_missing_de(self):
        r = _compare_lists([], ["Local ISO"], "Roles", True)
        assert r["difference_type"] == "missing"
        assert r["impact"] == "high"
        assert "DE" in r["description"]

    def test_non_critical_missing(self):
        r = _compare_lists(["quarterly"], [], "Triggers", False)
        assert r["difference_type"] == "missing"
        assert r["impact"] == "medium"  # non-critical → medium not high

    def test_case_insensitive(self):
        r = _compare_lists(["Jira"], ["JIRA"], "Tools", True)
        assert r["difference_type"] == "identical"

    def test_whitespace_stripped(self):
        r = _compare_lists(["  JIRA  "], ["JIRA"], "Tools", True)
        assert r["difference_type"] == "identical"

    def test_empty_strings_skipped(self):
        r = _compare_lists(["JIRA", "", "  "], ["JIRA"], "Tools", True)
        assert r["difference_type"] == "identical"


class TestComputeDelta:
    def test_identical_processes(self):
        de = {"steps": ["a", "b", "c"], "roles": ["R1"], "tools": ["T1"]}
        at = {"steps": ["a", "b", "c"], "roles": ["R1"], "tools": ["T1"]}
        result = compute_delta(de, at)
        assert result["summary"]["high_impact"] == 0
        assert all(i["difference_type"] == "identical" for i in result["items"])

    def test_completely_different_processes(self):
        de = {"steps": ["x", "y", "z"], "roles": ["CISO"], "tools": ["ServiceNow"], "controls": ["ISO-1"]}
        at = {"steps": ["a", "b", "c"], "roles": ["ISO"], "tools": ["JIRA"], "controls": ["BSI-1"]}
        result = compute_delta(de, at)
        assert result["summary"]["high_impact"] >= 3  # steps, roles, tools all differ

    def test_empty_both(self):
        result = compute_delta({}, {})
        assert result["items"] == []
        assert result["summary"]["total_items"] == 0

    def test_one_side_empty(self):
        de = {"steps": ["a", "b", "c"], "roles": ["R"]}
        result = compute_delta(de, {})
        missing = [i for i in result["items"] if i["difference_type"] == "missing"]
        assert len(missing) >= 2  # steps and roles

    def test_all_categories_compared(self):
        de = {
            "triggers": ["t"], "inputs": ["i"], "outputs": ["o"],
            "steps": ["s1", "s2", "s3"], "roles": ["r"], "tools": ["t"],
            "controls": ["c"], "evidence": ["e"], "responsibilities": ["x"],
        }
        at = dict(de)  # identical
        result = compute_delta(de, at)
        categories = {i["category"] for i in result["items"]}
        assert "Process Steps" in categories
        assert "Roles" in categories
        assert "Tools / Systems" in categories

    def test_summary_counts(self):
        de = {"steps": ["a", "b", "c"], "roles": ["CISO"], "tools": ["ServiceNow"]}
        at = {"steps": ["a", "b", "c"], "roles": ["ISO"], "tools": ["JIRA"]}
        result = compute_delta(de, at)
        s = result["summary"]
        assert s["total_items"] == s["high_impact"] + s["medium_impact"] + s["low_impact"]


class TestDeltaPenalty:
    def test_no_items(self):
        assert delta_penalty_from_computed({"items": []}, "de_standard") == 0.0

    def test_all_identical(self):
        items = [{"impact": "low", "difference_type": "identical", "category": "Steps"}]
        assert delta_penalty_from_computed({"items": items}, "de_standard") == 0.0

    def test_high_impact_penalty(self):
        items = [{"impact": "high", "difference_type": "different", "category": "Tools"}]
        p_adoption = delta_penalty_from_computed({"items": items}, "de_standard")
        p_central = delta_penalty_from_computed({"items": items}, "central")
        assert p_adoption > 0
        assert p_central > 0
        assert p_adoption > p_central  # adoption penalized more

    def test_missing_critical_extra_penalty(self):
        items = [{"impact": "high", "difference_type": "missing", "category": "Controls"}]
        p_adoption = delta_penalty_from_computed({"items": items}, "de_standard")
        p_central = delta_penalty_from_computed({"items": items}, "central")
        assert p_adoption > p_central

    def test_penalty_capped(self):
        # Many high-impact items
        items = [
            {"impact": "high", "difference_type": "different", "category": f"Cat{i}"}
            for i in range(20)
        ]
        p = delta_penalty_from_computed({"items": items}, "de_standard")
        assert p <= 0.5

    def test_medium_impact_penalty(self):
        items = [{"impact": "medium", "difference_type": "partial", "category": "Triggers"}]
        p = delta_penalty_from_computed({"items": items}, "central")
        assert p > 0

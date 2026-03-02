"""Tests for comparison/changelog.py — change log generation."""

from __future__ import annotations

import json

from cad_dxf_agent.core.comparison.changelog import (
    ChangeLog,
    DiffSummary,
    generate_changelog,
    generate_summary,
)
from cad_dxf_agent.core.comparison.classifier import classify_changes
from cad_dxf_agent.core.comparison.geometry import extract_snapshots
from cad_dxf_agent.core.comparison.matcher import match_entities
from cad_dxf_agent.models.comparison_schema import ChangeCategory, ComparisonConfig
from tests.helpers.comparison_factory import (
    make_added_removed_pair,
    make_comparison_result,
    make_complex_pair,
    make_entity_change,
    make_identical_pair,
    make_modified_text_pair,
    make_moved_entity_pair,
)


def _run_pipeline(master, revision, config=None):
    config = config or ComparisonConfig(tolerance=10.0, move_threshold=0.25)
    m_snaps = extract_snapshots(master, config)
    r_snaps = extract_snapshots(revision, config)
    mr = match_entities(m_snaps, r_snaps, config)
    return classify_changes(mr, config)


class TestChangeLog:
    def test_to_json_valid(self):
        log = ChangeLog(summary={"added": 1, "removed": 0}, entries=[])
        data = json.loads(log.to_json())
        assert "summary" in data
        assert "entries" in data
        assert "generated_at" in data

    def test_to_text_has_header(self):
        log = ChangeLog(summary={"added": 1, "removed": 0}, entries=[])
        text = log.to_text()
        assert "CHANGE LOG" in text
        assert "SUMMARY" in text

    def test_round_trip(self):
        log = ChangeLog(summary={"added": 2}, entries=[])
        data = json.loads(log.to_json())
        restored = ChangeLog(**data)
        assert restored.summary["added"] == 2


class TestGenerateChangelog:
    def test_identical_files_empty_changelog(self, tmp_path):
        master, revision = make_identical_pair(tmp_path)
        result = _run_pipeline(master, revision)
        log = generate_changelog(result)
        # Only unchanged — no entries
        assert len(log.entries) == 0

    def test_added_removed_has_entries(self, tmp_path):
        master, revision = make_added_removed_pair(tmp_path)
        result = _run_pipeline(master, revision)
        log = generate_changelog(result)
        assert len(log.entries) >= 2  # at least 1 added + 1 removed
        categories = {e.category for e in log.entries}
        assert "added" in categories
        assert "removed" in categories

    def test_moved_entity_entry(self, tmp_path):
        master, revision = make_moved_entity_pair(tmp_path, dx=5.0, dy=5.0)
        config = ComparisonConfig(tolerance=20.0, move_threshold=0.25)
        result = _run_pipeline(master, revision, config)
        log = generate_changelog(result)
        moved = [e for e in log.entries if e.category == "moved"]
        assert len(moved) >= 1
        for m in moved:
            assert m.from_point is not None
            assert m.to_point is not None

    def test_modified_text_entry(self, tmp_path):
        master, revision = make_modified_text_pair(tmp_path)
        config = ComparisonConfig(tolerance=1.0)
        result = _run_pipeline(master, revision, config)
        log = generate_changelog(result)
        modified = [e for e in log.entries if e.category == "modified"]
        assert len(modified) >= 1
        for m in modified:
            assert "text" in m.description.lower() or "modified" in m.description.lower()

    def test_entries_have_entity_type(self, tmp_path):
        master, revision = make_complex_pair(tmp_path)
        result = _run_pipeline(master, revision)
        log = generate_changelog(result)
        for entry in log.entries:
            assert entry.entity_type != "UNKNOWN"
            assert entry.layer != "UNKNOWN"

    def test_text_output_grouped(self, tmp_path):
        master, revision = make_complex_pair(tmp_path)
        result = _run_pipeline(master, revision)
        log = generate_changelog(result)
        text = log.to_text()
        # Text output should have category headers
        assert "CHANGE LOG" in text

    def test_json_output_parseable(self, tmp_path):
        master, revision = make_complex_pair(tmp_path)
        result = _run_pipeline(master, revision)
        log = generate_changelog(result)
        data = json.loads(log.to_json())
        assert isinstance(data["entries"], list)
        assert isinstance(data["summary"], dict)


class TestDiffSummary:
    def test_headline_format(self):
        result = make_comparison_result(
            [
                make_entity_change(ChangeCategory.ADDED),
                make_entity_change(ChangeCategory.REMOVED),
                make_entity_change(ChangeCategory.MOVED, displacement=(5.0, 0.0)),
            ]
        )
        summary = generate_summary(result)
        assert "3 changes" in summary.headline
        assert "1 added" in summary.headline
        assert "1 removed" in summary.headline
        assert "1 moved" in summary.headline

    def test_no_changes(self):
        result = make_comparison_result([])
        summary = generate_summary(result)
        assert summary.headline == "No changes detected"

    def test_large_move_warning(self):
        result = make_comparison_result(
            [
                make_entity_change(ChangeCategory.MOVED, displacement=(15.0, 0.0)),
            ]
        )
        summary = generate_summary(result)
        assert any("moved >10 units" in w for w in summary.warnings)

    def test_low_confidence_warning(self):
        result = make_comparison_result(
            [
                make_entity_change(ChangeCategory.MODIFIED, confidence=0.4),
            ]
        )
        summary = generate_summary(result)
        assert any("low-confidence" in w for w in summary.warnings)

    def test_by_layer_grouping(self):
        result = make_comparison_result(
            [
                make_entity_change(ChangeCategory.ADDED, layer="STRUCT"),
                make_entity_change(ChangeCategory.ADDED, layer="STRUCT"),
                make_entity_change(ChangeCategory.REMOVED, layer="NOTES"),
            ]
        )
        summary = generate_summary(result)
        assert "STRUCT" in summary.by_layer
        assert summary.by_layer["STRUCT"]["added"] == 2
        assert "NOTES" in summary.by_layer
        assert summary.by_layer["NOTES"]["removed"] == 1

    def test_single_change_headline_singular(self):
        result = make_comparison_result(
            [
                make_entity_change(ChangeCategory.ADDED),
            ]
        )
        summary = generate_summary(result)
        assert "1 change:" in summary.headline
        assert "changes" not in summary.headline

    def test_no_large_move_warning_below_threshold(self):
        result = make_comparison_result(
            [
                make_entity_change(ChangeCategory.MOVED, displacement=(5.0, 0.0)),
            ]
        )
        summary = generate_summary(result)
        assert not any("moved >10 units" in w for w in summary.warnings)

    def test_no_low_confidence_warning_at_threshold(self):
        result = make_comparison_result(
            [
                make_entity_change(ChangeCategory.MODIFIED, confidence=0.6),
            ]
        )
        summary = generate_summary(result)
        assert not any("low-confidence" in w for w in summary.warnings)

    def test_diff_summary_is_pydantic_model(self):
        result = make_comparison_result(
            [
                make_entity_change(ChangeCategory.ADDED),
            ]
        )
        summary = generate_summary(result)
        assert isinstance(summary, DiffSummary)
        assert isinstance(summary.headline, str)
        assert isinstance(summary.warnings, list)
        assert isinstance(summary.by_layer, dict)

    def test_unchanged_excluded_from_by_layer(self):
        result = make_comparison_result(
            [
                make_entity_change(ChangeCategory.UNCHANGED, layer="STRUCT"),
                make_entity_change(ChangeCategory.ADDED, layer="NOTES"),
            ]
        )
        summary = generate_summary(result)
        assert "STRUCT" not in summary.by_layer
        assert "NOTES" in summary.by_layer

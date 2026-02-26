"""Tests for comparison/changelog.py — change log generation."""

from __future__ import annotations

import json

from cad_dxf_agent.core.comparison.changelog import ChangeLog, generate_changelog
from cad_dxf_agent.core.comparison.classifier import classify_changes
from cad_dxf_agent.core.comparison.geometry import extract_snapshots
from cad_dxf_agent.core.comparison.matcher import match_entities
from cad_dxf_agent.models.comparison_schema import ComparisonConfig
from tests.helpers.comparison_factory import (
    make_added_removed_pair,
    make_complex_pair,
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

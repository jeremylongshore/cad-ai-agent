"""Tests for comparison/engine.py — full pipeline orchestrator."""

from __future__ import annotations

import json

import pytest

from cad_dxf_agent.core.comparison.engine import ComparisonEngine
from cad_dxf_agent.models.comparison_schema import (
    ChangeCategory,
    ComparisonConfig,
)
from tests.helpers.comparison_factory import (
    make_added_removed_pair,
    make_circle_pair,
    make_complex_pair,
    make_empty_vs_populated,
    make_identical_pair,
    make_modified_text_pair,
    make_moved_entity_pair,
)


class TestComparisonEngine:
    def setup_method(self):
        self.engine = ComparisonEngine()

    def test_identical_files(self, tmp_path):
        master, revision = make_identical_pair(tmp_path)
        result = self.engine.compare(master, revision)
        assert result.total_changes == 0
        assert result.summary["unchanged"] > 0

    def test_moved_entity(self, tmp_path):
        master, revision = make_moved_entity_pair(tmp_path, dx=5.0, dy=5.0)
        config = ComparisonConfig(tolerance=20.0, move_threshold=0.25)
        result = self.engine.compare(master, revision, config)
        categories = {c.category for c in result.changes}
        assert ChangeCategory.MOVED in categories

    def test_added_removed(self, tmp_path):
        master, revision = make_added_removed_pair(tmp_path)
        result = self.engine.compare(master, revision)
        assert result.summary["added"] >= 1
        assert result.summary["removed"] >= 1

    def test_modified_text(self, tmp_path):
        master, revision = make_modified_text_pair(tmp_path)
        config = ComparisonConfig(tolerance=1.0)
        result = self.engine.compare(master, revision, config)
        modified = [c for c in result.changes if c.category == ChangeCategory.MODIFIED]
        assert len(modified) >= 1

    def test_modified_circle(self, tmp_path):
        master, revision = make_circle_pair(tmp_path)
        config = ComparisonConfig(tolerance=1.0)
        result = self.engine.compare(master, revision, config)
        modified = [c for c in result.changes if c.category == ChangeCategory.MODIFIED]
        assert len(modified) >= 1

    def test_empty_master(self, tmp_path):
        master, revision = make_empty_vs_populated(tmp_path)
        result = self.engine.compare(master, revision)
        assert result.summary["added"] >= 1
        assert result.summary["removed"] == 0

    def test_complex(self, tmp_path):
        master, revision = make_complex_pair(tmp_path)
        config = ComparisonConfig(tolerance=10.0, move_threshold=0.25)
        result = self.engine.compare(master, revision, config)
        assert result.total_changes > 0

    def test_file_not_found(self, tmp_path):
        with pytest.raises(FileNotFoundError):
            self.engine.compare(tmp_path / "nope.dxf", tmp_path / "nah.dxf")


class TestComparisonEngineOutputs:
    def setup_method(self):
        self.engine = ComparisonEngine()

    def test_generate_outputs(self, tmp_path):
        master, revision = make_complex_pair(tmp_path)
        config = ComparisonConfig(tolerance=10.0, move_threshold=0.25)
        result = self.engine.compare(master, revision, config)
        output_dir = tmp_path / "outputs"
        outputs = self.engine.generate_outputs(master, revision, result, output_dir)

        # Changelog
        assert outputs.changelog is not None
        assert len(outputs.changelog.entries) > 0

        # Changelog files
        assert (output_dir / "changelog.json").exists()
        assert (output_dir / "changelog.txt").exists()

        # Verify JSON is valid
        data = json.loads((output_dir / "changelog.json").read_text())
        assert "entries" in data

        # Diff overlay DXF
        assert outputs.diff_overlay_path is not None
        assert outputs.diff_overlay_path.exists()

    def test_generate_outputs_identical(self, tmp_path):
        master, revision = make_identical_pair(tmp_path)
        result = self.engine.compare(master, revision)
        output_dir = tmp_path / "outputs"
        outputs = self.engine.generate_outputs(master, revision, result, output_dir)
        assert outputs.changelog is not None
        assert len(outputs.changelog.entries) == 0

    def test_output_dir_created(self, tmp_path):
        master, revision = make_added_removed_pair(tmp_path)
        result = self.engine.compare(master, revision)
        output_dir = tmp_path / "nested" / "output" / "dir"
        outputs = self.engine.generate_outputs(master, revision, result, output_dir)
        assert output_dir.exists()
        assert outputs.diff_overlay_path is not None

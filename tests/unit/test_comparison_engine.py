"""Tests for comparison/engine.py — full pipeline orchestrator."""

from __future__ import annotations

import json

import ezdxf
import pytest

from cad_dxf_agent.core.comparison.engine import ComparisonEngine
from cad_dxf_agent.core.units import DrawingUnitMismatchError
from cad_dxf_agent.models.cad_schema import DrawingUnit
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

    def test_converts_revision_units_to_master_units(self, tmp_path):
        master_doc = ezdxf.new(dxfversion="R2018")
        master_doc.header["$INSUNITS"] = int(DrawingUnit.INCHES)
        master_doc.modelspace().add_line((0, 0), (10, 0))
        master = tmp_path / "master_inches.dxf"
        master_doc.saveas(master)

        revision_doc = ezdxf.new(dxfversion="R2018")
        revision_doc.header["$INSUNITS"] = int(DrawingUnit.MILLIMETERS)
        revision_doc.modelspace().add_line((0, 0), (254, 0))
        revision = tmp_path / "revision_mm.dxf"
        revision_doc.saveas(revision)

        result = self.engine.compare(master, revision)

        assert result.total_changes == 0
        assert result.summary["unchanged"] == 1
        assert any("millimeters to inches" in warning for warning in result.warnings)

    def test_refuses_known_to_unitless_comparison(self, tmp_path):
        unitless_doc = ezdxf.new(dxfversion="R2018")
        unitless_doc.header["$INSUNITS"] = int(DrawingUnit.UNITLESS)
        unitless_doc.modelspace().add_line((0, 0), (10, 0))
        unitless = tmp_path / "unitless.dxf"
        unitless_doc.saveas(unitless)

        metric_doc = ezdxf.new(dxfversion="R2018")
        metric_doc.header["$INSUNITS"] = int(DrawingUnit.MILLIMETERS)
        metric_doc.modelspace().add_line((0, 0), (254, 0))
        metric = tmp_path / "metric.dxf"
        metric_doc.saveas(metric)

        with pytest.raises(DrawingUnitMismatchError, match=r"set \$INSUNITS"):
            self.engine.compare(unitless, metric)

    def test_warns_when_both_drawings_are_unitless(self, tmp_path):
        first = ezdxf.new(dxfversion="R2018")
        first.header["$INSUNITS"] = int(DrawingUnit.UNITLESS)
        first.modelspace().add_line((0, 0), (10, 0))
        master = tmp_path / "unitless_master.dxf"
        first.saveas(master)

        second = ezdxf.new(dxfversion="R2018")
        second.header["$INSUNITS"] = int(DrawingUnit.UNITLESS)
        second.modelspace().add_line((0, 0), (10, 0))
        revision = tmp_path / "unitless_revision.dxf"
        second.saveas(revision)

        result = self.engine.compare(master, revision)

        assert any("unitless $INSUNITS" in warning for warning in result.warnings)


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

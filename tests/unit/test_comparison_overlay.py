"""Tests for comparison/diff_overlay.py — DXF overlay generation."""

from __future__ import annotations

import ezdxf

from cad_dxf_agent.core.comparison.classifier import classify_changes
from cad_dxf_agent.core.comparison.diff_overlay import write_diff_overlay
from cad_dxf_agent.core.comparison.geometry import extract_snapshots
from cad_dxf_agent.core.comparison.matcher import match_entities
from cad_dxf_agent.models.comparison_schema import (
    ComparisonConfig,
    DiffOverlayLayers,
)
from tests.helpers.comparison_factory import (
    make_added_removed_pair,
    make_complex_pair,
    make_identical_pair,
    make_moved_entity_pair,
)


def _run_pipeline(master, revision, config=None):
    """Run extract → match → classify for test helpers."""
    config = config or ComparisonConfig(tolerance=10.0, move_threshold=0.25)
    m_snaps = extract_snapshots(master, config)
    r_snaps = extract_snapshots(revision, config)
    mr = match_entities(m_snaps, r_snaps, config)
    return classify_changes(mr, config)


class TestWriteDiffOverlay:
    def test_creates_output_file(self, tmp_path):
        master, revision = make_added_removed_pair(tmp_path)
        result = _run_pipeline(master, revision)
        output = tmp_path / "output" / "diff.dxf"
        output.parent.mkdir()
        path = write_diff_overlay(master, result, output)
        assert path.exists()
        assert path == output

    def test_overlay_has_four_layers(self, tmp_path):
        master, revision = make_complex_pair(tmp_path)
        result = _run_pipeline(master, revision)
        output = tmp_path / "diff.dxf"
        write_diff_overlay(master, result, output)
        doc = ezdxf.readfile(str(output))
        layer_names = {layer.dxf.name for layer in doc.layers}
        for layer_name, _ in DiffOverlayLayers.ALL:
            assert layer_name in layer_names

    def test_added_entities_on_added_layer(self, tmp_path):
        master, revision = make_added_removed_pair(tmp_path)
        result = _run_pipeline(master, revision)
        output = tmp_path / "diff.dxf"
        write_diff_overlay(master, result, output)
        doc = ezdxf.readfile(str(output))
        msp = doc.modelspace()
        added_entities = [e for e in msp if e.dxf.layer == "AI_ADDED"]
        assert len(added_entities) >= 1

    def test_removed_entities_on_removed_layer(self, tmp_path):
        master, revision = make_added_removed_pair(tmp_path)
        result = _run_pipeline(master, revision)
        output = tmp_path / "diff.dxf"
        write_diff_overlay(master, result, output)
        doc = ezdxf.readfile(str(output))
        msp = doc.modelspace()
        removed_entities = [e for e in msp if e.dxf.layer == "AI_REMOVED"]
        assert len(removed_entities) >= 1

    def test_identical_files_no_overlay_entities(self, tmp_path):
        master, revision = make_identical_pair(tmp_path)
        result = _run_pipeline(master, revision)
        output = tmp_path / "diff.dxf"
        write_diff_overlay(master, result, output)
        doc = ezdxf.readfile(str(output))
        msp = doc.modelspace()
        overlay_layers = {name for name, _ in DiffOverlayLayers.ALL}
        overlay_entities = [e for e in msp if e.dxf.layer in overlay_layers]
        assert len(overlay_entities) == 0

    def test_moved_entities_on_moved_layer(self, tmp_path):
        master, revision = make_moved_entity_pair(tmp_path, dx=5.0, dy=5.0)
        config = ComparisonConfig(tolerance=20.0, move_threshold=0.25)
        result = _run_pipeline(master, revision, config)
        output = tmp_path / "diff.dxf"
        write_diff_overlay(master, result, output)
        doc = ezdxf.readfile(str(output))
        msp = doc.modelspace()
        moved_entities = [e for e in msp if e.dxf.layer == "AI_MOVED"]
        assert len(moved_entities) >= 1

    def test_original_master_untouched(self, tmp_path):
        """write_diff_overlay should not modify the master file."""
        master, revision = make_added_removed_pair(tmp_path)
        master_bytes_before = master.read_bytes()
        result = _run_pipeline(master, revision)
        output = tmp_path / "diff.dxf"
        write_diff_overlay(master, result, output)
        master_bytes_after = master.read_bytes()
        assert master_bytes_before == master_bytes_after

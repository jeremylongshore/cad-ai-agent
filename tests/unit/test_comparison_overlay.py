"""Tests for comparison/diff_overlay.py — DXF overlay generation."""

from __future__ import annotations

import ezdxf

from cad_dxf_agent.core.comparison.classifier import classify_changes
from cad_dxf_agent.core.comparison.diff_overlay import write_diff_overlay
from cad_dxf_agent.core.comparison.geometry import extract_snapshots
from cad_dxf_agent.core.comparison.matcher import match_entities
from cad_dxf_agent.models.cad_schema import EntityType
from cad_dxf_agent.models.comparison_schema import (
    ChangeCategory,
    ComparisonConfig,
    DiffOverlayLayers,
    EntityChange,
)
from tests.helpers.comparison_factory import (
    make_added_removed_pair,
    make_comparison_result,
    make_complex_pair,
    make_geometry_snapshot,
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


# --- Additional overlay entity-type tests ---


class TestDiffOverlayEntityTypes:
    """Test _draw_snapshot() for entity types not exercised by the pipeline tests."""

    def test_circle_added_on_overlay(self, tmp_path):
        """CIRCLE change renders on AI_ADDED layer."""
        snap = make_geometry_snapshot(
            handle="C1",
            entity_type=EntityType.CIRCLE,
            layer="STRUCTURAL",
            points=[(50, 50)],
            attributes={"radius": 10.0},
        )
        change = EntityChange(category=ChangeCategory.ADDED, revision_snapshot=snap)
        result = make_comparison_result([change])

        master, _ = make_identical_pair(tmp_path)
        output = tmp_path / "overlay_circle.dxf"
        write_diff_overlay(master, result, output)

        doc = ezdxf.readfile(str(output))
        added = [e for e in doc.modelspace() if e.dxf.layer == "AI_ADDED"]
        assert len(added) >= 1

    def test_arc_removed_on_overlay(self, tmp_path):
        """ARC change renders on AI_REMOVED layer."""
        snap = make_geometry_snapshot(
            handle="A1",
            entity_type=EntityType.ARC,
            layer="STRUCTURAL",
            points=[(50, 50)],
            attributes={"radius": 10.0, "start_angle": 0.0, "end_angle": 180.0},
        )
        change = EntityChange(category=ChangeCategory.REMOVED, master_snapshot=snap)
        result = make_comparison_result([change])

        master, _ = make_identical_pair(tmp_path)
        output = tmp_path / "overlay_arc.dxf"
        write_diff_overlay(master, result, output)

        doc = ezdxf.readfile(str(output))
        removed = [e for e in doc.modelspace() if e.dxf.layer == "AI_REMOVED"]
        assert len(removed) >= 1

    def test_ellipse_added_on_overlay(self, tmp_path):
        """ELLIPSE change renders on overlay without error."""
        snap = make_geometry_snapshot(
            handle="E1",
            entity_type=EntityType.ELLIPSE,
            layer="STRUCTURAL",
            points=[(30, 30)],
            attributes={"ratio": 0.5, "major_axis": (10, 0, 0)},
        )
        change = EntityChange(category=ChangeCategory.ADDED, revision_snapshot=snap)
        result = make_comparison_result([change])

        master, _ = make_identical_pair(tmp_path)
        output = tmp_path / "overlay_ellipse.dxf"
        write_diff_overlay(master, result, output)

        assert output.exists()
        doc = ezdxf.readfile(str(output))
        added = [e for e in doc.modelspace() if e.dxf.layer == "AI_ADDED"]
        assert len(added) >= 1

    def test_polyline_added_on_overlay(self, tmp_path):
        """POLYLINE change renders as LWPOLYLINE approximation on overlay."""
        snap = make_geometry_snapshot(
            handle="PL1",
            entity_type=EntityType.POLYLINE,
            layer="STRUCTURAL",
            points=[(0, 0), (10, 0), (10, 10)],
        )
        change = EntityChange(category=ChangeCategory.ADDED, revision_snapshot=snap)
        result = make_comparison_result([change])

        master, _ = make_identical_pair(tmp_path)
        output = tmp_path / "overlay_polyline.dxf"
        write_diff_overlay(master, result, output)

        assert output.exists()
        doc = ezdxf.readfile(str(output))
        added = [e for e in doc.modelspace() if e.dxf.layer == "AI_ADDED"]
        assert len(added) >= 1

    def test_solid_fallback_marker_on_overlay(self, tmp_path):
        """SOLID (unhandled type) falls through to centroid marker on overlay."""
        snap = make_geometry_snapshot(
            handle="S1",
            entity_type=EntityType.SOLID,
            layer="STRUCTURAL",
            points=[(10, 10), (20, 10), (20, 20), (10, 20)],
        )
        change = EntityChange(category=ChangeCategory.ADDED, revision_snapshot=snap)
        result = make_comparison_result([change])

        master, _ = make_identical_pair(tmp_path)
        output = tmp_path / "overlay_solid.dxf"
        write_diff_overlay(master, result, output)

        doc = ezdxf.readfile(str(output))
        added = [e for e in doc.modelspace() if e.dxf.layer == "AI_ADDED"]
        # Fallback marker draws 3 entities (two X lines + text label)
        assert len(added) >= 3

    def test_modified_draws_both_snapshots(self, tmp_path):
        """MODIFIED renders both master and revision on AI_MODIFIED layer."""
        m_snap = make_geometry_snapshot(
            handle="M1",
            entity_type=EntityType.LINE,
            layer="STRUCTURAL",
            points=[(0, 0), (10, 0)],
        )
        r_snap = make_geometry_snapshot(
            handle="R1",
            entity_type=EntityType.LINE,
            layer="STRUCTURAL",
            points=[(0, 0), (12, 0)],
        )
        change = EntityChange(
            category=ChangeCategory.MODIFIED,
            master_snapshot=m_snap,
            revision_snapshot=r_snap,
            modifications={"geometry": "endpoint moved"},
        )
        result = make_comparison_result([change])

        master, _ = make_identical_pair(tmp_path)
        output = tmp_path / "overlay_modified.dxf"
        write_diff_overlay(master, result, output)

        doc = ezdxf.readfile(str(output))
        modified = [e for e in doc.modelspace() if e.dxf.layer == "AI_MODIFIED"]
        # Both master and revision snapshots should be drawn
        assert len(modified) >= 2

    def test_moved_draws_snapshot_and_arrow(self, tmp_path):
        """MOVED renders entity at new position plus displacement arrow."""
        m_snap = make_geometry_snapshot(
            handle="MV1",
            entity_type=EntityType.LINE,
            layer="STRUCTURAL",
            points=[(0, 0), (10, 0)],
        )
        r_snap = make_geometry_snapshot(
            handle="MV2",
            entity_type=EntityType.LINE,
            layer="STRUCTURAL",
            points=[(5, 5), (15, 5)],
        )
        change = EntityChange(
            category=ChangeCategory.MOVED,
            master_snapshot=m_snap,
            revision_snapshot=r_snap,
        )
        result = make_comparison_result([change])

        master, _ = make_identical_pair(tmp_path)
        output = tmp_path / "overlay_moved_direct.dxf"
        write_diff_overlay(master, result, output)

        doc = ezdxf.readfile(str(output))
        moved = [e for e in doc.modelspace() if e.dxf.layer == "AI_MOVED"]
        # Snapshot line + arrow line = at least 2 entities
        assert len(moved) >= 2

    def test_insert_draws_marker(self, tmp_path):
        """INSERT change renders as marker (block def not copied to overlay)."""
        snap = make_geometry_snapshot(
            handle="I1",
            entity_type=EntityType.INSERT,
            layer="STRUCTURAL",
            points=[(20, 20)],
            block_name="COL",
        )
        change = EntityChange(category=ChangeCategory.ADDED, revision_snapshot=snap)
        result = make_comparison_result([change])

        master, _ = make_identical_pair(tmp_path)
        output = tmp_path / "overlay_insert.dxf"
        write_diff_overlay(master, result, output)

        doc = ezdxf.readfile(str(output))
        added = [e for e in doc.modelspace() if e.dxf.layer == "AI_ADDED"]
        # Marker = 2 cross lines + 1 text label
        assert len(added) >= 3

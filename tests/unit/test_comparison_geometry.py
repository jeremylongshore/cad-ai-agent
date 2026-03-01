"""Tests for comparison/geometry.py — geometry extraction from DXF."""

from __future__ import annotations

import pytest

from cad_dxf_agent.core.comparison.geometry import apply_profile, extract_snapshots
from cad_dxf_agent.models.cad_schema import EntityType
from cad_dxf_agent.models.comparison_schema import BBoxRegion, ComparisonConfig, ComparisonProfile
from tests.helpers.comparison_factory import (
    make_circle_pair,
    make_complex_pair,
    make_geometry_snapshot,
    make_identical_pair,
)


class TestExtractSnapshots:
    def test_basic_extraction(self, tmp_path):
        master, _ = make_identical_pair(tmp_path)
        snaps = extract_snapshots(master)
        assert len(snaps) > 0

    def test_line_has_two_points(self, tmp_path):
        master, _ = make_identical_pair(tmp_path)
        snaps = extract_snapshots(master)
        lines = [s for s in snaps if s.entity_type == EntityType.LINE]
        assert len(lines) >= 1
        for line in lines:
            assert len(line.points) == 2

    def test_text_has_content(self, tmp_path):
        master, _ = make_identical_pair(tmp_path)
        snaps = extract_snapshots(master)
        texts = [s for s in snaps if s.entity_type == EntityType.TEXT]
        assert len(texts) >= 1
        for text in texts:
            assert text.text_content is not None
            assert len(text.points) == 1

    def test_lwpolyline_has_all_vertices(self, tmp_path):
        master, _ = make_identical_pair(tmp_path)
        snaps = extract_snapshots(master)
        polys = [s for s in snaps if s.entity_type == EntityType.LWPOLYLINE]
        assert len(polys) >= 1
        for poly in polys:
            assert len(poly.points) >= 2

    def test_circle_has_radius(self, tmp_path):
        master, _ = make_circle_pair(tmp_path)
        snaps = extract_snapshots(master)
        circles = [s for s in snaps if s.entity_type == EntityType.CIRCLE]
        assert len(circles) == 1
        assert circles[0].attributes["radius"] == 10.0
        assert circles[0].points[0].x == 50.0
        assert circles[0].points[0].y == 50.0

    def test_file_not_found(self, tmp_path):
        with pytest.raises(FileNotFoundError):
            extract_snapshots(tmp_path / "nonexistent.dxf")

    def test_ignored_layers(self, tmp_path):
        master, _ = make_identical_pair(tmp_path)
        config = ComparisonConfig(ignored_layers=["NOTES"])
        snaps = extract_snapshots(master, config)
        for snap in snaps:
            assert snap.layer != "NOTES"

    def test_focus_entity_types(self, tmp_path):
        master, _ = make_identical_pair(tmp_path)
        config = ComparisonConfig(focus_entity_types=[EntityType.LINE])
        snaps = extract_snapshots(master, config)
        for snap in snaps:
            assert snap.entity_type == EntityType.LINE

    def test_centroid_computed(self, tmp_path):
        master, _ = make_identical_pair(tmp_path)
        snaps = extract_snapshots(master)
        for snap in snaps:
            # Centroid should be finite
            assert snap.centroid.x != float("inf")
            assert snap.centroid.y != float("inf")

    def test_handles_are_strings(self, tmp_path):
        master, _ = make_identical_pair(tmp_path)
        snaps = extract_snapshots(master)
        for snap in snaps:
            assert isinstance(snap.handle, str)
            assert len(snap.handle) > 0

    def test_complex_drawing(self, tmp_path):
        master, _ = make_complex_pair(tmp_path)
        snaps = extract_snapshots(master)
        types = {s.entity_type for s in snaps}
        assert EntityType.LINE in types
        assert EntityType.TEXT in types
        assert EntityType.LWPOLYLINE in types


class TestExtractFromMixedDrawing:
    """Test extraction from a drawing with multiple entity types."""

    def test_all_entities_have_points(self, tmp_path):
        master, _ = make_complex_pair(tmp_path)
        snaps = extract_snapshots(master)
        for snap in snaps:
            assert len(snap.points) > 0, f"{snap.entity_type} has no points"


# --- Helper to build test snapshots quickly ---

def _snaps() -> list:
    """Build a mix of snapshots for apply_profile tests."""
    return [
        make_geometry_snapshot(handle="L1", entity_type=EntityType.LINE, layer="STRUCTURAL", points=[(0, 0), (10, 0)]),
        make_geometry_snapshot(handle="L2", entity_type=EntityType.LINE, layer="GRID", points=[(0, 0), (0, 100)]),
        make_geometry_snapshot(handle="T1", entity_type=EntityType.TEXT, layer="NOTES", points=[(50, 50)], text_content="Note A"),
        make_geometry_snapshot(handle="T2", entity_type=EntityType.TEXT, layer="TITLEBLOCK", points=[(5, 5)], text_content="Title"),
        make_geometry_snapshot(handle="P1", entity_type=EntityType.LWPOLYLINE, layer="STRUCTURAL", points=[(20, 20), (30, 20), (30, 30)]),
        make_geometry_snapshot(handle="I1", entity_type=EntityType.INSERT, layer="STRUCTURAL", points=[(200, 200)], block_name="COL"),
    ]


class TestApplyProfile:
    """Pure unit tests for apply_profile — no DXF, just GeometrySnapshot lists."""

    def test_no_filters(self):
        snaps = _snaps()
        profile = ComparisonProfile()
        result = apply_profile(snaps, profile)
        assert len(result) == len(snaps)

    def test_include_entity_types(self):
        snaps = _snaps()
        profile = ComparisonProfile(include_entity_types=[EntityType.LINE])
        result = apply_profile(snaps, profile)
        assert all(s.entity_type == EntityType.LINE for s in result)
        assert len(result) == 2

    def test_include_layers_regex(self):
        snaps = _snaps()
        profile = ComparisonProfile(include_layers=[r"^STRUCT"])
        result = apply_profile(snaps, profile)
        assert all(s.layer == "STRUCTURAL" for s in result)
        assert len(result) == 3  # L1, P1, I1

    def test_exclude_layers_regex(self):
        snaps = _snaps()
        profile = ComparisonProfile(exclude_layers=[r"(?i)^notes$"])
        result = apply_profile(snaps, profile)
        assert all(s.layer != "NOTES" for s in result)
        assert len(result) == 5

    def test_include_then_exclude(self):
        """Include STRUCTURAL and NOTES, then exclude NOTES — only STRUCTURAL remains."""
        snaps = _snaps()
        profile = ComparisonProfile(
            include_layers=[r"^STRUCTURAL$", r"^NOTES$"],
            exclude_layers=[r"^NOTES$"],
        )
        result = apply_profile(snaps, profile)
        assert all(s.layer == "STRUCTURAL" for s in result)
        assert len(result) == 3

    def test_exclude_regions(self):
        snaps = _snaps()
        # Exclude region covering (0,0)-(15,15) — should drop L1, T2
        profile = ComparisonProfile(
            exclude_regions=[BBoxRegion(min_x=0, min_y=0, max_x=15, max_y=15)],
        )
        result = apply_profile(snaps, profile)
        excluded_handles = {s.handle for s in snaps} - {s.handle for s in result}
        # L1 centroid=(5,0), T2 centroid=(5,5) — both inside
        assert "L1" in excluded_handles
        assert "T2" in excluded_handles

    def test_exclude_regions_edge(self):
        """Boundary is inclusive — entity exactly on edge is excluded."""
        snap = make_geometry_snapshot(
            handle="EDGE", entity_type=EntityType.LINE, layer="X", points=[(10, 10), (10, 10)],
        )
        profile = ComparisonProfile(
            exclude_regions=[BBoxRegion(min_x=10, min_y=10, max_x=20, max_y=20)],
        )
        result = apply_profile([snap], profile)
        assert len(result) == 0


class TestProfileViaExtraction:
    """Integration: profile on ComparisonConfig filters during extract_snapshots."""

    def test_profile_excludes_notes_layer(self, tmp_path):
        master, _ = make_complex_pair(tmp_path)
        config = ComparisonConfig(
            profile=ComparisonProfile(exclude_layers=[r"(?i)^notes$"]),
        )
        snaps = extract_snapshots(master, config)
        assert all(s.layer.upper() != "NOTES" for s in snaps)

    def test_structural_preset_filters(self, tmp_path):
        master, _ = make_complex_pair(tmp_path)
        config = ComparisonConfig(profile=ComparisonProfile.structural())
        snaps = extract_snapshots(master, config)
        # structural() excludes NOTES layer and only includes LINE, LWPOLYLINE, CIRCLE, ARC, INSERT
        allowed_types = {EntityType.LINE, EntityType.LWPOLYLINE, EntityType.CIRCLE, EntityType.ARC, EntityType.INSERT}
        for s in snaps:
            assert s.entity_type in allowed_types, f"{s.entity_type} should be filtered"
            assert not s.layer.upper().startswith("NOTE"), f"Layer {s.layer} should be excluded"

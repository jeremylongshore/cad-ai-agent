"""Tests for comparison/geometry.py — geometry extraction from DXF."""

from __future__ import annotations

import pytest

from cad_dxf_agent.core.comparison.geometry import extract_snapshots
from cad_dxf_agent.models.cad_schema import EntityType
from cad_dxf_agent.models.comparison_schema import ComparisonConfig
from tests.helpers.comparison_factory import (
    make_circle_pair,
    make_complex_pair,
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

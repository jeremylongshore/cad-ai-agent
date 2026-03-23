"""Tests for the zone detector — closed-loop detection and area calculation."""

from __future__ import annotations

from pathlib import Path

import ezdxf
import pytest

from cad_dxf_agent.core.dxf_reader import load_dxf
from cad_dxf_agent.core.zone_detector import (
    _aspect_ratio,
    _polygon_centroid,
    _polygon_perimeter,
    _shoelace_area,
    detect_zones,
)
from cad_dxf_agent.models.cad_schema import DrawingContext, Point2D

# ---------------------------------------------------------------------------
# DXF builder helpers
# ---------------------------------------------------------------------------


def _make_drawing_with_closed_polyline(tmp_path: Path, *, layer: str = "WALL") -> DrawingContext:
    """Create a drawing with a single closed LWPOLYLINE (10x10 square)."""
    doc = ezdxf.new(dxfversion="R2018")
    msp = doc.modelspace()
    doc.layers.add(layer, color=1)
    msp.add_lwpolyline(
        [(0, 0), (10, 0), (10, 10), (0, 10)],
        close=True,
        dxfattribs={"layer": layer},
    )
    path = tmp_path / "closed_poly.dxf"
    doc.saveas(str(path))
    return load_dxf(path)


def _make_drawing_with_open_polyline(tmp_path: Path) -> DrawingContext:
    """Create a drawing with an open LWPOLYLINE (not closed)."""
    doc = ezdxf.new(dxfversion="R2018")
    msp = doc.modelspace()
    doc.layers.add("WALL", color=1)
    msp.add_lwpolyline(
        [(0, 0), (10, 0), (10, 10)],
        close=False,
        dxfattribs={"layer": "WALL"},
    )
    path = tmp_path / "open_poly.dxf"
    doc.saveas(str(path))
    return load_dxf(path)


def _make_drawing_with_multiple_polylines(tmp_path: Path) -> DrawingContext:
    """Create a drawing with two closed polylines (rooms)."""
    doc = ezdxf.new(dxfversion="R2018")
    msp = doc.modelspace()
    doc.layers.add("WALL", color=1)
    # Room 1: 10x10 = area 100
    msp.add_lwpolyline(
        [(0, 0), (10, 0), (10, 10), (0, 10)],
        close=True,
        dxfattribs={"layer": "WALL"},
    )
    # Room 2: 20x15 = area 300
    msp.add_lwpolyline(
        [(20, 0), (40, 0), (40, 15), (20, 15)],
        close=True,
        dxfattribs={"layer": "WALL"},
    )
    path = tmp_path / "multi_poly.dxf"
    doc.saveas(str(path))
    return load_dxf(path)


def _make_drawing_with_lines_rectangle(tmp_path: Path) -> DrawingContext:
    """Create a drawing with 4 LINE segments forming a rectangle."""
    doc = ezdxf.new(dxfversion="R2018")
    msp = doc.modelspace()
    doc.layers.add("WALL", color=1)
    # 20x10 rectangle from 4 lines
    msp.add_line((0, 0), (20, 0), dxfattribs={"layer": "WALL"})
    msp.add_line((20, 0), (20, 10), dxfattribs={"layer": "WALL"})
    msp.add_line((20, 10), (0, 10), dxfattribs={"layer": "WALL"})
    msp.add_line((0, 10), (0, 0), dxfattribs={"layer": "WALL"})
    path = tmp_path / "line_rect.dxf"
    doc.saveas(str(path))
    return load_dxf(path)


def _make_drawing_with_text_labels(tmp_path: Path) -> DrawingContext:
    """Create a drawing with a closed polyline and a nearby text label."""
    doc = ezdxf.new(dxfversion="R2018")
    msp = doc.modelspace()
    doc.layers.add("WALL", color=1)
    doc.layers.add("TEXT", color=3)
    # 15x15 room
    msp.add_lwpolyline(
        [(0, 0), (15, 0), (15, 15), (0, 15)],
        close=True,
        dxfattribs={"layer": "WALL"},
    )
    # Label near centroid
    msp.add_text(
        "KITCHEN",
        dxfattribs={"layer": "TEXT", "height": 2.0, "insert": (7, 7)},
    )
    path = tmp_path / "labeled.dxf"
    doc.saveas(str(path))
    return load_dxf(path)


def _make_drawing_mixed(tmp_path: Path) -> DrawingContext:
    """Drawing with one closed + one open polyline."""
    doc = ezdxf.new(dxfversion="R2018")
    msp = doc.modelspace()
    doc.layers.add("WALL", color=1)
    # Closed
    msp.add_lwpolyline(
        [(0, 0), (10, 0), (10, 10), (0, 10)],
        close=True,
        dxfattribs={"layer": "WALL"},
    )
    # Open
    msp.add_lwpolyline(
        [(20, 0), (30, 0), (30, 10)],
        close=False,
        dxfattribs={"layer": "WALL"},
    )
    path = tmp_path / "mixed.dxf"
    doc.saveas(str(path))
    return load_dxf(path)


def _make_drawing_annotation_only(tmp_path: Path) -> DrawingContext:
    """Drawing with polylines only on annotation layers (should be filtered)."""
    doc = ezdxf.new(dxfversion="R2018")
    msp = doc.modelspace()
    doc.layers.add("WALL", color=1)
    doc.layers.add("NOTES", color=3)
    # Closed polyline on annotation layer
    msp.add_lwpolyline(
        [(0, 0), (10, 0), (10, 10), (0, 10)],
        close=True,
        dxfattribs={"layer": "NOTES"},
    )
    # A wall line to make WALL layer non-empty for classification
    msp.add_line((0, 0), (100, 0), dxfattribs={"layer": "WALL"})
    path = tmp_path / "annotation_only.dxf"
    doc.saveas(str(path))
    return load_dxf(path)


def _make_hallway_drawing(tmp_path: Path) -> DrawingContext:
    """Drawing with a long narrow closed polyline (hallway)."""
    doc = ezdxf.new(dxfversion="R2018")
    msp = doc.modelspace()
    doc.layers.add("WALL", color=1)
    # 50x5 → aspect ratio 10:1
    msp.add_lwpolyline(
        [(0, 0), (50, 0), (50, 5), (0, 5)],
        close=True,
        dxfattribs={"layer": "WALL"},
    )
    path = tmp_path / "hallway.dxf"
    doc.saveas(str(path))
    return load_dxf(path)


# ---------------------------------------------------------------------------
# Closed polyline detection tests
# ---------------------------------------------------------------------------


class TestClosedPolylineDetection:
    """Tests for detecting zones from closed LWPOLYLINE entities."""

    def test_single_closed_polyline(self, tmp_path):
        ctx = _make_drawing_with_closed_polyline(tmp_path)
        result = detect_zones(ctx)
        assert result.zone_count == 1
        assert result.zones[0].area == pytest.approx(100.0)

    def test_multiple_closed_polylines(self, tmp_path):
        ctx = _make_drawing_with_multiple_polylines(tmp_path)
        result = detect_zones(ctx)
        assert result.zone_count == 2
        areas = sorted(z.area for z in result.zones)
        assert areas[0] == pytest.approx(100.0)
        assert areas[1] == pytest.approx(300.0)
        assert result.total_area == pytest.approx(400.0)

    def test_open_polyline_not_detected(self, tmp_path):
        ctx = _make_drawing_with_open_polyline(tmp_path)
        result = detect_zones(ctx)
        assert result.zone_count == 0

    def test_mixed_closed_and_open(self, tmp_path):
        ctx = _make_drawing_mixed(tmp_path)
        result = detect_zones(ctx)
        assert result.zone_count == 1
        assert result.zones[0].area == pytest.approx(100.0)

    def test_layer_filtering(self, tmp_path):
        """Polylines on annotation layers should be filtered out."""
        ctx = _make_drawing_annotation_only(tmp_path)
        result = detect_zones(ctx)
        assert result.zone_count == 0


class TestLineSegmentCycles:
    """Tests for detecting zones from connected LINE segments."""

    def test_rectangle_from_lines(self, tmp_path):
        ctx = _make_drawing_with_lines_rectangle(tmp_path)
        result = detect_zones(ctx)
        assert result.zone_count >= 1
        # At least one zone should have the expected area (20x10 = 200)
        areas = [z.area for z in result.zones]
        assert any(pytest.approx(200.0, rel=0.01) == a for a in areas)


# ---------------------------------------------------------------------------
# Area calculation tests
# ---------------------------------------------------------------------------


class TestAreaCalculation:
    """Tests for shoelace formula accuracy."""

    def test_unit_square(self):
        verts = [
            Point2D(x=0, y=0),
            Point2D(x=1, y=0),
            Point2D(x=1, y=1),
            Point2D(x=0, y=1),
        ]
        assert _shoelace_area(verts) == pytest.approx(1.0)

    def test_known_rectangle(self):
        verts = [
            Point2D(x=0, y=0),
            Point2D(x=20, y=0),
            Point2D(x=20, y=10),
            Point2D(x=0, y=10),
        ]
        assert _shoelace_area(verts) == pytest.approx(200.0)

    def test_triangle(self):
        verts = [
            Point2D(x=0, y=0),
            Point2D(x=10, y=0),
            Point2D(x=5, y=8),
        ]
        assert _shoelace_area(verts) == pytest.approx(40.0)

    def test_reversed_winding(self):
        """Shoelace should return positive area regardless of winding."""
        verts_cw = [
            Point2D(x=0, y=0),
            Point2D(x=0, y=10),
            Point2D(x=10, y=10),
            Point2D(x=10, y=0),
        ]
        verts_ccw = list(reversed(verts_cw))
        assert _shoelace_area(verts_cw) == pytest.approx(_shoelace_area(verts_ccw))

    def test_empty_vertices(self):
        assert _shoelace_area([]) == 0.0

    def test_two_vertices(self):
        assert _shoelace_area([Point2D(x=0, y=0), Point2D(x=1, y=1)]) == 0.0


class TestPerimeter:
    """Tests for polygon perimeter calculation."""

    def test_unit_square_perimeter(self):
        verts = [
            Point2D(x=0, y=0),
            Point2D(x=1, y=0),
            Point2D(x=1, y=1),
            Point2D(x=0, y=1),
        ]
        assert _polygon_perimeter(verts) == pytest.approx(4.0)

    def test_rectangle_perimeter(self):
        verts = [
            Point2D(x=0, y=0),
            Point2D(x=20, y=0),
            Point2D(x=20, y=10),
            Point2D(x=0, y=10),
        ]
        assert _polygon_perimeter(verts) == pytest.approx(60.0)


class TestCentroid:
    """Tests for polygon centroid calculation."""

    def test_square_centroid(self):
        verts = [
            Point2D(x=0, y=0),
            Point2D(x=10, y=0),
            Point2D(x=10, y=10),
            Point2D(x=0, y=10),
        ]
        c = _polygon_centroid(verts)
        assert c.x == pytest.approx(5.0)
        assert c.y == pytest.approx(5.0)

    def test_empty_centroid(self):
        c = _polygon_centroid([])
        assert c.x == 0.0
        assert c.y == 0.0


# ---------------------------------------------------------------------------
# Zone classification tests
# ---------------------------------------------------------------------------


class TestZoneClassification:
    """Tests for zone type inference."""

    def test_classification_by_nearby_text(self, tmp_path):
        ctx = _make_drawing_with_text_labels(tmp_path)
        result = detect_zones(ctx)
        assert result.zone_count == 1
        assert result.zones[0].inferred_type == "kitchen"

    def test_hallway_by_aspect_ratio(self, tmp_path):
        ctx = _make_hallway_drawing(tmp_path)
        result = detect_zones(ctx)
        assert result.zone_count == 1
        assert result.zones[0].inferred_type == "hallway"

    def test_closet_by_area(self, tmp_path):
        """Small area (< 20 sq units) → closet."""
        doc = ezdxf.new(dxfversion="R2018")
        msp = doc.modelspace()
        doc.layers.add("WALL", color=1)
        # 4x4 = 16 sq units
        msp.add_lwpolyline(
            [(0, 0), (4, 0), (4, 4), (0, 4)],
            close=True,
            dxfattribs={"layer": "WALL"},
        )
        path = tmp_path / "closet.dxf"
        doc.saveas(str(path))
        ctx = load_dxf(path)
        result = detect_zones(ctx)
        assert result.zone_count == 1
        assert result.zones[0].inferred_type == "closet"

    def test_room_by_area(self, tmp_path):
        """Medium area (80-300 sq units) → room."""
        ctx = _make_drawing_with_closed_polyline(tmp_path)
        result = detect_zones(ctx)
        assert result.zone_count == 1
        # 10x10 = 100, classified as "room"
        assert result.zones[0].inferred_type == "room"

    def test_large_room_by_area(self, tmp_path):
        """Large area (300-600 sq units) → large_room."""
        doc = ezdxf.new(dxfversion="R2018")
        msp = doc.modelspace()
        doc.layers.add("WALL", color=1)
        # 20x20 = 400 sq units
        msp.add_lwpolyline(
            [(0, 0), (20, 0), (20, 20), (0, 20)],
            close=True,
            dxfattribs={"layer": "WALL"},
        )
        path = tmp_path / "large_room.dxf"
        doc.saveas(str(path))
        ctx = load_dxf(path)
        result = detect_zones(ctx)
        assert result.zone_count == 1
        assert result.zones[0].inferred_type == "large_room"

    def test_open_area_by_area(self, tmp_path):
        """Very large area (> 600 sq units) → open_area."""
        doc = ezdxf.new(dxfversion="R2018")
        msp = doc.modelspace()
        doc.layers.add("WALL", color=1)
        # 30x30 = 900 sq units
        msp.add_lwpolyline(
            [(0, 0), (30, 0), (30, 30), (0, 30)],
            close=True,
            dxfattribs={"layer": "WALL"},
        )
        path = tmp_path / "open_area.dxf"
        doc.saveas(str(path))
        ctx = load_dxf(path)
        result = detect_zones(ctx)
        assert result.zone_count == 1
        assert result.zones[0].inferred_type == "open_area"


# ---------------------------------------------------------------------------
# Edge cases
# ---------------------------------------------------------------------------


class TestEdgeCases:
    """Edge cases and boundary conditions."""

    def test_empty_drawing(self):
        ctx = DrawingContext(file_path="empty.dxf")
        result = detect_zones(ctx)
        assert result.zone_count == 0
        assert result.confidence == 0.0
        assert result.total_area == 0.0

    def test_no_polylines_or_lines(self, tmp_path):
        """Drawing with only text entities → no zones."""
        doc = ezdxf.new(dxfversion="R2018")
        msp = doc.modelspace()
        doc.layers.add("TEXT", color=3)
        msp.add_text("Hello", dxfattribs={"layer": "TEXT", "height": 2.0, "insert": (0, 0)})
        path = tmp_path / "text_only.dxf"
        doc.saveas(str(path))
        ctx = load_dxf(path)
        result = detect_zones(ctx)
        assert result.zone_count == 0

    def test_tolerance_handling(self, tmp_path):
        """Near-miss closure within tolerance should be detected."""
        doc = ezdxf.new(dxfversion="R2018")
        msp = doc.modelspace()
        doc.layers.add("WALL", color=1)
        # Almost-closed polyline (last vertex 0.3 units from first)
        msp.add_lwpolyline(
            [(0, 0), (10, 0), (10, 10), (0, 10), (0.2, 0.2)],
            close=False,
            dxfattribs={"layer": "WALL"},
        )
        path = tmp_path / "near_close.dxf"
        doc.saveas(str(path))
        ctx = load_dxf(path)
        result = detect_zones(ctx, tolerance=0.5)
        assert result.zone_count == 1

    def test_tight_tolerance_rejects_near_miss(self, tmp_path):
        """With tight tolerance, near-miss should not be detected."""
        doc = ezdxf.new(dxfversion="R2018")
        msp = doc.modelspace()
        doc.layers.add("WALL", color=1)
        # Gap of 1.0 units
        msp.add_lwpolyline(
            [(0, 0), (10, 0), (10, 10), (0, 10), (0, 1)],
            close=False,
            dxfattribs={"layer": "WALL"},
        )
        path = tmp_path / "miss.dxf"
        doc.saveas(str(path))
        ctx = load_dxf(path)
        result = detect_zones(ctx, tolerance=0.1)
        assert result.zone_count == 0

    def test_confidence_scales_with_zone_count(self, tmp_path):
        ctx = _make_drawing_with_multiple_polylines(tmp_path)
        result = detect_zones(ctx)
        assert result.confidence == pytest.approx(0.4)  # 2 zones * 0.2

    def test_source_handles_populated(self, tmp_path):
        ctx = _make_drawing_with_closed_polyline(tmp_path)
        result = detect_zones(ctx)
        assert result.zone_count == 1
        assert len(result.zones[0].source_handles) == 1
        assert result.zones[0].source_handles[0]  # non-empty handle

    def test_perimeter_computed(self, tmp_path):
        ctx = _make_drawing_with_closed_polyline(tmp_path)
        result = detect_zones(ctx)
        assert result.zones[0].perimeter == pytest.approx(40.0)

    def test_centroid_inside_zone(self, tmp_path):
        ctx = _make_drawing_with_closed_polyline(tmp_path)
        result = detect_zones(ctx)
        c = result.zones[0].centroid
        assert c.x == pytest.approx(5.0)
        assert c.y == pytest.approx(5.0)


class TestAspectRatio:
    """Tests for the aspect ratio helper."""

    def test_square(self):
        verts = [
            Point2D(x=0, y=0),
            Point2D(x=10, y=0),
            Point2D(x=10, y=10),
            Point2D(x=0, y=10),
        ]
        assert _aspect_ratio(verts) == pytest.approx(1.0)

    def test_wide_rectangle(self):
        verts = [
            Point2D(x=0, y=0),
            Point2D(x=50, y=0),
            Point2D(x=50, y=5),
            Point2D(x=0, y=5),
        ]
        assert _aspect_ratio(verts) == pytest.approx(10.0)

    def test_single_point(self):
        assert _aspect_ratio([Point2D(x=0, y=0)]) == 1.0


# ---------------------------------------------------------------------------
# Geometry helper reference-value tests
# ---------------------------------------------------------------------------


class TestGeometryHelpers:
    """Reference-value assertions for geometry functions.

    These serve as regression tests with exact expected values,
    and as Shapely-equivalent reference tests for future migration.
    """

    def test_square_10x10_area(self):
        """10x10 square: area = 100.0"""
        points = [Point2D(x=0, y=0), Point2D(x=10, y=0), Point2D(x=10, y=10), Point2D(x=0, y=10)]
        assert _shoelace_area(points) == pytest.approx(100.0)

    def test_square_10x10_perimeter(self):
        """10x10 square: perimeter = 40.0"""
        points = [Point2D(x=0, y=0), Point2D(x=10, y=0), Point2D(x=10, y=10), Point2D(x=0, y=10)]
        assert _polygon_perimeter(points) == pytest.approx(40.0)

    def test_square_10x10_centroid(self):
        """10x10 square: centroid = (5.0, 5.0)"""
        points = [Point2D(x=0, y=0), Point2D(x=10, y=0), Point2D(x=10, y=10), Point2D(x=0, y=10)]
        c = _polygon_centroid(points)
        assert c.x == pytest.approx(5.0)
        assert c.y == pytest.approx(5.0)

    def test_square_10x10_aspect_ratio(self):
        """10x10 square: aspect_ratio = 1.0"""
        points = [Point2D(x=0, y=0), Point2D(x=10, y=0), Point2D(x=10, y=10), Point2D(x=0, y=10)]
        assert _aspect_ratio(points) == pytest.approx(1.0)

    def test_rectangle_10x5_aspect_ratio(self):
        """10x5 rectangle: aspect_ratio = 2.0"""
        points = [Point2D(x=0, y=0), Point2D(x=10, y=0), Point2D(x=10, y=5), Point2D(x=0, y=5)]
        assert _aspect_ratio(points) == pytest.approx(2.0)

    def test_rectangle_10x5_area(self):
        """10x5 rectangle: area = 50.0"""
        points = [Point2D(x=0, y=0), Point2D(x=10, y=0), Point2D(x=10, y=5), Point2D(x=0, y=5)]
        assert _shoelace_area(points) == pytest.approx(50.0)

    def test_rectangle_20x15_area(self):
        """20x15 rectangle: area = 300.0"""
        points = [Point2D(x=0, y=0), Point2D(x=20, y=0), Point2D(x=20, y=15), Point2D(x=0, y=15)]
        assert _shoelace_area(points) == pytest.approx(300.0)

    def test_degenerate_polygon_two_vertices(self):
        """Degenerate polygon (< 3 vertices): area = 0.0 without raising."""
        points = [Point2D(x=0, y=0), Point2D(x=10, y=0)]
        assert _shoelace_area(points) == pytest.approx(0.0)

    def test_degenerate_polygon_single_vertex(self):
        """Single vertex: area = 0.0 without raising."""
        points = [Point2D(x=5, y=5)]
        assert _shoelace_area(points) == pytest.approx(0.0)

    def test_degenerate_polygon_empty(self):
        """Empty polygon: area = 0.0 without raising."""
        points: list[Point2D] = []
        assert _shoelace_area(points) == pytest.approx(0.0)

    def test_triangle_area(self):
        """Right triangle (0,0)-(10,0)-(0,10): area = 50.0"""
        points = [Point2D(x=0, y=0), Point2D(x=10, y=0), Point2D(x=0, y=10)]
        assert _shoelace_area(points) == pytest.approx(50.0)

    def test_offset_rectangle_centroid(self):
        """Rectangle at (20,0)-(40,15): centroid = (30.0, 7.5)"""
        points = [Point2D(x=20, y=0), Point2D(x=40, y=0), Point2D(x=40, y=15), Point2D(x=20, y=15)]
        c = _polygon_centroid(points)
        assert c.x == pytest.approx(30.0)
        assert c.y == pytest.approx(7.5)

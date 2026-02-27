"""Tests for core/comparison/canonical.py — quantization and normalization primitives."""

from __future__ import annotations

import pytest

from cad_dxf_agent.core.comparison.canonical import (
    DEFAULT_QUANTIZATION,
    QuantizationConfig,
    canonical_points,
    quantize_point,
    quantize_points,
    quantize_value,
    remove_near_duplicate_vertices,
    spatial_bin,
)
from cad_dxf_agent.models.cad_schema import EntityType, Point2D


class TestQuantizePoint:
    """Point quantization rounds coordinates to configured precision."""

    def test_default_4dp(self):
        pt = quantize_point(Point2D(x=1.000049999, y=2.000050001))
        assert pt.x == 1.0
        assert pt.y == 2.0001

    def test_rounds_consistently(self):
        """round() at 4dp is deterministic — same input always gives same output."""
        pt_a = quantize_point(Point2D(x=1.00005, y=2.00015))
        pt_b = quantize_point(Point2D(x=1.00005, y=2.00015))
        assert pt_a == pt_b
        # Exact values depend on float representation, but must be stable
        assert pt_a.x == round(1.00005, 4)
        assert pt_a.y == round(2.00015, 4)

    def test_custom_precision(self):
        config = QuantizationConfig(decimal_places=2)
        pt = quantize_point(Point2D(x=1.556, y=2.444), config)
        assert pt.x == 1.56
        assert pt.y == 2.44

    def test_zero_precision(self):
        config = QuantizationConfig(decimal_places=0)
        pt = quantize_point(Point2D(x=1.7, y=2.3), config)
        assert pt.x == 2.0
        assert pt.y == 2.0

    def test_negative_coordinates(self):
        pt = quantize_point(Point2D(x=-1.00006, y=-2.00004))
        assert pt.x == -1.0001
        assert pt.y == -2.0

    def test_large_coordinates(self):
        pt = quantize_point(Point2D(x=99999.12345678, y=-88888.87654321))
        assert pt.x == 99999.1235
        assert pt.y == -88888.8765

    def test_already_quantized_unchanged(self):
        pt = quantize_point(Point2D(x=1.0001, y=2.0002))
        assert pt.x == 1.0001
        assert pt.y == 2.0002

    def test_idempotent(self):
        """Quantizing twice gives same result as once."""
        original = Point2D(x=1.000049999, y=2.000050001)
        once = quantize_point(original)
        twice = quantize_point(once)
        assert once == twice


class TestQuantizePoints:
    def test_empty_list(self):
        assert quantize_points([]) == []

    def test_list_of_points(self):
        pts = [Point2D(x=1.00006, y=2.00004), Point2D(x=3.00008, y=4.00002)]
        result = quantize_points(pts)
        assert len(result) == 2
        assert result[0].x == 1.0001
        assert result[1].x == 3.0001


class TestQuantizeValue:
    def test_default_4dp(self):
        assert quantize_value(10.00006) == 10.0001

    def test_custom_precision(self):
        config = QuantizationConfig(decimal_places=1)
        assert quantize_value(10.55, config) == 10.6

    def test_idempotent(self):
        v = quantize_value(3.14159)
        assert quantize_value(v) == v


class TestRemoveNearDuplicateVertices:
    def test_no_duplicates(self):
        pts = [Point2D(x=0, y=0), Point2D(x=10, y=0), Point2D(x=10, y=10)]
        result = remove_near_duplicate_vertices(pts)
        assert len(result) == 3

    def test_consecutive_duplicates_removed(self):
        pts = [
            Point2D(x=0, y=0),
            Point2D(x=0.00001, y=0.00001),  # near-dup of first
            Point2D(x=10, y=0),
        ]
        result = remove_near_duplicate_vertices(pts)
        assert len(result) == 2
        assert result[0] == Point2D(x=0, y=0)
        assert result[1] == Point2D(x=10, y=0)

    def test_non_consecutive_duplicates_preserved(self):
        """Closed shape that revisits start point should keep both."""
        pts = [
            Point2D(x=0, y=0),
            Point2D(x=10, y=0),
            Point2D(x=10, y=10),
            Point2D(x=0, y=0),  # same as first, but not consecutive
        ]
        result = remove_near_duplicate_vertices(pts)
        assert len(result) == 4

    def test_all_same_point(self):
        pts = [Point2D(x=5, y=5)] * 5
        result = remove_near_duplicate_vertices(pts)
        assert len(result) == 1

    def test_empty_list(self):
        assert remove_near_duplicate_vertices([]) == []

    def test_single_point(self):
        pts = [Point2D(x=1, y=1)]
        assert remove_near_duplicate_vertices(pts) == pts

    def test_disabled_when_epsilon_zero(self):
        config = QuantizationConfig(near_vertex_epsilon=0.0)
        pts = [Point2D(x=0, y=0), Point2D(x=0.00001, y=0), Point2D(x=10, y=0)]
        result = remove_near_duplicate_vertices(pts, config)
        assert len(result) == 3  # no removal

    def test_custom_epsilon(self):
        config = QuantizationConfig(near_vertex_epsilon=1.0)
        pts = [Point2D(x=0, y=0), Point2D(x=0.5, y=0), Point2D(x=10, y=0)]
        result = remove_near_duplicate_vertices(pts, config)
        assert len(result) == 2  # 0.5 is within 1.0 of 0


class TestSpatialBin:
    def test_origin(self):
        assert spatial_bin(Point2D(x=0.1, y=0.1)) == (0, 0)

    def test_positive_coordinates(self):
        assert spatial_bin(Point2D(x=0.5, y=0.5)) == (2, 2)  # 0.5 / 0.25 = 2

    def test_negative_coordinates(self):
        bx, by = spatial_bin(Point2D(x=-1.0, y=-1.0))
        assert bx == -4  # -1.0 / 0.25 = -4
        assert by == -4

    def test_custom_bin_size(self):
        config = QuantizationConfig(spatial_bin_size=1.0)
        assert spatial_bin(Point2D(x=2.5, y=3.7), config) == (2, 3)

    def test_same_bin_for_nearby_points(self):
        a = spatial_bin(Point2D(x=1.0, y=1.0))
        b = spatial_bin(Point2D(x=1.1, y=1.1))
        assert a == b

    def test_different_bins_for_far_points(self):
        a = spatial_bin(Point2D(x=0.0, y=0.0))
        b = spatial_bin(Point2D(x=10.0, y=10.0))
        assert a != b


class TestDefaultConfig:
    def test_default_values(self):
        assert DEFAULT_QUANTIZATION.decimal_places == 4
        assert DEFAULT_QUANTIZATION.near_vertex_epsilon == 0.0001
        assert DEFAULT_QUANTIZATION.spatial_bin_size == 0.25

    def test_frozen(self):
        with pytest.raises(AttributeError):
            DEFAULT_QUANTIZATION.decimal_places = 3  # type: ignore[misc]


class TestCanonicalPointsLine:
    """LINE normalization: endpoints sorted so lower-x (then y) first."""

    def test_already_sorted(self):
        pts = [Point2D(x=0, y=0), Point2D(x=10, y=0)]
        result = canonical_points(pts, EntityType.LINE)
        assert result[0].x <= result[1].x

    def test_reversed_line_normalized(self):
        """LINE(10,0 → 0,0) should become LINE(0,0 → 10,0)."""
        pts = [Point2D(x=10, y=0), Point2D(x=0, y=0)]
        result = canonical_points(pts, EntityType.LINE)
        assert result[0] == Point2D(x=0, y=0)
        assert result[1] == Point2D(x=10, y=0)

    def test_both_directions_produce_same_result(self):
        forward = canonical_points(
            [Point2D(x=0, y=0), Point2D(x=10, y=5)], EntityType.LINE
        )
        reverse = canonical_points(
            [Point2D(x=10, y=5), Point2D(x=0, y=0)], EntityType.LINE
        )
        assert forward == reverse

    def test_same_x_sorts_by_y(self):
        pts = [Point2D(x=5, y=10), Point2D(x=5, y=0)]
        result = canonical_points(pts, EntityType.LINE)
        assert result[0] == Point2D(x=5, y=0)
        assert result[1] == Point2D(x=5, y=10)

    def test_quantization_applied(self):
        pts = [Point2D(x=0.000049, y=0), Point2D(x=10.000051, y=0)]
        result = canonical_points(pts, EntityType.LINE)
        assert result[0] == Point2D(x=0.0, y=0.0)
        assert result[1] == Point2D(x=10.0001, y=0.0)

    def test_identical_endpoints_kept(self):
        """Degenerate zero-length line — both points same after quantization."""
        pts = [Point2D(x=5, y=5), Point2D(x=5, y=5)]
        result = canonical_points(pts, EntityType.LINE)
        assert len(result) == 2  # not deduplicated — LINE always has 2 points


class TestCanonicalPointsPolyline:
    """LWPOLYLINE normalization: preserves vertex order, quantizes, deduplicates."""

    def test_order_preserved(self):
        pts = [Point2D(x=0, y=0), Point2D(x=10, y=0), Point2D(x=10, y=10), Point2D(x=0, y=10)]
        result = canonical_points(pts, EntityType.LWPOLYLINE)
        assert result == [
            Point2D(x=0, y=0),
            Point2D(x=10, y=0),
            Point2D(x=10, y=10),
            Point2D(x=0, y=10),
        ]

    def test_near_duplicate_vertices_removed(self):
        pts = [
            Point2D(x=0, y=0),
            Point2D(x=0.00001, y=0.00001),  # near-dup
            Point2D(x=10, y=0),
            Point2D(x=10, y=10),
        ]
        result = canonical_points(pts, EntityType.LWPOLYLINE)
        assert len(result) == 3

    def test_quantization_applied(self):
        pts = [Point2D(x=0.00006, y=0.00004), Point2D(x=10.00006, y=0)]
        result = canonical_points(pts, EntityType.LWPOLYLINE)
        assert result[0] == Point2D(x=0.0001, y=0.0)
        assert result[1] == Point2D(x=10.0001, y=0.0)


class TestCanonicalPointsSinglePoint:
    """Single-point entities (TEXT, INSERT, CIRCLE, etc.): just quantize."""

    def test_text_quantized(self):
        pts = [Point2D(x=5.00006, y=10.00004)]
        result = canonical_points(pts, EntityType.TEXT)
        assert result == [Point2D(x=5.0001, y=10.0)]

    def test_insert_quantized(self):
        pts = [Point2D(x=100.123456, y=200.654321)]
        result = canonical_points(pts, EntityType.INSERT)
        assert result == [Point2D(x=100.1235, y=200.6543)]

    def test_circle_quantized(self):
        pts = [Point2D(x=50.00009, y=50.00001)]
        result = canonical_points(pts, EntityType.CIRCLE)
        assert result == [Point2D(x=50.0001, y=50.0)]


class TestCanonicalPointsIdempotent:
    """Applying canonical_points twice gives same result as once."""

    def test_line_idempotent(self):
        pts = [Point2D(x=10.00006, y=5.00004), Point2D(x=0.00006, y=0.00004)]
        once = canonical_points(pts, EntityType.LINE)
        twice = canonical_points(once, EntityType.LINE)
        assert once == twice

    def test_polyline_idempotent(self):
        pts = [Point2D(x=0.00006, y=0), Point2D(x=10.00006, y=0), Point2D(x=10, y=10)]
        once = canonical_points(pts, EntityType.LWPOLYLINE)
        twice = canonical_points(once, EntityType.LWPOLYLINE)
        assert once == twice

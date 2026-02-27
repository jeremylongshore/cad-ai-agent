"""Tests for core/comparison/canonical.py — quantization and normalization primitives."""

from __future__ import annotations

import pytest

from cad_dxf_agent.core.comparison.canonical import (
    DEFAULT_QUANTIZATION,
    GeometrySignature,
    QuantizationConfig,
    canonical_points,
    compute_signature,
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


# ============================================================
# Geometry Signature tests
# ============================================================


class TestSignatureLine:
    """LINE signatures: length + angle bucket + midpoint bin."""

    def test_basic_horizontal(self):
        pts = [Point2D(x=0, y=0), Point2D(x=10, y=0)]
        sig = compute_signature(EntityType.LINE, pts)
        assert sig.entity_type == "LINE"
        assert sig.length == 10.0
        assert sig.angle_bucket == 0  # 0° = horizontal

    def test_basic_vertical(self):
        pts = [Point2D(x=0, y=0), Point2D(x=0, y=10)]
        sig = compute_signature(EntityType.LINE, pts)
        assert sig.length == 10.0
        assert sig.angle_bucket == 18  # 90° / 5° = 18

    def test_diagonal_45deg(self):
        pts = [Point2D(x=0, y=0), Point2D(x=10, y=10)]
        sig = compute_signature(EntityType.LINE, pts)
        assert sig.angle_bucket == 9  # 45° / 5° = 9

    def test_direction_independent(self):
        """LINE(A→B) and LINE(B→A) produce same signature."""
        pts_fwd = [Point2D(x=0, y=0), Point2D(x=10, y=5)]
        pts_rev = [Point2D(x=10, y=5), Point2D(x=0, y=0)]
        sig_fwd = compute_signature(EntityType.LINE, pts_fwd)
        sig_rev = compute_signature(EntityType.LINE, pts_rev)
        assert sig_fwd.length == sig_rev.length
        assert sig_fwd.angle_bucket == sig_rev.angle_bucket

    def test_small_noise_stable(self):
        """±0.001" noise doesn't change LINE signature."""
        pts_clean = [Point2D(x=0, y=0), Point2D(x=10, y=0)]
        pts_noisy = [Point2D(x=0.001, y=-0.001), Point2D(x=9.999, y=0.001)]
        sig_clean = compute_signature(EntityType.LINE, pts_clean)
        sig_noisy = compute_signature(EntityType.LINE, pts_noisy)
        assert sig_clean.length == sig_noisy.length  # Both round to 10.0
        assert sig_clean.angle_bucket == sig_noisy.angle_bucket

    def test_large_change_detected(self):
        """Moving a LINE endpoint significantly changes its signature."""
        pts_orig = [Point2D(x=0, y=0), Point2D(x=10, y=0)]
        pts_moved = [Point2D(x=0, y=0), Point2D(x=20, y=0)]
        sig_orig = compute_signature(EntityType.LINE, pts_orig)
        sig_moved = compute_signature(EntityType.LINE, pts_moved)
        assert sig_orig.length != sig_moved.length


class TestSignaturePolyline:
    """Polyline signatures: vertex count + perimeter + turn hash."""

    def test_rectangle(self):
        # Open polyline: 4 vertices = 3 segments (10+5+10 = 25)
        pts = [
            Point2D(x=0, y=0), Point2D(x=10, y=0),
            Point2D(x=10, y=5), Point2D(x=0, y=5),
        ]
        sig = compute_signature(EntityType.LWPOLYLINE, pts)
        assert sig.entity_type == "LWPOLYLINE"
        assert sig.vertex_count == 4
        assert sig.perimeter == 25.0  # 10+5+10 (open polyline, 3 segments)

    def test_triangle(self):
        pts = [
            Point2D(x=0, y=0), Point2D(x=10, y=0), Point2D(x=5, y=5),
        ]
        sig = compute_signature(EntityType.LWPOLYLINE, pts)
        assert sig.vertex_count == 3
        assert sig.perimeter > 0

    def test_different_vertex_count_differs(self):
        """Different vertex counts produce different signatures."""
        pts_3 = [Point2D(x=0, y=0), Point2D(x=10, y=0), Point2D(x=10, y=10)]
        pts_4 = [
            Point2D(x=0, y=0), Point2D(x=10, y=0),
            Point2D(x=10, y=10), Point2D(x=0, y=10),
        ]
        sig_3 = compute_signature(EntityType.LWPOLYLINE, pts_3)
        sig_4 = compute_signature(EntityType.LWPOLYLINE, pts_4)
        assert sig_3.vertex_count != sig_4.vertex_count

    def test_same_perimeter_different_shape(self):
        """Shapes with same perimeter but different turns get different turn_hash."""
        # L-shape: right turn
        pts_l = [
            Point2D(x=0, y=0), Point2D(x=10, y=0),
            Point2D(x=10, y=10), Point2D(x=10, y=20),
        ]
        # Z-shape: right then left turn
        pts_z = [
            Point2D(x=0, y=0), Point2D(x=10, y=0),
            Point2D(x=10, y=10), Point2D(x=20, y=10),
        ]
        sig_l = compute_signature(EntityType.LWPOLYLINE, pts_l)
        sig_z = compute_signature(EntityType.LWPOLYLINE, pts_z)
        assert sig_l.turn_hash != sig_z.turn_hash

    def test_small_noise_stable(self):
        """±0.001" noise doesn't change polyline signature."""
        pts_clean = [
            Point2D(x=0, y=0), Point2D(x=10, y=0),
            Point2D(x=10, y=10), Point2D(x=0, y=10),
        ]
        pts_noisy = [
            Point2D(x=0.001, y=-0.001), Point2D(x=9.999, y=0.001),
            Point2D(x=10.001, y=9.999), Point2D(x=-0.001, y=10.001),
        ]
        sig_clean = compute_signature(EntityType.LWPOLYLINE, pts_clean)
        sig_noisy = compute_signature(EntityType.LWPOLYLINE, pts_noisy)
        assert sig_clean.vertex_count == sig_noisy.vertex_count
        assert sig_clean.perimeter == sig_noisy.perimeter
        assert sig_clean.turn_hash == sig_noisy.turn_hash


class TestSignatureCircle:
    """CIRCLE signatures: radius + center bin."""

    def test_basic(self):
        pts = [Point2D(x=5, y=5)]
        sig = compute_signature(EntityType.CIRCLE, pts, attributes={"radius": 2.5})
        assert sig.entity_type == "CIRCLE"
        assert sig.radius == 2.5

    def test_different_radius(self):
        pts = [Point2D(x=5, y=5)]
        sig_a = compute_signature(EntityType.CIRCLE, pts, attributes={"radius": 2.5})
        sig_b = compute_signature(EntityType.CIRCLE, pts, attributes={"radius": 5.0})
        assert sig_a.radius != sig_b.radius


class TestSignatureArc:
    """ARC signatures: radius + start/end angle buckets + center bin."""

    def test_basic(self):
        pts = [Point2D(x=5, y=5)]
        sig = compute_signature(
            EntityType.ARC, pts,
            attributes={"radius": 3.0, "start_angle": 0.0, "end_angle": 90.0},
        )
        assert sig.entity_type == "ARC"
        assert sig.radius == 3.0
        assert sig.start_angle_bucket == 0  # 0° / 5° = 0
        assert sig.end_angle_bucket == 18  # 90° / 5° = 18

    def test_different_angles(self):
        pts = [Point2D(x=5, y=5)]
        sig_a = compute_signature(
            EntityType.ARC, pts,
            attributes={"radius": 3.0, "start_angle": 0.0, "end_angle": 90.0},
        )
        sig_b = compute_signature(
            EntityType.ARC, pts,
            attributes={"radius": 3.0, "start_angle": 0.0, "end_angle": 180.0},
        )
        assert sig_a.end_angle_bucket != sig_b.end_angle_bucket


class TestSignatureInsert:
    """INSERT signatures: block name + attrib keys + position bin."""

    def test_basic(self):
        pts = [Point2D(x=10, y=20)]
        sig = compute_signature(EntityType.INSERT, pts, block_name="COLUMN_MARK")
        assert sig.entity_type == "INSERT"
        assert sig.block_name == "COLUMN_MARK"

    def test_different_block_names(self):
        pts = [Point2D(x=10, y=20)]
        sig_a = compute_signature(EntityType.INSERT, pts, block_name="COLUMN_MARK")
        sig_b = compute_signature(EntityType.INSERT, pts, block_name="BEAM_TAG")
        assert sig_a.block_name != sig_b.block_name

    def test_attrib_keys_captured(self):
        pts = [Point2D(x=10, y=20)]
        sig = compute_signature(
            EntityType.INSERT, pts, block_name="TAG",
            attributes={"mark": "A1", "size": "W12x26"},
        )
        assert sig.attrib_keys == ("mark", "size")


class TestSignatureText:
    """TEXT/MTEXT signatures: text content + position bin."""

    def test_basic(self):
        pts = [Point2D(x=5, y=10)]
        sig = compute_signature(EntityType.TEXT, pts, text_content="NOTES:")
        assert sig.entity_type == "TEXT"
        assert sig.text_content == "NOTES:"

    def test_different_content(self):
        pts = [Point2D(x=5, y=10)]
        sig_a = compute_signature(EntityType.TEXT, pts, text_content="A")
        sig_b = compute_signature(EntityType.TEXT, pts, text_content="B")
        assert sig_a.text_content != sig_b.text_content

    def test_mtext(self):
        pts = [Point2D(x=5, y=10)]
        sig = compute_signature(EntityType.MTEXT, pts, text_content="Long note")
        assert sig.entity_type == "MTEXT"
        assert sig.text_content == "Long note"


class TestSignatureFrozen:
    """GeometrySignature is immutable."""

    def test_frozen(self):
        sig = compute_signature(EntityType.LINE, [Point2D(x=0, y=0), Point2D(x=10, y=0)])
        with pytest.raises(AttributeError):
            sig.length = 99.0  # type: ignore[misc]


class TestSignatureIdempotent:
    """Computing signature twice gives same result."""

    def test_line_idempotent(self):
        pts = [Point2D(x=1.23456, y=7.89012), Point2D(x=11.23456, y=7.89012)]
        sig_a = compute_signature(EntityType.LINE, pts)
        sig_b = compute_signature(EntityType.LINE, pts)
        assert sig_a == sig_b

    def test_polyline_idempotent(self):
        pts = [
            Point2D(x=0, y=0), Point2D(x=10.5, y=0),
            Point2D(x=10.5, y=8.3), Point2D(x=0, y=8.3),
        ]
        sig_a = compute_signature(EntityType.LWPOLYLINE, pts)
        sig_b = compute_signature(EntityType.LWPOLYLINE, pts)
        assert sig_a == sig_b

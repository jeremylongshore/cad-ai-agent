"""Tests for core/comparison/canonical.py — quantization and normalization primitives."""

from __future__ import annotations

import pytest

from cad_dxf_agent.core.comparison.canonical import (
    DEFAULT_QUANTIZATION,
    GeometrySignature,
    QuantizationConfig,
    assign_stable_ids,
    canonical_points,
    compute_signature,
    compute_stable_id,
    quantize_point,
    quantize_points,
    quantize_value,
    remove_near_duplicate_vertices,
    spatial_bin,
)
from cad_dxf_agent.models.cad_schema import EntityType, Point2D
from cad_dxf_agent.models.comparison_schema import GeometrySnapshot


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


# ============================================================
# Stable ID tests
# ============================================================


def _make_snap(
    entity_type: EntityType = EntityType.LINE,
    layer: str = "0",
    points: list[Point2D] | None = None,
    handle: str = "FF",
    **kwargs: object,
) -> GeometrySnapshot:
    """Helper to build a GeometrySnapshot for testing."""
    return GeometrySnapshot(
        handle=handle,
        entity_type=entity_type,
        layer=layer,
        points=points or [Point2D(x=0, y=0), Point2D(x=10, y=0)],
        **kwargs,  # type: ignore[arg-type]
    )


class TestComputeStableId:
    """compute_stable_id produces deterministic base IDs."""

    def test_deterministic(self):
        snap = _make_snap()
        id_a = compute_stable_id(snap)
        id_b = compute_stable_id(snap)
        assert id_a == id_b

    def test_format(self):
        snap = _make_snap(layer="STRUCTURAL")
        sid = compute_stable_id(snap)
        assert sid.startswith("LINE:STRUCTURAL:")
        # 12 hex chars after the prefix
        hex_part = sid.split(":")[-1]
        assert len(hex_part) == 12

    def test_different_geometry_different_id(self):
        snap_a = _make_snap(points=[Point2D(x=0, y=0), Point2D(x=10, y=0)])
        snap_b = _make_snap(points=[Point2D(x=0, y=0), Point2D(x=20, y=0)])
        assert compute_stable_id(snap_a) != compute_stable_id(snap_b)

    def test_different_layer_different_id(self):
        snap_a = _make_snap(layer="A")
        snap_b = _make_snap(layer="B")
        assert compute_stable_id(snap_a) != compute_stable_id(snap_b)

    def test_different_type_different_id(self):
        pts = [Point2D(x=5, y=5)]
        snap_a = _make_snap(entity_type=EntityType.TEXT, points=pts, text_content="X")
        snap_b = _make_snap(entity_type=EntityType.MTEXT, points=pts, text_content="X")
        assert compute_stable_id(snap_a) != compute_stable_id(snap_b)

    def test_handle_irrelevant(self):
        """Different DXF handles produce same stable ID."""
        snap_a = _make_snap(handle="1A")
        snap_b = _make_snap(handle="2B")
        assert compute_stable_id(snap_a) == compute_stable_id(snap_b)

    def test_small_noise_stable(self):
        """±0.001" noise doesn't change stable ID."""
        snap_clean = _make_snap(points=[Point2D(x=0, y=0), Point2D(x=10, y=0)])
        snap_noisy = _make_snap(points=[Point2D(x=0.001, y=-0.001), Point2D(x=9.999, y=0.001)])
        assert compute_stable_id(snap_clean) == compute_stable_id(snap_noisy)


class TestAssignStableIds:
    """assign_stable_ids handles collisions and ordering."""

    def test_unique_entities_no_suffix(self):
        snaps = [
            _make_snap(points=[Point2D(x=0, y=0), Point2D(x=10, y=0)]),
            _make_snap(points=[Point2D(x=0, y=0), Point2D(x=0, y=10)]),
        ]
        result = assign_stable_ids(snaps)
        assert all(s.stable_id is not None for s in result)
        assert result[0].stable_id != result[1].stable_id
        # No suffix needed
        assert "#" not in result[0].stable_id  # type: ignore[operator]
        assert "#" not in result[1].stable_id  # type: ignore[operator]

    def test_identical_entities_get_suffixes(self):
        """10 identical LINEs on same layer → 10 unique IDs with #0..#9."""
        snaps = [
            _make_snap(
                points=[Point2D(x=0, y=0), Point2D(x=10, y=0)],
                handle=str(i),
            )
            for i in range(10)
        ]
        result = assign_stable_ids(snaps)
        ids = [s.stable_id for s in result]
        # All unique
        assert len(set(ids)) == 10
        # All have suffixes
        assert all("#" in sid for sid in ids)  # type: ignore[operator]
        # Suffixes are 0-9
        suffixes = sorted(int(sid.split("#")[1]) for sid in ids)  # type: ignore[union-attr]
        assert suffixes == list(range(10))

    def test_collision_sorted_by_centroid(self):
        """Collision suffixes assigned by centroid (x, y) ordering."""
        # Three identical LINEs (same geometry) — only differ by handle
        # All have same signature+midpoint_bin → collision → suffix by centroid
        pts = [Point2D(x=0, y=0), Point2D(x=10, y=0)]
        snaps = [
            _make_snap(points=pts, handle="C"),
            _make_snap(points=pts, handle="A"),
            _make_snap(points=pts, handle="B"),
        ]
        result = assign_stable_ids(snaps)
        # All same centroid → suffix order is #0, #1, #2 (stable because identical centroids)
        ids = [s.stable_id for s in result]
        assert all("#" in sid for sid in ids)  # type: ignore[operator]
        # All unique
        assert len(set(ids)) == 3

    def test_preserves_original_order(self):
        """Result list is in same order as input."""
        snaps = [
            _make_snap(points=[Point2D(x=50, y=0), Point2D(x=60, y=0)], handle="A"),
            _make_snap(points=[Point2D(x=0, y=0), Point2D(x=10, y=0)], handle="B"),
        ]
        result = assign_stable_ids(snaps)
        assert result[0].handle == "A"
        assert result[1].handle == "B"

    def test_idempotent(self):
        """Assigning IDs twice produces same IDs."""
        snaps = [
            _make_snap(points=[Point2D(x=0, y=0), Point2D(x=10, y=0)]),
            _make_snap(points=[Point2D(x=0, y=0), Point2D(x=0, y=10)]),
        ]
        result_a = assign_stable_ids(snaps)
        result_b = assign_stable_ids(snaps)
        for a, b in zip(result_a, result_b, strict=True):
            assert a.stable_id == b.stable_id

    def test_empty_list(self):
        assert assign_stable_ids([]) == []

    def test_single_entity(self):
        snaps = [_make_snap()]
        result = assign_stable_ids(snaps)
        assert len(result) == 1
        assert result[0].stable_id is not None
        assert "#" not in result[0].stable_id  # type: ignore[operator]

    def test_mixed_types_no_collision(self):
        """Different entity types at same position don't collide."""
        pts = [Point2D(x=5, y=5)]
        snaps = [
            _make_snap(entity_type=EntityType.TEXT, points=pts, text_content="X"),
            _make_snap(entity_type=EntityType.CIRCLE, points=pts, attributes={"radius": 2.0}),
        ]
        result = assign_stable_ids(snaps)
        assert result[0].stable_id != result[1].stable_id
        assert "#" not in result[0].stable_id  # type: ignore[operator]
        assert "#" not in result[1].stable_id  # type: ignore[operator]

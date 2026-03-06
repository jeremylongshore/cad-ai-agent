"""Tests for markup ingestion and coordinate mapping (EPIC-CAD-03.2)."""

import pytest

from cad_dxf_agent.core.markup_parser import (
    AffineTransform,
    MarkupParser,
)
from cad_dxf_agent.models.cad_schema import Point2D
from cad_dxf_agent.models.region_schema import (
    CoordinateSpace,
    MarkupOverlay,
    MarkupType,
    RegionType,
)

# --- AffineTransform ---


class TestAffineTransform:
    def test_identity(self):
        t = AffineTransform.identity()
        p = t.apply(Point2D(x=5, y=10))
        assert p.x == 5.0
        assert p.y == 10.0

    def test_scale_and_offset(self):
        t = AffineTransform(scale_x=2.0, scale_y=3.0, offset_x=10, offset_y=20)
        p = t.apply(Point2D(x=5, y=10))
        assert p.x == 20.0  # 5*2 + 10
        assert p.y == 50.0  # 10*3 + 20

    def test_from_image_bounds(self):
        t = AffineTransform.from_image_bounds(
            image_width=1000,
            image_height=500,
            drawing_min_x=0,
            drawing_min_y=0,
            drawing_max_x=100,
            drawing_max_y=50,
        )
        # (0,0) in image → (0,0) in drawing
        p0 = t.apply(Point2D(x=0, y=0))
        assert p0.x == pytest.approx(0.0)
        assert p0.y == pytest.approx(0.0)
        # (1000,500) in image → (100,50) in drawing
        p1 = t.apply(Point2D(x=1000, y=500))
        assert p1.x == pytest.approx(100.0)
        assert p1.y == pytest.approx(50.0)

    def test_from_image_bounds_zero_image(self):
        t = AffineTransform.from_image_bounds(0, 0, 0, 0, 100, 100)
        # Should return identity
        p = t.apply(Point2D(x=5, y=5))
        assert p.x == 5.0
        assert p.y == 5.0


# --- Circle mapping ---


class TestCircleMapping:
    def test_circle_maps_correctly(self):
        parser = MarkupParser()
        overlay = MarkupOverlay(
            markup_type=MarkupType.CIRCLE,
            source_points=[
                Point2D(x=50, y=50),  # center
                Point2D(x=60, y=50),  # edge point
            ],
        )
        result = parser.map_overlay(overlay)
        assert result.confidence > 0.0
        assert result.region.source_type == RegionType.MARKUP_MAPPED
        assert result.region.coordinate_space == CoordinateSpace.DRAWING
        assert result.region.radius == pytest.approx(10.0)
        assert result.region.center.x == pytest.approx(50.0)
        assert result.region.center.y == pytest.approx(50.0)

    def test_circle_bounds(self):
        parser = MarkupParser()
        overlay = MarkupOverlay(
            markup_type=MarkupType.CIRCLE,
            source_points=[Point2D(x=100, y=100), Point2D(x=120, y=100)],
        )
        result = parser.map_overlay(overlay)
        assert result.region.bounds.min_x == pytest.approx(80.0)
        assert result.region.bounds.max_x == pytest.approx(120.0)

    def test_circle_insufficient_points(self):
        parser = MarkupParser()
        overlay = MarkupOverlay(
            markup_type=MarkupType.CIRCLE,
            source_points=[Point2D(x=50, y=50)],  # only 1 point
        )
        result = parser.map_overlay(overlay)
        assert result.confidence == 0.0
        assert "insufficient_points_for_circle" in result.ambiguity_flags

    def test_circle_zero_radius(self):
        parser = MarkupParser()
        overlay = MarkupOverlay(
            markup_type=MarkupType.CIRCLE,
            source_points=[
                Point2D(x=50, y=50),
                Point2D(x=50, y=50),  # same point
            ],
        )
        result = parser.map_overlay(overlay)
        assert result.confidence == 0.0
        assert "zero_radius_circle" in result.ambiguity_flags

    def test_circle_with_transform(self):
        # Non-uniform scale reduces confidence more than uniform
        transform = AffineTransform(scale_x=0.1, scale_y=0.05, offset_x=0, offset_y=0)
        parser = MarkupParser(transform=transform)
        overlay = MarkupOverlay(
            markup_type=MarkupType.CIRCLE,
            source_points=[Point2D(x=500, y=500), Point2D(x=600, y=500)],
        )
        result = parser.map_overlay(overlay)
        assert result.region.center.x == pytest.approx(50.0)
        assert result.region.center.y == pytest.approx(25.0)
        # Non-uniform transform reduces confidence
        assert result.confidence < 0.95


# --- Box mapping ---


class TestBoxMapping:
    def test_box_maps_correctly(self):
        parser = MarkupParser()
        overlay = MarkupOverlay(
            markup_type=MarkupType.BOX,
            source_points=[Point2D(x=10, y=20), Point2D(x=50, y=60)],
        )
        result = parser.map_overlay(overlay)
        assert result.confidence > 0.0
        assert result.region.bounds.min_x == pytest.approx(10.0)
        assert result.region.bounds.min_y == pytest.approx(20.0)
        assert result.region.bounds.max_x == pytest.approx(50.0)
        assert result.region.bounds.max_y == pytest.approx(60.0)

    def test_box_inverted_corners(self):
        """Box with corners in wrong order still normalizes."""
        parser = MarkupParser()
        overlay = MarkupOverlay(
            markup_type=MarkupType.BOX,
            source_points=[Point2D(x=50, y=60), Point2D(x=10, y=20)],
        )
        result = parser.map_overlay(overlay)
        assert result.region.bounds.min_x == pytest.approx(10.0)
        assert result.region.bounds.min_y == pytest.approx(20.0)

    def test_box_insufficient_points(self):
        parser = MarkupParser()
        overlay = MarkupOverlay(
            markup_type=MarkupType.BOX,
            source_points=[Point2D(x=10, y=20)],
        )
        result = parser.map_overlay(overlay)
        assert result.confidence == 0.0
        assert "insufficient_points_for_box" in result.ambiguity_flags

    def test_box_degenerate(self):
        parser = MarkupParser()
        overlay = MarkupOverlay(
            markup_type=MarkupType.BOX,
            source_points=[Point2D(x=10, y=20), Point2D(x=10, y=20)],
        )
        result = parser.map_overlay(overlay)
        assert result.confidence == 0.0
        assert "degenerate_box" in result.ambiguity_flags


# --- Loop mapping ---


class TestLoopMapping:
    def test_loop_maps_correctly(self):
        parser = MarkupParser()
        points = [
            Point2D(x=0, y=0),
            Point2D(x=20, y=0),
            Point2D(x=20, y=20),
            Point2D(x=0, y=20),
        ]
        overlay = MarkupOverlay(
            markup_type=MarkupType.LOOP,
            source_points=points,
        )
        result = parser.map_overlay(overlay)
        assert result.confidence > 0.0
        assert result.region.polygon is not None
        assert len(result.region.polygon) == 4
        assert result.region.bounds.min_x == pytest.approx(0.0)
        assert result.region.bounds.max_x == pytest.approx(20.0)

    def test_loop_insufficient_points(self):
        parser = MarkupParser()
        overlay = MarkupOverlay(
            markup_type=MarkupType.LOOP,
            source_points=[Point2D(x=0, y=0), Point2D(x=10, y=10)],
        )
        result = parser.map_overlay(overlay)
        assert result.confidence == 0.0
        assert "insufficient_points_for_loop" in result.ambiguity_flags

    def test_loop_degenerate(self):
        """All points at same location."""
        parser = MarkupParser()
        overlay = MarkupOverlay(
            markup_type=MarkupType.LOOP,
            source_points=[Point2D(x=5, y=5)] * 4,
        )
        result = parser.map_overlay(overlay)
        assert result.confidence == 0.0
        assert "degenerate_loop" in result.ambiguity_flags


# --- Arrow mapping (partial support) ---


class TestArrowMapping:
    def test_arrow_partial_support(self):
        parser = MarkupParser()
        overlay = MarkupOverlay(
            markup_type=MarkupType.ARROW,
            source_points=[Point2D(x=0, y=0), Point2D(x=50, y=50)],
        )
        result = parser.map_overlay(overlay)
        assert "arrow_partial_support" in result.ambiguity_flags
        # Arrow confidence capped at 0.5
        assert result.confidence <= 0.5
        # Region centered on arrow tip
        assert result.region.center.x == pytest.approx(50.0)
        assert result.region.center.y == pytest.approx(50.0)

    def test_arrow_no_points(self):
        parser = MarkupParser()
        overlay = MarkupOverlay(
            markup_type=MarkupType.ARROW,
            source_points=[],
        )
        result = parser.map_overlay(overlay)
        assert result.confidence == 0.0


# --- Highlight mapping (partial support) ---


class TestHighlightMapping:
    def test_highlight_partial_support(self):
        parser = MarkupParser()
        overlay = MarkupOverlay(
            markup_type=MarkupType.HIGHLIGHT,
            source_points=[Point2D(x=10, y=10), Point2D(x=40, y=30)],
        )
        result = parser.map_overlay(overlay)
        assert "highlight_partial_support" in result.ambiguity_flags
        # Highlight confidence capped at 0.6
        assert result.confidence <= 0.6

    def test_highlight_insufficient_points(self):
        parser = MarkupParser()
        overlay = MarkupOverlay(
            markup_type=MarkupType.HIGHLIGHT,
            source_points=[Point2D(x=10, y=10)],
        )
        result = parser.map_overlay(overlay)
        assert result.confidence == 0.0


# --- Multiple overlays ---


class TestMultipleOverlays:
    def test_map_overlays_batch(self):
        parser = MarkupParser()
        overlays = [
            MarkupOverlay(
                markup_type=MarkupType.CIRCLE,
                source_points=[Point2D(x=50, y=50), Point2D(x=60, y=50)],
            ),
            MarkupOverlay(
                markup_type=MarkupType.BOX,
                source_points=[Point2D(x=0, y=0), Point2D(x=20, y=20)],
            ),
        ]
        results = parser.map_overlays(overlays)
        assert len(results) == 2
        assert results[0].region.radius == pytest.approx(10.0)
        assert results[1].region.bounds.max_x == pytest.approx(20.0)

    def test_empty_overlays(self):
        parser = MarkupParser()
        assert parser.map_overlays([]) == []


# --- Confidence scoring ---


class TestConfidenceScoring:
    def test_identity_transform_high_confidence(self):
        parser = MarkupParser()  # identity transform
        overlay = MarkupOverlay(
            markup_type=MarkupType.BOX,
            source_points=[Point2D(x=0, y=0), Point2D(x=100, y=100)],
        )
        result = parser.map_overlay(overlay)
        assert result.confidence >= 0.9

    def test_non_identity_transform_reduces_confidence(self):
        parser = MarkupParser(transform=AffineTransform(scale_x=0.5, scale_y=0.3))
        overlay = MarkupOverlay(
            markup_type=MarkupType.BOX,
            source_points=[Point2D(x=0, y=0), Point2D(x=100, y=100)],
        )
        result = parser.map_overlay(overlay)
        assert result.confidence < 0.95

    def test_uniform_scale_better_than_nonuniform(self):
        uniform = MarkupParser(transform=AffineTransform(scale_x=2.0, scale_y=2.0))
        nonuniform = MarkupParser(transform=AffineTransform(scale_x=2.0, scale_y=0.1))
        overlay = MarkupOverlay(
            markup_type=MarkupType.BOX,
            source_points=[Point2D(x=0, y=0), Point2D(x=10, y=10)],
        )
        r_uniform = uniform.map_overlay(overlay)
        r_nonuniform = nonuniform.map_overlay(overlay)
        assert r_uniform.confidence > r_nonuniform.confidence

    def test_very_large_region_penalized(self):
        parser = MarkupParser()
        overlay = MarkupOverlay(
            markup_type=MarkupType.BOX,
            source_points=[Point2D(x=0, y=0), Point2D(x=2000, y=2000)],
        )
        result = parser.map_overlay(overlay)
        # 2000*2000 = 4M > 1M threshold
        assert result.confidence < 0.95


# --- Source markup preserved ---


class TestSourceMarkupPreserved:
    def test_source_markup_in_region(self):
        parser = MarkupParser()
        overlay = MarkupOverlay(
            markup_id="test-123",
            markup_type=MarkupType.CIRCLE,
            source_points=[Point2D(x=50, y=50), Point2D(x=60, y=50)],
            source_metadata={"page": 2, "dpi": 300},
        )
        result = parser.map_overlay(overlay)
        assert result.source_markup.markup_id == "test-123"
        assert result.region.source_markup is not None
        assert result.region.source_markup.source_metadata["page"] == 2

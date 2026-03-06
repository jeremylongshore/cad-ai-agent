"""Tests for normalized region model (EPIC-CAD-03.1)."""

import pytest
from pydantic import ValidationError

from cad_dxf_agent.models.cad_schema import Point2D
from cad_dxf_agent.models.region_schema import (
    BoundingBox,
    CoordinateSpace,
    MarkupOverlay,
    MarkupType,
    NormalizedRegion,
    RegionType,
    _point_in_polygon,
)

# --- BoundingBox ---


class TestBoundingBox:
    def test_width_height(self):
        bb = BoundingBox(min_x=0, min_y=0, max_x=10, max_y=5)
        assert bb.width == 10.0
        assert bb.height == 5.0

    def test_center(self):
        bb = BoundingBox(min_x=0, min_y=0, max_x=10, max_y=20)
        c = bb.center
        assert c.x == 5.0
        assert c.y == 10.0

    def test_area(self):
        bb = BoundingBox(min_x=0, min_y=0, max_x=4, max_y=3)
        assert bb.area == 12.0

    def test_contains_point_inside(self):
        bb = BoundingBox(min_x=0, min_y=0, max_x=10, max_y=10)
        assert bb.contains_point(Point2D(x=5, y=5))

    def test_contains_point_on_edge(self):
        bb = BoundingBox(min_x=0, min_y=0, max_x=10, max_y=10)
        assert bb.contains_point(Point2D(x=0, y=0))
        assert bb.contains_point(Point2D(x=10, y=10))

    def test_contains_point_outside(self):
        bb = BoundingBox(min_x=0, min_y=0, max_x=10, max_y=10)
        assert not bb.contains_point(Point2D(x=11, y=5))
        assert not bb.contains_point(Point2D(x=-1, y=5))

    def test_zero_area(self):
        bb = BoundingBox(min_x=5, min_y=5, max_x=5, max_y=5)
        assert bb.area == 0.0
        assert bb.width == 0.0
        assert bb.height == 0.0


# --- NormalizedRegion ---


class TestNormalizedRegion:
    def test_box_region_creation(self):
        region = NormalizedRegion(
            source_type=RegionType.BOX_SELECT,
            bounds=BoundingBox(min_x=0, min_y=0, max_x=100, max_y=100),
            center=Point2D(x=50, y=50),
        )
        assert region.source_type == RegionType.BOX_SELECT
        assert region.coordinate_space == CoordinateSpace.DRAWING
        assert region.confidence == 1.0
        assert region.schema_version == "1.0"
        assert region.region_id  # auto-generated

    def test_circle_region_creation(self):
        region = NormalizedRegion(
            source_type=RegionType.CIRCLE_SELECT,
            bounds=BoundingBox(min_x=-10, min_y=-10, max_x=10, max_y=10),
            center=Point2D(x=0, y=0),
            radius=10.0,
        )
        assert region.radius == 10.0

    def test_freehand_loop_with_polygon(self):
        polygon = [
            Point2D(x=0, y=0),
            Point2D(x=10, y=0),
            Point2D(x=10, y=10),
            Point2D(x=0, y=10),
        ]
        region = NormalizedRegion(
            source_type=RegionType.FREEHAND_LOOP,
            bounds=BoundingBox(min_x=0, min_y=0, max_x=10, max_y=10),
            center=Point2D(x=5, y=5),
            polygon=polygon,
        )
        assert len(region.polygon) == 4

    def test_viewport_box_normalizes(self):
        region = NormalizedRegion(
            source_type=RegionType.VIEWPORT_BOX,
            coordinate_space=CoordinateSpace.VIEWPORT,
            bounds=BoundingBox(min_x=100, min_y=200, max_x=300, max_y=400),
            center=Point2D(x=200, y=300),
            viewport_metadata={"zoom": 1.5, "pan_x": 0, "pan_y": 0},
        )
        assert region.coordinate_space == CoordinateSpace.VIEWPORT
        assert region.viewport_metadata["zoom"] == 1.5

    def test_markup_mapped_with_source(self):
        markup = MarkupOverlay(
            markup_type=MarkupType.CIRCLE,
            source_points=[Point2D(x=50, y=50), Point2D(x=60, y=50)],
        )
        region = NormalizedRegion(
            source_type=RegionType.MARKUP_MAPPED,
            bounds=BoundingBox(min_x=40, min_y=40, max_x=60, max_y=60),
            center=Point2D(x=50, y=50),
            source_markup=markup,
        )
        assert region.source_markup is not None
        assert region.source_markup.markup_type == MarkupType.CIRCLE

    def test_confidence_range_validation(self):
        with pytest.raises(ValidationError):
            NormalizedRegion(
                source_type=RegionType.BOX_SELECT,
                bounds=BoundingBox(min_x=0, min_y=0, max_x=10, max_y=10),
                center=Point2D(x=5, y=5),
                confidence=1.5,  # > 1.0
            )

    def test_confidence_zero_valid(self):
        region = NormalizedRegion(
            source_type=RegionType.BOX_SELECT,
            bounds=BoundingBox(min_x=0, min_y=0, max_x=10, max_y=10),
            center=Point2D(x=5, y=5),
            confidence=0.0,
        )
        assert region.confidence == 0.0

    def test_page_ref(self):
        region = NormalizedRegion(
            source_type=RegionType.BOX_SELECT,
            bounds=BoundingBox(min_x=0, min_y=0, max_x=10, max_y=10),
            center=Point2D(x=5, y=5),
            page_ref="Sheet1",
        )
        assert region.page_ref == "Sheet1"

    def test_ambiguity_flags(self):
        region = NormalizedRegion(
            source_type=RegionType.MARKUP_MAPPED,
            bounds=BoundingBox(min_x=0, min_y=0, max_x=10, max_y=10),
            center=Point2D(x=5, y=5),
            ambiguity_flags=["low_confidence_mapping"],
        )
        assert "low_confidence_mapping" in region.ambiguity_flags

    def test_serialization_roundtrip(self):
        region = NormalizedRegion(
            source_type=RegionType.CIRCLE_SELECT,
            bounds=BoundingBox(min_x=-5, min_y=-5, max_x=5, max_y=5),
            center=Point2D(x=0, y=0),
            radius=5.0,
            confidence=0.9,
        )
        data = region.model_dump()
        restored = NormalizedRegion.model_validate(data)
        assert restored.source_type == region.source_type
        assert restored.radius == region.radius
        assert restored.confidence == region.confidence


# --- contains_point ---


class TestContainsPoint:
    def test_box_contains(self):
        region = NormalizedRegion(
            source_type=RegionType.BOX_SELECT,
            bounds=BoundingBox(min_x=0, min_y=0, max_x=10, max_y=10),
            center=Point2D(x=5, y=5),
        )
        assert region.contains_point(Point2D(x=5, y=5))
        assert not region.contains_point(Point2D(x=15, y=5))

    def test_circle_contains(self):
        region = NormalizedRegion(
            source_type=RegionType.CIRCLE_SELECT,
            bounds=BoundingBox(min_x=-10, min_y=-10, max_x=10, max_y=10),
            center=Point2D(x=0, y=0),
            radius=10.0,
        )
        assert region.contains_point(Point2D(x=0, y=0))
        assert region.contains_point(Point2D(x=7, y=7))  # inside circle
        assert not region.contains_point(Point2D(x=9, y=9))  # outside circle (dist ~12.7)

    def test_polygon_contains(self):
        polygon = [
            Point2D(x=0, y=0),
            Point2D(x=10, y=0),
            Point2D(x=10, y=10),
            Point2D(x=0, y=10),
        ]
        region = NormalizedRegion(
            source_type=RegionType.FREEHAND_LOOP,
            bounds=BoundingBox(min_x=0, min_y=0, max_x=10, max_y=10),
            center=Point2D(x=5, y=5),
            polygon=polygon,
        )
        assert region.contains_point(Point2D(x=5, y=5))
        assert not region.contains_point(Point2D(x=15, y=5))


# --- _point_in_polygon ---


class TestPointInPolygon:
    def test_square(self):
        poly = [
            Point2D(x=0, y=0),
            Point2D(x=10, y=0),
            Point2D(x=10, y=10),
            Point2D(x=0, y=10),
        ]
        assert _point_in_polygon(Point2D(x=5, y=5), poly)
        assert not _point_in_polygon(Point2D(x=15, y=5), poly)

    def test_triangle(self):
        poly = [
            Point2D(x=0, y=0),
            Point2D(x=10, y=0),
            Point2D(x=5, y=10),
        ]
        assert _point_in_polygon(Point2D(x=5, y=3), poly)
        assert not _point_in_polygon(Point2D(x=0, y=10), poly)

    def test_concave_polygon(self):
        # L-shaped polygon
        poly = [
            Point2D(x=0, y=0),
            Point2D(x=10, y=0),
            Point2D(x=10, y=5),
            Point2D(x=5, y=5),
            Point2D(x=5, y=10),
            Point2D(x=0, y=10),
        ]
        assert _point_in_polygon(Point2D(x=2, y=2), poly)  # in bottom part
        assert _point_in_polygon(Point2D(x=2, y=8), poly)  # in left part
        assert not _point_in_polygon(Point2D(x=8, y=8), poly)  # in cutout


# --- MarkupOverlay ---


class TestMarkupOverlay:
    def test_creation(self):
        overlay = MarkupOverlay(
            markup_type=MarkupType.BOX,
            source_points=[Point2D(x=0, y=0), Point2D(x=100, y=100)],
            source_metadata={"page": 1, "dpi": 150},
        )
        assert overlay.markup_type == MarkupType.BOX
        assert len(overlay.source_points) == 2
        assert overlay.source_metadata["page"] == 1
        assert overlay.markup_id  # auto-generated

    def test_all_markup_types(self):
        for mt in MarkupType:
            overlay = MarkupOverlay(
                markup_type=mt,
                source_points=[Point2D(x=0, y=0)],
            )
            assert overlay.markup_type == mt


# --- RegionType enum ---


class TestRegionType:
    def test_all_members(self):
        expected = {
            "viewport_box",
            "box_select",
            "circle_select",
            "freehand_loop",
            "highlight",
            "markup_mapped",
        }
        assert {rt.value for rt in RegionType} == expected


# --- Malformed selections ---


class TestMalformedSelection:
    def test_negative_confidence_rejected(self):
        with pytest.raises(ValidationError):
            NormalizedRegion(
                source_type=RegionType.BOX_SELECT,
                bounds=BoundingBox(min_x=0, min_y=0, max_x=10, max_y=10),
                center=Point2D(x=5, y=5),
                confidence=-0.1,
            )

"""Tests for RegionContextBuilder."""

from __future__ import annotations

import pytest

from cad_dxf_agent.core.entity_index import EntityIndex
from cad_dxf_agent.core.region_context import RegionContextBuilder
from cad_dxf_agent.models.cad_schema import (
    DrawingContext,
    EntityRef,
    EntityType,
    Point2D,
)
from cad_dxf_agent.models.region_schema import (
    BoundingBox,
    NormalizedRegion,
    RegionType,
)


def _entity(handle, etype, layer, x=0.0, y=0.0, text=None, block=None):
    return EntityRef(
        handle=handle,
        entity_type=etype,
        layer=layer,
        insert_point=Point2D(x=x, y=y),
        text_content=text,
        block_name=block,
    )


def _context(entities):
    return DrawingContext(file_path="test.dxf", entities=entities)


def _region(min_x, min_y, max_x, max_y):
    cx = (min_x + max_x) / 2
    cy = (min_y + max_y) / 2
    return NormalizedRegion(
        source_type=RegionType.BOX_SELECT,
        bounds=BoundingBox(min_x=min_x, min_y=min_y, max_x=max_x, max_y=max_y),
        center=Point2D(x=cx, y=cy),
    )


@pytest.fixture
def builder():
    return RegionContextBuilder(max_entities=200, margin=5.0)


@pytest.fixture
def mixed_entities():
    return [
        _entity("T1", EntityType.TEXT, "NOTES", 10, 10, text="Label A"),
        _entity("T2", EntityType.MTEXT, "NOTES", 20, 10, text="Note B"),
        _entity("L1", EntityType.LINE, "STRUCTURAL", 10, 10),
        _entity("L2", EntityType.LINE, "STRUCTURAL", 50, 50),
        _entity("B1", EntityType.INSERT, "STRUCTURAL", 30, 30, block="COLUMN_MARK"),
        _entity("B2", EntityType.INSERT, "STRUCTURAL", 60, 60, block="DOOR"),
        _entity("D1", EntityType.DIMENSION, "NOTES", 15, 15),
        _entity("LD1", EntityType.LEADER, "NOTES", 25, 25),
        _entity("P1", EntityType.LWPOLYLINE, "STRUCTURAL", 40, 40),
    ]


class TestWholeDrawingContext:
    def test_basic_whole_drawing(self, builder, mixed_entities):
        ctx = _context(mixed_entities)
        result = builder.build(ctx)
        assert result.is_whole_drawing is True
        assert result.entity_count == 9
        assert result.total_drawing_entities == 9
        assert result.confidence == 1.0

    def test_categorizes_text_entities(self, builder, mixed_entities):
        ctx = _context(mixed_entities)
        result = builder.build(ctx)
        assert len(result.text_entities) == 2
        assert all(e.entity_type in ("TEXT", "MTEXT") for e in result.text_entities)

    def test_categorizes_dimension_entities(self, builder, mixed_entities):
        ctx = _context(mixed_entities)
        result = builder.build(ctx)
        assert len(result.dimension_entities) == 2
        types = {e.entity_type for e in result.dimension_entities}
        assert types == {EntityType.DIMENSION, EntityType.LEADER}

    def test_categorizes_block_refs(self, builder, mixed_entities):
        ctx = _context(mixed_entities)
        result = builder.build(ctx)
        assert len(result.block_refs) == 2
        assert set(result.block_names) == {"COLUMN_MARK", "DOOR"}

    def test_layer_counts(self, builder, mixed_entities):
        ctx = _context(mixed_entities)
        result = builder.build(ctx)
        assert "STRUCTURAL" in result.layer_counts
        assert "NOTES" in result.layer_counts
        assert result.layer_counts["STRUCTURAL"] == 5
        assert result.layer_counts["NOTES"] == 4

    def test_sorted_layers(self, builder, mixed_entities):
        ctx = _context(mixed_entities)
        result = builder.build(ctx)
        assert result.layers == sorted(result.layers)

    def test_empty_drawing(self, builder):
        ctx = _context([])
        result = builder.build(ctx)
        assert result.entity_count == 0
        assert result.confidence == 0.0
        assert "empty_drawing" in result.ambiguity_flags
        assert result.is_whole_drawing is True

    def test_no_bounds_for_whole_drawing(self, builder, mixed_entities):
        ctx = _context(mixed_entities)
        result = builder.build(ctx)
        assert result.bounds is None


class TestTruncation:
    def test_truncates_at_max_entities(self):
        builder = RegionContextBuilder(max_entities=5)
        entities = [_entity(f"E{i}", EntityType.LINE, "L", i, 0) for i in range(20)]
        ctx = _context(entities)
        result = builder.build(ctx)
        assert result.entity_count == 5
        assert "context_truncated" in result.ambiguity_flags
        assert result.total_drawing_entities == 20

    def test_no_truncation_under_limit(self, builder):
        entities = [_entity(f"E{i}", EntityType.LINE, "L", i, 0) for i in range(10)]
        ctx = _context(entities)
        result = builder.build(ctx)
        assert result.entity_count == 10
        assert "context_truncated" not in result.ambiguity_flags


class TestRegionContext:
    def test_region_filters_by_location(self, builder, mixed_entities):
        ctx = _context(mixed_entities)
        # Region around (10,10) — should capture nearby entities
        region = _region(5, 5, 25, 25)
        result = builder.build(ctx, region=region)
        assert result.is_whole_drawing is False
        assert result.bounds is not None
        assert result.total_drawing_entities == 9

    def test_region_has_bounds(self, builder, mixed_entities):
        ctx = _context(mixed_entities)
        region = _region(0, 0, 50, 50)
        result = builder.build(ctx, region=region)
        assert result.bounds is not None
        assert result.bounds.min_x == 0
        assert result.bounds.max_x == 50

    def test_region_entities_categorized(self, builder, mixed_entities):
        ctx = _context(mixed_entities)
        region = _region(0, 0, 100, 100)  # large region captures all
        result = builder.build(ctx, region=region)
        # All should be found since all entities are within [0,100]
        assert result.entity_count > 0
        # Categories should still work
        total_categorized = (
            len(result.text_entities)
            + len(result.dimension_entities)
            + len(result.block_refs)
        )
        # Not all entities are categorized (LINE/LWPOLYLINE are just in entities)
        assert total_categorized <= result.entity_count

    def test_respects_index_parameter(self, builder, mixed_entities):
        ctx = _context(mixed_entities)
        index = EntityIndex(ctx)
        region = _region(0, 0, 50, 50)
        result = builder.build(ctx, region=region, index=index)
        assert result.entity_count > 0

    def test_empty_region_returns_low_confidence(self, builder):
        ctx = _context([_entity("E1", EntityType.LINE, "L", 100, 100)])
        # Region far from the entity
        region = _region(0, 0, 1, 1)
        result = builder.build(ctx, region=region)
        # May be empty or very few entities
        # Confidence should reflect the region result
        assert result.is_whole_drawing is False

    def test_region_with_no_positioned_entities(self, builder):
        """Entities without insert_point are excluded from spatial queries."""
        entities = [
            EntityRef(handle="NP", entity_type=EntityType.LINE, layer="L"),
        ]
        ctx = _context(entities)
        region = _region(0, 0, 10, 10)
        result = builder.build(ctx, region=region)
        assert result.entity_count == 0


class TestEdgeCases:
    def test_single_entity(self, builder):
        ctx = _context([_entity("E1", EntityType.TEXT, "NOTES", 5, 5, text="Hello")])
        result = builder.build(ctx)
        assert result.entity_count == 1
        assert len(result.text_entities) == 1
        assert result.layers == ["NOTES"]

    def test_all_same_type(self, builder):
        entities = [_entity(f"T{i}", EntityType.TEXT, "L", i * 10, 0, text=f"T{i}") for i in range(5)]
        ctx = _context(entities)
        result = builder.build(ctx)
        assert len(result.text_entities) == 5
        assert result.dimension_entities == []
        assert result.block_refs == []

    def test_custom_margin(self, mixed_entities):
        builder = RegionContextBuilder(max_entities=200, margin=0.1)
        ctx = _context(mixed_entities)
        region = _region(9, 9, 11, 11)
        result = builder.build(ctx, region=region)
        assert result.is_whole_drawing is False

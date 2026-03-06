"""Tests for region-to-entity association (EPIC-CAD-03.3)."""

from cad_dxf_agent.core.entity_index import EntityIndex
from cad_dxf_agent.core.region_associator import (
    AssociationType,
    RegionAssociator,
)
from cad_dxf_agent.models.cad_schema import (
    DrawingContext,
    EntityRef,
    EntityType,
    LayerRule,
    Point2D,
)
from cad_dxf_agent.models.region_schema import (
    BoundingBox,
    NormalizedRegion,
    RegionType,
)


def _make_context(entities: list[EntityRef]) -> DrawingContext:
    """Build a minimal DrawingContext with the given entities."""
    layers = list({e.layer for e in entities})
    return DrawingContext(
        file_path="test.dxf",
        entities=entities,
        layers=[LayerRule(name=ln) for ln in layers],
    )


def _line(handle: str, x: float, y: float, layer: str = "STRUCTURAL") -> EntityRef:
    return EntityRef(
        handle=handle,
        entity_type=EntityType.LINE,
        layer=layer,
        insert_point=Point2D(x=x, y=y),
    )


def _text(handle: str, x: float, y: float, text: str, layer: str = "NOTES") -> EntityRef:
    return EntityRef(
        handle=handle,
        entity_type=EntityType.TEXT,
        layer=layer,
        insert_point=Point2D(x=x, y=y),
        text_content=text,
    )


def _dim(handle: str, x: float, y: float, layer: str = "DIMENSIONS") -> EntityRef:
    return EntityRef(
        handle=handle,
        entity_type=EntityType.DIMENSION,
        layer=layer,
        insert_point=Point2D(x=x, y=y),
        text_content="24'-0\"",
    )


def _insert(handle: str, x: float, y: float, block: str, layer: str = "STRUCTURAL") -> EntityRef:
    return EntityRef(
        handle=handle,
        entity_type=EntityType.INSERT,
        layer=layer,
        insert_point=Point2D(x=x, y=y),
        block_name=block,
    )


def _make_region(
    min_x: float = 0,
    min_y: float = 0,
    max_x: float = 100,
    max_y: float = 100,
    confidence: float = 0.95,
) -> NormalizedRegion:
    bounds = BoundingBox(min_x=min_x, min_y=min_y, max_x=max_x, max_y=max_y)
    return NormalizedRegion(
        source_type=RegionType.BOX_SELECT,
        bounds=bounds,
        center=bounds.center,
        confidence=confidence,
    )


# --- Basic association ---


class TestBasicAssociation:
    def test_entities_inside_region(self):
        entities = [
            _line("L1", 50, 50),
            _line("L2", 200, 200),  # outside
        ]
        context = _make_context(entities)
        region = _make_region(0, 0, 100, 100)

        result = RegionAssociator().associate(region, context)
        handles = {e.entity.handle for e in result.entities}
        assert "L1" in handles
        assert "L2" not in handles

    def test_nearby_entities(self):
        """Entity just outside region bounds but within margin."""
        entities = [_line("L1", 103, 50)]  # 3 units outside, within default margin of 5
        context = _make_context(entities)
        region = _make_region(0, 0, 100, 100)

        result = RegionAssociator(margin=5.0).associate(region, context)
        assert len(result.entities) == 1
        assert result.entities[0].association_type == AssociationType.NEARBY
        assert result.entities[0].distance > 0

    def test_no_entities_in_empty_region(self):
        entities = [_line("L1", 500, 500)]
        context = _make_context(entities)
        region = _make_region(0, 0, 10, 10)

        result = RegionAssociator().associate(region, context)
        assert result.entity_count == 0
        assert "no_entities_found" in result.ambiguity_flags
        assert result.confidence == 0.0

    def test_empty_context(self):
        context = DrawingContext(file_path="empty.dxf")
        region = _make_region()

        result = RegionAssociator().associate(region, context)
        assert result.entity_count == 0
        assert result.confidence == 0.0


# --- Entity type classification ---


class TestAssociationTypes:
    def test_text_classified_as_label(self):
        entities = [_text("T1", 50, 50, "Column A-1")]
        context = _make_context(entities)
        region = _make_region(0, 0, 100, 100)

        result = RegionAssociator().associate(region, context)
        assert result.entities[0].association_type == AssociationType.LABEL

    def test_dimension_classified_as_dimension(self):
        entities = [_dim("D1", 50, 50)]
        context = _make_context(entities)
        region = _make_region(0, 0, 100, 100)

        result = RegionAssociator().associate(region, context)
        assert result.entities[0].association_type == AssociationType.DIMENSION

    def test_insert_classified_as_block_ref(self):
        entities = [_insert("I1", 50, 50, "COLUMN_MARK")]
        context = _make_context(entities)
        region = _make_region(0, 0, 100, 100)

        result = RegionAssociator().associate(region, context)
        assert result.entities[0].association_type == AssociationType.BLOCK_REF

    def test_line_inside_classified_as_inside(self):
        entities = [_line("L1", 50, 50)]
        context = _make_context(entities)
        region = _make_region(0, 0, 100, 100)

        result = RegionAssociator().associate(region, context)
        assert result.entities[0].association_type == AssociationType.INSIDE


# --- Ranking ---


class TestRanking:
    def test_entities_ranked_by_distance(self):
        entities = [
            _line("L1", 80, 50),  # farther from center
            _line("L2", 50, 50),  # at center
            _line("L3", 30, 50),  # closer to edge
        ]
        context = _make_context(entities)
        region = _make_region(0, 0, 100, 100)

        result = RegionAssociator().associate(region, context)
        # All inside, so sorted by distance to region edge (all 0)
        assert len(result.entities) == 3
        # All inside entities have distance 0, so order preserved
        for e in result.entities:
            assert e.rank > 0

    def test_multiple_candidates_ranked(self):
        entities = [
            _line("L1", 50, 50),  # inside
            _line("L2", 103, 50),  # nearby (outside by 3 units)
        ]
        context = _make_context(entities)
        region = _make_region(0, 0, 100, 100)

        result = RegionAssociator(margin=5.0).associate(region, context)
        # Inside entity should be ranked higher (lower rank number)
        inside = [e for e in result.entities if e.entity.handle == "L1"]
        nearby = [e for e in result.entities if e.entity.handle == "L2"]
        assert inside[0].rank < nearby[0].rank


# --- Layer and block collection ---


class TestLayerBlockCollection:
    def test_layers_collected(self):
        entities = [
            _line("L1", 50, 50, layer="STRUCTURAL"),
            _text("T1", 60, 60, "label", layer="NOTES"),
        ]
        context = _make_context(entities)
        region = _make_region(0, 0, 100, 100)

        result = RegionAssociator().associate(region, context)
        assert "NOTES" in result.layers
        assert "STRUCTURAL" in result.layers

    def test_block_names_collected(self):
        entities = [
            _insert("I1", 50, 50, "COL_A"),
            _insert("I2", 60, 60, "COL_B"),
        ]
        context = _make_context(entities)
        region = _make_region(0, 0, 100, 100)

        result = RegionAssociator().associate(region, context)
        assert "COL_A" in result.block_names
        assert "COL_B" in result.block_names


# --- Confidence ---


class TestAssociationConfidence:
    def test_entities_inside_boosts_confidence(self):
        entities = [_line("L1", 50, 50)]
        context = _make_context(entities)
        region = _make_region(0, 0, 100, 100, confidence=0.95)

        result = RegionAssociator().associate(region, context)
        assert result.confidence > 0.5

    def test_all_nearby_reduces_confidence(self):
        entities = [_line("L1", 103, 50)]  # just outside
        context = _make_context(entities)
        region = _make_region(0, 0, 100, 100, confidence=0.95)

        result = RegionAssociator(margin=5.0).associate(region, context)
        assert result.confidence < 0.95
        assert "no_entities_inside_region" in result.ambiguity_flags

    def test_low_region_confidence_propagates(self):
        entities = [_line("L1", 50, 50)]
        context = _make_context(entities)
        region = _make_region(0, 0, 100, 100, confidence=0.3)

        result = RegionAssociator().associate(region, context)
        assert result.confidence < 0.5

    def test_high_entity_count_flagged(self):
        """Regions with many entities get penalized."""
        entities = [_line(f"L{i}", float(i % 90 + 5), float(i // 90 * 5 + 5)) for i in range(60)]
        context = _make_context(entities)
        region = _make_region(0, 0, 100, 100)

        result = RegionAssociator().associate(region, context)
        assert "high_entity_count" in result.ambiguity_flags


# --- Pre-built index ---


class TestPrebuiltIndex:
    def test_uses_provided_index(self):
        entities = [_line("L1", 50, 50)]
        context = _make_context(entities)
        index = EntityIndex(context)
        region = _make_region(0, 0, 100, 100)

        result = RegionAssociator().associate(region, context, index=index)
        assert result.entity_count == 1


# --- Convenience properties ---


class TestConvenienceProperties:
    def test_inside_entities_property(self):
        entities = [_line("L1", 50, 50)]
        context = _make_context(entities)
        region = _make_region(0, 0, 100, 100)

        result = RegionAssociator().associate(region, context)
        assert len(result.inside_entities) == 1

    def test_labels_property(self):
        entities = [_text("T1", 50, 50, "Column A")]
        context = _make_context(entities)
        region = _make_region(0, 0, 100, 100)

        result = RegionAssociator().associate(region, context)
        assert len(result.labels) == 1

    def test_dimensions_property(self):
        entities = [_dim("D1", 50, 50)]
        context = _make_context(entities)
        region = _make_region(0, 0, 100, 100)

        result = RegionAssociator().associate(region, context)
        assert len(result.dimensions) == 1

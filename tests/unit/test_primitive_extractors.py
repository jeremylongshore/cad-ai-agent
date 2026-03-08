"""Tests for shared primitive extractors."""

import pytest

from cad_dxf_agent.core.primitive_extractors import (
    classify_layers,
    count_entities_by_type,
    extract_labels,
    extract_primitives,
    extract_symbols,
)
from cad_dxf_agent.models.cad_schema import (
    DrawingContext,
    EntityRef,
    EntityType,
    LayerRule,
    Point2D,
)


def _entity(
    handle: str,
    etype: EntityType,
    layer: str,
    *,
    text: str | None = None,
    block: str | None = None,
) -> EntityRef:
    return EntityRef(
        handle=handle,
        entity_type=etype,
        layer=layer,
        text_content=text,
        block_name=block,
        insert_point=Point2D(x=0, y=0),
    )


@pytest.fixture
def mixed_context() -> DrawingContext:
    """Context with a mix of entity types across multiple layers."""
    return DrawingContext(
        file_path="test.dxf",
        layers=[
            LayerRule(name="STRUCTURAL"),
            LayerRule(name="NOTES"),
            LayerRule(name="DIMENSIONS"),
            LayerRule(name="TITLE"),
            LayerRule(name="E-POWER"),
        ],
        blocks=["COLUMN_MARK", "DOOR_36"],
        entities=[
            _entity("1", EntityType.LINE, "STRUCTURAL"),
            _entity("2", EntityType.LINE, "STRUCTURAL"),
            _entity("3", EntityType.LWPOLYLINE, "STRUCTURAL"),
            _entity("4", EntityType.TEXT, "NOTES", text="Column C-4"),
            _entity("5", EntityType.MTEXT, "NOTES", text="Foundation detail"),
            _entity("6", EntityType.TEXT, "TITLE", text="PROJECT TITLE"),
            _entity("7", EntityType.INSERT, "STRUCTURAL", block="COLUMN_MARK"),
            _entity("8", EntityType.INSERT, "STRUCTURAL", block="COLUMN_MARK"),
            _entity("9", EntityType.INSERT, "STRUCTURAL", block="DOOR_36"),
            _entity("A", EntityType.INSERT, "E-POWER", block="OUTLET"),
        ],
    )


class TestExtractSymbols:
    def test_counts_inserts(self, mixed_context):
        result = extract_symbols(mixed_context)
        assert result.total_inserts == 4
        assert result.unique_blocks == 3

    def test_block_counts(self, mixed_context):
        result = extract_symbols(mixed_context)
        assert result.counts_by_block["COLUMN_MARK"] == 2
        assert result.counts_by_block["DOOR_36"] == 1
        assert result.counts_by_block["OUTLET"] == 1

    def test_layer_counts(self, mixed_context):
        result = extract_symbols(mixed_context)
        assert result.counts_by_layer["STRUCTURAL"] == 3
        assert result.counts_by_layer["E-POWER"] == 1

    def test_empty_drawing(self):
        ctx = DrawingContext(file_path="empty.dxf")
        result = extract_symbols(ctx)
        assert result.total_inserts == 0
        assert result.unique_blocks == 0


class TestExtractLabels:
    def test_counts_text_entities(self, mixed_context):
        result = extract_labels(mixed_context)
        assert result.total_labels == 3  # 2 TEXT + 1 MTEXT

    def test_groups_by_layer(self, mixed_context):
        result = extract_labels(mixed_context)
        assert "NOTES" in result.by_layer
        assert len(result.by_layer["NOTES"]) == 2
        assert "TITLE" in result.by_layer

    def test_unique_count(self, mixed_context):
        result = extract_labels(mixed_context)
        assert result.unique_texts == 3

    def test_sample_texts(self, mixed_context):
        result = extract_labels(mixed_context)
        assert len(result.sample_texts) <= 20
        assert "Column C-4" in result.sample_texts

    def test_empty_drawing(self):
        ctx = DrawingContext(file_path="empty.dxf")
        result = extract_labels(ctx)
        assert result.total_labels == 0

    def test_skips_empty_text(self):
        ctx = DrawingContext(
            file_path="test.dxf",
            entities=[
                _entity("1", EntityType.TEXT, "NOTES", text=""),
                _entity("2", EntityType.TEXT, "NOTES", text="  "),
                _entity("3", EntityType.TEXT, "NOTES", text="Valid"),
            ],
        )
        result = extract_labels(ctx)
        assert result.total_labels == 1


class TestClassifyLayers:
    def test_structural_layers(self, mixed_context):
        result = classify_layers(mixed_context)
        assert "STRUCTURAL" in result.structural

    def test_dimension_layers(self, mixed_context):
        result = classify_layers(mixed_context)
        assert "DIMENSIONS" in result.dimension

    def test_title_layers(self, mixed_context):
        result = classify_layers(mixed_context)
        assert "TITLE" in result.title_border

    def test_mep_layers(self, mixed_context):
        result = classify_layers(mixed_context)
        assert "E-POWER" in result.mep

    def test_notes_as_annotation(self, mixed_context):
        result = classify_layers(mixed_context)
        assert "NOTES" in result.annotation


class TestCountEntitiesByType:
    def test_counts(self, mixed_context):
        result = count_entities_by_type(mixed_context)
        assert result["INSERT"] == 4
        assert result["LINE"] == 2
        assert result["TEXT"] == 2
        assert result["MTEXT"] == 1
        assert result["LWPOLYLINE"] == 1


class TestExtractPrimitives:
    def test_aggregates_all(self, mixed_context):
        result = extract_primitives(mixed_context)
        assert result.total_entities == 10
        assert result.symbols.total_inserts == 4
        assert result.labels.total_labels == 3
        assert len(result.entity_counts) > 0
        assert result.layer_classification.structural == ["STRUCTURAL"]

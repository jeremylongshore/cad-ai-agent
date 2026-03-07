"""Tests for TakeoffGenerator in cad_dxf_agent.core.design_ops."""

from __future__ import annotations

from cad_dxf_agent.core.design_ops import TakeoffGenerator
from cad_dxf_agent.models.cad_schema import (
    DrawingContext,
    EntityRef,
    EntityType,
    LayerRule,
    Point2D,
    TextGeometry,
    TextProvenance,
)
from cad_dxf_agent.models.design_ops_schema import TakeoffConfidence

# ---------------------------------------------------------------------------
# Test data factories
# ---------------------------------------------------------------------------


def _entity(
    handle: str,
    layer: str = "STRUCTURAL",
    entity_type: EntityType = EntityType.LINE,
    text: str | None = None,
    block_name: str | None = None,
    x: float = 0.0,
    y: float = 0.0,
    text_geometry: TextGeometry | None = None,
) -> EntityRef:
    return EntityRef(
        handle=handle,
        entity_type=entity_type,
        layer=layer,
        text_content=text,
        block_name=block_name,
        insert_point=Point2D(x=x, y=y) if (x or y) else None,
        text_geometry=text_geometry,
    )


def _context(entities: list[EntityRef], layers: list[str] | None = None) -> DrawingContext:
    layer_names = layers or sorted({e.layer for e in entities})
    return DrawingContext(
        file_path="test.dxf",
        entities=entities,
        layers=[LayerRule(name=n) for n in layer_names],
    )


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


class TestTakeoffGeneratorEmptyDrawing:
    def test_empty_drawing_returns_no_items_with_flag(self):
        ctx = _context([])
        result = TakeoffGenerator().generate(ctx, prompt="count everything")
        assert result.items == []
        assert "empty_drawing" in result.ambiguity_flags

    def test_empty_drawing_has_caveat(self):
        ctx = _context([])
        result = TakeoffGenerator().generate(ctx, prompt="count")
        assert result.caveats  # at least one caveat present


class TestTakeoffGeneratorBlockCounting:
    def test_five_column_mark_blocks_produce_single_item_qty_5(self):
        entities = [
            _entity(
                f"H{i}", layer="COLUMNS", entity_type=EntityType.INSERT, block_name="COLUMN_MARK"
            )
            for i in range(5)
        ]
        ctx = _context(entities)
        result = TakeoffGenerator().generate(ctx, prompt="count columns")
        block_items = [it for it in result.items if it.source_block_name == "COLUMN_MARK"]
        assert len(block_items) == 1
        assert block_items[0].quantity == 5

    def test_block_items_have_high_confidence(self):
        entities = [
            _entity(f"B{i}", layer="BEAMS", entity_type=EntityType.INSERT, block_name="BEAM_MARK")
            for i in range(3)
        ]
        ctx = _context(entities)
        result = TakeoffGenerator().generate(ctx, prompt="count beams")
        beam_items = [it for it in result.items if it.source_block_name == "BEAM_MARK"]
        assert beam_items[0].confidence == TakeoffConfidence.HIGH

    def test_multiple_block_types_counted_separately(self):
        entities = [
            _entity("C1", layer="COLS", entity_type=EntityType.INSERT, block_name="COL_A"),
            _entity("C2", layer="COLS", entity_type=EntityType.INSERT, block_name="COL_A"),
            _entity("D1", layer="DOORS", entity_type=EntityType.INSERT, block_name="DOOR_B"),
        ]
        ctx = _context(entities)
        result = TakeoffGenerator().generate(ctx, prompt="count all")
        block_names = {it.source_block_name for it in result.items if it.source_block_name}
        assert "COL_A" in block_names
        assert "DOOR_B" in block_names

    def test_block_without_block_name_not_counted_as_block(self):
        # INSERT entity with no block_name must be skipped in the block-counting pass
        entities = [
            _entity("N1", layer="MISC", entity_type=EntityType.INSERT, block_name=None),
            _entity("N2", layer="MISC", entity_type=EntityType.INSERT, block_name=None),
        ]
        ctx = _context(entities)
        result = TakeoffGenerator().generate(ctx, prompt="count")
        block_items = [it for it in result.items if it.source_block_name is not None]
        assert block_items == []

    def test_insert_with_no_block_name_excluded_from_block_items(self):
        # No block_name means entity_type=INSERT but no block — layer pass should also skip INSERTs
        entities = [
            _entity("Z1", layer="STRUCTURAL", entity_type=EntityType.INSERT, block_name=None),
            _entity("Z2", layer="STRUCTURAL", entity_type=EntityType.INSERT, block_name=None),
            _entity("Z3", layer="STRUCTURAL", entity_type=EntityType.LINE),
            _entity("Z4", layer="STRUCTURAL", entity_type=EntityType.LINE),
        ]
        ctx = _context(entities)
        result = TakeoffGenerator().generate(ctx, prompt="count")
        # Layer pass picks up 2 LINE entities on STRUCTURAL; nameless INSERT skipped
        layer_items = [
            it
            for it in result.items
            if it.source_layer == "STRUCTURAL" and it.source_block_name is None
        ]
        assert layer_items  # at least one layer-based item for the LINEs


class TestTakeoffGeneratorLayerCounting:
    def test_layer_based_counting_for_non_insert_entities(self):
        entities = [
            _entity("L1", layer="WALLS", entity_type=EntityType.LINE),
            _entity("L2", layer="WALLS", entity_type=EntityType.LINE),
            _entity("L3", layer="WALLS", entity_type=EntityType.LWPOLYLINE),
        ]
        ctx = _context(entities)
        result = TakeoffGenerator().generate(ctx, prompt="count walls")
        wall_items = [it for it in result.items if it.source_layer == "WALLS"]
        assert wall_items
        assert wall_items[0].quantity == 3

    def test_layer_counting_skips_layers_covered_by_blocks(self):
        # COLUMNS layer has block inserts; layer pass must not double-count it
        entities = [
            _entity("BC1", layer="COLUMNS", entity_type=EntityType.INSERT, block_name="COL"),
            _entity("BC2", layer="COLUMNS", entity_type=EntityType.INSERT, block_name="COL"),
        ]
        ctx = _context(entities)
        result = TakeoffGenerator().generate(ctx, prompt="count columns")
        # Only block item(s) should reference COLUMNS, not a separate layer item
        layer_items_for_columns = [
            it
            for it in result.items
            if it.source_layer == "COLUMNS" and it.source_block_name is None
        ]
        assert layer_items_for_columns == []

    def test_layer_with_single_entity_not_included(self):
        # Minimum count for a layer item is 2
        entities = [_entity("S1", layer="LONELY", entity_type=EntityType.LINE)]
        ctx = _context(entities)
        result = TakeoffGenerator().generate(ctx, prompt="count")
        lonely_items = [it for it in result.items if it.source_layer == "LONELY"]
        assert lonely_items == []


class TestTakeoffGeneratorTextQuantityExtraction:
    def test_text_ea_pattern_extracts_quantity(self):
        entities = [_entity("T1", layer="NOTES", entity_type=EntityType.TEXT, text="10 ea")]
        ctx = _context(entities)
        result = TakeoffGenerator().generate(ctx, prompt="count")
        text_items = [it for it in result.items if "10 ea" in it.name]
        assert text_items
        assert text_items[0].quantity == 10

    def test_text_pcs_pattern_extracts_quantity(self):
        entities = [_entity("T2", layer="NOTES", entity_type=EntityType.TEXT, text="5 pcs")]
        ctx = _context(entities)
        result = TakeoffGenerator().generate(ctx, prompt="count")
        text_items = [it for it in result.items if "5 pcs" in it.name]
        assert text_items
        assert text_items[0].quantity == 5

    def test_text_x_multiplier_pattern_extracts_quantity(self):
        entities = [_entity("T3", layer="NOTES", entity_type=EntityType.TEXT, text="3x units")]
        ctx = _context(entities)
        result = TakeoffGenerator().generate(ctx, prompt="count")
        text_items = [it for it in result.items if "3x units" in it.name]
        assert text_items
        assert text_items[0].quantity == 3

    def test_text_with_no_quantity_pattern_produces_no_item(self):
        entities = [_entity("T4", layer="NOTES", entity_type=EntityType.TEXT, text="see schedule")]
        ctx = _context(entities)
        result = TakeoffGenerator().generate(ctx, prompt="count")
        text_items = [it for it in result.items if "see schedule" in it.name]
        assert text_items == []

    def test_quantity_above_10000_ignored(self):
        entities = [_entity("T5", layer="NOTES", entity_type=EntityType.TEXT, text="99999 ea")]
        ctx = _context(entities)
        result = TakeoffGenerator().generate(ctx, prompt="count")
        text_items = [it for it in result.items if "99999" in it.name]
        assert text_items == []

    def test_quantity_zero_ignored(self):
        entities = [_entity("T6", layer="NOTES", entity_type=EntityType.TEXT, text="0 ea")]
        ctx = _context(entities)
        result = TakeoffGenerator().generate(ctx, prompt="count")
        text_items = [it for it in result.items if "0 ea" in it.name]
        assert text_items == []


class TestTakeoffGeneratorOCRProvenance:
    """SQ67 — OCR text must be downgraded to ESTIMATE_ONLY, never treated as exact truth."""

    def _ocr_geometry(self) -> TextGeometry:
        return TextGeometry.for_provenance(TextProvenance.RASTER_OCR_TEXT)

    def test_ocr_text_quantity_confidence_is_estimate_only(self):
        entities = [
            _entity(
                "OCR1",
                layer="NOTES",
                entity_type=EntityType.TEXT,
                text="10 ea",
                text_geometry=self._ocr_geometry(),
            )
        ]
        ctx = _context(entities)
        result = TakeoffGenerator().generate(ctx, prompt="count")
        text_items = [it for it in result.items if "10 ea" in it.name]
        assert text_items, "Expected a text-derived item for OCR text"
        assert text_items[0].confidence == TakeoffConfidence.ESTIMATE_ONLY

    def test_ocr_text_adds_provenance_warning(self):
        entities = [
            _entity(
                "OCR2",
                layer="NOTES",
                entity_type=EntityType.TEXT,
                text="10 ea",
                text_geometry=self._ocr_geometry(),
            )
        ]
        ctx = _context(entities)
        result = TakeoffGenerator().generate(ctx, prompt="count")
        assert result.provenance_warnings, "Expected at least one OCR provenance warning"
        assert any(
            "OCR" in w or "estimate_only" in w.lower() or "ESTIMATE_ONLY" in w
            for w in result.provenance_warnings
        )

    def test_native_cad_text_has_medium_confidence_not_estimate_only(self):
        native_geometry = TextGeometry.for_provenance(TextProvenance.NATIVE_CAD_TEXT)
        entities = [
            _entity(
                "NAT1",
                layer="NOTES",
                entity_type=EntityType.TEXT,
                text="7 ea",
                text_geometry=native_geometry,
            )
        ]
        ctx = _context(entities)
        result = TakeoffGenerator().generate(ctx, prompt="count")
        text_items = [it for it in result.items if "7 ea" in it.name]
        assert text_items
        assert text_items[0].confidence == TakeoffConfidence.MEDIUM

    def test_block_attribute_text_has_medium_confidence(self):
        attr_geometry = TextGeometry.for_provenance(TextProvenance.BLOCK_ATTRIBUTE_TEXT)
        entities = [
            _entity(
                "ATTR1",
                layer="NOTES",
                entity_type=EntityType.TEXT,
                text="4 ea",
                text_geometry=attr_geometry,
            )
        ]
        ctx = _context(entities)
        result = TakeoffGenerator().generate(ctx, prompt="count")
        text_items = [it for it in result.items if "4 ea" in it.name]
        assert text_items
        assert text_items[0].confidence == TakeoffConfidence.MEDIUM

    def test_anti_regression_ocr_cannot_become_high_or_medium(self):
        """OCR text must never yield HIGH or MEDIUM confidence — safety net."""
        entities = [
            _entity(
                "AREG1",
                layer="NOTES",
                entity_type=EntityType.TEXT,
                text="50 ea",
                text_geometry=self._ocr_geometry(),
            )
        ]
        ctx = _context(entities)
        result = TakeoffGenerator().generate(ctx, prompt="count")
        text_items = [it for it in result.items if "50 ea" in it.name]
        assert text_items
        assert text_items[0].confidence not in (TakeoffConfidence.HIGH, TakeoffConfidence.MEDIUM)

    def test_anti_regression_ocr_must_have_provenance_warning(self):
        """Every OCR quantity extraction must emit at least one provenance warning."""
        entities = [
            _entity(
                "AREG2",
                layer="NOTES",
                entity_type=EntityType.TEXT,
                text="12 ea",
                text_geometry=self._ocr_geometry(),
            )
        ]
        ctx = _context(entities)
        result = TakeoffGenerator().generate(ctx, prompt="count")
        assert result.provenance_warnings, "OCR text must always emit a provenance warning"

    def test_multiple_ocr_texts_each_emit_warning(self):
        entities = [
            _entity(
                f"MOCR{i}",
                layer="NOTES",
                entity_type=EntityType.TEXT,
                text=f"{i + 1} ea",
                text_geometry=self._ocr_geometry(),
            )
            for i in range(3)
        ]
        ctx = _context(entities)
        result = TakeoffGenerator().generate(ctx, prompt="count")
        # Three OCR entities → three warnings
        assert len(result.provenance_warnings) == 3


class TestTakeoffGeneratorAggregates:
    def test_total_items_and_total_quantity_computed(self):
        entities = [
            _entity("BLK1", layer="COLS", entity_type=EntityType.INSERT, block_name="COL"),
            _entity("BLK2", layer="COLS", entity_type=EntityType.INSERT, block_name="COL"),
            _entity("TXT1", layer="NOTES", entity_type=EntityType.TEXT, text="3 ea"),
        ]
        ctx = _context(entities)
        result = TakeoffGenerator().generate(ctx, prompt="count")
        assert result.total_items == len(result.items)
        assert result.total_quantity_items == sum(it.quantity for it in result.items)

    def test_aggregate_confidence_is_worst_of_all_items(self):
        ocr_geom = TextGeometry.for_provenance(TextProvenance.RASTER_OCR_TEXT)
        entities = [
            # HIGH confidence block item
            _entity("AG1", layer="COLS", entity_type=EntityType.INSERT, block_name="COL"),
            _entity("AG2", layer="COLS", entity_type=EntityType.INSERT, block_name="COL"),
            # ESTIMATE_ONLY due to OCR
            _entity(
                "AG3",
                layer="NOTES",
                entity_type=EntityType.TEXT,
                text="5 ea",
                text_geometry=ocr_geom,
            ),
        ]
        ctx = _context(entities)
        result = TakeoffGenerator().generate(ctx, prompt="count")
        # Mix of HIGH + ESTIMATE_ONLY → aggregate must be ESTIMATE_ONLY (worst)
        assert result.aggregate_confidence == TakeoffConfidence.ESTIMATE_ONLY

    def test_mixed_block_and_text_items_in_same_result(self):
        entities = [
            _entity("MX1", layer="COLS", entity_type=EntityType.INSERT, block_name="COL_A"),
            _entity("MX2", layer="COLS", entity_type=EntityType.INSERT, block_name="COL_A"),
            _entity("MX3", layer="NOTES", entity_type=EntityType.TEXT, text="8 ea"),
        ]
        ctx = _context(entities)
        result = TakeoffGenerator().generate(ctx, prompt="count")
        block_items = [it for it in result.items if it.source_block_name == "COL_A"]
        text_items = [it for it in result.items if "8 ea" in it.name]
        assert block_items
        assert text_items

    def test_region_subset_adds_partial_region_flag_and_caveat(self):
        from cad_dxf_agent.models.qna_schema import RegionContext

        entities = [
            _entity("R1", layer="ZONE_A", entity_type=EntityType.INSERT, block_name="BLK"),
            _entity("R2", layer="ZONE_A", entity_type=EntityType.INSERT, block_name="BLK"),
        ]
        ctx = _context(entities)

        region = RegionContext(
            entities=entities,
            is_whole_drawing=False,
            ambiguity_flags=[],
        )
        result = TakeoffGenerator().generate(ctx, prompt="count zone a", region=region)
        assert "partial_region" in result.ambiguity_flags
        assert any("region" in c.lower() for c in result.caveats)

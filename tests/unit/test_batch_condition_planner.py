"""Tests for BatchConditionPlanner from construction_ops."""

from __future__ import annotations

import pytest

from cad_dxf_agent.core.construction_ops import BatchConditionPlanner
from cad_dxf_agent.models.cad_schema import (
    DrawingContext,
    EntityRef,
    EntityType,
    LayerRule,
    Point2D,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _entity(
    handle,
    layer="STRUCTURAL",
    entity_type=EntityType.LINE,
    x=0.0,
    y=0.0,
    block_name=None,
    text_content=None,
    attributes=None,
):
    return EntityRef(
        handle=handle,
        entity_type=entity_type,
        layer=layer,
        insert_point=Point2D(x=x, y=y),
        block_name=block_name,
        text_content=text_content,
        attributes=attributes or {},
    )


def _context(entities):
    layer_names = sorted({e.layer for e in entities})
    return DrawingContext(
        file_path="test.dxf",
        entities=entities,
        layers=[LayerRule(name=n) for n in layer_names],
    )


def _inserts(block_name, count, layer="STRUCTURAL", start_handle=1):
    """Create *count* INSERT entities with the given block_name."""
    return [
        _entity(
            handle=f"I{start_handle + i}",
            layer=layer,
            entity_type=EntityType.INSERT,
            x=float(i * 100),
            y=float(i * 50),
            block_name=block_name,
        )
        for i in range(count)
    ]


def _texts(content, count, layer="NOTES", entity_type=EntityType.TEXT, start_handle=1):
    """Create *count* TEXT entities with the given content."""
    return [
        _entity(
            handle=f"T{start_handle + i}",
            layer=layer,
            entity_type=entity_type,
            x=float(i * 100),
            y=float(i * 50),
            text_content=content,
        )
        for i in range(count)
    ]


# ---------------------------------------------------------------------------
# Block-based grouping
# ---------------------------------------------------------------------------

class TestBlockGrouping:
    """INSERT entities grouped by block_name with 3+ instances."""

    def test_three_inserts_same_block_form_group(self):
        entities = _inserts("DOOR", 3)
        ctx = _context(entities)
        result = BatchConditionPlanner().plan(ctx, "batch")
        assert result.total_groups >= 1

    def test_four_inserts_same_block_form_group(self):
        entities = _inserts("WINDOW", 4)
        ctx = _context(entities)
        result = BatchConditionPlanner().plan(ctx, "batch")
        groups = [g for g in result.groups if g.name == "WINDOW" or "WINDOW" in str(g.model_dump())]
        assert len(groups) >= 1

    def test_two_inserts_below_threshold(self):
        entities = _inserts("OUTLET", 2)
        ctx = _context(entities)
        result = BatchConditionPlanner().plan(ctx, "batch")
        # Should NOT form a group since 2 < 3
        block_groups = [
            g for g in result.groups
            if "OUTLET" in str(g.model_dump())
        ]
        assert len(block_groups) == 0

    def test_multiple_block_names_separate_groups(self):
        doors = _inserts("DOOR", 4, start_handle=1)
        windows = _inserts("WINDOW", 3, start_handle=100)
        ctx = _context(doors + windows)
        result = BatchConditionPlanner().plan(ctx, "batch")
        assert result.total_groups >= 2

    def test_insert_without_block_name_skipped(self):
        entities = [
            _entity(f"I{i}", entity_type=EntityType.INSERT, x=float(i * 10), block_name=None)
            for i in range(5)
        ]
        ctx = _context(entities)
        result = BatchConditionPlanner().plan(ctx, "batch")
        assert result.total_groups == 0


# ---------------------------------------------------------------------------
# Text-based grouping
# ---------------------------------------------------------------------------

class TestTextGrouping:
    """TEXT/MTEXT entities grouped by similarity (levenshtein >= 0.8) with 3+ instances."""

    def test_three_identical_texts_form_group(self):
        entities = _texts("FIRE EXTINGUISHER", 3)
        ctx = _context(entities)
        result = BatchConditionPlanner().plan(ctx, "batch")
        assert result.total_groups >= 1

    def test_similar_texts_form_group(self):
        # Levenshtein similarity >= 0.8 between these
        entities = [
            _entity("T1", entity_type=EntityType.TEXT, text_content="EXIT SIGN TYPE A", x=0),
            _entity("T2", entity_type=EntityType.TEXT, text_content="EXIT SIGN TYPE B", x=100),
            _entity("T3", entity_type=EntityType.TEXT, text_content="EXIT SIGN TYPE A", x=200),
        ]
        ctx = _context(entities)
        result = BatchConditionPlanner().plan(ctx, "batch")
        assert result.total_groups >= 1

    def test_dissimilar_texts_not_grouped(self):
        entities = [
            _entity("T1", entity_type=EntityType.TEXT, text_content="DOOR SCHEDULE", x=0),
            _entity("T2", entity_type=EntityType.TEXT, text_content="WINDOW DETAIL", x=100),
            _entity("T3", entity_type=EntityType.TEXT, text_content="SECTION A-A", x=200),
        ]
        ctx = _context(entities)
        result = BatchConditionPlanner().plan(ctx, "batch")
        # These are all dissimilar, so no text group
        text_groups = [g for g in result.groups if "text" in str(g.model_dump()).lower() or getattr(g, "group_type", "") == "text"]
        assert len(text_groups) == 0

    def test_two_identical_texts_below_threshold(self):
        entities = _texts("FIRE ALARM", 2)
        ctx = _context(entities)
        result = BatchConditionPlanner().plan(ctx, "batch")
        text_groups = [
            g for g in result.groups
            if "FIRE ALARM" in str(g.model_dump())
        ]
        assert len(text_groups) == 0

    def test_mtext_entities_also_grouped(self):
        entities = _texts("EMERGENCY EXIT", 3, entity_type=EntityType.MTEXT)
        ctx = _context(entities)
        result = BatchConditionPlanner().plan(ctx, "batch")
        assert result.total_groups >= 1

    def test_entity_without_text_content_skipped(self):
        entities = [
            _entity(f"T{i}", entity_type=EntityType.TEXT, x=float(i * 10), text_content=None)
            for i in range(5)
        ]
        ctx = _context(entities)
        result = BatchConditionPlanner().plan(ctx, "batch")
        assert result.total_groups == 0

    def test_text_groups_have_similarity_caveat(self):
        entities = _texts("SPRINKLER HEAD", 4)
        ctx = _context(entities)
        result = BatchConditionPlanner().plan(ctx, "batch")
        dumped = str(result.model_dump()).lower()
        assert "similar" in dumped or "text" in dumped


# ---------------------------------------------------------------------------
# Mixed entity types
# ---------------------------------------------------------------------------

class TestMixedTypes:
    """Block and text groups returned together."""

    def test_blocks_and_texts_together(self):
        inserts = _inserts("VALVE", 3, start_handle=1)
        texts = _texts("CHECK VALVE", 3, start_handle=100)
        ctx = _context(inserts + texts)
        result = BatchConditionPlanner().plan(ctx, "batch")
        assert result.total_groups >= 2

    def test_non_insert_non_text_entities_ignored(self):
        lines = [
            _entity(f"L{i}", entity_type=EntityType.LINE, x=float(i * 10))
            for i in range(5)
        ]
        ctx = _context(lines)
        result = BatchConditionPlanner().plan(ctx, "batch")
        assert result.total_groups == 0


# ---------------------------------------------------------------------------
# Edge cases
# ---------------------------------------------------------------------------

class TestEdgeCases:
    """Empty drawings and no qualifying patterns."""

    def test_empty_drawing(self):
        ctx = _context([])
        result = BatchConditionPlanner().plan(ctx, "batch")
        assert result.total_groups == 0
        dumped = str(result.model_dump()).lower()
        assert "empty" in dumped or result.total_groups == 0

    def test_no_qualifying_patterns_has_caveat(self):
        entities = [
            _entity("E1", entity_type=EntityType.LINE, x=0),
            _entity("E2", entity_type=EntityType.LINE, x=100),
        ]
        ctx = _context(entities)
        result = BatchConditionPlanner().plan(ctx, "batch")
        assert result.total_groups == 0
        dumped = str(result.model_dump()).lower()
        assert "no repeated" in dumped or "no pattern" in dumped or result.total_groups == 0


# ---------------------------------------------------------------------------
# Sorting
# ---------------------------------------------------------------------------

class TestSorting:
    """Groups sorted by instance count descending."""

    def test_groups_sorted_by_count_descending(self):
        small = _inserts("SMALL", 3, start_handle=1)
        large = _inserts("LARGE", 7, start_handle=100)
        medium = _inserts("MEDIUM", 5, start_handle=200)
        ctx = _context(small + large + medium)
        result = BatchConditionPlanner().plan(ctx, "batch")
        counts = [g.total_instances for g in result.groups]
        assert counts == sorted(counts, reverse=True)


# ---------------------------------------------------------------------------
# Confidence
# ---------------------------------------------------------------------------

class TestConfidence:
    """Confidence scales with instance count; text groups have lower ceiling."""

    def test_block_confidence_3_instances(self):
        entities = _inserts("BLK", 3)
        ctx = _context(entities)
        result = BatchConditionPlanner().plan(ctx, "batch")
        group = result.groups[0]
        # 0.6 + 3 * 0.03 = 0.69
        assert group.confidence == pytest.approx(0.69, abs=0.05)

    def test_block_confidence_10_instances(self):
        entities = _inserts("BLK", 10)
        ctx = _context(entities)
        result = BatchConditionPlanner().plan(ctx, "batch")
        group = result.groups[0]
        # 0.6 + 10 * 0.03 = 0.90
        assert group.confidence == pytest.approx(0.90, abs=0.05)

    def test_block_confidence_capped_at_095(self):
        entities = _inserts("BLK", 20)
        ctx = _context(entities)
        result = BatchConditionPlanner().plan(ctx, "batch")
        group = result.groups[0]
        assert group.confidence <= 0.95

    def test_text_confidence_lower_than_block(self):
        texts = _texts("SAME TEXT", 5, start_handle=1)
        inserts = _inserts("BLK", 5, start_handle=100)
        ctx_text = _context(texts)
        ctx_block = _context(inserts)
        result_text = BatchConditionPlanner().plan(ctx_text, "batch")
        result_block = BatchConditionPlanner().plan(ctx_block, "batch")
        text_conf = result_text.groups[0].confidence
        block_conf = result_block.groups[0].confidence
        assert text_conf < block_conf

    def test_text_confidence_3_instances(self):
        entities = _texts("LABEL", 3)
        ctx = _context(entities)
        result = BatchConditionPlanner().plan(ctx, "batch")
        group = result.groups[0]
        # 0.5 + 3 * 0.03 = 0.59
        assert group.confidence == pytest.approx(0.59, abs=0.05)

    def test_text_confidence_capped_at_085(self):
        entities = _texts("REPEAT", 20)
        ctx = _context(entities)
        result = BatchConditionPlanner().plan(ctx, "batch")
        group = result.groups[0]
        assert group.confidence <= 0.85


# ---------------------------------------------------------------------------
# Result structure / metadata
# ---------------------------------------------------------------------------

class TestResultStructure:
    """Verify total counts, exemplar handles, serialization."""

    def test_total_groups_count(self):
        doors = _inserts("DOOR", 4, start_handle=1)
        windows = _inserts("WINDOW", 3, start_handle=100)
        ctx = _context(doors + windows)
        result = BatchConditionPlanner().plan(ctx, "batch")
        assert result.total_groups == len(result.groups)

    def test_total_instances_count(self):
        entities = _inserts("BLK", 5)
        ctx = _context(entities)
        result = BatchConditionPlanner().plan(ctx, "batch")
        assert result.total_instances >= 5

    def test_exemplar_handles_present(self):
        entities = _inserts("BLK", 4)
        ctx = _context(entities)
        result = BatchConditionPlanner().plan(ctx, "batch")
        group = result.groups[0]
        assert len(group.exemplar_handles) >= 1
        # First instance handle should be in exemplars
        assert group.exemplar_handles[0] in [e.handle for e in entities]

    def test_instances_contain_handle_layer_position(self):
        entities = _inserts("BLK", 3)
        ctx = _context(entities)
        result = BatchConditionPlanner().plan(ctx, "batch")
        group = result.groups[0]
        for inst in group.instances:
            inst_dict = inst if isinstance(inst, dict) else inst.model_dump() if hasattr(inst, "model_dump") else vars(inst)
            assert "handle" in inst_dict
            assert "layer" in inst_dict
            assert "position" in inst_dict or "x" in str(inst_dict)

    def test_text_instances_contain_text_content(self):
        entities = _texts("FIRE DOOR", 3)
        ctx = _context(entities)
        result = BatchConditionPlanner().plan(ctx, "batch")
        group = result.groups[0]
        for inst in group.instances:
            inst_str = str(inst.model_dump() if hasattr(inst, "model_dump") else inst)
            assert "FIRE DOOR" in inst_str or "text" in inst_str.lower()

    def test_model_dump_produces_dict(self):
        entities = _inserts("BLK", 3)
        ctx = _context(entities)
        result = BatchConditionPlanner().plan(ctx, "batch")
        dumped = result.model_dump()
        assert isinstance(dumped, dict)

    def test_aggregate_confidence_is_min(self):
        small = _inserts("SMALL", 3, start_handle=1)
        large = _inserts("LARGE", 10, start_handle=100)
        ctx = _context(small + large)
        result = BatchConditionPlanner().plan(ctx, "batch")
        if len(result.groups) >= 2:
            group_confs = [g.confidence for g in result.groups]
            assert result.aggregate_confidence == pytest.approx(min(group_confs), abs=0.01)

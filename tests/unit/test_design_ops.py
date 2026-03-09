"""Unit tests for cad_dxf_agent.core.design_ops.

Covers the public API of four deterministic analysis classes:
  - LayoutRecommender   (layout density, layer distribution, block placement, text labels)
  - RevisionSummarizer  (changeset → plain-language summary, comparison → summary)
  - TakeoffGenerator    (block counting, layer counting, text-quantity extraction)
  - ScopeBuilder        (assembles all three into a scope-style report)

Complements the more exhaustive TakeoffGenerator coverage in test_takeoff_generator.py
and the anti-regression invariants in test_design_ops_anti_regression.py.
"""

from __future__ import annotations

import pytest

from cad_dxf_agent.core.design_ops import (
    LayoutRecommender,
    RevisionSummarizer,
    ScopeBuilder,
    TakeoffGenerator,
)
from cad_dxf_agent.models.cad_schema import (
    DrawingContext,
    EntityRef,
    EntityType,
    LayerRule,
    Point2D,
    TextGeometry,
    TextProvenance,
)
from cad_dxf_agent.models.comparison_schema import (
    ChangeCategory,
    ComparisonResult,
    EntityChange,
    GeometrySnapshot,
)
from cad_dxf_agent.models.design_ops_schema import (
    RecommendationType,
    ScopeSectionType,
    TakeoffConfidence,
)
from cad_dxf_agent.models.ops_schema import ChangeSet, EditOperation, OpType
from cad_dxf_agent.models.qna_schema import RegionContext

# ---------------------------------------------------------------------------
# Shared helpers
# ---------------------------------------------------------------------------


def _entity(
    handle: str,
    layer: str = "STRUCTURAL",
    entity_type: EntityType = EntityType.LINE,
    text_content: str | None = None,
    block_name: str | None = None,
    x: float = 0.0,
    y: float = 0.0,
    text_geometry: TextGeometry | None = None,
) -> EntityRef:
    return EntityRef(
        handle=handle,
        entity_type=entity_type,
        layer=layer,
        text_content=text_content,
        block_name=block_name,
        insert_point=Point2D(x=x, y=y),
        text_geometry=text_geometry,
    )


def _insert(handle: str, block_name: str, layer: str = "STRUCTURAL", x: float = 0.0) -> EntityRef:
    return _entity(
        handle=handle,
        entity_type=EntityType.INSERT,
        block_name=block_name,
        layer=layer,
        x=x,
    )


def _text(
    handle: str,
    text: str,
    layer: str = "NOTES",
    text_geometry: TextGeometry | None = None,
) -> EntityRef:
    return _entity(
        handle=handle,
        entity_type=EntityType.TEXT,
        text_content=text,
        layer=layer,
        text_geometry=text_geometry,
    )


def _context(entities: list[EntityRef]) -> DrawingContext:
    layer_names = sorted({e.layer for e in entities})
    return DrawingContext(
        file_path="test.dxf",
        entities=entities,
        layers=[LayerRule(name=n) for n in layer_names],
    )


def _snapshot(
    handle: str = "S1",
    entity_type: EntityType = EntityType.LINE,
    layer: str = "STRUCTURAL",
    text_content: str | None = None,
) -> GeometrySnapshot:
    return GeometrySnapshot(
        handle=handle,
        entity_type=entity_type,
        layer=layer,
        points=[Point2D(x=0, y=0), Point2D(x=10, y=0)],
        text_content=text_content,
    )


def _comparison_result(
    *changes: EntityChange,
    warnings: list[str] | None = None,
) -> ComparisonResult:
    return ComparisonResult(
        changes=list(changes),
        summary={"added": 0, "removed": 0, "modified": 0, "moved": 0, "unchanged": 0},
        warnings=warnings or [],
    )


def _change(
    category: ChangeCategory,
    handle: str = "E1",
    layer: str = "STRUCTURAL",
    entity_type: EntityType = EntityType.LINE,
    text_content: str | None = None,
    confidence: float = 0.9,
) -> EntityChange:
    snap = _snapshot(handle=handle, entity_type=entity_type, layer=layer, text_content=text_content)
    if category == ChangeCategory.REMOVED:
        return EntityChange(category=category, master_snapshot=snap, confidence=confidence)
    return EntityChange(category=category, revision_snapshot=snap, confidence=confidence)


# ---------------------------------------------------------------------------
# LayoutRecommender
# ---------------------------------------------------------------------------


class TestLayoutRecommenderEmptyDrawing:
    def test_returns_result_not_none(self):
        ctx = _context([])
        result = LayoutRecommender().recommend(ctx, "any prompt")
        assert result is not None

    def test_empty_drawing_flag_present(self):
        ctx = _context([])
        result = LayoutRecommender().recommend(ctx, "any prompt")
        assert "empty_drawing" in result.ambiguity_flags
        assert result.recommendations == []
        assert result.aggregate_confidence == 0.0

    def test_empty_drawing_has_limitation(self):
        ctx = _context([])
        result = LayoutRecommender().recommend(ctx, "any prompt")
        assert result.limitations

    def test_empty_drawing_has_no_recommendations(self):
        ctx = _context([])
        result = LayoutRecommender().recommend(ctx, "any prompt")
        assert result.recommendations == []

    def test_empty_drawing_aggregate_confidence_is_zero(self):
        ctx = _context([])
        result = LayoutRecommender().recommend(ctx, "any prompt")
        assert result.aggregate_confidence == 0.0


class TestLayoutRecommenderLayerDistribution:
    def test_concentrated_layer_triggers_recommendation(self):
        # More than 60% on one layer with total > 10 entities
        entities = [_entity(f"S{i}", layer="WALLS") for i in range(12)]
        ctx = _context(entities)
        result = LayoutRecommender().recommend(ctx, "analyse layout")
        layer_recs = [
            r
            for r in result.recommendations
            if r.type == RecommendationType.GENERAL_OBSERVATION and "WALLS" in r.title
        ]
        assert layer_recs, "Expected a recommendation for concentrated layer 'WALLS'"

    def test_concentrated_layer_recommendation_names_layer(self):
        entities = [_entity(f"H{i}", layer="BEAMS") for i in range(12)]
        ctx = _context(entities)
        result = LayoutRecommender().recommend(ctx, "check")
        titles = [r.title for r in result.recommendations]
        assert any("BEAMS" in t for t in titles)

    def test_balanced_layers_no_concentration_recommendation(self):
        # Equal split across two layers — neither exceeds 60%
        entities = [_entity(f"A{i}", layer="LAYER_A") for i in range(5)] + [
            _entity(f"B{i}", layer="LAYER_B") for i in range(5)
        ]
        ctx = _context(entities)
        result = LayoutRecommender().recommend(ctx, "check balance")
        # No layer should have ratio > 0.6 with total > 10 — also total is exactly 10 so no trigger
        layer_obs = [
            r
            for r in result.recommendations
            if r.type == RecommendationType.GENERAL_OBSERVATION
            and "concentration" in r.title.lower()
        ]
        assert layer_obs == []

    def test_drawing_summary_includes_entity_count(self):
        entities = [_entity(f"E{i}", layer="STRUCTURAL") for i in range(6)]
        ctx = _context(entities)
        result = LayoutRecommender().recommend(ctx, "check")
        assert "6" in result.drawing_summary

    def test_drawing_summary_includes_layer_count(self):
        entities = [_entity("E1", layer="LAYER_A"), _entity("E2", layer="LAYER_B")]
        ctx = _context(entities)
        result = LayoutRecommender().recommend(ctx, "check")
        assert "2" in result.drawing_summary


class TestLayoutRecommenderBlockPlacement:
    def test_repeated_block_triggers_recommendation(self):
        # Block appearing >= 3 times triggers REGION_USAGE recommendation
        entities = [_insert(f"B{i}", block_name="DOOR_A", x=float(i * 5)) for i in range(4)]
        ctx = _context(entities)
        result = LayoutRecommender().recommend(ctx, "check placement")
        block_recs = [
            r for r in result.recommendations if r.type == RecommendationType.REGION_USAGE
        ]
        assert block_recs, "Expected REGION_USAGE recommendation for repeated block 'DOOR_A'"

    def test_repeated_block_recommendation_includes_count(self):
        entities = [_insert(f"C{i}", block_name="COL_MK", x=float(i * 10)) for i in range(5)]
        ctx = _context(entities)
        result = LayoutRecommender().recommend(ctx, "check")
        rec = next(
            (r for r in result.recommendations if "COL_MK" in r.title),
            None,
        )
        assert rec is not None
        assert "5" in rec.description

    def test_block_appearing_twice_does_not_trigger_recommendation(self):
        # Threshold is >= 3; two instances must not generate a recommendation
        entities = [_insert("B1", block_name="RARE"), _insert("B2", block_name="RARE", x=5.0)]
        ctx = _context(entities)
        result = LayoutRecommender().recommend(ctx, "check")
        rare_recs = [r for r in result.recommendations if "RARE" in r.title]
        assert rare_recs == []


class TestLayoutRecommenderRegionMode:
    def test_partial_region_adds_flag(self):
        entities = [_entity(f"E{i}", layer="WALLS") for i in range(5)]
        ctx = _context(entities)
        region = RegionContext(entities=entities, is_whole_drawing=False, ambiguity_flags=[])
        result = LayoutRecommender().recommend(ctx, "check region", region=region)
        assert "partial_region" in result.ambiguity_flags

    def test_partial_region_adds_limitation(self):
        entities = [_entity("E1", layer="WALLS")]
        ctx = _context(entities)
        region = RegionContext(entities=entities, is_whole_drawing=False, ambiguity_flags=[])
        result = LayoutRecommender().recommend(ctx, "check", region=region)
        assert any("region" in lim.lower() for lim in result.limitations)

    def test_context_truncated_region_flag_propagates(self):
        entities = [_entity("E1", layer="WALLS")]
        ctx = _context(entities)
        region = RegionContext(
            entities=entities,
            is_whole_drawing=False,
            ambiguity_flags=["context_truncated"],
        )
        result = LayoutRecommender().recommend(ctx, "check", region=region)
        assert "context_truncated" in result.ambiguity_flags

    def test_whole_drawing_region_no_partial_flag(self):
        entities = [_entity(f"E{i}", layer="WALLS") for i in range(5)]
        ctx = _context(entities)
        region = RegionContext(entities=entities, is_whole_drawing=True, ambiguity_flags=[])
        result = LayoutRecommender().recommend(ctx, "whole drawing", region=region)
        assert "partial_region" not in result.ambiguity_flags


class TestLayoutRecommenderSparseText:
    def test_fewer_than_three_text_entities_adds_sparse_flag(self):
        # All non-text entities → sparse_text_evidence must be raised
        entities = [
            _entity(f"L{i}", layer="STRUCTURAL", entity_type=EntityType.LINE) for i in range(8)
        ]
        ctx = _context(entities)
        result = LayoutRecommender().recommend(ctx, "check")
        assert "sparse_text_evidence" in result.ambiguity_flags

    def test_sufficient_text_does_not_add_sparse_flag(self):
        native = TextGeometry.for_provenance(TextProvenance.NATIVE_CAD_TEXT)
        entities = [_text(f"T{i}", text=f"Label {i}", text_geometry=native) for i in range(4)]
        ctx = _context(entities)
        result = LayoutRecommender().recommend(ctx, "check")
        assert "sparse_text_evidence" not in result.ambiguity_flags


# ---------------------------------------------------------------------------
# RevisionSummarizer
# ---------------------------------------------------------------------------


class TestRevisionSummarizerNoData:
    def test_no_args_returns_summary_not_none(self):
        result = RevisionSummarizer().summarize()
        assert result is not None

    def test_no_args_headline_is_meaningful(self):
        result = RevisionSummarizer().summarize()
        assert "No revision data" in result.headline or len(result.headline) > 0

    def test_no_args_missing_context_fields(self):
        result = RevisionSummarizer().summarize()
        assert "comparison_result" in result.missing_context
        assert "changeset" in result.missing_context


class TestRevisionSummarizerFromChangeset:
    def _make_changeset(self, *ops: EditOperation) -> ChangeSet:
        return ChangeSet(operations=list(ops), prompt="test prompt")

    def _op(
        self,
        op_type: OpType = OpType.MOVE_ENTITY,
        handle: str = "H1",
        layer: str = "STRUCTURAL",
    ) -> EditOperation:
        return EditOperation(op_type=op_type, target_handle=handle, target_layer=layer)

    def test_single_op_headline_mentions_count(self):
        cs = self._make_changeset(self._op())
        result = RevisionSummarizer().summarize(changeset=cs)
        assert "1" in result.headline

    def test_headline_for_zero_ops(self):
        cs = ChangeSet(operations=[], prompt="nothing")
        result = RevisionSummarizer().summarize(changeset=cs)
        assert "No operations" in result.headline or "0" in result.headline

    def test_key_changes_length_matches_ops(self):
        cs = self._make_changeset(
            self._op(OpType.MOVE_ENTITY, "H1"),
            self._op(OpType.DELETE_ENTITY, "H2"),
        )
        result = RevisionSummarizer().summarize(changeset=cs)
        assert len(result.key_changes) == 2
        # Verify each change carries the correct op type and layer
        assert result.key_changes[0].change_type == "move_entity"
        assert result.key_changes[1].change_type == "delete_entity"
        assert result.key_changes[0].layer == "STRUCTURAL"
        assert result.key_changes[1].layer == "STRUCTURAL"

    def test_key_change_layer_set_from_op(self):
        op = self._op(OpType.EDIT_TEXT, "H3", layer="NOTES")
        cs = self._make_changeset(op)
        result = RevisionSummarizer().summarize(changeset=cs)
        assert result.key_changes[0].layer == "NOTES"

    def test_areas_affected_contains_layers_from_ops(self):
        ops = [
            self._op(OpType.MOVE_ENTITY, "H1", layer="STRUCTURAL"),
            self._op(OpType.EDIT_TEXT, "H2", layer="NOTES"),
        ]
        cs = ChangeSet(operations=ops, prompt="test")
        result = RevisionSummarizer().summarize(changeset=cs)
        assert "STRUCTURAL" in result.areas_affected
        assert "NOTES" in result.areas_affected

    def test_areas_affected_sorted(self):
        ops = [
            self._op(OpType.MOVE_ENTITY, "H1", layer="ZONE_C"),
            self._op(OpType.MOVE_ENTITY, "H2", layer="ZONE_A"),
            self._op(OpType.MOVE_ENTITY, "H3", layer="ZONE_B"),
        ]
        cs = ChangeSet(operations=ops, prompt="test")
        result = RevisionSummarizer().summarize(changeset=cs)
        assert result.areas_affected == ["ZONE_A", "ZONE_B", "ZONE_C"]

    def test_move_entity_plain_description(self):
        op = self._op(OpType.MOVE_ENTITY, "H1", layer="STRUCTURAL")
        cs = self._make_changeset(op)
        result = RevisionSummarizer().summarize(changeset=cs)
        assert "repositioned" in result.key_changes[0].plain_description.lower()

    def test_delete_entity_plain_description(self):
        op = self._op(OpType.DELETE_ENTITY, "H1", layer="STRUCTURAL")
        cs = self._make_changeset(op)
        result = RevisionSummarizer().summarize(changeset=cs)
        assert "removed" in result.key_changes[0].plain_description.lower()

    def test_edit_text_plain_description(self):
        op = self._op(OpType.EDIT_TEXT, "H1", layer="NOTES")
        cs = self._make_changeset(op)
        result = RevisionSummarizer().summarize(changeset=cs)
        assert "text" in result.key_changes[0].plain_description.lower()

    def test_add_block_plain_description(self):
        op = self._op(OpType.ADD_BLOCK, "H1", layer="STRUCTURAL")
        cs = self._make_changeset(op)
        result = RevisionSummarizer().summarize(changeset=cs)
        assert (
            "block" in result.key_changes[0].plain_description.lower()
            or "inserted" in result.key_changes[0].plain_description.lower()
        )

    def test_unknown_layer_falls_back_to_unknown(self):
        op = EditOperation(op_type=OpType.MOVE_ENTITY, target_handle="H1", target_layer=None)
        cs = ChangeSet(operations=[op], prompt="test")
        result = RevisionSummarizer().summarize(changeset=cs)
        assert result.key_changes[0].layer == "unknown"

    def test_change_count_equals_op_count(self):
        ops = [self._op(op_type=OpType.MOVE_ENTITY, handle=f"H{i}") for i in range(3)]
        cs = ChangeSet(operations=ops, prompt="test")
        result = RevisionSummarizer().summarize(changeset=cs)
        assert result.change_count == 3


class TestRevisionSummarizerFromComparison:
    def test_added_change_builds_summary(self):
        cr = _comparison_result(_change(ChangeCategory.ADDED, handle="A1"))
        result = RevisionSummarizer().summarize(comparison_result=cr)
        assert result.change_count == 1
        assert "added" in result.headline.lower()

    def test_removed_change_builds_summary(self):
        cr = _comparison_result(_change(ChangeCategory.REMOVED, handle="R1"))
        result = RevisionSummarizer().summarize(comparison_result=cr)
        assert result.change_count == 1
        assert "removed" in result.headline.lower()

    def test_modified_change_builds_summary(self):
        cr = _comparison_result(_change(ChangeCategory.MODIFIED, handle="M1"))
        result = RevisionSummarizer().summarize(comparison_result=cr)
        assert "modified" in result.headline.lower()

    def test_moved_change_builds_summary(self):
        cr = _comparison_result(_change(ChangeCategory.MOVED, handle="MV1"))
        result = RevisionSummarizer().summarize(comparison_result=cr)
        assert "moved" in result.headline.lower()

    def test_unchanged_changes_excluded_from_count(self):
        changes = [
            _change(ChangeCategory.UNCHANGED, handle="U1"),
            _change(ChangeCategory.ADDED, handle="A1"),
        ]
        cr = _comparison_result(*changes)
        result = RevisionSummarizer().summarize(comparison_result=cr)
        # Only the ADDED change should count
        assert result.change_count == 1

    def test_no_changes_headline_says_no_changes(self):
        cr = _comparison_result()
        result = RevisionSummarizer().summarize(comparison_result=cr)
        assert "No changes" in result.headline

    def test_multiple_categories_all_in_headline(self):
        changes = [
            _change(ChangeCategory.ADDED, handle="A1"),
            _change(ChangeCategory.REMOVED, handle="R1"),
            _change(ChangeCategory.MODIFIED, handle="M1"),
        ]
        cr = _comparison_result(*changes)
        result = RevisionSummarizer().summarize(comparison_result=cr)
        assert "added" in result.headline
        assert "removed" in result.headline
        assert "modified" in result.headline

    def test_areas_affected_contains_layer(self):
        cr = _comparison_result(_change(ChangeCategory.ADDED, layer="STRUCTURAL"))
        result = RevisionSummarizer().summarize(comparison_result=cr)
        assert "STRUCTURAL" in result.areas_affected

    def test_warnings_from_comparison_appear_in_caveats(self):
        cr = _comparison_result(
            _change(ChangeCategory.ADDED),
            warnings=["Profile filtered out 10 entities."],
        )
        result = RevisionSummarizer().summarize(comparison_result=cr)
        assert any("filtered" in c.lower() or "Profile" in c for c in result.caveats)

    def test_text_content_included_in_plain_description(self):
        cr = _comparison_result(
            _change(ChangeCategory.MODIFIED, handle="T1", text_content="Column C-4")
        )
        result = RevisionSummarizer().summarize(comparison_result=cr)
        # The _plain_description helper prefixes text content in parentheses
        assert "Column C-4" in result.key_changes[0].plain_description

    def test_overall_assessment_summarises_categories(self):
        changes = [
            _change(ChangeCategory.ADDED, handle="A1"),
            _change(ChangeCategory.REMOVED, handle="R1"),
        ]
        cr = _comparison_result(*changes)
        result = RevisionSummarizer().summarize(comparison_result=cr)
        assert "added" in result.overall_assessment.lower()
        assert "removed" in result.overall_assessment.lower()

    def test_key_change_entries_have_evidence_when_handle_exists(self):
        snap = _snapshot(handle="EV1", layer="STRUCTURAL")
        change = EntityChange(
            category=ChangeCategory.ADDED,
            revision_snapshot=snap,
            confidence=0.9,
        )
        cr = _comparison_result(change)
        result = RevisionSummarizer().summarize(comparison_result=cr)
        # Entry for ADDED should carry evidence pointing to handle EV1
        assert result.key_changes
        assert any(e.entity_handle == "EV1" for e in result.key_changes[0].evidence)


# ---------------------------------------------------------------------------
# TakeoffGenerator — supplemental tests not in test_takeoff_generator.py
# ---------------------------------------------------------------------------


class TestTakeoffGeneratorBlockUnit:
    def test_block_items_use_ea_as_unit(self):
        entities = [_insert(f"B{i}", block_name="WINDOW") for i in range(3)]
        ctx = _context(entities)
        result = TakeoffGenerator().generate(ctx, "count windows")
        window_items = [it for it in result.items if it.source_block_name == "WINDOW"]
        assert window_items[0].unit == "ea"

    def test_block_item_entity_handles_match_inserts(self):
        entities = [_insert(f"BH{i}", block_name="DOOR", x=float(i)) for i in range(3)]
        ctx = _context(entities)
        result = TakeoffGenerator().generate(ctx, "count doors")
        door_item = next(it for it in result.items if it.source_block_name == "DOOR")
        # All three handles must appear in the item
        assert set(door_item.entity_handles) == {"BH0", "BH1", "BH2"}

    def test_block_item_source_layer_is_first_sorted_layer(self):
        # Two inserts on different layers — source_layer should be alphabetically first
        entities = [
            _insert("B1", block_name="COL", layer="ZONE_B"),
            _insert("B2", block_name="COL", layer="ZONE_A"),
        ]
        ctx = _context(entities)
        result = TakeoffGenerator().generate(ctx, "count")
        col_item = next(it for it in result.items if it.source_block_name == "COL")
        assert col_item.source_layer == "ZONE_A"


class TestTakeoffGeneratorLayerCountingUnit:
    def test_layer_item_has_no_unit(self):
        entities = [
            _entity("L1", layer="WALLS", entity_type=EntityType.LINE),
            _entity("L2", layer="WALLS", entity_type=EntityType.LINE),
        ]
        ctx = _context(entities)
        result = TakeoffGenerator().generate(ctx, "count walls")
        wall_items = [it for it in result.items if it.source_layer == "WALLS"]
        assert wall_items[0].unit is None

    def test_layer_item_confidence_is_medium(self):
        entities = [
            _entity("M1", layer="SLAB", entity_type=EntityType.LWPOLYLINE),
            _entity("M2", layer="SLAB", entity_type=EntityType.LWPOLYLINE),
        ]
        ctx = _context(entities)
        result = TakeoffGenerator().generate(ctx, "count slab")
        slab_items = [it for it in result.items if it.source_layer == "SLAB"]
        assert slab_items[0].confidence == TakeoffConfidence.MEDIUM

    def test_layer_item_has_caveat_about_layer_membership(self):
        entities = [
            _entity("C1", layer="MISC", entity_type=EntityType.LINE),
            _entity("C2", layer="MISC", entity_type=EntityType.LINE),
        ]
        ctx = _context(entities)
        result = TakeoffGenerator().generate(ctx, "count misc")
        misc_items = [it for it in result.items if it.source_layer == "MISC"]
        assert misc_items
        assert any("layer" in c.lower() for c in misc_items[0].caveats)


class TestTakeoffGeneratorTextPatterns:
    def test_nos_pattern_extracts_quantity(self):
        # "nos." is listed in the pattern as a suffix — e.g. "12 nos."
        entities = [_text("T1", "12 nos. bolts")]
        ctx = _context(entities)
        result = TakeoffGenerator().generate(ctx, "count")
        text_items = [it for it in result.items if "12 nos" in it.name]
        assert text_items
        assert text_items[0].quantity == 12

    def test_units_pattern_extracts_quantity(self):
        entities = [_text("T2", "7 units required")]
        ctx = _context(entities)
        result = TakeoffGenerator().generate(ctx, "count")
        text_items = [it for it in result.items if "7 units" in it.name]
        assert text_items
        assert text_items[0].quantity == 7

    def test_text_item_name_includes_label_prefix(self):
        entities = [_text("T3", "4 ea girders")]
        ctx = _context(entities)
        result = TakeoffGenerator().generate(ctx, "count")
        text_items = [it for it in result.items if "girders" in it.name]
        assert text_items
        assert all(it.name.startswith("Text-derived:") for it in text_items)

    def test_text_item_entity_handle_matches_source(self):
        entities = [_text("HNDL9", "3 ea beams")]
        ctx = _context(entities)
        result = TakeoffGenerator().generate(ctx, "count")
        text_items = [it for it in result.items if "3 ea beams" in it.name]
        assert text_items
        assert "HNDL9" in text_items[0].entity_handles


# ---------------------------------------------------------------------------
# ScopeBuilder
# ---------------------------------------------------------------------------


class TestScopeBuilderBasic:
    def test_returns_scope_summary(self):
        from cad_dxf_agent.models.design_ops_schema import ScopeSummary

        entities = [_insert(f"B{i}", block_name="COL", x=float(i * 10)) for i in range(4)]
        ctx = _context(entities)
        result = ScopeBuilder().build(ctx, "scope of work")
        assert isinstance(result, ScopeSummary)

    def test_empty_drawing_does_not_crash(self):
        ctx = _context([])
        result = ScopeBuilder().build(ctx, "scope of work")
        assert result is not None

    def test_no_revision_data_omits_revision_section(self):
        ctx = _context([])
        result = ScopeBuilder().build(ctx, "scope")
        assert "revision_summary" in result.omitted_sections

    def test_changeset_adds_revision_section(self):
        entities = [_entity("E1", layer="STRUCTURAL")]
        ctx = _context(entities)
        op = EditOperation(
            op_type=OpType.MOVE_ENTITY,
            target_handle="E1",
            target_layer="STRUCTURAL",
        )
        cs = ChangeSet(operations=[op], prompt="move it")
        result = ScopeBuilder().build(ctx, "scope", changeset=cs)
        section_types = [s.section_type for s in result.sections]
        assert ScopeSectionType.REVISION_SUMMARY in section_types

    def test_comparison_result_adds_revision_section(self):
        entities = [_entity("E1", layer="STRUCTURAL")]
        ctx = _context(entities)
        cr = _comparison_result(_change(ChangeCategory.ADDED, handle="A1"))
        result = ScopeBuilder().build(ctx, "scope", comparison_result=cr)
        section_types = [s.section_type for s in result.sections]
        assert ScopeSectionType.REVISION_SUMMARY in section_types

    def test_drawing_with_blocks_adds_takeoff_section(self):
        # At least two block inserts of the same name → TakeoffGenerator returns items
        entities = [_insert(f"B{i}", block_name="COLUMN") for i in range(3)]
        ctx = _context(entities)
        result = ScopeBuilder().build(ctx, "scope")
        section_types = [s.section_type for s in result.sections]
        assert ScopeSectionType.TAKEOFF_CANDIDATES in section_types

    def test_sections_are_serialisable(self):
        entities = [_insert(f"B{i}", block_name="DOOR", x=float(i * 5)) for i in range(3)]
        ctx = _context(entities)
        result = ScopeBuilder().build(ctx, "scope")
        # model_dump() must not raise
        dumped = result.model_dump()
        assert isinstance(dumped, dict)
        assert "sections" in dumped

    def test_aggregate_confidence_in_range(self):
        entities = [_insert(f"B{i}", block_name="COL", x=float(i * 5)) for i in range(5)]
        ctx = _context(entities)
        result = ScopeBuilder().build(ctx, "scope")
        assert 0.0 <= result.aggregate_confidence <= 1.0

    def test_section_caveats_propagate_to_summary(self):
        # A partial-region takeoff generates caveats that propagate to the scope summary
        entities = [_insert(f"R{i}", block_name="MARK", x=float(i * 5)) for i in range(3)]
        ctx = _context(entities)
        region = RegionContext(entities=entities, is_whole_drawing=False, ambiguity_flags=[])
        result = ScopeBuilder().build(ctx, "scope of region work", region=region)
        # partial_region flag should appear in the summary's ambiguity_flags
        assert "partial_region" in result.ambiguity_flags


# ---------------------------------------------------------------------------
# Negative / boundary tests — adversarial inputs
# ---------------------------------------------------------------------------


class TestRevisionSummarizerMalformedOps:
    """Test RevisionSummarizer with malformed EditOperation inputs."""

    def test_none_handle_op_still_produces_change(self):
        """An op with target_handle=None must not crash and should produce a key_change."""
        op = EditOperation(op_type=OpType.MOVE_ENTITY, target_handle=None, target_layer="WALLS")
        cs = ChangeSet(operations=[op], prompt="test")
        result = RevisionSummarizer().summarize(changeset=cs)
        assert result.change_count == 1
        assert result.key_changes[0].layer == "WALLS"

    def test_mixed_valid_and_none_handle_ops(self):
        """A mix of valid and None-handle ops must not crash and must count all ops."""
        ops = [
            EditOperation(op_type=OpType.MOVE_ENTITY, target_handle="H1", target_layer="A"),
            EditOperation(op_type=OpType.DELETE_ENTITY, target_handle=None, target_layer="B"),
            EditOperation(op_type=OpType.EDIT_TEXT, target_handle="H3", target_layer="C"),
        ]
        cs = ChangeSet(operations=ops, prompt="mixed")
        result = RevisionSummarizer().summarize(changeset=cs)
        assert result.change_count == 3
        layers = {kc.layer for kc in result.key_changes}
        assert layers == {"A", "B", "C"}


# ---------------------------------------------------------------------------
# Mutation-killing tests — density threshold, _plain_description exact text,
# _overall_assessment format, _technical_detail displacement,
# _op_to_plain with context, _extract_text_quantities bounds,
# _analyze_text_labels low-trust, _analyze_layer_distribution description,
# _build_summary entity types, ScopeBuilder section content & confidence
# ---------------------------------------------------------------------------


class TestAnalyzeDensityMutationKilling:
    """Kill mutations on _analyze_density: threshold, area calc, confidence."""

    def test_exactly_four_entities_returns_no_recommendation(self):
        """len(positioned) < 5 branch — 4 entities must not trigger density rec."""
        entities = [_entity(f"E{i}", x=float(i), y=float(i)) for i in range(4)]
        ctx = _context(entities)
        result = LayoutRecommender().recommend(ctx, "check density")
        placement_recs = [
            r for r in result.recommendations if r.type == RecommendationType.PLACEMENT_GUIDANCE
        ]
        assert placement_recs == []

    def test_exactly_five_entities_clumped_triggers_density_rec(self):
        """len(positioned) == 5 at boundary — all at same point → density > 0.1."""
        # All 5 at the same x,y → area = max(1.0) → density = 5/1.0 = 5.0 >> 0.1
        entities = [_entity(f"E{i}", x=0.0, y=0.0) for i in range(5)]
        ctx = _context(entities)
        result = LayoutRecommender().recommend(ctx, "check density")
        placement_recs = [
            r for r in result.recommendations if r.type == RecommendationType.PLACEMENT_GUIDANCE
        ]
        assert placement_recs, "5 clumped entities must trigger density recommendation"

    def test_density_description_contains_entity_count(self):
        """Description string must mention the positioned entity count."""
        entities = [_entity(f"E{i}", x=float(i * 0.1), y=0.0) for i in range(6)]
        ctx = _context(entities)
        result = LayoutRecommender().recommend(ctx, "check")
        placement_recs = [
            r for r in result.recommendations if r.type == RecommendationType.PLACEMENT_GUIDANCE
        ]
        assert placement_recs
        assert "6" in placement_recs[0].description

    def test_density_description_contains_density_value(self):
        """Description must contain the computed density string 'density:'."""
        entities = [_entity(f"E{i}", x=float(i * 0.1), y=0.0) for i in range(6)]
        ctx = _context(entities)
        result = LayoutRecommender().recommend(ctx, "check")
        placement_recs = [
            r for r in result.recommendations if r.type == RecommendationType.PLACEMENT_GUIDANCE
        ]
        assert placement_recs
        assert "density:" in placement_recs[0].description

    def test_density_confidence_is_0_70(self):
        """Density recommendation confidence must be exactly 0.70 (before any adjustment)."""
        # Use many entities on 2 layers so sparse-text adjustment only touches layer rec,
        # and density rec stays at 0.70 minus sparse penalty (0.15) = 0.55 (after penalty).
        # To get raw 0.70, supply 3 text entities and spread entities enough not to be sparse.
        native = TextGeometry.for_provenance(TextProvenance.NATIVE_CAD_TEXT)
        text_entities = [_text(f"T{i}", text=f"Label {i}", text_geometry=native) for i in range(3)]
        # 5 non-text entities all at same point → triggers density rec
        line_entities = [_entity(f"L{i}", x=0.0, y=0.0) for i in range(5)]
        ctx = _context(text_entities + line_entities)
        result = LayoutRecommender().recommend(ctx, "check")
        density_recs = [
            r for r in result.recommendations if r.type == RecommendationType.PLACEMENT_GUIDANCE
        ]
        assert density_recs
        # Raw confidence 0.70, no sparse penalty (3 text entities present)
        assert density_recs[0].confidence == pytest.approx(0.70)

    def test_wide_spread_entities_no_density_rec(self):
        """Entities spread far apart → low density → no recommendation."""
        # 10 entities spread 1000 units apart → density = 10/(1000*1000) = 1e-5 << 0.1
        entities = [_entity(f"E{i}", x=float(i * 100), y=float(i * 100)) for i in range(10)]
        ctx = _context(entities)
        result = LayoutRecommender().recommend(ctx, "check density spread")
        placement_recs = [
            r for r in result.recommendations if r.type == RecommendationType.PLACEMENT_GUIDANCE
        ]
        assert placement_recs == []


class TestPlainDescriptionExactText:
    """Kill mutations on _plain_description template strings."""

    def test_added_uses_was_added(self):
        cr = _comparison_result(_change(ChangeCategory.ADDED, handle="A1"))
        result = RevisionSummarizer().summarize(comparison_result=cr)
        assert "was added" in result.key_changes[0].plain_description

    def test_removed_uses_was_removed(self):
        cr = _comparison_result(_change(ChangeCategory.REMOVED, handle="R1"))
        result = RevisionSummarizer().summarize(comparison_result=cr)
        assert "was removed" in result.key_changes[0].plain_description

    def test_modified_uses_was_modified(self):
        cr = _comparison_result(_change(ChangeCategory.MODIFIED, handle="M1"))
        result = RevisionSummarizer().summarize(comparison_result=cr)
        assert "was modified" in result.key_changes[0].plain_description

    def test_moved_uses_was_repositioned(self):
        cr = _comparison_result(_change(ChangeCategory.MOVED, handle="V1"))
        result = RevisionSummarizer().summarize(comparison_result=cr)
        assert "was repositioned" in result.key_changes[0].plain_description

    def test_text_hint_uses_single_quotes(self):
        """Text hint must appear as ('preview') with single quotes."""
        cr = _comparison_result(_change(ChangeCategory.ADDED, handle="T1", text_content="Beam B-3"))
        result = RevisionSummarizer().summarize(comparison_result=cr)
        desc = result.key_changes[0].plain_description
        assert "'Beam B-3'" in desc

    def test_entity_type_appears_in_plain_description(self):
        """The entity type string must be interpolated into the description."""
        snap = _snapshot(handle="L1", entity_type=EntityType.LWPOLYLINE, layer="STRUCT")
        change = EntityChange(
            category=ChangeCategory.ADDED,
            revision_snapshot=snap,
            confidence=0.9,
        )
        cr = _comparison_result(change)
        result = RevisionSummarizer().summarize(comparison_result=cr)
        assert "lwpolyline" in result.key_changes[0].plain_description.lower()


class TestOverallAssessmentExactFormat:
    """Kill mutations on _overall_assessment string formatting and joining."""

    def test_overall_assessment_ends_with_period(self):
        changes = [_change(ChangeCategory.ADDED, handle="A1")]
        cr = _comparison_result(*changes)
        result = RevisionSummarizer().summarize(comparison_result=cr)
        assert result.overall_assessment.endswith(".")

    def test_overall_assessment_exact_added_count(self):
        """'1 element(s) were added' must appear verbatim."""
        changes = [_change(ChangeCategory.ADDED, handle="A1")]
        cr = _comparison_result(*changes)
        result = RevisionSummarizer().summarize(comparison_result=cr)
        assert "1 element(s) were added" in result.overall_assessment

    def test_overall_assessment_two_added(self):
        changes = [
            _change(ChangeCategory.ADDED, handle="A1"),
            _change(ChangeCategory.ADDED, handle="A2"),
        ]
        cr = _comparison_result(*changes)
        result = RevisionSummarizer().summarize(comparison_result=cr)
        assert "2 element(s) were added" in result.overall_assessment

    def test_overall_assessment_combined_added_removed(self):
        """Multiple categories joined with '. ' separator."""
        changes = [
            _change(ChangeCategory.ADDED, handle="A1"),
            _change(ChangeCategory.REMOVED, handle="R1"),
        ]
        cr = _comparison_result(*changes)
        result = RevisionSummarizer().summarize(comparison_result=cr)
        oa = result.overall_assessment
        assert "1 element(s) were added" in oa
        assert "1 element(s) were removed" in oa
        # Parts joined with ". "
        assert ". " in oa

    def test_overall_assessment_modified_exact_phrase(self):
        changes = [_change(ChangeCategory.MODIFIED, handle="M1")]
        cr = _comparison_result(*changes)
        result = RevisionSummarizer().summarize(comparison_result=cr)
        assert "1 element(s) were modified" in result.overall_assessment

    def test_overall_assessment_moved_exact_phrase(self):
        changes = [_change(ChangeCategory.MOVED, handle="MV1")]
        cr = _comparison_result(*changes)
        result = RevisionSummarizer().summarize(comparison_result=cr)
        assert "1 element(s) were repositioned" in result.overall_assessment

    def test_overall_assessment_no_changes(self):
        cr = _comparison_result()
        result = RevisionSummarizer().summarize(comparison_result=cr)
        assert result.overall_assessment == "No changes were detected between the drawings."


class TestTechnicalDetailDisplacement:
    """Kill mutations on _technical_detail displacement formatting."""

    def test_technical_detail_contains_displacement_when_present(self):
        """EntityChange with displacement must produce technical_detail with 'displacement='."""
        from cad_dxf_agent.models.cad_schema import Point2D
        from cad_dxf_agent.models.comparison_schema import GeometrySnapshot

        snap = GeometrySnapshot(
            handle="MV1",
            entity_type=EntityType.LINE,
            layer="STRUCTURAL",
            points=[Point2D(x=0, y=0), Point2D(x=10, y=0)],
        )
        change = EntityChange(
            category=ChangeCategory.MOVED,
            master_snapshot=snap,
            revision_snapshot=snap,
            displacement=Point2D(x=5.0, y=-3.0),
            confidence=0.9,
        )
        cr = _comparison_result(change)
        result = RevisionSummarizer().summarize(comparison_result=cr)
        tech = result.key_changes[0].technical_detail
        assert "displacement=" in tech
        assert "5.0" in tech
        assert "-3.0" in tech

    def test_technical_detail_empty_when_no_displacement(self):
        """EntityChange without displacement must produce empty technical_detail."""
        cr = _comparison_result(_change(ChangeCategory.MODIFIED, handle="M1"))
        result = RevisionSummarizer().summarize(comparison_result=cr)
        # No displacement on this change → technical_detail should be empty
        assert result.key_changes[0].technical_detail == ""


class TestOpToPlainWithContext:
    """Kill mutations on _op_to_plain entity description lookup path."""

    def test_with_context_entity_found_appends_description(self):
        """When context has the entity, plain description must include entity info."""
        entity = _entity("H1", layer="STRUCTURAL", entity_type=EntityType.LINE)
        ctx = _context([entity])
        op = EditOperation(
            op_type=OpType.MOVE_ENTITY,
            target_handle="H1",
            target_layer="STRUCTURAL",
        )
        cs = ChangeSet(operations=[op], prompt="move entity")
        result = RevisionSummarizer().summarize(changeset=cs, context=ctx)
        desc = result.key_changes[0].plain_description
        # With context, description should be "base — entity_desc" (non-empty entity_desc)
        assert " — " in desc

    def test_without_context_no_dash_separator(self):
        """Without context, plain description has no entity description suffix."""
        op = EditOperation(
            op_type=OpType.MOVE_ENTITY,
            target_handle="H1",
            target_layer="STRUCTURAL",
        )
        cs = ChangeSet(operations=[op], prompt="move entity")
        result = RevisionSummarizer().summarize(changeset=cs)
        desc = result.key_changes[0].plain_description
        # No context → no " — " suffix
        assert " — " not in desc

    def test_with_context_entity_not_found_falls_back_to_base(self):
        """Handle not in context → falls back to base template without separator."""
        entity = _entity("OTHER", layer="STRUCTURAL", entity_type=EntityType.LINE)
        ctx = _context([entity])
        op = EditOperation(
            op_type=OpType.MOVE_ENTITY,
            target_handle="MISSING",
            target_layer="STRUCTURAL",
        )
        cs = ChangeSet(operations=[op], prompt="move missing")
        result = RevisionSummarizer().summarize(changeset=cs, context=ctx)
        desc = result.key_changes[0].plain_description
        # Entity not found → no " — "
        assert " — " not in desc


class TestExtractTextQuantitiesMutationKilling:
    """Kill mutations on _extract_text_quantities bounds and OCR path."""

    def test_qty_zero_is_rejected(self):
        """qty == 0 must not produce a takeoff item (qty <= 0 guard)."""
        entities = [_text("T1", "0 ea widgets")]
        ctx = _context(entities)
        result = TakeoffGenerator().generate(ctx, "count")
        text_items = [it for it in result.items if "0 ea widgets" in it.name]
        assert text_items == []

    def test_qty_10001_is_rejected(self):
        """qty > 10000 must be skipped."""
        entities = [_text("T2", "10001 ea bolts")]
        ctx = _context(entities)
        result = TakeoffGenerator().generate(ctx, "count")
        text_items = [it for it in result.items if "10001" in it.name]
        assert text_items == []

    def test_qty_10000_is_accepted(self):
        """qty == 10000 is on the boundary and must be accepted."""
        entities = [_text("T3", "10000 ea rivets")]
        ctx = _context(entities)
        result = TakeoffGenerator().generate(ctx, "count")
        text_items = [it for it in result.items if "10000 ea rivets" in it.name]
        assert text_items
        assert text_items[0].quantity == 10000

    def test_qty_1_is_accepted(self):
        """qty == 1 is the minimum accepted value (> 0)."""
        entities = [_text("T4", "1 ea pump")]
        ctx = _context(entities)
        result = TakeoffGenerator().generate(ctx, "count")
        text_items = [it for it in result.items if "1 ea pump" in it.name]
        assert text_items
        assert text_items[0].quantity == 1

    def test_ocr_text_gets_estimate_only_confidence(self):
        """OCR-provenance text must produce ESTIMATE_ONLY confidence item."""
        ocr_geo = TextGeometry.for_provenance(TextProvenance.RASTER_OCR_TEXT)
        entities = [_text("T5", "5 ea panels", text_geometry=ocr_geo)]
        ctx = _context(entities)
        result = TakeoffGenerator().generate(ctx, "count")
        text_items = [it for it in result.items if "5 ea panels" in it.name]
        assert text_items
        assert text_items[0].confidence == TakeoffConfidence.ESTIMATE_ONLY

    def test_ocr_text_adds_provenance_warning(self):
        """OCR text must add a warning to provenance_warnings."""
        ocr_geo = TextGeometry.for_provenance(TextProvenance.RASTER_OCR_TEXT)
        entities = [_text("T6", "3 ea doors", text_geometry=ocr_geo)]
        ctx = _context(entities)
        result = TakeoffGenerator().generate(ctx, "count")
        assert result.provenance_warnings

    def test_native_text_gets_medium_confidence(self):
        """Native CAD text must produce MEDIUM confidence (not ESTIMATE_ONLY)."""
        native_geo = TextGeometry.for_provenance(TextProvenance.NATIVE_CAD_TEXT)
        entities = [_text("T7", "7 ea columns", text_geometry=native_geo)]
        ctx = _context(entities)
        result = TakeoffGenerator().generate(ctx, "count")
        text_items = [it for it in result.items if "7 ea columns" in it.name]
        assert text_items
        assert text_items[0].confidence == TakeoffConfidence.MEDIUM

    def test_aggregate_confidence_downgrades_with_ocr(self):
        """If any item is ESTIMATE_ONLY, aggregate must be ESTIMATE_ONLY."""
        ocr_geo = TextGeometry.for_provenance(TextProvenance.RASTER_OCR_TEXT)
        entities = [
            _insert("B1", block_name="COL"),
            _insert("B2", block_name="COL"),
            _insert("B3", block_name="COL"),
            _text("T1", "2 ea brackets", text_geometry=ocr_geo),
        ]
        ctx = _context(entities)
        result = TakeoffGenerator().generate(ctx, "count")
        assert result.aggregate_confidence == TakeoffConfidence.ESTIMATE_ONLY


class TestAnalyzeTextLabelsLowTrust:
    """Kill mutations on _analyze_text_labels low-trust recommendation."""

    def test_ocr_text_triggers_low_trust_recommendation(self):
        """Text with OCR provenance must produce a low-trust recommendation."""
        ocr_geo = TextGeometry.for_provenance(TextProvenance.RASTER_OCR_TEXT)
        entities = [_text("T1", "ROOM 101", text_geometry=ocr_geo)]
        ctx = _context(entities)
        result = LayoutRecommender().recommend(ctx, "check labels")
        low_trust_recs = [
            r
            for r in result.recommendations
            if "low-trust" in r.title.lower() or "Low-trust" in r.title
        ]
        assert low_trust_recs

    def test_low_trust_rec_mentions_entity_count(self):
        """Low-trust recommendation description must mention the count of affected entities."""
        ocr_geo = TextGeometry.for_provenance(TextProvenance.RASTER_OCR_TEXT)
        entities = [_text(f"T{i}", f"LABEL {i}", text_geometry=ocr_geo) for i in range(2)]
        ctx = _context(entities)
        result = LayoutRecommender().recommend(ctx, "check labels")
        low_trust_recs = [r for r in result.recommendations if "low-trust" in r.title.lower()]
        assert low_trust_recs
        assert "2" in low_trust_recs[0].description

    def test_native_text_does_not_trigger_low_trust_rec(self):
        """High-trust native CAD text must NOT produce a low-trust recommendation."""
        native_geo = TextGeometry.for_provenance(TextProvenance.NATIVE_CAD_TEXT)
        entities = [_text("T1", "NOTE A", text_geometry=native_geo)]
        ctx = _context(entities)
        result = LayoutRecommender().recommend(ctx, "check labels")
        low_trust_recs = [r for r in result.recommendations if "low-trust" in r.title.lower()]
        assert low_trust_recs == []

    def test_low_trust_confidence_is_0_60(self):
        """Low-trust recommendation must have base confidence 0.60 (no sparse penalty)."""
        # Supply enough native text (3+) so sparse penalty doesn't apply
        native_geo = TextGeometry.for_provenance(TextProvenance.NATIVE_CAD_TEXT)
        ocr_geo = TextGeometry.for_provenance(TextProvenance.RASTER_OCR_TEXT)
        entities = [
            _text("N1", "LABEL A", text_geometry=native_geo),
            _text("N2", "LABEL B", text_geometry=native_geo),
            _text("N3", "LABEL C", text_geometry=native_geo),
            _text("OCR1", "FUZZY", text_geometry=ocr_geo),
        ]
        ctx = _context(entities)
        result = LayoutRecommender().recommend(ctx, "check labels")
        low_trust_recs = [r for r in result.recommendations if "low-trust" in r.title.lower()]
        assert low_trust_recs
        assert low_trust_recs[0].confidence == pytest.approx(0.60)


class TestAnalyzeLayerDistributionDescription:
    """Kill mutations on _analyze_layer_distribution description string content."""

    def test_concentrated_layer_description_includes_count(self):
        """Description string must contain the entity count on that layer."""
        entities = [_entity(f"E{i}", layer="BEAMS") for i in range(12)]
        ctx = _context(entities)
        result = LayoutRecommender().recommend(ctx, "check")
        beams_recs = [r for r in result.recommendations if "BEAMS" in r.title]
        assert beams_recs
        # 12 of 12 are on BEAMS — description should mention "12 of 12"
        assert "12" in beams_recs[0].description

    def test_concentrated_layer_description_includes_total(self):
        """Description string must contain the total entity count."""
        entities = [_entity(f"E{i}", layer="WALLS") for i in range(11)]
        ctx = _context(entities)
        result = LayoutRecommender().recommend(ctx, "check")
        walls_recs = [r for r in result.recommendations if "WALLS" in r.title]
        assert walls_recs
        assert "11" in walls_recs[0].description

    def test_concentrated_layer_description_includes_percentage(self):
        """Description must contain a percentage sign (formatted ratio)."""
        entities = [_entity(f"E{i}", layer="SLAB") for i in range(15)]
        ctx = _context(entities)
        result = LayoutRecommender().recommend(ctx, "check")
        slab_recs = [r for r in result.recommendations if "SLAB" in r.title]
        assert slab_recs
        assert "%" in slab_recs[0].description

    def test_concentrated_layer_rec_confidence_is_0_85(self):
        """Layer concentration recommendation base confidence must be 0.85."""
        # Supply 3+ text entities so no sparse penalty applies
        native_geo = TextGeometry.for_provenance(TextProvenance.NATIVE_CAD_TEXT)
        text_e = [_text(f"T{i}", f"L{i}", text_geometry=native_geo) for i in range(3)]
        line_e = [_entity(f"L{i}", layer="BEAMS") for i in range(12)]
        ctx = _context(text_e + line_e)
        result = LayoutRecommender().recommend(ctx, "check")
        beams_recs = [r for r in result.recommendations if "BEAMS" in r.title]
        assert beams_recs
        assert beams_recs[0].confidence == pytest.approx(0.85)


class TestBuildSummaryEntityTypes:
    """Kill mutations on _build_summary entity type listing."""

    def test_summary_includes_entity_type_names(self):
        """Summary must list the most-common entity types."""
        entities = [_entity(f"L{i}", entity_type=EntityType.LINE) for i in range(5)] + [
            _entity(f"P{i}", entity_type=EntityType.LWPOLYLINE) for i in range(3)
        ]
        ctx = _context(entities)
        result = LayoutRecommender().recommend(ctx, "check")
        # "line" and "lwpolyline" (or at least one) should appear in drawing_summary
        summary = result.drawing_summary.lower()
        assert "line" in summary or "lwpolyline" in summary

    def test_summary_format_is_semicolon_separated(self):
        """Drawing summary uses '; ' as separator between parts."""
        entities = [
            _entity("L1", entity_type=EntityType.LINE),
            _entity("L2", entity_type=EntityType.LINE),
        ]
        ctx = _context(entities)
        result = LayoutRecommender().recommend(ctx, "check")
        # Summary format: "N entities across M layers; count etype"
        assert "; " in result.drawing_summary

    def test_summary_starts_with_entity_count(self):
        """First part of summary is 'N entities across M layers'."""
        entities = [_entity(f"E{i}", layer="WALLS") for i in range(7)]
        ctx = _context(entities)
        result = LayoutRecommender().recommend(ctx, "check")
        assert result.drawing_summary.startswith("7 entities across")


class TestScopeBuilderSectionContentAndConfidence:
    """Kill mutations on ScopeBuilder: section content keys and confidence computation."""

    def test_section_content_is_dict(self):
        """Each section's content must be a dict (not None or wrong type)."""
        entities = [_insert(f"B{i}", block_name="COL", x=float(i * 10)) for i in range(4)]
        ctx = _context(entities)
        result = ScopeBuilder().build(ctx, "scope")
        for section in result.sections:
            assert isinstance(section.content, dict)

    def test_layout_section_content_has_recommendations_key(self):
        """LAYOUT_RECOMMENDATIONS section content must have 'recommendations' key."""
        # Use many entities on one layer to trigger a layout recommendation
        entities = [_entity(f"E{i}", layer="WALLS") for i in range(12)]
        ctx = _context(entities)
        result = ScopeBuilder().build(ctx, "scope")
        layout_sections = [
            s for s in result.sections if s.section_type == ScopeSectionType.LAYOUT_RECOMMENDATIONS
        ]
        assert layout_sections
        assert "recommendations" in layout_sections[0].content

    def test_takeoff_section_content_has_items_key(self):
        """TAKEOFF_CANDIDATES section content must have 'items' key."""
        entities = [_insert(f"B{i}", block_name="FOOTING", x=float(i * 10)) for i in range(3)]
        ctx = _context(entities)
        result = ScopeBuilder().build(ctx, "scope")
        takeoff_sections = [
            s for s in result.sections if s.section_type == ScopeSectionType.TAKEOFF_CANDIDATES
        ]
        assert takeoff_sections
        assert "items" in takeoff_sections[0].content

    def test_aggregate_confidence_equals_min_of_section_confidences(self):
        """aggregate_confidence must equal the minimum of all section confidences."""
        entities = [_insert(f"B{i}", block_name="DOOR", x=float(i * 5)) for i in range(4)]
        ctx = _context(entities)
        result = ScopeBuilder().build(ctx, "scope")
        if result.sections:
            expected_min = min(s.confidence for s in result.sections if s.available)
            assert result.aggregate_confidence == pytest.approx(expected_min, abs=0.01)

    def test_revision_section_confidence_defaults_to_0_5_when_no_changes(self):
        """With zero key_changes, revision section confidence defaults to 0.5."""
        entities = [_entity("E1", layer="WALLS")]
        ctx = _context(entities)
        # Empty changeset → no key_changes → min(..., default=0.5) == 0.5
        cs = ChangeSet(operations=[], prompt="nothing")
        result = ScopeBuilder().build(ctx, "scope", changeset=cs)
        rev_sections = [
            s for s in result.sections if s.section_type == ScopeSectionType.REVISION_SUMMARY
        ]
        assert rev_sections
        assert rev_sections[0].confidence == pytest.approx(0.5)


# ---------------------------------------------------------------------------
# NEW MUTATION-KILLING TESTS — targeting the 191 surviving mutants
# ---------------------------------------------------------------------------

# ===========================================================================
# ScopeBuilder.build — propagation of prompt, region, confidence, caveats
# ===========================================================================


class TestScopeBuilderPropagation:
    """Kill argument-swapping/removal mutants and field-omission mutants in ScopeBuilder.build."""

    def test_region_propagates_partial_region_flag_into_scope(self):
        """partial_region ambiguity flag from LayoutRecommender must reach the scope summary."""
        entities = [_insert(f"B{i}", block_name="COL", x=float(i * 5)) for i in range(3)]
        ctx = _context(entities)
        region = RegionContext(entities=entities, is_whole_drawing=False, ambiguity_flags=[])
        result = ScopeBuilder().build(ctx, "scope", region=region)
        assert "partial_region" in result.ambiguity_flags

    def test_region_context_truncated_flag_propagates_into_scope(self):
        """context_truncated from a region ambiguity_flags must appear in scope ambiguity_flags."""
        entities = [_insert(f"B{i}", block_name="COL", x=float(i * 5)) for i in range(3)]
        ctx = _context(entities)
        region = RegionContext(
            entities=entities,
            is_whole_drawing=False,
            ambiguity_flags=["context_truncated"],
        )
        result = ScopeBuilder().build(ctx, "scope", region=region)
        assert "context_truncated" in result.ambiguity_flags

    def test_layout_section_confidence_equals_layout_result_aggregate(self):
        """LAYOUT_RECOMMENDATIONS confidence must equal aggregate_confidence."""
        # Many entities concentrated on one layer → triggers recommendation with known confidence
        entities = [_entity(f"E{i}", layer="WALLS") for i in range(12)]
        ctx = _context(entities)
        # Compute expected confidence independently
        layout_result = LayoutRecommender().recommend(ctx, "scope")
        result = ScopeBuilder().build(ctx, "scope")
        layout_sections = [
            s for s in result.sections if s.section_type == ScopeSectionType.LAYOUT_RECOMMENDATIONS
        ]
        assert layout_sections
        assert layout_sections[0].confidence == pytest.approx(
            layout_result.aggregate_confidence, abs=0.01
        )

    def test_layout_section_caveats_equal_layout_limitations(self):
        """LAYOUT_RECOMMENDATIONS section.caveats must equal layout_result.limitations."""
        entities = [_entity(f"E{i}", layer="WALLS") for i in range(12)]
        ctx = _context(entities)
        layout_result = LayoutRecommender().recommend(ctx, "scope")
        result = ScopeBuilder().build(ctx, "scope")
        layout_sections = [
            s for s in result.sections if s.section_type == ScopeSectionType.LAYOUT_RECOMMENDATIONS
        ]
        assert layout_sections
        assert layout_sections[0].caveats == layout_result.limitations

    def test_revision_summary_caveats_propagate_to_scope_all_caveats(self):
        """Caveats from revision summary must appear in the scope's top-level caveats."""
        entities = [_insert("B1", block_name="COL", x=0.0)]
        ctx = _context(entities)
        cr = _comparison_result(
            _change(ChangeCategory.ADDED, handle="A1"),
            warnings=["Profile filtered some entities."],
        )
        result = ScopeBuilder().build(ctx, "scope", comparison_result=cr)
        assert any("filtered" in c for c in result.caveats)

    def test_takeoff_caveats_propagate_to_scope_all_caveats(self):
        """Caveats from takeoff result must appear in the scope's top-level caveats."""
        entities = [_insert(f"B{i}", block_name="COL", x=float(i * 5)) for i in range(3)]
        ctx = _context(entities)
        region = RegionContext(entities=entities, is_whole_drawing=False, ambiguity_flags=[])
        result = ScopeBuilder().build(ctx, "scope", region=region)
        # partial-region takeoff generates "Counts are from the selected region only..." caveat
        assert any("selected region" in c for c in result.caveats)

    def test_takeoff_section_confidence_maps_high_to_0_95(self):
        """TakeoffConfidence.HIGH must map to 0.95 in the section confidence."""
        entities = [_insert(f"B{i}", block_name="COL", x=float(i * 5)) for i in range(3)]
        ctx = _context(entities)
        result = ScopeBuilder().build(ctx, "scope")
        takeoff_sections = [
            s for s in result.sections if s.section_type == ScopeSectionType.TAKEOFF_CANDIDATES
        ]
        assert takeoff_sections
        assert takeoff_sections[0].confidence == pytest.approx(0.95)

    def test_scope_aggregate_confidence_is_rounded_to_2dp(self):
        """aggregate_confidence must be rounded to 2 decimal places."""
        entities = [_entity(f"E{i}", layer="WALLS") for i in range(12)]
        ctx = _context(entities)
        result = ScopeBuilder().build(ctx, "scope")
        # round(x, 2) should equal the value (i.e. no unrounded floating point artifact)
        assert result.aggregate_confidence == round(result.aggregate_confidence, 2)

    def test_no_revision_data_appends_revision_summary_to_omitted(self):
        """Without revision data, 'revision_summary' must be in omitted_sections."""
        ctx = _context([_entity("E1", layer="WALLS")])
        result = ScopeBuilder().build(ctx, "scope")
        assert "revision_summary" in result.omitted_sections

    def test_empty_drawing_all_three_sections_omitted(self):
        """Empty drawing with no revision data must omit all three sections."""
        result = ScopeBuilder().build(_context([]), "scope")
        assert "layout_recommendations" in result.omitted_sections
        assert "revision_summary" in result.omitted_sections
        assert "takeoff_candidates" in result.omitted_sections

    def test_layout_section_title_is_layout_recommendations(self):
        """LAYOUT_RECOMMENDATIONS section title must be exactly 'Layout Recommendations'."""
        entities = [_entity(f"E{i}", layer="WALLS") for i in range(12)]
        ctx = _context(entities)
        result = ScopeBuilder().build(ctx, "scope")
        layout_sections = [
            s for s in result.sections if s.section_type == ScopeSectionType.LAYOUT_RECOMMENDATIONS
        ]
        assert layout_sections
        assert layout_sections[0].title == "Layout Recommendations"

    def test_revision_section_title_is_revision_summary(self):
        """REVISION_SUMMARY section title must be exactly 'Revision Summary'."""
        ctx = _context([_entity("E1", layer="WALLS")])
        op = EditOperation(
            op_type=OpType.MOVE_ENTITY,
            target_handle="E1",
            target_layer="WALLS",
        )
        cs = ChangeSet(operations=[op], prompt="move")
        result = ScopeBuilder().build(ctx, "scope", changeset=cs)
        rev_sections = [
            s for s in result.sections if s.section_type == ScopeSectionType.REVISION_SUMMARY
        ]
        assert rev_sections
        assert rev_sections[0].title == "Revision Summary"

    def test_takeoff_section_title_is_takeoff_candidates(self):
        """TAKEOFF_CANDIDATES section title must be exactly 'Takeoff Candidates'."""
        entities = [_insert(f"B{i}", block_name="COL", x=float(i * 5)) for i in range(3)]
        ctx = _context(entities)
        result = ScopeBuilder().build(ctx, "scope")
        takeoff_sections = [
            s for s in result.sections if s.section_type == ScopeSectionType.TAKEOFF_CANDIDATES
        ]
        assert takeoff_sections
        assert takeoff_sections[0].title == "Takeoff Candidates"

    def test_scope_aggregate_conf_is_min_of_sections(self):
        """aggregate_confidence must be the minimum of all section confidences."""
        # Build a scope with layout + takeoff sections and verify min is used
        entities = [_entity(f"E{i}", layer="WALLS") for i in range(12)]
        ctx = _context(entities)
        result = ScopeBuilder().build(ctx, "scope")
        if result.sections:
            expected = min(s.confidence for s in result.sections if s.available)
            assert result.aggregate_confidence == pytest.approx(expected, abs=0.01)

    def test_region_entities_used_not_context_entities(self):
        """When region is provided, entities come from region not context."""
        # Context has 20 entities (all on WALLS, concentrated)
        ctx_entities = [_entity(f"E{i}", layer="WALLS") for i in range(20)]
        ctx = _context(ctx_entities)
        # Region has only 2 entities (no concentration → no layout rec)
        region_entities = [
            _entity("R1", layer="ZONE_A"),
            _entity("R2", layer="ZONE_B"),
        ]
        region = RegionContext(entities=region_entities, is_whole_drawing=False, ambiguity_flags=[])
        result = ScopeBuilder().build(ctx, "scope", region=region)
        # If region is used, summary should mention 2 entities (region), not 20 (context)
        layout_sections = [
            s for s in result.sections if s.section_type == ScopeSectionType.LAYOUT_RECOMMENDATIONS
        ]
        # Layout result drawing_summary reflects region entity count (2)
        if layout_sections:
            assert "2" in layout_sections[0].content.get("drawing_summary", "")


# ===========================================================================
# LayoutRecommender.recommend — exact string content of empty-drawing result
# ===========================================================================


class TestLayoutRecommenderEmptyDrawingExactStrings:
    """Kill string-mutation survivors in the empty-drawing early return."""

    def test_empty_drawing_summary_exact_string(self):
        """drawing_summary for empty drawing must be the exact no-entities string."""
        result = LayoutRecommender().recommend(_context([]), "prompt")
        assert result.drawing_summary == "Empty drawing — no entities to analyze."

    def test_empty_drawing_ambiguity_flag_exact_value(self):
        """ambiguity_flags for empty drawing must be exactly ['empty_drawing']."""
        result = LayoutRecommender().recommend(_context([]), "prompt")
        assert result.ambiguity_flags == ["empty_drawing"]

    def test_empty_drawing_limitations_exact_string(self):
        """limitations for empty drawing must contain 'No entities available for analysis.'."""
        result = LayoutRecommender().recommend(_context([]), "prompt")
        assert result.limitations == ["No entities available for analysis."]


# ===========================================================================
# LayoutRecommender._analyze_layer_distribution — exact string content
# ===========================================================================


class TestLayerDistributionExactStrings:
    """Kill string-mutation survivors in _analyze_layer_distribution."""

    def test_layer_title_exact_format(self):
        """Title must be exactly \"High entity concentration on layer 'WALLS'\"."""
        entities = [_entity(f"E{i}", layer="WALLS") for i in range(12)]
        ctx = _context(entities)
        result = LayoutRecommender().recommend(ctx, "check")
        recs = [r for r in result.recommendations if "WALLS" in r.title]
        assert recs
        assert recs[0].title == "High entity concentration on layer 'WALLS'"

    def test_layer_description_exact_format(self):
        """Description must follow exact template with count, total, ratio, and sub-layer advice."""
        entities = [_entity(f"E{i}", layer="BEAMS") for i in range(12)]
        ctx = _context(entities)
        result = LayoutRecommender().recommend(ctx, "check")
        recs = [r for r in result.recommendations if "BEAMS" in r.title]
        assert recs
        assert recs[0].description == (
            "Layer 'BEAMS' contains 12 of 12 entities (100%). Consider splitting into sub-layers."
        )

    def test_layer_rationale_exact_string(self):
        """Rationale must be 'Concentrated layers can be harder to manage and filter.'."""
        entities = [_entity(f"E{i}", layer="COLS") for i in range(12)]
        ctx = _context(entities)
        result = LayoutRecommender().recommend(ctx, "check")
        recs = [r for r in result.recommendations if "COLS" in r.title]
        assert recs
        assert recs[0].rationale == "Concentrated layers can be harder to manage and filter."

    def test_layer_ratio_threshold_boundary_above(self):
        """With ratio > 0.6 and total > 10, recommendation must fire."""
        # 7 of 10 on HEAVY → 70% > 60%, but total=10 which is NOT > 10 → no trigger
        # Use 11 total, 8 on HEAVY → 72.7% > 60%, total=11 > 10 → triggers
        heavy = [_entity(f"H{i}", layer="HEAVY") for i in range(8)]
        light = [_entity(f"L{i}", layer="LIGHT") for i in range(3)]
        ctx = _context(heavy + light)
        result = LayoutRecommender().recommend(ctx, "check")
        recs = [r for r in result.recommendations if "HEAVY" in r.title]
        assert recs, "8/11 entities on HEAVY (73%) with total>10 must trigger recommendation"

    def test_layer_ratio_threshold_exactly_60_percent_no_trigger(self):
        """Exactly 60% on one layer must NOT trigger the recommendation (> 0.6, not >= 0.6)."""
        # 6 of 10 on LAYER_A = 60%, but total=10 is not > 10 either
        # Need total > 10: 12 on LAYER_A, 8 on LAYER_B = 12/20 = 60% exactly
        layer_a = [_entity(f"A{i}", layer="LAYER_A") for i in range(12)]
        layer_b = [_entity(f"B{i}", layer="LAYER_B") for i in range(8)]
        ctx = _context(layer_a + layer_b)
        result = LayoutRecommender().recommend(ctx, "check")
        recs = [r for r in result.recommendations if "LAYER_A" in r.title]
        # 60% is NOT > 0.6 → no recommendation
        assert recs == []

    def test_layer_total_threshold_exactly_10_no_trigger(self):
        """Total == 10 must NOT trigger the recommendation (needs > 10, not >= 10)."""
        # 9 of 10 on WALLS = 90% > 60%, but total=10 is not > 10
        entities = [_entity(f"W{i}", layer="WALLS") for i in range(9)] + [
            _entity("X1", layer="OTHER")
        ]
        ctx = _context(entities)
        result = LayoutRecommender().recommend(ctx, "check")
        recs = [r for r in result.recommendations if "WALLS" in r.title]
        assert recs == []

    def test_layer_only_most_concentrated_layer_reported(self):
        """Only the single most-concentrated layer is reported (break after first match)."""
        # It is mathematically impossible for two layers to each have >60% of the total.
        # The break ensures we never report more than one layer concentration rec.
        # Set up: ALPHA has 8/11 = 73%, BETA has 3/11 = 27%.  Both total > 10.
        # Only ALPHA fires.
        layer_a = [_entity(f"A{i}", layer="ALPHA") for i in range(8)]
        layer_b = [_entity(f"B{i}", layer="BETA") for i in range(3)]
        ctx = _context(layer_a + layer_b)
        result = LayoutRecommender().recommend(ctx, "check")
        layer_recs = [
            r
            for r in result.recommendations
            if r.type.value == "general_observation" and "concentration" in r.title.lower()
        ]
        # Exactly one layer concentration rec should be emitted
        assert len(layer_recs) == 1
        assert "ALPHA" in layer_recs[0].title

    def test_layer_description_partial_ratio(self):
        """Description with non-100% ratio must show correct percentage."""
        # 8 of 11 total → 72.7% rounds to 73%
        heavy = [_entity(f"H{i}", layer="STEEL") for i in range(8)]
        light = [_entity(f"L{i}", layer="OTHER") for i in range(3)]
        ctx = _context(heavy + light)
        result = LayoutRecommender().recommend(ctx, "check")
        recs = [r for r in result.recommendations if "STEEL" in r.title]
        assert recs
        assert "73%" in recs[0].description


# ===========================================================================
# LayoutRecommender._analyze_density — exact string content
# ===========================================================================


class TestDensityExactStrings:
    """Kill string-mutation survivors in _analyze_density."""

    def test_density_title_exact_string(self):
        """Title must be exactly 'High entity density detected'."""
        entities = [_entity(f"E{i}", x=float(i * 0.1), y=0.0) for i in range(5)]
        ctx = _context(entities)
        result = LayoutRecommender().recommend(ctx, "check")
        placement_recs = [r for r in result.recommendations if r.type.value == "placement_guidance"]
        assert placement_recs
        assert placement_recs[0].title == "High entity density detected"

    def test_density_description_contains_area_range(self):
        """Description must contain 'across NxM area' part."""
        # 5 entities spread along x-axis, y=0 → x_range=0.8, y_range=0
        entities = [_entity(f"E{i}", x=float(i * 0.2), y=0.0) for i in range(5)]
        ctx = _context(entities)
        result = LayoutRecommender().recommend(ctx, "check")
        placement_recs = [r for r in result.recommendations if r.type.value == "placement_guidance"]
        assert placement_recs
        desc = placement_recs[0].description
        assert "across" in desc
        assert "area" in desc

    def test_density_description_contains_unit_sq(self):
        """Description must contain the '/unit²' unicode suffix."""
        entities = [_entity(f"E{i}", x=float(i * 0.1), y=0.0) for i in range(5)]
        ctx = _context(entities)
        result = LayoutRecommender().recommend(ctx, "check")
        placement_recs = [r for r in result.recommendations if r.type.value == "placement_guidance"]
        assert placement_recs
        assert "/unit\u00b2" in placement_recs[0].description

    def test_density_rationale_exact_string(self):
        """Rationale must be 'Dense areas may benefit from spacing adjustments.'."""
        entities = [_entity(f"E{i}", x=float(i * 0.1), y=0.0) for i in range(5)]
        ctx = _context(entities)
        result = LayoutRecommender().recommend(ctx, "check")
        placement_recs = [r for r in result.recommendations if r.type.value == "placement_guidance"]
        assert placement_recs
        assert placement_recs[0].rationale == "Dense areas may benefit from spacing adjustments."

    def test_density_threshold_boundary_just_above(self):
        """density just above 0.1 must trigger the recommendation."""
        # 5 entities at x=[0,1,2,3,4], y=[0,1,2,3,4] → area=16, density=5/16=0.3125 > 0.1
        entities = [_entity(f"E{i}", x=float(i), y=float(i)) for i in range(5)]
        ctx = _context(entities)
        result = LayoutRecommender().recommend(ctx, "check")
        placement_recs = [r for r in result.recommendations if r.type.value == "placement_guidance"]
        assert placement_recs, "density 0.31 must trigger recommendation"

    def test_density_threshold_boundary_just_below(self):
        """density just below 0.1 must NOT trigger the recommendation."""
        # 5 entities spread 100 units apart → x_range=400, y_range=0, area=max(1)=1
        # Wait — y_range=0 makes area = max(0,1)=1, density=5/1=5 >> 0.1
        # Need 2D spread: x_range=100, y_range=100, area=10000, density=5/10000=0.0005 < 0.1
        entities = [_entity(f"E{i}", x=float(i * 25), y=float(i * 25)) for i in range(5)]
        ctx = _context(entities)
        result = LayoutRecommender().recommend(ctx, "check")
        placement_recs = [r for r in result.recommendations if r.type.value == "placement_guidance"]
        assert placement_recs == [], "density 0.0005 must NOT trigger recommendation"

    def test_density_description_uses_three_decimal_places(self):
        """Density value in description must be formatted to 3 decimal places."""
        entities = [_entity(f"E{i}", x=float(i * 0.1), y=0.0) for i in range(6)]
        ctx = _context(entities)
        result = LayoutRecommender().recommend(ctx, "check")
        placement_recs = [r for r in result.recommendations if r.type.value == "placement_guidance"]
        assert placement_recs
        # Pattern: "density: X.XXX/unit²"
        assert "density: " in placement_recs[0].description
        # Verify three decimal places (e.g. 6.000 not 6.0 or 6)
        import re

        m = re.search(r"density: (\d+\.\d+)", placement_recs[0].description)
        assert m is not None
        decimal_part = m.group(1).split(".")[1]
        assert len(decimal_part) == 3


# ===========================================================================
# LayoutRecommender._analyze_block_placement — exact string content
# ===========================================================================


class TestBlockPlacementExactStrings:
    """Kill string-mutation survivors in _analyze_block_placement."""

    def test_block_title_exact_format(self):
        """Title must be exactly \"Repeated block 'DOOR_A' (4 instances)\"."""
        entities = [_insert(f"B{i}", block_name="DOOR_A", x=float(i * 5)) for i in range(4)]
        ctx = _context(entities)
        result = LayoutRecommender().recommend(ctx, "check")
        recs = [r for r in result.recommendations if "DOOR_A" in r.title]
        assert recs
        assert recs[0].title == "Repeated block 'DOOR_A' (4 instances)"

    def test_block_description_exact_format(self):
        """Description must follow exact block-placement template."""
        entities = [_insert(f"C{i}", block_name="COL_MK", x=float(i * 10)) for i in range(5)]
        ctx = _context(entities)
        result = LayoutRecommender().recommend(ctx, "check")
        recs = [r for r in result.recommendations if "COL_MK" in r.title]
        assert recs
        assert recs[0].description == (
            "Block 'COL_MK' appears 5 times. Placement pattern analysis available."
        )

    def test_block_rationale_exact_string(self):
        """Rationale must be 'Repeated blocks often indicate structural grid or fixture.'."""
        entities = [_insert(f"B{i}", block_name="FOOTING", x=float(i * 5)) for i in range(3)]
        ctx = _context(entities)
        result = LayoutRecommender().recommend(ctx, "check")
        recs = [r for r in result.recommendations if "FOOTING" in r.title]
        assert recs
        assert recs[0].rationale == "Repeated blocks often indicate structural grid or fixture."

    def test_block_confidence_is_0_90(self):
        """Block placement recommendation confidence must be 0.90 (before sparse-text penalty)."""
        native = TextGeometry.for_provenance(TextProvenance.NATIVE_CAD_TEXT)
        text_entities = [_text(f"T{i}", f"Label {i}", text_geometry=native) for i in range(3)]
        inserts = [_insert(f"B{i}", block_name="SLAB", x=float(i * 5)) for i in range(4)]
        ctx = _context(text_entities + inserts)
        result = LayoutRecommender().recommend(ctx, "check")
        recs = [r for r in result.recommendations if "SLAB" in r.title]
        assert recs
        assert recs[0].confidence == pytest.approx(0.90)

    def test_block_threshold_exactly_two_no_recommendation(self):
        """Block appearing exactly twice must NOT trigger a recommendation (threshold is >= 3)."""
        entities = [_insert("B1", block_name="RARE"), _insert("B2", block_name="RARE", x=5.0)]
        ctx = _context(entities)
        result = LayoutRecommender().recommend(ctx, "check")
        recs = [r for r in result.recommendations if "RARE" in r.title]
        assert recs == []

    def test_block_threshold_exactly_three_triggers(self):
        """Block appearing exactly 3 times must trigger a recommendation (>= 3)."""
        entities = [
            _insert("B1", block_name="BEAM", x=0.0),
            _insert("B2", block_name="BEAM", x=5.0),
            _insert("B3", block_name="BEAM", x=10.0),
        ]
        ctx = _context(entities)
        result = LayoutRecommender().recommend(ctx, "check")
        recs = [r for r in result.recommendations if "BEAM" in r.title]
        assert recs, "Exactly 3 instances of BEAM must trigger recommendation"

    def test_block_most_common_three_blocks_reported(self):
        """At most 3 blocks are reported (most_common(3) in source)."""
        # 4 different blocks each appearing >= 3 times
        entities = []
        for block_name, count in [("A", 5), ("B", 4), ("C", 3), ("D", 3)]:
            entities.extend(
                [
                    _insert(f"{block_name}{i}", block_name=block_name, x=float(i))
                    for i in range(count)
                ]
            )
        ctx = _context(entities)
        result = LayoutRecommender().recommend(ctx, "check")
        block_recs = [r for r in result.recommendations if r.type.value == "region_usage"]
        assert len(block_recs) <= 3


# ===========================================================================
# LayoutRecommender._analyze_text_labels — exact string content
# ===========================================================================


class TestTextLabelsExactStrings:
    """Kill string-mutation survivors in _analyze_text_labels."""

    def test_low_trust_title_exact_format(self):
        """Title must be exactly 'Low-trust text detected (N entities)'."""
        ocr_geo = TextGeometry.for_provenance(TextProvenance.RASTER_OCR_TEXT)
        native = TextGeometry.for_provenance(TextProvenance.NATIVE_CAD_TEXT)
        entities = [
            _text("T1", "LABEL", text_geometry=ocr_geo),
            _text("N1", "NATIVE", text_geometry=native),
            _text("N2", "NATIVE2", text_geometry=native),
            _text("N3", "NATIVE3", text_geometry=native),
        ]
        ctx = _context(entities)
        result = LayoutRecommender().recommend(ctx, "check")
        recs = [r for r in result.recommendations if "low-trust" in r.title.lower()]
        assert recs
        assert recs[0].title == "Low-trust text detected (1 entities)"

    def test_low_trust_description_exact_format(self):
        """Description must follow exact template with OCR or vector-outline mention."""
        native = TextGeometry.for_provenance(TextProvenance.NATIVE_CAD_TEXT)
        ocr_geo = TextGeometry.for_provenance(TextProvenance.RASTER_OCR_TEXT)
        entities = [
            _text("T1", "OCR1", text_geometry=ocr_geo),
            _text("T2", "OCR2", text_geometry=ocr_geo),
            _text("N1", "NATIVE1", text_geometry=native),
            _text("N2", "NATIVE2", text_geometry=native),
            _text("N3", "NATIVE3", text_geometry=native),
        ]
        ctx = _context(entities)
        result = LayoutRecommender().recommend(ctx, "check")
        recs = [r for r in result.recommendations if "low-trust" in r.title.lower()]
        assert recs
        assert recs[0].description == (
            "2 text entities have OCR or vector-outline provenance. Labels may be inaccurate."
        )

    def test_low_trust_rationale_exact_string(self):
        """Rationale must be 'OCR-derived text has lower confidence for identification.'."""
        ocr_geo = TextGeometry.for_provenance(TextProvenance.RASTER_OCR_TEXT)
        native = TextGeometry.for_provenance(TextProvenance.NATIVE_CAD_TEXT)
        entities = [
            _text("T1", "LABEL", text_geometry=ocr_geo),
            _text("N1", "N", text_geometry=native),
            _text("N2", "N2", text_geometry=native),
            _text("N3", "N3", text_geometry=native),
        ]
        ctx = _context(entities)
        result = LayoutRecommender().recommend(ctx, "check")
        recs = [r for r in result.recommendations if "low-trust" in r.title.lower()]
        assert recs
        assert recs[0].rationale == "OCR-derived text has lower confidence for identification."

    def test_low_trust_caveat_exact_string(self):
        """Caveats must contain exact message about text content accuracy."""
        ocr_geo = TextGeometry.for_provenance(TextProvenance.RASTER_OCR_TEXT)
        native = TextGeometry.for_provenance(TextProvenance.NATIVE_CAD_TEXT)
        entities = [
            _text("T1", "LABEL", text_geometry=ocr_geo),
            _text("N1", "N", text_geometry=native),
            _text("N2", "N2", text_geometry=native),
            _text("N3", "N3", text_geometry=native),
        ]
        ctx = _context(entities)
        result = LayoutRecommender().recommend(ctx, "check")
        recs = [r for r in result.recommendations if "low-trust" in r.title.lower()]
        assert recs
        assert "Text content may not exactly match the original drawing." in recs[0].caveats


# ===========================================================================
# LayoutRecommender._build_summary — exact format
# ===========================================================================


class TestBuildSummaryExactFormat:
    """Kill string-mutation survivors in _build_summary."""

    def test_summary_format_n_entities_across_m_layers(self):
        """First segment must be exactly 'N entities across M layers'."""
        entities = [_entity(f"L{i}", layer="A") for i in range(3)] + [
            _entity(f"M{i}", layer="B") for i in range(2)
        ]
        ctx = _context(entities)
        result = LayoutRecommender().recommend(ctx, "check")
        assert result.drawing_summary.startswith("5 entities across 2 layers")

    def test_summary_top3_entity_types_in_order(self):
        """Summary must list the top 3 entity types by count, separated by '; '."""
        entities = (
            [_entity(f"L{i}", entity_type=EntityType.LINE) for i in range(5)]
            + [_entity(f"P{i}", entity_type=EntityType.LWPOLYLINE) for i in range(3)]
            + [_entity(f"T{i}", entity_type=EntityType.TEXT) for i in range(2)]
            + [_entity(f"I{i}", entity_type=EntityType.INSERT) for i in range(1)]
        )
        ctx = _context(entities)
        result = LayoutRecommender().recommend(ctx, "check")
        summary = result.drawing_summary
        # Must include top 3: LINE(5), LWPOLYLINE(3), TEXT(2) — not INSERT(1)
        assert "5 LINE" in summary
        assert "3 LWPOLYLINE" in summary
        assert "2 TEXT" in summary
        assert "1 INSERT" not in summary

    def test_summary_single_layer(self):
        """With one layer, summary includes '1 layers'."""
        entities = [_entity(f"E{i}", layer="ONLY") for i in range(4)]
        ctx = _context(entities)
        result = LayoutRecommender().recommend(ctx, "check")
        assert "across 1 layers" in result.drawing_summary

    def test_summary_three_layers(self):
        """With three layers, summary includes '3 layers'."""
        entities = [
            _entity("E1", layer="A"),
            _entity("E2", layer="B"),
            _entity("E3", layer="C"),
        ]
        ctx = _context(entities)
        result = LayoutRecommender().recommend(ctx, "check")
        assert "across 3 layers" in result.drawing_summary


# ===========================================================================
# RevisionSummarizer._op_to_plain — exact template strings
# ===========================================================================


class TestOpToPlainExactTemplates:
    """Kill string-mutation survivors in _op_to_plain template values."""

    def test_move_entity_exact_base_string(self):
        """move_entity must produce exactly 'An element was repositioned'."""
        op = EditOperation(op_type=OpType.MOVE_ENTITY, target_handle="H1", target_layer="L1")
        cs = ChangeSet(operations=[op], prompt="test")
        result = RevisionSummarizer().summarize(changeset=cs)
        assert result.key_changes[0].plain_description == "An element was repositioned"

    def test_delete_entity_exact_base_string(self):
        """delete_entity must produce exactly 'An element was removed'."""
        op = EditOperation(op_type=OpType.DELETE_ENTITY, target_handle="H1", target_layer="L1")
        cs = ChangeSet(operations=[op], prompt="test")
        result = RevisionSummarizer().summarize(changeset=cs)
        assert result.key_changes[0].plain_description == "An element was removed"

    def test_edit_text_exact_base_string(self):
        """edit_text must produce exactly 'A text label was updated'."""
        op = EditOperation(op_type=OpType.EDIT_TEXT, target_handle="H1", target_layer="NOTES")
        cs = ChangeSet(operations=[op], prompt="test")
        result = RevisionSummarizer().summarize(changeset=cs)
        assert result.key_changes[0].plain_description == "A text label was updated"

    def test_add_block_exact_base_string(self):
        """add_block must produce exactly 'A new block was inserted'."""
        op = EditOperation(op_type=OpType.ADD_BLOCK, target_handle="H1", target_layer="L1")
        cs = ChangeSet(operations=[op], prompt="test")
        result = RevisionSummarizer().summarize(changeset=cs)
        assert result.key_changes[0].plain_description == "A new block was inserted"

    def test_unknown_op_type_uses_operation_prefix(self):
        """Unknown op type must produce 'Operation: <op_type>'."""
        op = EditOperation(op_type=OpType.ROTATE_ENTITY, target_handle="H1", target_layer="L1")
        cs = ChangeSet(operations=[op], prompt="test")
        result = RevisionSummarizer().summarize(changeset=cs)
        assert result.key_changes[0].plain_description.startswith("Operation:")

    def test_op_to_plain_with_context_uses_em_dash_separator(self):
        """With a context entity found, separator must be ' — ' (em dash with spaces)."""
        entity = _entity("H1", layer="STRUCTURAL", entity_type=EntityType.LINE)
        ctx = _context([entity])
        op = EditOperation(
            op_type=OpType.MOVE_ENTITY,
            target_handle="H1",
            target_layer="STRUCTURAL",
        )
        cs = ChangeSet(operations=[op], prompt="test")
        result = RevisionSummarizer().summarize(changeset=cs, context=ctx)
        desc = result.key_changes[0].plain_description
        assert " \u2014 " in desc


# ===========================================================================
# RevisionSummarizer._from_changeset — exact headline and overall_assessment
# ===========================================================================


class TestFromChangesetExactStrings:
    """Kill string-mutation survivors in _from_changeset."""

    def test_single_op_headline_exact(self):
        """Headline for 1 op must be exactly '1 planned operation(s).'."""
        op = EditOperation(op_type=OpType.MOVE_ENTITY, target_handle="H1", target_layer="L1")
        cs = ChangeSet(operations=[op], prompt="test")
        result = RevisionSummarizer().summarize(changeset=cs)
        assert result.headline == "1 planned operation(s)."

    def test_three_op_headline_exact(self):
        """Headline for 3 ops must be exactly '3 planned operation(s).'."""
        ops = [
            EditOperation(op_type=OpType.MOVE_ENTITY, target_handle=f"H{i}", target_layer="L1")
            for i in range(3)
        ]
        cs = ChangeSet(operations=ops, prompt="test")
        result = RevisionSummarizer().summarize(changeset=cs)
        assert result.headline == "3 planned operation(s)."

    def test_zero_ops_headline_exact(self):
        """Headline for 0 ops must be exactly 'No operations planned.'."""
        cs = ChangeSet(operations=[], prompt="nothing")
        result = RevisionSummarizer().summarize(changeset=cs)
        assert result.headline == "No operations planned."

    def test_overall_assessment_exact_format_with_ops(self):
        """overall_assessment must follow '{N} edit operation(s) from the change plan.'."""
        ops = [
            EditOperation(op_type=OpType.MOVE_ENTITY, target_handle=f"H{i}", target_layer="L1")
            for i in range(4)
        ]
        cs = ChangeSet(operations=ops, prompt="test")
        result = RevisionSummarizer().summarize(changeset=cs)
        assert result.overall_assessment == "4 edit operation(s) from the change plan."

    def test_overall_assessment_zero_ops_exact(self):
        """overall_assessment for 0 ops must be '0 edit operation(s) from the change plan.'."""
        cs = ChangeSet(operations=[], prompt="nothing")
        result = RevisionSummarizer().summarize(changeset=cs)
        assert result.overall_assessment == "0 edit operation(s) from the change plan."

    def test_change_count_matches_op_count_exactly(self):
        """change_count must equal the exact number of operations, not N+1 or N-1."""
        for n in [1, 2, 5, 10]:
            ops = [
                EditOperation(op_type=OpType.MOVE_ENTITY, target_handle=f"H{i}", target_layer="L1")
                for i in range(n)
            ]
            cs = ChangeSet(operations=ops, prompt="test")
            result = RevisionSummarizer().summarize(changeset=cs)
            assert result.change_count == n, f"Expected {n}, got {result.change_count}"


# ===========================================================================
# RevisionSummarizer._from_comparison — exact headline and total count
# ===========================================================================


class TestFromComparisonExactStrings:
    """Kill string-mutation survivors in _from_comparison."""

    def test_headline_format_with_total_and_breakdown(self):
        """Headline must follow 'N change(s) detected: X added, Y removed, ...'."""
        cr = _comparison_result(
            _change(ChangeCategory.ADDED, "A1"),
            _change(ChangeCategory.REMOVED, "R1"),
            _change(ChangeCategory.MODIFIED, "M1"),
        )
        result = RevisionSummarizer().summarize(comparison_result=cr)
        assert result.headline == "3 change(s) detected: 1 added, 1 removed, 1 modified"

    def test_headline_order_added_removed_modified_moved(self):
        """Headline parts must appear in order: added, removed, modified, moved."""
        cr = _comparison_result(
            _change(ChangeCategory.MOVED, "V1"),
            _change(ChangeCategory.ADDED, "A1"),
        )
        result = RevisionSummarizer().summarize(comparison_result=cr)
        headline = result.headline
        added_pos = headline.find("added")
        moved_pos = headline.find("moved")
        assert added_pos < moved_pos, "added must precede moved in headline"

    def test_unchanged_not_counted_in_total(self):
        """UNCHANGED changes must not increment the total in the headline."""
        cr = _comparison_result(
            _change(ChangeCategory.UNCHANGED, "U1"),
            _change(ChangeCategory.UNCHANGED, "U2"),
            _change(ChangeCategory.ADDED, "A1"),
        )
        result = RevisionSummarizer().summarize(comparison_result=cr)
        assert result.change_count == 1
        assert result.headline.startswith("1 change(s) detected")

    def test_text_preview_truncated_to_40_chars(self):
        """Text content preview must be truncated to 40 characters."""
        long_text = "X" * 50
        cr = _comparison_result(_change(ChangeCategory.ADDED, "A1", text_content=long_text))
        result = RevisionSummarizer().summarize(comparison_result=cr)
        desc = result.key_changes[0].plain_description
        # The preview should have 40 X's, not 50
        assert "X" * 40 in desc
        assert "X" * 50 not in desc

    def test_areas_affected_is_sorted(self):
        """areas_affected must be sorted alphabetically."""
        cr = _comparison_result(
            _change(ChangeCategory.ADDED, "A1", layer="ZONE_C"),
            _change(ChangeCategory.ADDED, "A2", layer="ZONE_A"),
            _change(ChangeCategory.ADDED, "A3", layer="ZONE_B"),
        )
        result = RevisionSummarizer().summarize(comparison_result=cr)
        assert result.areas_affected == ["ZONE_A", "ZONE_B", "ZONE_C"]

    def test_evidence_entity_type_set_correctly(self):
        """EvidenceRef entity_type must match the snapshot entity_type.value string."""
        snap = _snapshot(handle="EV1", entity_type=EntityType.LWPOLYLINE, layer="STRUCT")
        change = EntityChange(category=ChangeCategory.ADDED, revision_snapshot=snap, confidence=0.9)
        cr = _comparison_result(change)
        result = RevisionSummarizer().summarize(comparison_result=cr)
        evidence = result.key_changes[0].evidence
        assert evidence
        # entity_type.value for EntityType.LWPOLYLINE is "LWPOLYLINE"
        assert evidence[0].entity_type == EntityType.LWPOLYLINE.value

    def test_evidence_layer_matches_snapshot_layer(self):
        """EvidenceRef layer must match the snapshot layer."""
        snap = _snapshot(handle="EV2", layer="NOTES")
        change = EntityChange(category=ChangeCategory.ADDED, revision_snapshot=snap, confidence=0.9)
        cr = _comparison_result(change)
        result = RevisionSummarizer().summarize(comparison_result=cr)
        assert result.key_changes[0].evidence[0].layer == "NOTES"

    def test_no_evidence_when_snapshot_has_empty_handle(self):
        """When snapshot handle is empty string, evidence list must be empty."""
        snap = GeometrySnapshot(
            handle="",
            entity_type=EntityType.LINE,
            layer="STRUCTURAL",
            points=[Point2D(x=0, y=0)],
        )
        change = EntityChange(category=ChangeCategory.ADDED, revision_snapshot=snap, confidence=0.9)
        cr = _comparison_result(change)
        result = RevisionSummarizer().summarize(comparison_result=cr)
        # Empty handle is falsy → evidence must be empty
        assert result.key_changes[0].evidence == []

    def test_warnings_all_propagated_to_caveats(self):
        """All warnings from comparison result must appear verbatim in caveats."""
        warnings = ["Warning one.", "Warning two.", "Warning three."]
        cr = _comparison_result(_change(ChangeCategory.ADDED, "A1"), warnings=warnings)
        result = RevisionSummarizer().summarize(comparison_result=cr)
        for w in warnings:
            assert w in result.caveats


# ===========================================================================
# RevisionSummarizer._plain_description — exact template strings
# ===========================================================================


class TestPlainDescriptionExactTemplates:
    """Kill string-mutation survivors in _plain_description."""

    def test_added_entity_type_in_description(self):
        """The entity_type.value must appear in the description between 'A ' and ' was added'."""
        snap = _snapshot(handle="S1", entity_type=EntityType.LINE, layer="L1")
        change = EntityChange(category=ChangeCategory.ADDED, revision_snapshot=snap, confidence=0.9)
        cr = _comparison_result(change)
        result = RevisionSummarizer().summarize(comparison_result=cr)
        # entity_type.value is "LINE" (uppercase from StrEnum)
        assert result.key_changes[0].plain_description == "A LINE was added"

    def test_removed_entity_type_in_description(self):
        """Removed: description must be 'A <TYPE> was removed' (type is uppercase)."""
        snap = _snapshot(handle="S1", entity_type=EntityType.TEXT, layer="L1")
        change = EntityChange(category=ChangeCategory.REMOVED, master_snapshot=snap, confidence=0.9)
        cr = _comparison_result(change)
        result = RevisionSummarizer().summarize(comparison_result=cr)
        assert result.key_changes[0].plain_description == "A TEXT was removed"

    def test_modified_entity_type_in_description(self):
        """Modified: description must be 'A <TYPE> was modified' (type is uppercase)."""
        snap = _snapshot(handle="S1", entity_type=EntityType.MTEXT, layer="L1")
        change = EntityChange(
            category=ChangeCategory.MODIFIED, revision_snapshot=snap, confidence=0.9
        )
        cr = _comparison_result(change)
        result = RevisionSummarizer().summarize(comparison_result=cr)
        assert result.key_changes[0].plain_description == "A MTEXT was modified"

    def test_moved_description_says_repositioned_not_moved(self):
        """Moved category must use 'repositioned', NOT 'moved'."""
        snap = _snapshot(handle="S1", entity_type=EntityType.LINE, layer="L1")
        change = EntityChange(
            category=ChangeCategory.MOVED,
            revision_snapshot=snap,
            master_snapshot=snap,
            confidence=0.9,
        )
        cr = _comparison_result(change)
        result = RevisionSummarizer().summarize(comparison_result=cr)
        assert "repositioned" in result.key_changes[0].plain_description
        assert "moved" not in result.key_changes[0].plain_description.lower()

    def test_text_hint_truncated_exactly_40_chars(self):
        """Text preview must be exactly min(len(text), 40) characters in the hint."""
        text_42 = "A" * 42
        cr = _comparison_result(_change(ChangeCategory.ADDED, "A1", text_content=text_42))
        result = RevisionSummarizer().summarize(comparison_result=cr)
        desc = result.key_changes[0].plain_description
        assert "(" + "'" + "A" * 40 + "'" + ")" in desc

    def test_no_text_hint_when_text_content_is_none(self):
        """When text_content is None, description must not contain text hint."""
        cr = _comparison_result(_change(ChangeCategory.ADDED, "A1", text_content=None))
        result = RevisionSummarizer().summarize(comparison_result=cr)
        desc = result.key_changes[0].plain_description
        # No parenthetical hint expected
        assert "(" not in desc


# ===========================================================================
# RevisionSummarizer._technical_detail — exact displacement format
# ===========================================================================


class TestTechnicalDetailExactFormat:
    """Kill string-mutation survivors in _technical_detail."""

    def test_displacement_format_exact_template(self):
        """displacement must be formatted as 'displacement=(X.Y, Y.Y)' with 1dp."""
        snap = _snapshot(handle="MV1", entity_type=EntityType.LINE, layer="L1")
        change = EntityChange(
            category=ChangeCategory.MOVED,
            master_snapshot=snap,
            revision_snapshot=snap,
            displacement=Point2D(x=3.5, y=-7.2),
            confidence=0.9,
        )
        cr = _comparison_result(change)
        result = RevisionSummarizer().summarize(comparison_result=cr)
        tech = result.key_changes[0].technical_detail
        assert tech == "displacement=(3.5, -7.2)"

    def test_displacement_x_negative(self):
        """Negative x displacement must be represented with minus sign."""
        snap = _snapshot(handle="MV2", layer="L1")
        change = EntityChange(
            category=ChangeCategory.MOVED,
            master_snapshot=snap,
            revision_snapshot=snap,
            displacement=Point2D(x=-12.0, y=0.0),
            confidence=0.9,
        )
        cr = _comparison_result(change)
        result = RevisionSummarizer().summarize(comparison_result=cr)
        assert "-12.0" in result.key_changes[0].technical_detail

    def test_displacement_zero_values_formatted(self):
        """Zero displacement must render as '0.0' not '0'."""
        snap = _snapshot(handle="MV3", layer="L1")
        change = EntityChange(
            category=ChangeCategory.MOVED,
            master_snapshot=snap,
            revision_snapshot=snap,
            displacement=Point2D(x=0.0, y=0.0),
            confidence=0.9,
        )
        cr = _comparison_result(change)
        result = RevisionSummarizer().summarize(comparison_result=cr)
        tech = result.key_changes[0].technical_detail
        assert tech == "displacement=(0.0, 0.0)"

    def test_modifications_list_in_technical_detail(self):
        """When modifications are present, fields list must appear in technical_detail."""
        snap = _snapshot(handle="M1", layer="L1")
        change = EntityChange(
            category=ChangeCategory.MODIFIED,
            revision_snapshot=snap,
            modifications={"color": "red", "linetype": "DASHED"},
            confidence=0.9,
        )
        cr = _comparison_result(change)
        result = RevisionSummarizer().summarize(comparison_result=cr)
        tech = result.key_changes[0].technical_detail
        assert "fields=" in tech
        assert "color" in tech or "linetype" in tech


# ===========================================================================
# TakeoffGenerator._count_by_layer — exact item fields
# ===========================================================================


class TestCountByLayerExactFields:
    """Kill string-mutation survivors in _count_by_layer."""

    def test_layer_item_name_exact_format(self):
        """Item name must be exactly \"Entities on 'WALLS'\"."""
        entities = [
            _entity("L1", layer="WALLS", entity_type=EntityType.LINE),
            _entity("L2", layer="WALLS", entity_type=EntityType.LINE),
        ]
        ctx = _context(entities)
        result = TakeoffGenerator().generate(ctx, "count")
        items = [it for it in result.items if it.source_layer == "WALLS"]
        assert items
        assert items[0].name == "Entities on 'WALLS'"

    def test_layer_item_caveat_exact_string(self):
        """Layer item caveat must be exactly the layer-membership note."""
        entities = [
            _entity("L1", layer="SLAB", entity_type=EntityType.LWPOLYLINE),
            _entity("L2", layer="SLAB", entity_type=EntityType.LWPOLYLINE),
        ]
        ctx = _context(entities)
        result = TakeoffGenerator().generate(ctx, "count")
        items = [it for it in result.items if it.source_layer == "SLAB"]
        assert items
        assert "Count based on layer membership, not element type." in items[0].caveats

    def test_layer_item_threshold_one_entity_excluded(self):
        """Layer with exactly 1 entity must NOT produce a takeoff item (threshold >= 2)."""
        entities = [_entity("L1", layer="SOLE", entity_type=EntityType.LINE)]
        ctx = _context(entities)
        result = TakeoffGenerator().generate(ctx, "count")
        items = [it for it in result.items if it.source_layer == "SOLE"]
        assert items == []

    def test_layer_item_threshold_two_entities_included(self):
        """Layer with exactly 2 entities must produce a takeoff item."""
        entities = [
            _entity("L1", layer="PAIR", entity_type=EntityType.LINE),
            _entity("L2", layer="PAIR", entity_type=EntityType.LINE),
        ]
        ctx = _context(entities)
        result = TakeoffGenerator().generate(ctx, "count")
        items = [it for it in result.items if it.source_layer == "PAIR"]
        assert items

    def test_layer_handles_capped_at_20(self):
        """entity_handles in layer item must contain at most 20 handles."""
        entities = [_entity(f"L{i}", layer="BIG", entity_type=EntityType.LINE) for i in range(30)]
        ctx = _context(entities)
        result = TakeoffGenerator().generate(ctx, "count")
        items = [it for it in result.items if it.source_layer == "BIG"]
        assert items
        assert len(items[0].entity_handles) <= 20

    def test_insert_entities_excluded_from_layer_counting(self):
        """INSERT entities must be excluded from layer-based counting."""
        entities = [
            _insert("I1", block_name="COL", layer="STRUCTURAL"),
            _insert("I2", block_name="COL", layer="STRUCTURAL"),
            _insert("I3", block_name="COL", layer="STRUCTURAL"),
            _entity("L1", layer="STRUCTURAL", entity_type=EntityType.LINE),
            _entity("L2", layer="STRUCTURAL", entity_type=EntityType.LINE),
        ]
        ctx = _context(entities)
        result = TakeoffGenerator().generate(ctx, "count")
        # Block items cover STRUCTURAL layer → layer items should exclude STRUCTURAL
        struct_layer_items = [
            it
            for it in result.items
            if it.source_layer == "STRUCTURAL" and it.source_block_name is None
        ]
        # STRUCTURAL is in block_layers → should be excluded from layer counting
        assert struct_layer_items == []


# ===========================================================================
# TakeoffGenerator._extract_text_quantities — exact item fields
# ===========================================================================


class TestExtractTextQuantitiesExactFields:
    """Kill string-mutation survivors in _extract_text_quantities."""

    def test_text_item_name_prefix_exact(self):
        """Item name must start with \"Text-derived: '\"."""
        entities = [_text("T1", "5 ea girders")]
        ctx = _context(entities)
        result = TakeoffGenerator().generate(ctx, "count")
        items = [it for it in result.items if "girders" in it.name]
        assert items
        assert items[0].name.startswith("Text-derived: '")

    def test_text_item_caveat_non_ocr_exact_string(self):
        """Non-OCR text item caveat must contain the verify-against-schedule note."""
        entities = [_text("T1", "5 ea girders")]
        ctx = _context(entities)
        result = TakeoffGenerator().generate(ctx, "count")
        items = [it for it in result.items if "girders" in it.name]
        assert items
        expected = "Quantity derived from text label \u2014 verify against schedule."
        assert expected in items[0].caveats

    def test_text_item_caveat_ocr_first_caveat_exact(self):
        """OCR text item first caveat must be the OCR inaccuracy warning."""
        ocr_geo = TextGeometry.for_provenance(TextProvenance.RASTER_OCR_TEXT)
        entities = [_text("T1", "3 ea doors", text_geometry=ocr_geo)]
        ctx = _context(entities)
        result = TakeoffGenerator().generate(ctx, "count")
        items = [it for it in result.items if "3 ea doors" in it.name]
        assert items
        assert "Quantity extracted from OCR text \u2014 may be inaccurate." in items[0].caveats

    def test_text_item_ocr_second_caveat_includes_provenance(self):
        """OCR text item second caveat must include 'Text provenance:'."""
        ocr_geo = TextGeometry.for_provenance(TextProvenance.RASTER_OCR_TEXT)
        entities = [_text("T1", "3 ea doors", text_geometry=ocr_geo)]
        ctx = _context(entities)
        result = TakeoffGenerator().generate(ctx, "count")
        items = [it for it in result.items if "3 ea doors" in it.name]
        assert items
        assert any("Text provenance:" in c for c in items[0].caveats)

    def test_ocr_warning_exact_format(self):
        """OCR provenance warning must follow exact template."""
        ocr_geo = TextGeometry.for_provenance(TextProvenance.RASTER_OCR_TEXT)
        entities = [_text("T1", "3 ea doors", layer="NOTES", text_geometry=ocr_geo)]
        ctx = _context(entities)
        result = TakeoffGenerator().generate(ctx, "count")
        assert any(
            "OCR-derived quantity '3 ea doors' on layer 'NOTES'" in w
            for w in result.provenance_warnings
        )
        assert any("ESTIMATE_ONLY" in w for w in result.provenance_warnings)

    def test_text_label_truncated_to_60_chars_in_name(self):
        """Label in item name must be truncated to 60 characters."""
        long_text = "5 ea " + "X" * 60  # total > 60 chars but qty still matches
        entities = [_text("T1", long_text)]
        ctx = _context(entities)
        result = TakeoffGenerator().generate(ctx, "count")
        items = [it for it in result.items if "5 ea" in it.name]
        assert items
        # The label in the name should not exceed 60 chars
        label_in_name = items[0].name[len("Text-derived: '") : -1]
        assert len(label_in_name) <= 60

    def test_pcs_pattern_extracts_quantity(self):
        """'pcs' suffix pattern must match and extract quantity."""
        entities = [_text("T1", "10 pcs screws")]
        ctx = _context(entities)
        result = TakeoffGenerator().generate(ctx, "count")
        items = [it for it in result.items if "10 pcs screws" in it.name]
        assert items
        assert items[0].quantity == 10

    def test_x_pattern_extracts_quantity(self):
        """'x' suffix pattern must match (e.g., '4x beams')."""
        entities = [_text("T1", "4x beams")]
        ctx = _context(entities)
        result = TakeoffGenerator().generate(ctx, "count")
        items = [it for it in result.items if "4x beams" in it.name]
        assert items
        assert items[0].quantity == 4


# ===========================================================================
# TakeoffGenerator.generate — aggregate fields
# ===========================================================================


class TestTakeoffGeneratorGenerateFields:
    """Kill field-mutation survivors in TakeoffGenerator.generate."""

    def test_total_items_matches_len_items(self):
        """total_items field must equal len(items), not len+1 or something else."""
        entities = [_insert(f"B{i}", block_name="COL", x=float(i * 5)) for i in range(3)]
        ctx = _context(entities)
        result = TakeoffGenerator().generate(ctx, "count")
        assert result.total_items == len(result.items)

    def test_total_quantity_items_is_sum_of_quantities(self):
        """total_quantity_items must equal sum of all item quantities."""
        entities = [_insert(f"B{i}", block_name="COL", x=float(i * 5)) for i in range(3)]
        ctx = _context(entities)
        result = TakeoffGenerator().generate(ctx, "count")
        assert result.total_quantity_items == sum(it.quantity for it in result.items)

    def test_empty_drawing_caveat_exact_string(self):
        """Empty drawing caveat must be exactly 'No entities in drawing.'."""
        result = TakeoffGenerator().generate(_context([]), "count")
        assert "No entities in drawing." in result.caveats

    def test_empty_drawing_flag_exact_value(self):
        """Empty drawing ambiguity flag must be exactly 'empty_drawing'."""
        result = TakeoffGenerator().generate(_context([]), "count")
        assert "empty_drawing" in result.ambiguity_flags

    def test_region_caveat_exact_string(self):
        """Region caveat must be the selected-region-only note."""
        entities = [_insert(f"B{i}", block_name="COL", x=float(i * 5)) for i in range(3)]
        ctx = _context(entities)
        region = RegionContext(entities=entities, is_whole_drawing=False, ambiguity_flags=[])
        result = TakeoffGenerator().generate(ctx, "count", region=region)
        assert "Counts are from the selected region only, not the entire drawing." in result.caveats

    def test_region_flag_exact_value(self):
        """Region ambiguity flag must be exactly 'partial_region'."""
        entities = [_insert(f"B{i}", block_name="COL", x=float(i * 5)) for i in range(3)]
        ctx = _context(entities)
        region = RegionContext(entities=entities, is_whole_drawing=False, ambiguity_flags=[])
        result = TakeoffGenerator().generate(ctx, "count", region=region)
        assert "partial_region" in result.ambiguity_flags

    def test_aggregate_confidence_is_high_for_block_only_drawing(self):
        """All-block drawing (no text items) must yield HIGH aggregate confidence."""
        entities = [_insert(f"B{i}", block_name="COL", x=float(i * 5)) for i in range(3)]
        ctx = _context(entities)
        result = TakeoffGenerator().generate(ctx, "count")
        assert result.aggregate_confidence == TakeoffConfidence.HIGH

    def test_aggregate_confidence_no_items_defaults_to_medium(self):
        """With no items (entities present but no blocks/text patterns), agg defaults to MEDIUM."""
        # A single line entity — no blocks, no text patterns, layer count < 2
        entities = [_entity("L1", layer="WALLS", entity_type=EntityType.LINE)]
        ctx = _context(entities)
        result = TakeoffGenerator().generate(ctx, "count")
        assert result.aggregate_confidence == TakeoffConfidence.MEDIUM

    def test_region_entities_used_not_context_entities(self):
        """When region is provided, its entities are counted, not context's."""
        ctx_entities = [_insert(f"B{i}", block_name="BIG", x=float(i)) for i in range(10)]
        ctx = _context(ctx_entities)
        region_entities = [_entity("R1", layer="SMALL", entity_type=EntityType.LINE)]
        region = RegionContext(entities=region_entities, is_whole_drawing=False, ambiguity_flags=[])
        result = TakeoffGenerator().generate(ctx, "count", region=region)
        # Region has no blocks → no block items
        block_items = [it for it in result.items if it.source_block_name == "BIG"]
        assert block_items == []


# ===========================================================================
# RevisionSummarizer.summarize — no-data path exact strings
# ===========================================================================


class TestRevisionSummarizerNoDataExactStrings:
    """Kill string-mutation survivors in the no-data early return."""

    def test_no_data_headline_exact(self):
        """No-data headline must be exactly 'No revision data available.'."""
        result = RevisionSummarizer().summarize()
        assert result.headline == "No revision data available."

    def test_no_data_caveats_exact(self):
        """No-data caveats must contain 'Neither comparison result nor changeset was provided.'."""
        result = RevisionSummarizer().summarize()
        assert "Neither comparison result nor changeset was provided." in result.caveats

    def test_no_data_missing_context_exact(self):
        """missing_context must be exactly ['comparison_result', 'changeset']."""
        result = RevisionSummarizer().summarize()
        assert result.missing_context == ["comparison_result", "changeset"]


# ===========================================================================
# RevisionSummarizer._overall_assessment — edge cases
# ===========================================================================


class TestOverallAssessmentEdgeCases:
    """Kill remaining mutation survivors in _overall_assessment."""

    def test_no_changes_exact_string(self):
        """Zero changes must produce 'No changes were detected between the drawings.'."""
        result = RevisionSummarizer().summarize(comparison_result=_comparison_result())
        assert result.overall_assessment == "No changes were detected between the drawings."

    def test_all_four_categories_in_assessment(self):
        """Assessment with all 4 categories must list them all joined by '. '."""
        cr = _comparison_result(
            _change(ChangeCategory.ADDED, "A1"),
            _change(ChangeCategory.REMOVED, "R1"),
            _change(ChangeCategory.MODIFIED, "M1"),
            _change(ChangeCategory.MOVED, "V1"),
        )
        result = RevisionSummarizer().summarize(comparison_result=cr)
        oa = result.overall_assessment
        assert "1 element(s) were added" in oa
        assert "1 element(s) were removed" in oa
        assert "1 element(s) were modified" in oa
        assert "1 element(s) were repositioned" in oa
        assert oa.endswith(".")

    def test_assessment_uses_period_join_not_comma(self):
        """Parts must be joined with '. ' not ', '."""
        cr = _comparison_result(
            _change(ChangeCategory.ADDED, "A1"),
            _change(ChangeCategory.REMOVED, "R1"),
        )
        result = RevisionSummarizer().summarize(comparison_result=cr)
        oa = result.overall_assessment
        # ". " must appear between the two parts
        assert ". " in oa
        # Comma joining must not appear
        assert ", 1 element" not in oa

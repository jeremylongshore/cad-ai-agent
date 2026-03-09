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
        text_entities = [
            _text(f"T{i}", text=f"Label {i}", text_geometry=native) for i in range(3)
        ]
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
        cr = _comparison_result(
            _change(ChangeCategory.ADDED, handle="T1", text_content="Beam B-3")
        )
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
        entities = [
            _text(f"T{i}", f"LABEL {i}", text_geometry=ocr_geo) for i in range(2)
        ]
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
        entities = [
            _entity(f"L{i}", entity_type=EntityType.LINE) for i in range(5)
        ] + [
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

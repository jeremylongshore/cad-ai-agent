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
        assert result.areas_affected == sorted(result.areas_affected)

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

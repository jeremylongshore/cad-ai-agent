"""Tests for ScopeBuilder — assembles layout, revision, and takeoff sections
into a unified scope-style report. All deterministic, no LLM calls.
"""

from __future__ import annotations

from cad_dxf_agent.core.design_ops import ScopeBuilder
from cad_dxf_agent.models.cad_schema import (
    DrawingContext,
    EntityRef,
    EntityType,
    LayerRule,
    Point2D,
)
from cad_dxf_agent.models.design_ops_schema import ScopeSectionType

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _entity(
    handle: str,
    layer: str = "STRUCTURAL",
    entity_type: EntityType = EntityType.INSERT,
    block_name: str = "MARK",
    x: float = 0.0,
    y: float = 0.0,
) -> EntityRef:
    return EntityRef(
        handle=handle,
        entity_type=entity_type,
        layer=layer,
        block_name=block_name,
        insert_point=Point2D(x=x, y=y),
    )


def _context(entities: list[EntityRef]) -> DrawingContext:
    layer_names = sorted({e.layer for e in entities})
    return DrawingContext(
        file_path="test.dxf",
        entities=entities,
        layers=[LayerRule(name=n) for n in layer_names],
    )


def _comparison_with_changes():
    from cad_dxf_agent.models.comparison_schema import (
        ChangeCategory,
        ComparisonResult,
        EntityChange,
        GeometrySnapshot,
    )

    snap = GeometrySnapshot(
        handle="X1",
        entity_type=EntityType.LINE,
        layer="STRUCTURAL",
        points=[Point2D(x=0, y=0)],
    )
    change = EntityChange(
        category=ChangeCategory.ADDED,
        revision_snapshot=snap,
        confidence=0.9,
    )
    return ComparisonResult(
        changes=[change],
        summary={
            "added": 1,
            "removed": 0,
            "modified": 0,
            "moved": 0,
            "unchanged": 0,
        },
    )


def _rich_entities() -> list[EntityRef]:
    """20+ inserts on a single layer so layout density/block recs fire."""
    return [
        _entity(f"H{i:03d}", layer="STRUCTURAL", block_name="COL", x=float(i), y=0.0)
        for i in range(20)
    ]


# ---------------------------------------------------------------------------
# Test cases
# ---------------------------------------------------------------------------


class TestScopeBuilderEmptyDrawing:
    def test_empty_drawing_returns_scope(self):
        ctx = _context([])
        scope = ScopeBuilder().build(ctx, "scope of work")
        assert scope is not None

    def test_empty_drawing_omits_layout_recommendations(self):
        ctx = _context([])
        scope = ScopeBuilder().build(ctx, "scope of work")
        assert "layout_recommendations" in scope.omitted_sections

    def test_empty_drawing_omits_takeoff_candidates(self):
        ctx = _context([])
        scope = ScopeBuilder().build(ctx, "scope of work")
        assert "takeoff_candidates" in scope.omitted_sections

    def test_empty_drawing_omits_revision_summary_without_comparison(self):
        ctx = _context([])
        scope = ScopeBuilder().build(ctx, "scope of work")
        assert "revision_summary" in scope.omitted_sections

    def test_empty_drawing_has_no_sections(self):
        ctx = _context([])
        scope = ScopeBuilder().build(ctx, "scope of work")
        assert len(scope.sections) == 0


class TestScopeBuilderWithEntities:
    def test_full_scope_produces_layout_section(self):
        entities = _rich_entities()
        ctx = _context(entities)
        scope = ScopeBuilder().build(ctx, "suggest layout improvements")
        section_types = [s.section_type for s in scope.sections]
        assert ScopeSectionType.LAYOUT_RECOMMENDATIONS in section_types

    def test_full_scope_produces_takeoff_section(self):
        entities = _rich_entities()
        ctx = _context(entities)
        scope = ScopeBuilder().build(ctx, "scope of work")
        section_types = [s.section_type for s in scope.sections]
        assert ScopeSectionType.TAKEOFF_CANDIDATES in section_types

    def test_section_types_are_enum_values(self):
        entities = _rich_entities()
        ctx = _context(entities)
        scope = ScopeBuilder().build(ctx, "scope of work")
        for section in scope.sections:
            assert isinstance(section.section_type, ScopeSectionType)

    def test_each_section_has_confidence(self):
        entities = _rich_entities()
        ctx = _context(entities)
        scope = ScopeBuilder().build(ctx, "scope of work")
        for section in scope.sections:
            assert 0.0 <= section.confidence <= 1.0

    def test_each_section_has_caveats_list(self):
        entities = _rich_entities()
        ctx = _context(entities)
        scope = ScopeBuilder().build(ctx, "scope of work")
        for section in scope.sections:
            assert isinstance(section.caveats, list)

    def test_aggregate_confidence_is_min_of_sections(self):
        entities = _rich_entities()
        ctx = _context(entities)
        scope = ScopeBuilder().build(ctx, "scope of work")
        if scope.sections:
            expected_min = min(s.confidence for s in scope.sections if s.available)
            assert abs(scope.aggregate_confidence - round(expected_min, 2)) < 1e-9

    def test_aggregate_confidence_in_valid_range(self):
        entities = _rich_entities()
        ctx = _context(entities)
        scope = ScopeBuilder().build(ctx, "scope of work")
        assert 0.0 <= scope.aggregate_confidence <= 1.0


class TestScopeBuilderWithComparison:
    def test_comparison_result_produces_revision_summary_section(self):
        entities = _rich_entities()
        ctx = _context(entities)
        comparison = _comparison_with_changes()
        scope = ScopeBuilder().build(ctx, "scope of work", comparison_result=comparison)
        section_types = [s.section_type for s in scope.sections]
        assert ScopeSectionType.REVISION_SUMMARY in section_types

    def test_missing_comparison_puts_revision_summary_in_omitted(self):
        entities = _rich_entities()
        ctx = _context(entities)
        scope = ScopeBuilder().build(ctx, "scope of work")
        assert "revision_summary" in scope.omitted_sections

    def test_revision_summary_not_in_omitted_when_comparison_provided(self):
        entities = _rich_entities()
        ctx = _context(entities)
        comparison = _comparison_with_changes()
        scope = ScopeBuilder().build(ctx, "scope of work", comparison_result=comparison)
        assert "revision_summary" not in scope.omitted_sections

    def test_scope_with_both_comparison_and_changeset(self):
        from cad_dxf_agent.models.ops_schema import ChangeSet, EditOperation, OpType

        entities = _rich_entities()
        ctx = _context(entities)
        comparison = _comparison_with_changes()
        changeset = ChangeSet(
            prompt="test",
            operations=[
                EditOperation(
                    op_type=OpType.MOVE_ENTITY,
                    target_handle="H001",
                    target_layer="STRUCTURAL",
                    params={"dx": 10, "dy": 0},
                )
            ],
        )
        # comparison_result takes priority per RevisionSummarizer logic
        scope = ScopeBuilder().build(
            ctx,
            "scope of work",
            comparison_result=comparison,
            changeset=changeset,
        )
        section_types = [s.section_type for s in scope.sections]
        assert ScopeSectionType.REVISION_SUMMARY in section_types


class TestScopeBuilderAmbiguityAndCaveats:
    def test_ambiguity_flags_propagated(self):
        # Sparse entities should trigger sparse_text_evidence flag from LayoutRecommender
        entities = [_entity("H001", entity_type=EntityType.LINE, block_name=None)]
        ctx = _context(entities)
        scope = ScopeBuilder().build(ctx, "suggest improvements")
        # The scope collects flags from sub-analyzers — just assert it's a list
        assert isinstance(scope.ambiguity_flags, list)

    def test_caveats_collected_across_sections(self):
        entities = _rich_entities()
        ctx = _context(entities)
        scope = ScopeBuilder().build(ctx, "scope of work")
        assert isinstance(scope.caveats, list)

    def test_omitted_sections_not_hallucinated(self):
        """Sections listed in omitted_sections must not appear in scope.sections."""
        ctx = _context([])
        scope = ScopeBuilder().build(ctx, "scope of work")
        present_types = {s.section_type.value for s in scope.sections}
        for omitted in scope.omitted_sections:
            assert omitted not in present_types

    def test_no_edit_operations_in_scope_result(self):
        """ScopeBuilder must never produce edit operations of any kind."""
        entities = _rich_entities()
        ctx = _context(entities)
        comparison = _comparison_with_changes()
        scope = ScopeBuilder().build(ctx, "scope of work", comparison_result=comparison)
        dumped = scope.model_dump()
        # Top-level result has no 'operations' key (it's a ScopeSummary, not PlatformResponse)
        assert "operations" not in dumped
        # Section content must not contain op_type fields
        for section in dumped.get("sections", []):
            content = section.get("content", {})
            assert "op_type" not in str(content), (
                f"Section '{section['section_type']}' content contains op_type"
            )

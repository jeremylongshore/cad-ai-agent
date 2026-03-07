"""Tests for FieldSummaryBuilder from cad_dxf_agent.core.construction_ops."""

from __future__ import annotations

import pytest

from cad_dxf_agent.core.construction_ops import FieldSummaryBuilder
from cad_dxf_agent.models.cad_schema import (
    DrawingContext,
    EntityRef,
    EntityType,
    LayerRule,
    Point2D,
)
from cad_dxf_agent.models.construction_ops_schema import FieldSectionType


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _entity(
    handle,
    layer="STRUCTURAL",
    entity_type=EntityType.INSERT,
    x=0.0,
    y=0.0,
    block_name="MARK",
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


def _rich_context():
    """20 block inserts spread across a wide area."""
    entities = [
        _entity(f"H{i:03d}", layer="STRUCTURAL", block_name="COL", x=float(i * 5), y=0.0)
        for i in range(20)
    ]
    return _context(entities)


def _grid_context():
    """Context with vertical and horizontal grid lines on GRID layer plus block inserts."""
    entities = [
        # Vertical grid lines (same x for start and end)
        EntityRef(
            handle=f"VG{i}",
            entity_type=EntityType.LINE,
            layer="GRID",
            insert_point=Point2D(x=float(i * 30), y=0.0),
            attributes={"end_point": (float(i * 30), 100.0)},
        )
        for i in range(4)
    ] + [
        # Horizontal grid lines (same y for start and end)
        EntityRef(
            handle=f"HG{i}",
            entity_type=EntityType.LINE,
            layer="GRID",
            insert_point=Point2D(x=0.0, y=float(i * 30)),
            attributes={"end_point": (120.0, float(i * 30))},
        )
        for i in range(4)
    ] + [
        # Some block inserts so other sections can fire too
        _entity(f"BLK{i}", block_name="COL", x=float(i * 30), y=50.0)
        for i in range(5)
    ]
    return _context(entities)


def _comparison_with_adds():
    from cad_dxf_agent.models.comparison_schema import (
        ChangeCategory,
        ComparisonResult,
        EntityChange,
        GeometrySnapshot,
    )

    snap = GeometrySnapshot(
        handle="CMP1",
        entity_type=EntityType.LINE,
        layer="STRUCTURAL",
        points=[Point2D(x=0, y=0), Point2D(x=10, y=0)],
    )
    return ComparisonResult(
        changes=[
            EntityChange(
                category=ChangeCategory.ADDED,
                revision_snapshot=snap,
                confidence=0.85,
            )
        ],
        summary={"added": 1, "removed": 0, "modified": 0, "moved": 0, "unchanged": 0},
    )


def _repeated_blocks_context():
    """Context with 3+ identical block inserts to trigger condition report."""
    entities = [
        _entity(f"REP{i}", block_name="FOOTING", x=float(i * 10), y=0.0)
        for i in range(5)
    ]
    return _context(entities)


# ---------------------------------------------------------------------------
# Tests: full assembly with rich context
# ---------------------------------------------------------------------------


class TestFullAssemblyRichContext:
    """Rich context (20 block inserts) should produce TAKEOFF_SUMMARY and LAYOUT_NOTES."""

    def test_returns_field_summary(self):
        builder = FieldSummaryBuilder()
        result = builder.build(_rich_context(), prompt="Summarize field conditions")
        assert result is not None

    def test_takeoff_summary_section_present(self):
        builder = FieldSummaryBuilder()
        result = builder.build(_rich_context(), prompt="Summarize field conditions")
        section_types = [s.section_type for s in result.sections]
        assert FieldSectionType.TAKEOFF_SUMMARY in section_types

    def test_layout_notes_section_present(self):
        builder = FieldSummaryBuilder()
        result = builder.build(_rich_context(), prompt="Summarize field conditions")
        section_types = [s.section_type for s in result.sections]
        assert FieldSectionType.LAYOUT_NOTES in section_types

    def test_sections_not_empty(self):
        builder = FieldSummaryBuilder()
        result = builder.build(_rich_context(), prompt="Summarize field conditions")
        assert len(result.sections) > 0


# ---------------------------------------------------------------------------
# Tests: grid context
# ---------------------------------------------------------------------------


class TestGridContext:
    """Grid layer lines should produce a GRID_SUMMARY section."""

    def test_grid_summary_section_present(self):
        builder = FieldSummaryBuilder()
        result = builder.build(_grid_context(), prompt="Analyze grid layout")
        section_types = [s.section_type for s in result.sections]
        assert FieldSectionType.GRID_SUMMARY in section_types


# ---------------------------------------------------------------------------
# Tests: missing section handling
# ---------------------------------------------------------------------------


class TestMissingSectionHandling:
    """Sections that cannot be generated should appear in omitted_sections."""

    def test_no_grid_entities_omits_grid_summary(self):
        ctx = _rich_context()  # no GRID layer lines
        builder = FieldSummaryBuilder()
        result = builder.build(ctx, prompt="Summarize")
        assert "GRID_SUMMARY" in result.omitted_sections or FieldSectionType.GRID_SUMMARY.value in result.omitted_sections

    def test_no_comparison_omits_revision_changes(self):
        builder = FieldSummaryBuilder()
        result = builder.build(_rich_context(), prompt="Summarize")
        assert "REVISION_CHANGES" in result.omitted_sections or FieldSectionType.REVISION_CHANGES.value in result.omitted_sections

    def test_handles_missing_comparison_result_gracefully(self):
        builder = FieldSummaryBuilder()
        # Should not crash when comparison_result is None
        result = builder.build(_rich_context(), prompt="Summarize", comparison_result=None)
        assert result is not None

    def test_handles_missing_changeset_gracefully(self):
        builder = FieldSummaryBuilder()
        # Should not crash when changeset is None
        result = builder.build(_rich_context(), prompt="Summarize", changeset=None)
        assert result is not None


# ---------------------------------------------------------------------------
# Tests: empty drawing
# ---------------------------------------------------------------------------


class TestEmptyDrawing:
    """Empty drawing should return a valid FieldSummary with no sections."""

    def test_empty_returns_empty_sections(self):
        ctx = _context([])
        builder = FieldSummaryBuilder()
        result = builder.build(ctx, prompt="Summarize")
        assert result.sections == []

    def test_empty_all_sections_omitted(self):
        ctx = _context([])
        builder = FieldSummaryBuilder()
        result = builder.build(ctx, prompt="Summarize")
        # All possible sections should be listed as omitted
        assert len(result.omitted_sections) > 0


# ---------------------------------------------------------------------------
# Tests: confidence propagation
# ---------------------------------------------------------------------------


class TestConfidencePropagation:
    """Aggregate confidence should be the minimum of available sections."""

    def test_aggregate_confidence_is_min_of_sections(self):
        builder = FieldSummaryBuilder()
        result = builder.build(_rich_context(), prompt="Summarize")
        if result.sections:
            section_confidences = [s.confidence for s in result.sections]
            assert result.aggregate_confidence == pytest.approx(min(section_confidences))

    def test_aggregate_confidence_with_comparison(self):
        builder = FieldSummaryBuilder()
        result = builder.build(
            _rich_context(),
            prompt="Summarize",
            comparison_result=_comparison_with_adds(),
        )
        if result.sections:
            section_confidences = [s.confidence for s in result.sections]
            assert result.aggregate_confidence == pytest.approx(min(section_confidences))


# ---------------------------------------------------------------------------
# Tests: section type enum values
# ---------------------------------------------------------------------------


class TestSectionTypeEnums:
    """Each section should have a correct FieldSectionType enum value."""

    def test_all_sections_have_valid_enum(self):
        builder = FieldSummaryBuilder()
        result = builder.build(_grid_context(), prompt="Summarize")
        valid_types = set(FieldSectionType)
        for section in result.sections:
            assert section.section_type in valid_types


# ---------------------------------------------------------------------------
# Tests: timestamp
# ---------------------------------------------------------------------------


class TestTimestamp:
    """FieldSummary should have a generated_at timestamp."""

    def test_has_generated_at(self):
        builder = FieldSummaryBuilder()
        result = builder.build(_rich_context(), prompt="Summarize")
        assert result.generated_at is not None


# ---------------------------------------------------------------------------
# Tests: caveats aggregation
# ---------------------------------------------------------------------------


class TestCaveatsAggregation:
    """Caveats should be aggregated from all sub-generators."""

    def test_caveats_is_list(self):
        builder = FieldSummaryBuilder()
        result = builder.build(_rich_context(), prompt="Summarize")
        assert isinstance(result.caveats, list)


# ---------------------------------------------------------------------------
# Tests: serialisation
# ---------------------------------------------------------------------------


class TestSerialisation:
    """model_dump() should produce a serializable dict."""

    def test_model_dump_returns_dict(self):
        builder = FieldSummaryBuilder()
        result = builder.build(_rich_context(), prompt="Summarize")
        dumped = result.model_dump()
        assert isinstance(dumped, dict)

    def test_no_operations_key_in_dump(self):
        builder = FieldSummaryBuilder()
        result = builder.build(_rich_context(), prompt="Summarize")
        dumped = result.model_dump()
        assert "operations" not in dumped

    def test_no_edit_operation_objects_in_dump(self):
        builder = FieldSummaryBuilder()
        result = builder.build(_rich_context(), prompt="Summarize")
        dumped_str = str(result.model_dump())
        for forbidden in ("op_type", "move_entity", "edit_text", "delete_entity", "add_block"):
            assert forbidden not in dumped_str, f"Found '{forbidden}' in serialised FieldSummary"


# ---------------------------------------------------------------------------
# Tests: omitted_sections tracking
# ---------------------------------------------------------------------------


class TestOmittedSections:
    """omitted_sections should track which sections couldn't be generated."""

    def test_omitted_sections_is_list(self):
        builder = FieldSummaryBuilder()
        result = builder.build(_rich_context(), prompt="Summarize")
        assert isinstance(result.omitted_sections, list)


# ---------------------------------------------------------------------------
# Tests: comparison_result triggers REVISION_CHANGES
# ---------------------------------------------------------------------------


class TestRevisionChangesSection:
    """Providing a comparison_result should produce a REVISION_CHANGES section."""

    def test_revision_changes_present_with_comparison(self):
        builder = FieldSummaryBuilder()
        result = builder.build(
            _rich_context(),
            prompt="Summarize",
            comparison_result=_comparison_with_adds(),
        )
        section_types = [s.section_type for s in result.sections]
        assert FieldSectionType.REVISION_CHANGES in section_types


# ---------------------------------------------------------------------------
# Tests: title default
# ---------------------------------------------------------------------------


class TestTitleDefault:
    """Field summary title should default to 'Construction Field Summary'."""

    def test_default_title(self):
        builder = FieldSummaryBuilder()
        result = builder.build(_rich_context(), prompt="Summarize")
        assert result.title == "Construction Field Summary"


# ---------------------------------------------------------------------------
# Tests: condition report with repeated blocks
# ---------------------------------------------------------------------------


class TestConditionReport:
    """3+ identical block inserts should trigger CONDITION_REPORT section."""

    def test_condition_report_with_repeated_blocks(self):
        builder = FieldSummaryBuilder()
        result = builder.build(_repeated_blocks_context(), prompt="Inspect conditions")
        section_types = [s.section_type for s in result.sections]
        assert FieldSectionType.CONDITION_REPORT in section_types

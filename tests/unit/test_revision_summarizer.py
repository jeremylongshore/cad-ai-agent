"""Tests for RevisionSummarizer in cad_dxf_agent.core.design_ops."""

from __future__ import annotations

from cad_dxf_agent.core.design_ops import RevisionSummarizer
from cad_dxf_agent.models.cad_schema import (
    DrawingContext,
    EntityRef,
    EntityType,
    LayerRule,
    Point2D,
)
from cad_dxf_agent.models.comparison_schema import (
    ChangeCategory,
    ComparisonResult,
    EntityChange,
    GeometrySnapshot,
)
from cad_dxf_agent.models.ops_schema import ChangeSet, EditOperation, OpType

# ---------------------------------------------------------------------------
# Test data factories
# ---------------------------------------------------------------------------


def _snapshot(
    handle: str = "A1",
    layer: str = "STRUCTURAL",
    entity_type: EntityType = EntityType.LINE,
    text: str | None = None,
) -> GeometrySnapshot:
    return GeometrySnapshot(
        handle=handle,
        entity_type=entity_type,
        layer=layer,
        points=[Point2D(x=0, y=0)],
        text_content=text,
    )


def _change(
    category: ChangeCategory,
    master: GeometrySnapshot | None = None,
    revision: GeometrySnapshot | None = None,
    displacement: Point2D | None = None,
    confidence: float = 0.95,
) -> EntityChange:
    return EntityChange(
        category=category,
        master_snapshot=master,
        revision_snapshot=revision,
        displacement=displacement,
        confidence=confidence,
    )


def _comparison(*changes: EntityChange, warnings: list[str] | None = None) -> ComparisonResult:
    summary: dict[str, int] = {"added": 0, "removed": 0, "modified": 0, "moved": 0, "unchanged": 0}
    for c in changes:
        summary[c.category.value] += 1
    return ComparisonResult(changes=list(changes), summary=summary, warnings=warnings or [])


def _context(entities: list[EntityRef], layers: list[str] | None = None) -> DrawingContext:
    layer_names = layers or sorted({e.layer for e in entities})
    return DrawingContext(
        file_path="test.dxf",
        entities=entities,
        layers=[LayerRule(name=n) for n in layer_names],
    )


def _entity(
    handle: str,
    layer: str = "STRUCTURAL",
    entity_type: EntityType = EntityType.LINE,
    text: str | None = None,
) -> EntityRef:
    return EntityRef(handle=handle, entity_type=entity_type, layer=layer, text_content=text)


# ---------------------------------------------------------------------------
# Test class
# ---------------------------------------------------------------------------


class TestRevisionSummarizerNoInputs:
    """Behaviour when neither comparison_result nor changeset is given."""

    def test_no_inputs_returns_no_revision_data_headline(self):
        result = RevisionSummarizer().summarize()
        assert result.headline == "No revision data available."

    def test_no_inputs_adds_missing_context_entries(self):
        result = RevisionSummarizer().summarize()
        assert "comparison_result" in result.missing_context
        assert "changeset" in result.missing_context

    def test_no_inputs_adds_caveat(self):
        result = RevisionSummarizer().summarize()
        assert result.caveats  # at least one caveat explaining the missing data


class TestRevisionSummarizerFromComparisonResult:
    """RevisionSummarizer.summarize(comparison_result=...) path."""

    def test_added_entities_in_summary(self):
        snap = _snapshot(handle="B1", layer="WALLS")
        comp = _comparison(_change(ChangeCategory.ADDED, revision=snap))
        result = RevisionSummarizer().summarize(comparison_result=comp)
        assert result.change_count == 1
        assert any("added" in e.change_type for e in result.key_changes)

    def test_removed_entities_in_summary(self):
        snap = _snapshot(handle="C1", layer="WALLS")
        comp = _comparison(_change(ChangeCategory.REMOVED, master=snap))
        result = RevisionSummarizer().summarize(comparison_result=comp)
        assert result.change_count == 1
        assert any("removed" in e.change_type for e in result.key_changes)

    def test_moved_entities_include_displacement_in_technical_detail(self):
        master = _snapshot(handle="D1", layer="GRID")
        revision = _snapshot(handle="D2", layer="GRID")
        disp = Point2D(x=5.0, y=3.0)
        comp = _comparison(
            _change(ChangeCategory.MOVED, master=master, revision=revision, displacement=disp)
        )
        result = RevisionSummarizer().summarize(comparison_result=comp)
        tech = result.key_changes[0].technical_detail
        assert "5.0" in tech
        assert "3.0" in tech

    def test_modified_entities_in_summary(self):
        snap = _snapshot(handle="E1", layer="STRUCTURAL")
        comp = _comparison(_change(ChangeCategory.MODIFIED, master=snap, revision=snap))
        result = RevisionSummarizer().summarize(comparison_result=comp)
        assert result.change_count == 1
        assert any("modified" in e.change_type for e in result.key_changes)

    def test_mixed_changes_counted_correctly(self):
        added_snap = _snapshot(handle="F1", layer="LAYER_A")
        removed_snap = _snapshot(handle="F2", layer="LAYER_B")
        modified_snap = _snapshot(handle="F3", layer="LAYER_A")
        comp = _comparison(
            _change(ChangeCategory.ADDED, revision=added_snap),
            _change(ChangeCategory.REMOVED, master=removed_snap),
            _change(ChangeCategory.MODIFIED, master=modified_snap, revision=modified_snap),
        )
        result = RevisionSummarizer().summarize(comparison_result=comp)
        assert result.change_count == 3

    def test_unchanged_entities_excluded_from_summary(self):
        snap = _snapshot(handle="G1", layer="STRUCTURAL")
        comp = _comparison(
            _change(ChangeCategory.UNCHANGED, master=snap, revision=snap),
            _change(ChangeCategory.ADDED, revision=_snapshot(handle="G2", layer="STRUCTURAL")),
        )
        result = RevisionSummarizer().summarize(comparison_result=comp)
        # Only the ADDED change should appear; UNCHANGED is excluded
        assert result.change_count == 1

    def test_headline_format_with_counts(self):
        added = _snapshot(handle="H1", layer="LAYER_A")
        removed = _snapshot(handle="H2", layer="LAYER_B")
        comp = _comparison(
            _change(ChangeCategory.ADDED, revision=added),
            _change(ChangeCategory.ADDED, revision=_snapshot(handle="H3", layer="LAYER_A")),
            _change(ChangeCategory.REMOVED, master=removed),
        )
        result = RevisionSummarizer().summarize(comparison_result=comp)
        assert "3 change(s) detected" in result.headline
        assert "2 added" in result.headline
        assert "1 removed" in result.headline

    def test_areas_affected_sorted_layer_names(self):
        snap_z = _snapshot(handle="I1", layer="ZONE_Z")
        snap_a = _snapshot(handle="I2", layer="ZONE_A")
        snap_m = _snapshot(handle="I3", layer="ZONE_M")
        comp = _comparison(
            _change(ChangeCategory.ADDED, revision=snap_z),
            _change(ChangeCategory.ADDED, revision=snap_a),
            _change(ChangeCategory.ADDED, revision=snap_m),
        )
        result = RevisionSummarizer().summarize(comparison_result=comp)
        assert result.areas_affected == sorted(result.areas_affected)
        assert set(result.areas_affected) == {"ZONE_A", "ZONE_M", "ZONE_Z"}

    def test_comparison_warnings_propagate_to_caveats(self):
        snap = _snapshot(handle="J1", layer="STRUCTURAL")
        comp = _comparison(
            _change(ChangeCategory.ADDED, revision=snap),
            warnings=["Too many entities excluded by profile filter."],
        )
        result = RevisionSummarizer().summarize(comparison_result=comp)
        assert any("excluded" in c for c in result.caveats)

    def test_all_unchanged_returns_no_changes_headline(self):
        snap = _snapshot(handle="K1", layer="STRUCTURAL")
        comp = _comparison(_change(ChangeCategory.UNCHANGED, master=snap, revision=snap))
        result = RevisionSummarizer().summarize(comparison_result=comp)
        assert result.headline == "No changes detected."

    def test_overall_assessment_includes_human_readable_counts(self):
        added = _snapshot(handle="L1", layer="STRUCTURAL")
        removed = _snapshot(handle="L2", layer="WALLS")
        comp = _comparison(
            _change(ChangeCategory.ADDED, revision=added),
            _change(ChangeCategory.REMOVED, master=removed),
        )
        result = RevisionSummarizer().summarize(comparison_result=comp)
        assert "1 element(s) were added" in result.overall_assessment
        assert "1 element(s) were removed" in result.overall_assessment

    def test_moved_plain_description_uses_repositioned_not_op_type(self):
        master = _snapshot(handle="M1", layer="GRID")
        revision = _snapshot(handle="M2", layer="GRID")
        comp = _comparison(
            _change(
                ChangeCategory.MOVED,
                master=master,
                revision=revision,
                displacement=Point2D(x=1.0, y=0.0),
            )
        )
        result = RevisionSummarizer().summarize(comparison_result=comp)
        desc = result.key_changes[0].plain_description
        assert "repositioned" in desc.lower()
        assert "MOVE" not in desc  # raw op type must not appear

    def test_result_has_no_operations_attribute(self):
        comp = _comparison()
        result = RevisionSummarizer().summarize(comparison_result=comp)
        assert not hasattr(result, "operations")

    def test_empty_comparison_returns_no_changes_headline(self):
        comp = _comparison()  # zero changes
        result = RevisionSummarizer().summarize(comparison_result=comp)
        assert result.headline == "No changes detected."


class TestRevisionSummarizerFromChangeset:
    """RevisionSummarizer.summarize(changeset=...) path."""

    def test_move_operations_in_summary(self):
        cs = ChangeSet(
            operations=[
                EditOperation(
                    op_type=OpType.MOVE_ENTITY, target_handle="N1", target_layer="STRUCTURAL"
                )
            ]
        )
        result = RevisionSummarizer().summarize(changeset=cs)
        assert result.change_count == 1
        assert any("repositioned" in e.plain_description.lower() for e in result.key_changes)

    def test_delete_operations_in_summary(self):
        cs = ChangeSet(
            operations=[
                EditOperation(
                    op_type=OpType.DELETE_ENTITY, target_handle="O1", target_layer="WALLS"
                )
            ]
        )
        result = RevisionSummarizer().summarize(changeset=cs)
        assert result.change_count == 1
        assert any("removed" in e.plain_description.lower() for e in result.key_changes)

    def test_edit_text_operations_in_summary(self):
        cs = ChangeSet(
            operations=[
                EditOperation(
                    op_type=OpType.EDIT_TEXT,
                    target_handle="P1",
                    target_layer="NOTES",
                    params={"new_text": "Revised label"},
                )
            ]
        )
        result = RevisionSummarizer().summarize(changeset=cs)
        assert result.change_count == 1
        assert any("text" in e.plain_description.lower() for e in result.key_changes)

    def test_plain_language_no_raw_op_types_in_descriptions(self):
        cs = ChangeSet(
            operations=[
                EditOperation(
                    op_type=OpType.MOVE_ENTITY, target_handle="Q1", target_layer="STRUCTURAL"
                ),
                EditOperation(
                    op_type=OpType.DELETE_ENTITY, target_handle="Q2", target_layer="WALLS"
                ),
                EditOperation(op_type=OpType.EDIT_TEXT, target_handle="Q3", target_layer="NOTES"),
            ]
        )
        result = RevisionSummarizer().summarize(changeset=cs)
        for entry in result.key_changes:
            assert "move_entity" not in entry.plain_description
            assert "delete_entity" not in entry.plain_description
            assert "edit_text" not in entry.plain_description

    def test_missing_context_when_neither_provided(self):
        # Verify the missing_context list names both keys
        result = RevisionSummarizer().summarize()
        assert "comparison_result" in result.missing_context
        assert "changeset" in result.missing_context

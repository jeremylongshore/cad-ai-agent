"""Integration tests for paper space editing (full pipeline)."""

from __future__ import annotations

from cad_dxf_agent.core.dxf_reader import load_dxf
from cad_dxf_agent.core.edit_engine import EditEngine
from cad_dxf_agent.core.revision_notes import insert_revision_note
from cad_dxf_agent.core.validators import validate_changeset
from cad_dxf_agent.models.config_schema import RevisionNoteConfig, RuleConfig
from cad_dxf_agent.models.ops_schema import ChangeSet, EditOperation, OpType
from tests.helpers.dxf_factory import create_drawing_with_layout


class TestPaperSpacePipelineIntegration:
    """Full pipeline tests for layout-targeted edits."""

    def test_move_in_layout_full_pipeline(self, tmp_path):
        """Load → validate → apply move in layout → save → reload → verify."""
        dxf = create_drawing_with_layout(tmp_path)
        ctx = load_dxf(dxf)
        rules = RuleConfig()

        # Find a layout entity
        layout_text = next(
            e for e in ctx.entities if e.space == "Sheet1" and e.text_content == "Layout Note"
        )

        changeset = ChangeSet(
            operations=[
                EditOperation(
                    op_type=OpType.MOVE_ENTITY,
                    target_handle=layout_text.handle,
                    target_layer=layout_text.layer,
                    target_space="Sheet1",
                    params={"dx": 20.0, "dy": 10.0},
                )
            ],
            prompt="Move layout note east and north",
        )

        # Validate
        validation = validate_changeset(changeset, ctx, rules)
        assert validation.valid

        # Apply
        engine = EditEngine(dxf)
        results = engine.apply_changeset(changeset)
        assert all(r.success for r in results)

        # Save
        out = tmp_path / "output.dxf"
        engine.save(out)

        # Reload and verify
        reloaded = load_dxf(out)
        moved = reloaded.get_entity_by_handle(layout_text.handle)
        assert moved is not None
        assert moved.space == "Sheet1"
        assert abs(moved.insert_point.x - 25.0) < 0.1  # 5 + 20
        assert abs(moved.insert_point.y - 15.0) < 0.1  # 5 + 10

    def test_delete_in_layout_with_revision_note(self, tmp_path):
        """Delete layout entity → insert revision note in same layout."""
        dxf = create_drawing_with_layout(tmp_path)
        ctx = load_dxf(dxf)

        layout_text = next(
            e for e in ctx.entities if e.space == "Sheet1" and e.text_content == "Layout Note"
        )

        changeset = ChangeSet(
            operations=[
                EditOperation(
                    op_type=OpType.DELETE_ENTITY,
                    target_handle=layout_text.handle,
                    target_layer=layout_text.layer,
                    target_space="Sheet1",
                )
            ],
            prompt="Delete layout note",
        )

        engine = EditEngine(dxf)
        results = engine.apply_changeset(changeset)
        assert results[0].success

        edited_path = tmp_path / "edited.dxf"
        engine.save(edited_path)

        # Insert revision note in same layout
        config = RevisionNoteConfig()
        final_path = tmp_path / "final.dxf"
        note_text = insert_revision_note(
            edited_path, final_path, results, config, layout_name="Sheet1"
        )
        assert "Deleted entity" in note_text

        # Verify: layout has note but no longer has the deleted text
        reloaded = load_dxf(final_path)
        sheet_entities = [e for e in reloaded.entities if e.space == "Sheet1"]
        deleted_still = [e for e in sheet_entities if e.text_content == "Layout Note"]
        assert len(deleted_still) == 0
        rev_notes = [e for e in sheet_entities if e.layer == config.layer_name]
        assert len(rev_notes) >= 1

    def test_multi_space_changeset(self, tmp_path):
        """A changeset with ops in both model and layout spaces."""
        dxf = create_drawing_with_layout(tmp_path)
        ctx = load_dxf(dxf)
        rules = RuleConfig()

        model_text = next(
            e for e in ctx.entities if e.space == "Model" and e.text_content == "Model Note"
        )
        layout_text = next(
            e for e in ctx.entities if e.space == "Sheet1" and e.text_content == "Layout Note"
        )

        changeset = ChangeSet(
            operations=[
                EditOperation(
                    op_type=OpType.EDIT_TEXT,
                    target_handle=model_text.handle,
                    target_layer=model_text.layer,
                    target_space="Model",
                    params={"new_text": "Updated Model"},
                ),
                EditOperation(
                    op_type=OpType.EDIT_TEXT,
                    target_handle=layout_text.handle,
                    target_layer=layout_text.layer,
                    target_space="Sheet1",
                    params={"new_text": "Updated Layout"},
                ),
            ],
            prompt="Edit text in both spaces",
        )

        validation = validate_changeset(changeset, ctx, rules)
        assert validation.valid

        engine = EditEngine(dxf)
        results = engine.apply_changeset(changeset)
        assert all(r.success for r in results)

        out = tmp_path / "multi_space.dxf"
        engine.save(out)

        reloaded = load_dxf(out)
        assert reloaded.get_entity_by_handle(model_text.handle).text_content == "Updated Model"
        assert reloaded.get_entity_by_handle(layout_text.handle).text_content == "Updated Layout"

"""Tests for paper space / layout editing support."""

from __future__ import annotations

import pytest

from cad_dxf_agent.core.dxf_reader import load_dxf
from cad_dxf_agent.core.edit_engine import EditEngine
from cad_dxf_agent.core.revision_notes import insert_revision_note
from cad_dxf_agent.models.config_schema import RevisionNoteConfig
from cad_dxf_agent.models.ops_schema import AppliedChange, ChangeSet, EditOperation, OpType
from tests.helpers.dxf_factory import create_drawing_with_layout


@pytest.fixture
def layout_dxf(tmp_path):
    """DXF with model space + paper space layout entities."""
    return create_drawing_with_layout(tmp_path, layout_name="Sheet1")


@pytest.fixture
def layout_context(layout_dxf):
    """DrawingContext loaded from the layout DXF."""
    return load_dxf(layout_dxf)


class TestDxfReaderLayouts:
    """Verify dxf_reader loads both model and layout entities."""

    def test_layout_entities_loaded(self, layout_context):
        """Entities from the named layout are present in the context."""
        layout_entities = [e for e in layout_context.entities if e.space == "Sheet1"]
        assert len(layout_entities) == 3  # text, line, mtext

    def test_model_entities_loaded(self, layout_context):
        """Model space entities are still loaded correctly."""
        model_entities = [e for e in layout_context.entities if e.space == "Model"]
        assert len(model_entities) >= 4  # 2 lines, 1 text, 1 insert

    def test_layout_info_present(self, layout_context):
        """LayoutInfo is generated for both Model and Sheet1."""
        names = {lay.name for lay in layout_context.layouts}
        assert "Model" in names
        assert "Sheet1" in names

    def test_layout_entity_count(self, layout_context):
        """LayoutInfo tracks correct entity count per layout."""
        sheet_info = next(lay for lay in layout_context.layouts if lay.name == "Sheet1")
        assert sheet_info.entity_count == 3

    def test_entity_space_field(self, layout_context):
        """Each entity carries the correct space field."""
        layout_text = [
            e
            for e in layout_context.entities
            if e.space == "Sheet1" and e.text_content == "Layout Note"
        ]
        assert len(layout_text) == 1


class TestEditEngineLayoutSupport:
    """Verify EditEngine can edit entities in paper space layouts."""

    def test_move_layout_entity(self, layout_dxf, layout_context, tmp_path):
        """Move an entity in a named layout — position changes."""
        # Find the layout text entity
        layout_text = next(
            e
            for e in layout_context.entities
            if e.space == "Sheet1" and e.text_content == "Layout Note"
        )

        engine = EditEngine(layout_dxf)
        changeset = ChangeSet(
            operations=[
                EditOperation(
                    op_type=OpType.MOVE_ENTITY,
                    target_handle=layout_text.handle,
                    target_layer=layout_text.layer,
                    target_space="Sheet1",
                    params={"dx": 10.0, "dy": 5.0},
                )
            ],
            prompt="Move layout text",
        )
        results = engine.apply_changeset(changeset)
        assert results[0].success

        # Save and reload to verify position changed
        out = tmp_path / "moved.dxf"
        engine.save(out)
        reloaded = load_dxf(out)
        moved = reloaded.get_entity_by_handle(layout_text.handle)
        assert moved is not None
        assert moved.insert_point is not None
        assert abs(moved.insert_point.x - 15.0) < 0.1  # 5 + 10
        assert abs(moved.insert_point.y - 10.0) < 0.1  # 5 + 5

    def test_edit_text_layout_entity(self, layout_dxf, layout_context, tmp_path):
        """Edit text on a layout TEXT entity."""
        layout_text = next(
            e
            for e in layout_context.entities
            if e.space == "Sheet1" and e.text_content == "Layout Note"
        )

        engine = EditEngine(layout_dxf)
        changeset = ChangeSet(
            operations=[
                EditOperation(
                    op_type=OpType.EDIT_TEXT,
                    target_handle=layout_text.handle,
                    target_layer=layout_text.layer,
                    target_space="Sheet1",
                    params={"new_text": "Updated Layout Note"},
                )
            ],
            prompt="Edit layout text",
        )
        results = engine.apply_changeset(changeset)
        assert results[0].success

        out = tmp_path / "edited.dxf"
        engine.save(out)
        reloaded = load_dxf(out)
        edited = reloaded.get_entity_by_handle(layout_text.handle)
        assert edited is not None
        assert edited.text_content == "Updated Layout Note"

    def test_delete_layout_entity(self, layout_dxf, layout_context, tmp_path):
        """Delete an entity from a paper space layout."""
        layout_text = next(
            e
            for e in layout_context.entities
            if e.space == "Sheet1" and e.text_content == "Layout Note"
        )

        engine = EditEngine(layout_dxf)
        changeset = ChangeSet(
            operations=[
                EditOperation(
                    op_type=OpType.DELETE_ENTITY,
                    target_handle=layout_text.handle,
                    target_layer=layout_text.layer,
                    target_space="Sheet1",
                )
            ],
            prompt="Delete layout text",
        )
        results = engine.apply_changeset(changeset)
        assert results[0].success

        out = tmp_path / "deleted.dxf"
        engine.save(out)
        reloaded = load_dxf(out)
        # Entity count in Sheet1 should be reduced
        sheet_entities = [e for e in reloaded.entities if e.space == "Sheet1"]
        assert len(sheet_entities) == 2  # was 3, now 2

    def test_add_block_to_layout(self, layout_dxf, layout_context, tmp_path):
        """Insert a block reference into a paper space layout."""
        engine = EditEngine(layout_dxf)
        changeset = ChangeSet(
            operations=[
                EditOperation(
                    op_type=OpType.ADD_BLOCK,
                    target_layer="STRUCTURAL",
                    target_space="Sheet1",
                    params={
                        "block_name": "COLUMN_MARK",
                        "insert_point": {"x": 100, "y": 100},
                    },
                )
            ],
            prompt="Add block to layout",
        )
        results = engine.apply_changeset(changeset)
        assert results[0].success

        out = tmp_path / "block_added.dxf"
        engine.save(out)
        reloaded = load_dxf(out)
        sheet_entities = [e for e in reloaded.entities if e.space == "Sheet1"]
        assert len(sheet_entities) == 4  # was 3, now 4

    def test_model_space_unaffected_by_layout_edit(self, layout_dxf, layout_context, tmp_path):
        """Editing layout entities does not change model space entity count."""
        model_before = len([e for e in layout_context.entities if e.space == "Model"])

        layout_text = next(
            e
            for e in layout_context.entities
            if e.space == "Sheet1" and e.text_content == "Layout Note"
        )

        engine = EditEngine(layout_dxf)
        changeset = ChangeSet(
            operations=[
                EditOperation(
                    op_type=OpType.DELETE_ENTITY,
                    target_handle=layout_text.handle,
                    target_layer=layout_text.layer,
                    target_space="Sheet1",
                )
            ],
            prompt="Delete layout entity",
        )
        engine.apply_changeset(changeset)

        out = tmp_path / "isolation.dxf"
        engine.save(out)
        reloaded = load_dxf(out)
        model_after = len([e for e in reloaded.entities if e.space == "Model"])
        assert model_after == model_before

    def test_invalid_layout_name_fails(self, layout_dxf):
        """Targeting a nonexistent layout fails gracefully."""
        engine = EditEngine(layout_dxf)
        changeset = ChangeSet(
            operations=[
                EditOperation(
                    op_type=OpType.DELETE_ENTITY,
                    target_handle="FAKE",
                    target_layer="NOTES",
                    target_space="NonExistentLayout",
                )
            ],
            prompt="Bad layout",
        )
        results = engine.apply_changeset(changeset)
        assert not results[0].success


class TestRevisionNotesLayout:
    """Verify revision notes can be inserted into paper space layouts."""

    def test_revision_note_in_layout(self, layout_dxf, tmp_path):
        """Revision note is inserted into the named layout, not model space."""
        config = RevisionNoteConfig()
        changes = [
            AppliedChange(
                operation=EditOperation(
                    op_type=OpType.MOVE_ENTITY,
                    target_handle="ABC",
                    target_space="Sheet1",
                    params={"dx": 10, "dy": 0},
                ),
                success=True,
                entity_handle="ABC",
                description="Moved entity",
            )
        ]

        out = tmp_path / "rev_note.dxf"
        note_text = insert_revision_note(
            layout_dxf, out, changes, config, layout_name="Sheet1"
        )
        assert "Moved entity" in note_text

        # Verify note is in the layout
        reloaded = load_dxf(out)
        sheet_entities = [e for e in reloaded.entities if e.space == "Sheet1"]
        note_entities = [
            e for e in sheet_entities if e.layer == config.layer_name
        ]
        assert len(note_entities) >= 1

    def test_revision_note_default_model_space(self, layout_dxf, tmp_path):
        """Default layout_name='Model' puts note in model space."""
        config = RevisionNoteConfig()
        changes = [
            AppliedChange(
                operation=EditOperation(
                    op_type=OpType.MOVE_ENTITY,
                    target_handle="ABC",
                    params={"dx": 10, "dy": 0},
                ),
                success=True,
                entity_handle="ABC",
                description="Moved entity",
            )
        ]

        out = tmp_path / "rev_note_model.dxf"
        insert_revision_note(layout_dxf, out, changes, config)

        reloaded = load_dxf(out)
        model_notes = [
            e
            for e in reloaded.entities
            if e.space == "Model" and e.layer == config.layer_name
        ]
        assert len(model_notes) >= 1

    def test_revision_note_invalid_layout_falls_back(self, layout_dxf, tmp_path):
        """Invalid layout name falls back to model space."""
        config = RevisionNoteConfig()
        changes = [
            AppliedChange(
                operation=EditOperation(
                    op_type=OpType.MOVE_ENTITY,
                    target_handle="ABC",
                    params={"dx": 10, "dy": 0},
                ),
                success=True,
                entity_handle="ABC",
                description="Moved entity",
            )
        ]

        out = tmp_path / "rev_fallback.dxf"
        insert_revision_note(
            layout_dxf, out, changes, config, layout_name="NoSuchLayout"
        )

        reloaded = load_dxf(out)
        model_notes = [
            e
            for e in reloaded.entities
            if e.space == "Model" and e.layer == config.layer_name
        ]
        assert len(model_notes) >= 1


class TestToolExecutorSpaceAwareness:
    """Verify ToolExecutor propagates space to operations and results."""

    def test_entity_dict_includes_space(self, layout_context):
        """_entity_to_dict includes space field."""
        from cad_dxf_agent.llm.tool_executor import _entity_to_dict

        layout_entity = next(
            e for e in layout_context.entities if e.space == "Sheet1"
        )
        result = _entity_to_dict(layout_entity)
        assert result["space"] == "Sheet1"

    def test_find_entities_returns_space(self, layout_context):
        """find_entities tool results include space for each entity."""
        from cad_dxf_agent.llm.tool_executor import ToolExecutor
        from cad_dxf_agent.settings import settings

        executor = ToolExecutor(layout_context, settings.protected_layers)
        result = executor.execute("find_entities", {"layer": "NOTES"})
        spaces = {e["space"] for e in result["entities"]}
        assert "Sheet1" in spaces
        assert "Model" in spaces

    def test_move_propagates_space(self, layout_context):
        """move_entity sets target_space from entity's space."""
        from cad_dxf_agent.llm.tool_executor import ToolExecutor
        from cad_dxf_agent.settings import settings

        layout_entity = next(
            e
            for e in layout_context.entities
            if e.space == "Sheet1" and e.text_content == "Layout Note"
        )

        executor = ToolExecutor(layout_context, settings.protected_layers)
        executor.execute(
            "move_entity", {"handle": layout_entity.handle, "dx": 5, "dy": 5}
        )

        ops = executor.operations
        assert len(ops) == 1
        assert ops[0].target_space == "Sheet1"

    def test_delete_propagates_space(self, layout_context):
        """delete_entity sets target_space from entity's space."""
        from cad_dxf_agent.llm.tool_executor import ToolExecutor
        from cad_dxf_agent.settings import settings

        layout_entity = next(
            e
            for e in layout_context.entities
            if e.space == "Sheet1" and e.text_content == "Layout Note"
        )

        executor = ToolExecutor(layout_context, settings.protected_layers)
        executor.execute("delete_entity", {"handle": layout_entity.handle})

        ops = executor.operations
        assert len(ops) == 1
        assert ops[0].target_space == "Sheet1"

"""Integration tests closing coverage gaps identified in the test audit.

Gaps addressed:
1. Move coordinate verification after save + reload
2. add_block through engine + save + reload
3. Agent loop (ScriptedAgentProvider) → engine → file
4. Undo/redo → save → reload round-trip
5. Revision note content per op type
6. Save-as contract: original file byte-identical after pipeline
"""

from __future__ import annotations

import hashlib
from pathlib import Path

import ezdxf
import pytest

from cad_dxf_agent.core.dxf_reader import load_dxf
from cad_dxf_agent.core.dxf_writer import copy_dxf_for_editing
from cad_dxf_agent.core.edit_engine import EditEngine
from cad_dxf_agent.core.edit_history import EditHistory
from cad_dxf_agent.core.revision_notes import insert_revision_note
from cad_dxf_agent.core.semantic_model import build_planner_context
from cad_dxf_agent.core.validators import validate_changeset
from cad_dxf_agent.models.config_schema import RevisionNoteConfig, RuleConfig
from cad_dxf_agent.models.ops_schema import ChangeSet, EditOperation, OpType
from tests.helpers.scripted_provider import ScriptedAgentProvider


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


# ---------------------------------------------------------------------------
# Gap 1: Move coordinate verification after save + reload
# ---------------------------------------------------------------------------


@pytest.mark.integration
class TestMoveCoordinateVerification:
    def test_move_coordinates_verified_after_reload(self, sample_dxf, tmp_path):
        """Move op produces correct coordinates in reloaded DXF."""
        context = load_dxf(sample_dxf)

        # Find an INSERT entity — has a clear insert point we can verify
        insert_entity = next(
            e
            for e in context.entities
            if e.entity_type == "INSERT"
            and e.layer.upper() not in ("TITLE", "TITLEBLOCK", "SEAL", "REVISION")
        )

        # Read original position
        doc_before = ezdxf.readfile(str(sample_dxf))
        ent_before = doc_before.entitydb.get(insert_entity.handle)
        orig_x = ent_before.dxf.insert.x
        orig_y = ent_before.dxf.insert.y

        dx, dy = 15.0, 10.0
        cs = ChangeSet(
            prompt="move for coordinate check",
            operations=[
                EditOperation(
                    op_type=OpType.MOVE_ENTITY,
                    target_handle=insert_entity.handle,
                    params={"dx": dx, "dy": dy},
                )
            ],
        )
        rules = RuleConfig()
        validation = validate_changeset(cs, context, rules)
        assert validation.valid

        work = copy_dxf_for_editing(sample_dxf, tmp_path / "work.dxf")
        engine = EditEngine(work)
        results = engine.apply_changeset(cs)
        assert results[0].success

        output = tmp_path / "moved.dxf"
        engine.save(output)

        # Reload and verify exact coordinates
        doc_after = ezdxf.readfile(str(output))
        ent_after = doc_after.entitydb.get(insert_entity.handle)
        assert ent_after is not None
        assert abs(ent_after.dxf.insert.x - (orig_x + dx)) < 0.01
        assert abs(ent_after.dxf.insert.y - (orig_y + dy)) < 0.01

    def test_move_line_endpoints_verified(self, sample_dxf, tmp_path):
        """Move op shifts LINE endpoints correctly after save + reload."""
        context = load_dxf(sample_dxf)
        line_entity = next(
            e
            for e in context.entities
            if e.entity_type == "LINE"
            and e.layer.upper() not in ("TITLE", "TITLEBLOCK", "SEAL", "REVISION")
        )

        doc_before = ezdxf.readfile(str(sample_dxf))
        ent_before = doc_before.entitydb.get(line_entity.handle)
        orig_start_x = ent_before.dxf.start.x
        orig_start_y = ent_before.dxf.start.y
        orig_end_x = ent_before.dxf.end.x
        orig_end_y = ent_before.dxf.end.y

        dx, dy = -5.0, 20.0
        cs = ChangeSet(
            prompt="move line",
            operations=[
                EditOperation(
                    op_type=OpType.MOVE_ENTITY,
                    target_handle=line_entity.handle,
                    params={"dx": dx, "dy": dy},
                )
            ],
        )
        rules = RuleConfig()
        assert validate_changeset(cs, context, rules).valid

        work = copy_dxf_for_editing(sample_dxf, tmp_path / "work.dxf")
        engine = EditEngine(work)
        assert engine.apply_changeset(cs)[0].success

        output = tmp_path / "moved_line.dxf"
        engine.save(output)

        doc_after = ezdxf.readfile(str(output))
        ent_after = doc_after.entitydb.get(line_entity.handle)
        assert abs(ent_after.dxf.start.x - (orig_start_x + dx)) < 0.01
        assert abs(ent_after.dxf.start.y - (orig_start_y + dy)) < 0.01
        assert abs(ent_after.dxf.end.x - (orig_end_x + dx)) < 0.01
        assert abs(ent_after.dxf.end.y - (orig_end_y + dy)) < 0.01


# ---------------------------------------------------------------------------
# Gap 2: add_block through engine + save + reload
# ---------------------------------------------------------------------------


@pytest.mark.integration
class TestAddBlockFullPipeline:
    def test_add_block_appears_in_reloaded_dxf(self, sample_dxf, tmp_path):
        """add_block inserts a new INSERT entity visible after save + reload."""
        context = load_dxf(sample_dxf)

        doc_before = ezdxf.readfile(str(sample_dxf))
        inserts_before = [
            e
            for e in doc_before.modelspace()
            if e.dxftype() == "INSERT" and e.dxf.name == "COLUMN_MARK"
        ]

        cs = ChangeSet(
            prompt="add block",
            operations=[
                EditOperation(
                    op_type=OpType.ADD_BLOCK,
                    params={
                        "block_name": "COLUMN_MARK",
                        "insert_point": {"x": 75.0, "y": 75.0},
                    },
                )
            ],
        )
        rules = RuleConfig()
        validation = validate_changeset(cs, context, rules)
        assert validation.valid

        work = copy_dxf_for_editing(sample_dxf, tmp_path / "work.dxf")
        engine = EditEngine(work)
        results = engine.apply_changeset(cs)
        assert results[0].success
        assert results[0].entity_handle is not None

        output = tmp_path / "added_block.dxf"
        engine.save(output)

        # Reload and count INSERT entities
        doc_after = ezdxf.readfile(str(output))
        inserts_after = [
            e
            for e in doc_after.modelspace()
            if e.dxftype() == "INSERT" and e.dxf.name == "COLUMN_MARK"
        ]
        assert len(inserts_after) == len(inserts_before) + 1

        # Verify the new one is at the right position
        new_insert = doc_after.entitydb.get(results[0].entity_handle)
        assert new_insert is not None
        assert abs(new_insert.dxf.insert.x - 75.0) < 0.01
        assert abs(new_insert.dxf.insert.y - 75.0) < 0.01

    def test_add_block_nonexistent_block_fails(self, sample_dxf, tmp_path):
        """add_block with unknown block name fails gracefully."""
        work = copy_dxf_for_editing(sample_dxf, tmp_path / "work.dxf")
        engine = EditEngine(work)

        cs = ChangeSet(
            prompt="add missing block",
            operations=[
                EditOperation(
                    op_type=OpType.ADD_BLOCK,
                    params={
                        "block_name": "NONEXISTENT_BLOCK_XYZ",
                        "insert_point": {"x": 0, "y": 0},
                    },
                )
            ],
        )
        results = engine.apply_changeset(cs)
        assert not results[0].success
        assert "not found" in results[0].description.lower()


# ---------------------------------------------------------------------------
# Gap 3: Agent loop → engine → file
# ---------------------------------------------------------------------------


@pytest.mark.integration
class TestAgentLoopToFile:
    def test_scripted_move_applied_and_saved(self, sample_dxf, tmp_path):
        """ScriptedAgentProvider → validate → apply → save → reload → verify."""
        context = load_dxf(sample_dxf)
        planner_ctx = build_planner_context(context)

        editable = next(
            e
            for e in context.entities
            if e.entity_type == "INSERT"
            and e.layer.upper() not in ("TITLE", "TITLEBLOCK", "SEAL", "REVISION")
        )

        doc_before = ezdxf.readfile(str(sample_dxf))
        orig_x = doc_before.entitydb.get(editable.handle).dxf.insert.x

        provider = ScriptedAgentProvider(
            turns=[
                [("find_entities", {"layer": "STRUCTURAL"})],
                [("move_entity", {"handle": editable.handle, "dx": 24.0, "dy": 0.0})],
            ]
        )
        changeset = provider.plan("Move column east by 2 feet", planner_ctx)
        assert changeset.op_count == 1

        rules = RuleConfig()
        validation = validate_changeset(changeset, context, rules)
        assert validation.valid

        work = copy_dxf_for_editing(sample_dxf, tmp_path / "work.dxf")
        engine = EditEngine(work)
        results = engine.apply_changeset(changeset)
        assert all(r.success for r in results)

        output = tmp_path / "agent_output.dxf"
        engine.save(output)

        # Reload and verify the move landed
        doc_after = ezdxf.readfile(str(output))
        ent_after = doc_after.entitydb.get(editable.handle)
        assert abs(ent_after.dxf.insert.x - (orig_x + 24.0)) < 0.01

    def test_scripted_edit_text_applied_and_saved(self, sample_dxf, tmp_path):
        """ScriptedAgentProvider edit_text → save → reload → verify text."""
        context = load_dxf(sample_dxf)
        planner_ctx = build_planner_context(context)

        text_entity = next(
            e
            for e in context.entities
            if e.entity_type == "TEXT"
            and e.layer.upper() not in ("TITLE", "TITLEBLOCK", "SEAL", "REVISION")
        )

        provider = ScriptedAgentProvider(
            turns=[
                [("find_entities", {"layer": "NOTES"})],
                [("edit_text", {"handle": text_entity.handle, "new_text": "RENAMED"})],
            ]
        )
        changeset = provider.plan("Rename column label", planner_ctx)
        assert changeset.op_count == 1

        rules = RuleConfig()
        assert validate_changeset(changeset, context, rules).valid

        work = copy_dxf_for_editing(sample_dxf, tmp_path / "work.dxf")
        engine = EditEngine(work)
        results = engine.apply_changeset(changeset)
        assert results[0].success

        output = tmp_path / "agent_text_output.dxf"
        engine.save(output)

        doc_after = ezdxf.readfile(str(output))
        ent = doc_after.entitydb.get(text_entity.handle)
        assert ent.dxf.text == "RENAMED"


# ---------------------------------------------------------------------------
# Gap 4: Undo/redo → save → reload round-trip
# ---------------------------------------------------------------------------


@pytest.mark.integration
class TestUndoRedoSaveReload:
    def test_undo_save_reload_matches_original(self, sample_dxf, tmp_path):
        """Apply edit → undo → save → reload → text matches original."""
        work = copy_dxf_for_editing(sample_dxf, tmp_path / "work.dxf")

        doc = ezdxf.readfile(str(work))
        text_entity = next(
            e for e in doc.modelspace() if e.dxftype() == "TEXT" and e.dxf.text == "Column C-4"
        )
        text_handle = text_entity.dxf.handle

        history = EditHistory(work)

        # Apply edit
        engine = EditEngine(work)
        cs = ChangeSet(
            prompt="edit text",
            operations=[
                EditOperation(
                    op_type=OpType.EDIT_TEXT,
                    target_handle=text_handle,
                    params={"new_text": "CHANGED-TEXT"},
                )
            ],
        )
        engine.apply_changeset(cs)
        history.push(engine.doc, "edit")

        # Undo
        restored_doc = history.undo()
        assert restored_doc is not None

        # Save the undone state
        undo_path = tmp_path / "undone.dxf"
        restored_doc.saveas(str(undo_path))

        # Reload and verify original text is back
        doc_reloaded = ezdxf.readfile(str(undo_path))
        ent = doc_reloaded.entitydb.get(text_handle)
        assert ent is not None
        assert ent.dxf.text == "Column C-4"

    def test_redo_save_reload_matches_edit(self, sample_dxf, tmp_path):
        """Apply → undo → redo → save → reload → text matches edit."""
        work = copy_dxf_for_editing(sample_dxf, tmp_path / "work.dxf")

        doc = ezdxf.readfile(str(work))
        text_entity = next(
            e for e in doc.modelspace() if e.dxftype() == "TEXT" and e.dxf.text == "Column C-4"
        )
        text_handle = text_entity.dxf.handle

        history = EditHistory(work)

        engine = EditEngine(work)
        cs = ChangeSet(
            prompt="edit",
            operations=[
                EditOperation(
                    op_type=OpType.EDIT_TEXT,
                    target_handle=text_handle,
                    params={"new_text": "REDO-TEST"},
                )
            ],
        )
        engine.apply_changeset(cs)
        history.push(engine.doc, "edit")

        history.undo()
        redone_doc = history.redo()
        assert redone_doc is not None

        redo_path = tmp_path / "redone.dxf"
        redone_doc.saveas(str(redo_path))

        doc_reloaded = ezdxf.readfile(str(redo_path))
        ent = doc_reloaded.entitydb.get(text_handle)
        assert ent.dxf.text == "REDO-TEST"


# ---------------------------------------------------------------------------
# Gap 5: Revision note content per op type
# ---------------------------------------------------------------------------


@pytest.mark.integration
class TestRevisionNoteContent:
    def _apply_and_get_note(self, sample_dxf, tmp_path, cs):
        """Apply changeset, insert revision note, return note text."""
        work = copy_dxf_for_editing(sample_dxf, tmp_path / "work.dxf")
        engine = EditEngine(work)
        results = engine.apply_changeset(cs)
        assert all(r.success for r in results)

        edited = tmp_path / "edited.dxf"
        engine.save(edited)

        config = RevisionNoteConfig()
        final = tmp_path / "final.dxf"
        note_text = insert_revision_note(edited, final, results, config)
        return note_text

    def test_move_note_contains_direction(self, sample_dxf, tmp_path):
        """Revision note for move contains cardinal direction."""
        context = load_dxf(sample_dxf)
        editable = next(
            e
            for e in context.entities
            if e.layer.upper() not in ("TITLE", "TITLEBLOCK", "SEAL", "REVISION")
        )
        cs = ChangeSet(
            prompt="move",
            operations=[
                EditOperation(
                    op_type=OpType.MOVE_ENTITY,
                    target_handle=editable.handle,
                    params={"dx": 0, "dy": 24.0},
                )
            ],
        )
        note = self._apply_and_get_note(sample_dxf, tmp_path, cs)
        assert "Moved entity" in note
        assert "north" in note

    def test_delete_note_contains_deleted(self, sample_dxf, tmp_path):
        """Revision note for delete says 'Deleted entity'."""
        context = load_dxf(sample_dxf)
        editable = next(
            e
            for e in context.entities
            if e.layer.upper() not in ("TITLE", "TITLEBLOCK", "SEAL", "REVISION")
        )
        cs = ChangeSet(
            prompt="delete",
            operations=[
                EditOperation(
                    op_type=OpType.DELETE_ENTITY,
                    target_handle=editable.handle,
                )
            ],
        )
        note = self._apply_and_get_note(sample_dxf, tmp_path, cs)
        assert "Deleted entity" in note

    def test_edit_text_note_contains_new_text(self, sample_dxf, tmp_path):
        """Revision note for edit_text includes the new text value."""
        context = load_dxf(sample_dxf)
        text_entity = next(
            e
            for e in context.entities
            if e.entity_type == "TEXT"
            and e.layer.upper() not in ("TITLE", "TITLEBLOCK", "SEAL", "REVISION")
        )
        cs = ChangeSet(
            prompt="rename",
            operations=[
                EditOperation(
                    op_type=OpType.EDIT_TEXT,
                    target_handle=text_entity.handle,
                    params={"new_text": "NEW-LABEL-42"},
                )
            ],
        )
        note = self._apply_and_get_note(sample_dxf, tmp_path, cs)
        assert "Updated text" in note
        assert "NEW-LABEL-42" in note

    def test_add_block_note_contains_block_name(self, sample_dxf, tmp_path):
        """Revision note for add_block includes the block name."""
        cs = ChangeSet(
            prompt="add",
            operations=[
                EditOperation(
                    op_type=OpType.ADD_BLOCK,
                    params={
                        "block_name": "COLUMN_MARK",
                        "insert_point": {"x": 50, "y": 50},
                    },
                )
            ],
        )
        note = self._apply_and_get_note(sample_dxf, tmp_path, cs)
        assert "Inserted block" in note
        assert "COLUMN_MARK" in note


# ---------------------------------------------------------------------------
# Gap 6: Save-as contract — original file untouched at integration level
# ---------------------------------------------------------------------------


@pytest.mark.integration
class TestSaveAsContract:
    def test_original_file_unchanged_after_full_pipeline(self, sample_dxf, tmp_path):
        """Original DXF is byte-identical after pipeline edits."""
        original_hash = _sha256(sample_dxf)

        context = load_dxf(sample_dxf)
        editable = next(
            e
            for e in context.entities
            if e.layer.upper() not in ("TITLE", "TITLEBLOCK", "SEAL", "REVISION")
        )

        cs = ChangeSet(
            prompt="move for save-as test",
            operations=[
                EditOperation(
                    op_type=OpType.MOVE_ENTITY,
                    target_handle=editable.handle,
                    params={"dx": 100, "dy": 100},
                )
            ],
        )
        rules = RuleConfig()
        assert validate_changeset(cs, context, rules).valid

        work = copy_dxf_for_editing(sample_dxf, tmp_path / "work.dxf")
        engine = EditEngine(work)
        engine.apply_changeset(cs)

        output = tmp_path / "output.dxf"
        engine.save(output)

        config = RevisionNoteConfig()
        final = tmp_path / "final.dxf"
        insert_revision_note(output, final, engine.applied_changes, config)

        # Original must be byte-identical
        assert _sha256(sample_dxf) == original_hash
        # Output must be different from original
        assert _sha256(final) != original_hash

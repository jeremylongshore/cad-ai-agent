"""Tests for revision note generation."""

from __future__ import annotations

from cad_dxf_agent.core.revision_notes import generate_note_text
from cad_dxf_agent.models.config_schema import RevisionNoteConfig
from cad_dxf_agent.models.ops_schema import AppliedChange, EditOperation, OpType


class TestNoteGeneration:
    def test_move_note(self):
        config = RevisionNoteConfig(revision_number=8)
        changes = [
            AppliedChange(
                operation=EditOperation(
                    op_type=OpType.MOVE_ENTITY,
                    target_handle="A1",
                    params={"dx": 24.0, "dy": 0.0},
                ),
                success=True,
                entity_handle="A1",
                description="Moved entity A1",
            )
        ]

        note = generate_note_text(changes, config)
        assert note.startswith("REV 8")
        assert "Moved" in note or "east" in note.lower()

    def test_edit_text_note(self):
        config = RevisionNoteConfig(revision_number=3)
        changes = [
            AppliedChange(
                operation=EditOperation(
                    op_type=OpType.EDIT_TEXT,
                    target_handle="B2",
                    params={"new_text": "Updated Label"},
                ),
                success=True,
                entity_handle="B2",
            )
        ]

        note = generate_note_text(changes, config)
        assert note.startswith("REV 3")
        assert "text" in note.lower() or "Updated" in note

    def test_delete_note(self):
        config = RevisionNoteConfig(revision_number=1)
        changes = [
            AppliedChange(
                operation=EditOperation(
                    op_type=OpType.DELETE_ENTITY,
                    target_handle="C3",
                ),
                success=True,
                entity_handle="C3",
            )
        ]

        note = generate_note_text(changes, config)
        assert note.startswith("REV 1")
        assert "Deleted" in note

    def test_no_changes(self):
        config = RevisionNoteConfig(revision_number=1)
        note = generate_note_text([], config)
        assert "No changes" in note

    def test_failed_changes_only(self):
        config = RevisionNoteConfig(revision_number=1)
        changes = [
            AppliedChange(
                operation=EditOperation(op_type=OpType.MOVE_ENTITY, target_handle="X"),
                success=False,
            )
        ]
        note = generate_note_text(changes, config)
        assert "No successful" in note

    def test_multiple_changes(self):
        config = RevisionNoteConfig(revision_number=5)
        changes = [
            AppliedChange(
                operation=EditOperation(
                    op_type=OpType.MOVE_ENTITY,
                    target_handle="A1",
                    params={"dx": 24.0, "dy": 0.0},
                ),
                success=True,
            ),
            AppliedChange(
                operation=EditOperation(
                    op_type=OpType.DELETE_ENTITY,
                    target_handle="B2",
                ),
                success=True,
            ),
        ]

        note = generate_note_text(changes, config)
        assert note.startswith("REV 5")
        assert ";" in note  # Multiple summaries joined

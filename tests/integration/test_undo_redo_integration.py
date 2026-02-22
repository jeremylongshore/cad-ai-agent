"""Integration tests for undo/redo with the EditHistory + EditEngine pipeline."""

from __future__ import annotations

import ezdxf
import pytest

from cad_dxf_agent.core.dxf_writer import copy_dxf_for_editing
from cad_dxf_agent.core.edit_engine import EditEngine
from cad_dxf_agent.core.edit_history import EditHistory
from cad_dxf_agent.models.ops_schema import ChangeSet, EditOperation, OpType


def _get_text_value(doc, handle):
    """Get the text value of a TEXT entity by handle."""
    entity = doc.entitydb.get(handle)
    if entity is None:
        return None
    return entity.dxf.text


def _find_text_handle(dxf_path, text_content):
    """Find handle of TEXT entity with given content."""
    doc = ezdxf.readfile(str(dxf_path))
    for e in doc.modelspace():
        if e.dxftype() == "TEXT" and e.dxf.text == text_content:
            return e.dxf.handle
    return None


@pytest.mark.integration
class TestUndoRedoIntegration:
    def test_apply_then_undo_restores_original(self, sample_dxf, tmp_path):
        """Apply an edit, then undo restores the original text."""
        work = copy_dxf_for_editing(sample_dxf, tmp_path / "work.dxf")
        handle = _find_text_handle(work, "Column C-4")
        assert handle is not None

        history = EditHistory(work)

        # Apply edit
        engine = EditEngine(work)
        cs = ChangeSet(
            prompt="edit text",
            operations=[
                EditOperation(
                    op_type=OpType.EDIT_TEXT,
                    target_handle=handle,
                    params={"new_text": "CHANGED"},
                )
            ],
        )
        engine.apply_changeset(cs)
        history.push(engine.doc, "edit text")

        # Verify change took effect
        assert _get_text_value(engine.doc, handle) == "CHANGED"

        # Undo
        restored_doc = history.undo()
        assert restored_doc is not None
        assert _get_text_value(restored_doc, handle) == "Column C-4"

    def test_undo_then_redo_reapplies(self, sample_dxf, tmp_path):
        """Undo then redo restores the edited state."""
        work = copy_dxf_for_editing(sample_dxf, tmp_path / "work.dxf")
        handle = _find_text_handle(work, "Column C-4")
        assert handle is not None

        history = EditHistory(work)

        # Apply edit
        engine = EditEngine(work)
        cs = ChangeSet(
            prompt="edit text",
            operations=[
                EditOperation(
                    op_type=OpType.EDIT_TEXT,
                    target_handle=handle,
                    params={"new_text": "MODIFIED"},
                )
            ],
        )
        engine.apply_changeset(cs)
        history.push(engine.doc, "edit text")

        # Undo
        history.undo()
        assert history.can_redo

        # Redo
        redone_doc = history.redo()
        assert redone_doc is not None
        assert _get_text_value(redone_doc, handle) == "MODIFIED"

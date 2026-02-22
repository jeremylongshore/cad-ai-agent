"""Tests for edit_engine — applies validated operations to DXF documents."""

from __future__ import annotations

import hashlib

import ezdxf

from cad_dxf_agent.core.dxf_writer import copy_dxf_for_editing
from cad_dxf_agent.core.edit_engine import EditEngine
from cad_dxf_agent.models.ops_schema import ChangeSet, EditOperation, OpType


def _get_text_handle(dxf_path, text_content):
    """Find the handle of a TEXT entity with the given text."""
    doc = ezdxf.readfile(str(dxf_path))
    for e in doc.modelspace():
        if e.dxftype() == "TEXT" and e.dxf.text == text_content:
            return e.dxf.handle
    return None


def _get_mtext_handle(dxf_path, text_fragment):
    """Find the handle of an MTEXT entity containing the given text."""
    doc = ezdxf.readfile(str(dxf_path))
    for e in doc.modelspace():
        if e.dxftype() == "MTEXT" and text_fragment in e.text:
            return e.dxf.handle
    return None


def _get_first_handle(dxf_path, dxf_type="LINE"):
    """Find the handle of the first entity of the given DXF type."""
    doc = ezdxf.readfile(str(dxf_path))
    for e in doc.modelspace():
        if e.dxftype() == dxf_type:
            return e.dxf.handle
    return None


def _get_insert_handle(dxf_path, block_name="COLUMN_MARK"):
    """Find the handle of the first INSERT of the given block."""
    doc = ezdxf.readfile(str(dxf_path))
    for e in doc.modelspace():
        if e.dxftype() == "INSERT" and e.dxf.name == block_name:
            return e.dxf.handle
    return None


class TestApplyMove:
    def test_apply_move_changes_position(self, sample_dxf, tmp_path):
        """Move operation shifts entity position in the DXF."""
        work = copy_dxf_for_editing(sample_dxf, tmp_path / "work.dxf")
        handle = _get_first_handle(work, "LINE")
        assert handle is not None

        # Read original position
        doc_before = ezdxf.readfile(str(work))
        entity_before = doc_before.entitydb.get(handle)
        start_x_before = entity_before.dxf.start.x

        engine = EditEngine(work)
        cs = ChangeSet(
            prompt="test move",
            operations=[
                EditOperation(
                    op_type=OpType.MOVE_ENTITY,
                    target_handle=handle,
                    params={"dx": 10.0, "dy": 5.0},
                )
            ],
        )
        results = engine.apply_changeset(cs)
        assert results[0].success

        # Save and reload to verify
        output = tmp_path / "moved.dxf"
        engine.save(output)
        doc_after = ezdxf.readfile(str(output))
        entity_after = doc_after.entitydb.get(handle)
        assert abs(entity_after.dxf.start.x - (start_x_before + 10.0)) < 0.01


class TestApplyEditText:
    def test_apply_edit_text_on_text_entity(self, sample_dxf, tmp_path):
        """Edit text on a TEXT entity updates dxf.text."""
        work = copy_dxf_for_editing(sample_dxf, tmp_path / "work.dxf")
        handle = _get_text_handle(work, "Column C-4")
        assert handle is not None

        engine = EditEngine(work)
        cs = ChangeSet(
            prompt="test edit text",
            operations=[
                EditOperation(
                    op_type=OpType.EDIT_TEXT,
                    target_handle=handle,
                    params={"new_text": "Column C-4A"},
                )
            ],
        )
        results = engine.apply_changeset(cs)
        assert results[0].success

        output = tmp_path / "edited.dxf"
        engine.save(output)
        doc = ezdxf.readfile(str(output))
        entity = doc.entitydb.get(handle)
        assert entity.dxf.text == "Column C-4A"

    def test_apply_edit_text_on_mtext_entity(self, sample_dxf, tmp_path):
        """Edit text on an MTEXT entity updates entity.text."""
        work = copy_dxf_for_editing(sample_dxf, tmp_path / "work.dxf")
        handle = _get_mtext_handle(work, "Footing detail")
        assert handle is not None

        engine = EditEngine(work)
        cs = ChangeSet(
            prompt="test edit mtext",
            operations=[
                EditOperation(
                    op_type=OpType.EDIT_TEXT,
                    target_handle=handle,
                    params={"new_text": "Updated note"},
                )
            ],
        )
        results = engine.apply_changeset(cs)
        assert results[0].success

        output = tmp_path / "edited_mtext.dxf"
        engine.save(output)
        doc = ezdxf.readfile(str(output))
        entity = doc.entitydb.get(handle)
        assert entity.text == "Updated note"

    def test_apply_edit_text_on_non_text_fails(self, sample_dxf, tmp_path):
        """Edit text on a LINE entity returns success=False."""
        work = copy_dxf_for_editing(sample_dxf, tmp_path / "work.dxf")
        handle = _get_first_handle(work, "LINE")
        assert handle is not None

        engine = EditEngine(work)
        cs = ChangeSet(
            prompt="test bad edit",
            operations=[
                EditOperation(
                    op_type=OpType.EDIT_TEXT,
                    target_handle=handle,
                    params={"new_text": "nope"},
                )
            ],
        )
        results = engine.apply_changeset(cs)
        assert not results[0].success
        assert "Cannot edit text" in results[0].description


class TestApplyDelete:
    def test_apply_delete_removes_entity(self, sample_dxf, tmp_path):
        """Delete operation removes the entity from modelspace."""
        work = copy_dxf_for_editing(sample_dxf, tmp_path / "work.dxf")

        doc_before = ezdxf.readfile(str(work))
        count_before = len(list(doc_before.modelspace()))

        handle = _get_first_handle(work, "LINE")
        assert handle is not None

        engine = EditEngine(work)
        cs = ChangeSet(
            prompt="test delete",
            operations=[
                EditOperation(
                    op_type=OpType.DELETE_ENTITY,
                    target_handle=handle,
                )
            ],
        )
        results = engine.apply_changeset(cs)
        assert results[0].success

        output = tmp_path / "deleted.dxf"
        engine.save(output)
        doc_after = ezdxf.readfile(str(output))
        count_after = len(list(doc_after.modelspace()))
        assert count_after == count_before - 1

    def test_apply_delete_not_found_fails(self, sample_dxf, tmp_path):
        """Delete on a nonexistent handle returns success=False."""
        work = copy_dxf_for_editing(sample_dxf, tmp_path / "work.dxf")
        engine = EditEngine(work)
        cs = ChangeSet(
            prompt="test",
            operations=[
                EditOperation(
                    op_type=OpType.DELETE_ENTITY,
                    target_handle="DOES_NOT_EXIST_999",
                )
            ],
        )
        results = engine.apply_changeset(cs)
        assert not results[0].success
        assert "not found" in results[0].description.lower()


class TestApplyAddBlock:
    def test_apply_add_block_inserts_reference(self, sample_dxf, tmp_path):
        """Add block inserts a new INSERT entity in modelspace."""
        work = copy_dxf_for_editing(sample_dxf, tmp_path / "work.dxf")

        doc_before = ezdxf.readfile(str(work))
        insert_count_before = sum(1 for e in doc_before.modelspace() if e.dxftype() == "INSERT")

        engine = EditEngine(work)
        cs = ChangeSet(
            prompt="test add block",
            operations=[
                EditOperation(
                    op_type=OpType.ADD_BLOCK,
                    params={
                        "block_name": "COLUMN_MARK",
                        "insert_point": {"x": 99.0, "y": 99.0},
                    },
                )
            ],
        )
        results = engine.apply_changeset(cs)
        assert results[0].success
        assert results[0].entity_handle  # Got a handle back

        output = tmp_path / "added.dxf"
        engine.save(output)
        doc_after = ezdxf.readfile(str(output))
        insert_count_after = sum(1 for e in doc_after.modelspace() if e.dxftype() == "INSERT")
        assert insert_count_after == insert_count_before + 1

    def test_apply_add_block_nonexistent_block_fails(self, sample_dxf, tmp_path):
        """Adding a block that doesn't exist in the doc returns success=False."""
        work = copy_dxf_for_editing(sample_dxf, tmp_path / "work.dxf")
        engine = EditEngine(work)
        cs = ChangeSet(
            prompt="test",
            operations=[
                EditOperation(
                    op_type=OpType.ADD_BLOCK,
                    params={
                        "block_name": "NONEXISTENT_BLOCK",
                        "insert_point": {"x": 0, "y": 0},
                    },
                )
            ],
        )
        results = engine.apply_changeset(cs)
        assert not results[0].success
        assert "not found" in results[0].description.lower()


class TestAppliedChangesAccumulate:
    def test_applied_changes_accumulate(self, sample_dxf, tmp_path):
        """Multiple changeset applications accumulate in applied_changes."""
        work = copy_dxf_for_editing(sample_dxf, tmp_path / "work.dxf")
        handle = _get_first_handle(work, "LINE")

        engine = EditEngine(work)
        cs1 = ChangeSet(
            prompt="move",
            operations=[
                EditOperation(
                    op_type=OpType.MOVE_ENTITY,
                    target_handle=handle,
                    params={"dx": 1, "dy": 0},
                )
            ],
        )
        cs2 = ChangeSet(
            prompt="move again",
            operations=[
                EditOperation(
                    op_type=OpType.MOVE_ENTITY,
                    target_handle=handle,
                    params={"dx": 2, "dy": 0},
                )
            ],
        )
        engine.apply_changeset(cs1)
        engine.apply_changeset(cs2)
        assert len(engine.applied_changes) == 2


class TestOriginalFileUntouched:
    def test_original_file_untouched(self, sample_dxf, tmp_path):
        """After edit + save, the original file is byte-identical."""
        sha_before = hashlib.sha256(sample_dxf.read_bytes()).hexdigest()

        work = copy_dxf_for_editing(sample_dxf, tmp_path / "work.dxf")
        handle = _get_first_handle(work, "LINE")

        engine = EditEngine(work)
        cs = ChangeSet(
            prompt="test",
            operations=[
                EditOperation(
                    op_type=OpType.MOVE_ENTITY,
                    target_handle=handle,
                    params={"dx": 100, "dy": 100},
                )
            ],
        )
        engine.apply_changeset(cs)
        engine.save(tmp_path / "output.dxf")

        sha_after = hashlib.sha256(sample_dxf.read_bytes()).hexdigest()
        assert sha_before == sha_after

"""Tests for EditHistory — snapshot-based undo/redo."""

from __future__ import annotations

from pathlib import Path

import ezdxf
import pytest

from cad_dxf_agent.core.edit_history import EditHistory


@pytest.fixture
def dxf_file(tmp_path: Path) -> Path:
    """Create a minimal DXF with a text entity for undo/redo testing."""
    doc = ezdxf.new(dxfversion="R2018")
    msp = doc.modelspace()
    msp.add_text(
        "ORIGINAL",
        dxfattribs={"layer": "NOTES", "height": 2.5, "insert": (10, 10)},
    )
    path = tmp_path / "undo_test.dxf"
    doc.saveas(str(path))
    return path


class TestEditHistory:
    def test_initial_state(self, dxf_file):
        history = EditHistory(dxf_file)
        assert history.depth == 0
        assert not history.can_undo
        assert not history.can_redo
        assert history.current_label == "initial"

    def test_push_creates_snapshot(self, dxf_file):
        history = EditHistory(dxf_file)
        doc = ezdxf.readfile(str(dxf_file))
        history.push(doc, "first edit")
        assert history.depth == 1
        assert history.can_undo
        assert not history.can_redo
        assert history.current_label == "first edit"

    def test_undo_returns_to_initial(self, dxf_file):
        history = EditHistory(dxf_file)

        # Make an edit
        doc = ezdxf.readfile(str(dxf_file))
        msp = doc.modelspace()
        for entity in msp:
            if entity.dxftype() == "TEXT":
                entity.dxf.text = "MODIFIED"
        history.push(doc, "modify text")

        # Undo
        restored = history.undo()
        assert restored is not None
        msp = restored.modelspace()
        texts = [e.dxf.text for e in msp if e.dxftype() == "TEXT"]
        assert "ORIGINAL" in texts

    def test_redo_after_undo(self, dxf_file):
        history = EditHistory(dxf_file)

        # Make an edit
        doc = ezdxf.readfile(str(dxf_file))
        msp = doc.modelspace()
        for entity in msp:
            if entity.dxftype() == "TEXT":
                entity.dxf.text = "MODIFIED"
        history.push(doc, "modify text")

        # Undo then redo
        history.undo()
        assert history.can_redo
        restored = history.redo()
        assert restored is not None
        msp = restored.modelspace()
        texts = [e.dxf.text for e in msp if e.dxftype() == "TEXT"]
        assert "MODIFIED" in texts

    def test_undo_at_initial_returns_none(self, dxf_file):
        history = EditHistory(dxf_file)
        assert history.undo() is None

    def test_redo_at_latest_returns_none(self, dxf_file):
        history = EditHistory(dxf_file)
        doc = ezdxf.readfile(str(dxf_file))
        history.push(doc, "edit")
        assert history.redo() is None

    def test_push_after_undo_truncates_redo(self, dxf_file):
        history = EditHistory(dxf_file)

        doc1 = ezdxf.readfile(str(dxf_file))
        history.push(doc1, "edit 1")

        doc2 = ezdxf.readfile(str(dxf_file))
        history.push(doc2, "edit 2")

        # Undo once (back to edit 1)
        history.undo()
        assert history.can_redo

        # Push new edit (should truncate edit 2)
        doc3 = ezdxf.readfile(str(dxf_file))
        history.push(doc3, "edit 3")
        assert not history.can_redo
        assert history.depth == 2  # edit 1 + edit 3
        assert history.current_label == "edit 3"

    def test_multiple_undos(self, dxf_file):
        history = EditHistory(dxf_file)

        for i in range(3):
            doc = ezdxf.readfile(str(dxf_file))
            history.push(doc, f"edit {i}")

        assert history.depth == 3

        # Undo all 3
        for _ in range(3):
            result = history.undo()
            assert result is not None

        # Now at initial — one more undo returns None
        assert history.undo() is None
        assert history.current_label == "initial"

    def test_get_current_doc(self, dxf_file):
        history = EditHistory(dxf_file)
        doc = history.get_current_doc()
        assert doc is not None
        msp = doc.modelspace()
        texts = [e.dxf.text for e in msp if e.dxftype() == "TEXT"]
        assert "ORIGINAL" in texts


class TestEditHistoryMaxSnapshots:
    def test_unlimited_by_default(self, dxf_file):
        """Default max_snapshots=0 means no eviction."""
        history = EditHistory(dxf_file)
        for i in range(10):
            doc = ezdxf.readfile(str(dxf_file))
            history.push(doc, f"edit {i}")
        assert history.depth == 10

    def test_cap_evicts_oldest(self, dxf_file):
        """When cap is hit, oldest snapshots are evicted."""
        history = EditHistory(dxf_file, max_snapshots=3)
        for i in range(5):
            doc = ezdxf.readfile(str(dxf_file))
            history.push(doc, f"edit {i}")
        assert history.depth == 3
        assert history.current_label == "edit 4"

    def test_cap_preserves_undo(self, dxf_file):
        """After eviction, remaining snapshots are still undoable."""
        history = EditHistory(dxf_file, max_snapshots=3)
        for i in range(5):
            doc = ezdxf.readfile(str(dxf_file))
            history.push(doc, f"edit {i}")

        # Should be able to undo 3 times (3 snapshots → initial)
        for _ in range(3):
            result = history.undo()
            assert result is not None
        # Now at initial
        assert history.current_label == "initial"
        assert history.undo() is None

    def test_cap_of_one(self, dxf_file):
        """Edge case: max_snapshots=1 keeps only the latest."""
        history = EditHistory(dxf_file, max_snapshots=1)
        for i in range(4):
            doc = ezdxf.readfile(str(dxf_file))
            history.push(doc, f"edit {i}")
        assert history.depth == 1
        assert history.current_label == "edit 3"

    def test_cap_with_undo_and_new_push(self, dxf_file):
        """Undo then push respects the cap after truncation."""
        history = EditHistory(dxf_file, max_snapshots=3)
        for i in range(3):
            doc = ezdxf.readfile(str(dxf_file))
            history.push(doc, f"edit {i}")
        assert history.depth == 3

        # Undo once, then push a new edit
        history.undo()
        doc = ezdxf.readfile(str(dxf_file))
        history.push(doc, "edit new")
        # Redo was truncated: edit 0, edit 1, edit new = 3 (at cap)
        assert history.depth == 3
        assert history.current_label == "edit new"

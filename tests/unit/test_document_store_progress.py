"""Tests for work-progress methods on InMemoryDocumentStore."""

from __future__ import annotations

from pathlib import Path

import pytest

from cad_dxf_agent.core.document_store import InMemoryDocumentStore
from cad_dxf_agent.models.work_progress_schema import WorkProgress

SAMPLE_DXF = b"0\nSECTION\n2\nHEADER\n0\nENDSEC\n0\nEOF\n"
WORKING_DXF = b"0\nSECTION\n2\nHEADER\n9\n$ACADVER\n1\nAC1015\n0\nENDSEC\n0\nEOF\n"


@pytest.fixture
def store() -> InMemoryDocumentStore:
    return InMemoryDocumentStore()


def _make_progress(user_id: str = "u1", doc_id: str = "doc-abc") -> WorkProgress:
    return WorkProgress(
        user_id=user_id,
        doc_id=doc_id,
        edit_count=3,
        last_prompt="move the door",
        conversation_history=[{"role": "user", "content": "move the door"}],
        audit_events=[{"op": "move_entity", "handle": "1A"}],
        snapshot_labels=["before-move"],
    )


class TestSaveAndGetWorkProgress:
    def test_save_then_get_returns_progress(self, store: InMemoryDocumentStore) -> None:
        """Saved progress is retrievable for the same doc."""
        doc = store.save_document("u1", "floor.dxf", SAMPLE_DXF)
        progress = _make_progress(user_id="u1", doc_id=doc.doc_id)

        store.save_work_progress("u1", doc.doc_id, progress)

        retrieved = store.get_work_progress("u1", doc.doc_id)
        assert retrieved is not None
        assert retrieved.doc_id == doc.doc_id
        assert retrieved.user_id == "u1"
        assert retrieved.edit_count == 3
        assert retrieved.last_prompt == "move the door"
        assert retrieved.conversation_history == [{"role": "user", "content": "move the door"}]
        assert retrieved.audit_events == [{"op": "move_entity", "handle": "1A"}]
        assert retrieved.snapshot_labels == ["before-move"]

    def test_get_returns_none_when_nothing_saved(self, store: InMemoryDocumentStore) -> None:
        """get_work_progress returns None for a doc with no saved progress."""
        doc = store.save_document("u1", "floor.dxf", SAMPLE_DXF)

        result = store.get_work_progress("u1", doc.doc_id)

        assert result is None

    def test_get_returns_none_for_unknown_doc_id(self, store: InMemoryDocumentStore) -> None:
        """get_work_progress returns None for a doc_id that was never seen."""
        result = store.get_work_progress("u1", "nonexistent-doc-id")

        assert result is None

    def test_save_overwrites_previous_progress(self, store: InMemoryDocumentStore) -> None:
        """A second save replaces the earlier progress for the same doc."""
        doc = store.save_document("u1", "floor.dxf", SAMPLE_DXF)
        first = WorkProgress(user_id="u1", doc_id=doc.doc_id, edit_count=1, last_prompt="first")
        second = WorkProgress(user_id="u1", doc_id=doc.doc_id, edit_count=5, last_prompt="second")

        store.save_work_progress("u1", doc.doc_id, first)
        store.save_work_progress("u1", doc.doc_id, second)

        retrieved = store.get_work_progress("u1", doc.doc_id)
        assert retrieved is not None
        assert retrieved.edit_count == 5
        assert retrieved.last_prompt == "second"


class TestWorkingDxf:
    def test_save_with_working_dxf_path_stores_bytes(
        self, store: InMemoryDocumentStore, tmp_path: Path
    ) -> None:
        """Providing a working_dxf_path persists its bytes and they are retrievable."""
        doc = store.save_document("u1", "floor.dxf", SAMPLE_DXF)
        progress = _make_progress(user_id="u1", doc_id=doc.doc_id)
        working_file = tmp_path / "working.dxf"
        working_file.write_bytes(WORKING_DXF)

        store.save_work_progress("u1", doc.doc_id, progress, working_dxf_path=working_file)

        data = store.get_working_dxf("u1", doc.doc_id)
        assert data == WORKING_DXF

    def test_get_working_dxf_returns_none_when_no_dxf_saved(
        self, store: InMemoryDocumentStore
    ) -> None:
        """get_working_dxf returns None when progress was saved without a DXF path."""
        doc = store.save_document("u1", "floor.dxf", SAMPLE_DXF)
        progress = _make_progress(user_id="u1", doc_id=doc.doc_id)

        store.save_work_progress("u1", doc.doc_id, progress)  # no working_dxf_path

        assert store.get_working_dxf("u1", doc.doc_id) is None

    def test_get_working_dxf_returns_none_for_unknown_doc(
        self, store: InMemoryDocumentStore
    ) -> None:
        """get_working_dxf returns None when no progress exists at all."""
        assert store.get_working_dxf("u1", "nonexistent-doc-id") is None

    def test_save_with_nonexistent_path_does_not_store_dxf(
        self, store: InMemoryDocumentStore, tmp_path: Path
    ) -> None:
        """If working_dxf_path points to a missing file, no DXF bytes are stored."""
        doc = store.save_document("u1", "floor.dxf", SAMPLE_DXF)
        progress = _make_progress(user_id="u1", doc_id=doc.doc_id)
        missing_path = tmp_path / "does-not-exist.dxf"

        store.save_work_progress("u1", doc.doc_id, progress, working_dxf_path=missing_path)

        assert store.get_working_dxf("u1", doc.doc_id) is None


class TestClearWorkProgress:
    def test_clear_removes_progress_and_returns_true(self, store: InMemoryDocumentStore) -> None:
        """clear_work_progress removes saved progress and returns True."""
        doc = store.save_document("u1", "floor.dxf", SAMPLE_DXF)
        store.save_work_progress("u1", doc.doc_id, _make_progress("u1", doc.doc_id))

        result = store.clear_work_progress("u1", doc.doc_id)

        assert result is True
        assert store.get_work_progress("u1", doc.doc_id) is None

    def test_clear_removes_working_dxf_bytes(
        self, store: InMemoryDocumentStore, tmp_path: Path
    ) -> None:
        """clear_work_progress also purges stored working DXF bytes."""
        doc = store.save_document("u1", "floor.dxf", SAMPLE_DXF)
        working_file = tmp_path / "working.dxf"
        working_file.write_bytes(WORKING_DXF)
        store.save_work_progress(
            "u1", doc.doc_id, _make_progress("u1", doc.doc_id), working_dxf_path=working_file
        )

        store.clear_work_progress("u1", doc.doc_id)

        assert store.get_working_dxf("u1", doc.doc_id) is None

    def test_clear_returns_false_when_nothing_to_clear(self, store: InMemoryDocumentStore) -> None:
        """clear_work_progress returns False when no progress existed."""
        doc = store.save_document("u1", "floor.dxf", SAMPLE_DXF)

        result = store.clear_work_progress("u1", doc.doc_id)

        assert result is False

    def test_clear_returns_false_for_unknown_doc_id(self, store: InMemoryDocumentStore) -> None:
        """clear_work_progress returns False for a completely unknown doc."""
        result = store.clear_work_progress("u1", "nonexistent-doc-id")

        assert result is False

    def test_clear_is_idempotent(self, store: InMemoryDocumentStore) -> None:
        """A second clear on the same doc returns False (already gone)."""
        doc = store.save_document("u1", "floor.dxf", SAMPLE_DXF)
        store.save_work_progress("u1", doc.doc_id, _make_progress("u1", doc.doc_id))

        assert store.clear_work_progress("u1", doc.doc_id) is True
        assert store.clear_work_progress("u1", doc.doc_id) is False


class TestHasWorkProgressFlag:
    def test_save_sets_flag_on_document(self, store: InMemoryDocumentStore) -> None:
        """save_work_progress marks has_work_progress=True on the UserDocument."""
        doc = store.save_document("u1", "floor.dxf", SAMPLE_DXF)
        assert doc.has_work_progress is False

        store.save_work_progress("u1", doc.doc_id, _make_progress("u1", doc.doc_id))

        refreshed = store.get_document("u1", doc.doc_id)
        assert refreshed is not None
        assert refreshed.has_work_progress is True

    def test_clear_resets_flag_on_document(self, store: InMemoryDocumentStore) -> None:
        """clear_work_progress resets has_work_progress=False on the UserDocument."""
        doc = store.save_document("u1", "floor.dxf", SAMPLE_DXF)
        store.save_work_progress("u1", doc.doc_id, _make_progress("u1", doc.doc_id))

        store.clear_work_progress("u1", doc.doc_id)

        refreshed = store.get_document("u1", doc.doc_id)
        assert refreshed is not None
        assert refreshed.has_work_progress is False

    def test_flag_false_by_default_on_new_document(self, store: InMemoryDocumentStore) -> None:
        """Freshly saved documents start with has_work_progress=False."""
        doc = store.save_document("u1", "fresh.dxf", SAMPLE_DXF)

        assert doc.has_work_progress is False

    def test_clear_without_prior_save_leaves_flag_false(self, store: InMemoryDocumentStore) -> None:
        """Clearing progress on a doc that never had any keeps the flag False."""
        doc = store.save_document("u1", "floor.dxf", SAMPLE_DXF)

        store.clear_work_progress("u1", doc.doc_id)

        refreshed = store.get_document("u1", doc.doc_id)
        assert refreshed is not None
        assert refreshed.has_work_progress is False


class TestMultipleDocumentIsolation:
    def test_progress_is_isolated_per_doc(self, store: InMemoryDocumentStore) -> None:
        """Progress saved for doc A does not affect doc B."""
        doc_a = store.save_document("u1", "a.dxf", SAMPLE_DXF)
        doc_b = store.save_document("u1", "b.dxf", SAMPLE_DXF)
        progress_a = WorkProgress(user_id="u1", doc_id=doc_a.doc_id, edit_count=10)

        store.save_work_progress("u1", doc_a.doc_id, progress_a)

        assert store.get_work_progress("u1", doc_b.doc_id) is None
        assert store.get_working_dxf("u1", doc_b.doc_id) is None

    def test_clearing_one_doc_does_not_affect_another(self, store: InMemoryDocumentStore) -> None:
        """Clearing progress for doc A leaves doc B's progress intact."""
        doc_a = store.save_document("u1", "a.dxf", SAMPLE_DXF)
        doc_b = store.save_document("u1", "b.dxf", SAMPLE_DXF)
        store.save_work_progress("u1", doc_a.doc_id, _make_progress("u1", doc_a.doc_id))
        store.save_work_progress("u1", doc_b.doc_id, _make_progress("u1", doc_b.doc_id))

        store.clear_work_progress("u1", doc_a.doc_id)

        assert store.get_work_progress("u1", doc_a.doc_id) is None
        assert store.get_work_progress("u1", doc_b.doc_id) is not None

    def test_progress_is_isolated_per_user(self, store: InMemoryDocumentStore) -> None:
        """Two users can each have progress on different documents without collision.

        The InMemoryDocumentStore keys work progress by (user_id, doc_id) tuples,
        ensuring that progress is isolated between users even if doc_ids were
        somehow not globally unique.
        """
        doc_u1 = store.save_document("u1", "floor.dxf", SAMPLE_DXF)
        doc_u2 = store.save_document("u2", "section.dxf", SAMPLE_DXF)
        p_u1 = WorkProgress(user_id="u1", doc_id=doc_u1.doc_id, edit_count=2)
        p_u2 = WorkProgress(user_id="u2", doc_id=doc_u2.doc_id, edit_count=7)

        store.save_work_progress("u1", doc_u1.doc_id, p_u1)
        store.save_work_progress("u2", doc_u2.doc_id, p_u2)

        r_u1 = store.get_work_progress("u1", doc_u1.doc_id)
        r_u2 = store.get_work_progress("u2", doc_u2.doc_id)
        assert r_u1 is not None and r_u1.edit_count == 2
        assert r_u2 is not None and r_u2.edit_count == 7

    def test_has_work_progress_flag_isolated_per_doc(self, store: InMemoryDocumentStore) -> None:
        """Setting the flag on doc A does not bleed onto doc B."""
        doc_a = store.save_document("u1", "a.dxf", SAMPLE_DXF)
        doc_b = store.save_document("u1", "b.dxf", SAMPLE_DXF)

        store.save_work_progress("u1", doc_a.doc_id, _make_progress("u1", doc_a.doc_id))

        doc_b_refreshed = store.get_document("u1", doc_b.doc_id)
        assert doc_b_refreshed is not None
        assert doc_b_refreshed.has_work_progress is False

    def test_multiple_docs_can_all_have_progress(self, store: InMemoryDocumentStore) -> None:
        """Three docs under the same user each hold independent progress state."""
        docs = [store.save_document("u1", f"{c}.dxf", SAMPLE_DXF) for c in ("a", "b", "c")]
        for i, doc in enumerate(docs):
            store.save_work_progress(
                "u1",
                doc.doc_id,
                WorkProgress(user_id="u1", doc_id=doc.doc_id, edit_count=i + 1),
            )

        for i, doc in enumerate(docs):
            progress = store.get_work_progress("u1", doc.doc_id)
            assert progress is not None
            assert progress.edit_count == i + 1

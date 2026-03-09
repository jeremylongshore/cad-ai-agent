"""Tests for work-progress auto-save and restore behaviour (EPIC-CAD-30)."""

from __future__ import annotations

import pytest

from cad_dxf_agent.core.document_store import InMemoryDocumentStore
from cad_dxf_agent.models.work_progress_schema import WorkProgress

starlette = pytest.importorskip("starlette", reason="web backend tests require fastapi/starlette")

SAMPLE_DXF_CONTENT = b"0\nSECTION\n2\nHEADER\n0\nENDSEC\n0\nEOF\n"


@pytest.fixture(autouse=True)
def _use_inmemory_doc_store(monkeypatch):
    """Force InMemoryDocumentStore for all tests in this module."""
    import web.backend.main as main_mod

    store = InMemoryDocumentStore()
    monkeypatch.setattr(main_mod, "_document_store", store)
    yield store
    monkeypatch.setattr(main_mod, "_document_store", None)


@pytest.mark.web
class TestLoadDocumentRestoredField:
    def test_load_returns_restored_false_when_no_progress(
        self, client, sample_dxf_bytes, _use_inmemory_doc_store
    ):
        """Loading a doc with no saved progress returns restored=False."""
        store = _use_inmemory_doc_store
        doc = store.save_document("test-user-123", "plan.dxf", sample_dxf_bytes)

        resp = client.post(f"/api/documents/{doc.doc_id}/load")
        assert resp.status_code == 200
        assert resp.json()["restored"] is False

    def test_load_returns_restored_true_when_progress_exists(
        self, client, sample_dxf_bytes, _use_inmemory_doc_store
    ):
        """Loading a doc that has saved progress returns restored=True."""
        store = _use_inmemory_doc_store
        doc = store.save_document("test-user-123", "plan.dxf", sample_dxf_bytes)

        # Seed the store directly with a WorkProgress record
        progress = WorkProgress(
            user_id="test-user-123",
            doc_id=doc.doc_id,
            conversation_history=[{"role": "user", "content": "move wall to x=5"}],
            edit_count=1,
            last_prompt="move wall to x=5",
        )
        store.save_work_progress("test-user-123", doc.doc_id, progress)

        resp = client.post(f"/api/documents/{doc.doc_id}/load")
        assert resp.status_code == 200
        assert resp.json()["restored"] is True

    def test_load_response_contains_session_id(
        self, client, sample_dxf_bytes, _use_inmemory_doc_store
    ):
        """Load response always includes a session_id."""
        store = _use_inmemory_doc_store
        doc = store.save_document("test-user-123", "plan.dxf", sample_dxf_bytes)

        resp = client.post(f"/api/documents/{doc.doc_id}/load")
        assert "session_id" in resp.json()

    def test_load_response_contains_document_id(
        self, client, sample_dxf_bytes, _use_inmemory_doc_store
    ):
        """Load response always includes the correct document_id."""
        store = _use_inmemory_doc_store
        doc = store.save_document("test-user-123", "plan.dxf", sample_dxf_bytes)

        resp = client.post(f"/api/documents/{doc.doc_id}/load")
        assert resp.json()["document_id"] == doc.doc_id


@pytest.mark.web
class TestRestoreWorkProgressHelper:
    """Unit tests for the _restore_work_progress helper function."""

    def test_restore_returns_false_when_no_progress(self, _use_inmemory_doc_store):
        """_restore_work_progress returns False when the store has no record."""
        from web.backend.main import _restore_work_progress
        from web.backend.session import SessionManager

        store = _use_inmemory_doc_store
        mgr = SessionManager()
        session = mgr.create("test-user-123")
        session.document_id = "no-progress-doc"

        restored = _restore_work_progress(session, "test-user-123", store)
        assert restored is False

    def test_restore_returns_false_when_no_document_id(self, _use_inmemory_doc_store):
        """_restore_work_progress returns False when the session has no document_id."""
        from web.backend.main import _restore_work_progress
        from web.backend.session import SessionManager

        store = _use_inmemory_doc_store
        mgr = SessionManager()
        session = mgr.create("test-user-123")
        # document_id is "" by default — no binding

        restored = _restore_work_progress(session, "test-user-123", store)
        assert restored is False

    def test_restore_returns_true_when_progress_exists(self, _use_inmemory_doc_store):
        """_restore_work_progress returns True when saved progress is found."""
        from web.backend.main import _restore_work_progress
        from web.backend.session import SessionManager

        store = _use_inmemory_doc_store
        # Seed progress
        doc = store.save_document("test-user-123", "plan.dxf", SAMPLE_DXF_CONTENT)
        progress = WorkProgress(
            user_id="test-user-123",
            doc_id=doc.doc_id,
            conversation_history=[{"role": "user", "content": "rotate block 90 degrees"}],
            edit_count=2,
        )
        store.save_work_progress("test-user-123", doc.doc_id, progress)

        mgr = SessionManager()
        session = mgr.create("test-user-123")
        session.document_id = doc.doc_id

        restored = _restore_work_progress(session, "test-user-123", store)
        assert restored is True

    def test_restore_populates_conversation_history(self, _use_inmemory_doc_store):
        """After restore, session.conversation_history contains the saved messages."""
        from web.backend.main import _restore_work_progress
        from web.backend.session import SessionManager

        store = _use_inmemory_doc_store
        doc = store.save_document("test-user-123", "plan.dxf", SAMPLE_DXF_CONTENT)
        history = [
            {"role": "user", "content": "delete layer WALLS"},
            {"role": "assistant", "content": "Understood, deleting WALLS layer."},
        ]
        progress = WorkProgress(
            user_id="test-user-123",
            doc_id=doc.doc_id,
            conversation_history=history,
        )
        store.save_work_progress("test-user-123", doc.doc_id, progress)

        mgr = SessionManager()
        session = mgr.create("test-user-123")
        session.document_id = doc.doc_id

        _restore_work_progress(session, "test-user-123", store)

        assert session.conversation_history == history

    def test_restore_populates_audit_events(self, _use_inmemory_doc_store):
        """After restore, session.audit_events contains the saved events."""
        from web.backend.main import _restore_work_progress
        from web.backend.session import SessionManager

        store = _use_inmemory_doc_store
        doc = store.save_document("test-user-123", "plan.dxf", SAMPLE_DXF_CONTENT)
        events = [{"op": "move_entity", "handle": "0x1A"}]
        progress = WorkProgress(
            user_id="test-user-123",
            doc_id=doc.doc_id,
            audit_events=events,
        )
        store.save_work_progress("test-user-123", doc.doc_id, progress)

        mgr = SessionManager()
        session = mgr.create("test-user-123")
        session.document_id = doc.doc_id

        _restore_work_progress(session, "test-user-123", store)

        assert session.audit_events == events

    def test_restore_leaves_session_unchanged_on_miss(self, _use_inmemory_doc_store):
        """When no progress exists, conversation_history and audit_events stay empty."""
        from web.backend.main import _restore_work_progress
        from web.backend.session import SessionManager

        store = _use_inmemory_doc_store
        mgr = SessionManager()
        session = mgr.create("test-user-123")
        session.document_id = "ghost-doc"

        _restore_work_progress(session, "test-user-123", store)

        assert session.conversation_history == []
        assert session.audit_events == []

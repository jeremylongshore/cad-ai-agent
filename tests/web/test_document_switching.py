"""Tests for document switching and session deduplication (EPIC-CAD-15 Story 5)."""

from __future__ import annotations

import time

import pytest

from cad_dxf_agent.core.document_store import InMemoryDocumentStore

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
class TestLoadDocumentDeduplication:
    def test_loading_same_document_twice_returns_same_session(
        self, client, sample_dxf_bytes, _use_inmemory_doc_store
    ):
        """Loading the same document a second time reuses the existing session."""
        store = _use_inmemory_doc_store
        doc = store.save_document("test-user-123", "plan.dxf", sample_dxf_bytes)

        resp1 = client.post(f"/api/documents/{doc.doc_id}/load")
        assert resp1.status_code == 200
        session_id_1 = resp1.json()["session_id"]

        resp2 = client.post(f"/api/documents/{doc.doc_id}/load")
        assert resp2.status_code == 200
        session_id_2 = resp2.json()["session_id"]

        assert session_id_1 == session_id_2

    def test_loading_same_document_twice_returns_document_id(
        self, client, sample_dxf_bytes, _use_inmemory_doc_store
    ):
        """Both responses include the correct document_id."""
        store = _use_inmemory_doc_store
        doc = store.save_document("test-user-123", "plan.dxf", sample_dxf_bytes)

        resp1 = client.post(f"/api/documents/{doc.doc_id}/load")
        resp2 = client.post(f"/api/documents/{doc.doc_id}/load")

        assert resp1.json()["document_id"] == doc.doc_id
        assert resp2.json()["document_id"] == doc.doc_id

    def test_switching_between_two_documents_returns_different_sessions(
        self, client, sample_dxf_bytes, _use_inmemory_doc_store
    ):
        """Loading two different documents creates two distinct sessions."""
        store = _use_inmemory_doc_store
        doc_a = store.save_document("test-user-123", "a.dxf", sample_dxf_bytes)
        doc_b = store.save_document("test-user-123", "b.dxf", sample_dxf_bytes)

        resp_a = client.post(f"/api/documents/{doc_a.doc_id}/load")
        resp_b = client.post(f"/api/documents/{doc_b.doc_id}/load")

        assert resp_a.status_code == 200
        assert resp_b.status_code == 200
        assert resp_a.json()["session_id"] != resp_b.json()["session_id"]
        assert resp_a.json()["document_id"] == doc_a.doc_id
        assert resp_b.json()["document_id"] == doc_b.doc_id


@pytest.mark.web
class TestActiveSessionsEndpoint:
    def test_active_sessions_empty_initially(self, client):
        resp = client.get("/api/sessions/active")
        assert resp.status_code == 200
        assert resp.json()["sessions"] == []

    def test_active_sessions_includes_loaded_document(
        self, client, sample_dxf_bytes, _use_inmemory_doc_store
    ):
        """After loading a document, it appears in /api/sessions/active."""
        store = _use_inmemory_doc_store
        doc = store.save_document("test-user-123", "plan.dxf", sample_dxf_bytes)

        load_resp = client.post(f"/api/documents/{doc.doc_id}/load")
        assert load_resp.status_code == 200
        session_id = load_resp.json()["session_id"]

        resp = client.get("/api/sessions/active")
        assert resp.status_code == 200
        sessions = resp.json()["sessions"]
        assert len(sessions) == 1
        assert sessions[0]["session_id"] == session_id
        assert sessions[0]["document_id"] == doc.doc_id

    def test_active_sessions_respects_user_isolation(
        self, sample_dxf_bytes, _use_inmemory_doc_store
    ):
        """Sessions from user A do not appear for user B."""
        from web.backend.main import app, get_user

        store = _use_inmemory_doc_store

        # Load a document as user A
        async def _user_a():
            return {"uid": "user-a", "email": "a@example.com"}

        app.dependency_overrides[get_user] = _user_a
        from starlette.testclient import TestClient

        with TestClient(app, raise_server_exceptions=False) as client_a:
            doc = store.save_document("user-a", "plan.dxf", sample_dxf_bytes)
            client_a.post(f"/api/documents/{doc.doc_id}/load")

        # Query active sessions as user B — should see none
        async def _user_b():
            return {"uid": "user-b", "email": "b@example.com"}

        app.dependency_overrides[get_user] = _user_b
        with TestClient(app, raise_server_exceptions=False) as client_b:
            resp = client_b.get("/api/sessions/active")
            assert resp.status_code == 200
            assert resp.json()["sessions"] == []

        app.dependency_overrides.clear()

    def test_active_sessions_includes_created_at(
        self, client, sample_dxf_bytes, _use_inmemory_doc_store
    ):
        """Each session entry includes a created_at timestamp."""
        store = _use_inmemory_doc_store
        doc = store.save_document("test-user-123", "plan.dxf", sample_dxf_bytes)
        client.post(f"/api/documents/{doc.doc_id}/load")

        resp = client.get("/api/sessions/active")
        sessions = resp.json()["sessions"]
        assert "created_at" in sessions[0]
        assert sessions[0]["created_at"] > 0


@pytest.mark.web
class TestSessionDocumentIdRoundtrip:
    def test_document_id_stored_on_session(self, sample_dxf_bytes, _use_inmemory_doc_store):
        """Session.document_id is set when loading from the library."""
        from web.backend.main import session_mgr

        store = _use_inmemory_doc_store
        doc = store.save_document("test-user-123", "plan.dxf", sample_dxf_bytes)

        from web.backend.main import app, get_user

        async def _override():
            return {"uid": "test-user-123", "email": "test@example.com"}

        app.dependency_overrides[get_user] = _override
        from starlette.testclient import TestClient

        with TestClient(app, raise_server_exceptions=False) as c:
            resp = c.post(f"/api/documents/{doc.doc_id}/load")
            assert resp.status_code == 200
            session_id = resp.json()["session_id"]

        session = session_mgr._sessions[session_id]
        assert session.document_id == doc.doc_id
        app.dependency_overrides.clear()

    def test_document_id_round_trips_through_metadata(self):
        """Session.document_id survives to_metadata/from_metadata round-trip."""
        from web.backend.session import Session, SessionManager

        mgr = SessionManager()
        session = mgr.create("test-user")
        session.document_id = "abc123doc"

        meta = session.to_metadata()
        assert meta.document_id == "abc123doc"

        restored = Session.from_metadata(meta)
        assert restored.document_id == "abc123doc"


@pytest.mark.web
class TestFindByDocument:
    def test_find_by_document_returns_correct_session(self):
        """find_by_document returns the session bound to the given document."""
        from web.backend.session import SessionManager

        mgr = SessionManager()
        session = mgr.create("user-1")
        session.document_id = "doc-xyz"

        found = mgr.find_by_document("user-1", "doc-xyz")
        assert found is not None
        assert found.session_id == session.session_id

    def test_find_by_document_returns_none_when_not_found(self):
        """find_by_document returns None when no matching session exists."""
        from web.backend.session import SessionManager

        mgr = SessionManager()
        assert mgr.find_by_document("user-1", "nonexistent-doc") is None

    def test_find_by_document_respects_user_id(self):
        """find_by_document does not return another user's session."""
        from web.backend.session import SessionManager

        mgr = SessionManager()
        session = mgr.create("user-1")
        session.document_id = "shared-doc"

        assert mgr.find_by_document("user-2", "shared-doc") is None

    def test_list_user_sessions_excludes_expired(self):
        """list_user_sessions excludes sessions past the TTL."""
        from web.backend.session import SessionManager

        from cad_dxf_agent.core.session_store import SESSION_TTL_SECONDS

        mgr = SessionManager()
        session = mgr.create("user-1")
        # Artificially age the session beyond the TTL
        session.created_at = time.time() - SESSION_TTL_SECONDS - 1

        result = mgr.list_user_sessions("user-1")
        assert all(s.session_id != session.session_id for s in result)

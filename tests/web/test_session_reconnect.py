"""Tests for session reconnect endpoint (EPIC-CAD-15 Story 6)."""

from __future__ import annotations

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
class TestSessionReconnect:
    def test_reconnect_with_active_session_returns_existing(
        self, client, sample_dxf_bytes, _use_inmemory_doc_store
    ):
        """Reconnecting when a session is active returns it with reconnected=True."""
        store = _use_inmemory_doc_store
        doc = store.save_document("test-user-123", "plan.dxf", sample_dxf_bytes)

        # Load to create session
        load_resp = client.post(f"/api/documents/{doc.doc_id}/load")
        assert load_resp.status_code == 200
        original_session_id = load_resp.json()["session_id"]

        # Reconnect
        resp = client.post("/api/session/reconnect", json={"document_id": doc.doc_id})
        assert resp.status_code == 200
        data = resp.json()
        assert data["session_id"] == original_session_id
        assert data["reconnected"] is True
        assert data["document_id"] == doc.doc_id

    def test_reconnect_without_active_session_creates_new_one(
        self, client, sample_dxf_bytes, _use_inmemory_doc_store
    ):
        """Reconnecting when no session exists creates a new session (reconnected=False)."""
        store = _use_inmemory_doc_store
        doc = store.save_document("test-user-123", "plan.dxf", sample_dxf_bytes)

        resp = client.post("/api/session/reconnect", json={"document_id": doc.doc_id})
        assert resp.status_code == 200
        data = resp.json()
        assert "session_id" in data
        assert data["reconnected"] is False
        assert data["document_id"] == doc.doc_id

    def test_reconnect_with_deleted_document_returns_404(self, client, _use_inmemory_doc_store):
        """Reconnecting to a deleted document returns 404."""
        store = _use_inmemory_doc_store
        doc = store.save_document("test-user-123", "plan.dxf", SAMPLE_DXF_CONTENT)
        store.delete_document("test-user-123", doc.doc_id)

        resp = client.post("/api/session/reconnect", json={"document_id": doc.doc_id})
        assert resp.status_code == 404

    def test_reconnect_with_unknown_document_returns_404(self, client):
        resp = client.post("/api/session/reconnect", json={"document_id": "does-not-exist"})
        assert resp.status_code == 404

    def test_reconnect_returns_file_info(self, client, sample_dxf_bytes, _use_inmemory_doc_store):
        """Reconnected response includes file_info."""
        store = _use_inmemory_doc_store
        doc = store.save_document("test-user-123", "plan.dxf", sample_dxf_bytes)

        # First load to establish a session
        client.post(f"/api/documents/{doc.doc_id}/load")

        resp = client.post("/api/session/reconnect", json={"document_id": doc.doc_id})
        assert resp.status_code == 200
        assert "file_info" in resp.json()

    def test_reconnect_new_session_returns_file_info(
        self, client, sample_dxf_bytes, _use_inmemory_doc_store
    ):
        """Newly created reconnect session includes file_info."""
        store = _use_inmemory_doc_store
        doc = store.save_document("test-user-123", "plan.dxf", sample_dxf_bytes)

        resp = client.post("/api/session/reconnect", json={"document_id": doc.doc_id})
        assert resp.status_code == 200
        assert "file_info" in resp.json()

    def test_reconnect_respects_user_isolation(self, sample_dxf_bytes, _use_inmemory_doc_store):
        """User B cannot reconnect to user A's document."""
        from web.backend.main import app, get_user

        store = _use_inmemory_doc_store
        doc_a = store.save_document("user-a", "plan.dxf", sample_dxf_bytes)

        # User B tries to reconnect to user A's document (different user_id in store lookup)
        async def _user_b():
            return {"uid": "user-b", "email": "b@example.com"}

        app.dependency_overrides[get_user] = _user_b
        from starlette.testclient import TestClient

        with TestClient(app, raise_server_exceptions=False) as client_b:
            resp = client_b.post("/api/session/reconnect", json={"document_id": doc_a.doc_id})
            # The doc was stored under user-a; user-b cannot find it
            assert resp.status_code == 404

        app.dependency_overrides.clear()

    def test_reconnect_creates_new_session_bound_to_document(
        self, client, sample_dxf_bytes, _use_inmemory_doc_store
    ):
        """A newly created reconnect session has document_id set correctly."""
        from web.backend.main import session_mgr

        store = _use_inmemory_doc_store
        doc = store.save_document("test-user-123", "plan.dxf", sample_dxf_bytes)

        resp = client.post("/api/session/reconnect", json={"document_id": doc.doc_id})
        assert resp.status_code == 200
        session_id = resp.json()["session_id"]

        session = session_mgr._sessions[session_id]
        assert session.document_id == doc.doc_id

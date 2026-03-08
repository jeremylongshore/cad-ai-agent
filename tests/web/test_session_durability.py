"""Tests for session durability — metadata persistence, lifecycle events."""

from __future__ import annotations

import time

import pytest

starlette = pytest.importorskip("starlette", reason="web backend tests require fastapi/starlette")


from cad_dxf_agent.core.session_store import (  # noqa: E402
    SESSION_TTL_SECONDS,
    InMemorySessionStore,
    SessionMetadata,
)

# ===========================================================================
# TestSessionLifecycle
# ===========================================================================


@pytest.mark.web
class TestSessionLifecycle:
    def test_upload_creates_session(self, client, sample_dxf_bytes):
        resp = client.post(
            "/api/upload",
            files={"file": ("drawing.dxf", sample_dxf_bytes, "application/octet-stream")},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert "session_id" in data
        assert len(data["session_id"]) == 16

    def test_session_has_file_info(self, client, sample_dxf_bytes):
        resp = client.post(
            "/api/upload",
            files={"file": ("plan.dxf", sample_dxf_bytes, "application/octet-stream")},
        )
        assert resp.status_code == 200
        data = resp.json()

        info = data["file_info"]
        assert info["filename"] == "plan.dxf"
        assert isinstance(info["entity_count"], int)
        assert info["entity_count"] > 0
        assert isinstance(info["layers"], list)

    def test_session_metadata_serializable(self, upload_dxf):
        from web.backend.main import session_mgr

        session_id, _ = upload_dxf
        session = session_mgr.get(session_id, "test-user-123")

        result = session.to_metadata().to_dict()

        assert isinstance(result, dict)
        assert result["session_id"] == session_id
        assert result["user_id"] == "test-user-123"
        assert "file_info" in result
        assert "conversation_history" in result
        assert "audit_events" in result

    def test_session_metadata_roundtrip(self, upload_dxf):
        from web.backend.main import session_mgr

        session_id, _ = upload_dxf
        session = session_mgr.get(session_id, "test-user-123")
        original_meta = session.to_metadata()

        restored_meta = SessionMetadata.from_dict(original_meta.to_dict())

        assert restored_meta.session_id == original_meta.session_id
        assert restored_meta.user_id == original_meta.user_id
        assert restored_meta.created_at == original_meta.created_at
        assert restored_meta.file_info == original_meta.file_info
        assert restored_meta.original_path == original_meta.original_path

    def test_expired_session_returns_404(self, client, upload_dxf, auth_user):
        from web.backend.main import session_mgr

        session_id, _ = upload_dxf
        session = session_mgr.get(session_id, auth_user["uid"])

        # Back-date creation beyond TTL
        session.created_at = time.time() - SESSION_TTL_SECONDS - 1

        # Any endpoint that resolves the session should return 404
        resp = client.post(
            "/api/plan",
            json={"session_id": session_id, "prompt": "move line"},
        )
        assert resp.status_code == 404

    def test_conversation_history_persists_in_metadata(self, upload_dxf):
        from web.backend.main import session_mgr

        session_id, _ = upload_dxf
        session = session_mgr.get(session_id, "test-user-123")

        # Inject fake conversation history
        session.conversation_history = [
            {"role": "user", "content": "move the wall"},
            {"role": "model", "content": "planned move"},
        ]
        session_mgr.save_metadata(session)

        meta = session_mgr.store.get(session_id)
        assert meta is not None
        assert len(meta.conversation_history) == 2
        assert meta.conversation_history[0]["role"] == "user"

    def test_audit_events_in_metadata(self, upload_dxf):
        from web.backend.main import session_mgr

        session_id, _ = upload_dxf
        session = session_mgr.get(session_id, "test-user-123")

        # Inject an audit event and persist
        session.audit_events.append({"event": "upload", "ts": time.time()})
        session_mgr.save_metadata(session)

        meta = session_mgr.store.get(session_id)
        assert meta is not None
        assert len(meta.audit_events) >= 1
        assert meta.audit_events[0]["event"] == "upload"


# ===========================================================================
# TestSessionManagerAPI
# ===========================================================================


@pytest.mark.web
class TestSessionManagerAPI:
    def test_manager_uses_inmemory_store_by_default(self):
        from web.backend.main import session_mgr

        assert isinstance(session_mgr.store, InMemorySessionStore)

    def test_manager_store_property_accessible(self):
        from web.backend.main import session_mgr

        store = session_mgr.store
        assert store is not None
        # The store ABC contract: list_sessions must be callable
        assert callable(store.list_sessions)

    def test_session_not_found_raises_404(self, client):
        resp = client.post(
            "/api/plan",
            json={"session_id": "doesnotexist0000", "prompt": "do something"},
        )
        assert resp.status_code == 404

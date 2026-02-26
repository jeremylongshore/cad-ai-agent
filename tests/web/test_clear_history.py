"""Tests for POST /api/clear-history endpoint.

Uses real pipeline components. The planned_session fixture reuses the
same upload+plan pattern established in test_apply.py.
"""

from __future__ import annotations

import pytest


@pytest.mark.web
class TestClearHistory:
    # ------------------------------------------------------------------
    # Fixtures
    # ------------------------------------------------------------------

    @pytest.fixture
    def planned_session(self, client, upload_dxf):
        """Upload a DXF and run a plan, leaving a changeset on the session."""
        session_id, _ = upload_dxf
        resp = client.post(
            "/api/plan",
            json={"session_id": session_id, "prompt": "move the first entity 10 units east"},
        )
        assert resp.status_code == 200
        return session_id

    # ------------------------------------------------------------------
    # Happy-path tests
    # ------------------------------------------------------------------

    def test_clear_history_succeeds(self, client, upload_dxf):
        """Clear returns 200 with a confirmation message."""
        session_id, _ = upload_dxf
        resp = client.post(
            "/api/clear-history",
            json={"session_id": session_id},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert "message" in data
        assert len(data["message"]) > 0

    def test_clear_history_message_content(self, client, upload_dxf):
        """The response message should confirm the conversation was cleared."""
        session_id, _ = upload_dxf
        resp = client.post(
            "/api/clear-history",
            json={"session_id": session_id},
        )
        assert resp.status_code == 200
        assert "cleared" in resp.json()["message"].lower()

    def test_clear_history_clears_conversation(self, client, planned_session):
        """After clearing, session.conversation_history must be empty."""
        from web.backend.main import session_mgr

        session_id = planned_session

        # Verify history was populated by the plan
        session = session_mgr._sessions[session_id]
        assert len(session.conversation_history) > 0

        resp = client.post(
            "/api/clear-history",
            json={"session_id": session_id},
        )
        assert resp.status_code == 200
        assert session.conversation_history == []

    def test_clear_history_clears_changeset(self, client, planned_session):
        """After clearing, session.changeset is None, so /api/apply must fail."""
        session_id = planned_session

        resp = client.post(
            "/api/clear-history",
            json={"session_id": session_id},
        )
        assert resp.status_code == 200

        # The pending changeset must have been wiped — apply should now fail
        apply_resp = client.post(
            "/api/apply",
            json={"session_id": session_id},
        )
        assert apply_resp.status_code == 400
        assert "No plan" in apply_resp.json()["detail"]

    def test_clear_history_preserves_file(self, client, planned_session):
        """Clearing history must not evict the loaded DXF from the session."""
        from web.backend.main import session_mgr

        session_id = planned_session
        client.post("/api/clear-history", json={"session_id": session_id})

        session = session_mgr._sessions[session_id]
        assert session.context is not None
        assert session.original_path is not None
        assert session.original_path.exists()

    def test_clear_history_idempotent(self, client, upload_dxf):
        """Clearing an already-empty session must still return 200."""
        session_id, _ = upload_dxf
        resp1 = client.post("/api/clear-history", json={"session_id": session_id})
        assert resp1.status_code == 200
        resp2 = client.post("/api/clear-history", json={"session_id": session_id})
        assert resp2.status_code == 200

    def test_clear_history_allows_replan(self, client, planned_session):
        """After clearing, planning again must succeed (file is still loaded)."""
        session_id = planned_session
        client.post("/api/clear-history", json={"session_id": session_id})

        resp = client.post(
            "/api/plan",
            json={"session_id": session_id, "prompt": "move the first line east"},
        )
        assert resp.status_code == 200
        assert "operations" in resp.json()

    # ------------------------------------------------------------------
    # Error paths
    # ------------------------------------------------------------------

    def test_clear_history_missing_session(self, client):
        """Nonexistent session_id must return 404."""
        resp = client.post(
            "/api/clear-history",
            json={"session_id": "nonexistent000000"},
        )
        assert resp.status_code == 404

    def test_clear_history_wrong_user(self, client, sample_dxf_bytes):
        """Upload as user-A, then clear as user-B must return 404."""
        from web.backend.main import app, get_user

        # Upload as user-A
        async def user_a():
            return {"uid": "user-A", "email": "a@test.com"}

        app.dependency_overrides[get_user] = user_a
        upload_resp = client.post(
            "/api/upload",
            files={"file": ("test.dxf", sample_dxf_bytes, "application/octet-stream")},
        )
        assert upload_resp.status_code == 200
        sid = upload_resp.json()["session_id"]

        # Clear as user-B
        async def user_b():
            return {"uid": "user-B", "email": "b@test.com"}

        app.dependency_overrides[get_user] = user_b
        resp = client.post(
            "/api/clear-history",
            json={"session_id": sid},
        )
        assert resp.status_code == 404

    def test_clear_history_requires_auth(self, unauth_client):
        """Unauthenticated requests must be rejected with 401."""
        resp = unauth_client.post(
            "/api/clear-history",
            json={"session_id": "anything"},
        )
        assert resp.status_code == 401

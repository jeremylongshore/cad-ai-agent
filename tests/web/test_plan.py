"""Tests for POST /api/plan endpoint."""

from __future__ import annotations

import pytest


@pytest.mark.web
class TestPlan:
    def test_plan_valid_prompt(self, client, upload_dxf):
        session_id, _ = upload_dxf
        resp = client.post(
            "/api/plan",
            json={"session_id": session_id, "prompt": "move the first line east 24 units"},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert "operations" in data
        assert isinstance(data["operations"], list)

    def test_plan_returns_validation(self, client, upload_dxf):
        session_id, _ = upload_dxf
        resp = client.post(
            "/api/plan",
            json={"session_id": session_id, "prompt": "move column east"},
        )
        data = resp.json()
        v = data["validation"]
        assert "is_valid" in v
        assert "blockers" in v
        assert "warnings" in v

    def test_plan_returns_summary(self, client, upload_dxf):
        session_id, _ = upload_dxf
        resp = client.post(
            "/api/plan",
            json={"session_id": session_id, "prompt": "delete a line"},
        )
        data = resp.json()
        assert "summary" in data
        assert isinstance(data["summary"], str)

    def test_plan_no_session(self, client):
        resp = client.post(
            "/api/plan",
            json={"session_id": "nonexistent000000", "prompt": "anything"},
        )
        assert resp.status_code == 404

    def test_plan_wrong_user(self, client, sample_dxf_bytes):
        """Upload as user A, then try to plan as user B."""
        from web.backend.main import app, get_user

        # Upload as user-A
        async def user_a():
            return {"uid": "user-A", "email": "a@test.com"}

        app.dependency_overrides[get_user] = user_a
        resp = client.post(
            "/api/upload",
            files={"file": ("test.dxf", sample_dxf_bytes, "application/octet-stream")},
        )
        sid = resp.json()["session_id"]

        # Plan as user-B
        async def user_b():
            return {"uid": "user-B", "email": "b@test.com"}

        app.dependency_overrides[get_user] = user_b
        resp = client.post(
            "/api/plan",
            json={"session_id": sid, "prompt": "move something"},
        )
        assert resp.status_code == 404

    def test_plan_no_file_loaded(self, client):
        """Create a session manually without uploading a file."""
        from web.backend.main import session_mgr

        session = session_mgr.create(user_id="test-user-123")
        resp = client.post(
            "/api/plan",
            json={"session_id": session.session_id, "prompt": "move something"},
        )
        assert resp.status_code == 400
        assert "No file loaded" in resp.json()["detail"]

    def test_plan_empty_prompt(self, client, upload_dxf):
        """Empty prompt still goes through the mock planner."""
        session_id, _ = upload_dxf
        resp = client.post(
            "/api/plan",
            json={"session_id": session_id, "prompt": ""},
        )
        # Mock planner should still return a response (possibly empty ops)
        assert resp.status_code == 200

    def test_plan_requires_auth(self, unauth_client):
        resp = unauth_client.post(
            "/api/plan",
            json={"session_id": "anything", "prompt": "move"},
        )
        assert resp.status_code == 401

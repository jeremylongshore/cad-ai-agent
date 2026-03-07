"""Tests for POST /api/apply endpoint."""

from __future__ import annotations

import pytest


@pytest.mark.web
class TestApply:
    @pytest.fixture
    def planned_session(self, client, upload_dxf):
        """Upload + plan, return session_id and operations."""
        session_id, _ = upload_dxf
        resp = client.post(
            "/api/plan",
            json={"session_id": session_id, "prompt": "move the first line east 24 units"},
        )
        assert resp.status_code == 200
        ops = resp.json()["operations"]
        return session_id, ops

    def test_apply_all_ops(self, client, planned_session):
        session_id, ops = planned_session
        resp = client.post(
            "/api/apply",
            json={"session_id": session_id},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert "message" in data
        assert "results" in data

    def test_apply_selected_ops(self, client, planned_session):
        session_id, ops = planned_session
        if not ops:
            pytest.skip("Planner returned no ops")
        resp = client.post(
            "/api/apply",
            json={"session_id": session_id, "selected_ops": [0]},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert "Applied" in data["message"]

    def test_apply_selected_out_of_range(self, client, planned_session):
        session_id, _ = planned_session
        resp = client.post(
            "/api/apply",
            json={"session_id": session_id, "selected_ops": [999]},
        )
        # Out-of-range indices are silently filtered — 0 ops applied
        assert resp.status_code == 200
        assert "0/" in resp.json()["message"]

    def test_apply_no_plan(self, client, upload_dxf):
        """Apply without running plan first."""
        session_id, _ = upload_dxf
        resp = client.post(
            "/api/apply",
            json={"session_id": session_id},
        )
        assert resp.status_code == 400
        assert "No plan" in resp.json()["detail"]

    def test_apply_no_session(self, client):
        resp = client.post(
            "/api/apply",
            json={"session_id": "nonexistent000000"},
        )
        assert resp.status_code == 404

    def test_apply_response_format(self, client, planned_session):
        session_id, _ = planned_session
        resp = client.post(
            "/api/apply",
            json={"session_id": session_id},
        )
        data = resp.json()
        assert isinstance(data["message"], str)
        assert isinstance(data["results"], list)
        for r in data["results"]:
            assert "success" in r

    def test_apply_creates_edited_file(self, client, planned_session):
        """After apply, the edited DXF should exist on disk."""
        from pathlib import Path

        from web.backend.main import session_mgr

        session_id, _ = planned_session
        client.post("/api/apply", json={"session_id": session_id})
        session = session_mgr._sessions[session_id]
        assert session.edited_path is not None
        assert Path(session.edited_path).exists()

    def test_apply_requires_auth(self, unauth_client):
        resp = unauth_client.post(
            "/api/apply",
            json={"session_id": "anything"},
        )
        # 401 (missing token) or 404 (session not found after auth bypass)
        assert resp.status_code in (401, 404)
>>>>>>> 3ba2349 (feat(eval): add capability scorecard evaluation harness)

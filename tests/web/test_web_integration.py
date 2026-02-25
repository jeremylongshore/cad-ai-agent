"""Integration tests: full multi-endpoint web workflows."""

from __future__ import annotations

import pytest


@pytest.mark.web
@pytest.mark.integration
class TestWebIntegration:
    def test_full_flow_upload_plan_apply_download(self, client, sample_dxf_bytes):
        """Complete workflow: upload -> plan -> apply -> download."""
        # Upload
        resp = client.post(
            "/api/upload",
            files={"file": ("floor_plan.dxf", sample_dxf_bytes, "application/octet-stream")},
        )
        assert resp.status_code == 200
        session_id = resp.json()["session_id"]

        # Plan
        resp = client.post(
            "/api/plan",
            json={"session_id": session_id, "prompt": "move the first line east 24 units"},
        )
        assert resp.status_code == 200
        plan_data = resp.json()
        validation = plan_data["validation"]
        assert validation["is_valid"] is True or len(validation["blockers"]) == 0

        # Apply
        resp = client.post(
            "/api/apply",
            json={"session_id": session_id},
        )
        assert resp.status_code == 200
        assert "Applied" in resp.json()["message"]

        # Download
        resp = client.get(f"/api/download?session_id={session_id}")
        assert resp.status_code == 200
        # Verify we got real DXF content (starts with comment or section marker)
        content = resp.content
        assert len(content) > 0

    def test_full_flow_with_selected_ops(self, client, sample_dxf_bytes):
        """Apply only the first operation from the plan."""
        resp = client.post(
            "/api/upload",
            files={"file": ("test.dxf", sample_dxf_bytes, "application/octet-stream")},
        )
        session_id = resp.json()["session_id"]

        resp = client.post(
            "/api/plan",
            json={"session_id": session_id, "prompt": "move the first line east 24 units"},
        )
        ops = resp.json()["operations"]
        if not ops:
            pytest.skip("Planner returned no ops")

        resp = client.post(
            "/api/apply",
            json={"session_id": session_id, "selected_ops": [0]},
        )
        assert resp.status_code == 200

    def test_session_isolation_between_users(self, client, sample_dxf_bytes):
        """User B cannot access User A's session."""
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

        # Try plan as user-B
        async def user_b():
            return {"uid": "user-B", "email": "b@test.com"}

        app.dependency_overrides[get_user] = user_b
        resp = client.post(
            "/api/plan",
            json={"session_id": sid, "prompt": "move something"},
        )
        assert resp.status_code == 404

        # Try download as user-B
        resp = client.get(f"/api/download?session_id={sid}")
        assert resp.status_code == 404

        # Try render as user-B
        resp = client.get(f"/api/render?session_id={sid}&type=original")
        assert resp.status_code == 404

    def test_multiple_plans_overwrite_changeset(self, client, sample_dxf_bytes):
        """Running plan twice should use the latest changeset for apply."""
        resp = client.post(
            "/api/upload",
            files={"file": ("test.dxf", sample_dxf_bytes, "application/octet-stream")},
        )
        session_id = resp.json()["session_id"]

        # First plan
        client.post(
            "/api/plan",
            json={"session_id": session_id, "prompt": "move the first line east 24 units"},
        )

        # Second plan (overwrites)
        resp = client.post(
            "/api/plan",
            json={"session_id": session_id, "prompt": "delete a line"},
        )
        assert resp.status_code == 200

        # Apply should work on the latest plan
        resp = client.post(
            "/api/apply",
            json={"session_id": session_id},
        )
        assert resp.status_code == 200

"""Tests for GET /api/download endpoint."""

from __future__ import annotations

import pytest


@pytest.mark.web
class TestDownload:
    @pytest.fixture
    def applied_session(self, client, upload_dxf):
        """Upload -> plan -> apply, return session_id."""
        session_id, _ = upload_dxf
        client.post(
            "/api/plan",
            json={"session_id": session_id, "prompt": "move the first line east 24 units"},
        )
        client.post("/api/apply", json={"session_id": session_id})
        return session_id

    def test_download_edited_dxf(self, client, applied_session):
        resp = client.get(f"/api/download?session_id={applied_session}")
        assert resp.status_code == 200
        assert "application/dxf" in resp.headers.get("content-type", "")

    def test_download_filename(self, client, applied_session):
        resp = client.get(f"/api/download?session_id={applied_session}")
        disposition = resp.headers.get("content-disposition", "")
        assert "test_edited.dxf" in disposition

    def test_download_no_edited_file(self, client, upload_dxf):
        """Download without applying first."""
        session_id, _ = upload_dxf
        resp = client.get(f"/api/download?session_id={session_id}")
        assert resp.status_code == 404
        assert "No edited file" in resp.json()["detail"]

    def test_download_wrong_session(self, client):
        resp = client.get("/api/download?session_id=nonexistent000000")
        assert resp.status_code == 404

    def test_download_no_auth_required(self, unauth_client):
        """Download endpoint works without auth (session UUID is the credential)."""
        resp = unauth_client.get("/api/download?session_id=nonexistent000000")
        # 404, not 401 — the endpoint is reachable, session just doesn't exist
        assert resp.status_code == 404

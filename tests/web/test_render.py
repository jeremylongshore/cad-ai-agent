"""Tests for GET /api/render endpoint."""

from __future__ import annotations

from pathlib import Path

import pytest


@pytest.mark.web
class TestRender:
    def test_render_original_png(self, client, upload_dxf, tiny_png):
        """Render original after upload (with pre-populated PNG)."""
        from web.backend.main import session_mgr

        session_id, _ = upload_dxf
        session = session_mgr._sessions[session_id]
        # Write a tiny PNG as the original render
        png_path = Path("/tmp/cad-sessions") / session_id / "original.png"
        png_path.write_bytes(tiny_png)
        session.original_render = png_path

        resp = client.get(f"/api/render?session_id={session_id}&type=original")
        assert resp.status_code == 200
        assert resp.headers["content-type"].startswith("image/png")

    def test_render_edited_png(self, client, upload_dxf, tiny_png):
        from web.backend.main import session_mgr

        session_id, _ = upload_dxf
        session = session_mgr._sessions[session_id]
        png_path = Path("/tmp/cad-sessions") / session_id / "edited.png"
        png_path.write_bytes(tiny_png)
        session.edited_render = png_path

        resp = client.get(f"/api/render?session_id={session_id}&type=edited")
        assert resp.status_code == 200

    def test_render_not_available(self, client, upload_dxf):
        """Original render not generated — should 404."""
        from web.backend.main import session_mgr

        session_id, _ = upload_dxf
        session = session_mgr._sessions[session_id]
        session.original_render = None

        resp = client.get(f"/api/render?session_id={session_id}&type=original")
        assert resp.status_code == 404

    def test_render_invalid_type(self, client, upload_dxf):
        session_id, _ = upload_dxf
        resp = client.get(f"/api/render?session_id={session_id}&type=foobar")
        assert resp.status_code == 404

    def test_render_wrong_session(self, client):
        resp = client.get("/api/render?session_id=nonexistent000000&type=original")
        assert resp.status_code == 404

    def test_render_requires_auth(self, unauth_client):
        """Render endpoint requires authentication."""
        resp = unauth_client.get("/api/render?session_id=nonexistent000000&type=original")
        assert resp.status_code == 401

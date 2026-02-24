"""Tests for consistent error response format across endpoints."""

from __future__ import annotations

import pytest


@pytest.mark.web
class TestErrorFormat:
    def test_404_has_detail(self, client):
        """Non-existent session returns {"detail": "..."}."""
        resp = client.post(
            "/api/plan",
            json={"session_id": "nonexistent000000", "prompt": "x"},
        )
        assert resp.status_code == 404
        assert "detail" in resp.json()

    def test_400_has_detail(self, client):
        """Invalid file type returns {"detail": "..."}."""
        resp = client.post(
            "/api/upload",
            files={"file": ("bad.txt", b"not a dxf", "text/plain")},
        )
        assert resp.status_code == 400
        assert "detail" in resp.json()

    def test_401_has_detail(self, unauth_client, sample_dxf_bytes):
        """Missing auth returns {"detail": "..."}."""
        resp = unauth_client.post(
            "/api/upload",
            files={"file": ("test.dxf", sample_dxf_bytes, "application/octet-stream")},
        )
        assert resp.status_code == 401
        assert "detail" in resp.json()

    def test_422_has_detail(self, client):
        """Corrupt DXF returns {"detail": "..."}."""
        resp = client.post(
            "/api/upload",
            files={"file": ("broken.dxf", b"garbage bytes", "application/octet-stream")},
        )
        assert resp.status_code == 422
        assert "detail" in resp.json()

    def test_missing_file_field_422(self, client):
        """Missing required field returns 422 with detail."""
        resp = client.post("/api/upload")
        assert resp.status_code == 422
        body = resp.json()
        assert "detail" in body

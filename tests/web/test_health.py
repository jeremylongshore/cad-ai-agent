"""Tests for GET /api/health endpoint."""

from __future__ import annotations

import pytest


@pytest.mark.web
class TestHealth:
    def test_health_returns_ok(self, client):
        resp = client.get("/api/health")
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "ok"
        assert data["service"] == "cad-dxf-web"

    def test_health_no_auth_required(self, unauth_client):
        """Health endpoint should work without any auth token."""
        resp = unauth_client.get("/api/health")
        assert resp.status_code == 200
        assert resp.json()["status"] == "ok"

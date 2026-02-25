"""Tests for CORS header configuration."""

from __future__ import annotations

import pytest


@pytest.mark.web
class TestCORS:
    def test_cors_allows_localhost(self, client):
        resp = client.options(
            "/api/health",
            headers={
                "Origin": "http://localhost:3000",
                "Access-Control-Request-Method": "GET",
            },
        )
        assert resp.headers.get("access-control-allow-origin") == "http://localhost:3000"

    def test_cors_allows_firebase_origin(self, client):
        resp = client.options(
            "/api/health",
            headers={
                "Origin": "https://cad-dxf-agent.web.app",
                "Access-Control-Request-Method": "GET",
            },
        )
        assert resp.headers.get("access-control-allow-origin") == "https://cad-dxf-agent.web.app"

    def test_cors_blocks_unknown_origin(self, client):
        resp = client.options(
            "/api/health",
            headers={
                "Origin": "https://evil.com",
                "Access-Control-Request-Method": "GET",
            },
        )
        # No ACAO header for disallowed origins
        acao = resp.headers.get("access-control-allow-origin")
        assert acao is None or "evil.com" not in acao

    def test_cors_allowed_origins_list(self):
        """Verify the hardcoded allowed origins include expected values."""
        from web.backend.main import ALLOWED_ORIGINS

        assert "http://localhost:3000" in ALLOWED_ORIGINS
        assert "https://cad-dxf-agent.web.app" in ALLOWED_ORIGINS
        assert "https://cad-dxf-agent.firebaseapp.com" in ALLOWED_ORIGINS

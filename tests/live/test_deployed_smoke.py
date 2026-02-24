"""Live smoke tests against the deployed web backend.

Requires CAD_WEB_URL env var (e.g., https://cad-dxf-agent.web.app).
Auto-skips if not set.
"""

from __future__ import annotations

import os

import httpx
import pytest

CAD_WEB_URL = os.getenv("CAD_WEB_URL", "")


def skip_if_no_url():
    if not CAD_WEB_URL:
        pytest.skip("CAD_WEB_URL not set — skipping live web tests")


@pytest.mark.web_live
class TestDeployedSmoke:
    def test_deployed_health_check(self):
        skip_if_no_url()
        resp = httpx.get(f"{CAD_WEB_URL}/api/health", timeout=30)
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "ok"

    def test_deployed_upload_requires_auth(self):
        skip_if_no_url()
        resp = httpx.post(
            f"{CAD_WEB_URL}/api/upload",
            files={"file": ("test.dxf", b"fake content", "application/octet-stream")},
            timeout=30,
        )
        assert resp.status_code == 401

    def test_deployed_cors_headers(self):
        skip_if_no_url()
        resp = httpx.options(
            f"{CAD_WEB_URL}/api/health",
            headers={
                "Origin": "https://cad-dxf-agent.web.app",
                "Access-Control-Request-Method": "GET",
            },
            timeout=30,
        )
        acao = resp.headers.get("access-control-allow-origin", "")
        assert "cad-dxf-agent.web.app" in acao

"""Tests for the POST /api/drawing-health endpoint."""

from __future__ import annotations

from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from tests.helpers.dxf_factory import create_structural_drawing


@pytest.fixture()
def client():
    """Create a test client with dev mode enabled."""
    import os

    old = os.environ.get("CAD_WEB_DEV_MODE")
    os.environ["CAD_WEB_DEV_MODE"] = "1"
    from web.backend.main import app

    with TestClient(app) as c:
        yield c
    if old is None:
        os.environ.pop("CAD_WEB_DEV_MODE", None)
    else:
        os.environ["CAD_WEB_DEV_MODE"] = old


@pytest.fixture()
def session_with_dxf(client: TestClient, tmp_path: Path):
    """Upload a DXF and return the session_id."""
    dxf_path = create_structural_drawing(tmp_path)
    with open(dxf_path, "rb") as f:
        resp = client.post("/api/upload", files={"file": ("test.dxf", f)})
    assert resp.status_code == 200
    return resp.json()["session_id"]


class TestDrawingHealthEndpoint:
    """Test POST /api/drawing-health."""

    def test_health_check_success(self, client, session_with_dxf):
        resp = client.post(
            "/api/drawing-health",
            json={"session_id": session_with_dxf},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert "score" in data
        assert "issues" in data
        assert "checks_run" in data
        assert "entity_count" in data
        assert isinstance(data["score"], (int, float))
        assert 0 <= data["score"] <= 100
        assert isinstance(data["issues"], list)

    def test_health_check_invalid_session(self, client):
        resp = client.post(
            "/api/drawing-health",
            json={"session_id": "nonexistent-session"},
        )
        assert resp.status_code in (400, 404)

    def test_health_check_missing_session_id(self, client):
        resp = client.post("/api/drawing-health", json={})
        assert resp.status_code == 422  # Pydantic validation error

    def test_health_report_issues_structure(self, client, session_with_dxf):
        resp = client.post(
            "/api/drawing-health",
            json={"session_id": session_with_dxf},
        )
        data = resp.json()
        for issue in data["issues"]:
            assert "severity" in issue
            assert "category" in issue
            assert "title" in issue
            assert "description" in issue
            assert issue["severity"] in ("critical", "warning", "info")

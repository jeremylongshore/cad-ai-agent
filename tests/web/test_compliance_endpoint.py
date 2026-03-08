"""Tests for POST /api/drawing-compliance and GET /api/compliance-profiles."""

from __future__ import annotations

from pathlib import Path

import pytest

starlette = pytest.importorskip("starlette", reason="web tests require fastapi/starlette")

from fastapi.testclient import TestClient  # noqa: E402

from tests.helpers.dxf_factory import create_structural_drawing  # noqa: E402


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


# ---------------------------------------------------------------------------
# GET /api/compliance-profiles
# ---------------------------------------------------------------------------


@pytest.mark.web
class TestComplianceProfilesList:
    def test_profiles_returns_200(self, client):
        resp = client.get("/api/compliance-profiles")
        assert resp.status_code == 200

    def test_profiles_has_builtin_entries(self, client):
        resp = client.get("/api/compliance-profiles")
        data = resp.json()
        assert "ada" in data
        assert "ibc-2021" in data
        assert "residential" in data

    def test_profile_has_name_and_description(self, client):
        resp = client.get("/api/compliance-profiles")
        ada = resp.json()["ada"]
        assert "name" in ada
        assert "description" in ada
        assert "enabled_categories" in ada

    def test_profile_categories_are_list(self, client):
        resp = client.get("/api/compliance-profiles")
        ibc = resp.json()["ibc-2021"]
        assert isinstance(ibc["enabled_categories"], list)
        assert len(ibc["enabled_categories"]) > 0


# ---------------------------------------------------------------------------
# POST /api/drawing-compliance
# ---------------------------------------------------------------------------


@pytest.mark.web
class TestComplianceEndpoint:
    def test_compliance_returns_200(self, client, session_with_dxf):
        resp = client.post(
            "/api/drawing-compliance",
            json={"session_id": session_with_dxf},
        )
        assert resp.status_code == 200

    def test_compliance_default_profile_is_ibc(self, client, session_with_dxf):
        resp = client.post(
            "/api/drawing-compliance",
            json={"session_id": session_with_dxf},
        )
        assert resp.json()["profile"] == "ibc-2021"

    def test_compliance_ada_profile(self, client, session_with_dxf):
        resp = client.post(
            "/api/drawing-compliance",
            json={"session_id": session_with_dxf, "profile": "ada"},
        )
        assert resp.status_code == 200
        assert resp.json()["profile"] == "ada"

    def test_compliance_residential_profile(self, client, session_with_dxf):
        resp = client.post(
            "/api/drawing-compliance",
            json={"session_id": session_with_dxf, "profile": "residential"},
        )
        assert resp.status_code == 200
        assert resp.json()["profile"] == "residential"

    def test_compliance_unknown_profile_returns_422(self, client, session_with_dxf):
        resp = client.post(
            "/api/drawing-compliance",
            json={"session_id": session_with_dxf, "profile": "nonexistent"},
        )
        assert resp.status_code == 422

    def test_compliance_response_structure(self, client, session_with_dxf):
        resp = client.post(
            "/api/drawing-compliance",
            json={"session_id": session_with_dxf},
        )
        data = resp.json()
        assert "profile" in data
        assert "passed" in data
        assert "score" in data
        assert "findings" in data
        assert "checks_run" in data
        assert "violation_count" in data
        assert "warning_count" in data
        assert "pass_count" in data

    def test_compliance_score_is_numeric(self, client, session_with_dxf):
        resp = client.post(
            "/api/drawing-compliance",
            json={"session_id": session_with_dxf},
        )
        score = resp.json()["score"]
        assert isinstance(score, (int, float))
        assert 0 <= score <= 100

    def test_compliance_findings_are_list(self, client, session_with_dxf):
        resp = client.post(
            "/api/drawing-compliance",
            json={"session_id": session_with_dxf},
        )
        findings = resp.json()["findings"]
        assert isinstance(findings, list)

    def test_compliance_checks_run_non_empty(self, client, session_with_dxf):
        resp = client.post(
            "/api/drawing-compliance",
            json={"session_id": session_with_dxf},
        )
        assert len(resp.json()["checks_run"]) > 0

    def test_compliance_invalid_session_returns_404(self, client):
        resp = client.post(
            "/api/drawing-compliance",
            json={"session_id": "nonexistent-session"},
        )
        assert resp.status_code == 404

    def test_compliance_passed_is_boolean(self, client, session_with_dxf):
        resp = client.post(
            "/api/drawing-compliance",
            json={"session_id": session_with_dxf},
        )
        assert isinstance(resp.json()["passed"], bool)

    def test_compliance_entity_count_matches_drawing(self, client, session_with_dxf):
        resp = client.post(
            "/api/drawing-compliance",
            json={"session_id": session_with_dxf},
        )
        assert resp.json()["entity_count"] > 0

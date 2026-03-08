"""Tests for design-ops task family dispatch via POST /api/v2/prompt.

All requests go through the intent router. Session state is injected via
SessionManager.get mock so no real file upload is required. The planner
is never called -- design-ops are fully deterministic.
"""

from __future__ import annotations

import time
from pathlib import Path
from unittest.mock import patch

import pytest

starlette = pytest.importorskip("starlette", reason="web tests require fastapi/starlette")

from starlette.testclient import TestClient  # noqa: E402
from web.backend.main import app, get_user  # noqa: E402
from web.backend.session import Session, SessionManager  # noqa: E402

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture(autouse=True)
def _auth_override():
    """Override auth to return a stable dev user for all tests in this module."""

    async def _dev_user():
        return {"uid": "dev-user", "email": "dev@test.local"}

    app.dependency_overrides[get_user] = _dev_user
    yield
    app.dependency_overrides.pop(get_user, None)


@pytest.fixture(autouse=True)
def _clean_sessions():
    """Reset session manager between tests."""
    from web.backend.main import session_mgr

    yield
    for sid in list(session_mgr._sessions.keys()):
        session_mgr.delete(sid)


@pytest.fixture
def client():
    with TestClient(app, raise_server_exceptions=False) as c:
        yield c


@pytest.fixture
def mock_session():
    """Inject a DrawingContext-loaded session without a real DXF upload."""
    from cad_dxf_agent.models.cad_schema import (
        DrawingContext,
        EntityRef,
        EntityType,
        LayerRule,
        Point2D,
    )

    entities = [
        EntityRef(
            handle=f"H{i}",
            entity_type=EntityType.INSERT,
            layer="STRUCTURAL",
            block_name="COLUMN_MARK",
            insert_point=Point2D(x=float(i * 10), y=0.0),
        )
        for i in range(5)
    ]
    ctx = DrawingContext(
        file_path="test.dxf",
        entities=entities,
        layers=[LayerRule(name="STRUCTURAL")],
    )

    session = Session(
        session_id="test-session",
        user_id="dev-user",
        created_at=time.time(),
        original_path=Path("/tmp/test.dxf"),
    )
    session.context = ctx

    with patch.object(SessionManager, "get", return_value=session):
        yield session


# ---------------------------------------------------------------------------
# DESIGN_ASSIST -- layout recommendations
# ---------------------------------------------------------------------------


@pytest.mark.web
class TestDesignAssistEndpoint:
    def test_design_assist_prompt_returns_200(self, client, mock_session):
        resp = client.post(
            "/api/v2/prompt",
            json={"session_id": "test-session", "prompt": "suggest layout improvements"},
        )
        assert resp.status_code == 200

    def test_design_assist_task_family(self, client, mock_session):
        resp = client.post(
            "/api/v2/prompt",
            json={"session_id": "test-session", "prompt": "suggest layout improvements"},
        )
        assert resp.json()["task_family"] == "design_assist"

    def test_design_assist_response_type_is_answer_only(self, client, mock_session):
        resp = client.post(
            "/api/v2/prompt",
            json={"session_id": "test-session", "prompt": "suggest layout improvements"},
        )
        assert resp.json()["response_type"] == "answer_only"

    def test_design_assist_scope_prompt_has_sections(self, client, mock_session):
        resp = client.post(
            "/api/v2/prompt",
            json={"session_id": "test-session", "prompt": "scope of work summary"},
        )
        data = resp.json()
        assert resp.status_code == 200
        assert "sections" in data["data"]

    def test_design_assist_has_no_edit_operations(self, client, mock_session):
        resp = client.post(
            "/api/v2/prompt",
            json={"session_id": "test-session", "prompt": "suggest layout improvements"},
        )
        assert resp.json()["operations"] == []

    def test_design_assist_risk_level_is_none(self, client, mock_session):
        resp = client.post(
            "/api/v2/prompt",
            json={"session_id": "test-session", "prompt": "suggest layout improvements"},
        )
        assert resp.json()["risk_level"] == "none"


# ---------------------------------------------------------------------------
# SUMMARY -- revision summarizer
# ---------------------------------------------------------------------------


@pytest.mark.web
class TestSummaryEndpoint:
    def test_summary_prompt_returns_200(self, client, mock_session):
        resp = client.post(
            "/api/v2/prompt",
            json={"session_id": "test-session", "prompt": "summarize the drawing"},
        )
        assert resp.status_code == 200

    def test_summary_task_family(self, client, mock_session):
        resp = client.post(
            "/api/v2/prompt",
            json={"session_id": "test-session", "prompt": "summarize the drawing"},
        )
        assert resp.json()["task_family"] == "summary"

    def test_summary_response_type_is_answer_only(self, client, mock_session):
        resp = client.post(
            "/api/v2/prompt",
            json={"session_id": "test-session", "prompt": "summarize the drawing"},
        )
        assert resp.json()["response_type"] == "answer_only"

    def test_summary_data_has_headline(self, client, mock_session):
        resp = client.post(
            "/api/v2/prompt",
            json={"session_id": "test-session", "prompt": "summarize the drawing"},
        )
        data = resp.json()
        assert "headline" in data["data"]

    def test_summary_has_no_edit_operations(self, client, mock_session):
        resp = client.post(
            "/api/v2/prompt",
            json={"session_id": "test-session", "prompt": "summarize the drawing"},
        )
        assert resp.json()["operations"] == []

    def test_summary_risk_level_is_none(self, client, mock_session):
        resp = client.post(
            "/api/v2/prompt",
            json={"session_id": "test-session", "prompt": "summarize the drawing"},
        )
        assert resp.json()["risk_level"] == "none"


# ---------------------------------------------------------------------------
# TAKEOFF_ESTIMATE -- entity counting
# ---------------------------------------------------------------------------


@pytest.mark.web
class TestTakeoffEstimateEndpoint:
    def test_takeoff_prompt_returns_200(self, client, mock_session):
        resp = client.post(
            "/api/v2/prompt",
            json={
                "session_id": "test-session",
                "prompt": "estimate the quantity of columns",
            },
        )
        assert resp.status_code == 200

    def test_takeoff_task_family(self, client, mock_session):
        resp = client.post(
            "/api/v2/prompt",
            json={
                "session_id": "test-session",
                "prompt": "estimate the quantity of columns",
            },
        )
        assert resp.json()["task_family"] == "takeoff_estimate"

    def test_takeoff_response_type_is_answer_only(self, client, mock_session):
        resp = client.post(
            "/api/v2/prompt",
            json={
                "session_id": "test-session",
                "prompt": "estimate the quantity of columns",
            },
        )
        assert resp.json()["response_type"] == "answer_only"

    def test_takeoff_data_has_items(self, client, mock_session):
        resp = client.post(
            "/api/v2/prompt",
            json={
                "session_id": "test-session",
                "prompt": "estimate the quantity of columns",
            },
        )
        data = resp.json()
        assert "items" in data["data"]

    def test_takeoff_has_no_edit_operations(self, client, mock_session):
        resp = client.post(
            "/api/v2/prompt",
            json={
                "session_id": "test-session",
                "prompt": "estimate the quantity of columns",
            },
        )
        assert resp.json()["operations"] == []

    def test_takeoff_risk_level_is_none(self, client, mock_session):
        resp = client.post(
            "/api/v2/prompt",
            json={
                "session_id": "test-session",
                "prompt": "estimate the quantity of columns",
            },
        )
        assert resp.json()["risk_level"] == "none"


# ---------------------------------------------------------------------------
# Needs-clarification fallback
# ---------------------------------------------------------------------------


@pytest.mark.web
class TestNeedsClarificationFallback:
    def test_empty_prompt_returns_needs_clarification(self, client, mock_session):
        resp = client.post(
            "/api/v2/prompt",
            json={"session_id": "test-session", "prompt": ""},
        )
        assert resp.status_code == 200
        assert resp.json()["response_type"] == "needs_clarification"

    def test_unrecognised_prompt_returns_needs_clarification(self, client, mock_session):
        resp = client.post(
            "/api/v2/prompt",
            json={"session_id": "test-session", "prompt": "xyzzy frobnicate quux"},
        )
        assert resp.status_code == 200
        assert resp.json()["response_type"] == "needs_clarification"

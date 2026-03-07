"""Tests for construction-ops task family dispatch via POST /api/v2/prompt.

All requests go through the intent router. Session state is injected via
SessionManager.get mock so no real file upload is required. Generators
are fully deterministic -- no LLM.
"""

from __future__ import annotations

import os
import time
from pathlib import Path
from unittest.mock import patch

import pytest

starlette = pytest.importorskip("starlette", reason="web tests require fastapi/starlette")

# Must be set before importing the app so the auth middleware sees it.
os.environ["CAD_WEB_DEV_MODE"] = "1"

from starlette.testclient import TestClient  # noqa: E402
from web.backend.main import app, get_user  # noqa: E402
from web.backend.session import Session, SessionManager  # noqa: E402

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture(autouse=True)
def _auth_override():
    async def _dev_user():
        return {"uid": "dev-user", "email": "dev@test.local"}

    app.dependency_overrides[get_user] = _dev_user
    yield
    app.dependency_overrides.pop(get_user, None)


@pytest.fixture(autouse=True)
def _clean_sessions():
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
    """Session with block inserts on STRUCTURAL, grid lines, and a cloud."""
    from cad_dxf_agent.models.cad_schema import (
        DrawingContext,
        EntityRef,
        EntityType,
        LayerRule,
        Point2D,
    )

    entities = [
        # Block inserts (for takeoff, batch condition)
        EntityRef(
            handle=f"H{i}",
            entity_type=EntityType.INSERT,
            layer="STRUCTURAL",
            block_name="COLUMN_MARK",
            insert_point=Point2D(x=float(i * 10), y=0.0),
        )
        for i in range(5)
    ] + [
        # LWPOLYLINE on CLOUD layer (for markup redline)
        EntityRef(
            handle="CLD1",
            entity_type=EntityType.LWPOLYLINE,
            layer="CLOUD",
            insert_point=Point2D(x=0.0, y=0.0),
            attributes={"vertices": [(0, 0), (50, 0), (50, 50), (0, 50)]},
        ),
        # LINE on GRID layer (for grid analysis)
        EntityRef(
            handle="GL1",
            entity_type=EntityType.LINE,
            layer="GRID",
            insert_point=Point2D(x=0.0, y=0.0),
            attributes={"end_point": (0.0, 100.0)},
        ),
        EntityRef(
            handle="GL2",
            entity_type=EntityType.LINE,
            layer="GRID",
            insert_point=Point2D(x=30.0, y=0.0),
            attributes={"end_point": (30.0, 100.0)},
        ),
    ]
    ctx = DrawingContext(
        file_path="test.dxf",
        entities=entities,
        layers=[
            LayerRule(name="STRUCTURAL"),
            LayerRule(name="CLOUD"),
            LayerRule(name="GRID"),
        ],
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
# DESIGN_ASSIST -- grid summary via sub-dispatch
# ---------------------------------------------------------------------------


@pytest.mark.web
class TestGridSummaryEndpoint:
    def test_grid_summary_prompt_returns_200(self, client, mock_session):
        resp = client.post(
            "/api/v2/prompt",
            json={"session_id": "test-session", "prompt": "show me the structural grid"},
        )
        assert resp.status_code == 200

    def test_grid_summary_task_family(self, client, mock_session):
        resp = client.post(
            "/api/v2/prompt",
            json={"session_id": "test-session", "prompt": "grid summary"},
        )
        assert resp.json()["task_family"] == "design_assist"

    def test_grid_summary_response_type(self, client, mock_session):
        resp = client.post(
            "/api/v2/prompt",
            json={"session_id": "test-session", "prompt": "grid summary"},
        )
        assert resp.json()["response_type"] == "answer_only"

    def test_grid_summary_has_grid_lines_in_data(self, client, mock_session):
        resp = client.post(
            "/api/v2/prompt",
            json={"session_id": "test-session", "prompt": "grid summary"},
        )
        data = resp.json()["data"]
        assert "grid_lines" in data

    def test_grid_summary_risk_level_is_none(self, client, mock_session):
        resp = client.post(
            "/api/v2/prompt",
            json={"session_id": "test-session", "prompt": "grid summary"},
        )
        assert resp.json()["risk_level"] == "none"

    def test_grid_summary_no_operations(self, client, mock_session):
        resp = client.post(
            "/api/v2/prompt",
            json={"session_id": "test-session", "prompt": "grid summary"},
        )
        assert resp.json()["operations"] == []


# ---------------------------------------------------------------------------
# MARKUP_INTERPRETATION -- redline report
# ---------------------------------------------------------------------------


@pytest.mark.web
class TestMarkupRedlineEndpoint:
    def test_redline_prompt_returns_200(self, client, mock_session):
        resp = client.post(
            "/api/v2/prompt",
            json={"session_id": "test-session", "prompt": "show me the redline clouds"},
        )
        assert resp.status_code == 200

    def test_redline_task_family(self, client, mock_session):
        resp = client.post(
            "/api/v2/prompt",
            json={"session_id": "test-session", "prompt": "show me the markup clouds"},
        )
        assert resp.json()["task_family"] == "markup_interpretation"

    def test_redline_response_type(self, client, mock_session):
        resp = client.post(
            "/api/v2/prompt",
            json={"session_id": "test-session", "prompt": "show me the markup clouds"},
        )
        assert resp.json()["response_type"] == "answer_only"

    def test_redline_has_entries_in_data(self, client, mock_session):
        resp = client.post(
            "/api/v2/prompt",
            json={"session_id": "test-session", "prompt": "show me the markup clouds"},
        )
        data = resp.json()["data"]
        assert "entries" in data

    def test_redline_risk_level_is_none(self, client, mock_session):
        resp = client.post(
            "/api/v2/prompt",
            json={"session_id": "test-session", "prompt": "show me the markup clouds"},
        )
        assert resp.json()["risk_level"] == "none"

    def test_redline_no_operations(self, client, mock_session):
        resp = client.post(
            "/api/v2/prompt",
            json={"session_id": "test-session", "prompt": "show me the markup clouds"},
        )
        assert resp.json()["operations"] == []


# ---------------------------------------------------------------------------
# REPEATED_CONDITION -- batch condition via sub-dispatch
# ---------------------------------------------------------------------------


@pytest.mark.web
class TestBatchConditionEndpoint:
    def test_batch_prompt_returns_200(self, client, mock_session):
        resp = client.post(
            "/api/v2/prompt",
            json={"session_id": "test-session", "prompt": "batch condition report"},
        )
        assert resp.status_code == 200

    def test_batch_task_family(self, client, mock_session):
        resp = client.post(
            "/api/v2/prompt",
            json={"session_id": "test-session", "prompt": "batch condition report"},
        )
        assert resp.json()["task_family"] == "repeated_condition"

    def test_batch_response_type(self, client, mock_session):
        resp = client.post(
            "/api/v2/prompt",
            json={"session_id": "test-session", "prompt": "batch condition report"},
        )
        assert resp.json()["response_type"] == "answer_only"

    def test_batch_risk_level_is_none(self, client, mock_session):
        resp = client.post(
            "/api/v2/prompt",
            json={"session_id": "test-session", "prompt": "batch condition report"},
        )
        assert resp.json()["risk_level"] == "none"

    def test_batch_no_operations(self, client, mock_session):
        resp = client.post(
            "/api/v2/prompt",
            json={"session_id": "test-session", "prompt": "batch condition report"},
        )
        assert resp.json()["operations"] == []


# ---------------------------------------------------------------------------
# DESIGN_ASSIST -- field summary via sub-dispatch
# ---------------------------------------------------------------------------


@pytest.mark.web
class TestFieldSummaryEndpoint:
    def test_field_summary_prompt_returns_200(self, client, mock_session):
        resp = client.post(
            "/api/v2/prompt",
            json={"session_id": "test-session", "prompt": "field summary"},
        )
        assert resp.status_code == 200

    def test_field_summary_task_family(self, client, mock_session):
        resp = client.post(
            "/api/v2/prompt",
            json={"session_id": "test-session", "prompt": "field summary"},
        )
        assert resp.json()["task_family"] == "design_assist"

    def test_field_summary_response_type(self, client, mock_session):
        resp = client.post(
            "/api/v2/prompt",
            json={"session_id": "test-session", "prompt": "field summary"},
        )
        assert resp.json()["response_type"] == "answer_only"

    def test_field_summary_has_sections(self, client, mock_session):
        resp = client.post(
            "/api/v2/prompt",
            json={"session_id": "test-session", "prompt": "field summary"},
        )
        data = resp.json()["data"]
        assert "sections" in data

    def test_field_summary_risk_level_is_none(self, client, mock_session):
        resp = client.post(
            "/api/v2/prompt",
            json={"session_id": "test-session", "prompt": "field summary"},
        )
        assert resp.json()["risk_level"] == "none"

    def test_field_summary_no_operations(self, client, mock_session):
        resp = client.post(
            "/api/v2/prompt",
            json={"session_id": "test-session", "prompt": "field summary"},
        )
        assert resp.json()["operations"] == []

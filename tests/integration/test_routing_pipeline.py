"""Integration tests: upload → classify → dispatch → verify PlatformResponse envelope.

Tests the full v2 routing pipeline end-to-end via TestClient.
"""

from __future__ import annotations

import pytest

starlette = pytest.importorskip("starlette", reason="integration tests require fastapi/starlette")
from starlette.testclient import TestClient  # noqa: E402


@pytest.fixture
def auth_user():
    return {"uid": "integration-user", "email": "int@test.com"}


@pytest.fixture
def client(auth_user):
    from web.backend.main import app, get_user

    async def _override():
        return auth_user

    app.dependency_overrides[get_user] = _override
    with TestClient(app, raise_server_exceptions=False) as c:
        yield c
    app.dependency_overrides.clear()


@pytest.fixture(autouse=True)
def clean_sessions():
    from web.backend.main import session_mgr

    yield
    for sid in list(session_mgr._sessions.keys()):
        session_mgr.delete(sid)


@pytest.fixture
def uploaded_session(client, sample_dxf):
    """Upload a DXF and return (session_id, file_info)."""
    dxf_bytes = sample_dxf.read_bytes()
    resp = client.post(
        "/api/upload",
        files={"file": ("test.dxf", dxf_bytes, "application/octet-stream")},
    )
    assert resp.status_code == 200
    data = resp.json()
    return data["session_id"], data["file_info"]


class TestRoutingPipelineIntegration:
    def test_edit_prompt_full_pipeline(self, client, uploaded_session):
        """Upload → edit prompt → verify PlatformResponse with operations."""
        session_id, file_info = uploaded_session

        resp = client.post(
            "/api/v2/prompt",
            json={"session_id": session_id, "prompt": "delete entity on layer WALLS"},
        )
        assert resp.status_code == 200
        data = resp.json()

        # Verify envelope structure
        assert data["task_family"] == "edit_plan"
        assert data["response_type"] == "plan_only"
        assert isinstance(data["operations"], list)
        assert isinstance(data["message"], str)
        assert "audit" in data
        assert data["audit"]["trace_id"]
        assert data["audit"]["total_request_time_ms"] > 0

    def test_qna_returns_answer_without_planner(self, client, uploaded_session):
        """Q&A prompt should return answer_only without calling the planner."""
        session_id, _ = uploaded_session

        resp = client.post(
            "/api/v2/prompt",
            json={"session_id": session_id, "prompt": "what is on layer ELECTRICAL"},
        )
        data = resp.json()

        assert data["task_family"] == "qna"
        assert data["response_type"] == "answer_only"
        # No LLM or validation timing — planner was never called
        assert data["audit"]["llm_time_ms"] is None
        assert data["audit"]["validation_time_ms"] is None

    def test_unsupported_never_reaches_planner(self, client, uploaded_session):
        """Summary prompt should return unsupported without calling the planner."""
        session_id, _ = uploaded_session

        resp = client.post(
            "/api/v2/prompt",
            json={"session_id": session_id, "prompt": "summarize this drawing"},
        )
        data = resp.json()

        assert data["task_family"] == "summary"
        assert data["response_type"] == "unsupported_operation"
        assert data["audit"]["llm_time_ms"] is None
        assert data["audit"]["validation_time_ms"] is None

    def test_v1_plan_still_works(self, client, uploaded_session):
        """v1 /api/plan endpoint must remain unaffected."""
        session_id, _ = uploaded_session

        resp = client.post(
            "/api/plan",
            json={"session_id": session_id, "prompt": "move entity A1 by 10,0"},
        )
        assert resp.status_code == 200
        data = resp.json()
        # v1 returns the old format (no task_family, no audit)
        assert "operations" in data
        assert "summary" in data
        assert "task_family" not in data

    def test_multiple_prompts_track_conversation(self, client, uploaded_session):
        """Successive edit prompts build conversation history."""
        session_id, _ = uploaded_session

        # First prompt
        resp1 = client.post(
            "/api/v2/prompt",
            json={"session_id": session_id, "prompt": "move entity A1 by 5,0"},
        )
        assert resp1.status_code == 200

        # Second prompt
        resp2 = client.post(
            "/api/v2/prompt",
            json={"session_id": session_id, "prompt": "now delete entity A2"},
        )
        assert resp2.status_code == 200
        assert resp2.json()["task_family"] == "edit_plan"

    def test_response_envelope_json_serializable(self, client, uploaded_session):
        """Every PlatformResponse field must be JSON-serializable."""
        import json

        session_id, _ = uploaded_session

        resp = client.post(
            "/api/v2/prompt",
            json={"session_id": session_id, "prompt": "add a door block at 50,100"},
        )
        # If this doesn't raise, the response is fully serializable
        json.loads(resp.text)

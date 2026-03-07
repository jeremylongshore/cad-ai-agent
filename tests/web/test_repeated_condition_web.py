"""Tests for repeated-condition handling via POST /api/v2/prompt."""

from __future__ import annotations

import pytest

starlette = pytest.importorskip("starlette", reason="web backend tests require fastapi/starlette")


class TestRepeatedConditionRouting:
    """Verify the repeated_condition task family flows through /api/v2/prompt."""

    def test_repeated_condition_needs_handles(self, client, upload_dxf):
        """No selected_regions → needs_clarification asking for exemplar."""
        session_id, _ = upload_dxf
        resp = client.post(
            "/api/v2/prompt",
            json={"session_id": session_id, "prompt": "find all repeated instances"},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["task_family"] == "repeated_condition"
        assert data["response_type"] == "needs_clarification"
        assert "select" in data["message"].lower() or "exemplar" in data["message"].lower()

    def test_repeated_condition_empty_handles(self, client, upload_dxf):
        """Empty handles list → needs_clarification."""
        session_id, _ = upload_dxf
        resp = client.post(
            "/api/v2/prompt",
            json={
                "session_id": session_id,
                "prompt": "find all repeated instances",
                "selected_regions": [{"handles": []}],
            },
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["response_type"] == "needs_clarification"

    def test_repeated_condition_with_valid_handles(self, client, upload_dxf, auth_user):
        """Valid exemplar handles → answer_only with result data."""
        session_id, file_info = upload_dxf
        # Grab entity handles from the loaded drawing context
        from web.backend.main import session_mgr

        session = session_mgr.get(session_id, user_id=auth_user["uid"])
        assert session is not None and session.context is not None
        handles = [e.handle for e in session.context.entities[:2]]

        resp = client.post(
            "/api/v2/prompt",
            json={
                "session_id": session_id,
                "prompt": "find all repeated instances",
                "selected_regions": [{"handles": handles}],
            },
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["task_family"] == "repeated_condition"
        assert data["response_type"] == "answer_only"
        # Result data should contain the repeated-condition result structure
        assert "data" in data
        result_data = data["data"]
        assert "exemplar_handles" in result_data
        assert "candidates" in result_data
        assert "summary" in result_data
        assert isinstance(result_data["candidates"], list)

    def test_repeated_condition_has_audit(self, client, upload_dxf):
        """Audit metadata is present on repeated-condition responses."""
        session_id, _ = upload_dxf
        resp = client.post(
            "/api/v2/prompt",
            json={"session_id": session_id, "prompt": "find all repeated patterns"},
        )
        assert resp.status_code == 200
        audit = resp.json()["audit"]
        assert audit["total_request_time_ms"] is not None
        assert "trace_id" in audit

    def test_repeated_condition_invalid_handles(self, client, upload_dxf):
        """Non-existent handles → answer_only with empty candidates."""
        session_id, _ = upload_dxf
        resp = client.post(
            "/api/v2/prompt",
            json={
                "session_id": session_id,
                "prompt": "find all repeated instances",
                "selected_regions": [{"handles": ["BOGUS_1", "BOGUS_2"]}],
            },
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["task_family"] == "repeated_condition"
        assert data["response_type"] == "answer_only"
        assert data["data"]["candidates"] == []
        assert "no valid" in data["data"]["summary"].lower()

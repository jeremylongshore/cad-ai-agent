"""Tests for POST /api/v2/prompt — intent-routed prompt endpoint."""

from __future__ import annotations

import pytest

starlette = pytest.importorskip("starlette", reason="web backend tests require fastapi/starlette")


class TestV2PromptAuth:
    def test_requires_auth(self, unauth_client):
        resp = unauth_client.post(
            "/api/v2/prompt",
            json={"session_id": "fake", "prompt": "move the wall"},
        )
        assert resp.status_code in (401, 403)

    def test_invalid_session(self, client):
        resp = client.post(
            "/api/v2/prompt",
            json={"session_id": "nonexistent", "prompt": "move the wall"},
        )
        assert resp.status_code == 404


class TestV2PromptRouting:
    def test_edit_plan_returns_plan_only(self, client, upload_dxf):
        session_id, _ = upload_dxf
        resp = client.post(
            "/api/v2/prompt",
            json={"session_id": session_id, "prompt": "move entity A1 by 10,0"},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["task_family"] == "edit_plan"
        assert data["response_type"] == "plan_only"
        assert "audit" in data
        assert data["audit"]["router_source"] == "heuristic"
        assert data["audit"]["router_time_ms"] >= 0

    def test_qna_returns_answer(self, client, upload_dxf):
        session_id, _ = upload_dxf
        resp = client.post(
            "/api/v2/prompt",
            json={"session_id": session_id, "prompt": "what is on layer WALLS"},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["task_family"] == "qna"
        assert data["response_type"] == "answer_only"
        assert data["audit"]["total_request_time_ms"] is not None
        assert data["audit"]["context_build_time_ms"] is not None

    def test_summary_returns_answer_only(self, client, upload_dxf):
        session_id, _ = upload_dxf
        resp = client.post(
            "/api/v2/prompt",
            json={"session_id": session_id, "prompt": "summarize this drawing"},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["task_family"] == "summary"
        assert data["response_type"] == "answer_only"

    def test_empty_prompt_returns_clarification(self, client, upload_dxf):
        session_id, _ = upload_dxf
        resp = client.post(
            "/api/v2/prompt",
            json={"session_id": session_id, "prompt": ""},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["response_type"] == "needs_clarification"

    def test_gibberish_returns_clarification(self, client, upload_dxf):
        session_id, _ = upload_dxf
        resp = client.post(
            "/api/v2/prompt",
            json={"session_id": session_id, "prompt": "asdfghjkl"},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["response_type"] == "needs_clarification"

    def test_compare_without_revision_asks_for_upload(self, client, upload_dxf):
        session_id, _ = upload_dxf
        resp = client.post(
            "/api/v2/prompt",
            json={"session_id": session_id, "prompt": "compare these drawings"},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["task_family"] == "compare"
        assert data["response_type"] == "needs_clarification"
        assert "upload" in data["message"].lower() or "revision" in data["message"].lower()


class TestV2PromptAudit:
    def test_audit_metadata_present(self, client, upload_dxf):
        session_id, _ = upload_dxf
        resp = client.post(
            "/api/v2/prompt",
            json={"session_id": session_id, "prompt": "delete entity A1"},
        )
        assert resp.status_code == 200
        audit = resp.json()["audit"]
        assert "trace_id" in audit
        assert "timestamp" in audit
        assert audit["router_time_ms"] is not None
        assert audit["total_request_time_ms"] is not None

    def test_edit_plan_has_latency_breakdown(self, client, upload_dxf):
        session_id, _ = upload_dxf
        resp = client.post(
            "/api/v2/prompt",
            json={"session_id": session_id, "prompt": "move entity A1 by 5,5"},
        )
        assert resp.status_code == 200
        audit = resp.json()["audit"]
        assert audit["context_build_time_ms"] is not None
        assert audit["llm_time_ms"] is not None
        assert audit["validation_time_ms"] is not None

    def test_unsupported_has_total_time(self, client, upload_dxf):
        session_id, _ = upload_dxf
        resp = client.post(
            "/api/v2/prompt",
            json={"session_id": session_id, "prompt": "summarize this drawing"},
        )
        audit = resp.json()["audit"]
        assert audit["total_request_time_ms"] is not None
        # Unsupported should be fast (no LLM call)
        assert audit["llm_time_ms"] is None


class TestV2PromptObjectiveWiring:
    """Verify that objective pipeline metadata flows through to API responses."""

    def test_response_has_request_class(self, client, upload_dxf):
        session_id, _ = upload_dxf
        resp = client.post(
            "/api/v2/prompt",
            json={"session_id": session_id, "prompt": "move entity A1 by 10,0"},
        )
        data = resp.json()
        assert data["request_class"] == "modify"

    def test_response_has_objective_tag_when_matched(self, client, upload_dxf):
        session_id, _ = upload_dxf
        resp = client.post(
            "/api/v2/prompt",
            json={"session_id": session_id, "prompt": "how much does this cost"},
        )
        data = resp.json()
        assert data["objective_tag"] == "cost_reduction"

    def test_response_has_document_family(self, client, upload_dxf):
        session_id, _ = upload_dxf
        resp = client.post(
            "/api/v2/prompt",
            json={"session_id": session_id, "prompt": "what is on layer WALLS"},
        )
        data = resp.json()
        # document_family should be present (value depends on test fixture content)
        assert "document_family" in data
        assert data["document_family"] is not None

    def test_response_has_stage_pipeline(self, client, upload_dxf):
        session_id, _ = upload_dxf
        resp = client.post(
            "/api/v2/prompt",
            json={"session_id": session_id, "prompt": "move entity A1 by 10,0"},
        )
        data = resp.json()
        assert data["stage_pipeline"] is not None
        assert "stages" in data["stage_pipeline"]
        assert "output_mode" in data["stage_pipeline"]

    def test_modify_pipeline_has_plan_preview(self, client, upload_dxf):
        session_id, _ = upload_dxf
        resp = client.post(
            "/api/v2/prompt",
            json={"session_id": session_id, "prompt": "delete entity A1"},
        )
        data = resp.json()
        pipeline = data["stage_pipeline"]
        assert "plan" in pipeline["stages"]
        assert "preview" in pipeline["stages"]

    def test_estimate_pipeline_has_analyze(self, client, upload_dxf):
        session_id, _ = upload_dxf
        resp = client.post(
            "/api/v2/prompt",
            json={"session_id": session_id, "prompt": "how many windows are there"},
        )
        data = resp.json()
        pipeline = data["stage_pipeline"]
        assert "analyze" in pipeline["stages"]


class TestV2PromptNoFile:
    def test_no_file_loaded(self, client, auth_user):
        from web.backend.main import session_mgr

        session = session_mgr.create(user_id=auth_user["uid"])
        resp = client.post(
            "/api/v2/prompt",
            json={"session_id": session.session_id, "prompt": "move entity"},
        )
        assert resp.status_code == 400
        assert "No file loaded" in resp.json()["detail"]

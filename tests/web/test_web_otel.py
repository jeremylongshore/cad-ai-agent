"""Tests that OTel spans fire through web backend endpoints."""

from __future__ import annotations

import pytest
from opentelemetry.sdk.trace.export.in_memory_span_exporter import InMemorySpanExporter
from starlette.testclient import TestClient

from cad_dxf_agent.otel import init_otel_testing, reset_otel


@pytest.fixture()
def otel_client(auth_user, sample_dxf_bytes):
    """TestClient with OTel wired to an in-memory exporter."""
    exporter = InMemorySpanExporter()
    init_otel_testing(exporter)

    from web.backend.main import app, get_user

    async def _override():
        return auth_user

    app.dependency_overrides[get_user] = _override
    with TestClient(app, raise_server_exceptions=False) as c:
        yield c, exporter

    app.dependency_overrides.clear()
    reset_otel()
    exporter.shutdown()


@pytest.mark.web
class TestWebOtelSpans:
    def test_upload_plan_produces_pipeline_spans(self, otel_client, sample_dxf_bytes):
        """Upload + plan should produce pipeline spans."""
        client, exporter = otel_client

        # Upload
        resp = client.post(
            "/api/upload",
            files={"file": ("test.dxf", sample_dxf_bytes, "application/octet-stream")},
        )
        assert resp.status_code == 200
        session_id = resp.json()["session_id"]

        # Plan
        resp = client.post(
            "/api/plan",
            json={"session_id": session_id, "prompt": "Move the column east by 2 feet"},
        )
        assert resp.status_code == 200

        spans = exporter.get_finished_spans()
        span_names = {s.name for s in spans}
        assert "cad.load_dxf" in span_names
        assert "cad.build_context" in span_names
        assert "cad.run_planner" in span_names
        assert "cad.validate" in span_names


@pytest.mark.web
class TestWebOtelDisabled:
    def test_endpoints_work_without_otel(self, sample_dxf_bytes, auth_user):
        """Web endpoints must work when OTel is not initialized."""
        reset_otel()

        from web.backend.main import app, get_user

        async def _override():
            return auth_user

        app.dependency_overrides[get_user] = _override
        try:
            with TestClient(app, raise_server_exceptions=False) as c:
                resp = c.get("/api/health")
                assert resp.status_code == 200

                resp = c.post(
                    "/api/upload",
                    files={"file": ("test.dxf", sample_dxf_bytes, "application/octet-stream")},
                )
                assert resp.status_code == 200
        finally:
            app.dependency_overrides.clear()
            reset_otel()

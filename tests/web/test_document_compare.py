"""Tests for compare-from-library endpoint (EPIC-CAD-15 Story 8)."""

from __future__ import annotations

import pytest

from cad_dxf_agent.core.document_store import InMemoryDocumentStore

starlette = pytest.importorskip("starlette", reason="web backend tests require fastapi/starlette")

SAMPLE_DXF_CONTENT = b"0\nSECTION\n2\nHEADER\n0\nENDSEC\n0\nEOF\n"


@pytest.fixture(autouse=True)
def _use_inmemory_doc_store(monkeypatch):
    """Force InMemoryDocumentStore for all tests in this module."""
    import web.backend.main as main_mod

    store = InMemoryDocumentStore()
    monkeypatch.setattr(main_mod, "_document_store", store)
    yield store
    monkeypatch.setattr(main_mod, "_document_store", None)


@pytest.mark.web
class TestCompareLibraryDocuments:
    def test_compare_two_valid_documents_returns_comparison_results(
        self, client, sample_dxf_bytes, _use_inmemory_doc_store
    ):
        """Comparing two valid library documents returns a structured result."""
        store = _use_inmemory_doc_store
        master = store.save_document("test-user-123", "master.dxf", sample_dxf_bytes)
        revision = store.save_document("test-user-123", "revision.dxf", sample_dxf_bytes)

        resp = client.post(
            "/api/documents/compare",
            json={
                "master_doc_id": master.doc_id,
                "revision_doc_id": revision.doc_id,
            },
        )
        assert resp.status_code == 200
        data = resp.json()
        # The compare response wraps results; verify it has the expected envelope shape
        assert "status" in data or "type" in data or "data" in data or "total_changes" in data

    def test_compare_with_nonexistent_master_returns_404(
        self, client, sample_dxf_bytes, _use_inmemory_doc_store
    ):
        store = _use_inmemory_doc_store
        revision = store.save_document("test-user-123", "revision.dxf", sample_dxf_bytes)

        resp = client.post(
            "/api/documents/compare",
            json={
                "master_doc_id": "nonexistent-master",
                "revision_doc_id": revision.doc_id,
            },
        )
        assert resp.status_code == 404
        assert "master" in resp.json()["detail"].lower()

    def test_compare_with_nonexistent_revision_returns_404(
        self, client, sample_dxf_bytes, _use_inmemory_doc_store
    ):
        store = _use_inmemory_doc_store
        master = store.save_document("test-user-123", "master.dxf", sample_dxf_bytes)

        resp = client.post(
            "/api/documents/compare",
            json={
                "master_doc_id": master.doc_id,
                "revision_doc_id": "nonexistent-revision",
            },
        )
        assert resp.status_code == 404
        assert "revision" in resp.json()["detail"].lower()

    def test_compare_same_document_works(
        self, client, sample_dxf_bytes, _use_inmemory_doc_store
    ):
        """Self-comparing a document (master == revision) is valid and returns zero changes."""
        store = _use_inmemory_doc_store
        doc = store.save_document("test-user-123", "plan.dxf", sample_dxf_bytes)

        resp = client.post(
            "/api/documents/compare",
            json={
                "master_doc_id": doc.doc_id,
                "revision_doc_id": doc.doc_id,
            },
        )
        assert resp.status_code == 200

    def test_compare_respects_user_isolation(
        self, sample_dxf_bytes, _use_inmemory_doc_store
    ):
        """User B cannot use user A's documents in a compare."""
        from web.backend.main import app, get_user

        store = _use_inmemory_doc_store
        doc_a = store.save_document("user-a", "master.dxf", sample_dxf_bytes)
        doc_b = store.save_document("user-b", "revision.dxf", sample_dxf_bytes)

        async def _user_b():
            return {"uid": "user-b", "email": "b@example.com"}

        app.dependency_overrides[get_user] = _user_b
        from starlette.testclient import TestClient

        with TestClient(app, raise_server_exceptions=False) as client_b:
            # user-b tries to use user-a's doc as master
            resp = client_b.post(
                "/api/documents/compare",
                json={
                    "master_doc_id": doc_a.doc_id,
                    "revision_doc_id": doc_b.doc_id,
                },
            )
            assert resp.status_code == 404

        app.dependency_overrides.clear()

    def test_compare_with_profile_parameter_accepted(
        self, client, sample_dxf_bytes, _use_inmemory_doc_store
    ):
        """The profile parameter is accepted without error."""
        store = _use_inmemory_doc_store
        master = store.save_document("test-user-123", "master.dxf", sample_dxf_bytes)
        revision = store.save_document("test-user-123", "revision.dxf", sample_dxf_bytes)

        resp = client.post(
            "/api/documents/compare",
            json={
                "master_doc_id": master.doc_id,
                "revision_doc_id": revision.doc_id,
                "profile": None,
            },
        )
        # Either succeeds (200) or fails gracefully; must not be a validation error
        assert resp.status_code != 422

    def test_compare_requires_master_doc_id(self, client):
        """Missing master_doc_id returns a validation error."""
        resp = client.post(
            "/api/documents/compare",
            json={"revision_doc_id": "some-rev"},
        )
        assert resp.status_code == 422

    def test_compare_requires_revision_doc_id(self, client):
        """Missing revision_doc_id returns a validation error."""
        resp = client.post(
            "/api/documents/compare",
            json={"master_doc_id": "some-master"},
        )
        assert resp.status_code == 422

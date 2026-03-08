"""Tests for storage usage endpoint (EPIC-CAD-15 Story 9)."""

from __future__ import annotations

import pytest

from cad_dxf_agent.core.document_store import (
    MAX_DOCUMENTS_PER_USER,
    MAX_FILE_SIZE_BYTES,
    MAX_TOTAL_STORAGE_BYTES,
    InMemoryDocumentStore,
)

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
class TestStorageUsageEndpoint:
    def test_usage_returns_correct_structure(self, client):
        """GET /api/documents/usage returns all required fields."""
        resp = client.get("/api/documents/usage")
        assert resp.status_code == 200
        data = resp.json()
        assert "used_bytes" in data
        assert "max_bytes" in data
        assert "document_count" in data
        assert "max_documents" in data
        assert "max_file_size_bytes" in data
        assert "usage_percent" in data

    def test_usage_reports_zero_with_no_documents(self, client):
        """With no documents, used_bytes and document_count are zero."""
        resp = client.get("/api/documents/usage")
        assert resp.status_code == 200
        data = resp.json()
        assert data["used_bytes"] == 0
        assert data["document_count"] == 0
        assert data["usage_percent"] == 0.0

    def test_usage_reports_correct_constants(self, client):
        """The limits match the constants from document_store."""
        resp = client.get("/api/documents/usage")
        data = resp.json()
        assert data["max_bytes"] == MAX_TOTAL_STORAGE_BYTES
        assert data["max_documents"] == MAX_DOCUMENTS_PER_USER
        assert data["max_file_size_bytes"] == MAX_FILE_SIZE_BYTES

    def test_usage_updates_after_upload(self, client, _use_inmemory_doc_store):
        """used_bytes and document_count increase after uploading a document."""
        resp_before = client.get("/api/documents/usage")
        data_before = resp_before.json()

        client.post(
            "/api/documents",
            files={"file": ("plan.dxf", SAMPLE_DXF_CONTENT, "application/octet-stream")},
        )

        resp_after = client.get("/api/documents/usage")
        data_after = resp_after.json()

        assert data_after["document_count"] == data_before["document_count"] + 1
        assert data_after["used_bytes"] == data_before["used_bytes"] + len(SAMPLE_DXF_CONTENT)

    def test_usage_updates_after_delete(self, client, _use_inmemory_doc_store):
        """used_bytes and document_count decrease after deleting a document."""
        upload_resp = client.post(
            "/api/documents",
            files={"file": ("plan.dxf", SAMPLE_DXF_CONTENT, "application/octet-stream")},
        )
        doc_id = upload_resp.json()["document"]["doc_id"]

        resp_after_upload = client.get("/api/documents/usage")
        count_after_upload = resp_after_upload.json()["document_count"]

        client.delete(f"/api/documents/{doc_id}")

        resp_after_delete = client.get("/api/documents/usage")
        data_after_delete = resp_after_delete.json()

        assert data_after_delete["document_count"] == count_after_upload - 1
        assert data_after_delete["used_bytes"] == 0

    def test_usage_percent_calculation(self, client, _use_inmemory_doc_store):
        """usage_percent is computed as (used_bytes / max_bytes) * 100."""
        upload_resp = client.post(
            "/api/documents",
            files={"file": ("plan.dxf", SAMPLE_DXF_CONTENT, "application/octet-stream")},
        )
        assert upload_resp.status_code == 200

        resp = client.get("/api/documents/usage")
        data = resp.json()

        expected = round(len(SAMPLE_DXF_CONTENT) / MAX_TOTAL_STORAGE_BYTES * 100, 2)
        assert data["usage_percent"] == pytest.approx(expected, abs=0.01)

    def test_upload_at_limit_returns_413_with_usage_data(self, client, _use_inmemory_doc_store):
        """When StorageLimitError is raised, the 413 response includes usage fields."""
        store = _use_inmemory_doc_store
        # Pre-fill to the document count limit
        for i in range(MAX_DOCUMENTS_PER_USER):
            store.save_document("test-user-123", f"doc{i}.dxf", b"x")

        resp = client.post(
            "/api/documents",
            files={"file": ("overflow.dxf", SAMPLE_DXF_CONTENT, "application/octet-stream")},
        )
        assert resp.status_code == 413
        detail = resp.json()["detail"]
        # detail is now a structured dict, not a plain string
        assert isinstance(detail, dict)
        assert "message" in detail
        assert "used_bytes" in detail
        assert "max_bytes" in detail
        assert "document_count" in detail
        assert "max_documents" in detail
        assert "usage_percent" in detail
        assert "limit" in detail["message"].lower()

    def test_upload_at_limit_usage_data_reflects_current_state(
        self, client, _use_inmemory_doc_store
    ):
        """The usage data inside the 413 error matches the actual current usage."""
        store = _use_inmemory_doc_store
        for i in range(MAX_DOCUMENTS_PER_USER):
            store.save_document("test-user-123", f"doc{i}.dxf", b"x")

        resp = client.post(
            "/api/documents",
            files={"file": ("overflow.dxf", SAMPLE_DXF_CONTENT, "application/octet-stream")},
        )
        assert resp.status_code == 413
        detail = resp.json()["detail"]

        # document_count in error should equal MAX_DOCUMENTS_PER_USER
        assert detail["document_count"] == MAX_DOCUMENTS_PER_USER
        # used_bytes should reflect bytes of the pre-filled documents (each b"x" = 1 byte)
        assert detail["used_bytes"] == MAX_DOCUMENTS_PER_USER

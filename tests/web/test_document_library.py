"""Tests for document library API endpoints (EPIC-CAD-15)."""

from __future__ import annotations

from pathlib import Path

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
class TestListDocuments:
    def test_empty_library(self, client):
        resp = client.get("/api/documents")
        assert resp.status_code == 200
        assert resp.json()["documents"] == []

    def test_lists_uploaded_documents(self, client):
        # Upload two documents
        client.post(
            "/api/documents",
            files={"file": ("a.dxf", SAMPLE_DXF_CONTENT, "application/octet-stream")},
        )
        client.post(
            "/api/documents",
            files={"file": ("b.dxf", SAMPLE_DXF_CONTENT, "application/octet-stream")},
        )

        resp = client.get("/api/documents")
        assert resp.status_code == 200
        docs = resp.json()["documents"]
        assert len(docs) == 2
        filenames = {d["filename"] for d in docs}
        assert filenames == {"a.dxf", "b.dxf"}


@pytest.mark.web
class TestUploadDocument:
    def test_upload_success(self, client):
        resp = client.post(
            "/api/documents",
            files={"file": ("floor-plan.dxf", SAMPLE_DXF_CONTENT, "application/octet-stream")},
        )
        assert resp.status_code == 200
        doc = resp.json()["document"]
        assert doc["filename"] == "floor-plan.dxf"
        assert doc["status"] == "active"
        assert doc["file_size_bytes"] == len(SAMPLE_DXF_CONTENT)
        assert doc["user_id"] == "test-user-123"
        assert len(doc["doc_id"]) == 16

    def test_upload_rejects_non_dxf(self, client):
        resp = client.post(
            "/api/documents",
            files={"file": ("image.png", b"fakepng", "image/png")},
        )
        assert resp.status_code == 400
        assert "DXF" in resp.json()["detail"]

    def test_upload_rejects_empty_file(self, client):
        resp = client.post(
            "/api/documents",
            files={"file": ("empty.dxf", b"", "application/octet-stream")},
        )
        assert resp.status_code == 400

    def test_upload_storage_limit(self, client, _use_inmemory_doc_store):
        """Exceeding document count limit returns 413."""
        from cad_dxf_agent.core.document_store import MAX_DOCUMENTS_PER_USER

        store = _use_inmemory_doc_store
        # Pre-fill to limit
        for i in range(MAX_DOCUMENTS_PER_USER):
            store.save_document("test-user-123", f"doc{i}.dxf", b"x")

        resp = client.post(
            "/api/documents",
            files={"file": ("overflow.dxf", SAMPLE_DXF_CONTENT, "application/octet-stream")},
        )
        assert resp.status_code == 413
        assert "limit" in resp.json()["detail"].lower()


@pytest.mark.web
class TestGetDocument:
    def test_get_existing(self, client):
        upload_resp = client.post(
            "/api/documents",
            files={"file": ("test.dxf", SAMPLE_DXF_CONTENT, "application/octet-stream")},
        )
        doc_id = upload_resp.json()["document"]["doc_id"]

        resp = client.get(f"/api/documents/{doc_id}")
        assert resp.status_code == 200
        assert resp.json()["document"]["doc_id"] == doc_id

    def test_get_nonexistent(self, client):
        resp = client.get("/api/documents/nonexistent")
        assert resp.status_code == 404


@pytest.mark.web
class TestDeleteDocument:
    def test_delete_success(self, client):
        upload_resp = client.post(
            "/api/documents",
            files={"file": ("test.dxf", SAMPLE_DXF_CONTENT, "application/octet-stream")},
        )
        doc_id = upload_resp.json()["document"]["doc_id"]

        resp = client.delete(f"/api/documents/{doc_id}")
        assert resp.status_code == 200
        assert resp.json()["status"] == "deleted"

        # No longer in list
        list_resp = client.get("/api/documents")
        assert len(list_resp.json()["documents"]) == 0

    def test_delete_nonexistent(self, client):
        resp = client.delete("/api/documents/nonexistent")
        assert resp.status_code == 404

    def test_delete_idempotent(self, client):
        upload_resp = client.post(
            "/api/documents",
            files={"file": ("test.dxf", SAMPLE_DXF_CONTENT, "application/octet-stream")},
        )
        doc_id = upload_resp.json()["document"]["doc_id"]

        client.delete(f"/api/documents/{doc_id}")
        resp = client.delete(f"/api/documents/{doc_id}")
        assert resp.status_code == 404


@pytest.mark.web
class TestLoadDocument:
    def test_load_creates_session(self, client, sample_dxf_bytes, _use_inmemory_doc_store):
        """Loading a library document creates a working session."""
        store = _use_inmemory_doc_store
        # Upload a real DXF so load_dxf succeeds
        doc = store.save_document("test-user-123", "real.dxf", sample_dxf_bytes)

        resp = client.post(f"/api/documents/{doc.doc_id}/load")
        assert resp.status_code == 200
        data = resp.json()
        assert "session_id" in data
        assert data["document_id"] == doc.doc_id
        assert "file_info" in data

    def test_load_nonexistent_document(self, client):
        resp = client.post("/api/documents/nonexistent/load")
        assert resp.status_code == 404

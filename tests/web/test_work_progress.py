"""Tests for work-progress save/clear endpoints (EPIC-CAD-30)."""

from __future__ import annotations

import pytest

from cad_dxf_agent.core.document_store import InMemoryDocumentStore
from cad_dxf_agent.models.work_progress_schema import WorkProgress

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
class TestSaveProgress:
    def test_save_progress_returns_404_when_no_active_session(
        self, client, _use_inmemory_doc_store
    ):
        """POST save-progress returns 404 when there is no active session for the doc."""
        store = _use_inmemory_doc_store
        doc = store.save_document("test-user-123", "plan.dxf", SAMPLE_DXF_CONTENT)

        resp = client.post(f"/api/documents/{doc.doc_id}/save-progress")
        assert resp.status_code == 404

    def test_save_progress_returns_404_for_unknown_doc(self, client):
        """POST save-progress returns 404 for a non-existent document."""
        resp = client.post("/api/documents/does-not-exist/save-progress")
        assert resp.status_code == 404

    def test_save_progress_returns_200_when_session_exists(
        self, client, sample_dxf_bytes, _use_inmemory_doc_store
    ):
        """POST save-progress succeeds when an active session is bound to the doc."""
        store = _use_inmemory_doc_store
        doc = store.save_document("test-user-123", "plan.dxf", sample_dxf_bytes)

        # Load the document to create an active session
        load_resp = client.post(f"/api/documents/{doc.doc_id}/load")
        assert load_resp.status_code == 200

        resp = client.post(f"/api/documents/{doc.doc_id}/save-progress")
        assert resp.status_code == 200

    def test_save_progress_response_contains_status_saved(
        self, client, sample_dxf_bytes, _use_inmemory_doc_store
    ):
        """save-progress response includes status=saved and the doc_id."""
        store = _use_inmemory_doc_store
        doc = store.save_document("test-user-123", "plan.dxf", sample_dxf_bytes)
        client.post(f"/api/documents/{doc.doc_id}/load")

        resp = client.post(f"/api/documents/{doc.doc_id}/save-progress")
        data = resp.json()
        assert data["status"] == "saved"
        assert data["doc_id"] == doc.doc_id

    def test_save_progress_persists_to_store(
        self, client, sample_dxf_bytes, _use_inmemory_doc_store
    ):
        """After saving progress, the store has a WorkProgress record for the doc."""
        store = _use_inmemory_doc_store
        doc = store.save_document("test-user-123", "plan.dxf", sample_dxf_bytes)
        client.post(f"/api/documents/{doc.doc_id}/load")

        client.post(f"/api/documents/{doc.doc_id}/save-progress")

        progress = store.get_work_progress("test-user-123", doc.doc_id)
        assert progress is not None
        assert isinstance(progress, WorkProgress)
        assert progress.doc_id == doc.doc_id


@pytest.mark.web
class TestClearProgress:
    def test_clear_progress_returns_404_when_no_progress_saved(
        self, client, _use_inmemory_doc_store
    ):
        """DELETE work-progress returns 404 when nothing has been saved yet."""
        store = _use_inmemory_doc_store
        doc = store.save_document("test-user-123", "plan.dxf", SAMPLE_DXF_CONTENT)

        resp = client.delete(f"/api/documents/{doc.doc_id}/work-progress")
        assert resp.status_code == 404

    def test_clear_progress_returns_404_for_unknown_doc(self, client):
        """DELETE work-progress returns 404 for a non-existent document."""
        resp = client.delete("/api/documents/does-not-exist/work-progress")
        assert resp.status_code == 404

    def test_clear_progress_returns_200_after_progress_saved(
        self, client, sample_dxf_bytes, _use_inmemory_doc_store
    ):
        """DELETE work-progress returns 200 when there is progress to clear."""
        store = _use_inmemory_doc_store
        doc = store.save_document("test-user-123", "plan.dxf", sample_dxf_bytes)

        # Create session and save progress
        client.post(f"/api/documents/{doc.doc_id}/load")
        client.post(f"/api/documents/{doc.doc_id}/save-progress")

        resp = client.delete(f"/api/documents/{doc.doc_id}/work-progress")
        assert resp.status_code == 200

    def test_clear_progress_response_contains_status_cleared(
        self, client, sample_dxf_bytes, _use_inmemory_doc_store
    ):
        """Clear response includes status=cleared and the doc_id."""
        store = _use_inmemory_doc_store
        doc = store.save_document("test-user-123", "plan.dxf", sample_dxf_bytes)
        client.post(f"/api/documents/{doc.doc_id}/load")
        client.post(f"/api/documents/{doc.doc_id}/save-progress")

        resp = client.delete(f"/api/documents/{doc.doc_id}/work-progress")
        data = resp.json()
        assert data["status"] == "cleared"
        assert data["doc_id"] == doc.doc_id

    def test_clear_progress_removes_record_from_store(
        self, client, sample_dxf_bytes, _use_inmemory_doc_store
    ):
        """After clearing, the store no longer has a WorkProgress record."""
        store = _use_inmemory_doc_store
        doc = store.save_document("test-user-123", "plan.dxf", sample_dxf_bytes)
        client.post(f"/api/documents/{doc.doc_id}/load")
        client.post(f"/api/documents/{doc.doc_id}/save-progress")

        client.delete(f"/api/documents/{doc.doc_id}/work-progress")

        assert store.get_work_progress("test-user-123", doc.doc_id) is None

    def test_clear_progress_is_not_idempotent(
        self, client, sample_dxf_bytes, _use_inmemory_doc_store
    ):
        """Clearing progress twice returns 404 on the second call."""
        store = _use_inmemory_doc_store
        doc = store.save_document("test-user-123", "plan.dxf", sample_dxf_bytes)
        client.post(f"/api/documents/{doc.doc_id}/load")
        client.post(f"/api/documents/{doc.doc_id}/save-progress")

        client.delete(f"/api/documents/{doc.doc_id}/work-progress")
        resp = client.delete(f"/api/documents/{doc.doc_id}/work-progress")
        assert resp.status_code == 404


@pytest.mark.web
class TestHasWorkProgressInDocumentList:
    def test_document_list_has_work_progress_field(self, client, _use_inmemory_doc_store):
        """Documents returned from GET /api/documents include has_work_progress."""
        store = _use_inmemory_doc_store
        store.save_document("test-user-123", "plan.dxf", SAMPLE_DXF_CONTENT)

        resp = client.get("/api/documents")
        assert resp.status_code == 200
        docs = resp.json()["documents"]
        assert len(docs) == 1
        assert "has_work_progress" in docs[0]

    def test_has_work_progress_false_by_default(self, client, _use_inmemory_doc_store):
        """Freshly uploaded documents have has_work_progress=False."""
        store = _use_inmemory_doc_store
        store.save_document("test-user-123", "plan.dxf", SAMPLE_DXF_CONTENT)

        resp = client.get("/api/documents")
        doc = resp.json()["documents"][0]
        assert doc["has_work_progress"] is False

    def test_has_work_progress_true_after_saving(
        self, client, sample_dxf_bytes, _use_inmemory_doc_store
    ):
        """has_work_progress becomes True after saving progress via the endpoint."""
        store = _use_inmemory_doc_store
        doc = store.save_document("test-user-123", "plan.dxf", sample_dxf_bytes)

        client.post(f"/api/documents/{doc.doc_id}/load")
        client.post(f"/api/documents/{doc.doc_id}/save-progress")

        resp = client.get("/api/documents")
        listed = resp.json()["documents"][0]
        assert listed["has_work_progress"] is True

    def test_has_work_progress_false_after_clearing(
        self, client, sample_dxf_bytes, _use_inmemory_doc_store
    ):
        """has_work_progress returns to False after clearing saved progress."""
        store = _use_inmemory_doc_store
        doc = store.save_document("test-user-123", "plan.dxf", sample_dxf_bytes)

        client.post(f"/api/documents/{doc.doc_id}/load")
        client.post(f"/api/documents/{doc.doc_id}/save-progress")
        client.delete(f"/api/documents/{doc.doc_id}/work-progress")

        resp = client.get("/api/documents")
        listed = resp.json()["documents"][0]
        assert listed["has_work_progress"] is False

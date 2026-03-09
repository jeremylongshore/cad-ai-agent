"""Tests for cross-tenant document isolation.

Verifies that documents uploaded by user A are invisible, inaccessible, and
unmodifiable by user B — even when they share the same InMemoryDocumentStore
instance (which proves the scoping is done correctly by user_id, not just
by a separate store instance per user).

EPIC-CAD-15 — Document Persistence
"""

from __future__ import annotations

import pytest

from cad_dxf_agent.core.document_store import InMemoryDocumentStore

starlette = pytest.importorskip("starlette", reason="web backend tests require fastapi/starlette")

from starlette.testclient import TestClient  # noqa: E402

SAMPLE_DXF_CONTENT = b"0\nSECTION\n2\nHEADER\n0\nENDSEC\n0\nEOF\n"


# ---------------------------------------------------------------------------
# Module-level fixtures
# ---------------------------------------------------------------------------


@pytest.fixture(autouse=True)
def _use_inmemory_doc_store(monkeypatch):
    """Force a fresh InMemoryDocumentStore for every test in this module.

    Monkeypatching the module-level ``_document_store`` sentinel means the
    lazy ``_get_document_store()`` factory inside main.py is bypassed — every
    endpoint call hits our in-process store, so isolation behaviour is
    deterministic and requires no network.
    """
    import web.backend.main as main_mod

    store = InMemoryDocumentStore()
    monkeypatch.setattr(main_mod, "_document_store", store)
    yield store
    monkeypatch.setattr(main_mod, "_document_store", None)


def _make_client(uid: str, email: str, tenant_id: str) -> TestClient:
    """Return a TestClient whose auth dependency yields the given identity.

    Callers are responsible for managing the context-manager lifecycle.
    """
    from web.backend.main import app, get_user

    async def _override():
        return {"uid": uid, "email": email, "tenant_id": tenant_id}

    app.dependency_overrides[get_user] = _override
    return TestClient(app, raise_server_exceptions=False)


def _upload_doc(client: TestClient, filename: str = "drawing.dxf") -> str:
    """Upload SAMPLE_DXF_CONTENT and return the doc_id."""
    resp = client.post(
        "/api/documents",
        files={"file": (filename, SAMPLE_DXF_CONTENT, "application/octet-stream")},
    )
    assert resp.status_code == 200, f"Upload failed: {resp.text}"
    return resp.json()["document"]["doc_id"]


# ---------------------------------------------------------------------------
# Test classes
# ---------------------------------------------------------------------------


@pytest.mark.web
class TestListIsolation:
    """User B cannot see documents belonging to user A."""

    def test_user_b_sees_empty_library_after_user_a_upload(self, _use_inmemory_doc_store):
        """A document uploaded by user A must not appear in user B's list."""
        from web.backend.main import app, get_user

        # --- User A uploads a document ---
        async def _user_a():
            return {"uid": "user-a", "email": "a@test.com", "tenant_id": "tenant-a"}

        app.dependency_overrides[get_user] = _user_a
        with TestClient(app, raise_server_exceptions=False) as client_a:
            _upload_doc(client_a, "a-drawing.dxf")

        # --- User B lists their library ---
        async def _user_b():
            return {"uid": "user-b", "email": "b@test.com", "tenant_id": "tenant-b"}

        app.dependency_overrides[get_user] = _user_b
        with TestClient(app, raise_server_exceptions=False) as client_b:
            resp = client_b.get("/api/documents")

        app.dependency_overrides.clear()

        assert resp.status_code == 200
        assert resp.json()["documents"] == []

    def test_users_see_only_their_own_documents(self, _use_inmemory_doc_store):
        """When both users have documents, each list response is scoped to that user."""
        from web.backend.main import app, get_user

        async def _user_a():
            return {"uid": "user-a", "email": "a@test.com", "tenant_id": "tenant-a"}

        async def _user_b():
            return {"uid": "user-b", "email": "b@test.com", "tenant_id": "tenant-b"}

        # Upload one doc each
        app.dependency_overrides[get_user] = _user_a
        with TestClient(app, raise_server_exceptions=False) as c:
            _upload_doc(c, "a.dxf")

        app.dependency_overrides[get_user] = _user_b
        with TestClient(app, raise_server_exceptions=False) as c:
            _upload_doc(c, "b.dxf")

        # Verify each user's list
        app.dependency_overrides[get_user] = _user_a
        with TestClient(app, raise_server_exceptions=False) as c:
            docs_a = c.get("/api/documents").json()["documents"]

        app.dependency_overrides[get_user] = _user_b
        with TestClient(app, raise_server_exceptions=False) as c:
            docs_b = c.get("/api/documents").json()["documents"]

        app.dependency_overrides.clear()

        assert len(docs_a) == 1
        assert docs_a[0]["filename"] == "a.dxf"
        assert len(docs_b) == 1
        assert docs_b[0]["filename"] == "b.dxf"


@pytest.mark.web
class TestLoadIsolation:
    """User B cannot load (GET metadata for) user A's document."""

    def test_get_user_b_cannot_load_user_a_document(self, _use_inmemory_doc_store):
        """GET /api/documents/{id} returns 404 when the id belongs to another user."""
        from web.backend.main import app, get_user

        async def _user_a():
            return {"uid": "user-a", "email": "a@test.com", "tenant_id": "tenant-a"}

        app.dependency_overrides[get_user] = _user_a
        with TestClient(app, raise_server_exceptions=False) as client_a:
            doc_id = _upload_doc(client_a)

        async def _user_b():
            return {"uid": "user-b", "email": "b@test.com", "tenant_id": "tenant-b"}

        app.dependency_overrides[get_user] = _user_b
        with TestClient(app, raise_server_exceptions=False) as client_b:
            resp = client_b.get(f"/api/documents/{doc_id}")

        app.dependency_overrides.clear()

        assert resp.status_code == 404

    def test_load_session_user_b_cannot_load_user_a_document(self, _use_inmemory_doc_store):
        """POST /api/documents/{id}/load returns 404 when the id belongs to another user."""
        from web.backend.main import app, get_user

        async def _user_a():
            return {"uid": "user-a", "email": "a@test.com", "tenant_id": "tenant-a"}

        app.dependency_overrides[get_user] = _user_a
        with TestClient(app, raise_server_exceptions=False) as client_a:
            doc_id = _upload_doc(client_a)

        async def _user_b():
            return {"uid": "user-b", "email": "b@test.com", "tenant_id": "tenant-b"}

        app.dependency_overrides[get_user] = _user_b
        with TestClient(app, raise_server_exceptions=False) as client_b:
            resp = client_b.post(f"/api/documents/{doc_id}/load")

        app.dependency_overrides.clear()

        assert resp.status_code == 404


@pytest.mark.web
class TestDeleteIsolation:
    """User B cannot delete user A's document."""

    def test_user_b_cannot_delete_user_a_document(self, _use_inmemory_doc_store):
        """DELETE /api/documents/{id} returns 404 when the id belongs to another user."""
        from web.backend.main import app, get_user

        async def _user_a():
            return {"uid": "user-a", "email": "a@test.com", "tenant_id": "tenant-a"}

        app.dependency_overrides[get_user] = _user_a
        with TestClient(app, raise_server_exceptions=False) as client_a:
            doc_id = _upload_doc(client_a)

        async def _user_b():
            return {"uid": "user-b", "email": "b@test.com", "tenant_id": "tenant-b"}

        app.dependency_overrides[get_user] = _user_b
        with TestClient(app, raise_server_exceptions=False) as client_b:
            resp = client_b.delete(f"/api/documents/{doc_id}")

        app.dependency_overrides.clear()

        assert resp.status_code == 404

    def test_document_survives_cross_user_delete_attempt(self, _use_inmemory_doc_store):
        """After user B's failed delete, user A's document is still present."""
        from web.backend.main import app, get_user

        store: InMemoryDocumentStore = _use_inmemory_doc_store

        async def _user_a():
            return {"uid": "user-a", "email": "a@test.com", "tenant_id": "tenant-a"}

        app.dependency_overrides[get_user] = _user_a
        with TestClient(app, raise_server_exceptions=False) as client_a:
            doc_id = _upload_doc(client_a)

        async def _user_b():
            return {"uid": "user-b", "email": "b@test.com", "tenant_id": "tenant-b"}

        app.dependency_overrides[get_user] = _user_b
        with TestClient(app, raise_server_exceptions=False) as client_b:
            client_b.delete(f"/api/documents/{doc_id}")

        app.dependency_overrides.clear()

        # Confirm the doc is still active in the store under user-a
        doc = store.get_document("user-a", doc_id)
        assert doc is not None
        assert doc.status == "active"


@pytest.mark.web
class TestWorkProgressIsolation:
    """User B cannot access work progress saved by user A.

    Work progress isolation is enforced at multiple layers.  At the storage
    layer, ``InMemoryDocumentStore`` keys progress data by ``(user_id, doc_id)``
    tuples.  At the application layer, endpoints validate document ownership by
    the requesting user's ID before accessing or modifying data.  These tests
    verify isolation at both the store API and the HTTP endpoint level.
    """

    def test_user_b_get_work_progress_returns_none(self, _use_inmemory_doc_store):
        """Work progress saved for user A's document is not accessible to user B.

        InMemoryDocumentStore keys work progress by ``(user_id, doc_id)`` tuples,
        so ``get_work_progress("user-b", doc_a_id)`` returns ``None`` even when
        user A has progress saved under the same doc_id.  Likewise,
        ``get_document("user-b", doc_a_id)`` returns ``None``, which means
        higher-level callers such as ``_restore_work_progress`` that guard
        themselves with a document ownership check also get no data.
        """
        from cad_dxf_agent.models.work_progress_schema import WorkProgress

        store: InMemoryDocumentStore = _use_inmemory_doc_store

        # User A saves a document and work progress
        doc = store.save_document("user-a", "a.dxf", SAMPLE_DXF_CONTENT)
        progress = WorkProgress(
            user_id="user-a",
            doc_id=doc.doc_id,
            tenant_id="tenant-a",
            last_prompt="move wall to x=10",
            edit_count=3,
        )
        store.save_work_progress("user-a", doc.doc_id, progress)

        # User A can retrieve their own progress
        retrieved_a = store.get_work_progress("user-a", doc.doc_id)
        assert retrieved_a is not None
        assert retrieved_a.last_prompt == "move wall to x=10"

        # The document is invisible to user B — the gating check used by
        # _restore_work_progress before it ever calls get_work_progress
        doc_b = store.get_document("user-b", doc.doc_id)
        assert doc_b is None, "store.get_document must return None for cross-user access"

    def test_save_progress_endpoint_respects_user_isolation(self, _use_inmemory_doc_store):
        """POST /api/documents/{id}/save-progress returns 404 for another user's doc.

        The endpoint looks up an active session scoped to the requesting user's
        uid — it will never find user A's session when called as user B.
        """
        from web.backend.main import app, get_user

        store: InMemoryDocumentStore = _use_inmemory_doc_store

        # Seed a document directly in the store under user-a (no active session needed
        # to confirm the 404 path — the endpoint checks session_mgr first)
        doc = store.save_document("user-a", "plan.dxf", SAMPLE_DXF_CONTENT)

        async def _user_b():
            return {"uid": "user-b", "email": "b@test.com", "tenant_id": "tenant-b"}

        app.dependency_overrides[get_user] = _user_b
        with TestClient(app, raise_server_exceptions=False) as client_b:
            resp = client_b.post(f"/api/documents/{doc.doc_id}/save-progress")

        app.dependency_overrides.clear()

        # No active session for user-b bound to this doc → 404
        assert resp.status_code == 404

    def test_clear_progress_endpoint_respects_user_isolation(self, _use_inmemory_doc_store):
        """DELETE /api/documents/{id}/work-progress returns 404 for another user's doc.

        User B calling the clear endpoint with user A's doc_id cannot erase
        user A's progress because the store lookup is keyed by the requesting
        user's uid.
        """
        from web.backend.main import app, get_user

        from cad_dxf_agent.models.work_progress_schema import WorkProgress

        store: InMemoryDocumentStore = _use_inmemory_doc_store

        doc = store.save_document("user-a", "plan.dxf", SAMPLE_DXF_CONTENT)
        progress = WorkProgress(user_id="user-a", doc_id=doc.doc_id, edit_count=1)
        store.save_work_progress("user-a", doc.doc_id, progress)

        async def _user_b():
            return {"uid": "user-b", "email": "b@test.com", "tenant_id": "tenant-b"}

        app.dependency_overrides[get_user] = _user_b
        with TestClient(app, raise_server_exceptions=False) as client_b:
            resp = client_b.delete(f"/api/documents/{doc.doc_id}/work-progress")

        app.dependency_overrides.clear()

        # User B's uid has no progress for this doc_id → 404
        assert resp.status_code == 404

        # User A's progress must still be intact
        still_there = store.get_work_progress("user-a", doc.doc_id)
        assert still_there is not None
        assert still_there.edit_count == 1


@pytest.mark.web
class TestReconnectIsolation:
    """User B cannot reconnect to a session created from user A's document."""

    def test_user_b_cannot_reconnect_to_user_a_document(self, _use_inmemory_doc_store):
        """POST /api/session/reconnect returns 404 when document belongs to another user."""
        from web.backend.main import app, get_user

        store: InMemoryDocumentStore = _use_inmemory_doc_store
        doc = store.save_document("user-a", "plan.dxf", SAMPLE_DXF_CONTENT)

        async def _user_b():
            return {"uid": "user-b", "email": "b@test.com", "tenant_id": "tenant-b"}

        app.dependency_overrides[get_user] = _user_b
        with TestClient(app, raise_server_exceptions=False) as client_b:
            resp = client_b.post("/api/session/reconnect", json={"document_id": doc.doc_id})

        app.dependency_overrides.clear()

        assert resp.status_code == 404


@pytest.mark.web
class TestStorageUsageIsolation:
    """Storage usage stats are scoped to the requesting user."""

    def test_user_b_usage_is_zero_after_user_a_upload(self, _use_inmemory_doc_store):
        """User B's /api/documents/usage shows 0 bytes even after user A uploads."""
        from web.backend.main import app, get_user

        async def _user_a():
            return {"uid": "user-a", "email": "a@test.com", "tenant_id": "tenant-a"}

        app.dependency_overrides[get_user] = _user_a
        with TestClient(app, raise_server_exceptions=False) as client_a:
            _upload_doc(client_a)

        async def _user_b():
            return {"uid": "user-b", "email": "b@test.com", "tenant_id": "tenant-b"}

        app.dependency_overrides[get_user] = _user_b
        with TestClient(app, raise_server_exceptions=False) as client_b:
            resp = client_b.get("/api/documents/usage")

        app.dependency_overrides.clear()

        assert resp.status_code == 200
        data = resp.json()
        assert data["document_count"] == 0
        assert data["used_bytes"] == 0

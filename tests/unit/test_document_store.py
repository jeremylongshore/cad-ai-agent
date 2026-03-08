"""Tests for document_store — InMemoryDocumentStore."""

from __future__ import annotations

import threading

import pytest

from cad_dxf_agent.core.document_store import (
    MAX_DOCUMENTS_PER_USER,
    MAX_FILE_SIZE_BYTES,
    MAX_TOTAL_STORAGE_BYTES,
    InMemoryDocumentStore,
    StorageLimitError,
)


@pytest.fixture
def store() -> InMemoryDocumentStore:
    return InMemoryDocumentStore()


SAMPLE_DXF = b"0\nSECTION\n2\nHEADER\n0\nENDSEC\n0\nEOF\n"


class TestInMemoryDocumentStore:
    def test_save_and_get(self, store: InMemoryDocumentStore):
        """Save a document and retrieve it by ID."""
        doc = store.save_document("u1", "floor.dxf", SAMPLE_DXF)
        assert doc.user_id == "u1"
        assert doc.filename == "floor.dxf"
        assert doc.file_size_bytes == len(SAMPLE_DXF)
        assert doc.status == "active"

        retrieved = store.get_document("u1", doc.doc_id)
        assert retrieved is not None
        assert retrieved.doc_id == doc.doc_id

    def test_get_nonexistent(self, store: InMemoryDocumentStore):
        """Getting a nonexistent document returns None."""
        assert store.get_document("u1", "nope") is None

    def test_get_wrong_user(self, store: InMemoryDocumentStore):
        """Documents are user-scoped — wrong user gets None."""
        doc = store.save_document("u1", "a.dxf", SAMPLE_DXF)
        assert store.get_document("u2", doc.doc_id) is None

    def test_list_documents(self, store: InMemoryDocumentStore):
        """List returns all active documents for a user."""
        store.save_document("u1", "a.dxf", SAMPLE_DXF)
        store.save_document("u1", "b.dxf", SAMPLE_DXF)
        store.save_document("u2", "c.dxf", SAMPLE_DXF)

        u1_docs = store.list_documents("u1")
        assert len(u1_docs) == 2
        assert {d.filename for d in u1_docs} == {"a.dxf", "b.dxf"}

        u2_docs = store.list_documents("u2")
        assert len(u2_docs) == 1

    def test_list_empty_user(self, store: InMemoryDocumentStore):
        """Listing for a user with no documents returns empty list."""
        assert store.list_documents("nobody") == []

    def test_delete_document(self, store: InMemoryDocumentStore):
        """Delete soft-deletes — document no longer appears in list or get."""
        doc = store.save_document("u1", "a.dxf", SAMPLE_DXF)
        assert store.delete_document("u1", doc.doc_id) is True
        assert store.get_document("u1", doc.doc_id) is None
        assert store.list_documents("u1") == []

    def test_delete_nonexistent(self, store: InMemoryDocumentStore):
        """Deleting a nonexistent document returns False."""
        assert store.delete_document("u1", "nope") is False

    def test_delete_idempotent(self, store: InMemoryDocumentStore):
        """Deleting an already-deleted document returns False."""
        doc = store.save_document("u1", "a.dxf", SAMPLE_DXF)
        assert store.delete_document("u1", doc.doc_id) is True
        assert store.delete_document("u1", doc.doc_id) is False

    def test_get_file_data(self, store: InMemoryDocumentStore):
        """Retrieve raw file bytes for a stored document."""
        doc = store.save_document("u1", "a.dxf", SAMPLE_DXF)
        data = store.get_file_data("u1", doc.doc_id)
        assert data == SAMPLE_DXF

    def test_get_file_data_deleted(self, store: InMemoryDocumentStore):
        """Cannot retrieve file data for deleted documents."""
        doc = store.save_document("u1", "a.dxf", SAMPLE_DXF)
        store.delete_document("u1", doc.doc_id)
        assert store.get_file_data("u1", doc.doc_id) is None

    def test_get_file_data_nonexistent(self, store: InMemoryDocumentStore):
        """File data for nonexistent doc returns None."""
        assert store.get_file_data("u1", "nope") is None

    def test_save_with_metadata(self, store: InMemoryDocumentStore):
        """Custom metadata is preserved."""
        doc = store.save_document(
            "u1", "a.dxf", SAMPLE_DXF, metadata={"layers": 5, "entity_count": 200}
        )
        assert doc.metadata == {"layers": 5, "entity_count": 200}

    def test_document_count_limit(self, store: InMemoryDocumentStore):
        """Cannot exceed MAX_DOCUMENTS_PER_USER."""
        for i in range(MAX_DOCUMENTS_PER_USER):
            store.save_document("u1", f"doc{i}.dxf", b"x")

        with pytest.raises(StorageLimitError, match="Document limit"):
            store.save_document("u1", "one-too-many.dxf", b"x")

    def test_file_size_limit(self, store: InMemoryDocumentStore):
        """Cannot upload a file exceeding MAX_FILE_SIZE_BYTES."""
        big_data = b"x" * (MAX_FILE_SIZE_BYTES + 1)
        with pytest.raises(StorageLimitError, match="maximum size"):
            store.save_document("u1", "huge.dxf", big_data)

    def test_total_storage_limit(self, store: InMemoryDocumentStore):
        """Cannot exceed total per-user storage quota."""
        chunk_size = MAX_TOTAL_STORAGE_BYTES // 4
        for i in range(4):
            store.save_document("u1", f"big{i}.dxf", b"x" * chunk_size)

        with pytest.raises(StorageLimitError, match="Storage quota"):
            store.save_document("u1", "overflow.dxf", b"x" * chunk_size)

    def test_limits_per_user_isolation(self, store: InMemoryDocumentStore):
        """Storage limits are per-user — u2 is unaffected by u1's usage."""
        for i in range(MAX_DOCUMENTS_PER_USER):
            store.save_document("u1", f"doc{i}.dxf", b"x")

        # u2 can still upload
        doc = store.save_document("u2", "fresh.dxf", SAMPLE_DXF)
        assert doc.status == "active"

    def test_deleted_docs_dont_count_against_limit(self, store: InMemoryDocumentStore):
        """Deleted documents free up slots for new uploads."""
        docs = []
        for i in range(MAX_DOCUMENTS_PER_USER):
            docs.append(store.save_document("u1", f"doc{i}.dxf", b"x"))

        # At limit
        with pytest.raises(StorageLimitError):
            store.save_document("u1", "blocked.dxf", b"x")

        # Delete one
        store.delete_document("u1", docs[0].doc_id)

        # Now we can upload
        new_doc = store.save_document("u1", "freed.dxf", b"x")
        assert new_doc.status == "active"

    def test_thread_safety(self, store: InMemoryDocumentStore):
        """Concurrent saves don't corrupt state."""
        errors = []

        def save_batch(user_id: str, start: int):
            try:
                for i in range(10):
                    store.save_document(user_id, f"doc{start + i}.dxf", b"data")
            except Exception as e:
                errors.append(e)

        threads = [
            threading.Thread(target=save_batch, args=("u1", i * 10))
            for i in range(3)
        ]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        assert not errors
        docs = store.list_documents("u1")
        assert len(docs) == 30

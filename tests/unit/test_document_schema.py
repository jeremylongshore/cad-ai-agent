"""Tests for document_schema — UserDocument model."""

from __future__ import annotations

from cad_dxf_agent.models.document_schema import UserDocument


class TestUserDocument:
    def test_creation_with_defaults(self):
        """Newly created document has auto-generated doc_id, timestamps, and sane defaults."""
        doc = UserDocument(user_id="u1", filename="floor-plan.dxf")
        assert doc.user_id == "u1"
        assert doc.filename == "floor-plan.dxf"
        assert len(doc.doc_id) == 16
        assert doc.status == "active"
        assert doc.file_size_bytes == 0
        assert doc.gcs_path == ""
        assert doc.metadata == {}
        assert doc.upload_time  # non-empty ISO string
        assert doc.last_accessed

    def test_unique_doc_ids(self):
        """Each document gets a unique ID."""
        docs = [UserDocument(user_id="u1", filename="a.dxf") for _ in range(10)]
        ids = {d.doc_id for d in docs}
        assert len(ids) == 10

    def test_touch_updates_last_accessed(self):
        """touch() bumps last_accessed to current time."""
        doc = UserDocument(
            user_id="u1",
            filename="a.dxf",
            last_accessed="2020-01-01T00:00:00+00:00",
        )
        old = doc.last_accessed
        doc.touch()
        assert doc.last_accessed != old
        assert doc.last_accessed > old

    def test_json_roundtrip(self):
        """Model serializes and deserializes cleanly."""
        doc = UserDocument(
            user_id="u1",
            filename="test.dxf",
            file_size_bytes=12345,
            gcs_path="gs://bucket/path",
            metadata={"layers": 5},
        )
        json_str = doc.model_dump_json()
        restored = UserDocument.model_validate_json(json_str)
        assert restored.user_id == doc.user_id
        assert restored.doc_id == doc.doc_id
        assert restored.filename == doc.filename
        assert restored.file_size_bytes == 12345
        assert restored.gcs_path == "gs://bucket/path"
        assert restored.metadata == {"layers": 5}

    def test_status_values(self):
        """Status accepts 'active' and 'deleted' only."""
        doc_active = UserDocument(user_id="u1", filename="a.dxf", status="active")
        assert doc_active.status == "active"

        doc_deleted = UserDocument(user_id="u1", filename="a.dxf", status="deleted")
        assert doc_deleted.status == "deleted"

    def test_explicit_doc_id(self):
        """Can provide explicit doc_id."""
        doc = UserDocument(user_id="u1", filename="a.dxf", doc_id="custom123")
        assert doc.doc_id == "custom123"

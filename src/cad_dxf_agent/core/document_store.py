"""Document store — ABC + InMemory + GCS implementations for persistent user documents.

Documents are permanently stored per-user, independent of ephemeral sessions.
InMemoryDocumentStore is for testing. GCSDocumentStore is for production.
"""

from __future__ import annotations

import abc
import logging
from threading import Lock
from typing import Any

from cad_dxf_agent.models.document_schema import UserDocument

logger = logging.getLogger(__name__)

# Storage limits
MAX_DOCUMENTS_PER_USER = 50
MAX_FILE_SIZE_BYTES = 25 * 1024 * 1024  # 25 MB
MAX_TOTAL_STORAGE_BYTES = 100 * 1024 * 1024  # 100 MB per user


class StorageLimitError(Exception):
    """Raised when a storage limit is exceeded."""


class DocumentStore(abc.ABC):
    """Abstract document store for permanent user documents.

    Implementations must be thread-safe for concurrent access.
    """

    @abc.abstractmethod
    def save_document(
        self,
        user_id: str,
        filename: str,
        data: bytes,
        metadata: dict[str, Any] | None = None,
    ) -> UserDocument:
        """Upload and persist a document. Returns the created UserDocument."""

    @abc.abstractmethod
    def get_document(self, user_id: str, doc_id: str) -> UserDocument | None:
        """Get document metadata by ID, or None if not found."""

    @abc.abstractmethod
    def list_documents(self, user_id: str) -> list[UserDocument]:
        """List all active documents for a user."""

    @abc.abstractmethod
    def delete_document(self, user_id: str, doc_id: str) -> bool:
        """Soft-delete a document. Returns True if found and deleted."""

    @abc.abstractmethod
    def get_file_data(self, user_id: str, doc_id: str) -> bytes | None:
        """Retrieve the raw file bytes for a document."""

    def touch_document(self, user_id: str, doc_id: str) -> bool:
        """Update last_accessed timestamp. Returns True if document exists."""
        return False  # Default no-op; subclasses override for persistence

    def _check_limits(
        self,
        user_id: str,
        file_size: int,
        existing_docs: list[UserDocument],
    ) -> None:
        """Validate storage limits before upload. Raises StorageLimitError."""
        if file_size > MAX_FILE_SIZE_BYTES:
            raise StorageLimitError(
                f"File exceeds maximum size of {MAX_FILE_SIZE_BYTES // (1024 * 1024)} MB"
            )

        active_docs = [d for d in existing_docs if d.status == "active"]
        if len(active_docs) >= MAX_DOCUMENTS_PER_USER:
            raise StorageLimitError(f"Document limit reached ({MAX_DOCUMENTS_PER_USER} documents)")

        total_storage = sum(d.file_size_bytes for d in active_docs)
        if total_storage + file_size > MAX_TOTAL_STORAGE_BYTES:
            raise StorageLimitError(
                f"Storage quota exceeded ({MAX_TOTAL_STORAGE_BYTES // (1024 * 1024)} MB limit)"
            )


# ---------------------------------------------------------------------------
# InMemoryDocumentStore (testing)
# ---------------------------------------------------------------------------


class InMemoryDocumentStore(DocumentStore):
    """In-memory document store for testing.

    Stores file data and metadata in dicts. Not durable.
    """

    def __init__(self) -> None:
        self._documents: dict[str, dict[str, UserDocument]] = {}  # user_id -> {doc_id -> doc}
        self._file_data: dict[str, bytes] = {}  # doc_id -> bytes
        self._lock = Lock()

    def save_document(
        self,
        user_id: str,
        filename: str,
        data: bytes,
        metadata: dict[str, Any] | None = None,
    ) -> UserDocument:
        with self._lock:
            existing = list((self._documents.get(user_id) or {}).values())
            self._check_limits(user_id, len(data), existing)

            doc = UserDocument(
                user_id=user_id,
                filename=filename,
                file_size_bytes=len(data),
                metadata=metadata or {},
            )

            if user_id not in self._documents:
                self._documents[user_id] = {}
            self._documents[user_id][doc.doc_id] = doc
            self._file_data[doc.doc_id] = data

        logger.info("Stored document %s (%s) for user %s", doc.doc_id, filename, user_id)
        return doc

    def get_document(self, user_id: str, doc_id: str) -> UserDocument | None:
        with self._lock:
            user_docs = self._documents.get(user_id, {})
            doc = user_docs.get(doc_id)
        if doc and doc.status == "active":
            return doc
        return None

    def list_documents(self, user_id: str) -> list[UserDocument]:
        with self._lock:
            user_docs = self._documents.get(user_id, {})
            return [d for d in user_docs.values() if d.status == "active"]

    def delete_document(self, user_id: str, doc_id: str) -> bool:
        with self._lock:
            user_docs = self._documents.get(user_id, {})
            doc = user_docs.get(doc_id)
            if doc and doc.status == "active":
                doc.status = "deleted"
                return True
        return False

    def touch_document(self, user_id: str, doc_id: str) -> bool:
        with self._lock:
            user_docs = self._documents.get(user_id, {})
            doc = user_docs.get(doc_id)
            if doc and doc.status == "active":
                doc.touch()
                return True
        return False

    def get_file_data(self, user_id: str, doc_id: str) -> bytes | None:
        doc = self.get_document(user_id, doc_id)
        if doc is None:
            return None
        with self._lock:
            return self._file_data.get(doc_id)


# ---------------------------------------------------------------------------
# GCSDocumentStore (production)
# ---------------------------------------------------------------------------


class GCSDocumentStore(DocumentStore):
    """GCS-backed document store for production.

    Layout:
        gs://{bucket}/{prefix}{user_id}/{doc_id}/original.dxf
        gs://{bucket}/{prefix}{user_id}/{doc_id}/metadata.json
    """

    def __init__(
        self,
        bucket_name: str = "cad-dxf-agent-documents",
        prefix: str = "documents/",
    ):
        self._bucket_name = bucket_name
        self._prefix = prefix
        self._client = None

    def _get_client(self):
        if self._client is None:
            from google.cloud import storage  # type: ignore[attr-defined]

            self._client = storage.Client()
        return self._client

    def _bucket(self):
        return self._get_client().bucket(self._bucket_name)

    def _doc_prefix(self, user_id: str, doc_id: str) -> str:
        return f"{self._prefix}{user_id}/{doc_id}/"

    def save_document(
        self,
        user_id: str,
        filename: str,
        data: bytes,
        metadata: dict[str, Any] | None = None,
    ) -> UserDocument:
        existing = self.list_documents(user_id)
        self._check_limits(user_id, len(data), existing)

        doc = UserDocument(
            user_id=user_id,
            filename=filename,
            file_size_bytes=len(data),
            metadata=metadata or {},
        )
        prefix = self._doc_prefix(user_id, doc.doc_id)
        doc.gcs_path = f"gs://{self._bucket_name}/{prefix}original.dxf"

        try:
            bucket = self._bucket()

            # Upload file
            file_blob = bucket.blob(f"{self._doc_prefix(user_id, doc.doc_id)}original.dxf")
            file_blob.upload_from_string(data, content_type="application/octet-stream")

            # Upload metadata
            meta_blob = bucket.blob(f"{self._doc_prefix(user_id, doc.doc_id)}metadata.json")
            meta_blob.upload_from_string(
                doc.model_dump_json(),
                content_type="application/json",
            )

            logger.info("Stored document %s (%s) to GCS for user %s", doc.doc_id, filename, user_id)
        except Exception as exc:
            logger.exception("Failed to upload document to GCS: %s", exc)
            raise

        return doc

    def get_document(self, user_id: str, doc_id: str) -> UserDocument | None:
        try:
            meta_blob = self._bucket().blob(f"{self._doc_prefix(user_id, doc_id)}metadata.json")
            if not meta_blob.exists():
                return None
            doc = UserDocument.model_validate_json(meta_blob.download_as_text())
            if doc.status != "active":
                return None
            return doc
        except Exception as exc:
            logger.warning("Failed to fetch document %s from GCS: %s", doc_id, exc)
            return None

    def list_documents(self, user_id: str) -> list[UserDocument]:
        results = []
        try:
            blobs = self._bucket().list_blobs(prefix=f"{self._prefix}{user_id}/")
            for blob in blobs:
                if not blob.name.endswith("metadata.json"):
                    continue
                try:
                    doc = UserDocument.model_validate_json(blob.download_as_text())
                    if doc.status == "active":
                        results.append(doc)
                except Exception as exc:
                    logger.debug("Skipping malformed doc blob %s: %s", blob.name, exc)
        except Exception as exc:
            logger.exception("Failed to list documents from GCS: %s", exc)
        return results

    def delete_document(self, user_id: str, doc_id: str) -> bool:
        doc = self.get_document(user_id, doc_id)
        if doc is None:
            return False

        doc.status = "deleted"
        try:
            meta_blob = self._bucket().blob(f"{self._doc_prefix(user_id, doc_id)}metadata.json")
            meta_blob.upload_from_string(
                doc.model_dump_json(),
                content_type="application/json",
            )
            return True
        except Exception as exc:
            logger.exception("Failed to delete document %s from GCS: %s", doc_id, exc)
            return False

    def touch_document(self, user_id: str, doc_id: str) -> bool:
        doc = self.get_document(user_id, doc_id)
        if doc is None:
            return False
        doc.touch()
        try:
            meta_blob = self._bucket().blob(f"{self._doc_prefix(user_id, doc_id)}metadata.json")
            meta_blob.upload_from_string(
                doc.model_dump_json(),
                content_type="application/json",
            )
            return True
        except Exception as exc:
            logger.warning("Failed to touch document %s in GCS: %s", doc_id, exc)
            return False

    def get_file_data(self, user_id: str, doc_id: str) -> bytes | None:
        doc = self.get_document(user_id, doc_id)
        if doc is None:
            return None
        try:
            file_blob = self._bucket().blob(f"{self._doc_prefix(user_id, doc_id)}original.dxf")
            if not file_blob.exists():
                return None
            return bytes(file_blob.download_as_bytes())
        except Exception as exc:
            logger.warning("Failed to download document %s from GCS: %s", doc_id, exc)
            return None

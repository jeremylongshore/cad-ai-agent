"""Session store abstraction — ABC + InMemory + GCS implementations.

Provides durable session metadata storage behind a clean interface.
InMemorySessionStore is the default (test-compatible, current behavior).
GCSSessionStore persists metadata to Google Cloud Storage for production durability.
"""

from __future__ import annotations

import abc
import dataclasses
import json
import logging
import shutil
import time
import uuid
from dataclasses import asdict, dataclass, field
from pathlib import Path
from threading import Lock
from typing import Any

logger = logging.getLogger(__name__)

SESSION_TTL_SECONDS = 2 * 60 * 60  # 2 hours
DEFAULT_SESSION_DIR = Path("/tmp/cad-sessions")  # noqa: S108


# ---------------------------------------------------------------------------
# Session metadata model (serializable)
# ---------------------------------------------------------------------------


@dataclass
class SessionMetadata:
    """Durable session metadata — serializable to/from JSON.

    Separates serializable metadata from runtime objects (context, changeset, etc.)
    that live only in-memory during an active session.
    """

    session_id: str
    user_id: str
    created_at: float
    state: str = "active"  # active | expired | completed
    file_info: dict = field(default_factory=dict)
    conversation_history: list[dict] = field(default_factory=list)
    audit_events: list = field(default_factory=list)
    # Paths stored as strings for serialization
    original_path: str = ""
    working_path: str = ""
    edited_path: str = ""
    original_render: str = ""
    edited_render: str = ""
    diff_render: str = ""
    diff_overlay_path: str = ""
    diff_overlay_render: str = ""
    revision_path: str = ""
    bundle_dir: str = ""

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> SessionMetadata:
        known = {f.name for f in dataclasses.fields(cls)}
        filtered = {k: v for k, v in data.items() if k in known}
        return cls(**filtered)

    @property
    def is_expired(self) -> bool:
        return (
            self.state == "expired"
            or time.time() - self.created_at > SESSION_TTL_SECONDS
        )


# ---------------------------------------------------------------------------
# ABC
# ---------------------------------------------------------------------------


class SessionStore(abc.ABC):
    """Abstract session metadata store.

    Implementations must be thread-safe for concurrent access.
    File blobs (DXF, renders) remain on the local filesystem — the store
    handles only metadata persistence.
    """

    @abc.abstractmethod
    def create(self, user_id: str) -> SessionMetadata:
        """Create a new session. Returns metadata with session_id assigned."""

    @abc.abstractmethod
    def get(self, session_id: str) -> SessionMetadata | None:
        """Get session metadata by ID, or None if not found/expired."""

    @abc.abstractmethod
    def save(self, metadata: SessionMetadata) -> None:
        """Persist updated session metadata."""

    @abc.abstractmethod
    def delete(self, session_id: str) -> None:
        """Delete a session and its associated files."""

    @abc.abstractmethod
    def cleanup_expired(self) -> int:
        """Remove all expired sessions. Returns count removed."""

    @abc.abstractmethod
    def list_sessions(self, user_id: str | None = None) -> list[SessionMetadata]:
        """List active sessions, optionally filtered by user_id."""


# ---------------------------------------------------------------------------
# InMemorySessionStore (default, backward-compatible)
# ---------------------------------------------------------------------------


class InMemorySessionStore(SessionStore):
    """In-memory session store with local temp directory backing.

    Drop-in replacement for the original SessionManager behavior.
    Sessions are lost on process restart.
    """

    def __init__(self, session_dir: Path | None = None):
        self._sessions: dict[str, SessionMetadata] = {}
        self._lock = Lock()
        self._session_dir = session_dir or DEFAULT_SESSION_DIR
        self._session_dir.mkdir(parents=True, exist_ok=True)

    @property
    def session_dir(self) -> Path:
        return self._session_dir

    def create(self, user_id: str) -> SessionMetadata:
        session_id = uuid.uuid4().hex[:16]
        session_dir = self._session_dir / session_id
        session_dir.mkdir(parents=True, exist_ok=True)

        metadata = SessionMetadata(
            session_id=session_id,
            user_id=user_id,
            created_at=time.time(),
            original_path=str(session_dir / "original.dxf"),
        )

        with self._lock:
            self._sessions[session_id] = metadata

        logger.info("Created session %s for user %s", session_id, user_id)
        return metadata

    def get(self, session_id: str) -> SessionMetadata | None:
        with self._lock:
            metadata = self._sessions.get(session_id)

        if metadata is None:
            return None

        if metadata.is_expired:
            self.delete(session_id)
            return None

        return metadata

    def save(self, metadata: SessionMetadata) -> None:
        with self._lock:
            self._sessions[metadata.session_id] = metadata

    def delete(self, session_id: str) -> None:
        with self._lock:
            self._sessions.pop(session_id, None)

        session_dir = self._session_dir / session_id
        if session_dir.exists():
            shutil.rmtree(session_dir, ignore_errors=True)
        logger.info("Deleted session %s", session_id)

    def cleanup_expired(self) -> int:
        now = time.time()
        expired = []

        with self._lock:
            for sid, meta in self._sessions.items():
                if now - meta.created_at > SESSION_TTL_SECONDS:
                    expired.append(sid)

        for sid in expired:
            self.delete(sid)

        if expired:
            logger.info("Cleaned up %d expired sessions", len(expired))
        return len(expired)

    def list_sessions(self, user_id: str | None = None) -> list[SessionMetadata]:
        with self._lock:
            sessions = list(self._sessions.values())

        now = time.time()
        active = [s for s in sessions if now - s.created_at <= SESSION_TTL_SECONDS]

        if user_id is not None:
            active = [s for s in active if s.user_id == user_id]

        return active


# ---------------------------------------------------------------------------
# GCSSessionStore (production, durable)
# ---------------------------------------------------------------------------


class GCSSessionStore(SessionStore):
    """GCS-backed session store for production durability.

    Metadata is stored as JSON blobs in a GCS bucket.
    File blobs (DXF, renders) remain on local filesystem — only metadata
    is persisted to GCS for cross-instance access and restart survival.

    Requires: google-cloud-storage package.
    Bucket must exist and be accessible via application default credentials.
    """

    def __init__(
        self,
        bucket_name: str = "cad-dxf-sessions",
        prefix: str = "sessions/",
        session_dir: Path | None = None,
    ):
        self._bucket_name = bucket_name
        self._prefix = prefix
        self._session_dir = session_dir or DEFAULT_SESSION_DIR
        self._session_dir.mkdir(parents=True, exist_ok=True)
        self._client = None  # Lazy init

    @property
    def session_dir(self) -> Path:
        return self._session_dir

    def _get_client(self):
        """Lazy-initialize GCS client."""
        if self._client is None:
            from google.cloud import storage

            self._client = storage.Client()
        return self._client

    def _bucket(self):
        return self._get_client().bucket(self._bucket_name)

    def _blob_path(self, session_id: str) -> str:
        return f"{self._prefix}{session_id}/metadata.json"

    def create(self, user_id: str) -> SessionMetadata:
        session_id = uuid.uuid4().hex[:16]
        session_dir = self._session_dir / session_id
        session_dir.mkdir(parents=True, exist_ok=True)

        metadata = SessionMetadata(
            session_id=session_id,
            user_id=user_id,
            created_at=time.time(),
            original_path=str(session_dir / "original.dxf"),
        )

        self.save(metadata)
        logger.info("Created GCS session %s for user %s", session_id, user_id)
        return metadata

    def get(self, session_id: str) -> SessionMetadata | None:
        try:
            from google.api_core.exceptions import GoogleAPIError

            blob = self._bucket().blob(self._blob_path(session_id))
            if not blob.exists():
                return None
            data = json.loads(blob.download_as_text())
            metadata = SessionMetadata.from_dict(data)
        except (GoogleAPIError, json.JSONDecodeError, KeyError, TypeError) as exc:
            logger.warning("Failed to fetch session %s from GCS: %s", session_id, exc)
            return None

        if metadata.is_expired:
            self.delete(session_id)
            return None

        return metadata

    def save(self, metadata: SessionMetadata) -> None:
        try:
            from google.api_core.exceptions import GoogleAPIError

            blob = self._bucket().blob(self._blob_path(metadata.session_id))
            blob.upload_from_string(
                json.dumps(metadata.to_dict(), default=str),
                content_type="application/json",
            )
        except (GoogleAPIError, json.JSONDecodeError) as exc:
            logger.exception("Failed to save session %s to GCS: %s", metadata.session_id, exc)
            raise

    def delete(self, session_id: str) -> None:
        try:
            from google.api_core.exceptions import GoogleAPIError, NotFound

            blob = self._bucket().blob(self._blob_path(session_id))
            if blob.exists():
                blob.delete()
        except NotFound:
            pass  # Already deleted — no action needed
        except GoogleAPIError as exc:
            logger.warning("Failed to delete session %s from GCS: %s", session_id, exc)

        session_dir = self._session_dir / session_id
        if session_dir.exists():
            shutil.rmtree(session_dir, ignore_errors=True)
        logger.info("Deleted GCS session %s", session_id)

    def cleanup_expired(self) -> int:
        from google.api_core.exceptions import GoogleAPIError

        count = 0
        try:
            blobs = self._bucket().list_blobs(prefix=self._prefix)
            for blob in blobs:
                if not blob.name.endswith("metadata.json"):
                    continue
                try:
                    data = json.loads(blob.download_as_text())
                    meta = SessionMetadata.from_dict(data)
                    if meta.is_expired:
                        self.delete(meta.session_id)
                        count += 1
                except (json.JSONDecodeError, KeyError, TypeError) as exc:
                    logger.warning("Skipping malformed session blob %s: %s", blob.name, exc)
        except GoogleAPIError:
            logger.exception("Failed to cleanup expired sessions from GCS")

        if count:
            logger.info("Cleaned up %d expired GCS sessions", count)
        return count

    def list_sessions(self, user_id: str | None = None) -> list[SessionMetadata]:
        from google.api_core.exceptions import GoogleAPIError

        results = []
        try:
            blobs = self._bucket().list_blobs(prefix=self._prefix)
            for blob in blobs:
                if not blob.name.endswith("metadata.json"):
                    continue
                try:
                    data = json.loads(blob.download_as_text())
                    meta = SessionMetadata.from_dict(data)
                    if not meta.is_expired and (
                        user_id is None or meta.user_id == user_id
                    ):
                        results.append(meta)
                except (json.JSONDecodeError, KeyError, TypeError) as exc:
                    logger.debug("Skipping unreadable blob %s: %s", blob.name, exc)
                    continue
        except GoogleAPIError:
            logger.exception("Failed to list sessions from GCS")

        return results

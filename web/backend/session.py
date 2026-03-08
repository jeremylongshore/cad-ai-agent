"""Session management — wraps SessionStore ABC for web backend.

The Session dataclass holds runtime objects (context, changeset, etc.)
that cannot be serialized. SessionMetadata (from core.session_store)
holds the durable, serializable subset. SessionManager bridges the two.
"""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass, field
from pathlib import Path
from threading import Lock

from cad_dxf_agent.core.session_store import (
    DEFAULT_SESSION_DIR,
    SESSION_TTL_SECONDS,
    InMemorySessionStore,
    SessionMetadata,
    SessionStore,
)

logger = logging.getLogger(__name__)


@dataclass
class Session:
    """A user editing session tied to one uploaded file.

    Combines durable metadata (survives restart via SessionStore)
    with transient runtime state (objects, loaded contexts, etc.).
    """

    session_id: str
    user_id: str
    created_at: float
    original_path: Path
    working_path: Path | None = None
    edited_path: Path | None = None
    original_render: Path | None = None
    edited_render: Path | None = None
    diff_render: Path | None = None
    changeset: object | None = None
    context: object | None = None
    file_info: dict = field(default_factory=dict)
    conversation_history: list[dict] = field(default_factory=list)
    # Comparison state
    comparison_result: object | None = None
    comparison_changelog: object | None = None
    diff_overlay_path: Path | None = None
    diff_overlay_render: Path | None = None
    # Revision pipeline state
    revision_path: Path | None = None
    alignment_result: object | None = None  # AlignmentResult
    alignment_control_points: list | None = None
    revision_ops: list | None = None  # list[RevisionOp]
    approval_set: object | None = None  # ApprovalSet
    apply_result: object | None = None  # ApplyResult
    bundle_dir: Path | None = None
    # EPIC-CAD-08: Structured edit plan preview + apply state
    edit_plan: object | None = None
    edit_preview: object | None = None
    edit_approval: object | None = None
    edit_apply_result: object | None = None
    audit_events: list = field(default_factory=list)
    # EPIC-CAD-15: Document library binding
    document_id: str = ""

    def to_metadata(self) -> SessionMetadata:
        """Extract durable metadata from this runtime session."""
        return SessionMetadata(
            session_id=self.session_id,
            user_id=self.user_id,
            created_at=self.created_at,
            file_info=self.file_info,
            conversation_history=self.conversation_history,
            audit_events=self.audit_events,
            document_id=self.document_id,
            original_path=str(self.original_path) if self.original_path else "",
            working_path=str(self.working_path) if self.working_path else "",
            edited_path=str(self.edited_path) if self.edited_path else "",
            original_render=str(self.original_render) if self.original_render else "",
            edited_render=str(self.edited_render) if self.edited_render else "",
            diff_render=str(self.diff_render) if self.diff_render else "",
            diff_overlay_path=str(self.diff_overlay_path) if self.diff_overlay_path else "",
            diff_overlay_render=str(self.diff_overlay_render) if self.diff_overlay_render else "",
            revision_path=str(self.revision_path) if self.revision_path else "",
            bundle_dir=str(self.bundle_dir) if self.bundle_dir else "",
        )

    @classmethod
    def from_metadata(cls, meta: SessionMetadata) -> Session:
        """Restore a Session from durable metadata.

        Runtime objects (context, changeset, etc.) will be None and must
        be re-loaded from DXF files on the filesystem.
        """
        return cls(
            session_id=meta.session_id,
            user_id=meta.user_id,
            created_at=meta.created_at,
            document_id=meta.document_id,
            original_path=(
                Path(meta.original_path) if meta.original_path
                else DEFAULT_SESSION_DIR / meta.session_id / "original.dxf"
            ),
            working_path=Path(meta.working_path) if meta.working_path else None,
            edited_path=Path(meta.edited_path) if meta.edited_path else None,
            original_render=Path(meta.original_render) if meta.original_render else None,
            edited_render=Path(meta.edited_render) if meta.edited_render else None,
            diff_render=Path(meta.diff_render) if meta.diff_render else None,
            diff_overlay_path=Path(meta.diff_overlay_path) if meta.diff_overlay_path else None,
            diff_overlay_render=(
                Path(meta.diff_overlay_render) if meta.diff_overlay_render else None
            ),
            revision_path=Path(meta.revision_path) if meta.revision_path else None,
            bundle_dir=Path(meta.bundle_dir) if meta.bundle_dir else None,
            file_info=meta.file_info,
            conversation_history=meta.conversation_history,
            audit_events=meta.audit_events,
        )


class SessionManager:
    """Session manager backed by a SessionStore.

    Maintains runtime Session objects in-memory while delegating
    durable metadata to the underlying SessionStore. API is unchanged
    from the original implementation for backward compatibility.
    """

    def __init__(self, store: SessionStore | None = None):
        self._store = store or InMemorySessionStore()
        self._sessions: dict[str, Session] = {}
        self._lock = Lock()

    @property
    def store(self) -> SessionStore:
        """Access the underlying session store."""
        return self._store

    def create(self, user_id: str) -> Session:
        """Create a new session with a temp directory."""
        metadata = self._store.create(user_id)

        session = Session.from_metadata(metadata)
        with self._lock:
            self._sessions[session.session_id] = session

        logger.info("Created session %s for user %s", session.session_id, user_id)
        return session

    def get(self, session_id: str, user_id: str) -> Session:
        """Get a session, validating ownership."""
        with self._lock:
            session = self._sessions.get(session_id)

        if session is None:
            raise KeyError(f"Session not found: {session_id}")
        if session.user_id != user_id:
            raise PermissionError("Session does not belong to this user")
        if time.time() - session.created_at > SESSION_TTL_SECONDS:
            self.delete(session_id)
            raise KeyError(f"Session expired: {session_id}")

        return session

    def get_by_id(self, session_id: str) -> Session:
        """Get a session by ID without ownership check."""
        with self._lock:
            session = self._sessions.get(session_id)

        if session is None:
            raise KeyError(f"Session not found: {session_id}")
        if time.time() - session.created_at > SESSION_TTL_SECONDS:
            self.delete(session_id)
            raise KeyError(f"Session expired: {session_id}")

        return session

    def delete(self, session_id: str) -> None:
        """Delete a session and its temp directory."""
        with self._lock:
            self._sessions.pop(session_id, None)

        self._store.delete(session_id)
        logger.info("Deleted session %s", session_id)

    def save_metadata(self, session: Session) -> None:
        """Persist the durable metadata for a session."""
        self._store.save(session.to_metadata())

    def cleanup_expired(self) -> int:
        """Remove all expired sessions. Returns count removed."""
        now = time.time()
        expired = []

        with self._lock:
            for sid, session in self._sessions.items():
                if now - session.created_at > SESSION_TTL_SECONDS:
                    expired.append(sid)

        for sid in expired:
            self.delete(sid)

        if expired:
            logger.info("Cleaned up %d expired sessions", len(expired))
        return len(expired)

    def find_by_document(self, user_id: str, document_id: str) -> Session | None:
        """Find an existing non-expired session for this user+document pair.

        Returns the first active session that is bound to the given document,
        or None if no such session exists.
        """
        now = time.time()
        with self._lock:
            sessions = list(self._sessions.values())

        for session in sessions:
            if session.user_id != user_id:
                continue
            if session.document_id != document_id:
                continue
            if now - session.created_at > SESSION_TTL_SECONDS:
                continue
            return session

        return None

    def list_user_sessions(self, user_id: str) -> list[Session]:
        """Return all non-expired sessions for this user."""
        now = time.time()
        with self._lock:
            sessions = list(self._sessions.values())

        return [
            s for s in sessions
            if s.user_id == user_id and now - s.created_at <= SESSION_TTL_SECONDS
        ]

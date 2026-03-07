"""Session management — temp directories for uploaded files and edits."""

from __future__ import annotations

import logging
import shutil
import time
import uuid
from dataclasses import dataclass, field
from pathlib import Path
from threading import Lock

logger = logging.getLogger(__name__)

SESSION_DIR = Path("/tmp/cad-sessions")
SESSION_TTL_SECONDS = 2 * 60 * 60  # 2 hours


@dataclass
class Session:
    """A user editing session tied to one uploaded file."""

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
    alignment_control_points: list | None = None  # parsed control points from align step
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


class SessionManager:
    """In-memory session store with temp-dir backing."""

    def __init__(self):
        self._sessions: dict[str, Session] = {}
        self._lock = Lock()
        SESSION_DIR.mkdir(parents=True, exist_ok=True)

    def create(self, user_id: str) -> Session:
        """Create a new session with a temp directory."""
        session_id = uuid.uuid4().hex[:16]
        session_dir = SESSION_DIR / session_id
        session_dir.mkdir(parents=True, exist_ok=True)

        session = Session(
            session_id=session_id,
            user_id=user_id,
            created_at=time.time(),
            original_path=session_dir / "original.dxf",
        )

        with self._lock:
            self._sessions[session_id] = session

        logger.info("Created session %s for user %s", session_id, user_id)
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
        """Get a session by ID without ownership check.

        Used for read-only endpoints (render, download) where the
        session UUID itself serves as the access credential.
        """
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
            session = self._sessions.pop(session_id, None)

        if session:
            session_dir = SESSION_DIR / session_id
            if session_dir.exists():
                shutil.rmtree(session_dir, ignore_errors=True)
            logger.info("Deleted session %s", session_id)

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

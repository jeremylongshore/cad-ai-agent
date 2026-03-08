"""Tests for Session <-> SessionMetadata bridge and SessionManager."""

from __future__ import annotations

import time
from pathlib import Path

import pytest
from web.backend.session import Session, SessionManager

from cad_dxf_agent.core.session_store import (
    SESSION_TTL_SECONDS,
    InMemorySessionStore,
    SessionMetadata,
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_session(
    session_id: str = "abc123def456abcd",
    user_id: str = "user-42",
    created_at: float | None = None,
    original_path: Path | None = None,
    working_path: Path | None = None,
) -> Session:
    """Build a minimal Session for bridge tests (no store involved)."""
    return Session(
        session_id=session_id,
        user_id=user_id,
        created_at=created_at if created_at is not None else time.time(),
        original_path=original_path or Path("/tmp/cad-sessions/abc123def456abcd/original.dxf"),
        working_path=working_path,
    )


def _make_metadata(
    session_id: str = "abc123def456abcd",
    user_id: str = "user-42",
    created_at: float | None = None,
) -> SessionMetadata:
    return SessionMetadata(
        session_id=session_id,
        user_id=user_id,
        created_at=created_at if created_at is not None else time.time(),
        original_path="/tmp/cad-sessions/abc123def456abcd/original.dxf",
    )


# ===========================================================================
# TestSessionToMetadata
# ===========================================================================


class TestSessionToMetadata:
    def test_to_metadata_preserves_ids(self):
        ts = time.time()
        session = _make_session(
            session_id="deadbeef12345678",
            user_id="u-999",
            created_at=ts,
        )
        meta = session.to_metadata()

        assert meta.session_id == "deadbeef12345678"
        assert meta.user_id == "u-999"
        assert meta.created_at == ts

    def test_to_metadata_preserves_paths(self, tmp_path: Path):
        orig = tmp_path / "original.dxf"
        work = tmp_path / "working.dxf"
        session = _make_session(original_path=orig, working_path=work)
        meta = session.to_metadata()

        assert meta.original_path == str(orig)
        assert meta.working_path == str(work)

    def test_to_metadata_preserves_file_info(self):
        session = _make_session()
        session.file_info = {"filename": "plan.dxf", "entity_count": 42, "layers": ["A", "B"]}
        meta = session.to_metadata()

        assert meta.file_info == {"filename": "plan.dxf", "entity_count": 42, "layers": ["A", "B"]}

    def test_to_metadata_preserves_conversation_history(self):
        session = _make_session()
        history = [
            {"role": "user", "content": "move line"},
            {"role": "model", "content": "moved"},
        ]
        session.conversation_history = history
        meta = session.to_metadata()

        assert meta.conversation_history == history

    def test_to_metadata_preserves_audit_events(self):
        session = _make_session()
        events = [
            {"event": "upload", "ts": 1700000000.0},
            {"event": "apply", "ts": 1700000060.0},
        ]
        session.audit_events = events
        meta = session.to_metadata()

        assert meta.audit_events == events

    def test_to_metadata_none_paths_become_empty_strings(self):
        session = _make_session()
        # All optional paths default to None
        assert session.working_path is None
        assert session.edited_path is None
        assert session.diff_render is None

        meta = session.to_metadata()

        assert meta.working_path == ""
        assert meta.edited_path == ""
        assert meta.diff_render == ""

    def test_to_metadata_returns_session_metadata_instance(self):
        session = _make_session()
        meta = session.to_metadata()
        assert isinstance(meta, SessionMetadata)


# ===========================================================================
# TestSessionFromMetadata
# ===========================================================================


class TestSessionFromMetadata:
    def test_from_metadata_restores_session(self):
        ts = time.time()
        meta = _make_metadata(
            session_id="cafebabe00000001",
            user_id="u-7",
            created_at=ts,
        )
        session = Session.from_metadata(meta)

        assert session.session_id == "cafebabe00000001"
        assert session.user_id == "u-7"
        assert session.created_at == ts

    def test_from_metadata_paths_become_path_objects(self):
        meta = SessionMetadata(
            session_id="sid1",
            user_id="u1",
            created_at=time.time(),
            original_path="/tmp/cad-sessions/sid1/original.dxf",
            working_path="/tmp/cad-sessions/sid1/working.dxf",
            edited_path="/tmp/cad-sessions/sid1/edited.dxf",
        )
        session = Session.from_metadata(meta)

        assert isinstance(session.original_path, Path)
        assert session.original_path == Path("/tmp/cad-sessions/sid1/original.dxf")
        assert isinstance(session.working_path, Path)
        assert session.working_path == Path("/tmp/cad-sessions/sid1/working.dxf")
        assert isinstance(session.edited_path, Path)

    def test_from_metadata_empty_paths_become_none(self):
        meta = SessionMetadata(
            session_id="sid2",
            user_id="u2",
            created_at=time.time(),
            original_path="/tmp/cad-sessions/sid2/original.dxf",
            working_path="",
            edited_path="",
            diff_render="",
        )
        session = Session.from_metadata(meta)

        assert session.working_path is None
        assert session.edited_path is None
        assert session.diff_render is None

    def test_from_metadata_runtime_fields_are_none(self):
        meta = _make_metadata()
        session = Session.from_metadata(meta)

        # Runtime objects must not be reconstructed from metadata
        assert session.context is None
        assert session.changeset is None
        assert session.comparison_result is None
        assert session.edit_plan is None
        assert session.edit_preview is None
        assert session.apply_result is None

    def test_roundtrip_preserves_data(self):
        ts = time.time()
        original = Session(
            session_id="roundtrip0000001",
            user_id="u-rt",
            created_at=ts,
            original_path=Path("/tmp/cad-sessions/roundtrip0000001/original.dxf"),
            working_path=Path("/tmp/cad-sessions/roundtrip0000001/working.dxf"),
            file_info={"filename": "arch.dxf", "entity_count": 10},
            conversation_history=[{"role": "user", "content": "hello"}],
            audit_events=[{"event": "upload", "ts": ts}],
        )

        restored = Session.from_metadata(original.to_metadata())

        assert restored.session_id == original.session_id
        assert restored.user_id == original.user_id
        assert restored.created_at == original.created_at
        assert restored.original_path == original.original_path
        assert restored.working_path == original.working_path
        assert restored.file_info == original.file_info
        assert restored.conversation_history == original.conversation_history
        assert restored.audit_events == original.audit_events


# ===========================================================================
# TestSessionManagerWithStore
# ===========================================================================


class TestSessionManagerWithStore:
    @pytest.fixture
    def mgr(self, tmp_path: Path) -> SessionManager:
        store = InMemorySessionStore(session_dir=tmp_path)
        manager = SessionManager(store=store)
        yield manager
        for sid in list(manager._sessions.keys()):
            manager.delete(sid)

    def test_create_uses_store(self, mgr: SessionManager):
        session = mgr.create(user_id="u1")

        # The store must hold matching metadata
        meta = mgr.store.get(session.session_id)
        assert meta is not None
        assert meta.session_id == session.session_id
        assert meta.user_id == "u1"

    def test_get_validates_ownership(self, mgr: SessionManager):
        session = mgr.create(user_id="owner")

        # Wrong user is rejected
        with pytest.raises(PermissionError, match="does not belong"):
            mgr.get(session.session_id, "intruder")

        # Correct owner succeeds
        retrieved = mgr.get(session.session_id, "owner")
        assert retrieved.session_id == session.session_id

    def test_get_raises_on_missing(self, mgr: SessionManager):
        with pytest.raises(KeyError, match="not found"):
            mgr.get("nonexistent-session-x", "u1")

    def test_get_raises_on_expired(self, mgr: SessionManager):
        session = mgr.create(user_id="u1")
        # Back-date the creation time beyond TTL
        session.created_at = time.time() - SESSION_TTL_SECONDS - 1

        with pytest.raises(KeyError, match="expired"):
            mgr.get(session.session_id, "u1")

    def test_delete_removes_from_store(self, mgr: SessionManager):
        session = mgr.create(user_id="u1")
        sid = session.session_id
        assert mgr.store.get(sid) is not None

        mgr.delete(sid)

        assert sid not in mgr._sessions
        assert mgr.store.get(sid) is None

    def test_save_metadata_persists(self, mgr: SessionManager):
        session = mgr.create(user_id="u1")
        session.file_info = {"filename": "updated.dxf", "entity_count": 99}

        mgr.save_metadata(session)

        meta = mgr.store.get(session.session_id)
        assert meta is not None
        assert meta.file_info == {"filename": "updated.dxf", "entity_count": 99}

    def test_cleanup_expired_works(self, mgr: SessionManager):
        s1 = mgr.create(user_id="u1")
        s2 = mgr.create(user_id="u2")

        # Expire only s1
        s1.created_at = time.time() - SESSION_TTL_SECONDS - 1

        removed = mgr.cleanup_expired()

        assert removed == 1
        assert s1.session_id not in mgr._sessions
        assert s2.session_id in mgr._sessions

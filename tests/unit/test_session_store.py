"""Tests for session_store module — SessionMetadata, SessionStore ABC, InMemorySessionStore."""

from __future__ import annotations

import threading
import time
from pathlib import Path
from unittest.mock import patch

import pytest

from cad_dxf_agent.core.session_store import (
    SESSION_TTL_SECONDS,
    InMemorySessionStore,
    SessionMetadata,
    SessionStore,
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _fresh_metadata(
    session_id: str = "abc123",
    user_id: str = "u1",
    state: str = "active",
    created_at: float | None = None,
) -> SessionMetadata:
    return SessionMetadata(
        session_id=session_id,
        user_id=user_id,
        created_at=created_at if created_at is not None else time.time(),
        state=state,
    )


# ---------------------------------------------------------------------------
# TestSessionMetadata
# ---------------------------------------------------------------------------


class TestSessionMetadata:
    def test_creation_with_defaults(self):
        """Newly created metadata has sane defaults for all optional fields."""
        m = SessionMetadata(session_id="s1", user_id="u1", created_at=1000.0)
        assert m.state == "active"
        assert m.file_info == {}
        assert m.conversation_history == []
        assert m.audit_events == []
        assert m.original_path == ""
        assert m.edited_path == ""
        assert m.bundle_dir == ""

    def test_to_dict_roundtrip(self):
        """to_dict() / from_dict() round-trip preserves all fields."""
        m = SessionMetadata(
            session_id="s42",
            user_id="alice",
            created_at=9999.5,
            state="completed",
            file_info={"name": "plan.dxf", "size": 1024},
            conversation_history=[{"role": "user", "content": "hi"}],
            audit_events=[{"event": "upload"}],
            original_path="/tmp/cad-sessions/s42/original.dxf",
            working_path="/tmp/cad-sessions/s42/working.dxf",
            diff_render="/tmp/cad-sessions/s42/diff.png",
        )
        restored = SessionMetadata.from_dict(m.to_dict())
        assert restored.session_id == "s42"
        assert restored.user_id == "alice"
        assert restored.created_at == 9999.5
        assert restored.state == "completed"
        assert restored.file_info == {"name": "plan.dxf", "size": 1024}
        assert restored.conversation_history == [{"role": "user", "content": "hi"}]
        assert restored.original_path == "/tmp/cad-sessions/s42/original.dxf"
        assert restored.diff_render == "/tmp/cad-sessions/s42/diff.png"

    def test_from_dict_filters_unknown_keys(self):
        """from_dict() silently drops fields not present on the dataclass."""
        data = {
            "session_id": "s1",
            "user_id": "u1",
            "created_at": 1000.0,
            "unknown_future_field": "should-be-ignored",
            "another_extra": 42,
        }
        m = SessionMetadata.from_dict(data)
        assert m.session_id == "s1"
        assert not hasattr(m, "unknown_future_field")

    def test_from_dict_with_missing_optional_keys(self):
        """from_dict() tolerates absent optional fields and uses dataclass defaults."""
        data = {"session_id": "s2", "user_id": "u2", "created_at": 500.0}
        m = SessionMetadata.from_dict(data)
        assert m.state == "active"
        assert m.file_info == {}
        assert m.conversation_history == []
        assert m.original_path == ""

    def test_is_expired_fresh_is_false(self):
        """A just-created session is not expired."""
        m = _fresh_metadata()
        assert m.is_expired is False

    def test_is_expired_old_is_true(self):
        """A session older than SESSION_TTL_SECONDS is expired."""
        stale_time = time.time() - SESSION_TTL_SECONDS - 1
        m = _fresh_metadata(created_at=stale_time)
        assert m.is_expired is True

    def test_is_expired_when_state_is_expired(self):
        """state='expired' marks the session expired regardless of age."""
        m = _fresh_metadata(state="expired")
        assert m.is_expired is True

    def test_is_expired_state_completed_uses_ttl(self):
        """state='completed' still respects the TTL check."""
        m = _fresh_metadata(state="completed")
        assert m.is_expired is False  # fresh, so TTL not exceeded

    def test_state_default_is_active(self):
        """Default state for a new SessionMetadata is 'active'."""
        m = SessionMetadata(session_id="x", user_id="y", created_at=1.0)
        assert m.state == "active"


# ---------------------------------------------------------------------------
# TestSessionStoreABC
# ---------------------------------------------------------------------------


class TestSessionStoreABC:
    def test_cannot_instantiate_abc_directly(self):
        """SessionStore is abstract and cannot be instantiated directly."""
        with pytest.raises(TypeError):
            SessionStore()  # type: ignore[abstract]


# ---------------------------------------------------------------------------
# TestInMemorySessionStore
# ---------------------------------------------------------------------------


@pytest.fixture
def store(tmp_path: Path) -> InMemorySessionStore:
    """Isolated InMemorySessionStore using tmp_path to avoid touching /tmp."""
    return InMemorySessionStore(session_dir=tmp_path / "cad-sessions")


class TestInMemorySessionStore:
    def test_create_returns_metadata_with_valid_fields(self, store: InMemorySessionStore):
        """create() returns a SessionMetadata with required fields populated."""
        m = store.create(user_id="u1")
        assert isinstance(m, SessionMetadata)
        assert m.user_id == "u1"
        assert m.state == "active"
        assert len(m.session_id) == 16
        assert m.created_at > 0

    def test_create_assigns_unique_session_ids(self, store: InMemorySessionStore):
        """Successive create() calls produce distinct session IDs."""
        ids = {store.create(user_id="u1").session_id for _ in range(10)}
        assert len(ids) == 10

    def test_create_makes_temp_directory(self, store: InMemorySessionStore):
        """create() creates a backing directory under session_dir."""
        m = store.create(user_id="u1")
        session_dir = store.session_dir / m.session_id
        assert session_dir.is_dir()

    def test_get_returns_metadata_for_existing_session(self, store: InMemorySessionStore):
        """get() retrieves the metadata for a session that was just created."""
        m = store.create(user_id="u1")
        retrieved = store.get(m.session_id)
        assert retrieved is not None
        assert retrieved.session_id == m.session_id
        assert retrieved.user_id == "u1"

    def test_get_returns_none_for_nonexistent_session(self, store: InMemorySessionStore):
        """get() returns None when the session ID is unknown."""
        result = store.get("does-not-exist")
        assert result is None

    def test_get_returns_none_and_deletes_expired_session(self, store: InMemorySessionStore):
        """get() auto-deletes and returns None when the session is expired."""
        m = store.create(user_id="u1")
        sid = m.session_id
        # Wind the clock forward past TTL
        future_time = time.time() + SESSION_TTL_SECONDS + 1
        with patch("cad_dxf_agent.core.session_store.time") as mock_time:
            mock_time.time.return_value = future_time
            # is_expired is evaluated via time.time() inside the property
            # We must also patch the module-level time used in cleanup
            result = store.get(sid)
        assert result is None
        # Session should have been removed from the internal dict
        assert sid not in store._sessions

    def test_save_updates_existing_metadata(self, store: InMemorySessionStore):
        """save() overwrites metadata for an existing session_id."""
        m = store.create(user_id="u1")
        m.state = "completed"
        m.file_info = {"name": "drawing.dxf"}
        store.save(m)
        retrieved = store.get(m.session_id)
        assert retrieved is not None
        assert retrieved.state == "completed"
        assert retrieved.file_info == {"name": "drawing.dxf"}

    def test_save_can_add_new_metadata(self, store: InMemorySessionStore):
        """save() can insert arbitrary metadata (not created through create())."""
        m = _fresh_metadata(session_id="custom-id-1234567")
        store.save(m)
        retrieved = store.get("custom-id-1234567")
        assert retrieved is not None
        assert retrieved.user_id == "u1"

    def test_delete_removes_session(self, store: InMemorySessionStore):
        """delete() removes the session from the internal dict."""
        m = store.create(user_id="u1")
        sid = m.session_id
        store.delete(sid)
        assert store.get(sid) is None

    def test_delete_removes_temp_directory(self, store: InMemorySessionStore):
        """delete() removes the backing temp directory."""
        m = store.create(user_id="u1")
        sid = m.session_id
        session_dir = store.session_dir / sid
        assert session_dir.exists()
        store.delete(sid)
        assert not session_dir.exists()

    def test_delete_nonexistent_session_is_noop(self, store: InMemorySessionStore):
        """delete() on an unknown session_id does not raise."""
        store.delete("ghost-session-id")  # must not raise

    def test_cleanup_expired_removes_old_sessions(self, store: InMemorySessionStore):
        """cleanup_expired() removes sessions whose age exceeds the TTL."""
        stale = store.create(user_id="u1")
        fresh = store.create(user_id="u2")

        # Make the stale session appear old by backdating created_at directly
        store._sessions[stale.session_id].created_at = time.time() - SESSION_TTL_SECONDS - 60

        store.cleanup_expired()

        assert store.get(stale.session_id) is None
        assert store.get(fresh.session_id) is not None

    def test_cleanup_expired_returns_count(self, store: InMemorySessionStore):
        """cleanup_expired() returns the number of sessions it removed."""
        for _ in range(3):
            m = store.create(user_id="u1")
            store._sessions[m.session_id].created_at = time.time() - SESSION_TTL_SECONDS - 60
        # One fresh session that should survive
        store.create(user_id="u1")

        removed = store.cleanup_expired()
        assert removed == 3

    def test_cleanup_expired_leaves_active_sessions_alone(self, store: InMemorySessionStore):
        """cleanup_expired() does not touch sessions within the TTL window."""
        sessions = [store.create(user_id="u1") for _ in range(5)]
        removed = store.cleanup_expired()
        assert removed == 0
        for m in sessions:
            assert store.get(m.session_id) is not None

    def test_list_sessions_returns_all_active(self, store: InMemorySessionStore):
        """list_sessions() returns all non-expired sessions when no filter is given."""
        s1 = store.create(user_id="alice")
        s2 = store.create(user_id="bob")
        listed_ids = {m.session_id for m in store.list_sessions()}
        assert s1.session_id in listed_ids
        assert s2.session_id in listed_ids

    def test_list_sessions_filtered_by_user_id(self, store: InMemorySessionStore):
        """list_sessions(user_id=...) returns only sessions belonging to that user."""
        store.create(user_id="alice")
        store.create(user_id="alice")
        store.create(user_id="bob")

        alice_sessions = store.list_sessions(user_id="alice")
        assert len(alice_sessions) == 2
        assert all(m.user_id == "alice" for m in alice_sessions)

    def test_list_sessions_excludes_expired(self, store: InMemorySessionStore):
        """list_sessions() excludes sessions whose TTL has been exceeded."""
        active = store.create(user_id="u1")
        stale = store.create(user_id="u1")
        store._sessions[stale.session_id].created_at = time.time() - SESSION_TTL_SECONDS - 60

        listed_ids = {m.session_id for m in store.list_sessions()}
        assert active.session_id in listed_ids
        assert stale.session_id not in listed_ids

    def test_custom_session_dir(self, tmp_path: Path):
        """InMemorySessionStore respects a caller-supplied session_dir."""
        custom_dir = tmp_path / "my-sessions"
        s = InMemorySessionStore(session_dir=custom_dir)
        assert s.session_dir == custom_dir
        assert custom_dir.is_dir()

        m = s.create(user_id="u1")
        assert (custom_dir / m.session_id).is_dir()

    def test_thread_safety_concurrent_create(self, store: InMemorySessionStore):
        """Concurrent create() calls from multiple threads produce unique sessions."""
        results: list[SessionMetadata] = []
        errors: list[Exception] = []
        lock = threading.Lock()

        def worker():
            try:
                m = store.create(user_id="parallel-user")
                with lock:
                    results.append(m)
            except Exception as exc:
                with lock:
                    errors.append(exc)

        threads = [threading.Thread(target=worker) for _ in range(20)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        assert errors == [], f"Thread errors: {errors}"
        assert len(results) == 20
        # All session IDs must be unique
        ids = {m.session_id for m in results}
        assert len(ids) == 20

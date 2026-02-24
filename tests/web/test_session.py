"""Tests for SessionManager (web/backend/session.py)."""

from __future__ import annotations

import time
from pathlib import Path
from unittest.mock import patch

import pytest

from web.backend.session import Session, SessionManager


@pytest.mark.web
class TestSessionManager:
    @pytest.fixture
    def mgr(self):
        m = SessionManager()
        yield m
        # Cleanup
        for sid in list(m._sessions.keys()):
            m.delete(sid)

    def test_create_returns_session_with_id(self, mgr):
        session = mgr.create(user_id="u1")
        assert isinstance(session, Session)
        assert len(session.session_id) == 16
        assert session.user_id == "u1"

    def test_create_makes_directory(self, mgr):
        session = mgr.create(user_id="u1")
        session_dir = Path("/tmp/cad-sessions") / session.session_id
        assert session_dir.is_dir()

    def test_get_returns_session(self, mgr):
        session = mgr.create(user_id="u1")
        retrieved = mgr.get(session.session_id, "u1")
        assert retrieved.session_id == session.session_id

    def test_get_wrong_user_raises_permission(self, mgr):
        session = mgr.create(user_id="u1")
        with pytest.raises(PermissionError, match="does not belong"):
            mgr.get(session.session_id, "u2")

    def test_get_nonexistent_raises_keyerror(self, mgr):
        with pytest.raises(KeyError, match="not found"):
            mgr.get("nonexistent-id-1234", "u1")

    def test_get_expired_session_raises_keyerror(self, mgr):
        session = mgr.create(user_id="u1")
        # Make session appear created 3 hours ago
        session.created_at = time.time() - (3 * 60 * 60)
        with pytest.raises(KeyError, match="expired"):
            mgr.get(session.session_id, "u1")

    def test_delete_removes_session_and_dir(self, mgr):
        session = mgr.create(user_id="u1")
        sid = session.session_id
        session_dir = Path("/tmp/cad-sessions") / sid
        assert session_dir.exists()

        mgr.delete(sid)
        assert sid not in mgr._sessions
        assert not session_dir.exists()

    def test_cleanup_expired_removes_old(self, mgr):
        s1 = mgr.create(user_id="u1")
        s2 = mgr.create(user_id="u2")
        # Make s1 expired
        s1.created_at = time.time() - (3 * 60 * 60)

        removed = mgr.cleanup_expired()
        assert removed == 1
        assert s1.session_id not in mgr._sessions
        assert s2.session_id in mgr._sessions

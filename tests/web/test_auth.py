"""Tests for Firebase Auth token verification (web/backend/auth.py).

Auth is the ONE boundary where we must isolate from the external Firebase SDK.
We use real Starlette Request objects (not MagicMock) and only patch the
firebase_admin.auth.verify_id_token call since there's no real Firebase project
in the test environment.
"""

from __future__ import annotations

import os

import pytest
from fastapi import HTTPException
from starlette.requests import Request


def _make_request(auth_header: str | None = None) -> Request:
    """Build a real Starlette Request with the given Authorization header."""
    headers_dict = {}
    if auth_header is not None:
        headers_dict["authorization"] = auth_header
    scope = {
        "type": "http",
        "method": "GET",
        "path": "/",
        "headers": [(k.encode(), v.encode()) for k, v in headers_dict.items()],
    }
    return Request(scope)


@pytest.mark.web
class TestAuthVerifyToken:
    """Test verify_token function in isolation (no HTTP)."""

    @pytest.fixture(autouse=True)
    def _reset_firebase(self):
        """Reset the lazy-init firebase app between tests."""
        import web.backend.auth as auth_mod

        auth_mod._firebase_app = None
        yield
        auth_mod._firebase_app = None

    @pytest.mark.asyncio
    async def test_dev_mode_bypasses_auth(self):
        from web.backend.auth import verify_token

        req = _make_request()
        old = os.environ.get("CAD_WEB_DEV_MODE")
        os.environ["CAD_WEB_DEV_MODE"] = "1"
        try:
            result = await verify_token(req)
        finally:
            if old is None:
                os.environ.pop("CAD_WEB_DEV_MODE", None)
            else:
                os.environ["CAD_WEB_DEV_MODE"] = old
        assert result["uid"] == "dev-user"
        assert result["email"] == "dev@localhost"

    @pytest.mark.asyncio
    async def test_missing_auth_header_returns_401(self):
        from web.backend.auth import verify_token

        os.environ.pop("CAD_WEB_DEV_MODE", None)
        req = _make_request(auth_header="")
        with pytest.raises(HTTPException) as exc_info:
            await verify_token(req)
        assert exc_info.value.status_code == 401

    @pytest.mark.asyncio
    async def test_empty_bearer_token_returns_401(self):
        from web.backend.auth import verify_token

        os.environ.pop("CAD_WEB_DEV_MODE", None)
        req = _make_request(auth_header="Bearer ")
        with pytest.raises(HTTPException) as exc_info:
            await verify_token(req)
        assert exc_info.value.status_code == 401

    @pytest.mark.asyncio
    async def test_invalid_token_returns_401(self):
        """A bad token triggers firebase_admin to reject — we patch only the SDK call."""
        from unittest.mock import patch

        from web.backend.auth import verify_token

        os.environ.pop("CAD_WEB_DEV_MODE", None)
        req = _make_request(auth_header="Bearer invalid-token-abc")
        with (
            patch("web.backend.auth._init_firebase"),
            patch("firebase_admin.auth.verify_id_token", side_effect=Exception("bad token")),
            pytest.raises(HTTPException) as exc_info,
        ):
            await verify_token(req)
        assert exc_info.value.status_code == 401

    @pytest.mark.asyncio
    async def test_valid_token_returns_decoded(self):
        """A valid token returns the decoded payload — we patch only the SDK call."""
        from unittest.mock import patch

        from web.backend.auth import verify_token

        os.environ.pop("CAD_WEB_DEV_MODE", None)
        decoded = {"uid": "real-user-456", "email": "user@example.com"}
        req = _make_request(auth_header="Bearer valid-token-xyz")
        with (
            patch("web.backend.auth._init_firebase"),
            patch("firebase_admin.auth.verify_id_token", return_value=decoded),
        ):
            result = await verify_token(req)
        assert result["uid"] == "real-user-456"

    @pytest.mark.asyncio
    async def test_non_bearer_scheme_returns_401(self):
        from web.backend.auth import verify_token

        os.environ.pop("CAD_WEB_DEV_MODE", None)
        req = _make_request(auth_header="Basic abc123")
        with pytest.raises(HTTPException) as exc_info:
            await verify_token(req)
        assert exc_info.value.status_code == 401

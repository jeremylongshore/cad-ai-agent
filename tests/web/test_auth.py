"""Tests for Firebase Auth token verification (web/backend/auth.py)."""

from __future__ import annotations

import os
from unittest.mock import MagicMock, patch

import pytest
from fastapi import HTTPException


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

    def _make_request(self, auth_header: str | None = None) -> MagicMock:
        req = MagicMock()
        if auth_header is not None:
            req.headers.get.return_value = auth_header
        else:
            req.headers.get.return_value = ""
        return req

    @pytest.mark.asyncio
    async def test_dev_mode_bypasses_auth(self):
        from web.backend.auth import verify_token

        req = self._make_request()
        with patch.dict(os.environ, {"CAD_WEB_DEV_MODE": "1"}):
            result = await verify_token(req)
        assert result["uid"] == "dev-user"
        assert result["email"] == "dev@localhost"

    @pytest.mark.asyncio
    async def test_missing_auth_header_returns_401(self):
        from web.backend.auth import verify_token

        req = self._make_request(auth_header="")
        with patch.dict(os.environ, {}, clear=False):
            os.environ.pop("CAD_WEB_DEV_MODE", None)
            with pytest.raises(HTTPException) as exc_info:
                await verify_token(req)
        assert exc_info.value.status_code == 401

    @pytest.mark.asyncio
    async def test_empty_bearer_token_returns_401(self):
        from web.backend.auth import verify_token

        req = self._make_request(auth_header="Bearer ")
        with patch.dict(os.environ, {}, clear=False):
            os.environ.pop("CAD_WEB_DEV_MODE", None)
            with pytest.raises(HTTPException) as exc_info:
                await verify_token(req)
        assert exc_info.value.status_code == 401

    @pytest.mark.asyncio
    async def test_invalid_token_returns_401(self):
        from web.backend.auth import verify_token

        req = self._make_request(auth_header="Bearer invalid-token-abc")
        with patch.dict(os.environ, {}, clear=False):
            os.environ.pop("CAD_WEB_DEV_MODE", None)
            with (
                patch("web.backend.auth._init_firebase"),
                patch("firebase_admin.auth.verify_id_token", side_effect=Exception("bad token")),
            ):
                with pytest.raises(HTTPException) as exc_info:
                    await verify_token(req)
        assert exc_info.value.status_code == 401

    @pytest.mark.asyncio
    async def test_valid_token_returns_decoded(self):
        from web.backend.auth import verify_token

        decoded = {"uid": "real-user-456", "email": "user@example.com"}
        req = self._make_request(auth_header="Bearer valid-token-xyz")
        with patch.dict(os.environ, {}, clear=False):
            os.environ.pop("CAD_WEB_DEV_MODE", None)
            with (
                patch("web.backend.auth._init_firebase"),
                patch("firebase_admin.auth.verify_id_token", return_value=decoded),
            ):
                result = await verify_token(req)
        assert result["uid"] == "real-user-456"

    @pytest.mark.asyncio
    async def test_non_bearer_scheme_returns_401(self):
        from web.backend.auth import verify_token

        req = self._make_request(auth_header="Basic abc123")
        with patch.dict(os.environ, {}, clear=False):
            os.environ.pop("CAD_WEB_DEV_MODE", None)
            with pytest.raises(HTTPException) as exc_info:
                await verify_token(req)
        assert exc_info.value.status_code == 401

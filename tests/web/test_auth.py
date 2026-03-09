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


@pytest.mark.web
class TestCheckLicense:
    """Test check_license: anonymous rejection, auto-provisioning, expiry."""

    @pytest.fixture(autouse=True)
    def _reset_state(self):
        """Reset caches between tests."""
        import web.backend.auth as auth_mod

        auth_mod._license_cache.clear()
        auth_mod._allowlist_cache.clear()
        old_dev = os.environ.pop("CAD_WEB_DEV_MODE", None)
        yield
        auth_mod._license_cache.clear()
        auth_mod._allowlist_cache.clear()
        if old_dev is not None:
            os.environ["CAD_WEB_DEV_MODE"] = old_dev
        else:
            os.environ.pop("CAD_WEB_DEV_MODE", None)

    @pytest.mark.asyncio
    async def test_anonymous_user_rejected(self):
        from web.backend.auth import check_license

        user = {"uid": "anon-123", "firebase": {"sign_in_provider": "anonymous"}}
        with pytest.raises(HTTPException) as exc_info:
            await check_license(user)
        assert exc_info.value.status_code == 403
        assert "Google sign-in required" in exc_info.value.detail

    @pytest.mark.asyncio
    async def test_user_without_email_rejected(self):
        from web.backend.auth import check_license

        user = {"uid": "no-email-456", "firebase": {"sign_in_provider": "google.com"}}
        with pytest.raises(HTTPException) as exc_info:
            await check_license(user)
        assert exc_info.value.status_code == 403
        assert "Google sign-in required" in exc_info.value.detail

    @pytest.mark.asyncio
    async def test_existing_active_license_passes(self):
        from unittest.mock import patch

        from web.backend.auth import check_license

        user = {
            "uid": "licensed-user",
            "email": "u@example.com",
            "firebase": {"sign_in_provider": "google.com"},
        }
        with patch("web.backend.auth._fetch_license", return_value=True):
            await check_license(user)  # should not raise

    @pytest.mark.asyncio
    async def test_new_user_auto_provisioned_when_on_allowlist(self):
        from unittest.mock import MagicMock, patch

        from web.backend.auth import check_license

        user = {
            "uid": "new-user",
            "email": "anyone@gmail.com",
            "firebase": {"sign_in_provider": "google.com"},
        }

        mock_provision = MagicMock()
        with (
            patch("web.backend.auth._fetch_license", return_value=False),
            patch("web.backend.auth._check_email_allowed", return_value=True),
            patch("web.backend.auth._provision_license", mock_provision),
        ):
            await check_license(user)  # should not raise

        mock_provision.assert_called_once_with("new-user", "anyone@gmail.com")

    @pytest.mark.asyncio
    async def test_expired_license_returns_403(self):
        from unittest.mock import patch

        from web.backend.auth import check_license

        user = {
            "uid": "expired-user",
            "email": "u@example.com",
            "firebase": {"sign_in_provider": "google.com"},
        }
        # _fetch_license returns False for expired licenses
        with (
            patch("web.backend.auth._fetch_license", return_value=False),
            patch("web.backend.auth._provision_license", side_effect=Exception("already exists")),
            pytest.raises(HTTPException),
        ):
            await check_license(user)

    @pytest.mark.asyncio
    async def test_dev_mode_bypasses_license(self):
        from web.backend.auth import check_license

        os.environ["CAD_WEB_DEV_MODE"] = "1"
        user = {"uid": "any-user"}
        await check_license(user)  # should not raise


@pytest.mark.web
class TestAllowlist:
    """Test email allowlist gating for auto-provisioning."""

    @pytest.fixture(autouse=True)
    def _reset_state(self):
        """Reset caches and env vars between tests."""
        import web.backend.auth as auth_mod

        auth_mod._license_cache.clear()
        auth_mod._allowlist_cache.clear()
        old_dev = os.environ.pop("CAD_WEB_DEV_MODE", None)
        old_allowed = os.environ.pop("CAD_ALLOWED_EMAILS", None)
        yield
        auth_mod._license_cache.clear()
        auth_mod._allowlist_cache.clear()
        if old_dev is not None:
            os.environ["CAD_WEB_DEV_MODE"] = old_dev
        else:
            os.environ.pop("CAD_WEB_DEV_MODE", None)
        if old_allowed is not None:
            os.environ["CAD_ALLOWED_EMAILS"] = old_allowed
        else:
            os.environ.pop("CAD_ALLOWED_EMAILS", None)

    @pytest.mark.asyncio
    async def test_unlisted_email_rejected_with_403(self):
        """A new user not on the allowlist gets 403, not auto-provisioned."""
        from unittest.mock import patch

        from web.backend.auth import check_license

        user = {
            "uid": "stranger",
            "email": "stranger@gmail.com",
            "firebase": {"sign_in_provider": "google.com"},
        }
        with (
            patch("web.backend.auth._fetch_license", return_value=False),
            patch("web.backend.auth._check_email_allowed", return_value=False),
            pytest.raises(HTTPException) as exc_info,
        ):
            await check_license(user)
        assert exc_info.value.status_code == 403
        assert "Access restricted" in exc_info.value.detail

    @pytest.mark.asyncio
    async def test_env_var_allows_email(self):
        """Email listed in CAD_ALLOWED_EMAILS is auto-provisioned."""
        from unittest.mock import MagicMock, patch

        from web.backend.auth import check_license

        os.environ["CAD_ALLOWED_EMAILS"] = "beta@test.com,vip@corp.com"
        user = {
            "uid": "beta-user",
            "email": "beta@test.com",
            "firebase": {"sign_in_provider": "google.com"},
        }
        mock_provision = MagicMock()
        with (
            patch("web.backend.auth._fetch_license", return_value=False),
            patch("web.backend.auth._provision_license", mock_provision),
        ):
            await check_license(user)
        mock_provision.assert_called_once()

    @pytest.mark.asyncio
    async def test_env_var_case_insensitive(self):
        """Allowlist matching is case-insensitive."""
        from unittest.mock import MagicMock, patch

        from web.backend.auth import check_license

        os.environ["CAD_ALLOWED_EMAILS"] = "BETA@Test.COM"
        user = {
            "uid": "beta-user",
            "email": "beta@test.com",
            "firebase": {"sign_in_provider": "google.com"},
        }
        mock_provision = MagicMock()
        with (
            patch("web.backend.auth._fetch_license", return_value=False),
            patch("web.backend.auth._provision_license", mock_provision),
        ):
            await check_license(user)
        mock_provision.assert_called_once()

    @pytest.mark.asyncio
    async def test_firestore_allowlist_allows_email(self):
        """Email found in Firestore allowlist collection is auto-provisioned."""
        from unittest.mock import MagicMock, patch

        from web.backend.auth import check_license

        user = {
            "uid": "firestore-user",
            "email": "approved@corp.com",
            "firebase": {"sign_in_provider": "google.com"},
        }
        mock_provision = MagicMock()
        with (
            patch("web.backend.auth._fetch_license", return_value=False),
            patch("web.backend.auth._check_email_allowed", return_value=True),
            patch("web.backend.auth._provision_license", mock_provision),
        ):
            await check_license(user)
        mock_provision.assert_called_once()

    @pytest.mark.asyncio
    async def test_existing_license_skips_allowlist(self):
        """A user with an active license is not checked against the allowlist."""
        from unittest.mock import patch

        from web.backend.auth import check_license

        user = {
            "uid": "existing-user",
            "email": "old@example.com",
            "firebase": {"sign_in_provider": "google.com"},
        }
        # _check_email_allowed should NOT be called
        with (
            patch("web.backend.auth._fetch_license", return_value=True),
            patch("web.backend.auth._check_email_allowed") as mock_check,
        ):
            await check_license(user)
        mock_check.assert_not_called()

    @pytest.mark.asyncio
    async def test_allowlist_cached(self):
        """Second check for same email uses the cache, not Firestore."""
        import time

        from web.backend.auth import _allowlist_cache, _check_email_allowed

        # Pre-populate cache
        _allowlist_cache["cached@test.com"] = (True, time.monotonic())
        # No Firestore or env var needed — cache hit
        assert _check_email_allowed("cached@test.com") is True

    @pytest.mark.asyncio
    async def test_dev_mode_bypasses_allowlist(self):
        """Dev mode skips the entire license+allowlist chain."""
        from web.backend.auth import check_license

        os.environ["CAD_WEB_DEV_MODE"] = "1"
        user = {"uid": "any-user"}
        await check_license(user)  # should not raise

"""Tests for user profile endpoints (EPIC-CAD-30)."""

from __future__ import annotations

import pytest

starlette = pytest.importorskip("starlette", reason="web backend tests require fastapi/starlette")


@pytest.mark.web
class TestGetProfile:
    def test_get_profile_returns_200(self, client, monkeypatch):
        """GET /api/profile returns 200 with the expected envelope."""
        monkeypatch.setenv("CAD_WEB_DEV_MODE", "1")
        resp = client.get("/api/profile")
        assert resp.status_code == 200

    def test_get_profile_contains_uid(self, client, monkeypatch):
        """Profile response includes the authenticated user's uid."""
        monkeypatch.setenv("CAD_WEB_DEV_MODE", "1")
        resp = client.get("/api/profile")
        data = resp.json()
        assert "profile" in data
        assert data["profile"]["uid"] == "test-user-123"

    def test_get_profile_contains_email(self, client, monkeypatch):
        """Profile response includes the authenticated user's email."""
        monkeypatch.setenv("CAD_WEB_DEV_MODE", "1")
        resp = client.get("/api/profile")
        profile = resp.json()["profile"]
        assert profile["email"] == "test@example.com"

    def test_get_profile_contains_display_name(self, client, monkeypatch):
        """Profile response includes a display_name field."""
        monkeypatch.setenv("CAD_WEB_DEV_MODE", "1")
        resp = client.get("/api/profile")
        profile = resp.json()["profile"]
        assert "display_name" in profile

    def test_get_profile_contains_tenant_id(self, client, monkeypatch):
        """Profile response includes a tenant_id field."""
        monkeypatch.setenv("CAD_WEB_DEV_MODE", "1")
        resp = client.get("/api/profile")
        profile = resp.json()["profile"]
        assert "tenant_id" in profile

    def test_get_profile_dev_mode_returns_synthetic(self, client, monkeypatch):
        """Dev mode returns a synthetic profile without hitting Firestore."""
        monkeypatch.setenv("CAD_WEB_DEV_MODE", "1")
        resp = client.get("/api/profile")
        assert resp.status_code == 200
        profile = resp.json()["profile"]
        # Tenant defaults to dev-tenant in dev mode
        assert profile["tenant_id"] == "dev-tenant"


@pytest.mark.web
class TestUpdateProfile:
    def test_put_profile_with_display_name_returns_200(self, client, monkeypatch):
        """PUT /api/profile with a display_name returns 200."""
        monkeypatch.setenv("CAD_WEB_DEV_MODE", "1")
        resp = client.put("/api/profile", json={"display_name": "Alice Smith"})
        assert resp.status_code == 200

    def test_put_profile_response_contains_updated_display_name(self, client, monkeypatch):
        """PUT /api/profile response echoes the updated display_name."""
        monkeypatch.setenv("CAD_WEB_DEV_MODE", "1")
        resp = client.put("/api/profile", json={"display_name": "Bob Jones"})
        profile = resp.json()["profile"]
        assert profile["display_name"] == "Bob Jones"

    def test_put_profile_response_contains_uid(self, client, monkeypatch):
        """PUT /api/profile response includes the authenticated user's uid."""
        monkeypatch.setenv("CAD_WEB_DEV_MODE", "1")
        resp = client.put("/api/profile", json={"display_name": "Carol"})
        profile = resp.json()["profile"]
        assert profile["uid"] == "test-user-123"

    def test_put_profile_empty_body_returns_400_outside_dev_mode(self, client, monkeypatch):
        """PUT /api/profile with no update fields returns 400 when not in dev mode.

        In dev mode the endpoint short-circuits before the validation check, so this
        test patches CAD_WEB_DEV_MODE out (not set) to exercise the real validation
        path.  The auth dep is still overridden by the ``client`` fixture so the
        request reaches the handler.
        """
        monkeypatch.delenv("CAD_WEB_DEV_MODE", raising=False)
        resp = client.put("/api/profile", json={})
        assert resp.status_code == 400

    def test_put_profile_with_company_dev_mode_returns_200(self, client, monkeypatch):
        """PUT /api/profile with a company field is accepted in dev mode."""
        monkeypatch.setenv("CAD_WEB_DEV_MODE", "1")
        resp = client.put("/api/profile", json={"company": "Acme Corp"})
        assert resp.status_code == 200

    def test_put_profile_with_both_fields_dev_mode(self, client, monkeypatch):
        """PUT /api/profile with display_name and company succeeds in dev mode."""
        monkeypatch.setenv("CAD_WEB_DEV_MODE", "1")
        resp = client.put(
            "/api/profile",
            json={"display_name": "Dana Lee", "company": "Blueprint Inc"},
        )
        assert resp.status_code == 200
        profile = resp.json()["profile"]
        assert profile["display_name"] == "Dana Lee"

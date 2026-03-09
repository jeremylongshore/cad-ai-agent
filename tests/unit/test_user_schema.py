"""Tests for user_schema — UserProfile model."""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from cad_dxf_agent.models.user_schema import UserProfile


class TestUserProfileDefaults:
    def test_required_fields_only(self):
        u = UserProfile(uid="uid-1", email="alice@example.com", tenant_id="tid-001")
        assert u.uid == "uid-1"
        assert u.email == "alice@example.com"
        assert u.tenant_id == "tid-001"
        assert u.display_name == ""
        assert u.company == ""
        assert u.role == "owner"
        assert u.settings == {}
        assert u.created_at  # non-empty ISO string
        assert u.last_login_at  # non-empty ISO string


class TestUserProfileAllFields:
    def test_all_fields_accepted(self):
        u = UserProfile(
            uid="uid-2",
            email="bob@firm.com",
            display_name="Bob Builder",
            company="Builder LLC",
            tenant_id="tid-002",
            role="editor",
            created_at="2026-01-01T00:00:00+00:00",
            last_login_at="2026-03-01T12:00:00+00:00",
            settings={"theme": "dark", "notifications": True},
        )
        assert u.display_name == "Bob Builder"
        assert u.company == "Builder LLC"
        assert u.role == "editor"
        assert u.settings["theme"] == "dark"

    def test_viewer_role(self):
        u = UserProfile(uid="u", email="v@x.com", tenant_id="t", role="viewer")
        assert u.role == "viewer"


class TestUserProfileRoleValidation:
    def test_invalid_role_raises(self):
        with pytest.raises(ValidationError):
            UserProfile(uid="u", email="x@x.com", tenant_id="t", role="admin")

    def test_invalid_role_uppercase_raises(self):
        with pytest.raises(ValidationError):
            UserProfile(uid="u", email="x@x.com", tenant_id="t", role="Owner")


class TestUserProfileTouchLogin:
    def test_touch_login_updates_timestamp(self):
        u = UserProfile(
            uid="uid-3",
            email="charlie@x.com",
            tenant_id="tid-003",
            last_login_at="2020-01-01T00:00:00+00:00",
        )
        old = u.last_login_at
        u.touch_login()
        assert u.last_login_at != old
        assert u.last_login_at > old

    def test_touch_login_does_not_change_other_fields(self):
        u = UserProfile(uid="uid-4", email="d@x.com", tenant_id="tid-004")
        original_email = u.email
        original_uid = u.uid
        u.touch_login()
        assert u.email == original_email
        assert u.uid == original_uid


class TestUserProfileJsonRoundtrip:
    def test_roundtrip_minimal(self):
        u = UserProfile(uid="uid-5", email="e@x.com", tenant_id="tid-005")
        restored = UserProfile.model_validate_json(u.model_dump_json())
        assert restored.uid == u.uid
        assert restored.email == u.email
        assert restored.tenant_id == u.tenant_id
        assert restored.role == u.role
        assert restored.settings == u.settings

    def test_roundtrip_preserves_role_and_settings(self):
        u = UserProfile(
            uid="uid-6",
            email="f@firm.com",
            tenant_id="tid-006",
            role="editor",
            settings={"lang": "en"},
        )
        restored = UserProfile.model_validate_json(u.model_dump_json())
        assert restored.role == "editor"
        assert restored.settings == {"lang": "en"}

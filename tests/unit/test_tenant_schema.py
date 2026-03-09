"""Tests for tenant_schema — Tenant model."""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from cad_dxf_agent.models.tenant_schema import Tenant


class TestTenantDefaults:
    def test_required_fields_only(self):
        t = Tenant(name="Acme Corp", owner_uid="uid-abc")
        assert t.name == "Acme Corp"
        assert t.owner_uid == "uid-abc"
        assert t.plan == "personal"
        assert t.settings == {}
        assert t.tenant_id  # auto-generated, non-empty
        assert t.created_at  # non-empty ISO string

    def test_tenant_id_length(self):
        t = Tenant(name="Studio X", owner_uid="uid-xyz")
        assert len(t.tenant_id) == 12

    def test_unique_tenant_ids(self):
        tenants = [Tenant(name="T", owner_uid="u") for _ in range(10)]
        ids = {t.tenant_id for t in tenants}
        assert len(ids) == 10

    def test_explicit_tenant_id(self):
        t = Tenant(tenant_id="custom000001", name="X", owner_uid="u")
        assert t.tenant_id == "custom000001"


class TestTenantAllFields:
    def test_all_fields_accepted(self):
        t = Tenant(
            tenant_id="abc123def456",
            name="Enterprise LLC",
            owner_uid="uid-owner-1",
            plan="enterprise",
            created_at="2026-01-01T00:00:00+00:00",
            settings={"max_users": 500, "feature_flags": ["batch_ops"]},
        )
        assert t.plan == "enterprise"
        assert t.settings["max_users"] == 500
        assert t.created_at == "2026-01-01T00:00:00+00:00"

    def test_team_plan(self):
        t = Tenant(name="Design Team", owner_uid="uid-t", plan="team")
        assert t.plan == "team"


class TestTenantPlanValidation:
    def test_invalid_plan_raises(self):
        with pytest.raises(ValidationError):
            Tenant(name="X", owner_uid="u", plan="pro")

    def test_invalid_plan_uppercase_raises(self):
        with pytest.raises(ValidationError):
            Tenant(name="X", owner_uid="u", plan="Personal")


class TestTenantJsonRoundtrip:
    def test_roundtrip_minimal(self):
        t = Tenant(name="Round Trip Co", owner_uid="uid-rt")
        restored = Tenant.model_validate_json(t.model_dump_json())
        assert restored.tenant_id == t.tenant_id
        assert restored.name == t.name
        assert restored.owner_uid == t.owner_uid
        assert restored.plan == t.plan
        assert restored.settings == t.settings

    def test_roundtrip_with_settings(self):
        t = Tenant(
            name="Full Corp",
            owner_uid="uid-full",
            plan="enterprise",
            settings={"region": "us-west", "seats": 50},
        )
        restored = Tenant.model_validate_json(t.model_dump_json())
        assert restored.settings == {"region": "us-west", "seats": 50}
        assert restored.plan == "enterprise"

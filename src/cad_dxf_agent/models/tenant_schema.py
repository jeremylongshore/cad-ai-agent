"""Tenant model for multi-tenant workspace isolation.

Every resource is scoped to a tenant. For beta, each user auto-gets a personal
tenant (1:1). Later, an org admin creates a shared tenant and invites members.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from typing import Any, Literal

from pydantic import BaseModel, Field


class Tenant(BaseModel):
    """A workspace tenant — the top-level isolation boundary.

    Personal tenants are auto-provisioned on first login.
    Team/enterprise tenants are created by org admins (future).
    """

    tenant_id: str = Field(default_factory=lambda: uuid.uuid4().hex[:12])
    name: str
    owner_uid: str
    plan: Literal["personal", "team", "enterprise"] = "personal"
    created_at: str = Field(default_factory=lambda: datetime.now(UTC).isoformat())
    settings: dict[str, Any] = Field(default_factory=dict)

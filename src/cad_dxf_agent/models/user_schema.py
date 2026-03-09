"""User profile model for persistent user identity.

Stored in Firestore at ``users/{uid}``. Links the Firebase Auth identity
to a tenant and tracks display preferences.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any, Literal

from pydantic import BaseModel, Field


class UserProfile(BaseModel):
    """Persistent user profile linked to a tenant workspace."""

    uid: str
    email: str
    display_name: str = ""
    company: str = ""
    tenant_id: str
    role: Literal["owner", "editor", "viewer"] = "owner"
    created_at: str = Field(default_factory=lambda: datetime.now(UTC).isoformat())
    last_login_at: str = Field(default_factory=lambda: datetime.now(UTC).isoformat())
    settings: dict[str, Any] = Field(default_factory=dict)

    def touch_login(self) -> None:
        """Update last_login_at to now."""
        self.last_login_at = datetime.now(UTC).isoformat()

"""Apply schema for structured edit plan application (EPIC-CAD-08).

Defines typed models for the result of applying an EditPlan, approval
decisions, and audit events.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from enum import StrEnum
from typing import Any

from pydantic import BaseModel, Field


class ApplyStatus(StrEnum):
    """Outcome of applying an edit plan."""

    SUCCESS = "success"
    PARTIAL = "partial"
    FAILED = "failed"
    REJECTED = "rejected"


class ActionResult(BaseModel):
    """Result of applying a single edit action."""

    action_id: str
    action_type: str
    success: bool = True
    entity_handle: str | None = None
    description: str = ""
    error: str | None = None


class ApplyResult(BaseModel):
    """Complete result of applying an edit plan."""

    apply_id: str = Field(default_factory=lambda: uuid.uuid4().hex[:16])
    plan_id: str = ""
    preview_id: str = ""
    request_id: str = ""
    status: ApplyStatus = ApplyStatus.SUCCESS
    action_results: list[ActionResult] = Field(default_factory=list)
    success_count: int = 0
    failure_count: int = 0
    output_path: str | None = None
    revision_note: str | None = None
    summary: str = ""
    warnings: list[str] = Field(default_factory=list)
    apply_ms: float | None = None
    save_ms: float | None = None
    total_ms: float | None = None


class AuditEvent(BaseModel):
    """Audit trail event for the preview/approve/apply workflow."""

    event_id: str = Field(default_factory=lambda: uuid.uuid4().hex[:16])
    event_type: str
    timestamp: str = Field(default_factory=lambda: datetime.now(UTC).isoformat())
    plan_id: str | None = None
    preview_id: str | None = None
    apply_id: str | None = None
    actor: str = ""
    details: dict[str, Any] = Field(default_factory=dict)


class ApprovalDecision(BaseModel):
    """User approval or rejection of an edit plan."""

    plan_id: str
    approved: bool
    approved_by: str = ""
    approved_at: str = Field(default_factory=lambda: datetime.now(UTC).isoformat())
    notes: str = ""

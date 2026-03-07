"""Preview schema for structured edit plan previews (EPIC-CAD-08).

Defines typed models for previewing what an EditPlan will do before
applying it. Each action gets a before/after state, confidence badge,
risk indicator, and destructive flag.
"""

from __future__ import annotations

import uuid
from enum import StrEnum
from typing import Any

from pydantic import BaseModel, Field

from .response_schema import RiskLevel


class PreviewStatus(StrEnum):
    """Overall status of an edit preview."""

    READY = "ready"
    BLOCKED = "blocked"
    NEEDS_CLARIFICATION = "needs_clarification"


class ActionPreview(BaseModel):
    """Preview of a single edit action with before/after state."""

    action_id: str
    action_type: str
    description: str = ""
    target_handle: str | None = None
    target_layer: str | None = None
    target_entity_type: str | None = None
    before_state: dict[str, Any] = Field(default_factory=dict)
    after_state: dict[str, Any] = Field(default_factory=dict)
    confidence: float = Field(default=1.0, ge=0.0, le=1.0)
    risk_level: RiskLevel = RiskLevel.LOW
    is_destructive: bool = False
    warnings: list[str] = Field(default_factory=list)
    ambiguity: list[str] = Field(default_factory=list)
    validation_status: str = "valid"
    blockers: list[str] = Field(default_factory=list)


class EditPreview(BaseModel):
    """Complete preview of an edit plan — what will happen if applied."""

    preview_id: str = Field(default_factory=lambda: uuid.uuid4().hex[:16])
    plan_id: str = ""
    request_id: str = ""
    status: PreviewStatus = PreviewStatus.READY
    actions: list[ActionPreview] = Field(default_factory=list)
    total_actions: int = 0
    destructive_count: int = 0
    blocked_count: int = 0
    confidence: float = Field(default=1.0, ge=0.0, le=1.0)
    risk_level: RiskLevel = RiskLevel.LOW
    summary: str = ""
    warnings: list[str] = Field(default_factory=list)
    approval_requirements: list[str] = Field(default_factory=list)
    requires_approval: bool = True
    preview_build_ms: float | None = None

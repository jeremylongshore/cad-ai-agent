"""Precision control schemas for EPIC-CAD-14 — Professional Precision Controls.

Professionals can override AI inference with exact targeting, inspectability,
deterministic overrides, and structured preview/audit. All models flow via
PlatformRequest.client_metadata — no new request/response types.
"""

from __future__ import annotations

from enum import StrEnum
from typing import Any

from pydantic import BaseModel, Field


class PrecisionControls(BaseModel):
    """User-specified precision overrides flowing via client_metadata.precision.

    Controls entity scope (handles, layers, types), deterministic deltas,
    and confidence thresholds. All fields optional — omitted = no override.
    """

    target_handles: list[str] = Field(default_factory=list)
    target_layers: list[str] = Field(default_factory=list)
    exclude_layers: list[str] = Field(default_factory=list)
    target_types: list[str] = Field(default_factory=list)
    model_space_only: bool = False
    exact_delta: dict[str, float] | None = None
    confidence_threshold: float = Field(default=0.0, ge=0.0, le=1.0)
    disable_inference: bool = False


class MatchCandidate(BaseModel):
    """A candidate entity when targeting is ambiguous."""

    handle: str
    layer: str
    entity_type: str
    confidence: float = Field(ge=0.0, le=1.0)
    match_reason: str = ""
    location: tuple[float, float] | None = None


class ActionStatus(StrEnum):
    """Status of a per-entity action in the precision audit trail."""

    PLANNED = "planned"
    APPLIED = "applied"
    SKIPPED = "skipped"
    BLOCKED = "blocked"


class ActionDetail(BaseModel):
    """Per-entity breakdown for structured preview/audit."""

    entity_handle: str
    entity_type: str
    layer: str
    action: str
    before: dict[str, Any] = Field(default_factory=dict)
    after: dict[str, Any] = Field(default_factory=dict)
    status: ActionStatus = ActionStatus.PLANNED
    skip_reason: str | None = None
    confidence: float = Field(default=1.0, ge=0.0, le=1.0)
    evidence: list[str] = Field(default_factory=list)

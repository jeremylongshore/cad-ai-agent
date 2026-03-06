"""Platform response contracts for the Drawing Intelligence Platform.

Defines TaskFamily (11 intent categories), ResponseType (7 response kinds),
RiskLevel, EvidenceRef, AuditMetadata, PlatformRequest, and the PlatformResponse envelope.

All responses from /api/v2/prompt use PlatformResponse regardless of task family.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from enum import StrEnum
from typing import Any

from pydantic import BaseModel, Field


class TaskFamily(StrEnum):
    """Intent categories for the Drawing Intelligence Platform.

    Priority order (heuristic matching):
    1. compare
    2. markup_interpretation
    3. edit_plan
    4. apply_edit
    5. takeoff_estimate
    6. repeated_condition
    7. design_assist
    8. summary
    9. qna
    10. needs_clarification (fallback)
    11. unsupported (system-level, never from user intent)

    11 members total.
    """

    COMPARE = "compare"
    MARKUP_INTERPRETATION = "markup_interpretation"
    EDIT_PLAN = "edit_plan"
    APPLY_EDIT = "apply_edit"
    TAKEOFF_ESTIMATE = "takeoff_estimate"
    REPEATED_CONDITION = "repeated_condition"
    DESIGN_ASSIST = "design_assist"
    SUMMARY = "summary"
    QNA = "qna"
    NEEDS_CLARIFICATION = "needs_clarification"
    UNSUPPORTED = "unsupported"


class ResponseType(StrEnum):
    """The kind of response being returned."""

    PLAN_ONLY = "plan_only"
    PREVIEW_EDIT = "preview_edit"
    APPLIED_EDIT = "applied_edit"
    ANSWER_ONLY = "answer_only"
    COMPARISON_RESULT = "comparison_result"
    NEEDS_CLARIFICATION = "needs_clarification"
    UNSUPPORTED_OPERATION = "unsupported_operation"


class RiskLevel(StrEnum):
    """Risk classification for planned operations."""

    NONE = "none"  # no risk, informational
    LOW = "low"  # reversible, non-destructive
    MEDIUM = "medium"  # potentially destructive, requires confirmation
    HIGH = "high"  # destructive/irreversible operations


class EvidenceRef(BaseModel):
    """Reference to supporting evidence (entity handle, layer, coordinate)."""

    entity_handle: str | None = None
    layer: str | None = None
    description: str = ""
    entity_type: str | None = None
    location: tuple[float, float] | None = None
    text_excerpt: str | None = None


class AuditMetadata(BaseModel):
    """Audit trail and latency instrumentation for every response."""

    trace_id: str = Field(default_factory=lambda: uuid.uuid4().hex[:16])
    timestamp: str = Field(default_factory=lambda: datetime.now(UTC).isoformat())
    router_time_ms: float | None = None
    context_build_time_ms: float | None = None
    llm_time_ms: float | None = None
    validation_time_ms: float | None = None
    total_request_time_ms: float | None = None
    router_source: str | None = None
    router_confidence: float | None = None


class PlatformRequest(BaseModel):
    """Typed request contract for /api/v2/prompt."""

    request_id: str = Field(default_factory=lambda: uuid.uuid4().hex[:16])
    prompt: str
    session_id: str
    task_family: TaskFamily | None = None  # pre-classified, or None for router
    selected_regions: list[dict[str, Any]] = Field(default_factory=list)
    drawing_references: list[str] = Field(default_factory=list)
    comparison_references: list[str] = Field(default_factory=list)
    markup_references: list[str] = Field(default_factory=list)
    client_metadata: dict[str, Any] = Field(default_factory=dict)
    schema_version: str = "1.0"


class PlatformResponse(BaseModel):
    """Typed response envelope for all /api/v2/prompt responses.

    Every response includes:
    - task_family: which intent category was identified
    - response_type: what kind of response this is
    - message: human-readable summary
    - audit: latency and trace metadata

    Depending on response_type:
    - plan_only: operations list populated, not yet applied
    - preview_edit: proposed edit with diff preview, awaiting confirmation
    - applied_edit: edit was executed and saved
    - answer_only: message contains the answer text
    - comparison_result: operations may contain diff ops
    - needs_clarification: message asks for more info
    - unsupported_operation: message explains what's not available
    """

    task_family: TaskFamily
    response_type: ResponseType
    message: str
    operations: list[dict[str, Any]] = Field(default_factory=list)
    risk_level: RiskLevel = RiskLevel.LOW
    evidence: list[EvidenceRef] = Field(default_factory=list)
    validation: dict[str, Any] | None = None
    audit: AuditMetadata = Field(default_factory=AuditMetadata)
    schema_version: str = "1.0"
    confidence: float | None = None  # top-level routing confidence
    ambiguity_flags: list[str] = Field(default_factory=list)
    data: dict[str, Any] = Field(default_factory=dict)  # task-specific payload
    session_id: str | None = None

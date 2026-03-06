"""Platform response contracts for the Drawing Intelligence Platform.

Defines TaskFamily (10 intent categories), ResponseType (6 response kinds),
RiskLevel, EvidenceRef, AuditMetadata, and the PlatformResponse envelope.

All responses from /api/v2/prompt use PlatformResponse regardless of task family.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from enum import StrEnum
from typing import Any

from pydantic import BaseModel, Field


class TaskFamily(StrEnum):
    """Intent categories for the Drawing Intelligence Platform.

    Priority order (heuristic matching):
    1. compare
    2. markup_interpretation
    3. edit_plan
    4. takeoff_estimate
    5. repeated_condition
    6. design_assist
    7. summary
    8. qna
    9. needs_clarification (fallback)
    10. unsupported (system-level, never from user intent)
    """

    COMPARE = "compare"
    MARKUP_INTERPRETATION = "markup_interpretation"
    EDIT_PLAN = "edit_plan"
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
    PLAN_APPLIED = "plan_applied"
    ANSWER = "answer"
    COMPARISON_RESULT = "comparison_result"
    NEEDS_CLARIFICATION = "needs_clarification"
    UNSUPPORTED_OPERATION = "unsupported_operation"


class RiskLevel(StrEnum):
    """Risk classification for planned operations."""

    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"


class EvidenceRef(BaseModel):
    """Reference to supporting evidence (entity handle, layer, coordinate)."""

    entity_handle: str | None = None
    layer: str | None = None
    description: str = ""


class AuditMetadata(BaseModel):
    """Audit trail and latency instrumentation for every response."""

    trace_id: str = Field(default_factory=lambda: uuid.uuid4().hex[:16])
    timestamp: str = Field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat()
    )
    router_time_ms: float | None = None
    context_build_time_ms: float | None = None
    llm_time_ms: float | None = None
    validation_time_ms: float | None = None
    total_request_time_ms: float | None = None
    router_source: str | None = None
    router_confidence: float | None = None


class PlatformResponse(BaseModel):
    """Typed response envelope for all /api/v2/prompt responses.

    Every response includes:
    - task_family: which intent category was identified
    - response_type: what kind of response this is
    - message: human-readable summary
    - audit: latency and trace metadata

    Depending on response_type:
    - plan_only/plan_applied: operations list populated
    - answer: message contains the answer text
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

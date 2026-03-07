"""Edit plan schema for structured edit planning (EPIC-CAD-07).

Defines the canonical typed edit plan model that represents a set of
validated, bounded edit actions ready for preview/apply in the next epic.
Plans are plan_only — they describe changes but do not execute them.
"""

from __future__ import annotations

import uuid
from enum import StrEnum

from pydantic import BaseModel, Field

from .response_schema import EvidenceRef, RiskLevel


class EditActionType(StrEnum):
    """Supported edit action types for structured planning.

    Each action maps to a concrete V1 operation that the edit engine
    can execute. Unsupported operations must not be planned.
    """

    MOVE_ENTITY = "move_entity"
    EDIT_TEXT = "edit_text"
    DELETE_ENTITY = "delete_entity"
    ADD_BLOCK = "add_block"
    REPLICATE_NOTE = "replicate_note"


class PlanValidationStatus(StrEnum):
    """Validation outcome for an edit plan or individual action."""

    VALID = "valid"
    VALID_WITH_WARNINGS = "valid_with_warnings"
    BLOCKED = "blocked"
    NEEDS_CLARIFICATION = "needs_clarification"


class ActionValidationDetail(BaseModel):
    """Per-action validation result."""

    status: PlanValidationStatus = PlanValidationStatus.VALID
    blockers: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)


class EditAction(BaseModel):
    """A single edit action within a structured edit plan.

    Each action is typed, bounded, and traceable — with explicit
    confidence, evidence, and validation status.
    """

    action_id: str = Field(default_factory=lambda: uuid.uuid4().hex[:12])
    action_type: EditActionType
    target_handle: str | None = Field(
        default=None, description="Handle of the entity to act on"
    )
    target_layer: str | None = None
    target_entity_type: str | None = None
    region_id: str | None = Field(
        default=None, description="Source region for this action"
    )
    params: dict = Field(
        default_factory=dict,
        description="Action-specific parameters (dx/dy, new_text, block_name, etc.)",
    )
    evidence: list[EvidenceRef] = Field(
        default_factory=list, description="Supporting evidence for this action"
    )
    rationale: str = Field(
        default="", description="Why this action was planned"
    )
    confidence: float = Field(
        default=1.0, ge=0.0, le=1.0, description="Confidence in this action"
    )
    ambiguity: list[str] = Field(
        default_factory=list, description="Ambiguity flags for this action"
    )
    risk_level: RiskLevel = RiskLevel.LOW
    validation: ActionValidationDetail = Field(
        default_factory=ActionValidationDetail
    )


class ApprovalRequirement(BaseModel):
    """A condition that must be met before the plan can be applied."""

    requirement_id: str = Field(default_factory=lambda: uuid.uuid4().hex[:8])
    description: str
    category: str = "user_confirmation"
    satisfied: bool = False


class PlanLatency(BaseModel):
    """Timing metadata for plan generation."""

    context_build_ms: float | None = None
    plan_build_ms: float | None = None
    validation_ms: float | None = None
    total_ms: float | None = None


class EditPlan(BaseModel):
    """Canonical typed edit plan — the structured output of edit planning.

    An EditPlan describes a bounded set of edit actions with explicit
    confidence, validation, risk, and approval requirements. Plans
    are plan_only: they do not apply changes. The preview/apply workflow
    (EPIC-CAD-08) consumes EditPlan as its input.
    """

    schema_version: str = "1.0"
    plan_id: str = Field(default_factory=lambda: uuid.uuid4().hex[:16])
    request_id: str = Field(
        default_factory=lambda: uuid.uuid4().hex[:16],
        description="Correlates to the originating PlatformRequest",
    )
    task_family: str = "edit_plan"

    # Drawing references
    source_drawing: str | None = Field(
        default=None, description="Path or ID of the source drawing"
    )
    target_drawing: str | None = Field(
        default=None, description="Path or ID of the target drawing (if different)"
    )

    # Selection context
    selected_region_ids: list[str] = Field(
        default_factory=list, description="Region IDs used as input"
    )
    entity_handles: list[str] = Field(
        default_factory=list, description="Known entity handles used as input"
    )

    # Actions
    actions: list[EditAction] = Field(
        default_factory=list, description="Ordered list of planned edit actions"
    )

    # Aggregate assessment
    confidence: float = Field(
        default=1.0, ge=0.0, le=1.0, description="Overall plan confidence"
    )
    ambiguity_flags: list[str] = Field(
        default_factory=list, description="Plan-level ambiguity flags"
    )
    risk_level: RiskLevel = RiskLevel.LOW
    validation_status: PlanValidationStatus = PlanValidationStatus.VALID
    blocked_reasons: list[str] = Field(
        default_factory=list, description="Why the plan is blocked (if status=blocked)"
    )

    # Evidence and rationale
    evidence: list[EvidenceRef] = Field(
        default_factory=list, description="Plan-level evidence references"
    )
    rationale: str = Field(
        default="", description="Top-level explanation of the plan"
    )

    # Approval
    approval_requirements: list[ApprovalRequirement] = Field(
        default_factory=list,
        description="Conditions that must be satisfied before apply",
    )
    requires_approval: bool = Field(
        default=True, description="Whether user approval is needed before apply"
    )

    # Metadata
    latency: PlanLatency = Field(default_factory=PlanLatency)
    prompt: str = Field(default="", description="Original user request text")

    @property
    def action_count(self) -> int:
        return len(self.actions)

    @property
    def is_blocked(self) -> bool:
        return self.validation_status == PlanValidationStatus.BLOCKED

    @property
    def has_warnings(self) -> bool:
        return self.validation_status == PlanValidationStatus.VALID_WITH_WARNINGS

    @property
    def needs_clarification(self) -> bool:
        return self.validation_status == PlanValidationStatus.NEEDS_CLARIFICATION

"""Response builder — constructs typed PlatformResponse objects.

Static methods for each response type. Keeps response construction
logic in one place rather than scattered across endpoints.
"""

from __future__ import annotations

from typing import Any

from cad_dxf_agent.models.plan_schema import EditPlan
from cad_dxf_agent.models.response_schema import (
    AuditMetadata,
    EvidenceRef,
    PlatformResponse,
    ResponseType,
    RiskLevel,
    TaskFamily,
)


class ResponseBuilder:
    """Factory for typed PlatformResponse objects."""

    @staticmethod
    def plan_only(
        *,
        operations: list[dict[str, Any]],
        message: str,
        validation: dict[str, Any] | None = None,
        audit: AuditMetadata | None = None,
        risk_level: RiskLevel | None = None,
    ) -> PlatformResponse:
        """Build a plan_only response (edit operations planned, not yet applied)."""
        return PlatformResponse(
            task_family=TaskFamily.EDIT_PLAN,
            response_type=ResponseType.PLAN_ONLY,
            message=message,
            operations=operations,
            validation=validation,
            risk_level=_infer_risk(operations, risk_level),
            audit=audit or AuditMetadata(),
        )

    @staticmethod
    def unsupported_operation(
        *,
        family: TaskFamily,
        audit: AuditMetadata | None = None,
    ) -> PlatformResponse:
        """Build an unsupported_operation response for unimplemented families."""
        family_labels = {
            TaskFamily.QNA: "Q&A",
            TaskFamily.SUMMARY: "Drawing summary",
            TaskFamily.MARKUP_INTERPRETATION: "Markup interpretation",
            TaskFamily.TAKEOFF_ESTIMATE: "Takeoff estimation",
            TaskFamily.REPEATED_CONDITION: "Repeated condition detection",
            TaskFamily.DESIGN_ASSIST: "Design assistance",
        }
        label = family_labels.get(family, family.value.replace("_", " ").title())
        return PlatformResponse(
            task_family=family,
            response_type=ResponseType.UNSUPPORTED_OPERATION,
            message=f"{label} is not yet available.",
            audit=audit or AuditMetadata(),
        )

    @staticmethod
    def needs_clarification(
        *,
        message: str = "Could you be more specific about what you'd like to do?",
        family: TaskFamily = TaskFamily.NEEDS_CLARIFICATION,
        audit: AuditMetadata | None = None,
    ) -> PlatformResponse:
        """Build a needs_clarification response."""
        return PlatformResponse(
            task_family=family,
            response_type=ResponseType.NEEDS_CLARIFICATION,
            message=message,
            audit=audit or AuditMetadata(),
        )

    @staticmethod
    def comparison_result(
        *,
        message: str,
        operations: list[dict[str, Any]] | None = None,
        data: dict[str, Any] | None = None,
        audit: AuditMetadata | None = None,
    ) -> PlatformResponse:
        """Build a comparison_result response."""
        return PlatformResponse(
            task_family=TaskFamily.COMPARE,
            response_type=ResponseType.COMPARISON_RESULT,
            message=message,
            operations=operations or [],
            data=data or {},
            audit=audit or AuditMetadata(),
        )

    @staticmethod
    def answer(
        *,
        family: TaskFamily,
        message: str,
        evidence: list[Any] | None = None,
        confidence: float | None = None,
        data: dict[str, Any] | None = None,
        ambiguity_flags: list[str] | None = None,
        audit: AuditMetadata | None = None,
    ) -> PlatformResponse:
        """Build an answer response (Q&A, summary, etc.)."""
        return PlatformResponse(
            task_family=family,
            response_type=ResponseType.ANSWER_ONLY,
            message=message,
            evidence=evidence or [],
            confidence=confidence,
            data=data or {},
            ambiguity_flags=ambiguity_flags or [],
            audit=audit or AuditMetadata(),
        )

    @staticmethod
    def repeated_condition(
        *,
        message: str,
        data: dict[str, Any],
        evidence: list[Any] | None = None,
        confidence: float | None = None,
        ambiguity_flags: list[str] | None = None,
        audit: AuditMetadata | None = None,
    ) -> PlatformResponse:
        """Build a repeated_condition response (preview of found conditions)."""
        return PlatformResponse(
            task_family=TaskFamily.REPEATED_CONDITION,
            response_type=ResponseType.ANSWER_ONLY,
            message=message,
            evidence=evidence or [],
            confidence=confidence,
            data=data,
            ambiguity_flags=ambiguity_flags or [],
            risk_level=RiskLevel.NONE,
            audit=audit or AuditMetadata(),
        )

    @staticmethod
    def structured_plan(
        *,
        plan: EditPlan,
        message: str | None = None,
        audit: AuditMetadata | None = None,
    ) -> PlatformResponse:
        """Build a plan_only response from a structured EditPlan."""
        operations = [
            {
                "action_id": a.action_id,
                "action_type": a.action_type.value,
                "target_handle": a.target_handle,
                "target_layer": a.target_layer,
                "params": a.params,
                "confidence": a.confidence,
                "risk_level": a.risk_level.value,
                "rationale": a.rationale,
                "validation_status": a.validation.status.value,
            }
            for a in plan.actions
        ]
        plan_message = message or plan.rationale or "Structured edit plan generated."
        return PlatformResponse(
            task_family=TaskFamily.EDIT_PLAN,
            response_type=ResponseType.PLAN_ONLY,
            message=plan_message,
            operations=operations,
            risk_level=plan.risk_level,
            evidence=plan.evidence,
            confidence=plan.confidence,
            ambiguity_flags=plan.ambiguity_flags,
            validation={
                "status": plan.validation_status.value,
                "blocked_reasons": plan.blocked_reasons,
                "approval_requirements": [
                    {
                        "description": r.description,
                        "category": r.category,
                        "satisfied": r.satisfied,
                    }
                    for r in plan.approval_requirements
                ],
            },
            data={
                "plan_id": plan.plan_id,
                "schema_version": plan.schema_version,
                "action_count": plan.action_count,
            },
            audit=audit or AuditMetadata(),
        )

    @staticmethod
    def preview_edit(
        *,
        operations: list[dict[str, Any]],
        message: str,
        validation: dict[str, Any] | None = None,
        audit: AuditMetadata | None = None,
        risk_level: RiskLevel | None = None,
    ) -> PlatformResponse:
        """Build a preview_edit response (proposed edit with diff preview)."""
        return PlatformResponse(
            task_family=TaskFamily.EDIT_PLAN,
            response_type=ResponseType.PREVIEW_EDIT,
            message=message,
            operations=operations,
            validation=validation,
            risk_level=_infer_risk(operations, risk_level),
            audit=audit or AuditMetadata(),
        )

    @staticmethod
    def applied_edit(
        *,
        operations: list[dict[str, Any]],
        message: str,
        audit: AuditMetadata | None = None,
    ) -> PlatformResponse:
        """Build an applied_edit response (edit was executed and saved)."""
        return PlatformResponse(
            task_family=TaskFamily.APPLY_EDIT,
            response_type=ResponseType.APPLIED_EDIT,
            message=message,
            operations=operations,
            risk_level=RiskLevel.NONE,
            audit=audit or AuditMetadata(),
        )


def _infer_risk(
    operations: list[dict[str, Any]],
    override: RiskLevel | None,
) -> RiskLevel:
    """Infer risk level from operation count and types."""
    if override is not None:
        return override
    if not operations:
        return RiskLevel.LOW

    delete_count = sum(1 for op in operations if op.get("op_type") == "delete_entity")
    total = len(operations)

    if delete_count > 5 or total > 20:
        return RiskLevel.HIGH
    if delete_count > 0 or total > 5:
        return RiskLevel.MEDIUM
    return RiskLevel.LOW

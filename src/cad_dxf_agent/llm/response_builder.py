"""Response builder — constructs typed PlatformResponse objects.

Static methods for each response type. Keeps response construction
logic in one place rather than scattered across endpoints.
"""

from __future__ import annotations

from typing import Any

from cad_dxf_agent.models.response_schema import (
    AuditMetadata,
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
        audit: AuditMetadata | None = None,
    ) -> PlatformResponse:
        """Build a comparison_result response."""
        return PlatformResponse(
            task_family=TaskFamily.COMPARE,
            response_type=ResponseType.COMPARISON_RESULT,
            message=message,
            operations=operations or [],
            audit=audit or AuditMetadata(),
        )

    @staticmethod
    def answer(
        *,
        family: TaskFamily,
        message: str,
        audit: AuditMetadata | None = None,
    ) -> PlatformResponse:
        """Build an answer response (Q&A, summary, etc.)."""
        return PlatformResponse(
            task_family=family,
            response_type=ResponseType.ANSWER_ONLY,
            message=message,
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

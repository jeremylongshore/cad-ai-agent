"""Response builder — constructs typed PlatformResponse objects.

Static methods for each response type. Keeps response construction
logic in one place rather than scattered across endpoints.
"""

from __future__ import annotations

from typing import Any

from cad_dxf_agent.models.plan_schema import EditPlan
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
        ambiguity_candidates: list[dict[str, Any]] | None = None,
        precision_actions: list[dict[str, Any]] | None = None,
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
            ambiguity_candidates=ambiguity_candidates or [],
            precision_actions=precision_actions or [],
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
        message: str = (
            "I'm not sure what you'd like to do. Try asking something like:\n"
            '\u2022 "summarize this drawing"\n'
            '\u2022 "how many doors are there"\n'
            '\u2022 "what text is in this drawing"\n'
            '\u2022 "suggest layout improvements"'
        ),
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
    def design_assist(
        *,
        message: str,
        data: dict[str, Any],
        evidence: list[Any] | None = None,
        confidence: float | None = None,
        ambiguity_flags: list[str] | None = None,
        audit: AuditMetadata | None = None,
    ) -> PlatformResponse:
        """Build a design_assist response (layout recommendations, scope summaries)."""
        return PlatformResponse(
            task_family=TaskFamily.DESIGN_ASSIST,
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
    def summary_result(
        *,
        message: str,
        data: dict[str, Any],
        evidence: list[Any] | None = None,
        confidence: float | None = None,
        ambiguity_flags: list[str] | None = None,
        audit: AuditMetadata | None = None,
    ) -> PlatformResponse:
        """Build a summary response (revision summaries)."""
        return PlatformResponse(
            task_family=TaskFamily.SUMMARY,
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
    def takeoff_result(
        *,
        message: str,
        data: dict[str, Any],
        evidence: list[Any] | None = None,
        confidence: float | None = None,
        ambiguity_flags: list[str] | None = None,
        audit: AuditMetadata | None = None,
    ) -> PlatformResponse:
        """Build a takeoff_estimate response."""
        return PlatformResponse(
            task_family=TaskFamily.TAKEOFF_ESTIMATE,
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
    def markup_redline(
        *,
        message: str,
        data: dict[str, Any],
        evidence: list[Any] | None = None,
        confidence: float | None = None,
        ambiguity_flags: list[str] | None = None,
        audit: AuditMetadata | None = None,
    ) -> PlatformResponse:
        """Build a markup_interpretation response (redline report)."""
        return PlatformResponse(
            task_family=TaskFamily.MARKUP_INTERPRETATION,
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
        ambiguity_candidates: list[dict[str, Any]] | None = None,
        precision_actions: list[dict[str, Any]] | None = None,
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
            ambiguity_candidates=ambiguity_candidates or [],
            precision_actions=precision_actions or [],
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

    @staticmethod
    def structured_preview(
        *,
        preview: Any,
        message: str | None = None,
        audit: AuditMetadata | None = None,
    ) -> PlatformResponse:
        """Build a preview_edit response from a structured EditPreview."""
        preview_dict = preview.model_dump() if hasattr(preview, "model_dump") else preview
        actions = preview_dict.get("actions", [])
        operations = [
            {
                "action_id": a.get("action_id"),
                "action_type": a.get("action_type"),
                "description": a.get("description", ""),
                "target_handle": a.get("target_handle"),
                "target_layer": a.get("target_layer"),
                "before_state": a.get("before_state", {}),
                "after_state": a.get("after_state", {}),
                "confidence": a.get("confidence"),
                "risk_level": a.get("risk_level"),
                "is_destructive": a.get("is_destructive", False),
                "warnings": a.get("warnings", []),
            }
            for a in actions
        ]
        return PlatformResponse(
            task_family=TaskFamily.EDIT_PLAN,
            response_type=ResponseType.PREVIEW_EDIT,
            message=message or preview_dict.get("summary", "Preview ready."),
            operations=operations,
            risk_level=RiskLevel(preview_dict.get("risk_level", "low")),
            confidence=preview_dict.get("confidence"),
            data={
                "preview_id": preview_dict.get("preview_id"),
                "plan_id": preview_dict.get("plan_id"),
                "status": preview_dict.get("status"),
                "total_actions": preview_dict.get("total_actions", 0),
                "destructive_count": preview_dict.get("destructive_count", 0),
                "blocked_count": preview_dict.get("blocked_count", 0),
                "requires_approval": preview_dict.get("requires_approval", True),
            },
            audit=audit or AuditMetadata(),
        )

    @staticmethod
    def structured_apply_result(
        *,
        result: Any,
        message: str | None = None,
        audit: AuditMetadata | None = None,
    ) -> PlatformResponse:
        """Build an applied_edit response from a structured ApplyResult."""
        result_dict = result.model_dump() if hasattr(result, "model_dump") else result
        action_results = result_dict.get("action_results", [])
        operations = [
            {
                "action_id": ar.get("action_id"),
                "action_type": ar.get("action_type"),
                "success": ar.get("success"),
                "entity_handle": ar.get("entity_handle"),
                "description": ar.get("description", ""),
                "error": ar.get("error"),
            }
            for ar in action_results
        ]
        return PlatformResponse(
            task_family=TaskFamily.APPLY_EDIT,
            response_type=ResponseType.APPLIED_EDIT,
            message=message or result_dict.get("summary", "Applied."),
            operations=operations,
            risk_level=RiskLevel.NONE,
            data={
                "apply_id": result_dict.get("apply_id"),
                "plan_id": result_dict.get("plan_id"),
                "status": result_dict.get("status"),
                "success_count": result_dict.get("success_count", 0),
                "failure_count": result_dict.get("failure_count", 0),
                "output_path": result_dict.get("output_path"),
                "revision_note": result_dict.get("revision_note"),
            },
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

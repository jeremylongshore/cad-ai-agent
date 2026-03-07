"""Plan validator — enforces drawing constraints on structured edit plans.

Validates EditPlan actions against:
- protected layer rules
- unsupported entity/action combinations
- low-confidence targeting
- missing evidence/references
- repeated-condition batch approval requirements
- text trust issues (SQ67 provenance)
- ambiguity that should block or require confirmation
"""

from __future__ import annotations

import logging

from ..models.cad_schema import DrawingContext, EntityType
from ..models.config_schema import RuleConfig
from ..models.plan_schema import (
    ActionValidationDetail,
    ApprovalRequirement,
    EditAction,
    EditActionType,
    EditPlan,
    PlanValidationStatus,
)
from .entity_index import EntityIndex

logger = logging.getLogger(__name__)

_TEXT_TYPES = frozenset({EntityType.TEXT, EntityType.MTEXT})

# Actions that only make sense on specific entity types
_ACTION_ENTITY_CONSTRAINTS: dict[EditActionType, frozenset[EntityType] | None] = {
    EditActionType.EDIT_TEXT: _TEXT_TYPES,
    EditActionType.MOVE_ENTITY: None,  # any entity can be moved
    EditActionType.DELETE_ENTITY: None,  # any entity can be deleted
    EditActionType.ADD_BLOCK: None,  # no existing entity needed
    EditActionType.REPLICATE_NOTE: None,  # handled separately
}


class PlanValidator:
    """Validates edit plans against drawing constraints and rules.

    Does not modify the plan — returns validation results that can be
    applied by the caller.
    """

    def __init__(
        self,
        context: DrawingContext,
        rules: RuleConfig | None = None,
    ) -> None:
        self._context = context
        self._rules = rules or RuleConfig()
        self._index = EntityIndex(context)
        self._protected_upper = [layer.upper() for layer in self._rules.protected_layers]

    def validate(self, plan: EditPlan) -> EditPlan:
        """Validate all actions in a plan. Mutates and returns the plan.

        Sets validation status, blockers, and warnings on each action
        and on the plan itself.
        """
        plan_blockers: list[str] = []
        plan_warnings: list[str] = []

        for action in plan.actions:
            detail = self._validate_action(action)
            action.validation = detail

        # Aggregate plan-level status
        action_statuses = [a.validation.status for a in plan.actions]

        if PlanValidationStatus.BLOCKED in action_statuses:
            plan.validation_status = PlanValidationStatus.BLOCKED
            for a in plan.actions:
                plan_blockers.extend(a.validation.blockers)
        elif PlanValidationStatus.NEEDS_CLARIFICATION in action_statuses:
            plan.validation_status = PlanValidationStatus.NEEDS_CLARIFICATION
        elif PlanValidationStatus.VALID_WITH_WARNINGS in action_statuses:
            plan.validation_status = PlanValidationStatus.VALID_WITH_WARNINGS
        else:
            plan.validation_status = PlanValidationStatus.VALID

        # Check plan-level constraints
        self._check_plan_level(plan, plan_blockers, plan_warnings)

        plan.blocked_reasons.extend(plan_blockers)
        for w in plan_warnings:
            if w not in plan.ambiguity_flags:
                plan.ambiguity_flags.append(w)

        return plan

    def _validate_action(self, action: EditAction) -> ActionValidationDetail:
        """Validate a single action against drawing constraints."""
        detail = ActionValidationDetail()
        blockers: list[str] = []
        warnings: list[str] = []

        # ADD_BLOCK doesn't need existing entity validation
        if action.action_type == EditActionType.ADD_BLOCK:
            self._validate_add_block(action, blockers, warnings)
        elif action.action_type == EditActionType.REPLICATE_NOTE:
            self._validate_replicate(action, blockers, warnings)
        else:
            # All other actions need a target entity
            if not action.target_handle:
                blockers.append(f"{action.action_type.value} requires a target entity handle")
            else:
                entity = self._index.get_by_handle(action.target_handle)
                if entity is None:
                    blockers.append(f"Target entity not found: {action.target_handle}")
                else:
                    # Protected layer check
                    if entity.layer.upper() in self._protected_upper:
                        blockers.append(f"Cannot edit entity on protected layer: {entity.layer}")

                    # Entity/action compatibility
                    allowed_types = _ACTION_ENTITY_CONSTRAINTS.get(action.action_type)
                    if allowed_types is not None and entity.entity_type not in allowed_types:
                        blockers.append(
                            f"{action.action_type.value} not supported on "
                            f"{entity.entity_type.value} entities"
                        )

                    # Text trust check
                    if (
                        action.action_type == EditActionType.EDIT_TEXT
                        and entity.text_geometry
                        and entity.text_geometry.confidence_content < 0.5
                    ):
                        warnings.append(
                            f"Low text trust ({entity.text_geometry.confidence_content:.2f}) — "
                            "OCR-derived text may not match exact content"
                        )

                    # Move-specific validation
                    if action.action_type == EditActionType.MOVE_ENTITY:
                        self._validate_move_params(action, warnings)

                    # Edit text validation
                    if action.action_type == EditActionType.EDIT_TEXT:
                        self._validate_edit_text_params(action, blockers)

        # Low confidence check
        if action.confidence < 0.5:
            warnings.append(
                f"Low confidence ({action.confidence:.2f}) — result may not match intent"
            )

        # Missing evidence check
        if not action.evidence and action.action_type not in (
            EditActionType.ADD_BLOCK,
            EditActionType.REPLICATE_NOTE,
        ):
            warnings.append("No evidence references for this action")

        detail.blockers = blockers
        detail.warnings = warnings

        if blockers:
            detail.status = PlanValidationStatus.BLOCKED
        elif warnings:
            detail.status = PlanValidationStatus.VALID_WITH_WARNINGS
        else:
            detail.status = PlanValidationStatus.VALID

        return detail

    def _validate_move_params(self, action: EditAction, warnings: list[str]) -> None:
        """Validate move_entity params."""
        dx = action.params.get("dx")
        dy = action.params.get("dy")
        if dx is None or dy is None:
            warnings.append("Move displacement (dx, dy) not specified")
        elif dx == 0 and dy == 0:
            warnings.append("Zero displacement — entity won't move")

        if self._rules.max_move_distance is not None:
            import math

            if isinstance(dx, (int, float)) and isinstance(dy, (int, float)):
                dist = math.sqrt(dx**2 + dy**2)
                if dist > self._rules.max_move_distance:
                    warnings.append(
                        f"Move distance {dist:.1f} exceeds max {self._rules.max_move_distance}"
                    )

    def _validate_edit_text_params(self, action: EditAction, blockers: list[str]) -> None:
        """Validate edit_text params."""
        new_text = action.params.get("new_text")
        if new_text is None:
            blockers.append("edit_text requires new_text parameter")
        elif not isinstance(new_text, str):
            blockers.append("new_text must be a string")

    def _validate_add_block(
        self, action: EditAction, blockers: list[str], warnings: list[str]
    ) -> None:
        """Validate add_block action."""
        if not action.params.get("block_name") and not action.params.get("insert_point"):
            warnings.append("Block name and insert point not fully specified")

        target_layer = action.target_layer
        if target_layer and target_layer.upper() in self._protected_upper:
            blockers.append(f"Cannot insert on protected layer: {target_layer}")

    def _validate_replicate(
        self, action: EditAction, blockers: list[str], warnings: list[str]
    ) -> None:
        """Validate replicate_note action."""
        source = action.params.get("source_handles")
        target = action.params.get("target_centroid")
        if not source:
            blockers.append("Replicate requires source_handles")
        if not target:
            blockers.append("Replicate requires target_centroid")

    def _check_plan_level(
        self,
        plan: EditPlan,
        blockers: list[str],
        warnings: list[str],
    ) -> None:
        """Check plan-level constraints."""
        # Batch replication requires prior approval evidence
        replicate_actions = [
            a for a in plan.actions if a.action_type == EditActionType.REPLICATE_NOTE
        ]
        if replicate_actions:
            has_approval = any(
                req.category == "repeated_condition_approval" and req.satisfied
                for req in plan.approval_requirements
            )
            if not has_approval and not any(
                req.category == "batch_confirmation" for req in plan.approval_requirements
            ):
                plan.approval_requirements.append(
                    ApprovalRequirement(
                        description="Batch replication requires approval of target locations",
                        category="batch_confirmation",
                    )
                )

        # Too many actions warning
        if len(plan.actions) > 20:
            warnings.append(f"Large plan ({len(plan.actions)} actions) — review carefully")

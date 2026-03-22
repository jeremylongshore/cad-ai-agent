"""Edit preview builder — generates before/after previews from EditPlans.

Looks up entity state from the DrawingContext via EntityIndex and builds
a typed EditPreview with per-action before/after diffs.
"""

from __future__ import annotations

import time

from ..models.cad_schema import DrawingContext
from ..models.plan_schema import EditAction, EditActionType, EditPlan
from ..models.preview_schema import ActionPreview, EditPreview, PreviewStatus
from ..models.response_schema import RiskLevel


class EditPreviewBuilder:
    """Builds EditPreview objects from EditPlan + DrawingContext."""

    def __init__(self, context: DrawingContext) -> None:
        self._context = context
        self._index = context.index

    def build(self, plan: EditPlan) -> EditPreview:
        """Build a preview of what the plan will do."""
        start = time.monotonic()

        preview = EditPreview(
            plan_id=plan.plan_id,
            request_id=plan.request_id,
            requires_approval=plan.requires_approval,
            approval_requirements=[r.description for r in plan.approval_requirements],
        )

        # Early return for blocked/unclear plans
        if plan.is_blocked:
            preview.status = PreviewStatus.BLOCKED
            preview.summary = "Plan is blocked: " + "; ".join(plan.blocked_reasons)
            preview.warnings = list(plan.blocked_reasons)
            preview.preview_build_ms = (time.monotonic() - start) * 1000
            return preview

        if plan.needs_clarification:
            preview.status = PreviewStatus.NEEDS_CLARIFICATION
            preview.summary = plan.rationale or "Plan needs clarification."
            preview.warnings = list(plan.blocked_reasons)
            preview.preview_build_ms = (time.monotonic() - start) * 1000
            return preview

        # Build per-action previews
        action_previews: list[ActionPreview] = []
        for action in plan.actions:
            ap = self._build_action_preview(action)
            action_previews.append(ap)

        preview.actions = action_previews
        preview.total_actions = len(action_previews)
        preview.destructive_count = sum(1 for a in action_previews if a.is_destructive)
        preview.blocked_count = sum(1 for a in action_previews if a.validation_status == "blocked")

        # Aggregates
        if action_previews:
            preview.confidence = min(a.confidence for a in action_previews)
            risk_order = {
                RiskLevel.NONE: 0,
                RiskLevel.LOW: 1,
                RiskLevel.MEDIUM: 2,
                RiskLevel.HIGH: 3,
            }
            preview.risk_level = max(
                (a.risk_level for a in action_previews),
                key=lambda r: risk_order.get(r, 0),
            )

        # Collect warnings
        all_warnings: list[str] = []
        for ap in action_previews:
            all_warnings.extend(ap.warnings)
        preview.warnings = all_warnings

        # Summary
        preview.summary = self._build_summary(action_previews)

        preview.preview_build_ms = (time.monotonic() - start) * 1000
        return preview

    def _build_action_preview(self, action: EditAction) -> ActionPreview:
        """Build preview for a single action."""
        entity = None
        if action.target_handle:
            entity = self._index.get_by_handle(action.target_handle)

        before: dict = {}
        after: dict = {}
        is_destructive = False
        warnings: list[str] = []

        if action.action_type == EditActionType.MOVE_ENTITY:
            before, after = self._preview_move(action, entity)
        elif action.action_type == EditActionType.EDIT_TEXT:
            before, after = self._preview_edit_text(action, entity)
        elif action.action_type == EditActionType.DELETE_ENTITY:
            before, after, is_destructive = self._preview_delete(action, entity)
        elif action.action_type == EditActionType.ADD_BLOCK:
            before, after = self._preview_add_block(action)
        elif action.action_type == EditActionType.REPLICATE_NOTE:
            before, after = self._preview_replicate(action)

        if action.target_handle and entity is None:
            warnings.append(f"Entity {action.target_handle} not found in drawing")

        # Forward action-level warnings
        warnings.extend(action.validation.warnings)

        return ActionPreview(
            action_id=action.action_id,
            action_type=action.action_type.value,
            description=action.rationale,
            target_handle=action.target_handle,
            target_layer=action.target_layer or (entity.layer if entity else None),
            target_entity_type=action.target_entity_type
            or (entity.entity_type.value if entity else None),
            before_state=before,
            after_state=after,
            confidence=action.confidence,
            risk_level=action.risk_level,
            is_destructive=is_destructive,
            warnings=warnings,
            ambiguity=list(action.ambiguity),
            validation_status=action.validation.status.value,
            blockers=list(action.validation.blockers),
        )

    def _preview_move(self, action: EditAction, entity) -> tuple[dict, dict]:
        dx = action.params.get("dx", 0)
        dy = action.params.get("dy", 0)
        before: dict = {}
        after: dict = {}

        if entity and entity.insert_point:
            before = {"position": {"x": entity.insert_point.x, "y": entity.insert_point.y}}
            after = {
                "position": {
                    "x": entity.insert_point.x + dx,
                    "y": entity.insert_point.y + dy,
                },
                "delta": {"dx": dx, "dy": dy},
            }
        else:
            before = {"position": None}
            after = {"delta": {"dx": dx, "dy": dy}}

        return before, after

    def _preview_edit_text(self, action: EditAction, entity) -> tuple[dict, dict]:
        new_text = action.params.get("new_text", "")
        old_text = entity.text_content if entity else None
        before = {"text": old_text}
        after = {"text": new_text}
        return before, after

    def _preview_delete(self, action: EditAction, entity) -> tuple[dict, dict, bool]:
        before: dict = {}
        if entity:
            before = {
                "entity_type": entity.entity_type.value,
                "layer": entity.layer,
            }
            if entity.insert_point:
                before["position"] = {
                    "x": entity.insert_point.x,
                    "y": entity.insert_point.y,
                }
            if entity.text_content:
                before["text"] = entity.text_content
        return before, {}, True

    def _preview_add_block(self, action: EditAction) -> tuple[dict, dict]:
        block_name = action.params.get("block_name", "")
        insert_point = action.params.get("insert_point", {})
        after = {"block_name": block_name, "insert_point": insert_point}
        return {}, after

    def _preview_replicate(self, action: EditAction) -> tuple[dict, dict]:
        source_handles = action.params.get("source_handles", [])
        target_centroid = action.params.get("target_centroid", {})
        before = {"source_handles": source_handles}
        after = {"target_centroid": target_centroid}
        return before, after

    @staticmethod
    def _build_summary(previews: list[ActionPreview]) -> str:
        if not previews:
            return "No actions to preview."

        parts: list[str] = []
        type_counts: dict[str, int] = {}
        for p in previews:
            type_counts[p.action_type] = type_counts.get(p.action_type, 0) + 1

        for atype, count in type_counts.items():
            label = atype.replace("_", " ")
            parts.append(f"{count} {label}" if count > 1 else label)

        return ", ".join(parts).capitalize()

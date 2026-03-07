"""Edit plan builder — converts routed edit requests into structured plans.

Deterministic-first: parses user requests into bounded action plans using
pattern matching and drawing context. LLM is not called in this module.

Supported request types:
- move entity to position / by offset
- change text content
- delete entity / entities in region
- replicate note to approved target regions
- batch plan from approved repeated-condition matches

Unsupported requests return NEEDS_CLARIFICATION or BLOCKED plans.
"""

from __future__ import annotations

import logging
import re
import time
from dataclasses import dataclass

from ..core.text_utils import describe_entity, entity_to_evidence
from ..models.cad_schema import DrawingContext, EntityRef, EntityType
from ..models.plan_schema import (
    ApprovalRequirement,
    EditAction,
    EditActionType,
    EditPlan,
    PlanValidationStatus,
)
from ..models.region_schema import NormalizedRegion
from ..models.repeated_condition_schema import (
    ApprovalState,
    RepeatedConditionResult,
)
from ..models.response_schema import RiskLevel

logger = logging.getLogger(__name__)

_TEXT_TYPES = frozenset({EntityType.TEXT, EntityType.MTEXT})


@dataclass
class PlanRequest:
    """Input bundle for the plan builder."""

    prompt: str
    drawing_context: DrawingContext
    request_id: str = ""
    source_drawing: str | None = None
    selected_regions: list[NormalizedRegion] | None = None
    target_handles: list[str] | None = None
    repeated_condition_result: RepeatedConditionResult | None = None


class EditPlanBuilder:
    """Builds structured edit plans from user requests and drawing context.

    Uses deterministic parsing to convert supported requests into bounded
    action plans. Does not call the LLM — all planning is rule-based.
    """

    def build(self, request: PlanRequest) -> EditPlan:
        """Build an edit plan from a plan request.

        Routes to the appropriate action generator based on request analysis.
        """
        start = time.monotonic()

        plan = EditPlan(
            request_id=request.request_id,
            source_drawing=request.source_drawing,
            prompt=request.prompt,
        )

        if request.selected_regions:
            plan.selected_region_ids = [r.region_id for r in request.selected_regions]
        if request.target_handles:
            plan.entity_handles = list(request.target_handles)

        # Route to appropriate builder
        prompt_lower = request.prompt.lower().strip()

        if request.repeated_condition_result is not None:
            self._build_batch_plan(plan, request)
        elif self._is_delete_request(prompt_lower):
            self._build_delete_plan(plan, request)
        elif self._is_move_request(prompt_lower):
            self._build_move_plan(plan, request)
        elif self._is_text_edit_request(prompt_lower):
            self._build_text_edit_plan(plan, request)
        elif self._is_add_request(prompt_lower):
            self._build_add_plan(plan, request)
        else:
            self._build_unsupported_plan(plan, request)

        elapsed = (time.monotonic() - start) * 1000
        plan.latency.plan_build_ms = elapsed
        plan.latency.total_ms = elapsed

        # Compute aggregate confidence and risk
        self._compute_aggregates(plan)

        return plan

    # --- Request classification ---

    _MOVE_PATTERN = re.compile(r"\b(move|shift|relocate|reposition)\b", re.IGNORECASE)
    _DELETE_PATTERN = re.compile(r"\b(delete|remove|erase|clear)\b", re.IGNORECASE)
    _TEXT_EDIT_PATTERN = re.compile(
        r"\b(change\s+text|rename|update\s+text|edit\s+text|"
        r"replace\s+text|set\s+text|change\s+.*\s+to)\b",
        re.IGNORECASE,
    )
    _ADD_PATTERN = re.compile(r"\b(add|insert|place|create|replicate|copy\s+to)\b", re.IGNORECASE)

    def _is_move_request(self, prompt: str) -> bool:
        return bool(self._MOVE_PATTERN.search(prompt))

    def _is_delete_request(self, prompt: str) -> bool:
        return bool(self._DELETE_PATTERN.search(prompt))

    def _is_text_edit_request(self, prompt: str) -> bool:
        return bool(self._TEXT_EDIT_PATTERN.search(prompt))

    def _is_add_request(self, prompt: str) -> bool:
        return bool(self._ADD_PATTERN.search(prompt))

    # --- Plan builders ---

    def _build_move_plan(self, plan: EditPlan, request: PlanRequest) -> None:
        """Build a move plan for targeted entities."""
        targets = self._resolve_targets(request)
        if not targets:
            plan.validation_status = PlanValidationStatus.NEEDS_CLARIFICATION
            plan.blocked_reasons.append("No target entities identified for move")
            plan.ambiguity_flags.append("no_move_target")
            plan.rationale = "Could not identify which entity to move."
            return

        # Parse displacement from prompt
        dx, dy = self._parse_displacement(request.prompt)

        for entity in targets:
            action = EditAction(
                action_type=EditActionType.MOVE_ENTITY,
                target_handle=entity.handle,
                target_layer=entity.layer,
                target_entity_type=entity.entity_type.value,
                region_id=(
                    request.selected_regions[0].region_id if request.selected_regions else None
                ),
                params={"dx": dx, "dy": dy},
                evidence=[entity_to_evidence(entity)],
                rationale=f"Move {describe_entity(entity)} by ({dx}, {dy})",
                confidence=1.0 if (dx != 0 or dy != 0) else 0.5,
                risk_level=RiskLevel.LOW,
            )
            if dx == 0 and dy == 0:
                action.ambiguity.append("displacement_not_specified")
                action.confidence = 0.5
                plan.ambiguity_flags.append("displacement_not_specified")
            plan.actions.append(action)

        plan.rationale = f"Move {len(targets)} entity(ies)"
        plan.approval_requirements.append(
            ApprovalRequirement(
                description="Confirm move displacement and target entities",
                category="user_confirmation",
            )
        )

    def _build_delete_plan(self, plan: EditPlan, request: PlanRequest) -> None:
        """Build a delete plan for targeted entities."""
        targets = self._resolve_targets(request)
        if not targets:
            plan.validation_status = PlanValidationStatus.NEEDS_CLARIFICATION
            plan.blocked_reasons.append("No target entities identified for deletion")
            plan.ambiguity_flags.append("no_delete_target")
            plan.rationale = "Could not identify which entities to delete."
            return

        for entity in targets:
            action = EditAction(
                action_type=EditActionType.DELETE_ENTITY,
                target_handle=entity.handle,
                target_layer=entity.layer,
                target_entity_type=entity.entity_type.value,
                region_id=(
                    request.selected_regions[0].region_id if request.selected_regions else None
                ),
                params={},
                evidence=[entity_to_evidence(entity)],
                rationale=f"Delete {describe_entity(entity)}",
                confidence=1.0,
                risk_level=RiskLevel.MEDIUM,
            )
            plan.actions.append(action)

        plan.rationale = f"Delete {len(targets)} entity(ies)"
        plan.risk_level = RiskLevel.HIGH if len(targets) > 5 else RiskLevel.MEDIUM
        plan.approval_requirements.append(
            ApprovalRequirement(
                description=f"Confirm deletion of {len(targets)} entities",
                category="destructive_confirmation",
            )
        )

    def _build_text_edit_plan(self, plan: EditPlan, request: PlanRequest) -> None:
        """Build a text edit plan for TEXT/MTEXT entities."""
        targets = self._resolve_targets(request)
        text_targets = [t for t in targets if t.entity_type in _TEXT_TYPES]

        if not text_targets:
            if targets:
                plan.validation_status = PlanValidationStatus.BLOCKED
                plan.blocked_reasons.append("Target entities are not text (TEXT/MTEXT)")
                plan.rationale = "Cannot edit text on non-text entities."
            else:
                plan.validation_status = PlanValidationStatus.NEEDS_CLARIFICATION
                plan.blocked_reasons.append("No text entities identified")
                plan.ambiguity_flags.append("no_text_target")
                plan.rationale = "Could not identify which text to change."
            return

        new_text = self._parse_new_text(request.prompt)

        for entity in text_targets:
            confidence = 1.0
            ambiguity: list[str] = []

            # Text trust check: low-provenance text targeting is weaker
            if entity.text_geometry and entity.text_geometry.confidence_content < 0.5:
                confidence *= 0.6
                ambiguity.append("low_text_trust")

            action = EditAction(
                action_type=EditActionType.EDIT_TEXT,
                target_handle=entity.handle,
                target_layer=entity.layer,
                target_entity_type=entity.entity_type.value,
                params={"new_text": new_text} if new_text else {},
                evidence=[entity_to_evidence(entity)],
                rationale=(
                    f"Change text from '{entity.text_content or ''}' to '{new_text}'"
                    if new_text
                    else f"Edit text of {describe_entity(entity)}"
                ),
                confidence=confidence if new_text else 0.5,
                ambiguity=ambiguity,
                risk_level=RiskLevel.LOW,
            )
            if not new_text:
                action.ambiguity.append("new_text_not_specified")
                plan.ambiguity_flags.append("new_text_not_specified")
            plan.actions.append(action)

        plan.rationale = f"Edit text on {len(text_targets)} entity(ies)"
        plan.approval_requirements.append(
            ApprovalRequirement(
                description="Confirm text changes",
                category="user_confirmation",
            )
        )

    def _build_add_plan(self, plan: EditPlan, request: PlanRequest) -> None:
        """Build an add/replicate plan."""
        # Check if we have region context for placement
        if not request.selected_regions:
            plan.validation_status = PlanValidationStatus.NEEDS_CLARIFICATION
            plan.blocked_reasons.append("No target region specified for placement")
            plan.ambiguity_flags.append("no_placement_region")
            plan.rationale = "Specify a target region for placement."
            return

        region = request.selected_regions[0]

        action = EditAction(
            action_type=EditActionType.ADD_BLOCK,
            region_id=region.region_id,
            params={
                "insert_point": {"x": region.center.x, "y": region.center.y},
            },
            evidence=[],
            rationale=(
                f"Add element at region center ({region.center.x:.1f}, {region.center.y:.1f})"
            ),
            confidence=0.7,
            ambiguity=["block_name_not_specified"],
            risk_level=RiskLevel.LOW,
        )
        plan.actions.append(action)
        plan.ambiguity_flags.append("block_name_not_specified")
        plan.rationale = "Add element at specified region"
        plan.approval_requirements.append(
            ApprovalRequirement(
                description="Confirm block name and placement",
                category="user_confirmation",
            )
        )

    def _build_batch_plan(self, plan: EditPlan, request: PlanRequest) -> None:
        """Build a batch plan from approved repeated-condition matches."""
        rc_result = request.repeated_condition_result
        if rc_result is None:
            return

        approved = [c for c in rc_result.candidates if c.approval_state == ApprovalState.APPROVED]
        pending = [c for c in rc_result.candidates if c.approval_state == ApprovalState.PENDING]

        if not approved and pending:
            plan.validation_status = PlanValidationStatus.BLOCKED
            plan.blocked_reasons.append(
                f"{len(pending)} candidates pending approval — "
                "approve matches before generating batch plan"
            )
            plan.approval_requirements.append(
                ApprovalRequirement(
                    description="Approve repeated-condition matches before batch planning",
                    category="repeated_condition_approval",
                    satisfied=False,
                )
            )
            plan.rationale = "Batch plan requires approved matches."
            return

        if not approved:
            plan.validation_status = PlanValidationStatus.NEEDS_CLARIFICATION
            plan.blocked_reasons.append("No approved candidates for batch plan")
            plan.rationale = "No approved matches to act on."
            return

        for candidate in approved:
            action = EditAction(
                action_type=EditActionType.REPLICATE_NOTE,
                target_handle=(candidate.entity_handles[0] if candidate.entity_handles else None),
                params={
                    "source_handles": list(rc_result.exemplar_handles),
                    "target_centroid": {
                        "x": candidate.centroid.x,
                        "y": candidate.centroid.y,
                    },
                },
                evidence=list(candidate.evidence),
                rationale=(
                    f"Replicate from exemplar to match at "
                    f"({candidate.centroid.x:.1f}, {candidate.centroid.y:.1f})"
                ),
                confidence=candidate.confidence,
                risk_level=RiskLevel.LOW,
            )
            plan.actions.append(action)

        plan.rationale = (
            f"Batch replicate to {len(approved)} approved locations "
            f"from {len(rc_result.exemplar_handles)} exemplar entities"
        )
        plan.approval_requirements.append(
            ApprovalRequirement(
                description=f"Confirm batch replication to {len(approved)} locations",
                category="batch_confirmation",
            )
        )

    def _build_unsupported_plan(self, plan: EditPlan, request: PlanRequest) -> None:
        """Return a needs_clarification plan for unrecognized requests."""
        plan.validation_status = PlanValidationStatus.NEEDS_CLARIFICATION
        plan.blocked_reasons.append("Request does not map to a supported edit action")
        plan.ambiguity_flags.append("unsupported_edit_request")
        plan.rationale = (
            "Could not map this request to a supported edit action. "
            "Supported actions: move, delete, change text, add block, "
            "replicate note to approved regions."
        )

    # --- Helpers ---

    def _resolve_targets(self, request: PlanRequest) -> list[EntityRef]:
        """Resolve target entities from handles or region context."""
        entities: list[EntityRef] = []

        # Direct handle references take priority
        if request.target_handles:
            handle_set = set(request.target_handles)
            for entity in request.drawing_context.entities:
                if entity.handle in handle_set:
                    entities.append(entity)
            return entities

        # Fall back to entities in selected regions
        if request.selected_regions:
            for region in request.selected_regions:
                for entity in request.drawing_context.entities:
                    if entity.insert_point and region.contains_point(entity.insert_point):
                        entities.append(entity)
            return entities

        return entities

    @staticmethod
    def _parse_displacement(prompt: str) -> tuple[float, float]:
        """Try to extract dx, dy from a prompt string.

        Patterns: "by (10, 20)", "10 units right", "move up 5", etc.
        Returns (0, 0) if no displacement is found.
        """
        # Pattern: (dx, dy) or dx,dy
        m = re.search(r"\(?\s*(-?\d+\.?\d*)\s*,\s*(-?\d+\.?\d*)\s*\)?", prompt)
        if m:
            return float(m.group(1)), float(m.group(2))

        # Pattern: N units direction
        m = re.search(
            r"(-?\d+\.?\d*)\s*(?:units?\s+)?(right|left|up|down)",
            prompt,
            re.IGNORECASE,
        )
        if m:
            val = float(m.group(1))
            direction = m.group(2).lower()
            dx = val if direction == "right" else (-val if direction == "left" else 0)
            dy = val if direction == "up" else (-val if direction == "down" else 0)
            return dx, dy

        # Pattern: direction N
        m = re.search(
            r"(right|left|up|down)\s+(-?\d+\.?\d*)",
            prompt,
            re.IGNORECASE,
        )
        if m:
            direction = m.group(1).lower()
            val = float(m.group(2))
            dx = val if direction == "right" else (-val if direction == "left" else 0)
            dy = val if direction == "up" else (-val if direction == "down" else 0)
            return dx, dy

        return 0.0, 0.0

    @staticmethod
    def _parse_new_text(prompt: str) -> str | None:
        """Try to extract new text value from a prompt.

        Patterns: 'to "new value"', "to 'new value'", "change X to Y"
        """
        # Quoted text after "to"
        m = re.search(r'\bto\s+["\']([^"\']+)["\']', prompt)
        if m:
            return m.group(1)

        # Unquoted: "change ... to WORD" at end
        m = re.search(r"\bto\s+(\S+)\s*$", prompt)
        if m:
            return m.group(1)

        return None

    @staticmethod
    def _compute_aggregates(plan: EditPlan) -> None:
        """Compute plan-level confidence, risk, and validation from actions."""
        if not plan.actions:
            return

        # Confidence: minimum across actions
        confidences = [a.confidence for a in plan.actions]
        plan.confidence = min(confidences) if confidences else 1.0

        # Risk: maximum across actions
        risk_order = {
            RiskLevel.NONE: 0,
            RiskLevel.LOW: 1,
            RiskLevel.MEDIUM: 2,
            RiskLevel.HIGH: 3,
        }
        max_risk = max(plan.actions, key=lambda a: risk_order.get(a.risk_level, 0))
        plan.risk_level = max_risk.risk_level

        # Override if many deletes
        delete_count = sum(1 for a in plan.actions if a.action_type == EditActionType.DELETE_ENTITY)
        if delete_count > 5 or len(plan.actions) > 20:
            plan.risk_level = RiskLevel.HIGH

        # Collect ambiguity from actions
        for action in plan.actions:
            for flag in action.ambiguity:
                if flag not in plan.ambiguity_flags:
                    plan.ambiguity_flags.append(flag)

        # Validation status: worst action status wins
        statuses = [a.validation.status for a in plan.actions]
        if PlanValidationStatus.BLOCKED in statuses:
            plan.validation_status = PlanValidationStatus.BLOCKED
        elif PlanValidationStatus.NEEDS_CLARIFICATION in statuses:
            plan.validation_status = PlanValidationStatus.NEEDS_CLARIFICATION
        elif PlanValidationStatus.VALID_WITH_WARNINGS in statuses:
            plan.validation_status = PlanValidationStatus.VALID_WITH_WARNINGS

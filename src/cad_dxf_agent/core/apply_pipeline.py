"""Apply pipeline — applies validated EditPlans to DXF files.

Bridges the EPIC-07 EditPlan into the existing EditEngine via the
plan_to_changeset converter. Handles approval checking, application,
saving, and revision note insertion.
"""

from __future__ import annotations

import logging
import time
from pathlib import Path

from ..models.apply_schema import ActionResult, ApplyResult, ApplyStatus, ApprovalDecision
from ..models.cad_schema import DrawingContext
from ..models.config_schema import RevisionNoteConfig, RuleConfig
from ..models.plan_schema import EditPlan
from .edit_engine import EditEngine
from .plan_converter import plan_to_changeset

logger = logging.getLogger(__name__)


class ApplyPipeline:
    """Applies an EditPlan to a DXF file via the legacy EditEngine."""

    def __init__(
        self,
        context: DrawingContext,
        rules: RuleConfig | None = None,
    ) -> None:
        self._context = context
        self._rules = rules or RuleConfig()

    def apply(
        self,
        plan: EditPlan,
        dxf_path: str | Path,
        output_path: str | Path,
        *,
        approval: ApprovalDecision | None = None,
        revision_config: RevisionNoteConfig | None = None,
    ) -> ApplyResult:
        """Apply an edit plan to a DXF file.

        Steps:
        1. Check preconditions (blocked/needs_clarification)
        2. Check approval if required
        3. Convert plan → changeset
        4. Apply via EditEngine
        5. Save output
        6. Insert revision notes (if enabled)
        7. Build and return ApplyResult
        """
        total_start = time.monotonic()
        result = ApplyResult(
            plan_id=plan.plan_id,
            request_id=plan.request_id,
        )

        # 1. Check preconditions
        if plan.is_blocked:
            result.status = ApplyStatus.REJECTED
            result.summary = "Plan is blocked: " + "; ".join(plan.blocked_reasons)
            result.total_ms = (time.monotonic() - total_start) * 1000
            return result

        if plan.needs_clarification:
            result.status = ApplyStatus.REJECTED
            result.summary = "Plan needs clarification before applying."
            result.total_ms = (time.monotonic() - total_start) * 1000
            return result

        # 2. Check approval
        if plan.requires_approval and (approval is None or not approval.approved):
            result.status = ApplyStatus.REJECTED
            result.summary = "Plan requires approval before applying."
            result.total_ms = (time.monotonic() - total_start) * 1000
            return result

        # 3. Convert plan → changeset
        changeset, action_index_map = plan_to_changeset(plan, self._context)

        if not changeset.operations:
            result.status = ApplyStatus.FAILED
            result.summary = "No operations to apply."
            result.total_ms = (time.monotonic() - total_start) * 1000
            return result

        # 4. Apply via EditEngine
        apply_start = time.monotonic()
        try:
            engine = EditEngine(dxf_path)
            applied_changes = engine.apply_changeset(changeset)
        except Exception as e:
            logger.error("EditEngine failed: %s", e, exc_info=True)
            result.status = ApplyStatus.FAILED
            result.summary = f"Apply failed: {e}"
            result.total_ms = (time.monotonic() - total_start) * 1000
            return result
        result.apply_ms = (time.monotonic() - apply_start) * 1000

        # 5. Save output
        save_start = time.monotonic()
        try:
            saved_path = engine.save(output_path)
            result.output_path = str(saved_path)
        except Exception as e:
            logger.error("Save failed: %s", e, exc_info=True)
            result.status = ApplyStatus.FAILED
            result.summary = f"Save failed: {e}"
            result.total_ms = (time.monotonic() - total_start) * 1000
            return result
        result.save_ms = (time.monotonic() - save_start) * 1000

        # 6. Insert revision notes
        if revision_config and revision_config.enabled:
            try:
                from .revision_notes import insert_revision_note

                note_text = insert_revision_note(
                    dxf_path=output_path,
                    output_path=output_path,
                    changes=applied_changes,
                    config=revision_config,
                )
                result.revision_note = note_text
            except Exception as e:
                logger.warning("Revision note insertion failed: %s", e)
                result.warnings.append(f"Revision note failed: {e}")

        # 7. Build action results
        action_results: list[ActionResult] = []
        success_count = 0
        failure_count = 0

        for op_idx, applied in enumerate(applied_changes):
            action_idx = action_index_map.get(op_idx)
            action = plan.actions[action_idx] if action_idx is not None else None
            ar = ActionResult(
                action_id=action.action_id if action else f"op-{op_idx}",
                action_type=action.action_type.value if action else applied.operation.op_type.value,
                success=applied.success,
                entity_handle=applied.entity_handle,
                description=applied.description,
                error=None if applied.success else applied.description,
            )
            action_results.append(ar)
            if applied.success:
                success_count += 1
            else:
                failure_count += 1

        result.action_results = action_results
        result.success_count = success_count
        result.failure_count = failure_count

        # Determine status
        if failure_count == 0:
            result.status = ApplyStatus.SUCCESS
        elif success_count > 0:
            result.status = ApplyStatus.PARTIAL
        else:
            result.status = ApplyStatus.FAILED

        result.summary = f"Applied {success_count}/{success_count + failure_count} operations."
        result.total_ms = (time.monotonic() - total_start) * 1000

        return result

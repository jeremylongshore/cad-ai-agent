"""Tests for ApplyPipeline — applies EditPlans to DXF files (EPIC-CAD-08).

Covers SUCCESS/PARTIAL/FAILED/REJECTED status paths, approval gating,
timing metadata, save-as safety, revision notes, and multi-action plans.
"""

from __future__ import annotations

from cad_dxf_agent.core.apply_pipeline import ApplyPipeline
from cad_dxf_agent.models.apply_schema import ApplyStatus, ApprovalDecision
from cad_dxf_agent.models.config_schema import RevisionNoteConfig
from cad_dxf_agent.models.plan_schema import (
    EditAction,
    EditActionType,
    EditPlan,
    PlanValidationStatus,
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _find_handle(context, *, entity_type: str | None = None, layer: str | None = None) -> str:
    """Return the handle of the first matching entity."""
    for entity in context.entities:
        if entity_type and entity.entity_type.value != entity_type:
            continue
        if layer and entity.layer != layer:
            continue
        return entity.handle
    raise ValueError(f"No entity found: type={entity_type!r}, layer={layer!r}")


def _find_text_handle(context, text: str) -> str:
    """Return the handle of the first TEXT/MTEXT entity with matching content."""
    for entity in context.entities:
        if entity.text_content and text in entity.text_content:
            return entity.handle
    raise ValueError(f"No text entity found containing: {text!r}")


def _move_plan(handle: str, *, requires_approval: bool = False) -> EditPlan:
    """Build a minimal move plan targeting the given handle."""
    return EditPlan(
        prompt="move entity",
        requires_approval=requires_approval,
        actions=[
            EditAction(
                action_type=EditActionType.MOVE_ENTITY,
                target_handle=handle,
                params={"dx": 5.0, "dy": 0.0},
            )
        ],
    )


def _edit_text_plan(handle: str, new_text: str, *, requires_approval: bool = False) -> EditPlan:
    """Build a minimal edit_text plan targeting the given handle."""
    return EditPlan(
        prompt="edit text",
        requires_approval=requires_approval,
        actions=[
            EditAction(
                action_type=EditActionType.EDIT_TEXT,
                target_handle=handle,
                params={"new_text": new_text},
            )
        ],
    )


# ---------------------------------------------------------------------------
# Test 1: valid move plan → SUCCESS, output file created
# ---------------------------------------------------------------------------


def test_move_plan_succeeds_and_creates_output(sample_dxf, sample_context, tmp_path):
    handle = _find_handle(sample_context, entity_type="LINE", layer="STRUCTURAL")
    plan = _move_plan(handle)
    output = tmp_path / "out.dxf"

    result = ApplyPipeline(sample_context).apply(plan, sample_dxf, output)

    assert result.status == ApplyStatus.SUCCESS
    assert output.exists()
    assert result.output_path == str(output)


# ---------------------------------------------------------------------------
# Test 2: valid edit_text plan → SUCCESS
# ---------------------------------------------------------------------------


def test_edit_text_plan_succeeds(sample_dxf, sample_context, tmp_path):
    handle = _find_text_handle(sample_context, "Column C-4")
    plan = _edit_text_plan(handle, "Column C-5")
    output = tmp_path / "out.dxf"

    result = ApplyPipeline(sample_context).apply(plan, sample_dxf, output)

    assert result.status == ApplyStatus.SUCCESS
    assert result.success_count == 1
    assert result.failure_count == 0


# ---------------------------------------------------------------------------
# Test 3: blocked plan → REJECTED, no output file created
# ---------------------------------------------------------------------------


def test_blocked_plan_is_rejected(sample_dxf, sample_context, tmp_path):
    handle = _find_handle(sample_context, entity_type="LINE", layer="STRUCTURAL")
    plan = EditPlan(
        prompt="blocked",
        requires_approval=False,
        validation_status=PlanValidationStatus.BLOCKED,
        blocked_reasons=["Protected layer constraint violation"],
        actions=[
            EditAction(
                action_type=EditActionType.MOVE_ENTITY,
                target_handle=handle,
                params={"dx": 1.0, "dy": 0.0},
            )
        ],
    )
    output = tmp_path / "out.dxf"

    result = ApplyPipeline(sample_context).apply(plan, sample_dxf, output)

    assert result.status == ApplyStatus.REJECTED
    assert not output.exists()
    assert "blocked" in result.summary.lower()


# ---------------------------------------------------------------------------
# Test 4: needs_clarification plan → REJECTED
# ---------------------------------------------------------------------------


def test_needs_clarification_plan_is_rejected(sample_dxf, sample_context, tmp_path):
    handle = _find_handle(sample_context, entity_type="LINE", layer="STRUCTURAL")
    plan = EditPlan(
        prompt="unclear request",
        requires_approval=False,
        validation_status=PlanValidationStatus.NEEDS_CLARIFICATION,
        actions=[
            EditAction(
                action_type=EditActionType.MOVE_ENTITY,
                target_handle=handle,
                params={"dx": 1.0, "dy": 0.0},
            )
        ],
    )
    output = tmp_path / "out.dxf"

    result = ApplyPipeline(sample_context).apply(plan, sample_dxf, output)

    assert result.status == ApplyStatus.REJECTED
    assert not output.exists()
    assert "clarification" in result.summary.lower()


# ---------------------------------------------------------------------------
# Test 5: requires_approval=True with no ApprovalDecision → REJECTED
# ---------------------------------------------------------------------------


def test_requires_approval_without_decision_is_rejected(sample_dxf, sample_context, tmp_path):
    handle = _find_handle(sample_context, entity_type="LINE", layer="STRUCTURAL")
    plan = _move_plan(handle, requires_approval=True)
    output = tmp_path / "out.dxf"

    result = ApplyPipeline(sample_context).apply(plan, sample_dxf, output, approval=None)

    assert result.status == ApplyStatus.REJECTED
    assert not output.exists()
    assert "approval" in result.summary.lower()


# ---------------------------------------------------------------------------
# Test 6: approval granted → SUCCESS
# ---------------------------------------------------------------------------


def test_approval_granted_allows_apply(sample_dxf, sample_context, tmp_path):
    handle = _find_handle(sample_context, entity_type="LINE", layer="STRUCTURAL")
    plan = _move_plan(handle, requires_approval=True)
    approval = ApprovalDecision(
        plan_id=plan.plan_id,
        approved=True,
        approved_by="engineer@example.com",
        notes="Reviewed and approved",
    )
    output = tmp_path / "out.dxf"

    result = ApplyPipeline(sample_context).apply(plan, sample_dxf, output, approval=approval)

    assert result.status == ApplyStatus.SUCCESS
    assert output.exists()


# ---------------------------------------------------------------------------
# Test 7: ApprovalDecision with approved=False → REJECTED
# ---------------------------------------------------------------------------


def test_approval_rejected_blocks_apply(sample_dxf, sample_context, tmp_path):
    handle = _find_handle(sample_context, entity_type="LINE", layer="STRUCTURAL")
    plan = _move_plan(handle, requires_approval=True)
    approval = ApprovalDecision(
        plan_id=plan.plan_id,
        approved=False,
        approved_by="reviewer@example.com",
        notes="Too broad — needs scoping",
    )
    output = tmp_path / "out.dxf"

    result = ApplyPipeline(sample_context).apply(plan, sample_dxf, output, approval=approval)

    assert result.status == ApplyStatus.REJECTED
    assert not output.exists()


# ---------------------------------------------------------------------------
# Test 8: timing metadata is populated on SUCCESS
# ---------------------------------------------------------------------------


def test_timing_metadata_populated_on_success(sample_dxf, sample_context, tmp_path):
    handle = _find_handle(sample_context, entity_type="LINE", layer="STRUCTURAL")
    plan = _move_plan(handle)
    output = tmp_path / "out.dxf"

    result = ApplyPipeline(sample_context).apply(plan, sample_dxf, output)

    assert result.total_ms is not None
    assert result.total_ms > 0
    assert result.apply_ms is not None
    assert result.apply_ms > 0
    assert result.save_ms is not None
    assert result.save_ms > 0


# ---------------------------------------------------------------------------
# Test 9: original file is unchanged after save-as (apply never mutates source)
# ---------------------------------------------------------------------------


def test_original_file_unchanged_after_apply(sample_dxf, sample_context, tmp_path):
    handle = _find_handle(sample_context, entity_type="LINE", layer="STRUCTURAL")
    plan = _move_plan(handle)
    output = tmp_path / "out.dxf"

    original_bytes = sample_dxf.read_bytes()
    ApplyPipeline(sample_context).apply(plan, sample_dxf, output)

    assert sample_dxf.read_bytes() == original_bytes, (
        "Source DXF was modified — ApplyPipeline must use save-as, never overwrite the original"
    )


# ---------------------------------------------------------------------------
# Test 10: success_count and failure_count are correct on SUCCESS
# ---------------------------------------------------------------------------


def test_success_and_failure_counts_on_success(sample_dxf, sample_context, tmp_path):
    handle = _find_handle(sample_context, entity_type="LINE", layer="STRUCTURAL")
    plan = _move_plan(handle)
    output = tmp_path / "out.dxf"

    result = ApplyPipeline(sample_context).apply(plan, sample_dxf, output)

    assert result.success_count == 1
    assert result.failure_count == 0
    assert len(result.action_results) == 1
    assert result.action_results[0].success is True


# ---------------------------------------------------------------------------
# Test 11: apply result carries the plan_id from the plan
# ---------------------------------------------------------------------------


def test_apply_result_carries_plan_id(sample_dxf, sample_context, tmp_path):
    handle = _find_handle(sample_context, entity_type="LINE", layer="STRUCTURAL")
    plan = _move_plan(handle)
    output = tmp_path / "out.dxf"

    result = ApplyPipeline(sample_context).apply(plan, sample_dxf, output)

    assert result.plan_id == plan.plan_id


# ---------------------------------------------------------------------------
# Test 12: empty plan (no actions) → FAILED
# ---------------------------------------------------------------------------


def test_empty_plan_fails(sample_dxf, sample_context, tmp_path):
    plan = EditPlan(
        prompt="nothing to do",
        requires_approval=False,
        actions=[],
    )
    output = tmp_path / "out.dxf"

    result = ApplyPipeline(sample_context).apply(plan, sample_dxf, output)

    assert result.status == ApplyStatus.FAILED
    assert not output.exists()
    assert "no operations" in result.summary.lower()


# ---------------------------------------------------------------------------
# Test 13: requires_approval=False needs no approval object
# ---------------------------------------------------------------------------


def test_no_approval_needed_when_flag_is_false(sample_dxf, sample_context, tmp_path):
    handle = _find_handle(sample_context, entity_type="LINE", layer="STRUCTURAL")
    plan = _move_plan(handle, requires_approval=False)
    output = tmp_path / "out.dxf"

    # Explicitly pass no approval object — should not be rejected
    result = ApplyPipeline(sample_context).apply(plan, sample_dxf, output, approval=None)

    assert result.status == ApplyStatus.SUCCESS


# ---------------------------------------------------------------------------
# Test 14: revision notes are generated when RevisionNoteConfig is provided
# ---------------------------------------------------------------------------


def test_revision_notes_generated_when_config_provided(sample_dxf, sample_context, tmp_path):
    handle = _find_handle(sample_context, entity_type="LINE", layer="STRUCTURAL")
    plan = _move_plan(handle)
    revision_config = RevisionNoteConfig(enabled=True)
    output = tmp_path / "out.dxf"

    result = ApplyPipeline(sample_context).apply(
        plan, sample_dxf, output, revision_config=revision_config
    )

    assert result.status == ApplyStatus.SUCCESS
    # Revision note text should be set (may be empty string if no text was generated,
    # but the field should not be None on a successful apply with config enabled)
    assert result.revision_note is not None


# ---------------------------------------------------------------------------
# Test 15: multiple actions in one plan → all applied, counts match
# ---------------------------------------------------------------------------


def test_multiple_actions_all_applied(sample_dxf, sample_context, tmp_path):
    line_handle = _find_handle(sample_context, entity_type="LINE", layer="STRUCTURAL")
    text_handle = _find_text_handle(sample_context, "Column C-4")
    mtext_handle = _find_text_handle(sample_context, "Footing detail note")

    plan = EditPlan(
        prompt="batch edit",
        requires_approval=False,
        actions=[
            EditAction(
                action_type=EditActionType.MOVE_ENTITY,
                target_handle=line_handle,
                params={"dx": 10.0, "dy": 5.0},
            ),
            EditAction(
                action_type=EditActionType.EDIT_TEXT,
                target_handle=text_handle,
                params={"new_text": "Column C-99"},
            ),
            EditAction(
                action_type=EditActionType.EDIT_TEXT,
                target_handle=mtext_handle,
                params={"new_text": "Updated footing note"},
            ),
        ],
    )
    output = tmp_path / "out.dxf"

    result = ApplyPipeline(sample_context).apply(plan, sample_dxf, output)

    assert result.status == ApplyStatus.SUCCESS
    assert result.success_count == 3
    assert result.failure_count == 0
    assert len(result.action_results) == 3
    assert all(ar.success for ar in result.action_results)
    assert output.exists()

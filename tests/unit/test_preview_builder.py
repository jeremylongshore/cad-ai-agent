"""Tests for EditPreviewBuilder (EPIC-CAD-08).

Covers before/after state generation for every action type, aggregate
confidence/risk, warning forwarding, blocked/clarification short-circuits,
and build-timing metadata.
"""

from __future__ import annotations

import pytest

from cad_dxf_agent.core.preview_builder import EditPreviewBuilder
from cad_dxf_agent.models.cad_schema import DrawingContext, EntityRef, EntityType, Point2D
from cad_dxf_agent.models.plan_schema import (
    ActionValidationDetail,
    ApprovalRequirement,
    EditAction,
    EditActionType,
    EditPlan,
    PlanValidationStatus,
)
from cad_dxf_agent.models.preview_schema import PreviewStatus
from cad_dxf_agent.models.response_schema import RiskLevel

# ---------------------------------------------------------------------------
# Fixtures / helpers
# ---------------------------------------------------------------------------


def make_context() -> DrawingContext:
    """DrawingContext with three entities covering the main entity types."""
    return DrawingContext(
        file_path="test.dxf",
        entities=[
            EntityRef(
                handle="A1",
                entity_type=EntityType.LINE,
                layer="STRUCTURAL",
                insert_point=Point2D(x=10.0, y=20.0),
            ),
            EntityRef(
                handle="B1",
                entity_type=EntityType.TEXT,
                layer="NOTES",
                insert_point=Point2D(x=30.0, y=40.0),
                text_content="Old Label",
            ),
            EntityRef(
                handle="C1",
                entity_type=EntityType.INSERT,
                layer="STRUCTURAL",
                insert_point=Point2D(x=50.0, y=60.0),
                block_name="COLUMN_MARK",
            ),
        ],
    )


def make_plan(**kwargs) -> EditPlan:
    """EditPlan factory with sane defaults."""
    return EditPlan(
        actions=kwargs.pop("actions", []),
        **kwargs,
    )


def move_action(
    handle: str = "A1",
    dx: float = 5.0,
    dy: float = 3.0,
    confidence: float = 1.0,
    risk_level: RiskLevel = RiskLevel.LOW,
    validation: ActionValidationDetail | None = None,
    ambiguity: list[str] | None = None,
) -> EditAction:
    return EditAction(
        action_type=EditActionType.MOVE_ENTITY,
        target_handle=handle,
        params={"dx": dx, "dy": dy},
        confidence=confidence,
        risk_level=risk_level,
        validation=validation or ActionValidationDetail(),
        ambiguity=ambiguity or [],
    )


def edit_text_action(
    handle: str = "B1",
    new_text: str = "New Label",
    confidence: float = 1.0,
    risk_level: RiskLevel = RiskLevel.LOW,
    validation: ActionValidationDetail | None = None,
) -> EditAction:
    return EditAction(
        action_type=EditActionType.EDIT_TEXT,
        target_handle=handle,
        params={"new_text": new_text},
        confidence=confidence,
        risk_level=risk_level,
        validation=validation or ActionValidationDetail(),
    )


def delete_action(
    handle: str = "A1",
    risk_level: RiskLevel = RiskLevel.HIGH,
    validation: ActionValidationDetail | None = None,
) -> EditAction:
    return EditAction(
        action_type=EditActionType.DELETE_ENTITY,
        target_handle=handle,
        risk_level=risk_level,
        validation=validation or ActionValidationDetail(),
    )


def add_block_action(
    block_name: str = "BEAM_MARK",
    insert_point: dict | None = None,
    confidence: float = 1.0,
    risk_level: RiskLevel = RiskLevel.LOW,
) -> EditAction:
    return EditAction(
        action_type=EditActionType.ADD_BLOCK,
        params={
            "block_name": block_name,
            "insert_point": insert_point or {"x": 100.0, "y": 200.0},
        },
        confidence=confidence,
        risk_level=risk_level,
        validation=ActionValidationDetail(),
    )


def replicate_action(
    source_handles: list[str] | None = None,
    target_centroid: dict | None = None,
    confidence: float = 0.9,
) -> EditAction:
    return EditAction(
        action_type=EditActionType.REPLICATE_NOTE,
        params={
            "source_handles": source_handles or ["B1", "C1"],
            "target_centroid": target_centroid or {"x": 150.0, "y": 250.0},
        },
        confidence=confidence,
        validation=ActionValidationDetail(),
    )


# ---------------------------------------------------------------------------
# Test 1 — Move: correct before/after positions
# ---------------------------------------------------------------------------


def test_move_before_after_positions() -> None:
    ctx = make_context()
    plan = make_plan(actions=[move_action(handle="A1", dx=5.0, dy=3.0)])
    preview = EditPreviewBuilder(ctx).build(plan)

    ap = preview.actions[0]
    assert ap.before_state == {"position": {"x": 10.0, "y": 20.0}}
    assert ap.after_state == {
        "position": {"x": 15.0, "y": 23.0},
        "delta": {"dx": 5.0, "dy": 3.0},
    }


# ---------------------------------------------------------------------------
# Test 2 — Edit text: before has old text, after has new text
# ---------------------------------------------------------------------------


def test_edit_text_before_after() -> None:
    ctx = make_context()
    plan = make_plan(actions=[edit_text_action(handle="B1", new_text="Updated Label")])
    preview = EditPreviewBuilder(ctx).build(plan)

    ap = preview.actions[0]
    assert ap.before_state == {"text": "Old Label"}
    assert ap.after_state == {"text": "Updated Label"}


# ---------------------------------------------------------------------------
# Test 3 — Delete: is_destructive=True and empty after_state
# ---------------------------------------------------------------------------


def test_delete_is_destructive_with_empty_after() -> None:
    ctx = make_context()
    plan = make_plan(actions=[delete_action(handle="A1")])
    preview = EditPreviewBuilder(ctx).build(plan)

    ap = preview.actions[0]
    assert ap.is_destructive is True
    assert ap.after_state == {}


# ---------------------------------------------------------------------------
# Test 4 — Add block: after_state has block_name and insert_point
# ---------------------------------------------------------------------------


def test_add_block_after_state() -> None:
    ctx = make_context()
    action = add_block_action(block_name="BEAM_MARK", insert_point={"x": 100.0, "y": 200.0})
    plan = make_plan(actions=[action])
    preview = EditPreviewBuilder(ctx).build(plan)

    ap = preview.actions[0]
    assert ap.before_state == {}
    assert ap.after_state["block_name"] == "BEAM_MARK"
    assert ap.after_state["insert_point"] == {"x": 100.0, "y": 200.0}


# ---------------------------------------------------------------------------
# Test 5 — Replicate note: before has source_handles, after has target_centroid
# ---------------------------------------------------------------------------


def test_replicate_note_before_after() -> None:
    ctx = make_context()
    plan = make_plan(
        actions=[
            replicate_action(
                source_handles=["B1", "C1"],
                target_centroid={"x": 150.0, "y": 250.0},
            )
        ]
    )
    preview = EditPreviewBuilder(ctx).build(plan)

    ap = preview.actions[0]
    assert ap.before_state == {"source_handles": ["B1", "C1"]}
    assert ap.after_state == {"target_centroid": {"x": 150.0, "y": 250.0}}


# ---------------------------------------------------------------------------
# Test 6 — Blocked plan yields BLOCKED status
# ---------------------------------------------------------------------------


def test_blocked_plan_returns_blocked_status() -> None:
    ctx = make_context()
    plan = make_plan(
        validation_status=PlanValidationStatus.BLOCKED,
        blocked_reasons=["Protected layer: SEAL", "Entity not found"],
        actions=[],
    )
    preview = EditPreviewBuilder(ctx).build(plan)

    assert preview.status == PreviewStatus.BLOCKED
    assert "Protected layer: SEAL" in preview.summary
    assert "Entity not found" in preview.warnings


# ---------------------------------------------------------------------------
# Test 7 — Needs-clarification plan yields NEEDS_CLARIFICATION status
# ---------------------------------------------------------------------------


def test_needs_clarification_plan_returns_correct_status() -> None:
    ctx = make_context()
    plan = make_plan(
        validation_status=PlanValidationStatus.NEEDS_CLARIFICATION,
        rationale="Which entity should be moved?",
        actions=[],
    )
    preview = EditPreviewBuilder(ctx).build(plan)

    assert preview.status == PreviewStatus.NEEDS_CLARIFICATION
    assert "Which entity should be moved?" in preview.summary


# ---------------------------------------------------------------------------
# Test 8 — Empty plan yields no actions and correct summary
# ---------------------------------------------------------------------------


def test_empty_plan_summary() -> None:
    ctx = make_context()
    plan = make_plan(actions=[])
    preview = EditPreviewBuilder(ctx).build(plan)

    assert preview.actions == []
    assert preview.total_actions == 0
    assert preview.summary == "No actions to preview."


# ---------------------------------------------------------------------------
# Test 9 — Missing entity surfaces a warning
# ---------------------------------------------------------------------------


def test_missing_entity_surfaces_warning() -> None:
    ctx = make_context()
    plan = make_plan(actions=[move_action(handle="GHOST")])
    preview = EditPreviewBuilder(ctx).build(plan)

    combined_warnings = preview.warnings
    assert any("GHOST" in w and "not found" in w for w in combined_warnings)


# ---------------------------------------------------------------------------
# Test 10 — Confidence is minimum across all actions
# ---------------------------------------------------------------------------


def test_confidence_is_minimum_across_actions() -> None:
    ctx = make_context()
    plan = make_plan(
        actions=[
            move_action(handle="A1", confidence=0.9),
            edit_text_action(handle="B1", confidence=0.6),
            delete_action(handle="C1"),  # default confidence=1.0
        ]
    )
    preview = EditPreviewBuilder(ctx).build(plan)

    assert preview.confidence == pytest.approx(0.6)


# ---------------------------------------------------------------------------
# Test 11 — Risk level is maximum across all actions
# ---------------------------------------------------------------------------


def test_risk_level_is_maximum_across_actions() -> None:
    ctx = make_context()
    plan = make_plan(
        actions=[
            move_action(handle="A1", risk_level=RiskLevel.LOW),
            edit_text_action(handle="B1", risk_level=RiskLevel.MEDIUM),
        ]
    )
    preview = EditPreviewBuilder(ctx).build(plan)

    assert preview.risk_level == RiskLevel.MEDIUM


# ---------------------------------------------------------------------------
# Test 12 — Warnings forwarded from action validation
# ---------------------------------------------------------------------------


def test_action_validation_warnings_forwarded() -> None:
    ctx = make_context()
    validation = ActionValidationDetail(
        status=PlanValidationStatus.VALID_WITH_WARNINGS,
        warnings=["Move distance exceeds 500 units"],
    )
    plan = make_plan(actions=[move_action(handle="A1", validation=validation)])
    preview = EditPreviewBuilder(ctx).build(plan)

    assert "Move distance exceeds 500 units" in preview.warnings


# ---------------------------------------------------------------------------
# Test 13 — Approval requirements forwarded from plan
# ---------------------------------------------------------------------------


def test_approval_requirements_forwarded() -> None:
    ctx = make_context()
    plan = make_plan(
        actions=[delete_action(handle="A1")],
        requires_approval=True,
        approval_requirements=[
            ApprovalRequirement(description="Confirm destructive delete"),
            ApprovalRequirement(description="Supervisor sign-off required"),
        ],
    )
    preview = EditPreviewBuilder(ctx).build(plan)

    assert preview.requires_approval is True
    assert "Confirm destructive delete" in preview.approval_requirements
    assert "Supervisor sign-off required" in preview.approval_requirements


# ---------------------------------------------------------------------------
# Test 14 — Build timing is set and non-negative
# ---------------------------------------------------------------------------


def test_build_timing_is_set() -> None:
    ctx = make_context()
    plan = make_plan(actions=[move_action()])
    preview = EditPreviewBuilder(ctx).build(plan)

    assert preview.preview_build_ms is not None
    assert preview.preview_build_ms >= 0.0


# ---------------------------------------------------------------------------
# Test 15 — Multiple actions in one plan
# ---------------------------------------------------------------------------


def test_multiple_actions_all_previewed() -> None:
    ctx = make_context()
    plan = make_plan(
        actions=[
            move_action(handle="A1"),
            edit_text_action(handle="B1"),
            delete_action(handle="C1"),
        ]
    )
    preview = EditPreviewBuilder(ctx).build(plan)

    assert preview.total_actions == 3
    assert preview.destructive_count == 1
    action_types = {ap.action_type for ap in preview.actions}
    assert action_types == {"move_entity", "edit_text", "delete_entity"}


# ---------------------------------------------------------------------------
# Test 16 — Move with missing insert_point still builds (delta-only after_state)
# ---------------------------------------------------------------------------


def test_move_missing_insert_point_still_builds() -> None:
    ctx = DrawingContext(
        file_path="test.dxf",
        entities=[
            EntityRef(
                handle="NO_PT",
                entity_type=EntityType.LINE,
                layer="STRUCTURAL",
                insert_point=None,  # no position
            )
        ],
    )
    plan = make_plan(actions=[move_action(handle="NO_PT", dx=10.0, dy=0.0)])
    preview = EditPreviewBuilder(ctx).build(plan)

    ap = preview.actions[0]
    assert ap.before_state == {"position": None}
    assert ap.after_state == {"delta": {"dx": 10.0, "dy": 0.0}}
    # No crash — build completes
    assert preview.status == PreviewStatus.READY


# ---------------------------------------------------------------------------
# Test 17 — Delete entity with text content included in before_state
# ---------------------------------------------------------------------------


def test_delete_text_entity_includes_text_in_before() -> None:
    ctx = make_context()
    plan = make_plan(actions=[delete_action(handle="B1")])  # B1 has text_content
    preview = EditPreviewBuilder(ctx).build(plan)

    ap = preview.actions[0]
    assert ap.before_state.get("text") == "Old Label"
    assert ap.before_state.get("entity_type") == EntityType.TEXT.value
    assert ap.before_state.get("layer") == "NOTES"


# ---------------------------------------------------------------------------
# Test 18 — Delete entity with position included in before_state
# ---------------------------------------------------------------------------


def test_delete_entity_includes_position_in_before() -> None:
    ctx = make_context()
    plan = make_plan(actions=[delete_action(handle="A1")])  # A1 has insert_point
    preview = EditPreviewBuilder(ctx).build(plan)

    ap = preview.actions[0]
    assert ap.before_state.get("position") == {"x": 10.0, "y": 20.0}
    assert ap.before_state.get("entity_type") == EntityType.LINE.value


# ---------------------------------------------------------------------------
# Test 19 — Action ambiguity forwarded to action preview
# ---------------------------------------------------------------------------


def test_action_ambiguity_forwarded() -> None:
    ctx = make_context()
    action = move_action(
        handle="A1",
        ambiguity=["displacement_not_specified", "multiple_candidates"],
    )
    plan = make_plan(actions=[action])
    preview = EditPreviewBuilder(ctx).build(plan)

    ap = preview.actions[0]
    assert "displacement_not_specified" in ap.ambiguity
    assert "multiple_candidates" in ap.ambiguity


# ---------------------------------------------------------------------------
# Test 20 — Blocked action validation status forwarded
# ---------------------------------------------------------------------------


def test_blocked_action_validation_status_forwarded() -> None:
    ctx = make_context()
    validation = ActionValidationDetail(
        status=PlanValidationStatus.BLOCKED,
        blockers=["Entity is on a protected layer"],
    )
    action = EditAction(
        action_type=EditActionType.EDIT_TEXT,
        target_handle="B1",
        params={"new_text": "X"},
        validation=validation,
    )
    plan = make_plan(actions=[action])
    preview = EditPreviewBuilder(ctx).build(plan)

    ap = preview.actions[0]
    assert ap.validation_status == "blocked"
    assert "Entity is on a protected layer" in ap.blockers
    assert preview.blocked_count == 1

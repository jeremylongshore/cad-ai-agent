"""Anti-regression tests for edit planning (EPIC-CAD-07.4).

These tests enforce hard boundaries:
1. Edit planning does not apply edits
2. Non-edit task families do not enter edit planning
3. Planner does not emit unsupported freeform action blobs
4. Blocked plans remain blocked
5. Q&A and summary never route to edit planning
6. Low-trust OCR text does not masquerade as exact targeting
7. Repeated-condition batch plans require prior approval
"""

from __future__ import annotations

import pytest

from cad_dxf_agent.llm.intent_router import IntentRouter
from cad_dxf_agent.llm.plan_builder import EditPlanBuilder, PlanRequest
from cad_dxf_agent.models.cad_schema import (
    DrawingContext,
    EntityRef,
    EntityType,
    Point2D,
    TextGeometry,
    TextProvenance,
)
from cad_dxf_agent.models.plan_schema import (
    EditActionType,
    EditPlan,
    PlanValidationStatus,
)
from cad_dxf_agent.models.repeated_condition_schema import (
    ApprovalState,
    ConditionMatch,
    RepeatedConditionResult,
)
from cad_dxf_agent.models.response_schema import TaskFamily


@pytest.fixture
def builder():
    return EditPlanBuilder()


@pytest.fixture
def drawing_context():
    return DrawingContext(
        file_path="test.dxf",
        entities=[
            EntityRef(
                handle="T1",
                entity_type=EntityType.TEXT,
                layer="NOTES",
                insert_point=Point2D(x=10, y=20),
                text_content="Note A",
            ),
        ],
        layers=[],
        blocks=[],
    )


class TestEditPlanDoesNotApplyEdits:
    """Edit planning must never apply edits — plan_only output."""

    def test_plan_has_no_apply_method(self):
        plan = EditPlan()
        assert not hasattr(plan, "apply")
        assert not hasattr(plan, "execute")

    def test_plan_builder_returns_plan_not_changeset(self, builder, drawing_context):
        req = PlanRequest(
            prompt="move right 10",
            drawing_context=drawing_context,
            target_handles=["T1"],
        )
        result = builder.build(req)
        assert isinstance(result, EditPlan)
        # Must NOT be a ChangeSet or have apply semantics
        assert not hasattr(result, "apply")


class TestNonEditFamiliesExcluded:
    """Non-edit task families must not enter edit planning."""

    @pytest.mark.parametrize(
        "prompt,expected_family",
        [
            ("what is on layer WALLS?", TaskFamily.QNA),
            ("summarize this drawing", TaskFamily.SUMMARY),
            ("compare these two drawings", TaskFamily.COMPARE),
            ("find all instances of this", TaskFamily.REPEATED_CONDITION),
        ],
    )
    def test_non_edit_prompts_do_not_route_to_edit(self, prompt, expected_family):
        router = IntentRouter()
        result = router.classify(prompt)
        assert result.family == expected_family
        assert result.family != TaskFamily.EDIT_PLAN

    def test_qna_does_not_enter_edit_planning(self):
        router = IntentRouter()
        result = router.classify("what is this text?")
        assert result.family == TaskFamily.QNA

    def test_summary_does_not_enter_edit_planning(self):
        router = IntentRouter()
        result = router.classify("give me an overview of this drawing")
        assert result.family == TaskFamily.SUMMARY


class TestNoUnsupportedFreeformActions:
    """Planner must not emit unsupported action types."""

    def test_all_action_types_are_valid_enum(self, builder, drawing_context):
        req = PlanRequest(
            prompt="move right 10",
            drawing_context=drawing_context,
            target_handles=["T1"],
        )
        plan = builder.build(req)
        for action in plan.actions:
            # This would raise ValueError if action_type isn't a valid enum
            assert action.action_type in EditActionType

    def test_unsupported_request_produces_no_actions(self, builder, drawing_context):
        req = PlanRequest(
            prompt="analyze the structural integrity of this beam",
            drawing_context=drawing_context,
        )
        plan = builder.build(req)
        assert plan.action_count == 0
        assert plan.validation_status == PlanValidationStatus.NEEDS_CLARIFICATION


class TestBlockedPlansRemainBlocked:
    """Blocked plans must not be silently downgraded."""

    def test_blocked_status_persists_after_creation(self, builder, drawing_context):
        req = PlanRequest(
            prompt='change text to "X"',
            drawing_context=drawing_context,
            target_handles=["T1"],
        )
        plan = builder.build(req)
        # Manually block it
        plan.validation_status = PlanValidationStatus.BLOCKED
        plan.blocked_reasons.append("test block")
        # Status must persist
        assert plan.is_blocked
        assert "test block" in plan.blocked_reasons

    def test_batch_plan_pending_stays_blocked(self, builder, drawing_context):
        rc_result = RepeatedConditionResult(
            exemplar_handles=["T1"],
            exemplar_centroid=Point2D(x=10, y=20),
            candidates=[
                ConditionMatch(
                    entity_handles=["T1"],
                    confidence=0.9,
                    centroid=Point2D(x=100, y=200),
                    approval_state=ApprovalState.PENDING,
                ),
            ],
        )
        req = PlanRequest(
            prompt="replicate",
            drawing_context=drawing_context,
            repeated_condition_result=rc_result,
        )
        plan = builder.build(req)
        assert plan.validation_status == PlanValidationStatus.BLOCKED


class TestOcrTextDoesNotMasqueradeAsExact:
    """Low-trust OCR text must not pass as strong targeting evidence."""

    def test_ocr_text_reduces_confidence(self, builder):
        ctx = DrawingContext(
            file_path="test.dxf",
            entities=[
                EntityRef(
                    handle="OCR1",
                    entity_type=EntityType.TEXT,
                    layer="NOTES",
                    insert_point=Point2D(x=10, y=20),
                    text_content="Fuzzy text",
                    text_geometry=TextGeometry(
                        provenance=TextProvenance.RASTER_OCR_TEXT,
                        confidence_position=0.2,
                        confidence_rotation=0.2,
                        confidence_content=0.2,
                    ),
                ),
            ],
            layers=[],
            blocks=[],
        )
        req = PlanRequest(
            prompt='change text to "Fixed"',
            drawing_context=ctx,
            target_handles=["OCR1"],
        )
        plan = builder.build(req)
        assert plan.actions[0].confidence < 1.0
        assert "low_text_trust" in plan.actions[0].ambiguity


class TestRepeatedConditionApprovalRequired:
    """Batch plans from repeated-condition must require prior approval."""

    def test_unapproved_candidates_blocked(self, builder, drawing_context):
        rc_result = RepeatedConditionResult(
            exemplar_handles=["T1"],
            exemplar_centroid=Point2D(x=10, y=20),
            candidates=[
                ConditionMatch(
                    entity_handles=["T1"],
                    confidence=0.9,
                    centroid=Point2D(x=100, y=200),
                    approval_state=ApprovalState.PENDING,
                ),
            ],
        )
        req = PlanRequest(
            prompt="batch replicate",
            drawing_context=drawing_context,
            repeated_condition_result=rc_result,
        )
        plan = builder.build(req)
        assert plan.validation_status == PlanValidationStatus.BLOCKED
        assert any(
            req.category == "repeated_condition_approval" for req in plan.approval_requirements
        )

    def test_approved_candidates_proceed(self, builder, drawing_context):
        rc_result = RepeatedConditionResult(
            exemplar_handles=["T1"],
            exemplar_centroid=Point2D(x=10, y=20),
            candidates=[
                ConditionMatch(
                    entity_handles=["T1"],
                    confidence=0.9,
                    centroid=Point2D(x=100, y=200),
                    approval_state=ApprovalState.APPROVED,
                ),
            ],
        )
        req = PlanRequest(
            prompt="batch replicate",
            drawing_context=drawing_context,
            repeated_condition_result=rc_result,
        )
        plan = builder.build(req)
        assert plan.action_count == 1
        assert plan.validation_status != PlanValidationStatus.BLOCKED

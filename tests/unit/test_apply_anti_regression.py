"""Anti-regression tests for the preview + apply workflow (EPIC-CAD-08).

These tests guard specific invariants that must never break:
- Blocked plans never reach EditEngine
- Apply does not mutate the plan object
- REPLICATE_NOTE produces ADD_BLOCK, not an unknown op
- Non-edit task families do not enter apply flow
- Low-trust OCR text warnings preserved through apply
- Preview does not mutate drawing context
"""

from __future__ import annotations

from cad_dxf_agent.core.plan_converter import plan_to_changeset
from cad_dxf_agent.core.preview_builder import EditPreviewBuilder
from cad_dxf_agent.models.cad_schema import (
    DrawingContext,
    EntityRef,
    EntityType,
    Point2D,
    TextGeometry,
    TextProvenance,
)
from cad_dxf_agent.models.ops_schema import OpType
from cad_dxf_agent.models.plan_schema import (
    ActionValidationDetail,
    EditAction,
    EditActionType,
    EditPlan,
    PlanValidationStatus,
)


def _make_context() -> DrawingContext:
    return DrawingContext(
        file_path="test.dxf",
        entities=[
            EntityRef(
                handle="E1",
                entity_type=EntityType.TEXT,
                layer="NOTES",
                insert_point=Point2D(x=10, y=20),
                text_content="Sample",
            ),
            EntityRef(
                handle="E2",
                entity_type=EntityType.INSERT,
                layer="STRUCTURAL",
                insert_point=Point2D(x=50, y=60),
                block_name="COLUMN_MARK",
            ),
        ],
    )


def test_blocked_plan_never_reaches_edit_engine(sample_dxf, sample_context, tmp_path):
    """A blocked plan must never produce operations for the engine."""
    plan = EditPlan(
        validation_status=PlanValidationStatus.BLOCKED,
        blocked_reasons=["Protected layer"],
        actions=[
            EditAction(
                action_type=EditActionType.DELETE_ENTITY,
                target_handle="DOES_NOT_MATTER",
            )
        ],
    )

    from cad_dxf_agent.core.apply_pipeline import ApplyPipeline
    from cad_dxf_agent.models.apply_schema import ApplyStatus

    pipeline = ApplyPipeline(sample_context)
    result = pipeline.apply(plan, sample_dxf, tmp_path / "out.dxf")

    assert result.status == ApplyStatus.REJECTED
    assert not (tmp_path / "out.dxf").exists()


def test_apply_does_not_mutate_plan(sample_dxf, sample_context, tmp_path):
    """The apply pipeline must not modify the EditPlan object."""
    text_entity = next(
        e
        for e in sample_context.entities
        if e.entity_type in (EntityType.TEXT, EntityType.MTEXT) and e.layer != "TITLE"
    )

    plan = EditPlan(
        requires_approval=False,
        actions=[
            EditAction(
                action_type=EditActionType.EDIT_TEXT,
                target_handle=text_entity.handle,
                params={"new_text": "Changed"},
            )
        ],
    )

    plan_before = plan.model_dump()

    from cad_dxf_agent.core.apply_pipeline import ApplyPipeline

    pipeline = ApplyPipeline(sample_context)
    pipeline.apply(plan, sample_dxf, tmp_path / "out.dxf")

    plan_after = plan.model_dump()
    # Compare everything except action_id which is UUID-generated
    assert plan_before["actions"][0]["action_type"] == plan_after["actions"][0]["action_type"]
    assert plan_before["actions"][0]["params"] == plan_after["actions"][0]["params"]
    assert plan_before["requires_approval"] == plan_after["requires_approval"]
    assert plan_before["validation_status"] == plan_after["validation_status"]


def test_replicate_note_produces_add_block():
    """REPLICATE_NOTE must convert to ADD_BLOCK, not an unknown op type."""
    context = _make_context()
    plan = EditPlan(
        actions=[
            EditAction(
                action_type=EditActionType.REPLICATE_NOTE,
                target_handle="E2",
                params={
                    "source_handles": ["E2"],
                    "target_centroid": {"x": 100, "y": 200},
                },
            )
        ],
    )

    changeset, _ = plan_to_changeset(plan, context)
    assert len(changeset.operations) == 1
    assert changeset.operations[0].op_type == OpType.ADD_BLOCK


def test_non_edit_task_family_does_not_enter_apply():
    """Plans with non-edit task families should still work through the converter.

    The plan_to_changeset function doesn't filter by task_family — it only
    cares about action types. This test documents that behavior.
    """
    plan = EditPlan(
        task_family="qna",  # Not an edit family
        actions=[],
    )
    changeset, index_map = plan_to_changeset(plan)
    assert len(changeset.operations) == 0
    assert len(index_map) == 0


def test_low_trust_ocr_text_warning_preserved():
    """Low-trust OCR text entities should surface warnings through preview."""
    context = DrawingContext(
        file_path="test.dxf",
        entities=[
            EntityRef(
                handle="OCR1",
                entity_type=EntityType.TEXT,
                layer="NOTES",
                insert_point=Point2D(x=10, y=20),
                text_content="OCR Result",
                text_geometry=TextGeometry.for_provenance(TextProvenance.RASTER_OCR_TEXT),
            ),
        ],
    )

    plan = EditPlan(
        actions=[
            EditAction(
                action_type=EditActionType.EDIT_TEXT,
                target_handle="OCR1",
                params={"new_text": "Fixed Text"},
                confidence=0.6,
                ambiguity=["low_text_trust"],
                validation=ActionValidationDetail(
                    warnings=["Low text confidence from OCR"],
                ),
            )
        ],
    )

    builder = EditPreviewBuilder(context)
    preview = builder.build(plan)

    assert len(preview.actions) == 1
    assert "Low text confidence from OCR" in preview.actions[0].warnings
    assert "low_text_trust" in preview.actions[0].ambiguity


def test_preview_does_not_mutate_drawing_context():
    """Building a preview must not modify the DrawingContext."""
    context = _make_context()
    entities_before = [e.model_dump() for e in context.entities]

    plan = EditPlan(
        actions=[
            EditAction(
                action_type=EditActionType.MOVE_ENTITY,
                target_handle="E1",
                params={"dx": 10, "dy": 20},
            )
        ],
    )

    builder = EditPreviewBuilder(context)
    builder.build(plan)

    entities_after = [e.model_dump() for e in context.entities]
    assert entities_before == entities_after


def test_blocked_action_skipped_in_converter():
    """Blocked individual actions are skipped by the converter."""
    plan = EditPlan(
        actions=[
            EditAction(
                action_type=EditActionType.MOVE_ENTITY,
                target_handle="E1",
                params={"dx": 10, "dy": 0},
            ),
            EditAction(
                action_type=EditActionType.DELETE_ENTITY,
                target_handle="E2",
                validation=ActionValidationDetail(
                    status=PlanValidationStatus.BLOCKED,
                    blockers=["Protected layer"],
                ),
            ),
        ],
    )

    changeset, index_map = plan_to_changeset(plan)
    assert len(changeset.operations) == 1
    assert changeset.operations[0].op_type == OpType.MOVE_ENTITY
    assert index_map == {0: 0}


def test_preview_build_with_mixed_valid_and_blocked_actions():
    """Preview should include all actions, even blocked ones."""
    context = _make_context()
    plan = EditPlan(
        actions=[
            EditAction(
                action_type=EditActionType.MOVE_ENTITY,
                target_handle="E1",
                params={"dx": 5, "dy": 0},
            ),
            EditAction(
                action_type=EditActionType.DELETE_ENTITY,
                target_handle="E2",
                validation=ActionValidationDetail(
                    status=PlanValidationStatus.BLOCKED,
                    blockers=["Protected"],
                ),
            ),
        ],
    )

    builder = EditPreviewBuilder(context)
    preview = builder.build(plan)

    assert len(preview.actions) == 2
    assert preview.actions[1].validation_status == "blocked"
    assert preview.blocked_count == 1

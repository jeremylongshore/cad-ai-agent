"""Tests for edit plan builder (EPIC-CAD-07.2)."""

from __future__ import annotations

import pytest

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
    PlanValidationStatus,
)
from cad_dxf_agent.models.region_schema import BoundingBox, NormalizedRegion, RegionType
from cad_dxf_agent.models.repeated_condition_schema import (
    ApprovalState,
    ConditionMatch,
    RepeatedConditionResult,
)
from cad_dxf_agent.models.response_schema import RiskLevel


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
            EntityRef(
                handle="T2",
                entity_type=EntityType.MTEXT,
                layer="NOTES",
                insert_point=Point2D(x=50, y=60),
                text_content="Note B",
            ),
            EntityRef(
                handle="L1",
                entity_type=EntityType.LINE,
                layer="WALLS",
                insert_point=Point2D(x=100, y=200),
            ),
            EntityRef(
                handle="I1",
                entity_type=EntityType.INSERT,
                layer="SYMBOLS",
                insert_point=Point2D(x=30, y=40),
                block_name="DETAIL_A",
            ),
        ],
        layers=[],
        blocks=[],
    )


@pytest.fixture
def region_containing_t1():
    return NormalizedRegion(
        region_id="region-1",
        source_type=RegionType.BOX_SELECT,
        bounds=BoundingBox(min_x=0, min_y=0, max_x=25, max_y=35),
        center=Point2D(x=12.5, y=17.5),
    )


class TestMoveRequests:
    """Plan builder generates move plans."""

    def test_move_with_handles(self, builder, drawing_context):
        req = PlanRequest(
            prompt="move this right 10",
            drawing_context=drawing_context,
            target_handles=["T1"],
        )
        plan = builder.build(req)
        assert plan.action_count == 1
        assert plan.actions[0].action_type == EditActionType.MOVE_ENTITY
        assert plan.actions[0].target_handle == "T1"
        assert plan.actions[0].params["dx"] == 10.0
        assert plan.actions[0].params["dy"] == 0.0

    def test_move_with_coordinates(self, builder, drawing_context):
        req = PlanRequest(
            prompt="move by (5, -3)",
            drawing_context=drawing_context,
            target_handles=["L1"],
        )
        plan = builder.build(req)
        assert plan.actions[0].params["dx"] == 5.0
        assert plan.actions[0].params["dy"] == -3.0

    def test_move_no_target_returns_clarification(self, builder, drawing_context):
        req = PlanRequest(
            prompt="move this somewhere",
            drawing_context=drawing_context,
        )
        plan = builder.build(req)
        assert plan.validation_status == PlanValidationStatus.NEEDS_CLARIFICATION
        assert "no_move_target" in plan.ambiguity_flags

    def test_move_no_displacement_flags_ambiguity(self, builder, drawing_context):
        req = PlanRequest(
            prompt="move this note",
            drawing_context=drawing_context,
            target_handles=["T1"],
        )
        plan = builder.build(req)
        assert "displacement_not_specified" in plan.ambiguity_flags
        assert plan.actions[0].confidence == 0.5

    def test_move_in_region(self, builder, drawing_context, region_containing_t1):
        req = PlanRequest(
            prompt="move up 5",
            drawing_context=drawing_context,
            selected_regions=[region_containing_t1],
        )
        plan = builder.build(req)
        assert plan.action_count >= 1
        assert plan.actions[0].params["dy"] == 5.0
        assert plan.selected_region_ids == ["region-1"]


class TestDeleteRequests:
    """Plan builder generates delete plans."""

    def test_delete_with_handle(self, builder, drawing_context):
        req = PlanRequest(
            prompt="delete this entity",
            drawing_context=drawing_context,
            target_handles=["L1"],
        )
        plan = builder.build(req)
        assert plan.action_count == 1
        assert plan.actions[0].action_type == EditActionType.DELETE_ENTITY
        assert plan.actions[0].target_handle == "L1"

    def test_delete_multiple(self, builder, drawing_context, region_containing_t1):
        req = PlanRequest(
            prompt="remove everything in this area",
            drawing_context=drawing_context,
            selected_regions=[region_containing_t1],
        )
        plan = builder.build(req)
        assert plan.action_count >= 1
        assert plan.risk_level in (RiskLevel.MEDIUM, RiskLevel.HIGH)
        assert any(req.category == "destructive_confirmation" for req in plan.approval_requirements)

    def test_delete_no_target_returns_clarification(self, builder, drawing_context):
        req = PlanRequest(
            prompt="delete something",
            drawing_context=drawing_context,
        )
        plan = builder.build(req)
        assert plan.validation_status == PlanValidationStatus.NEEDS_CLARIFICATION


class TestTextEditRequests:
    """Plan builder generates text edit plans."""

    def test_edit_text_with_new_value(self, builder, drawing_context):
        req = PlanRequest(
            prompt='change text to "Updated Note"',
            drawing_context=drawing_context,
            target_handles=["T1"],
        )
        plan = builder.build(req)
        assert plan.action_count == 1
        assert plan.actions[0].action_type == EditActionType.EDIT_TEXT
        assert plan.actions[0].params["new_text"] == "Updated Note"

    def test_edit_text_no_new_value_flags_ambiguity(self, builder, drawing_context):
        req = PlanRequest(
            prompt="change text on this note",
            drawing_context=drawing_context,
            target_handles=["T1"],
        )
        plan = builder.build(req)
        assert "new_text_not_specified" in plan.ambiguity_flags

    def test_edit_text_on_non_text_entity_blocked(self, builder, drawing_context):
        req = PlanRequest(
            prompt='change text to "X"',
            drawing_context=drawing_context,
            target_handles=["L1"],  # LINE entity
        )
        plan = builder.build(req)
        assert plan.validation_status == PlanValidationStatus.BLOCKED

    def test_edit_text_low_trust_reduces_confidence(self, builder):
        ctx = DrawingContext(
            file_path="test.dxf",
            entities=[
                EntityRef(
                    handle="OCR1",
                    entity_type=EntityType.TEXT,
                    layer="NOTES",
                    insert_point=Point2D(x=10, y=20),
                    text_content="OCR text",
                    text_geometry=TextGeometry(
                        provenance=TextProvenance.RASTER_OCR_TEXT,
                        confidence_position=0.3,
                        confidence_rotation=0.3,
                        confidence_content=0.3,
                    ),
                ),
            ],
            layers=[],
            blocks=[],
        )
        req = PlanRequest(
            prompt='change text to "fixed"',
            drawing_context=ctx,
            target_handles=["OCR1"],
        )
        plan = builder.build(req)
        assert plan.actions[0].confidence < 1.0
        assert "low_text_trust" in plan.actions[0].ambiguity


class TestAddRequests:
    """Plan builder generates add/insert plans."""

    def test_add_with_region(self, builder, drawing_context, region_containing_t1):
        req = PlanRequest(
            prompt="add a note here",
            drawing_context=drawing_context,
            selected_regions=[region_containing_t1],
        )
        plan = builder.build(req)
        assert plan.action_count == 1
        assert plan.actions[0].action_type == EditActionType.ADD_BLOCK

    def test_add_without_region_needs_clarification(self, builder, drawing_context):
        req = PlanRequest(
            prompt="insert a block",
            drawing_context=drawing_context,
        )
        plan = builder.build(req)
        assert plan.validation_status == PlanValidationStatus.NEEDS_CLARIFICATION


class TestBatchPlans:
    """Plan builder handles repeated-condition batch plans."""

    def test_batch_from_approved_matches(self, builder, drawing_context):
        rc_result = RepeatedConditionResult(
            exemplar_handles=["I1"],
            exemplar_centroid=Point2D(x=30, y=40),
            candidates=[
                ConditionMatch(
                    entity_handles=["T1"],
                    confidence=0.85,
                    centroid=Point2D(x=100, y=200),
                    approval_state=ApprovalState.APPROVED,
                ),
                ConditionMatch(
                    entity_handles=["T2"],
                    confidence=0.75,
                    centroid=Point2D(x=200, y=300),
                    approval_state=ApprovalState.APPROVED,
                ),
            ],
        )
        req = PlanRequest(
            prompt="replicate to all approved locations",
            drawing_context=drawing_context,
            repeated_condition_result=rc_result,
        )
        plan = builder.build(req)
        assert plan.action_count == 2
        assert all(a.action_type == EditActionType.REPLICATE_NOTE for a in plan.actions)

    def test_batch_with_pending_matches_blocked(self, builder, drawing_context):
        rc_result = RepeatedConditionResult(
            exemplar_handles=["I1"],
            exemplar_centroid=Point2D(x=30, y=40),
            candidates=[
                ConditionMatch(
                    entity_handles=["T1"],
                    confidence=0.85,
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
        assert any("pending approval" in r for r in plan.blocked_reasons)

    def test_batch_no_candidates_needs_clarification(self, builder, drawing_context):
        rc_result = RepeatedConditionResult(
            exemplar_handles=["I1"],
            exemplar_centroid=Point2D(x=30, y=40),
            candidates=[],
        )
        req = PlanRequest(
            prompt="replicate",
            drawing_context=drawing_context,
            repeated_condition_result=rc_result,
        )
        plan = builder.build(req)
        assert plan.validation_status == PlanValidationStatus.NEEDS_CLARIFICATION


class TestUnsupportedRequests:
    """Unsupported requests return clarification, not fake plans."""

    def test_unsupported_prompt(self, builder, drawing_context):
        req = PlanRequest(
            prompt="please optimize the layout for energy efficiency",
            drawing_context=drawing_context,
        )
        plan = builder.build(req)
        assert plan.validation_status == PlanValidationStatus.NEEDS_CLARIFICATION
        assert plan.action_count == 0
        assert "unsupported_edit_request" in plan.ambiguity_flags

    def test_empty_prompt(self, builder, drawing_context):
        req = PlanRequest(
            prompt="",
            drawing_context=drawing_context,
        )
        plan = builder.build(req)
        assert plan.validation_status == PlanValidationStatus.NEEDS_CLARIFICATION


class TestPlanEvidencePreservation:
    """Plans preserve evidence and rationale."""

    def test_move_preserves_evidence(self, builder, drawing_context):
        req = PlanRequest(
            prompt="move right 10",
            drawing_context=drawing_context,
            target_handles=["T1"],
        )
        plan = builder.build(req)
        assert len(plan.actions[0].evidence) > 0
        assert plan.actions[0].evidence[0].entity_handle == "T1"

    def test_delete_preserves_evidence(self, builder, drawing_context):
        req = PlanRequest(
            prompt="delete",
            drawing_context=drawing_context,
            target_handles=["L1"],
        )
        plan = builder.build(req)
        assert len(plan.actions[0].evidence) > 0

    def test_plan_has_latency(self, builder, drawing_context):
        req = PlanRequest(
            prompt="delete",
            drawing_context=drawing_context,
            target_handles=["T1"],
        )
        plan = builder.build(req)
        assert plan.latency.plan_build_ms is not None
        assert plan.latency.plan_build_ms >= 0


class TestDisplacementParsing:
    """Displacement parsing from prompt text."""

    def test_parse_tuple(self):
        dx, dy = EditPlanBuilder._parse_displacement("move by (10, -5)")
        assert dx == 10.0
        assert dy == -5.0

    def test_parse_direction_right(self):
        dx, dy = EditPlanBuilder._parse_displacement("move 15 units right")
        assert dx == 15.0
        assert dy == 0.0

    def test_parse_direction_up(self):
        dx, dy = EditPlanBuilder._parse_displacement("shift up 7")
        assert dx == 0.0
        assert dy == 7.0

    def test_parse_direction_left(self):
        dx, dy = EditPlanBuilder._parse_displacement("move left 3")
        assert dx == -3.0
        assert dy == 0.0

    def test_parse_no_displacement(self):
        dx, dy = EditPlanBuilder._parse_displacement("move it somewhere")
        assert dx == 0.0
        assert dy == 0.0


class TestNewTextParsing:
    """New text extraction from prompt."""

    def test_quoted_text(self):
        text = EditPlanBuilder._parse_new_text('change to "Hello World"')
        assert text == "Hello World"

    def test_single_quoted_text(self):
        text = EditPlanBuilder._parse_new_text("rename to 'Fixed'")
        assert text == "Fixed"

    def test_unquoted_trailing(self):
        text = EditPlanBuilder._parse_new_text("change to REVISED")
        assert text == "REVISED"

    def test_no_text(self):
        text = EditPlanBuilder._parse_new_text("change the text")
        assert text is None

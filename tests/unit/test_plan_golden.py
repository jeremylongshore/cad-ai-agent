"""Golden tests for edit planning (EPIC-CAD-07.4).

Representative edit planning fixtures covering:
1. Construction-oriented edit planning
2. General drawing review / annotation edit
3. Text-sensitive case with SQ67 provenance influence
"""

from __future__ import annotations

import pytest

from cad_dxf_agent.core.plan_validator import PlanValidator
from cad_dxf_agent.llm.plan_builder import EditPlanBuilder, PlanRequest
from cad_dxf_agent.models.cad_schema import (
    DrawingContext,
    EntityRef,
    EntityType,
    Point2D,
    TextGeometry,
    TextProvenance,
)
from cad_dxf_agent.models.config_schema import RuleConfig
from cad_dxf_agent.models.plan_schema import (
    EditActionType,
    PlanValidationStatus,
)
from cad_dxf_agent.models.region_schema import (
    BoundingBox,
    NormalizedRegion,
    RegionType,
)
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
def rules():
    return RuleConfig(
        protected_layers=["TITLE", "TITLEBLOCK", "SEAL", "REVISION"],
        max_move_distance=500.0,
    )


class TestGoldenConstructionEdit:
    """Construction drawing: relocate a callout and update its text."""

    @pytest.fixture
    def construction_context(self):
        return DrawingContext(
            file_path="test.dxf",
            entities=[
                EntityRef(
                    handle="C1",
                    entity_type=EntityType.TEXT,
                    layer="CALLOUTS",
                    insert_point=Point2D(x=150, y=300),
                    text_content="SEE DETAIL A",
                    text_geometry=TextGeometry(
                        provenance=TextProvenance.NATIVE_CAD_TEXT,
                        confidence_position=0.95,
                        confidence_rotation=0.95,
                        confidence_content=0.99,
                    ),
                ),
                EntityRef(
                    handle="W1",
                    entity_type=EntityType.LINE,
                    layer="WALLS",
                    insert_point=Point2D(x=200, y=350),
                ),
                EntityRef(
                    handle="TITLE1",
                    entity_type=EntityType.TEXT,
                    layer="TITLE",
                    insert_point=Point2D(x=0, y=0),
                    text_content="FLOOR PLAN",
                ),
            ],
            layers=[],
            blocks=[],
        )

    def test_move_callout_produces_valid_plan(self, builder, construction_context, rules):
        req = PlanRequest(
            prompt="move this callout right 25",
            drawing_context=construction_context,
            target_handles=["C1"],
        )
        plan = builder.build(req)

        assert plan.action_count == 1
        assert plan.actions[0].action_type == EditActionType.MOVE_ENTITY
        assert plan.actions[0].params["dx"] == 25.0
        assert plan.actions[0].confidence == 1.0

        # Validate against constraints
        validator = PlanValidator(construction_context, rules)
        validated = validator.validate(plan)
        assert validated.validation_status in (
            PlanValidationStatus.VALID,
            PlanValidationStatus.VALID_WITH_WARNINGS,
        )

    def test_edit_callout_text(self, builder, construction_context, rules):
        req = PlanRequest(
            prompt='change text to "SEE DETAIL B"',
            drawing_context=construction_context,
            target_handles=["C1"],
        )
        plan = builder.build(req)

        assert plan.action_count == 1
        assert plan.actions[0].action_type == EditActionType.EDIT_TEXT
        assert plan.actions[0].params["new_text"] == "SEE DETAIL B"

        validator = PlanValidator(construction_context, rules)
        validated = validator.validate(plan)
        assert not validated.is_blocked

    def test_edit_title_blocked(self, builder, construction_context, rules):
        req = PlanRequest(
            prompt='change text to "MODIFIED"',
            drawing_context=construction_context,
            target_handles=["TITLE1"],
        )
        plan = builder.build(req)
        validator = PlanValidator(construction_context, rules)
        validated = validator.validate(plan)
        assert validated.is_blocked


class TestGoldenAnnotationReview:
    """General drawing review: delete annotation entities in a selected region."""

    @pytest.fixture
    def review_context(self):
        return DrawingContext(
            file_path="test.dxf",
            entities=[
                EntityRef(
                    handle="N1",
                    entity_type=EntityType.TEXT,
                    layer="ANNOTATIONS",
                    insert_point=Point2D(x=10, y=10),
                    text_content="Old note",
                ),
                EntityRef(
                    handle="N2",
                    entity_type=EntityType.TEXT,
                    layer="ANNOTATIONS",
                    insert_point=Point2D(x=15, y=12),
                    text_content="Another note",
                ),
                EntityRef(
                    handle="KEEP",
                    entity_type=EntityType.LINE,
                    layer="STRUCTURAL",
                    insert_point=Point2D(x=500, y=500),
                ),
            ],
            layers=[],
            blocks=[],
        )

    @pytest.fixture
    def annotation_region(self):
        return NormalizedRegion(
            region_id="annot-region",
            source_type=RegionType.BOX_SELECT,
            bounds=BoundingBox(min_x=0, min_y=0, max_x=30, max_y=30),
            center=Point2D(x=15, y=15),
        )

    def test_delete_annotations_in_region(self, builder, review_context, annotation_region, rules):
        req = PlanRequest(
            prompt="remove all items in this area",
            drawing_context=review_context,
            selected_regions=[annotation_region],
        )
        plan = builder.build(req)

        # Should find N1 and N2 in region, not KEEP
        assert plan.action_count == 2
        handles = {a.target_handle for a in plan.actions}
        assert "N1" in handles
        assert "N2" in handles
        assert "KEEP" not in handles

        assert plan.risk_level in (RiskLevel.MEDIUM, RiskLevel.HIGH)
        assert any(r.category == "destructive_confirmation" for r in plan.approval_requirements)

        # Validate
        validator = PlanValidator(review_context, rules)
        validated = validator.validate(plan)
        assert not validated.is_blocked


class TestGoldenTextProvenance:
    """Text-sensitive edit influenced by SQ67 provenance trust hierarchy."""

    @pytest.fixture
    def provenance_context(self):
        return DrawingContext(
            file_path="test.dxf",
            entities=[
                EntityRef(
                    handle="NATIVE",
                    entity_type=EntityType.TEXT,
                    layer="NOTES",
                    insert_point=Point2D(x=10, y=20),
                    text_content="Native text",
                    text_geometry=TextGeometry(
                        provenance=TextProvenance.NATIVE_CAD_TEXT,
                        confidence_position=0.95,
                        confidence_rotation=0.95,
                        confidence_content=0.99,
                    ),
                ),
                EntityRef(
                    handle="OCR",
                    entity_type=EntityType.TEXT,
                    layer="NOTES",
                    insert_point=Point2D(x=50, y=60),
                    text_content="Fuzzy OCR",
                    text_geometry=TextGeometry(
                        provenance=TextProvenance.RASTER_OCR_TEXT,
                        confidence_position=0.2,
                        confidence_rotation=0.2,
                        confidence_content=0.3,
                    ),
                ),
            ],
            layers=[],
            blocks=[],
        )

    def test_native_text_high_confidence(self, builder, provenance_context):
        req = PlanRequest(
            prompt='change text to "Updated"',
            drawing_context=provenance_context,
            target_handles=["NATIVE"],
        )
        plan = builder.build(req)
        assert plan.actions[0].confidence == 1.0
        assert "low_text_trust" not in plan.actions[0].ambiguity

    def test_ocr_text_reduced_confidence(self, builder, provenance_context):
        req = PlanRequest(
            prompt='change text to "Fixed"',
            drawing_context=provenance_context,
            target_handles=["OCR"],
        )
        plan = builder.build(req)
        assert plan.actions[0].confidence < 1.0
        assert "low_text_trust" in plan.actions[0].ambiguity

    def test_ocr_text_validator_warns(self, builder, provenance_context, rules):
        req = PlanRequest(
            prompt='change text to "Fixed"',
            drawing_context=provenance_context,
            target_handles=["OCR"],
        )
        plan = builder.build(req)
        validator = PlanValidator(provenance_context, rules)
        validated = validator.validate(plan)
        action_warnings = validated.actions[0].validation.warnings
        assert any("text trust" in w.lower() for w in action_warnings)


class TestGoldenBatchReplication:
    """Batch plan from approved repeated-condition matches."""

    @pytest.fixture
    def batch_context(self):
        return DrawingContext(
            file_path="test.dxf",
            entities=[
                EntityRef(
                    handle="EX1",
                    entity_type=EntityType.INSERT,
                    layer="SYMBOLS",
                    insert_point=Point2D(x=10, y=20),
                    block_name="DETAIL_A",
                ),
            ],
            layers=[],
            blocks=[],
        )

    def test_approved_batch_generates_replication_plan(self, builder, batch_context, rules):
        rc_result = RepeatedConditionResult(
            exemplar_handles=["EX1"],
            exemplar_centroid=Point2D(x=10, y=20),
            candidates=[
                ConditionMatch(
                    entity_handles=["M1"],
                    confidence=0.88,
                    centroid=Point2D(x=100, y=200),
                    approval_state=ApprovalState.APPROVED,
                ),
                ConditionMatch(
                    entity_handles=["M2"],
                    confidence=0.82,
                    centroid=Point2D(x=300, y=400),
                    approval_state=ApprovalState.APPROVED,
                ),
            ],
        )
        req = PlanRequest(
            prompt="replicate to approved locations",
            drawing_context=batch_context,
            repeated_condition_result=rc_result,
        )
        plan = builder.build(req)

        assert plan.action_count == 2
        assert all(a.action_type == EditActionType.REPLICATE_NOTE for a in plan.actions)
        # Confidences from match scores
        assert plan.actions[0].confidence == 0.88
        assert plan.actions[1].confidence == 0.82

        validator = PlanValidator(batch_context, rules)
        validated = validator.validate(plan)
        assert not validated.is_blocked

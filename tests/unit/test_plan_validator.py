"""Tests for plan validator (EPIC-CAD-07.3)."""

from __future__ import annotations

import pytest

from cad_dxf_agent.core.plan_validator import PlanValidator
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
    EditAction,
    EditActionType,
    EditPlan,
    PlanValidationStatus,
)
from cad_dxf_agent.models.response_schema import EvidenceRef


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
                handle="P1",
                entity_type=EntityType.TEXT,
                layer="TITLE",
                insert_point=Point2D(x=50, y=60),
                text_content="Drawing Title",
            ),
            EntityRef(
                handle="L1",
                entity_type=EntityType.LINE,
                layer="WALLS",
                insert_point=Point2D(x=100, y=200),
            ),
            EntityRef(
                handle="OCR1",
                entity_type=EntityType.TEXT,
                layer="NOTES",
                insert_point=Point2D(x=70, y=80),
                text_content="OCR derived",
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


@pytest.fixture
def rules():
    return RuleConfig(
        protected_layers=["TITLE", "TITLEBLOCK", "SEAL", "REVISION"],
        max_move_distance=500.0,
    )


@pytest.fixture
def validator(drawing_context, rules):
    return PlanValidator(drawing_context, rules)


class TestProtectedLayerBlocking:
    """Protected layers block edit actions."""

    def test_edit_on_protected_layer_blocked(self, validator):
        plan = EditPlan(
            actions=[
                EditAction(
                    action_type=EditActionType.EDIT_TEXT,
                    target_handle="P1",
                    params={"new_text": "New Title"},
                ),
            ],
        )
        result = validator.validate(plan)
        assert result.validation_status == PlanValidationStatus.BLOCKED
        assert any("protected layer" in b.lower() for b in result.blocked_reasons)

    def test_move_on_protected_layer_blocked(self, validator):
        plan = EditPlan(
            actions=[
                EditAction(
                    action_type=EditActionType.MOVE_ENTITY,
                    target_handle="P1",
                    params={"dx": 10, "dy": 0},
                ),
            ],
        )
        result = validator.validate(plan)
        assert result.validation_status == PlanValidationStatus.BLOCKED

    def test_delete_on_protected_layer_blocked(self, validator):
        plan = EditPlan(
            actions=[
                EditAction(
                    action_type=EditActionType.DELETE_ENTITY,
                    target_handle="P1",
                ),
            ],
        )
        result = validator.validate(plan)
        assert result.validation_status == PlanValidationStatus.BLOCKED

    def test_add_block_on_protected_layer_blocked(self, validator):
        plan = EditPlan(
            actions=[
                EditAction(
                    action_type=EditActionType.ADD_BLOCK,
                    target_layer="TITLE",
                    params={"block_name": "X", "insert_point": {"x": 0, "y": 0}},
                ),
            ],
        )
        result = validator.validate(plan)
        assert result.validation_status == PlanValidationStatus.BLOCKED


class TestUnsupportedEntityActionCombinations:
    """Unsupported entity/action combos are blocked."""

    def test_edit_text_on_line_blocked(self, validator):
        plan = EditPlan(
            actions=[
                EditAction(
                    action_type=EditActionType.EDIT_TEXT,
                    target_handle="L1",
                    params={"new_text": "hello"},
                ),
            ],
        )
        result = validator.validate(plan)
        assert result.validation_status == PlanValidationStatus.BLOCKED
        assert any("not supported" in b for b in result.blocked_reasons)


class TestMissingTargets:
    """Missing targets generate blockers."""

    def test_move_missing_handle_blocked(self, validator):
        plan = EditPlan(
            actions=[
                EditAction(
                    action_type=EditActionType.MOVE_ENTITY,
                    params={"dx": 10, "dy": 0},
                ),
            ],
        )
        result = validator.validate(plan)
        assert result.validation_status == PlanValidationStatus.BLOCKED

    def test_nonexistent_handle_blocked(self, validator):
        plan = EditPlan(
            actions=[
                EditAction(
                    action_type=EditActionType.DELETE_ENTITY,
                    target_handle="NONEXISTENT",
                ),
            ],
        )
        result = validator.validate(plan)
        assert result.validation_status == PlanValidationStatus.BLOCKED
        assert any("not found" in b for b in result.blocked_reasons)


class TestLowConfidenceTargeting:
    """Low confidence targeting surfaces warnings."""

    def test_low_confidence_action_warns(self, validator):
        plan = EditPlan(
            actions=[
                EditAction(
                    action_type=EditActionType.MOVE_ENTITY,
                    target_handle="T1",
                    params={"dx": 10, "dy": 0},
                    confidence=0.3,
                ),
            ],
        )
        result = validator.validate(plan)
        assert result.validation_status == PlanValidationStatus.VALID_WITH_WARNINGS
        action_warnings = result.actions[0].validation.warnings
        assert any("low confidence" in w.lower() for w in action_warnings)

    def test_missing_evidence_warns(self, validator):
        plan = EditPlan(
            actions=[
                EditAction(
                    action_type=EditActionType.DELETE_ENTITY,
                    target_handle="T1",
                    evidence=[],
                ),
            ],
        )
        result = validator.validate(plan)
        action_warnings = result.actions[0].validation.warnings
        assert any("no evidence" in w.lower() for w in action_warnings)


class TestTextTrustIssues:
    """Low-trust OCR text targeting surfaces warnings."""

    def test_ocr_text_edit_warns(self, validator):
        plan = EditPlan(
            actions=[
                EditAction(
                    action_type=EditActionType.EDIT_TEXT,
                    target_handle="OCR1",
                    params={"new_text": "fixed"},
                ),
            ],
        )
        result = validator.validate(plan)
        action_warnings = result.actions[0].validation.warnings
        assert any("text trust" in w.lower() for w in action_warnings)


class TestMoveValidation:
    """Move-specific validation."""

    def test_zero_displacement_warns(self, validator):
        plan = EditPlan(
            actions=[
                EditAction(
                    action_type=EditActionType.MOVE_ENTITY,
                    target_handle="T1",
                    params={"dx": 0, "dy": 0},
                ),
            ],
        )
        result = validator.validate(plan)
        action_warnings = result.actions[0].validation.warnings
        assert any("zero displacement" in w.lower() for w in action_warnings)

    def test_large_distance_warns(self, validator):
        plan = EditPlan(
            actions=[
                EditAction(
                    action_type=EditActionType.MOVE_ENTITY,
                    target_handle="T1",
                    params={"dx": 1000, "dy": 0},
                ),
            ],
        )
        result = validator.validate(plan)
        action_warnings = result.actions[0].validation.warnings
        assert any("exceeds max" in w for w in action_warnings)


class TestEditTextValidation:
    """Edit text param validation."""

    def test_missing_new_text_blocked(self, validator):
        plan = EditPlan(
            actions=[
                EditAction(
                    action_type=EditActionType.EDIT_TEXT,
                    target_handle="T1",
                    params={},
                ),
            ],
        )
        result = validator.validate(plan)
        assert result.validation_status == PlanValidationStatus.BLOCKED


class TestReplicateValidation:
    """Replicate action validation."""

    def test_missing_source_handles_blocked(self, validator):
        plan = EditPlan(
            actions=[
                EditAction(
                    action_type=EditActionType.REPLICATE_NOTE,
                    params={"target_centroid": {"x": 0, "y": 0}},
                ),
            ],
        )
        result = validator.validate(plan)
        assert result.validation_status == PlanValidationStatus.BLOCKED

    def test_missing_target_centroid_blocked(self, validator):
        plan = EditPlan(
            actions=[
                EditAction(
                    action_type=EditActionType.REPLICATE_NOTE,
                    params={"source_handles": ["I1"]},
                ),
            ],
        )
        result = validator.validate(plan)
        assert result.validation_status == PlanValidationStatus.BLOCKED


class TestPlanLevelValidation:
    """Plan-level constraints."""

    def test_valid_plan_stays_valid(self, validator):
        plan = EditPlan(
            actions=[
                EditAction(
                    action_type=EditActionType.MOVE_ENTITY,
                    target_handle="T1",
                    params={"dx": 10, "dy": 5},
                    evidence=[EvidenceRef(entity_handle="T1", description="target")],
                ),
            ],
        )
        result = validator.validate(plan)
        assert result.validation_status in (
            PlanValidationStatus.VALID,
            PlanValidationStatus.VALID_WITH_WARNINGS,
        )

    def test_mixed_valid_and_blocked(self, validator):
        plan = EditPlan(
            actions=[
                EditAction(
                    action_type=EditActionType.MOVE_ENTITY,
                    target_handle="T1",
                    params={"dx": 10, "dy": 0},
                ),
                EditAction(
                    action_type=EditActionType.EDIT_TEXT,
                    target_handle="P1",  # protected
                    params={"new_text": "X"},
                ),
            ],
        )
        result = validator.validate(plan)
        assert result.validation_status == PlanValidationStatus.BLOCKED

"""Tests for edit plan schema (EPIC-CAD-07.1)."""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from cad_dxf_agent.models.plan_schema import (
    ActionValidationDetail,
    ApprovalRequirement,
    EditAction,
    EditActionType,
    EditPlan,
    PlanLatency,
    PlanValidationStatus,
)
from cad_dxf_agent.models.response_schema import EvidenceRef, RiskLevel


class TestEditActionType:
    """Action type enum validates correctly."""

    def test_all_types_defined(self):
        assert len(EditActionType) == 5

    def test_supported_types(self):
        assert EditActionType.MOVE_ENTITY == "move_entity"
        assert EditActionType.EDIT_TEXT == "edit_text"
        assert EditActionType.DELETE_ENTITY == "delete_entity"
        assert EditActionType.ADD_BLOCK == "add_block"
        assert EditActionType.REPLICATE_NOTE == "replicate_note"

    def test_invalid_type_raises(self):
        with pytest.raises(ValueError):
            EditActionType("fly_entity")


class TestPlanValidationStatus:
    """Validation status enum validates correctly."""

    def test_all_statuses(self):
        assert PlanValidationStatus.VALID == "valid"
        assert PlanValidationStatus.VALID_WITH_WARNINGS == "valid_with_warnings"
        assert PlanValidationStatus.BLOCKED == "blocked"
        assert PlanValidationStatus.NEEDS_CLARIFICATION == "needs_clarification"


class TestEditAction:
    """Edit action model validates and serializes."""

    def test_minimal_action(self):
        action = EditAction(action_type=EditActionType.MOVE_ENTITY)
        assert action.action_type == EditActionType.MOVE_ENTITY
        assert action.action_id  # auto-generated
        assert action.confidence == 1.0
        assert action.risk_level == RiskLevel.LOW
        assert action.ambiguity == []
        assert action.evidence == []
        assert action.validation.status == PlanValidationStatus.VALID

    def test_full_action(self):
        action = EditAction(
            action_type=EditActionType.EDIT_TEXT,
            target_handle="ABC",
            target_layer="NOTES",
            target_entity_type="TEXT",
            region_id="region1",
            params={"new_text": "Updated"},
            evidence=[EvidenceRef(entity_handle="ABC", description="test")],
            rationale="User requested text change",
            confidence=0.9,
            ambiguity=["partial_match"],
            risk_level=RiskLevel.MEDIUM,
        )
        assert action.target_handle == "ABC"
        assert action.params["new_text"] == "Updated"
        assert len(action.evidence) == 1
        assert action.confidence == 0.9

    def test_confidence_bounds(self):
        with pytest.raises(ValidationError):
            EditAction(action_type=EditActionType.MOVE_ENTITY, confidence=1.5)
        with pytest.raises(ValidationError):
            EditAction(action_type=EditActionType.MOVE_ENTITY, confidence=-0.1)

    def test_action_serialization(self):
        action = EditAction(
            action_type=EditActionType.DELETE_ENTITY,
            target_handle="DEF",
        )
        data = action.model_dump()
        assert data["action_type"] == "delete_entity"
        assert data["target_handle"] == "DEF"
        assert "action_id" in data


class TestActionValidationDetail:
    """Per-action validation detail."""

    def test_defaults_to_valid(self):
        detail = ActionValidationDetail()
        assert detail.status == PlanValidationStatus.VALID
        assert detail.blockers == []
        assert detail.warnings == []

    def test_blocked(self):
        detail = ActionValidationDetail(
            status=PlanValidationStatus.BLOCKED,
            blockers=["protected layer"],
        )
        assert detail.status == PlanValidationStatus.BLOCKED


class TestEditPlan:
    """Edit plan model validates correctly."""

    def test_empty_plan(self):
        plan = EditPlan()
        assert plan.schema_version == "1.0"
        assert plan.task_family == "edit_plan"
        assert plan.action_count == 0
        assert not plan.is_blocked
        assert plan.requires_approval

    def test_plan_with_actions(self):
        plan = EditPlan(
            actions=[
                EditAction(action_type=EditActionType.MOVE_ENTITY),
                EditAction(action_type=EditActionType.DELETE_ENTITY),
            ],
            source_drawing="test.dxf",
        )
        assert plan.action_count == 2
        assert plan.source_drawing == "test.dxf"

    def test_plan_confidence_ambiguity_risk(self):
        plan = EditPlan(
            confidence=0.7,
            ambiguity_flags=["displacement_not_specified"],
            risk_level=RiskLevel.HIGH,
        )
        assert plan.confidence == 0.7
        assert "displacement_not_specified" in plan.ambiguity_flags
        assert plan.risk_level == RiskLevel.HIGH

    def test_plan_blocked_status(self):
        plan = EditPlan(
            validation_status=PlanValidationStatus.BLOCKED,
            blocked_reasons=["protected layer"],
        )
        assert plan.is_blocked
        assert plan.blocked_reasons == ["protected layer"]

    def test_plan_needs_clarification(self):
        plan = EditPlan(
            validation_status=PlanValidationStatus.NEEDS_CLARIFICATION,
        )
        assert plan.needs_clarification

    def test_plan_with_warnings(self):
        plan = EditPlan(
            validation_status=PlanValidationStatus.VALID_WITH_WARNINGS,
        )
        assert plan.has_warnings

    def test_plan_approval_requirements(self):
        plan = EditPlan(
            approval_requirements=[
                ApprovalRequirement(
                    description="Confirm deletion",
                    category="destructive_confirmation",
                ),
            ],
        )
        assert len(plan.approval_requirements) == 1
        assert not plan.approval_requirements[0].satisfied

    def test_plan_latency(self):
        plan = EditPlan(
            latency=PlanLatency(
                plan_build_ms=5.2,
                validation_ms=1.1,
                total_ms=6.3,
            ),
        )
        assert plan.latency.plan_build_ms == 5.2
        assert plan.latency.total_ms == 6.3

    def test_plan_evidence(self):
        plan = EditPlan(
            evidence=[
                EvidenceRef(entity_handle="A1", description="source entity"),
            ],
        )
        assert len(plan.evidence) == 1

    def test_plan_serialization_roundtrip(self):
        plan = EditPlan(
            actions=[
                EditAction(
                    action_type=EditActionType.EDIT_TEXT,
                    target_handle="X",
                    params={"new_text": "hello"},
                ),
            ],
            confidence=0.85,
            risk_level=RiskLevel.MEDIUM,
            validation_status=PlanValidationStatus.VALID_WITH_WARNINGS,
            rationale="Test plan",
        )
        data = plan.model_dump()
        restored = EditPlan.model_validate(data)
        assert restored.action_count == 1
        assert restored.confidence == 0.85
        assert restored.risk_level == RiskLevel.MEDIUM

    def test_plan_entity_handles(self):
        plan = EditPlan(entity_handles=["A", "B", "C"])
        assert plan.entity_handles == ["A", "B", "C"]

    def test_plan_selected_regions(self):
        plan = EditPlan(selected_region_ids=["r1", "r2"])
        assert len(plan.selected_region_ids) == 2

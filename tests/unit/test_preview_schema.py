"""Tests for preview_schema: PreviewStatus, ActionPreview, EditPreview (EPIC-CAD-08)."""

from __future__ import annotations

import json

import pytest
from pydantic import ValidationError

from cad_dxf_agent.models.preview_schema import ActionPreview, EditPreview, PreviewStatus
from cad_dxf_agent.models.response_schema import RiskLevel

# ---------------------------------------------------------------------------
# PreviewStatus enum
# ---------------------------------------------------------------------------


def test_preview_status_values():
    assert PreviewStatus.READY == "ready"
    assert PreviewStatus.BLOCKED == "blocked"
    assert PreviewStatus.NEEDS_CLARIFICATION == "needs_clarification"


def test_preview_status_has_three_members():
    assert len(PreviewStatus) == 3


def test_preview_status_is_str():
    # StrEnum members are plain strings — usable wherever str is expected.
    assert isinstance(PreviewStatus.READY, str)
    assert f"status={PreviewStatus.BLOCKED}" == "status=blocked"


# ---------------------------------------------------------------------------
# ActionPreview defaults
# ---------------------------------------------------------------------------


def test_action_preview_defaults():
    action = ActionPreview(action_id="a1", action_type="move_entity")
    assert action.action_id == "a1"
    assert action.action_type == "move_entity"
    assert action.description == ""
    assert action.target_handle is None
    assert action.target_layer is None
    assert action.target_entity_type is None
    assert action.before_state == {}
    assert action.after_state == {}
    assert action.confidence == 1.0
    assert action.risk_level == RiskLevel.LOW
    assert action.is_destructive is False
    assert action.warnings == []
    assert action.ambiguity == []
    assert action.validation_status == "valid"
    assert action.blockers == []


# ---------------------------------------------------------------------------
# ActionPreview with all fields populated
# ---------------------------------------------------------------------------


def test_action_preview_all_fields():
    action = ActionPreview(
        action_id="a2",
        action_type="edit_text",
        description="Change callout from A to B",
        target_handle="1F3",
        target_layer="NOTES",
        target_entity_type="TEXT",
        before_state={"text": "A"},
        after_state={"text": "B"},
        confidence=0.85,
        risk_level=RiskLevel.MEDIUM,
        is_destructive=False,
        warnings=["text differs by more than threshold"],
        ambiguity=["multiple_matches"],
        validation_status="valid_with_warnings",
        blockers=[],
    )
    assert action.target_handle == "1F3"
    assert action.target_layer == "NOTES"
    assert action.target_entity_type == "TEXT"
    assert action.before_state == {"text": "A"}
    assert action.after_state == {"text": "B"}
    assert action.confidence == 0.85
    assert action.risk_level == RiskLevel.MEDIUM
    assert action.warnings == ["text differs by more than threshold"]
    assert action.ambiguity == ["multiple_matches"]
    assert action.validation_status == "valid_with_warnings"


# ---------------------------------------------------------------------------
# ActionPreview confidence validation
# ---------------------------------------------------------------------------


def test_action_preview_confidence_boundary_valid():
    low = ActionPreview(action_id="x", action_type="move_entity", confidence=0.0)
    high = ActionPreview(action_id="y", action_type="move_entity", confidence=1.0)
    mid = ActionPreview(action_id="z", action_type="move_entity", confidence=0.5)
    assert low.confidence == 0.0
    assert high.confidence == 1.0
    assert mid.confidence == 0.5


def test_action_preview_confidence_above_one_raises():
    with pytest.raises(ValidationError):
        ActionPreview(action_id="bad", action_type="move_entity", confidence=1.1)


def test_action_preview_confidence_below_zero_raises():
    with pytest.raises(ValidationError):
        ActionPreview(action_id="bad", action_type="move_entity", confidence=-0.01)


# ---------------------------------------------------------------------------
# ActionPreview serialization roundtrip
# ---------------------------------------------------------------------------


def test_action_preview_serialization_roundtrip():
    action = ActionPreview(
        action_id="rt1",
        action_type="delete_entity",
        target_handle="9A4",
        target_layer="WALLS",
        before_state={"layer": "WALLS", "type": "LINE"},
        after_state={},
        confidence=0.75,
        risk_level=RiskLevel.HIGH,
        is_destructive=True,
        warnings=["irreversible"],
        blockers=[],
    )
    data = action.model_dump()
    restored = ActionPreview.model_validate(data)

    assert restored.action_id == action.action_id
    assert restored.action_type == action.action_type
    assert restored.target_handle == action.target_handle
    assert restored.before_state == {"layer": "WALLS", "type": "LINE"}
    assert restored.after_state == {}
    assert restored.confidence == 0.75
    assert restored.risk_level == RiskLevel.HIGH
    assert restored.is_destructive is True
    assert restored.warnings == ["irreversible"]


# ---------------------------------------------------------------------------
# EditPreview defaults
# ---------------------------------------------------------------------------


def test_edit_preview_defaults():
    preview = EditPreview()
    assert preview.plan_id == ""
    assert preview.request_id == ""
    assert preview.status == PreviewStatus.READY
    assert preview.actions == []
    assert preview.total_actions == 0
    assert preview.destructive_count == 0
    assert preview.blocked_count == 0
    assert preview.confidence == 1.0
    assert preview.risk_level == RiskLevel.LOW
    assert preview.summary == ""
    assert preview.warnings == []
    assert preview.approval_requirements == []
    assert preview.requires_approval is True
    assert preview.preview_build_ms is None


def test_edit_preview_auto_generated_preview_id():
    p1 = EditPreview()
    p2 = EditPreview()
    assert p1.preview_id  # non-empty
    assert len(p1.preview_id) == 16
    assert p1.preview_id != p2.preview_id


# ---------------------------------------------------------------------------
# EditPreview with actions
# ---------------------------------------------------------------------------


def test_edit_preview_with_actions():
    actions = [
        ActionPreview(action_id="a1", action_type="move_entity", target_handle="H1"),
        ActionPreview(action_id="a2", action_type="edit_text", target_handle="H2"),
    ]
    preview = EditPreview(
        plan_id="plan-001",
        request_id="req-abc",
        actions=actions,
        total_actions=2,
        summary="Move entity H1 and update text on H2",
    )
    assert len(preview.actions) == 2
    assert preview.actions[0].action_id == "a1"
    assert preview.actions[1].action_type == "edit_text"
    assert preview.total_actions == 2
    assert preview.plan_id == "plan-001"
    assert preview.request_id == "req-abc"
    assert "H2" in preview.summary


# ---------------------------------------------------------------------------
# EditPreview status values
# ---------------------------------------------------------------------------


def test_edit_preview_status_ready():
    preview = EditPreview(status=PreviewStatus.READY)
    assert preview.status == PreviewStatus.READY
    assert preview.status == "ready"


def test_edit_preview_status_blocked():
    preview = EditPreview(
        status=PreviewStatus.BLOCKED,
        blocked_count=1,
        warnings=["operation targets protected layer TITLE"],
    )
    assert preview.status == PreviewStatus.BLOCKED
    assert preview.blocked_count == 1
    assert len(preview.warnings) == 1


def test_edit_preview_status_needs_clarification():
    preview = EditPreview(status=PreviewStatus.NEEDS_CLARIFICATION)
    assert preview.status == PreviewStatus.NEEDS_CLARIFICATION
    assert preview.status == "needs_clarification"


# ---------------------------------------------------------------------------
# EditPreview serialization roundtrip
# ---------------------------------------------------------------------------


def test_edit_preview_serialization_roundtrip():
    preview = EditPreview(
        plan_id="plan-rt",
        request_id="req-rt",
        status=PreviewStatus.READY,
        actions=[
            ActionPreview(
                action_id="ra1",
                action_type="move_entity",
                target_handle="C9",
                confidence=0.9,
                risk_level=RiskLevel.LOW,
            ),
        ],
        total_actions=1,
        destructive_count=0,
        confidence=0.9,
        risk_level=RiskLevel.LOW,
        summary="Move C9 by (5, 0)",
        preview_build_ms=12.4,
    )
    data = json.loads(preview.model_dump_json())
    restored = EditPreview.model_validate(data)

    assert restored.plan_id == "plan-rt"
    assert restored.request_id == "req-rt"
    assert restored.status == PreviewStatus.READY
    assert len(restored.actions) == 1
    assert restored.actions[0].target_handle == "C9"
    assert restored.total_actions == 1
    assert restored.confidence == 0.9
    assert restored.risk_level == RiskLevel.LOW
    assert restored.preview_build_ms == 12.4


# ---------------------------------------------------------------------------
# EditPreview with approval requirements
# ---------------------------------------------------------------------------


def test_edit_preview_approval_requirements():
    preview = EditPreview(
        requires_approval=True,
        approval_requirements=["Confirm deletion of 3 entities", "Acknowledge high-risk operation"],
    )
    assert preview.requires_approval is True
    assert len(preview.approval_requirements) == 2
    assert "Confirm deletion of 3 entities" in preview.approval_requirements


def test_edit_preview_no_approval_required():
    preview = EditPreview(requires_approval=False, approval_requirements=[])
    assert preview.requires_approval is False
    assert preview.approval_requirements == []


# ---------------------------------------------------------------------------
# EditPreview destructive count
# ---------------------------------------------------------------------------


def test_edit_preview_destructive_count():
    actions = [
        ActionPreview(action_id="d1", action_type="delete_entity", is_destructive=True),
        ActionPreview(action_id="d2", action_type="delete_entity", is_destructive=True),
        ActionPreview(action_id="d3", action_type="move_entity", is_destructive=False),
    ]
    preview = EditPreview(
        actions=actions,
        total_actions=3,
        destructive_count=2,
        risk_level=RiskLevel.HIGH,
    )
    assert preview.destructive_count == 2
    assert preview.total_actions == 3
    assert preview.risk_level == RiskLevel.HIGH
    destructive = [a for a in preview.actions if a.is_destructive]
    assert len(destructive) == 2


# ---------------------------------------------------------------------------
# EditPreview blocked status
# ---------------------------------------------------------------------------


def test_edit_preview_blocked_status_with_blockers():
    actions = [
        ActionPreview(
            action_id="b1",
            action_type="edit_text",
            target_layer="TITLE",
            validation_status="blocked",
            blockers=["layer TITLE is protected"],
        ),
    ]
    preview = EditPreview(
        status=PreviewStatus.BLOCKED,
        actions=actions,
        total_actions=1,
        blocked_count=1,
        warnings=["1 action blocked due to protected layer"],
    )
    assert preview.status == PreviewStatus.BLOCKED
    assert preview.blocked_count == 1
    assert preview.actions[0].blockers == ["layer TITLE is protected"]
    assert preview.actions[0].validation_status == "blocked"
    blocked_actions = [a for a in preview.actions if a.validation_status == "blocked"]
    assert len(blocked_actions) == 1

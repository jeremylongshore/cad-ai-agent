"""Tests for apply schema models (EPIC-CAD-08)."""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from cad_dxf_agent.models.apply_schema import (
    ActionResult,
    ApplyResult,
    ApplyStatus,
    ApprovalDecision,
    AuditEvent,
)

# ---------------------------------------------------------------------------
# ApplyStatus
# ---------------------------------------------------------------------------


def test_apply_status_values():
    assert ApplyStatus.SUCCESS == "success"
    assert ApplyStatus.PARTIAL == "partial"
    assert ApplyStatus.FAILED == "failed"
    assert ApplyStatus.REJECTED == "rejected"


def test_apply_status_invalid_raises():
    with pytest.raises(ValueError):
        ApplyStatus("unknown")


# ---------------------------------------------------------------------------
# ActionResult
# ---------------------------------------------------------------------------


def test_action_result_defaults():
    result = ActionResult(action_id="a1", action_type="move_entity")
    assert result.action_id == "a1"
    assert result.action_type == "move_entity"
    assert result.success is True
    assert result.entity_handle is None
    assert result.description == ""
    assert result.error is None


def test_action_result_with_error():
    result = ActionResult(
        action_id="a2",
        action_type="delete_entity",
        success=False,
        entity_handle="3F",
        description="Entity not found",
        error="Handle 3F does not exist in drawing",
    )
    assert result.success is False
    assert result.entity_handle == "3F"
    assert result.error == "Handle 3F does not exist in drawing"
    assert result.description == "Entity not found"


# ---------------------------------------------------------------------------
# ApplyResult
# ---------------------------------------------------------------------------


def test_apply_result_defaults():
    result = ApplyResult()
    assert result.apply_id  # auto-generated, non-empty
    assert result.plan_id == ""
    assert result.preview_id == ""
    assert result.request_id == ""
    assert result.status == ApplyStatus.SUCCESS
    assert result.action_results == []
    assert result.success_count == 0
    assert result.failure_count == 0
    assert result.output_path is None
    assert result.revision_note is None
    assert result.summary == ""
    assert result.warnings == []
    assert result.apply_ms is None
    assert result.save_ms is None
    assert result.total_ms is None


def test_apply_result_apply_id_is_unique():
    r1 = ApplyResult()
    r2 = ApplyResult()
    assert r1.apply_id != r2.apply_id


def test_apply_result_with_action_results():
    actions = [
        ActionResult(action_id="a1", action_type="move_entity", success=True),
        ActionResult(
            action_id="a2",
            action_type="edit_text",
            success=False,
            error="Protected layer",
        ),
    ]
    result = ApplyResult(
        plan_id="plan-001",
        preview_id="prev-001",
        request_id="req-001",
        status=ApplyStatus.PARTIAL,
        action_results=actions,
        success_count=1,
        failure_count=1,
        output_path="/tmp/out.dxf",
        revision_note="1 of 2 actions applied",
        summary="Partial apply: one action blocked",
        warnings=["edit_text blocked on protected layer"],
        apply_ms=12.5,
        save_ms=3.1,
        total_ms=15.6,
    )
    assert result.status == ApplyStatus.PARTIAL
    assert len(result.action_results) == 2
    assert result.success_count == 1
    assert result.failure_count == 1
    assert result.output_path == "/tmp/out.dxf"
    assert result.revision_note == "1 of 2 actions applied"
    assert result.warnings == ["edit_text blocked on protected layer"]
    assert result.apply_ms == pytest.approx(12.5)
    assert result.total_ms == pytest.approx(15.6)


# ---------------------------------------------------------------------------
# AuditEvent
# ---------------------------------------------------------------------------


def test_audit_event_required_fields_and_defaults():
    event = AuditEvent(event_type="plan_created")
    assert event.event_id  # auto-generated
    assert event.event_type == "plan_created"
    assert event.timestamp  # auto-generated ISO string
    assert event.plan_id is None
    assert event.preview_id is None
    assert event.apply_id is None
    assert event.actor == ""
    assert event.details == {}


def test_audit_event_event_id_is_unique():
    e1 = AuditEvent(event_type="apply_started")
    e2 = AuditEvent(event_type="apply_started")
    assert e1.event_id != e2.event_id


def test_audit_event_with_all_fields():
    event = AuditEvent(
        event_type="apply_completed",
        plan_id="plan-001",
        preview_id="prev-001",
        apply_id="apply-001",
        actor="user@example.com",
        details={"success_count": 3, "failure_count": 0},
    )
    assert event.plan_id == "plan-001"
    assert event.preview_id == "prev-001"
    assert event.apply_id == "apply-001"
    assert event.actor == "user@example.com"
    assert event.details["success_count"] == 3


# ---------------------------------------------------------------------------
# ApprovalDecision
# ---------------------------------------------------------------------------


def test_approval_decision_approved():
    decision = ApprovalDecision(plan_id="plan-42", approved=True)
    assert decision.plan_id == "plan-42"
    assert decision.approved is True
    assert decision.approved_by == ""
    assert decision.approved_at  # auto-generated ISO string
    assert decision.notes == ""


def test_approval_decision_rejected():
    decision = ApprovalDecision(
        plan_id="plan-43",
        approved=False,
        approved_by="reviewer@example.com",
        notes="Scope too broad — split into smaller operations",
    )
    assert decision.approved is False
    assert decision.approved_by == "reviewer@example.com"
    assert decision.notes == "Scope too broad — split into smaller operations"


def test_approval_decision_requires_plan_id():
    with pytest.raises(ValidationError):
        ApprovalDecision(approved=True)  # type: ignore[call-arg]


def test_approval_decision_requires_approved():
    with pytest.raises(ValidationError):
        ApprovalDecision(plan_id="plan-44")  # type: ignore[call-arg]

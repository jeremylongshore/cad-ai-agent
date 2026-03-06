"""Tests for response_schema: TaskFamily, ResponseType, PlatformResponse, AuditMetadata."""

from __future__ import annotations

import json

from cad_dxf_agent.models.response_schema import (
    AuditMetadata,
    EvidenceRef,
    PlatformResponse,
    ResponseType,
    RiskLevel,
    TaskFamily,
)

# ---------------------------------------------------------------------------
# TaskFamily enum
# ---------------------------------------------------------------------------


class TestTaskFamily:
    def test_has_10_members(self):
        assert len(TaskFamily) == 10

    def test_all_values_are_lowercase(self):
        for member in TaskFamily:
            assert member.value == member.value.lower()

    def test_compare_is_first_priority(self):
        members = list(TaskFamily)
        assert members[0] == TaskFamily.COMPARE

    def test_needs_clarification_is_penultimate(self):
        members = list(TaskFamily)
        assert members[-2] == TaskFamily.NEEDS_CLARIFICATION

    def test_unsupported_is_last(self):
        members = list(TaskFamily)
        assert members[-1] == TaskFamily.UNSUPPORTED

    def test_str_serialization(self):
        assert str(TaskFamily.EDIT_PLAN) == "edit_plan"
        assert str(TaskFamily.QNA) == "qna"

    def test_all_expected_families_present(self):
        expected = {
            "compare",
            "markup_interpretation",
            "edit_plan",
            "takeoff_estimate",
            "repeated_condition",
            "design_assist",
            "summary",
            "qna",
            "needs_clarification",
            "unsupported",
        }
        assert {f.value for f in TaskFamily} == expected


# ---------------------------------------------------------------------------
# ResponseType enum
# ---------------------------------------------------------------------------


class TestResponseType:
    def test_has_6_members(self):
        assert len(ResponseType) == 6

    def test_plan_only_exists(self):
        assert ResponseType.PLAN_ONLY == "plan_only"

    def test_all_expected_types_present(self):
        expected = {
            "plan_only",
            "plan_applied",
            "answer",
            "comparison_result",
            "needs_clarification",
            "unsupported_operation",
        }
        assert {r.value for r in ResponseType} == expected


# ---------------------------------------------------------------------------
# RiskLevel enum
# ---------------------------------------------------------------------------


class TestRiskLevel:
    def test_has_3_members(self):
        assert len(RiskLevel) == 3

    def test_ordering(self):
        assert RiskLevel.LOW.value == "low"
        assert RiskLevel.HIGH.value == "high"


# ---------------------------------------------------------------------------
# EvidenceRef
# ---------------------------------------------------------------------------


class TestEvidenceRef:
    def test_minimal(self):
        ref = EvidenceRef()
        assert ref.entity_handle is None
        assert ref.description == ""

    def test_with_values(self):
        ref = EvidenceRef(entity_handle="A1", layer="WALLS", description="moved 5 units")
        assert ref.entity_handle == "A1"
        assert ref.layer == "WALLS"


# ---------------------------------------------------------------------------
# AuditMetadata
# ---------------------------------------------------------------------------


class TestAuditMetadata:
    def test_auto_generated_trace_id(self):
        audit = AuditMetadata()
        assert len(audit.trace_id) == 16
        assert audit.trace_id.isalnum()

    def test_auto_generated_timestamp(self):
        audit = AuditMetadata()
        assert "T" in audit.timestamp  # ISO format

    def test_unique_trace_ids(self):
        a1 = AuditMetadata()
        a2 = AuditMetadata()
        assert a1.trace_id != a2.trace_id

    def test_latency_fields_default_none(self):
        audit = AuditMetadata()
        assert audit.router_time_ms is None
        assert audit.llm_time_ms is None
        assert audit.total_request_time_ms is None

    def test_latency_fields_populated(self):
        audit = AuditMetadata(
            router_time_ms=1.5,
            context_build_time_ms=10.0,
            llm_time_ms=500.0,
            validation_time_ms=2.0,
            total_request_time_ms=513.5,
        )
        assert audit.router_time_ms == 1.5
        assert audit.total_request_time_ms == 513.5

    def test_router_source_and_confidence(self):
        audit = AuditMetadata(router_source="heuristic", router_confidence=0.95)
        assert audit.router_source == "heuristic"
        assert audit.router_confidence == 0.95


# ---------------------------------------------------------------------------
# PlatformResponse
# ---------------------------------------------------------------------------


class TestPlatformResponse:
    def test_minimal_response(self):
        resp = PlatformResponse(
            task_family=TaskFamily.EDIT_PLAN,
            response_type=ResponseType.PLAN_ONLY,
            message="Move entity A1 by (10, 0)",
        )
        assert resp.task_family == TaskFamily.EDIT_PLAN
        assert resp.response_type == ResponseType.PLAN_ONLY
        assert resp.operations == []
        assert resp.risk_level == RiskLevel.LOW
        assert resp.audit.trace_id  # auto-generated

    def test_with_operations(self):
        resp = PlatformResponse(
            task_family=TaskFamily.EDIT_PLAN,
            response_type=ResponseType.PLAN_ONLY,
            message="Plan ready",
            operations=[{"op_type": "move_entity", "target_handle": "A1"}],
        )
        assert len(resp.operations) == 1
        assert resp.operations[0]["op_type"] == "move_entity"

    def test_unsupported_operation(self):
        resp = PlatformResponse(
            task_family=TaskFamily.QNA,
            response_type=ResponseType.UNSUPPORTED_OPERATION,
            message="Q&A is not yet available.",
        )
        assert resp.response_type == ResponseType.UNSUPPORTED_OPERATION
        assert resp.operations == []

    def test_needs_clarification(self):
        resp = PlatformResponse(
            task_family=TaskFamily.NEEDS_CLARIFICATION,
            response_type=ResponseType.NEEDS_CLARIFICATION,
            message="Could you be more specific?",
        )
        assert resp.task_family == TaskFamily.NEEDS_CLARIFICATION

    def test_json_serialization(self):
        resp = PlatformResponse(
            task_family=TaskFamily.EDIT_PLAN,
            response_type=ResponseType.PLAN_ONLY,
            message="test",
        )
        data = json.loads(resp.model_dump_json())
        assert data["task_family"] == "edit_plan"
        assert data["response_type"] == "plan_only"
        assert "trace_id" in data["audit"]

    def test_with_validation(self):
        resp = PlatformResponse(
            task_family=TaskFamily.EDIT_PLAN,
            response_type=ResponseType.PLAN_ONLY,
            message="Plan ready",
            validation={
                "blockers": [],
                "warnings": [{"message": "Large move distance"}],
                "is_valid": True,
            },
        )
        assert resp.validation["is_valid"] is True

    def test_with_evidence(self):
        resp = PlatformResponse(
            task_family=TaskFamily.EDIT_PLAN,
            response_type=ResponseType.PLAN_ONLY,
            message="test",
            evidence=[EvidenceRef(entity_handle="A1", description="target")],
        )
        assert len(resp.evidence) == 1

    def test_risk_level_override(self):
        resp = PlatformResponse(
            task_family=TaskFamily.EDIT_PLAN,
            response_type=ResponseType.PLAN_ONLY,
            message="Deleting 50 entities",
            risk_level=RiskLevel.HIGH,
        )
        assert resp.risk_level == RiskLevel.HIGH

    def test_comparison_result_type(self):
        resp = PlatformResponse(
            task_family=TaskFamily.COMPARE,
            response_type=ResponseType.COMPARISON_RESULT,
            message="3 changes found",
            operations=[{"op_type": "added", "description": "new wall"}],
        )
        assert resp.response_type == ResponseType.COMPARISON_RESULT

"""Tests for response_schema: TaskFamily, ResponseType, PlatformResponse, AuditMetadata."""

from __future__ import annotations

import json

from cad_dxf_agent.models.response_schema import (
    AuditMetadata,
    EvidenceRef,
    PlatformRequest,
    PlatformResponse,
    ResponseType,
    RiskLevel,
    TaskFamily,
)

# ---------------------------------------------------------------------------
# TaskFamily enum
# ---------------------------------------------------------------------------


class TestTaskFamily:
    def test_has_11_members(self):
        assert len(TaskFamily) == 11

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
            "apply_edit",
            "takeoff_estimate",
            "repeated_condition",
            "design_assist",
            "summary",
            "qna",
            "needs_clarification",
            "unsupported",
        }
        assert {f.value for f in TaskFamily} == expected

    def test_apply_edit_exists(self):
        assert TaskFamily.APPLY_EDIT == "apply_edit"


# ---------------------------------------------------------------------------
# ResponseType enum
# ---------------------------------------------------------------------------


class TestResponseType:
    def test_has_7_members(self):
        assert len(ResponseType) == 7

    def test_plan_only_exists(self):
        assert ResponseType.PLAN_ONLY == "plan_only"

    def test_all_expected_types_present(self):
        expected = {
            "plan_only",
            "preview_edit",
            "applied_edit",
            "answer_only",
            "comparison_result",
            "needs_clarification",
            "unsupported_operation",
        }
        assert {r.value for r in ResponseType} == expected

    def test_answer_only_not_answer(self):
        assert hasattr(ResponseType, "ANSWER_ONLY")

    def test_preview_edit_exists(self):
        assert ResponseType.PREVIEW_EDIT == "preview_edit"

    def test_applied_edit_exists(self):
        assert ResponseType.APPLIED_EDIT == "applied_edit"


# ---------------------------------------------------------------------------
# RiskLevel enum
# ---------------------------------------------------------------------------


class TestRiskLevel:
    def test_has_4_members(self):
        assert len(RiskLevel) == 4

    def test_ordering(self):
        assert RiskLevel.NONE.value == "none"
        assert RiskLevel.LOW.value == "low"
        assert RiskLevel.HIGH.value == "high"

    def test_none_level_exists(self):
        assert RiskLevel.NONE == "none"


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

    def test_extended_fields(self):
        ref = EvidenceRef(
            entity_handle="B2",
            layer="DOORS",
            description="door entity",
            entity_type="INSERT",
            location=(50.0, 100.0),
            text_excerpt="DOOR-101",
        )
        assert ref.entity_type == "INSERT"
        assert ref.location == (50.0, 100.0)
        assert ref.text_excerpt == "DOOR-101"


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
# PlatformRequest
# ---------------------------------------------------------------------------


class TestPlatformRequest:
    def test_minimal_request(self):
        req = PlatformRequest(prompt="move wall", session_id="sess-1")
        assert req.prompt == "move wall"
        assert req.session_id == "sess-1"
        assert req.request_id  # auto-generated
        assert req.schema_version == "1.0"

    def test_auto_generated_request_id(self):
        r1 = PlatformRequest(prompt="a", session_id="s")
        r2 = PlatformRequest(prompt="a", session_id="s")
        assert r1.request_id != r2.request_id

    def test_optional_fields_default_empty(self):
        req = PlatformRequest(prompt="test", session_id="s")
        assert req.task_family is None
        assert req.selected_regions == []
        assert req.drawing_references == []
        assert req.comparison_references == []
        assert req.markup_references == []
        assert req.client_metadata == {}

    def test_full_request(self):
        req = PlatformRequest(
            prompt="compare drawings",
            session_id="sess-1",
            task_family=TaskFamily.COMPARE,
            selected_regions=[{"x": 0, "y": 0, "w": 100, "h": 100}],
            drawing_references=["master.dxf"],
            comparison_references=["revision.dxf"],
            client_metadata={"source": "web"},
        )
        assert req.task_family == TaskFamily.COMPARE
        assert len(req.selected_regions) == 1
        assert req.drawing_references == ["master.dxf"]

    def test_json_serialization(self):
        req = PlatformRequest(prompt="test", session_id="s")
        data = json.loads(req.model_dump_json())
        assert "request_id" in data
        assert data["schema_version"] == "1.0"


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

    def test_schema_version_default(self):
        resp = PlatformResponse(
            task_family=TaskFamily.EDIT_PLAN,
            response_type=ResponseType.PLAN_ONLY,
            message="test",
        )
        assert resp.schema_version == "1.0"

    def test_confidence_field(self):
        resp = PlatformResponse(
            task_family=TaskFamily.EDIT_PLAN,
            response_type=ResponseType.PLAN_ONLY,
            message="test",
            confidence=0.95,
        )
        assert resp.confidence == 0.95

    def test_ambiguity_flags(self):
        resp = PlatformResponse(
            task_family=TaskFamily.EDIT_PLAN,
            response_type=ResponseType.PLAN_ONLY,
            message="test",
            ambiguity_flags=["low_confidence", "multiple_matches"],
        )
        assert "low_confidence" in resp.ambiguity_flags
        assert len(resp.ambiguity_flags) == 2

    def test_data_payload(self):
        resp = PlatformResponse(
            task_family=TaskFamily.QNA,
            response_type=ResponseType.ANSWER_ONLY,
            message="42 entities on WALLS",
            data={"entity_count": 42, "layer": "WALLS"},
        )
        assert resp.data["entity_count"] == 42

    def test_session_id_field(self):
        resp = PlatformResponse(
            task_family=TaskFamily.EDIT_PLAN,
            response_type=ResponseType.PLAN_ONLY,
            message="test",
            session_id="sess-123",
        )
        assert resp.session_id == "sess-123"

    def test_preview_edit_type(self):
        resp = PlatformResponse(
            task_family=TaskFamily.EDIT_PLAN,
            response_type=ResponseType.PREVIEW_EDIT,
            message="Preview of proposed changes",
        )
        assert resp.response_type == ResponseType.PREVIEW_EDIT

    def test_applied_edit_type(self):
        resp = PlatformResponse(
            task_family=TaskFamily.APPLY_EDIT,
            response_type=ResponseType.APPLIED_EDIT,
            message="Changes applied",
        )
        assert resp.response_type == ResponseType.APPLIED_EDIT
        assert resp.task_family == TaskFamily.APPLY_EDIT

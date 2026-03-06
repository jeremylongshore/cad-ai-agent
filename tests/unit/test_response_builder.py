"""Tests for ResponseBuilder — typed PlatformResponse construction."""

from __future__ import annotations

from cad_dxf_agent.llm.response_builder import ResponseBuilder
from cad_dxf_agent.models.response_schema import (
    AuditMetadata,
    ResponseType,
    RiskLevel,
    TaskFamily,
)


class TestPlanOnly:
    def test_basic_plan(self):
        resp = ResponseBuilder.plan_only(
            operations=[{"op_type": "move_entity", "target_handle": "A1"}],
            message="Move entity A1 by (10, 0)",
        )
        assert resp.task_family == TaskFamily.EDIT_PLAN
        assert resp.response_type == ResponseType.PLAN_ONLY
        assert len(resp.operations) == 1

    def test_with_validation(self):
        resp = ResponseBuilder.plan_only(
            operations=[],
            message="No ops",
            validation={"blockers": [], "warnings": [], "is_valid": True},
        )
        assert resp.validation["is_valid"] is True

    def test_risk_inferred_low(self):
        resp = ResponseBuilder.plan_only(
            operations=[{"op_type": "move_entity"}],
            message="test",
        )
        assert resp.risk_level == RiskLevel.LOW

    def test_risk_inferred_medium_with_deletes(self):
        resp = ResponseBuilder.plan_only(
            operations=[{"op_type": "delete_entity"}],
            message="test",
        )
        assert resp.risk_level == RiskLevel.MEDIUM

    def test_risk_inferred_high_many_deletes(self):
        ops = [{"op_type": "delete_entity"} for _ in range(6)]
        resp = ResponseBuilder.plan_only(operations=ops, message="test")
        assert resp.risk_level == RiskLevel.HIGH

    def test_risk_override(self):
        resp = ResponseBuilder.plan_only(
            operations=[{"op_type": "move_entity"}],
            message="test",
            risk_level=RiskLevel.HIGH,
        )
        assert resp.risk_level == RiskLevel.HIGH


class TestUnsupportedOperation:
    def test_qna_unsupported(self):
        resp = ResponseBuilder.unsupported_operation(family=TaskFamily.QNA)
        assert resp.response_type == ResponseType.UNSUPPORTED_OPERATION
        assert "Q&A" in resp.message
        assert "not yet available" in resp.message

    def test_summary_unsupported(self):
        resp = ResponseBuilder.unsupported_operation(family=TaskFamily.SUMMARY)
        assert "Drawing summary" in resp.message

    def test_markup_unsupported(self):
        resp = ResponseBuilder.unsupported_operation(family=TaskFamily.MARKUP_INTERPRETATION)
        assert "Markup interpretation" in resp.message


class TestNeedsClarification:
    def test_default_message(self):
        resp = ResponseBuilder.needs_clarification()
        assert resp.response_type == ResponseType.NEEDS_CLARIFICATION
        assert "more specific" in resp.message

    def test_custom_message(self):
        resp = ResponseBuilder.needs_clarification(message="Upload a file first.")
        assert resp.message == "Upload a file first."


class TestComparisonResult:
    def test_basic(self):
        resp = ResponseBuilder.comparison_result(message="3 changes found")
        assert resp.task_family == TaskFamily.COMPARE
        assert resp.response_type == ResponseType.COMPARISON_RESULT


class TestAnswer:
    def test_answer(self):
        resp = ResponseBuilder.answer(family=TaskFamily.QNA, message="Layer WALLS has 42 entities")
        assert resp.response_type == ResponseType.ANSWER
        assert resp.task_family == TaskFamily.QNA


class TestAuditPassthrough:
    def test_custom_audit(self):
        audit = AuditMetadata(
            router_time_ms=1.5,
            total_request_time_ms=100.0,
            router_source="heuristic",
            router_confidence=0.95,
        )
        resp = ResponseBuilder.plan_only(
            operations=[],
            message="test",
            audit=audit,
        )
        assert resp.audit.router_time_ms == 1.5
        assert resp.audit.total_request_time_ms == 100.0

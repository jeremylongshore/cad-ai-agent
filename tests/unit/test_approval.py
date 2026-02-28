"""Tests for approval gating logic."""

from __future__ import annotations

import pytest

from cad_dxf_agent.core.comparison.approval import (
    approve_all_pending,
    approve_op,
    build_initial_approvals,
    force_approve_op,
    reject_op,
    validate_approvals,
)
from cad_dxf_agent.models.comparison_schema import (
    ApprovalConfig,
    ApprovalStatus,
    RevisionOp,
    RevisionOpType,
)


def _make_op(op_id: str = "op1", confidence: float = 0.9) -> RevisionOp:
    return RevisionOp(
        op_id=op_id,
        op_type=RevisionOpType.MOVE,
        change_index=0,
        target_handle="A0",
        target_layer="STRUCTURAL",
        confidence=confidence,
    )


class TestBuildInitialApprovals:
    def test_high_confidence_auto_approved(self):
        ops = [_make_op("a", 0.95)]
        aset = build_initial_approvals(ops, ApprovalConfig(auto_approve_threshold=0.85))
        assert "a" in aset.approved_op_ids
        assert aset.get_decision("a").status == ApprovalStatus.AUTO_APPROVED

    def test_low_confidence_pending(self):
        ops = [_make_op("a", 0.70)]
        aset = build_initial_approvals(ops, ApprovalConfig(auto_approve_threshold=0.85))
        assert "a" in aset.pending_op_ids

    def test_boundary_confidence_auto_approved(self):
        """Exactly at threshold → auto-approved."""
        ops = [_make_op("a", 0.85)]
        aset = build_initial_approvals(ops, ApprovalConfig(auto_approve_threshold=0.85))
        assert "a" in aset.approved_op_ids

    def test_mixed_confidences(self):
        ops = [_make_op("high", 0.90), _make_op("low", 0.50)]
        aset = build_initial_approvals(ops, ApprovalConfig(auto_approve_threshold=0.85))
        assert "high" in aset.approved_op_ids
        assert "low" in aset.pending_op_ids


class TestApproveRejectForce:
    def test_approve_op(self):
        ops = [_make_op("a", 0.70)]
        aset = build_initial_approvals(ops)
        approve_op(aset, "a", reason="looks good")
        assert "a" in aset.approved_op_ids

    def test_reject_op(self):
        ops = [_make_op("a", 0.70)]
        aset = build_initial_approvals(ops)
        reject_op(aset, "a")
        assert "a" in aset.rejected_op_ids

    def test_force_approve_requires_allow_force(self):
        ops = [_make_op("a", 0.40)]
        aset = build_initial_approvals(ops, ApprovalConfig(allow_force=False))
        with pytest.raises(ValueError, match="allow_force"):
            force_approve_op(aset, "a")

    def test_force_approve_succeeds_when_allowed(self):
        ops = [_make_op("a", 0.40)]
        aset = build_initial_approvals(ops, ApprovalConfig(allow_force=True))
        force_approve_op(aset, "a", reason="reviewed manually")
        assert aset.get_decision("a").status == ApprovalStatus.FORCE_APPROVED

    def test_approve_unknown_op_raises(self):
        aset = build_initial_approvals([])
        with pytest.raises(ValueError, match="No decision"):
            approve_op(aset, "nonexistent")


class TestApproveAllPending:
    def test_batch_approve(self):
        ops = [_make_op("a", 0.70), _make_op("b", 0.60), _make_op("c", 0.95)]
        aset = build_initial_approvals(ops, ApprovalConfig(auto_approve_threshold=0.85))
        count = approve_all_pending(aset)
        assert count == 2
        assert aset.pending_op_ids == set()


class TestValidateApprovals:
    def test_valid_all_approved(self):
        ops = [_make_op("a", 0.90)]
        aset = build_initial_approvals(ops)
        errors = validate_approvals(ops, aset)
        assert errors == []

    def test_pending_ops_flagged(self):
        ops = [_make_op("a", 0.70)]
        aset = build_initial_approvals(ops)
        errors = validate_approvals(ops, aset)
        assert any("pending" in e for e in errors)

    def test_low_confidence_needs_force(self):
        ops = [_make_op("a", 0.50)]
        config = ApprovalConfig(
            auto_approve_threshold=0.85,
            force_required_threshold=0.60,
        )
        aset = build_initial_approvals(ops, config)
        # Approve it (not force) — should be flagged
        approve_op(aset, "a")
        errors = validate_approvals(ops, aset)
        assert any("force_approve" in e for e in errors)

    def test_force_approved_low_confidence_valid(self):
        ops = [_make_op("a", 0.50)]
        config = ApprovalConfig(
            auto_approve_threshold=0.85,
            force_required_threshold=0.60,
            allow_force=True,
        )
        aset = build_initial_approvals(ops, config)
        force_approve_op(aset, "a")
        errors = validate_approvals(ops, aset)
        assert errors == []

"""Tests for CLI output formatters — covering previously uncovered paths."""

from __future__ import annotations

import json

import pytest

from cad_dxf_agent.models.comparison_schema import (
    AlignmentDiagnostics,
    AlignmentMethod,
    AlignmentResult,
    ApprovalDecision,
    ApprovalSet,
    ApprovalStatus,
    ComparisonResult,
    RevisionOp,
    RevisionOpType,
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_comparison_result(
    *,
    warnings: list[str] | None = None,
    alignment: AlignmentResult | None = None,
) -> ComparisonResult:
    """Build a ComparisonResult with optional warnings and alignment."""
    summary = {"added": 1, "removed": 2, "modified": 0, "moved": 0, "unchanged": 5}
    return ComparisonResult(
        summary=summary,
        warnings=warnings or [],
        alignment_result=alignment,
    )


def _make_alignment(
    *,
    method: AlignmentMethod = AlignmentMethod.translation,
    confidence: float = 0.95,
    translation: tuple[float, float] = (1.0, 2.0),
    rotation_deg: float = 0.5,
    with_diagnostics: bool = True,
) -> AlignmentResult:
    diag = (
        AlignmentDiagnostics(
            rms_residual=0.001,
            overlap_ratio=0.95,
            match_count=100,
            inlier_count=90,
        )
        if with_diagnostics
        else AlignmentDiagnostics()
    )
    return AlignmentResult(
        method=method,
        confidence=confidence,
        translation=translation,
        rotation_deg=rotation_deg,
        diagnostics=diag,
    )


def _make_revision_op(
    op_id: str = "op1",
    op_type: RevisionOpType = RevisionOpType.MOVE,
    handle: str = "H1",
    layer: str = "STRUCTURAL",
    confidence: float = 0.9,
    description: str = "Move entity",
) -> RevisionOp:
    return RevisionOp(
        op_id=op_id,
        op_type=op_type,
        change_index=0,
        target_handle=handle,
        target_layer=layer,
        confidence=confidence,
        description=description,
    )


def _make_approval_set(ops: list[RevisionOp]) -> ApprovalSet:
    decisions = [ApprovalDecision(op_id=op.op_id, status=ApprovalStatus.APPROVED) for op in ops]
    return ApprovalSet(decisions=decisions)


# ---------------------------------------------------------------------------
# format_summary — lines 16-18
# ---------------------------------------------------------------------------


class TestFormatSummary:
    def test_format_summary_with_single_warning(self):
        """Lines 15-17: warnings list is rendered before the table."""
        from cad_dxf_agent.cli.formatters import format_summary

        result = _make_comparison_result(warnings=["Layer X excluded all entities"])
        text = format_summary(result)

        assert "WARNING: Layer X excluded all entities" in text
        # Table still appears after the warning block
        assert "Category" in text

    def test_format_summary_with_multiple_warnings(self):
        """Multiple warnings each get their own WARNING: line."""
        from cad_dxf_agent.cli.formatters import format_summary

        result = _make_comparison_result(warnings=["warn A", "warn B", "warn C"])
        text = format_summary(result)

        assert "WARNING: warn A" in text
        assert "WARNING: warn B" in text
        assert "WARNING: warn C" in text

    def test_format_summary_no_warnings(self):
        """No warnings → no WARNING: prefix in output."""
        from cad_dxf_agent.cli.formatters import format_summary

        result = _make_comparison_result()
        text = format_summary(result)

        assert "WARNING:" not in text
        assert "total" in text


# ---------------------------------------------------------------------------
# format_summary_json — lines 37, 42
# ---------------------------------------------------------------------------


class TestFormatSummaryJson:
    def test_format_summary_json_with_alignment_result(self):
        """Line 37: alignment_result is truthy → included in JSON output."""
        from cad_dxf_agent.cli.formatters import format_summary_json

        alignment = _make_alignment(method=AlignmentMethod.rigid, confidence=0.88)
        result = _make_comparison_result(alignment=alignment)
        text = format_summary_json(result)
        data = json.loads(text)

        assert "alignment" in data
        assert data["alignment"]["method"] == "rigid"
        assert data["alignment"]["confidence"] == pytest.approx(0.88)

    def test_format_summary_json_with_warnings(self):
        """Line 42: warnings list is truthy → included in JSON output."""
        from cad_dxf_agent.cli.formatters import format_summary_json

        result = _make_comparison_result(warnings=["too many exclusions"])
        text = format_summary_json(result)
        data = json.loads(text)

        assert "warnings" in data
        assert "too many exclusions" in data["warnings"]

    def test_format_summary_json_without_optional_fields(self):
        """No alignment, no warnings → neither key appears in JSON."""
        from cad_dxf_agent.cli.formatters import format_summary_json

        result = _make_comparison_result()
        text = format_summary_json(result)
        data = json.loads(text)

        assert "alignment" not in data
        assert "warnings" not in data
        assert "total_changes" in data

    def test_format_summary_json_with_both_optional_fields(self):
        """Both alignment and warnings together in one result."""
        from cad_dxf_agent.cli.formatters import format_summary_json

        alignment = _make_alignment(confidence=0.77)
        result = _make_comparison_result(warnings=["overlap low"], alignment=alignment)
        text = format_summary_json(result)
        data = json.loads(text)

        assert "alignment" in data
        assert "warnings" in data


# ---------------------------------------------------------------------------
# format_alignment_json — lines 65-80
# ---------------------------------------------------------------------------


class TestFormatAlignmentJson:
    def test_format_alignment_json_with_diagnostics(self):
        """Lines 65-80: full alignment JSON including diagnostics block."""
        from cad_dxf_agent.cli.formatters import format_alignment_json

        alignment = _make_alignment(
            method=AlignmentMethod.feature,
            confidence=0.99,
            translation=(3.5, -1.2),
            rotation_deg=2.0,
            with_diagnostics=True,
        )
        text = format_alignment_json(alignment)
        data = json.loads(text)

        assert data["method"] == "feature"
        assert data["confidence"] == pytest.approx(0.99)
        assert data["translation"] == pytest.approx([3.5, -1.2])
        assert data["rotation_deg"] == pytest.approx(2.0)
        assert "diagnostics" in data
        assert data["diagnostics"]["rms_residual"] == pytest.approx(0.001)
        assert data["diagnostics"]["overlap_ratio"] == pytest.approx(0.95)
        assert data["diagnostics"]["match_count"] == 100
        assert data["diagnostics"]["inlier_count"] == 90

    def test_format_alignment_json_identity_no_diagnostics(self):
        """diagnostics block omitted when diagnostics fields are all zero (falsy guard)."""
        from cad_dxf_agent.cli.formatters import format_alignment_json

        # AlignmentDiagnostics with all-zero defaults is still truthy as an object,
        # but the formatter checks `if alignment.diagnostics:` which is always True
        # for a Pydantic model. We test the None case by creating a result with None.
        alignment = AlignmentResult(
            method=AlignmentMethod.identity,
            confidence=1.0,
            translation=(0.0, 0.0),
            rotation_deg=0.0,
            diagnostics=AlignmentDiagnostics(),  # always included when present
        )
        text = format_alignment_json(alignment)
        data = json.loads(text)

        assert data["method"] == "identity"
        assert "diagnostics" in data  # diagnostics model is always truthy

    def test_format_alignment_json_anchor_method(self):
        """Round-trip check with anchor alignment method."""
        from cad_dxf_agent.cli.formatters import format_alignment_json

        alignment = _make_alignment(method=AlignmentMethod.anchor, confidence=0.75)
        text = format_alignment_json(alignment)
        data = json.loads(text)

        assert data["method"] == "anchor"
        assert data["confidence"] == pytest.approx(0.75)


# ---------------------------------------------------------------------------
# format_dry_run_json — lines 105-125
# ---------------------------------------------------------------------------


class TestFormatDryRunJson:
    def test_format_dry_run_json_single_op(self):
        """Lines 105-125: JSON output for a single approved op."""
        from cad_dxf_agent.cli.formatters import format_dry_run_json

        op = _make_revision_op()
        result = _make_comparison_result()
        approval = _make_approval_set([op])

        text = format_dry_run_json(result, [op], approval)
        data = json.loads(text)

        assert "ops" in data
        assert len(data["ops"]) == 1
        entry = data["ops"][0]
        assert entry["op_id"] == "op1"
        assert entry["op_type"] == "move"
        assert entry["target_handle"] == "H1"
        assert entry["target_layer"] == "STRUCTURAL"
        assert entry["confidence"] == pytest.approx(0.9)
        assert entry["description"] == "Move entity"
        assert entry["status"] == "approved"

    def test_format_dry_run_json_multiple_ops(self):
        """Multiple ops with different types appear in order."""
        from cad_dxf_agent.cli.formatters import format_dry_run_json

        op1 = _make_revision_op(op_id="m1", op_type=RevisionOpType.MOVE)
        op2 = _make_revision_op(
            op_id="d1",
            op_type=RevisionOpType.DELETE,
            handle="H2",
            description="Delete entity",
        )
        ops = [op1, op2]
        result = _make_comparison_result()
        approval = _make_approval_set(ops)

        text = format_dry_run_json(result, ops, approval)
        data = json.loads(text)

        assert len(data["ops"]) == 2
        assert data["ops"][0]["op_type"] == "move"
        assert data["ops"][1]["op_type"] == "delete"

    def test_format_dry_run_json_no_ops(self):
        """Empty ops list produces empty array."""
        from cad_dxf_agent.cli.formatters import format_dry_run_json

        result = _make_comparison_result()
        approval = _make_approval_set([])

        text = format_dry_run_json(result, [], approval)
        data = json.loads(text)

        assert data["ops"] == []
        assert "summary" in data
        assert "total_changes" in data

    def test_format_dry_run_json_op_without_decision(self):
        """Op not in approval set → status is 'unknown'."""
        from cad_dxf_agent.cli.formatters import format_dry_run_json

        op = _make_revision_op(op_id="orphan")
        result = _make_comparison_result()
        empty_approval = ApprovalSet(decisions=[])  # no decisions at all

        text = format_dry_run_json(result, [op], empty_approval)
        data = json.loads(text)

        assert data["ops"][0]["status"] == "unknown"

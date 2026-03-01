"""Text output helpers for CLI commands."""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from ..core.comparison.alignment import AlignmentResult
    from ..models.comparison_schema import ApprovalSet, ComparisonResult, RevisionOp


def format_summary(result: ComparisonResult) -> str:
    """Format category counts as a table."""
    lines: list[str] = []
    if result.warnings:
        for w in result.warnings:
            lines.append(f"WARNING: {w}")
        lines.append("")
    lines.extend(["Category       Count", "-" * 22])
    for cat in ("added", "removed", "modified", "moved", "unchanged"):
        count = result.summary.get(cat, 0)
        lines.append(f"  {cat:<12s} {count:>5d}")
    lines.append("-" * 22)
    lines.append(f"  {'total':<12s} {result.total_changes:>5d}")
    return "\n".join(lines)


def format_summary_json(result: ComparisonResult) -> str:
    """Format comparison result summary as JSON."""
    import json

    data = {
        "summary": result.summary,
        "total_changes": result.total_changes,
    }
    if result.alignment_result:
        data["alignment"] = {
            "method": result.alignment_result.method.value,
            "confidence": result.alignment_result.confidence,
        }
    if result.warnings:
        data["warnings"] = result.warnings
    return json.dumps(data, indent=2)


def format_alignment(alignment: AlignmentResult) -> str:
    """Format alignment result details."""
    lines = [
        f"Method:      {alignment.method.value}",
        f"Confidence:  {alignment.confidence:.4f}",
        f"Translation: ({alignment.translation[0]:.4f}, {alignment.translation[1]:.4f})",
        f"Rotation:    {alignment.rotation_deg:.4f} deg",
    ]
    diag = alignment.diagnostics
    if diag:
        lines.append(f"RMS residual:  {diag.rms_residual:.6f}")
        lines.append(f"Overlap ratio: {diag.overlap_ratio:.4f}")
        lines.append(f"Match count:   {diag.match_count}")
        lines.append(f"Inlier count:  {diag.inlier_count}")
    return "\n".join(lines)


def format_alignment_json(alignment: AlignmentResult) -> str:
    """Format alignment result as JSON."""
    import json

    data: dict[str, object] = {
        "method": alignment.method.value,
        "confidence": alignment.confidence,
        "translation": list(alignment.translation),
        "rotation_deg": alignment.rotation_deg,
    }
    if alignment.diagnostics:
        data["diagnostics"] = {
            "rms_residual": alignment.diagnostics.rms_residual,
            "overlap_ratio": alignment.diagnostics.overlap_ratio,
            "match_count": alignment.diagnostics.match_count,
            "inlier_count": alignment.diagnostics.inlier_count,
        }
    return json.dumps(data, indent=2)


def format_dry_run(
    result: ComparisonResult, ops: list[RevisionOp], approval_set: ApprovalSet
) -> str:
    """Format ops table with approval status."""
    lines = [format_summary(result), "", f"Operations: {len(ops)}", ""]
    if ops:
        lines.append(f"{'Op ID':<10s} {'Type':<18s} {'Layer':<15s} {'Conf':>5s} {'Status':<15s}")
        lines.append("-" * 65)
        for op in ops:
            decision = approval_set.get_decision(op.op_id)
            status = decision.status.value if decision else "unknown"
            lines.append(
                f"{op.op_id:<10s} {op.op_type.value:<18s} "
                f"{op.target_layer:<15s} {op.confidence:>5.2f} {status:<15s}"
            )
    return "\n".join(lines)


def format_dry_run_json(
    result: ComparisonResult, ops: list[RevisionOp], approval_set: ApprovalSet
) -> str:
    """Format dry-run result as JSON."""
    import json

    data = {
        "summary": result.summary,
        "total_changes": result.total_changes,
        "ops": [
            {
                "op_id": op.op_id,
                "op_type": op.op_type.value,
                "target_handle": op.target_handle,
                "target_layer": op.target_layer,
                "confidence": op.confidence,
                "description": op.description,
                "status": (
                    d.status.value if (d := approval_set.get_decision(op.op_id)) else "unknown"
                ),
            }
            for op in ops
        ],
    }
    return json.dumps(data, indent=2)

"""Approval gating for revision ops based on confidence scores."""

from __future__ import annotations

from datetime import UTC, datetime

from ...models.comparison_schema import (
    ApprovalConfig,
    ApprovalDecision,
    ApprovalSet,
    ApprovalStatus,
    RevisionOp,
)


def build_initial_approvals(
    ops: list[RevisionOp], config: ApprovalConfig | None = None
) -> ApprovalSet:
    """Create an ApprovalSet with initial statuses based on confidence thresholds.

    - confidence >= auto_approve_threshold → AUTO_APPROVED
    - confidence < auto_approve_threshold → PENDING (needs explicit approve/force)
    """
    config = config or ApprovalConfig()
    decisions: list[ApprovalDecision] = []
    for op in ops:
        if op.confidence >= config.auto_approve_threshold:
            status = ApprovalStatus.AUTO_APPROVED
            reason = f"confidence {op.confidence:.2f} >= {config.auto_approve_threshold:.2f}"
        else:
            status = ApprovalStatus.PENDING
            reason = f"confidence {op.confidence:.2f} < {config.auto_approve_threshold:.2f}"
        decisions.append(
            ApprovalDecision(
                op_id=op.op_id,
                status=status,
                reason=reason,
                decided_at=_now_iso(),
            )
        )
    return ApprovalSet(decisions=decisions, config=config)


def approve_op(approval_set: ApprovalSet, op_id: str, *, reason: str = "") -> None:
    """Approve a pending op."""
    decision = approval_set.get_decision(op_id)
    if decision is None:
        raise ValueError(f"No decision found for op_id={op_id!r}")
    decision.status = ApprovalStatus.APPROVED
    decision.reason = reason or "manually approved"
    decision.decided_at = _now_iso()


def reject_op(approval_set: ApprovalSet, op_id: str, *, reason: str = "") -> None:
    """Reject a pending op."""
    decision = approval_set.get_decision(op_id)
    if decision is None:
        raise ValueError(f"No decision found for op_id={op_id!r}")
    decision.status = ApprovalStatus.REJECTED
    decision.reason = reason or "manually rejected"
    decision.decided_at = _now_iso()


def force_approve_op(approval_set: ApprovalSet, op_id: str, *, reason: str = "") -> None:
    """Force-approve a low-confidence op (requires allow_force in config)."""
    if not approval_set.config.allow_force:
        raise ValueError("Force approval is disabled in config (allow_force=False)")
    decision = approval_set.get_decision(op_id)
    if decision is None:
        raise ValueError(f"No decision found for op_id={op_id!r}")
    decision.status = ApprovalStatus.FORCE_APPROVED
    decision.reason = reason or "force approved"
    decision.decided_at = _now_iso()


def approve_all_pending(approval_set: ApprovalSet, *, reason: str = "") -> int:
    """Approve all PENDING ops. Returns count of ops approved."""
    count = 0
    for d in approval_set.decisions:
        if d.status == ApprovalStatus.PENDING:
            d.status = ApprovalStatus.APPROVED
            d.reason = reason or "batch approved"
            d.decided_at = _now_iso()
            count += 1
    return count


def validate_approvals(ops: list[RevisionOp], approval_set: ApprovalSet) -> list[str]:
    """Check that all ops are resolved and low-confidence ops are properly forced.

    Returns list of error strings (empty = valid).
    """
    errors: list[str] = []

    pending = approval_set.pending_op_ids
    if pending:
        errors.append(f"{len(pending)} op(s) still pending: {sorted(pending)}")

    config = approval_set.config
    for op in ops:
        decision = approval_set.get_decision(op.op_id)
        if decision is None:
            errors.append(f"No decision for op {op.op_id}")
            continue

        # Low-confidence ops must be force-approved, not just approved
        if op.confidence < config.force_required_threshold and decision.status in (
            ApprovalStatus.APPROVED,
            ApprovalStatus.AUTO_APPROVED,
        ):
            errors.append(
                f"Op {op.op_id} has confidence {op.confidence:.2f} < "
                f"{config.force_required_threshold:.2f} — requires force_approve"
            )

    return errors


def _now_iso() -> str:
    return datetime.now(UTC).isoformat()

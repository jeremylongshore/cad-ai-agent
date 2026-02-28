"""DXF comparison engine — deterministic geometry diff between master and revision."""

from .alignment import align_drawings, apply_alignment
from .applier import RevisionApplier
from .approval import (
    approve_all_pending,
    approve_op,
    build_initial_approvals,
    force_approve_op,
    reject_op,
    validate_approvals,
)
from .bundle import dry_run, export_bundle
from .canonical import (
    assign_stable_ids,
    compute_signature,
    compute_stable_id,
    sort_changes,
    sort_snapshots,
)
from .changelog import ChangeLog, generate_changelog
from .classifier import classify_changes
from .diff_overlay import write_diff_overlay
from .engine import ComparisonEngine
from .geometry import extract_snapshots
from .matcher import match_entities
from .revision_ops import comparison_result_to_ops, entity_change_to_ops
from .scorer import score_match

__all__ = [
    "ChangeLog",
    "ComparisonEngine",
    "RevisionApplier",
    "align_drawings",
    "apply_alignment",
    "approve_all_pending",
    "approve_op",
    "assign_stable_ids",
    "build_initial_approvals",
    "classify_changes",
    "comparison_result_to_ops",
    "compute_signature",
    "compute_stable_id",
    "dry_run",
    "entity_change_to_ops",
    "export_bundle",
    "extract_snapshots",
    "force_approve_op",
    "generate_changelog",
    "match_entities",
    "reject_op",
    "score_match",
    "sort_changes",
    "sort_snapshots",
    "validate_approvals",
    "write_diff_overlay",
]

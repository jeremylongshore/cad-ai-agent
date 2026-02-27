"""DXF comparison engine — deterministic geometry diff between master and revision."""

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

__all__ = [
    "ChangeLog",
    "ComparisonEngine",
    "assign_stable_ids",
    "classify_changes",
    "compute_signature",
    "compute_stable_id",
    "extract_snapshots",
    "generate_changelog",
    "match_entities",
    "sort_changes",
    "sort_snapshots",
    "write_diff_overlay",
]

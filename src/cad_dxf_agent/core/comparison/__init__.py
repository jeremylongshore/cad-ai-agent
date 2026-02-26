"""DXF comparison engine — deterministic geometry diff between master and revision."""

from .changelog import ChangeLog, generate_changelog
from .classifier import classify_changes
from .diff_overlay import write_diff_overlay
from .engine import ComparisonEngine
from .geometry import extract_snapshots
from .matcher import match_entities

__all__ = [
    "ChangeLog",
    "ComparisonEngine",
    "classify_changes",
    "extract_snapshots",
    "generate_changelog",
    "match_entities",
    "write_diff_overlay",
]

"""Change log generation — JSON and human-readable output."""

from __future__ import annotations

import math
from datetime import UTC, datetime

from pydantic import BaseModel, Field

from ...models.comparison_schema import (
    ChangeCategory,
    ComparisonResult,
    EntityChange,
)
from ...otel import get_tracer

tracer = get_tracer(__name__)


class ChangeLogEntry(BaseModel):
    """One entry in the change log."""

    category: str
    entity_type: str
    layer: str
    description: str
    from_point: dict[str, float] | None = None
    to_point: dict[str, float] | None = None


class ChangeLog(BaseModel):
    """Structured change log for a comparison result."""

    generated_at: str = Field(default_factory=lambda: datetime.now(UTC).isoformat())
    summary: dict[str, int] = Field(default_factory=dict)
    entries: list[ChangeLogEntry] = Field(default_factory=list)

    def to_json(self, indent: int = 2) -> str:
        """Serialize to JSON string."""
        return self.model_dump_json(indent=indent)

    def to_text(self) -> str:
        """Generate human-readable change log."""
        lines: list[str] = []
        lines.append("=" * 60)
        lines.append("CHANGE LOG")
        lines.append(f"Generated: {self.generated_at}")
        lines.append("=" * 60)
        lines.append("")

        # Summary
        lines.append("SUMMARY")
        lines.append("-" * 30)
        for category, count in self.summary.items():
            if count > 0:
                lines.append(f"  {category.upper():12s}: {count}")
        lines.append("")

        # Group entries by category
        by_category: dict[str, list[ChangeLogEntry]] = {}
        for entry in self.entries:
            by_category.setdefault(entry.category, []).append(entry)

        for category in ("added", "removed", "modified", "moved"):
            entries = by_category.get(category, [])
            if not entries:
                continue
            lines.append(f"{category.upper()} ({len(entries)})")
            lines.append("-" * 30)
            for entry in entries:
                lines.append(f"  - {entry.description}")
            lines.append("")

        return "\n".join(lines)


def generate_changelog(result: ComparisonResult) -> ChangeLog:
    """Build a ChangeLog from a ComparisonResult.

    Args:
        result: The classified comparison result.

    Returns:
        ChangeLog with entries for every non-unchanged change.
    """
    with tracer.start_as_current_span("cad.compare.generate_changelog") as span:
        entries: list[ChangeLogEntry] = []

        for change in result.changes:
            if change.category == ChangeCategory.UNCHANGED:
                continue
            entry = _build_entry(change)
            entries.append(entry)

        span.set_attribute("cad.compare.entries_count", len(entries))

        return ChangeLog(
            summary=result.summary,
            entries=entries,
        )


def _build_entry(change: EntityChange) -> ChangeLogEntry:
    """Build a single change log entry."""
    snap = change.revision_snapshot or change.master_snapshot
    entity_type = snap.entity_type.value if snap else "UNKNOWN"
    layer = snap.layer if snap else "UNKNOWN"

    from_point = None
    to_point = None

    if change.category == ChangeCategory.ADDED:
        assert change.revision_snapshot is not None
        c = change.revision_snapshot.centroid
        to_point = {"x": round(c.x, 4), "y": round(c.y, 4)}
        desc = _describe_added(change)

    elif change.category == ChangeCategory.REMOVED:
        assert change.master_snapshot is not None
        c = change.master_snapshot.centroid
        from_point = {"x": round(c.x, 4), "y": round(c.y, 4)}
        desc = _describe_removed(change)

    elif change.category == ChangeCategory.MOVED:
        assert change.master_snapshot is not None
        assert change.revision_snapshot is not None
        mc = change.master_snapshot.centroid
        rc = change.revision_snapshot.centroid
        from_point = {"x": round(mc.x, 4), "y": round(mc.y, 4)}
        to_point = {"x": round(rc.x, 4), "y": round(rc.y, 4)}
        desc = _describe_moved(change)

    elif change.category == ChangeCategory.MODIFIED:
        assert change.master_snapshot is not None
        mc = change.master_snapshot.centroid
        from_point = {"x": round(mc.x, 4), "y": round(mc.y, 4)}
        desc = _describe_modified(change)

    else:
        desc = f"{entity_type} on {layer}: unknown change"

    return ChangeLogEntry(
        category=change.category.value,
        entity_type=entity_type,
        layer=layer,
        description=desc,
        from_point=from_point,
        to_point=to_point,
    )


def _describe_added(change: EntityChange) -> str:
    snap = change.revision_snapshot
    assert snap is not None
    c = snap.centroid
    base = f"{snap.entity_type.value} added on layer {snap.layer} at ({c.x:.1f}, {c.y:.1f})"
    if snap.text_content:
        base += f' — text: "{snap.text_content}"'
    if snap.block_name:
        base += f" — block: {snap.block_name}"
    return base


def _describe_removed(change: EntityChange) -> str:
    snap = change.master_snapshot
    assert snap is not None
    c = snap.centroid
    base = f"{snap.entity_type.value} removed from layer {snap.layer} at ({c.x:.1f}, {c.y:.1f})"
    if snap.text_content:
        base += f' — text: "{snap.text_content}"'
    if snap.block_name:
        base += f" — block: {snap.block_name}"
    return base


def _describe_moved(change: EntityChange) -> str:
    snap = change.master_snapshot
    assert snap is not None
    assert change.displacement is not None
    c = snap.centroid
    dx = change.displacement.x
    dy = change.displacement.y
    return (
        f"{snap.entity_type.value} on layer {snap.layer} "
        f"moved from ({c.x:.1f}, {c.y:.1f}) "
        f"by ({dx:+.1f}, {dy:+.1f})"
    )


def _describe_modified(change: EntityChange) -> str:
    snap = change.master_snapshot
    assert snap is not None
    c = snap.centroid
    parts = [f"{snap.entity_type.value} on layer {snap.layer} modified at ({c.x:.1f}, {c.y:.1f})"]
    if change.modifications:
        if "text_content" in change.modifications:
            tc = change.modifications["text_content"]
            parts.append(f'text: "{tc["from"]}" → "{tc["to"]}"')
        if "point_count" in change.modifications:
            pc = change.modifications["point_count"]
            parts.append(f"points: {pc['from']} → {pc['to']}")
        if "radius" in change.modifications:
            r = change.modifications["radius"]
            parts.append(f"radius: {r['from']} → {r['to']}")
    return " — ".join(parts)


class DiffSummary(BaseModel):
    """Human-readable summary of a comparison result with warnings."""

    headline: str = Field(description="e.g. '12 changes: 3 added, 2 removed, 4 modified, 3 moved'")
    warnings: list[str] = Field(default_factory=list)
    by_layer: dict[str, dict[str, int]] = Field(
        default_factory=dict,
        description="Change counts grouped by layer, e.g. {'STRUCT': {'added': 2, 'moved': 1}}",
    )


def generate_summary(result: ComparisonResult) -> DiffSummary:
    """Build a human-readable summary with warnings from a ComparisonResult."""
    # Build headline
    parts = []
    for cat in ("added", "removed", "modified", "moved"):
        count = result.summary.get(cat, 0)
        if count > 0:
            parts.append(f"{count} {cat}")

    total = result.total_changes
    headline = (
        f"{total} change{'s' if total != 1 else ''}: {', '.join(parts)}"
        if parts
        else "No changes detected"
    )

    # Build by_layer
    by_layer: dict[str, dict[str, int]] = {}
    for change in result.changes:
        if change.category.value == "unchanged":
            continue
        snap = change.revision_snapshot or change.master_snapshot
        if snap is None:
            continue
        layer = snap.layer
        cat = change.category.value
        if layer not in by_layer:
            by_layer[layer] = {}
        by_layer[layer][cat] = by_layer[layer].get(cat, 0) + 1

    # Generate warnings
    warnings: list[str] = []

    # Large moves (displacement > 10 units)
    large_moves = 0
    for change in result.changes:
        if change.displacement is not None:
            dist = math.sqrt(change.displacement.x**2 + change.displacement.y**2)
            if dist > 10.0:
                large_moves += 1
    if large_moves > 0:
        warnings.append(f"{large_moves} entit{'ies' if large_moves != 1 else 'y'} moved >10 units")

    # Low-confidence matches
    low_conf = sum(
        1
        for c in result.changes
        if c.confidence < 0.6 and c.category.value not in ("added", "removed", "unchanged")
    )
    if low_conf > 0:
        warnings.append(f"{low_conf} low-confidence match{'es' if low_conf != 1 else ''} (<0.6)")

    # High remove count
    master_total = (
        result.summary.get("removed", 0)
        + result.summary.get("moved", 0)
        + result.summary.get("modified", 0)
        + result.summary.get("unchanged", 0)
    )
    if master_total > 0:
        remove_pct = result.summary.get("removed", 0) / master_total
        if remove_pct > 0.5:
            warnings.append(
                f"{result.summary['removed']} entities removed (>{remove_pct:.0%} of master)"
            )

    return DiffSummary(headline=headline, warnings=warnings, by_layer=by_layer)

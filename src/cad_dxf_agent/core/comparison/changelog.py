"""Change log generation — JSON and human-readable output."""

from __future__ import annotations

from datetime import UTC, datetime

from pydantic import BaseModel, Field

from ...models.comparison_schema import (
    ChangeCategory,
    ComparisonResult,
    EntityChange,
)


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
    entries: list[ChangeLogEntry] = []

    for change in result.changes:
        if change.category == ChangeCategory.UNCHANGED:
            continue
        entry = _build_entry(change)
        entries.append(entry)

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

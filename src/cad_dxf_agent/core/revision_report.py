"""Revision report — human-readable comparison summary with delta analysis.

Combines the comparison engine's structured changelog with zone detection
on both drawing versions to produce area deltas and a plain-language
revision summary for project managers and stakeholders.

Public API:
    generate_revision_report(master, revision, changelog) -> RevisionReport
"""

from __future__ import annotations

from pydantic import BaseModel, Field

from cad_dxf_agent.core.comparison.changelog import ChangeLog, ChangeLogEntry
from cad_dxf_agent.core.zone_detector import detect_zones
from cad_dxf_agent.models.cad_schema import DrawingContext
from cad_dxf_agent.models.zone_schema import ZoneDetectionResult


class ZoneDelta(BaseModel):
    """Change in a single zone between revisions."""

    zone_type: str
    status: str  # "added", "removed", "resized", "unchanged"
    old_area: float | None = None
    new_area: float | None = None
    area_change: float = 0.0


class ChangeCategorySummary(BaseModel):
    """Summary of changes by category (added, modified, removed, moved)."""

    category: str
    count: int
    layers_affected: list[str] = Field(default_factory=list)
    sample_descriptions: list[str] = Field(default_factory=list)


class RevisionReport(BaseModel):
    """Structured revision report combining diff + zone analysis."""

    headline: str
    total_changes: int = 0
    change_categories: list[ChangeCategorySummary] = Field(
        default_factory=list,
    )
    zone_deltas: list[ZoneDelta] = Field(default_factory=list)
    old_total_area: float = 0.0
    new_total_area: float = 0.0
    area_change: float = 0.0
    old_zone_count: int = 0
    new_zone_count: int = 0
    plain_summary: str = ""


def generate_revision_report(
    master_context: DrawingContext,
    revision_context: DrawingContext,
    changelog: ChangeLog,
    *,
    master_zones: ZoneDetectionResult | None = None,
    revision_zones: ZoneDetectionResult | None = None,
) -> RevisionReport:
    """Generate a human-readable revision report.

    Args:
        master_context: Original drawing context.
        revision_context: Revised drawing context.
        changelog: Structured change log from comparison engine.
        master_zones: Pre-computed zones for master (computed if None).
        revision_zones: Pre-computed zones for revision (computed if None).

    Returns:
        RevisionReport with change categories, zone deltas, and summary.
    """
    if master_zones is None:
        master_zones = detect_zones(master_context)
    if revision_zones is None:
        revision_zones = detect_zones(revision_context)

    # Categorize changes
    change_categories = _categorize_changes(changelog.entries)

    # Compute zone deltas
    zone_deltas = _compute_zone_deltas(master_zones, revision_zones)

    old_total = master_zones.total_area
    new_total = revision_zones.total_area
    area_change = new_total - old_total

    # Build headline and summary
    headline = _build_headline(changelog, zone_deltas, area_change)
    plain_summary = _build_plain_summary(
        changelog,
        change_categories,
        zone_deltas,
        area_change,
        master_context,
        revision_context,
    )

    return RevisionReport(
        headline=headline,
        total_changes=len(changelog.entries),
        change_categories=change_categories,
        zone_deltas=zone_deltas,
        old_total_area=round(old_total, 1),
        new_total_area=round(new_total, 1),
        area_change=round(area_change, 1),
        old_zone_count=master_zones.zone_count,
        new_zone_count=revision_zones.zone_count,
        plain_summary=plain_summary,
    )


def _categorize_changes(
    entries: list[ChangeLogEntry],
) -> list[ChangeCategorySummary]:
    """Group changelog entries by category."""
    by_cat: dict[str, list[ChangeLogEntry]] = {}
    for entry in entries:
        by_cat.setdefault(entry.category, []).append(entry)

    summaries: list[ChangeCategorySummary] = []
    for category, cat_entries in sorted(by_cat.items()):
        layers = sorted({e.layer for e in cat_entries})
        descriptions = [e.description for e in cat_entries[:5]]
        summaries.append(
            ChangeCategorySummary(
                category=category,
                count=len(cat_entries),
                layers_affected=layers,
                sample_descriptions=descriptions,
            )
        )

    return summaries


def _compute_zone_deltas(
    master_zones: ZoneDetectionResult,
    revision_zones: ZoneDetectionResult,
) -> list[ZoneDelta]:
    """Compare zones between versions to find added/removed/resized spaces."""
    deltas: list[ZoneDelta] = []

    # Build lookup by inferred_type for comparison
    old_by_type: dict[str, list[float]] = {}
    for zone in master_zones.zones:
        zone_type = zone.inferred_type or "unknown"
        old_by_type.setdefault(zone_type, []).append(zone.area)

    new_by_type: dict[str, list[float]] = {}
    for zone in revision_zones.zones:
        zone_type = zone.inferred_type or "unknown"
        new_by_type.setdefault(zone_type, []).append(zone.area)

    all_types = sorted(set(old_by_type.keys()) | set(new_by_type.keys()))

    for zone_type in all_types:
        old_areas = sorted(old_by_type.get(zone_type, []))
        new_areas = sorted(new_by_type.get(zone_type, []))

        old_count = len(old_areas)
        new_count = len(new_areas)

        if old_count == 0 and new_count > 0:
            # All zones of this type are new
            for area in new_areas:
                deltas.append(
                    ZoneDelta(
                        zone_type=zone_type,
                        status="added",
                        new_area=round(area, 1),
                        area_change=round(area, 1),
                    )
                )
        elif old_count > 0 and new_count == 0:
            # All zones of this type were removed
            for area in old_areas:
                deltas.append(
                    ZoneDelta(
                        zone_type=zone_type,
                        status="removed",
                        old_area=round(area, 1),
                        area_change=round(-area, 1),
                    )
                )
        else:
            # Compare counts
            matched = min(old_count, new_count)
            for i in range(matched):
                old_a = old_areas[i]
                new_a = new_areas[i]
                change = new_a - old_a
                status = "resized" if abs(change) > 0.1 else "unchanged"
                deltas.append(
                    ZoneDelta(
                        zone_type=zone_type,
                        status=status,
                        old_area=round(old_a, 1),
                        new_area=round(new_a, 1),
                        area_change=round(change, 1),
                    )
                )

            # Extra new zones
            for i in range(matched, new_count):
                deltas.append(
                    ZoneDelta(
                        zone_type=zone_type,
                        status="added",
                        new_area=round(new_areas[i], 1),
                        area_change=round(new_areas[i], 1),
                    )
                )

            # Extra removed zones
            for i in range(matched, old_count):
                deltas.append(
                    ZoneDelta(
                        zone_type=zone_type,
                        status="removed",
                        old_area=round(old_areas[i], 1),
                        area_change=round(-old_areas[i], 1),
                    )
                )

    return deltas


def _build_headline(
    changelog: ChangeLog,
    zone_deltas: list[ZoneDelta],
    area_change: float,
) -> str:
    """Build a concise headline summarizing the revision."""
    parts: list[str] = []
    parts.append(f"{len(changelog.entries)} change(s) detected")

    added = sum(1 for d in zone_deltas if d.status == "added")
    removed = sum(1 for d in zone_deltas if d.status == "removed")
    resized = sum(1 for d in zone_deltas if d.status == "resized")

    delta_parts: list[str] = []
    if added:
        delta_parts.append(f"{added} room(s) added")
    if removed:
        delta_parts.append(f"{removed} room(s) removed")
    if resized:
        delta_parts.append(f"{resized} room(s) resized")

    if delta_parts:
        parts.append(", ".join(delta_parts))

    if abs(area_change) > 0.1:
        sign = "+" if area_change > 0 else ""
        parts.append(f"net area: {sign}{area_change:.0f} sq units")

    return " — ".join(parts)


def _build_plain_summary(
    changelog: ChangeLog,
    change_categories: list[ChangeCategorySummary],
    zone_deltas: list[ZoneDelta],
    area_change: float,
    master_context: DrawingContext,
    revision_context: DrawingContext,
) -> str:
    """Build a multi-sentence plain-English summary."""
    sentences: list[str] = []

    sentences.append(
        f"Comparison of '{master_context.file_path}' "
        f"and '{revision_context.file_path}': "
        f"{len(changelog.entries)} change(s) detected."
    )

    if change_categories:
        cat_strs = [f"{c.count} {c.category}" for c in change_categories]
        sentences.append(f"Changes: {', '.join(cat_strs)}.")

    added = [d for d in zone_deltas if d.status == "added"]
    removed = [d for d in zone_deltas if d.status == "removed"]
    resized = [d for d in zone_deltas if d.status == "resized"]

    if added:
        types = ", ".join(d.zone_type for d in added[:3])
        sentences.append(f"{len(added)} space(s) added: {types}.")

    if removed:
        types = ", ".join(d.zone_type for d in removed[:3])
        sentences.append(f"{len(removed)} space(s) removed: {types}.")

    if resized:
        sentences.append(f"{len(resized)} space(s) resized.")

    if abs(area_change) > 0.1:
        sign = "+" if area_change > 0 else ""
        sentences.append(f"Net area change: {sign}{area_change:.0f} square units.")

    return " ".join(sentences)

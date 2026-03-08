"""RFI generator — detect ambiguities and missing information in drawings.

Deterministic analysis producing structured RFI (Request for Information)
items that a contractor would typically raise about incomplete or
ambiguous drawing details.

Public API:
    generate_rfi(context, zones=None) -> RFIReport
"""

from __future__ import annotations

import re
from collections import Counter

from cad_dxf_agent.core.zone_detector import detect_zones
from cad_dxf_agent.models.cad_schema import DrawingContext, EntityType
from cad_dxf_agent.models.rfi_schema import (
    RFICategory,
    RFIItem,
    RFIReport,
    RFISeverity,
)
from cad_dxf_agent.models.zone_schema import ZoneDetectionResult

# Block patterns for symbol detection
_DOOR_PATTERN = re.compile(r"door|dr[_\-\s]|entry|exit|gate", re.IGNORECASE)
_WINDOW_PATTERN = re.compile(r"window|wndw|win[_\-\s]|glazing", re.IGNORECASE)


def generate_rfi(
    context: DrawingContext,
    *,
    zones: ZoneDetectionResult | None = None,
) -> RFIReport:
    """Generate RFI items from drawing analysis.

    Args:
        context: Drawing context with entities.
        zones: Pre-computed zone detection (computed if None).

    Returns:
        RFIReport with categorized questions.
    """
    if zones is None:
        zones = detect_zones(context)

    items: list[RFIItem] = []
    checks_run: list[str] = []
    rfi_counter = 0

    for check_fn, check_name in _ALL_CHECKS:
        checks_run.append(check_name)
        new_items = check_fn(context, zones, rfi_counter)
        rfi_counter += len(new_items)
        items.extend(new_items)

    critical = sum(1 for i in items if i.severity == RFISeverity.CRITICAL)
    major = sum(1 for i in items if i.severity == RFISeverity.MAJOR)
    minor = sum(1 for i in items if i.severity == RFISeverity.MINOR)

    return RFIReport(
        items=items,
        total_items=len(items),
        critical_count=critical,
        major_count=major,
        minor_count=minor,
        checks_run=checks_run,
        entity_count=context.entity_count,
        zone_count=zones.zone_count,
    )


# --- Check functions ---


def _check_unlabeled_rooms(
    context: DrawingContext,
    zones: ZoneDetectionResult,
    start_id: int,
) -> list[RFIItem]:
    """Flag rooms/zones that have no inferred type label."""
    items: list[RFIItem] = []

    for zone in zones.zones:
        if zone.inferred_type is None:
            items.append(
                RFIItem(
                    rfi_id=f"RFI-{start_id + len(items) + 1:03d}",
                    category=RFICategory.MISSING_LABEL,
                    severity=RFISeverity.MAJOR,
                    question=(
                        f"What is the intended use of the space at "
                        f"({zone.centroid.x:.0f}, {zone.centroid.y:.0f})?"
                    ),
                    location_description=(
                        f"Zone {zone.zone_id[:8]} — area {zone.area:.0f} "
                        f"sq units, no room label detected"
                    ),
                    zone_id=zone.zone_id,
                    entity_handles=zone.source_handles,
                    suggested_resolution="Add a room name/label text entity inside the space.",
                )
            )

    return items


def _check_dimensions_near_doors(
    context: DrawingContext,
    zones: ZoneDetectionResult,
    start_id: int,
) -> list[RFIItem]:
    """Flag doors that have no nearby DIMENSION entity."""
    items: list[RFIItem] = []

    doors = [
        e
        for e in context.entities
        if e.entity_type == EntityType.INSERT
        and e.block_name
        and _DOOR_PATTERN.search(e.block_name)
    ]

    if not doors:
        return items

    dim_entities = [
        e
        for e in context.entities
        if e.entity_type == EntityType.DIMENSION and e.insert_point is not None
    ]

    for door in doors:
        if door.insert_point is None:
            continue

        has_nearby_dim = False
        search_radius = 50.0

        for dim in dim_entities:
            dx = dim.insert_point.x - door.insert_point.x  # type: ignore[union-attr]
            dy = dim.insert_point.y - door.insert_point.y  # type: ignore[union-attr]
            if (dx * dx + dy * dy) ** 0.5 <= search_radius:
                has_nearby_dim = True
                break

        if not has_nearby_dim:
            items.append(
                RFIItem(
                    rfi_id=f"RFI-{start_id + len(items) + 1:03d}",
                    category=RFICategory.MISSING_DIMENSION,
                    severity=RFISeverity.CRITICAL,
                    question=(
                        f"What is the clear opening width of door "
                        f"'{door.block_name}' at "
                        f"({door.insert_point.x:.0f}, "
                        f"{door.insert_point.y:.0f})?"
                    ),
                    location_description=(
                        f"Door block '{door.block_name}' on layer "
                        f"'{door.layer}' — no dimension entity within "
                        f"{search_radius:.0f} units"
                    ),
                    entity_handles=[door.handle],
                    suggested_resolution=(
                        "Add a dimension entity showing door clear opening width."
                    ),
                )
            )

    return items


def _check_symbols_without_legend(
    context: DrawingContext,
    zones: ZoneDetectionResult,
    start_id: int,
) -> list[RFIItem]:
    """Flag unique block names that don't appear in any text legend."""
    items: list[RFIItem] = []

    inserts = [e for e in context.entities if e.entity_type == EntityType.INSERT and e.block_name]
    if not inserts:
        return items

    block_names = {e.block_name for e in inserts}

    # Collect all text content for legend searching
    all_text = " ".join(
        e.text_content.upper()
        for e in context.entities
        if e.entity_type in (EntityType.TEXT, EntityType.MTEXT) and e.text_content
    )

    for block_name in sorted(n for n in block_names if n is not None):
        # Check if block name (or simplified form) appears in text
        simplified = re.sub(r"[_\-\s]", "", block_name.upper())
        if block_name.upper() not in all_text and simplified not in all_text:
            handles = [e.handle for e in inserts if e.block_name == block_name][:5]
            items.append(
                RFIItem(
                    rfi_id=f"RFI-{start_id + len(items) + 1:03d}",
                    category=RFICategory.AMBIGUOUS_SYMBOL,
                    severity=RFISeverity.MINOR,
                    question=(
                        f"What does the symbol '{block_name}' represent? No legend entry found."
                    ),
                    location_description=(
                        f"Block '{block_name}' appears "
                        f"{len([e for e in inserts if e.block_name == block_name])} "
                        f"time(s) but is not referenced in any text/legend"
                    ),
                    entity_handles=handles,
                    suggested_resolution="Add a symbol legend or schedule referencing this block.",
                )
            )

    return items


def _check_empty_layers(
    context: DrawingContext,
    zones: ZoneDetectionResult,
    start_id: int,
) -> list[RFIItem]:
    """Flag layers that exist but have no entities (may be orphaned)."""
    items: list[RFIItem] = []

    entity_layers = {e.layer for e in context.entities}

    for layer in context.layers:
        if layer.name not in entity_layers and layer.name != "0":
            items.append(
                RFIItem(
                    rfi_id=f"RFI-{start_id + len(items) + 1:03d}",
                    category=RFICategory.INCOMPLETE_SECTION,
                    severity=RFISeverity.MINOR,
                    question=(
                        f"Layer '{layer.name}' exists but contains no entities. Is content missing?"
                    ),
                    location_description=f"Layer '{layer.name}' — 0 entities",
                    suggested_resolution=(
                        "Verify layer content was included in the export, "
                        "or remove the layer if unused."
                    ),
                )
            )

    return items


def _check_unclosed_boundaries(
    context: DrawingContext,
    zones: ZoneDetectionResult,
    start_id: int,
) -> list[RFIItem]:
    """Flag LWPOLYLINE entities that are nearly closed but not quite."""
    items: list[RFIItem] = []
    tolerance_close = 5.0  # "almost closed" threshold
    tolerance_actual = 0.5  # "actually closed" threshold

    for entity in context.entities:
        if entity.entity_type != EntityType.LWPOLYLINE:
            continue

        vertices = entity.attributes.get("vertices", [])
        if len(vertices) < 3:
            continue

        if entity.attributes.get("is_closed", False):
            continue

        # Check gap between first and last vertex
        first = vertices[0]
        last = vertices[-1]
        dx = first[0] - last[0]
        dy = first[1] - last[1]
        gap = (dx * dx + dy * dy) ** 0.5

        if tolerance_actual < gap <= tolerance_close:
            pos = entity.insert_point
            loc = f"({pos.x:.0f}, {pos.y:.0f})" if pos else "unknown"
            items.append(
                RFIItem(
                    rfi_id=f"RFI-{start_id + len(items) + 1:03d}",
                    category=RFICategory.COORDINATION,
                    severity=RFISeverity.MAJOR,
                    question=(
                        f"Polyline on layer '{entity.layer}' at {loc} "
                        f"has a {gap:.1f}-unit gap. Should this boundary "
                        f"be closed?"
                    ),
                    location_description=(
                        f"LWPOLYLINE {entity.handle} on layer "
                        f"'{entity.layer}' — gap of {gap:.1f} units "
                        f"between first and last vertex"
                    ),
                    entity_handles=[entity.handle],
                    suggested_resolution="Close the polyline or confirm the gap is intentional.",
                )
            )

    return items


def _check_mixed_text_heights(
    context: DrawingContext,
    zones: ZoneDetectionResult,
    start_id: int,
) -> list[RFIItem]:
    """Flag layers with inconsistent text heights (may indicate drafting errors)."""
    items: list[RFIItem] = []

    # Group text heights by layer
    layer_heights: dict[str, Counter[float]] = {}
    for entity in context.entities:
        if entity.entity_type not in (EntityType.TEXT, EntityType.MTEXT):
            continue
        height = entity.text_geometry.effective_height if entity.text_geometry else None
        if height is not None and height > 0:
            height = round(height, 2)
            layer_heights.setdefault(entity.layer, Counter())[height] += 1

    for layer, height_counts in layer_heights.items():
        if len(height_counts) < 3:
            continue

        # Find the dominant height
        dominant_height, dominant_count = height_counts.most_common(1)[0]
        total = sum(height_counts.values())
        outlier_count = total - dominant_count

        if outlier_count >= 2 and outlier_count / total > 0.1:
            outlier_heights = sorted(h for h in height_counts if h != dominant_height)
            items.append(
                RFIItem(
                    rfi_id=f"RFI-{start_id + len(items) + 1:03d}",
                    category=RFICategory.COORDINATION,
                    severity=RFISeverity.MINOR,
                    question=(
                        f"Layer '{layer}' has {len(height_counts)} "
                        f"different text heights. Is this intentional?"
                    ),
                    location_description=(
                        f"Layer '{layer}' — dominant height "
                        f"{dominant_height}, also has "
                        f"{', '.join(str(h) for h in outlier_heights[:3])}"
                    ),
                    suggested_resolution=(
                        "Standardize text heights per layer, or confirm "
                        "variations are intentional (e.g., titles vs labels)."
                    ),
                )
            )

    return items


# --- Check registry ---

_ALL_CHECKS = [
    (_check_unlabeled_rooms, "unlabeled_rooms"),
    (_check_dimensions_near_doors, "dimensions_near_doors"),
    (_check_symbols_without_legend, "symbols_without_legend"),
    (_check_empty_layers, "empty_layers"),
    (_check_unclosed_boundaries, "unclosed_boundaries"),
    (_check_mixed_text_heights, "mixed_text_heights"),
]

"""Takeoff engine — automated quantity extraction from drawings.

Orchestrates zone areas, symbol counts, linear measurements, and
block counts into a structured TakeoffReport. Deterministic (no LLM).

Public API:
    generate_takeoff(context, zones=None) -> TakeoffReport
"""

from __future__ import annotations

import math
from collections import Counter

from cad_dxf_agent.core.zone_detector import detect_zones
from cad_dxf_agent.models.cad_schema import DrawingContext, EntityRef, EntityType
from cad_dxf_agent.models.takeoff_schema import (
    TakeoffCategory,
    TakeoffReport,
    TakeoffReportItem,
)
from cad_dxf_agent.models.zone_schema import ZoneDetectionResult


def generate_takeoff(
    context: DrawingContext,
    *,
    zones: ZoneDetectionResult | None = None,
) -> TakeoffReport:
    """Generate a comprehensive takeoff report from a drawing.

    Args:
        context: Drawing context with entities.
        zones: Pre-computed zone detection result (computed if None).

    Returns:
        TakeoffReport with categorized items.
    """
    if zones is None:
        zones = detect_zones(context)

    items: list[TakeoffReportItem] = []

    # 1. Block/symbol counts
    items.extend(_count_symbols(context))

    # 2. Linear measurements (wall lengths, pipe runs, etc.)
    items.extend(_measure_linear(context))

    # 3. Zone areas (room square footage)
    items.extend(_measure_zone_areas(zones))

    # 4. Entity counts per layer
    items.extend(_count_by_layer(context))

    return TakeoffReport(
        items=items,
        total_items=len(items),
        zone_count=zones.zone_count,
        entity_count=context.entity_count,
    )


def _count_symbols(context: DrawingContext) -> list[TakeoffReportItem]:
    """Count INSERT blocks by block name."""
    items: list[TakeoffReportItem] = []
    by_block: dict[str, list[EntityRef]] = {}

    for entity in context.entities:
        if entity.entity_type != EntityType.INSERT:
            continue
        if not entity.block_name:
            continue
        by_block.setdefault(entity.block_name, []).append(entity)

    for block_name, entities in sorted(by_block.items()):
        layers = sorted({e.layer for e in entities})
        handles = [e.handle for e in entities]
        items.append(
            TakeoffReportItem(
                name=block_name,
                category=TakeoffCategory.SYMBOL,
                quantity=len(entities),
                unit="ea",
                source_layer=layers[0] if layers else None,
                entity_handles=handles,
                notes=f"Block inserts across {len(layers)} layer(s)",
            )
        )

    return items


def _measure_linear(context: DrawingContext) -> list[TakeoffReportItem]:
    """Measure total linear length of LINE and LWPOLYLINE entities per layer."""
    items: list[TakeoffReportItem] = []
    layer_lengths: dict[str, float] = {}
    layer_handles: dict[str, list[str]] = {}

    for entity in context.entities:
        length = _entity_length(entity)
        if length <= 0:
            continue

        layer_lengths[entity.layer] = layer_lengths.get(entity.layer, 0) + length
        layer_handles.setdefault(entity.layer, []).append(entity.handle)

    for layer, total_length in sorted(layer_lengths.items()):
        handles = layer_handles.get(layer, [])
        items.append(
            TakeoffReportItem(
                name=f"Linear on '{layer}'",
                category=TakeoffCategory.LINEAR,
                quantity=round(total_length, 2),
                unit="drawing_units",
                source_layer=layer,
                entity_handles=handles[:20],
                notes=f"{len(handles)} segment(s)",
            )
        )

    return items


def _measure_zone_areas(zones: ZoneDetectionResult) -> list[TakeoffReportItem]:
    """Extract area measurements from detected zones."""
    items: list[TakeoffReportItem] = []

    for zone in zones.zones:
        zone_type = zone.inferred_type or "unknown"
        items.append(
            TakeoffReportItem(
                name=f"{zone_type.replace('_', ' ').title()} ({zone.zone_id[:8]})",
                category=TakeoffCategory.AREA,
                quantity=round(zone.area, 2),
                unit="sq_drawing_units",
                zone_id=zone.zone_id,
                entity_handles=zone.source_handles,
                notes=f"Perimeter: {zone.perimeter:.1f}",
            )
        )

    return items


def _count_by_layer(context: DrawingContext) -> list[TakeoffReportItem]:
    """Count non-INSERT entities per layer."""
    items: list[TakeoffReportItem] = []
    layer_counts: Counter[str] = Counter()
    layer_handles: dict[str, list[str]] = {}

    for entity in context.entities:
        if entity.entity_type == EntityType.INSERT:
            continue
        layer_counts[entity.layer] += 1
        layer_handles.setdefault(entity.layer, []).append(entity.handle)

    for layer, count in layer_counts.most_common():
        if count < 2:
            continue
        handles = layer_handles.get(layer, [])
        items.append(
            TakeoffReportItem(
                name=f"Entities on '{layer}'",
                category=TakeoffCategory.COUNT,
                quantity=count,
                unit="ea",
                source_layer=layer,
                entity_handles=handles[:20],
            )
        )

    return items


def _entity_length(entity: EntityRef) -> float:
    """Compute length of a LINE or LWPOLYLINE entity."""
    if entity.entity_type == EntityType.LINE:
        return _line_length(entity)
    if entity.entity_type == EntityType.LWPOLYLINE:
        return _polyline_length(entity)
    return 0.0


def _line_length(entity: EntityRef) -> float:
    """Compute length of a LINE entity from start/end points."""
    if entity.insert_point is None:
        return 0.0
    end = entity.attributes.get("end_point")
    if end is None:
        return 0.0
    dx = end[0] - entity.insert_point.x
    dy = end[1] - entity.insert_point.y
    return math.sqrt(dx * dx + dy * dy)


def _polyline_length(entity: EntityRef) -> float:
    """Compute total length of a LWPOLYLINE from its vertices."""
    vertices = entity.attributes.get("vertices", [])
    if len(vertices) < 2:
        return 0.0
    total = 0.0
    for i in range(len(vertices) - 1):
        dx = vertices[i + 1][0] - vertices[i][0]
        dy = vertices[i + 1][1] - vertices[i][1]
        total += math.sqrt(dx * dx + dy * dy)

    # Add closing segment if closed
    if entity.attributes.get("is_closed", False) and len(vertices) >= 3:
        dx = vertices[0][0] - vertices[-1][0]
        dy = vertices[0][1] - vertices[-1][1]
        total += math.sqrt(dx * dx + dy * dy)

    return total

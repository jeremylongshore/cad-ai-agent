"""Selection and markup debug inspection tooling.

Generates structured debug payloads for engineering verification of
region mapping, entity association, confidence scoring, and ambiguity signals.
"""

from __future__ import annotations

from typing import Any

from ..models.region_schema import NormalizedRegion
from .region_associator import AssociatedEntity, AssociationResult


def build_debug_payload(result: AssociationResult) -> dict[str, Any]:
    """Build a structured debug payload for a region association result.

    Returns a JSON-serializable dict containing:
    - region: the normalized region with bounds, center, confidence
    - mapped_coordinates: bounding box and center in drawing space
    - associated_entities: ranked list of entities with distance and type
    - confidence: overall association confidence
    - ambiguity_signals: all flags from region and association
    """
    region = result.region

    return {
        "region": _serialize_region(region),
        "mapped_coordinates": {
            "bounds": {
                "min_x": region.bounds.min_x,
                "min_y": region.bounds.min_y,
                "max_x": region.bounds.max_x,
                "max_y": region.bounds.max_y,
            },
            "center": {"x": region.center.x, "y": region.center.y},
            "radius": region.radius,
            "area": region.bounds.area,
        },
        "associated_entities": [_serialize_entity(e) for e in result.entities],
        "summary": {
            "entity_count": result.entity_count,
            "inside_count": len(result.inside_entities),
            "nearby_count": len(result.nearby_entities),
            "label_count": len(result.labels),
            "dimension_count": len(result.dimensions),
            "layers": result.layers,
            "block_names": result.block_names,
        },
        "confidence": {
            "region_confidence": region.confidence,
            "association_confidence": result.confidence,
        },
        "ambiguity_signals": _collect_ambiguity(region, result),
    }


def format_debug_text(result: AssociationResult) -> str:
    """Format a human-readable debug summary for terminal/log output."""
    region = result.region
    lines = [
        f"=== Selection Debug: {region.region_id} ===",
        f"Source type: {region.source_type.value}",
        f"Coordinate space: {region.coordinate_space.value}",
        f"Bounds: ({region.bounds.min_x:.2f}, {region.bounds.min_y:.2f}) → "
        f"({region.bounds.max_x:.2f}, {region.bounds.max_y:.2f})",
        f"Center: ({region.center.x:.2f}, {region.center.y:.2f})",
        f"Area: {region.bounds.area:.2f}",
    ]

    if region.radius is not None:
        lines.append(f"Radius: {region.radius:.2f}")

    lines.extend(
        [
            f"Region confidence: {region.confidence:.3f}",
            f"Association confidence: {result.confidence:.3f}",
            f"Entity count: {result.entity_count}",
            f"  Inside: {len(result.inside_entities)}",
            f"  Nearby: {len(result.nearby_entities)}",
            f"  Labels: {len(result.labels)}",
            f"  Dimensions: {len(result.dimensions)}",
            f"Layers: {', '.join(result.layers) or '(none)'}",
            f"Blocks: {', '.join(result.block_names) or '(none)'}",
        ]
    )

    flags = _collect_ambiguity(region, result)
    if flags:
        lines.append(f"Ambiguity: {', '.join(flags)}")
    else:
        lines.append("Ambiguity: (none)")

    if result.entities:
        lines.append("")
        lines.append("--- Top entities ---")
        for e in result.entities[:10]:
            ent = e.entity
            label = ent.text_content or ent.block_name or ent.entity_type.value
            lines.append(
                f"  #{e.rank} [{e.association_type.value}] "
                f"{ent.handle} {label} "
                f"layer={ent.layer} dist={e.distance:.2f}"
            )

    return "\n".join(lines)


def _serialize_region(region: NormalizedRegion) -> dict[str, Any]:
    """Serialize region metadata for debug output."""
    data: dict[str, Any] = {
        "region_id": region.region_id,
        "source_type": region.source_type.value,
        "coordinate_space": region.coordinate_space.value,
        "schema_version": region.schema_version,
    }
    if region.page_ref:
        data["page_ref"] = region.page_ref
    if region.source_markup:
        data["source_markup"] = {
            "markup_id": region.source_markup.markup_id,
            "markup_type": region.source_markup.markup_type.value,
            "point_count": len(region.source_markup.source_points),
        }
    if region.polygon:
        data["polygon_point_count"] = len(region.polygon)
    return data


def _serialize_entity(assoc: AssociatedEntity) -> dict[str, Any]:
    """Serialize an associated entity for debug output."""
    ent = assoc.entity
    data: dict[str, Any] = {
        "rank": assoc.rank,
        "handle": ent.handle,
        "entity_type": ent.entity_type.value,
        "layer": ent.layer,
        "association_type": assoc.association_type.value,
        "distance": round(assoc.distance, 4),
    }
    if ent.insert_point:
        data["position"] = {"x": ent.insert_point.x, "y": ent.insert_point.y}
    if ent.text_content:
        data["text"] = ent.text_content
    if ent.block_name:
        data["block_name"] = ent.block_name
    return data


def _collect_ambiguity(region: NormalizedRegion, result: AssociationResult) -> list[str]:
    """Collect all ambiguity flags from region and association."""
    flags = list(region.ambiguity_flags)
    flags.extend(result.ambiguity_flags)
    return flags

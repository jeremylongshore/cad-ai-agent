"""Drawing summarizer — plain-English explanation of any drawing.

Deterministic (no LLM). Combines entity statistics, zone detection,
family detection, and primitive extraction to produce a structured
summary accessible to non-CAD users.

Public API:
    summarize_drawing(context, zones=None) -> DrawingSummary
"""

from __future__ import annotations

from pydantic import BaseModel, Field

from cad_dxf_agent.core.family_detector import detect_document_family
from cad_dxf_agent.core.primitive_extractors import classify_layers, extract_symbols
from cad_dxf_agent.core.zone_detector import detect_zones
from cad_dxf_agent.models.cad_schema import DrawingContext, EntityType
from cad_dxf_agent.models.zone_schema import ZoneDetectionResult


class RoomSummary(BaseModel):
    """Summary of a single detected room."""

    name: str
    area: float
    zone_id: str


class DrawingSummary(BaseModel):
    """Structured plain-English summary of a drawing."""

    headline: str
    drawing_type: str
    entity_count: int = 0
    layer_count: int = 0
    total_area: float = 0.0
    room_count: int = 0
    rooms: list[RoomSummary] = Field(default_factory=list)
    key_features: list[str] = Field(default_factory=list)
    layer_breakdown: list[str] = Field(default_factory=list)
    plain_description: str = ""


def summarize_drawing(
    context: DrawingContext,
    *,
    zones: ZoneDetectionResult | None = None,
) -> DrawingSummary:
    """Generate a plain-English summary of a drawing.

    Args:
        context: Drawing context with entities.
        zones: Pre-computed zone detection (computed if None).

    Returns:
        DrawingSummary with headline, rooms, features, and description.
    """
    if zones is None:
        zones = detect_zones(context)

    family = detect_document_family(context)
    layer_cls = classify_layers(context)
    symbols = extract_symbols(context)

    # Drawing type from family detection
    drawing_type = family.family.value.replace("_", " ").title()

    # Room summaries from zones
    rooms: list[RoomSummary] = []
    for zone in zones.zones:
        room_name = (zone.inferred_type or "unknown space").replace("_", " ").title()
        rooms.append(RoomSummary(
            name=room_name,
            area=round(zone.area, 1),
            zone_id=zone.zone_id,
        ))

    # Key features
    key_features = _extract_key_features(context, zones, symbols)

    # Layer breakdown
    layer_breakdown = _build_layer_breakdown(context, layer_cls)

    # Build headline
    headline = _build_headline(drawing_type, context, zones, rooms)

    # Build plain description
    plain_description = _build_description(
        drawing_type, context, zones, rooms, key_features,
    )

    return DrawingSummary(
        headline=headline,
        drawing_type=drawing_type,
        entity_count=context.entity_count,
        layer_count=len(context.layers),
        total_area=round(zones.total_area, 1),
        room_count=len(rooms),
        rooms=rooms,
        key_features=key_features,
        layer_breakdown=layer_breakdown,
        plain_description=plain_description,
    )


def _extract_key_features(
    context: DrawingContext,
    zones: ZoneDetectionResult,
    symbols,
) -> list[str]:
    """Extract notable features as short descriptions."""
    features: list[str] = []

    # Entity type distribution
    type_counts: dict[str, int] = {}
    for entity in context.entities:
        t = entity.entity_type.value
        type_counts[t] = type_counts.get(t, 0) + 1

    if EntityType.INSERT.value in type_counts:
        count = type_counts[EntityType.INSERT.value]
        features.append(f"{count} symbol(s) placed ({symbols.unique_blocks} unique block types)")

    if EntityType.DIMENSION.value in type_counts:
        features.append(f"{type_counts[EntityType.DIMENSION.value]} dimension(s)")

    if EntityType.TEXT.value in type_counts or EntityType.MTEXT.value in type_counts:
        text_count = (
            type_counts.get(EntityType.TEXT.value, 0)
            + type_counts.get(EntityType.MTEXT.value, 0)
        )
        features.append(f"{text_count} text label(s)")

    # Zone features
    if zones.zone_count > 0:
        room_types = set()
        for zone in zones.zones:
            if zone.inferred_type:
                room_types.add(zone.inferred_type.replace("_", " "))
        if room_types:
            features.append(f"Room types: {', '.join(sorted(room_types))}")

    # Block highlights
    if symbols.unique_blocks > 0:
        top_blocks = sorted(
            symbols.counts_by_block.items(),
            key=lambda x: x[1],
            reverse=True,
        )[:3]
        for block_name, count in top_blocks:
            features.append(f"{count}x {block_name}")

    return features


def _build_layer_breakdown(context: DrawingContext, layer_cls) -> list[str]:
    """Build layer descriptions."""
    breakdown: list[str] = []

    # Count entities per layer
    layer_entity_counts: dict[str, int] = {}
    for entity in context.entities:
        layer_entity_counts[entity.layer] = layer_entity_counts.get(entity.layer, 0) + 1

    for layer in context.layers:
        count = layer_entity_counts.get(layer.name, 0)
        if count > 0:
            category = _classify_single_layer(layer.name, layer_cls)
            breakdown.append(f"{layer.name}: {count} entities ({category})")

    return breakdown


def _classify_single_layer(name: str, layer_cls) -> str:
    """Classify a single layer name into a category."""
    if name in layer_cls.structural:
        return "structural"
    if name in layer_cls.annotation:
        return "annotation"
    if name in layer_cls.dimension:
        return "dimension"
    if name in layer_cls.title_border:
        return "title/border"
    if name in layer_cls.mep:
        return "MEP"
    return "general"


def _build_headline(
    drawing_type: str,
    context: DrawingContext,
    zones: ZoneDetectionResult,
    rooms: list[RoomSummary],
) -> str:
    """Build a concise headline summarizing the drawing."""
    parts = [drawing_type]

    if zones.zone_count > 0:
        room_type_counts: dict[str, int] = {}
        for room in rooms:
            room_type_counts[room.name] = room_type_counts.get(room.name, 0) + 1

        type_strs = []
        for rtype, count in sorted(room_type_counts.items()):
            if count > 1:
                type_strs.append(f"{count} {rtype}s")
            else:
                type_strs.append(rtype)

        if type_strs:
            parts.append(f"with {', '.join(type_strs[:4])}")

    parts.append(f"— {context.entity_count} entities")

    return " ".join(parts)


def _build_description(
    drawing_type: str,
    context: DrawingContext,
    zones: ZoneDetectionResult,
    rooms: list[RoomSummary],
    key_features: list[str],
) -> str:
    """Build a multi-sentence plain-English description."""
    sentences: list[str] = []

    sentences.append(
        f"This is a {drawing_type.lower()} drawing containing "
        f"{context.entity_count} entities across "
        f"{len(context.layers)} layers."
    )

    if zones.zone_count > 0:
        sentences.append(
            f"{zones.zone_count} enclosed space(s) detected "
            f"with a total area of {zones.total_area:.0f} square units."
        )

        if rooms:
            room_list = ", ".join(
                f"{r.name} ({r.area:.0f} sq units)" for r in rooms[:5]
            )
            sentences.append(f"Spaces: {room_list}.")
    else:
        sentences.append("No enclosed spaces detected.")

    if key_features:
        sentences.append(
            f"Key features: {'; '.join(key_features[:4])}."
        )

    return " ".join(sentences)

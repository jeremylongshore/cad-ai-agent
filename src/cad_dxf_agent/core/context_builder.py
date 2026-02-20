"""Context builder — produces LLM-friendly structured context from DrawingContext.

Two serialization modes:
  - full_context: all entities, layers, blocks
  - subset_context: entities around a target set or bounding region

Token-economy summaries provide compact overviews (counts, top text labels)
for prompt construction without sending the entire entity list.
"""

from __future__ import annotations

from collections import Counter
from typing import Any

from ..models.cad_schema import DrawingContext, EntityRef, EntityType
from .entity_index import EntityIndex


def full_context(context: DrawingContext) -> dict[str, Any]:
    """Serialize the full drawing context as LLM-friendly structured JSON.

    Includes all entities, layers, blocks, metadata, and summary statistics.
    """
    return {
        "file_path": context.file_path,
        "entity_count": context.entity_count,
        "layers": _serialize_layers(context),
        "entities": _serialize_entities(context.entities),
        "blocks": context.blocks,
        "unsupported_types": context.unsupported_entity_types,
        "metadata": dict(context.metadata),
        "summary": token_economy_summary(context),
    }


def subset_context(
    context: DrawingContext,
    *,
    entity_ids: list[str] | None = None,
    center: tuple[float, float] | None = None,
    radius: float | None = None,
    layers: list[str] | None = None,
    entity_types: list[str] | None = None,
) -> dict[str, Any]:
    """Serialize a subset of the drawing context.

    Filters entities by any combination of:
      - entity_ids: explicit list of handles to include
      - center + radius: spatial bounding circle
      - layers: layer name filter
      - entity_types: entity type filter

    When multiple filters are provided, they are intersected.
    """
    index = EntityIndex(context)
    candidates = set(e.handle for e in context.entities)

    if entity_ids is not None:
        candidates &= set(entity_ids)

    if layers is not None:
        layer_handles: set[str] = set()
        for layer in layers:
            layer_handles.update(e.handle for e in index.get_by_layer(layer))
        candidates &= layer_handles

    if entity_types is not None:
        type_handles: set[str] = set()
        for et in entity_types:
            try:
                etype = EntityType(et)
                type_handles.update(e.handle for e in index.get_by_type(etype))
            except ValueError:
                continue
        candidates &= type_handles

    if center is not None and radius is not None:
        cx, cy = center
        spatial_handles: set[str] = set()
        for entity in context.entities:
            if entity.insert_point is None:
                continue
            dx = entity.insert_point.x - cx
            dy = entity.insert_point.y - cy
            if (dx * dx + dy * dy) <= radius * radius:
                spatial_handles.add(entity.handle)
        candidates &= spatial_handles

    # Preserve insertion order
    selected = [e for e in context.entities if e.handle in candidates]

    return {
        "file_path": context.file_path,
        "entity_count": len(selected),
        "total_entity_count": context.entity_count,
        "layers": _serialize_layers(context),
        "entities": _serialize_entities(selected),
        "blocks": context.blocks,
        "summary": _subset_summary(selected, context),
    }


def token_economy_summary(context: DrawingContext) -> dict[str, Any]:
    """Compact summary for prompt construction.

    Provides counts by layer and type, plus top N text labels,
    without sending the full entity list.
    """
    counts_by_layer: Counter[str] = Counter()
    counts_by_type: Counter[str] = Counter()
    text_labels: list[str] = []

    for entity in context.entities:
        counts_by_layer[entity.layer] += 1
        counts_by_type[entity.entity_type.value] += 1
        if entity.text_content:
            text_labels.append(entity.text_content)

    return {
        "entity_count": context.entity_count,
        "counts_by_layer": dict(counts_by_layer),
        "counts_by_type": dict(counts_by_type),
        "layer_count": len(context.layers),
        "block_count": len(context.blocks),
        "top_text_labels": text_labels[:10],
        "protected_layers": context.get_protected_layers(),
    }


# --- Internal helpers ---


def _serialize_layers(context: DrawingContext) -> list[dict[str, Any]]:
    """Serialize layer info with per-layer entity counts."""
    entity_counts: Counter[str] = Counter()
    for e in context.entities:
        entity_counts[e.layer.upper()] += 1

    return [
        {
            "name": layer.name,
            "protected": layer.protected,
            "entity_count": entity_counts.get(layer.name.upper(), 0),
        }
        for layer in context.layers
    ]


def _serialize_entities(entities: list[EntityRef]) -> list[dict[str, Any]]:
    """Serialize entity list as LLM-friendly dicts."""
    return [
        {
            "handle": e.handle,
            "type": e.entity_type.value,
            "layer": e.layer,
            "insert_point": (
                {"x": e.insert_point.x, "y": e.insert_point.y} if e.insert_point else None
            ),
            "text": e.text_content,
            "block_name": e.block_name,
        }
        for e in entities
    ]


def _subset_summary(selected: list[EntityRef], context: DrawingContext) -> dict[str, Any]:
    """Summary for a subset context."""
    counts_by_type: Counter[str] = Counter()
    for e in selected:
        counts_by_type[e.entity_type.value] += 1

    return {
        "selected_count": len(selected),
        "total_count": context.entity_count,
        "counts_by_type": dict(counts_by_type),
        "protected_layers": context.get_protected_layers(),
    }

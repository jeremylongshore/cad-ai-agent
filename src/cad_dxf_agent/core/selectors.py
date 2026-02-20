"""Deterministic selectors — resolve entity targets without LLM involvement.

These are building blocks for Phase 4 (validator + op executor) and
Phase 5 (LLM planner targeting). All resolution is deterministic:
same inputs always produce the same outputs.
"""

from __future__ import annotations

from ..models.cad_schema import DrawingContext, EntityRef
from .entity_index import EntityIndex


def resolve_target_by_id(context: DrawingContext, entity_id: str) -> EntityRef | None:
    """Resolve a single entity by its DXF handle (id).

    Returns None if no entity matches.
    """
    index = EntityIndex(context)
    return index.get_by_id(entity_id)


def resolve_targets_by_layer_type(
    context: DrawingContext,
    layer: str | None = None,
    entity_type: str | None = None,
) -> list[EntityRef]:
    """Resolve entities matching layer and/or type filters.

    Both filters are optional. When both are provided, returns
    the intersection. Returns results in stable insertion order.
    """
    index = EntityIndex(context)
    return index.filter(layer=layer, entity_type=entity_type)


def resolve_targets_by_text(context: DrawingContext, query: str) -> list[EntityRef]:
    """Resolve TEXT/MTEXT entities whose content matches the query.

    Uses normalized token matching (case-insensitive, all tokens
    must be present). Returns results in stable insertion order.
    """
    index = EntityIndex(context)
    return index.search_text(query)


def resolve_target_nearest_point(
    context: DrawingContext,
    x: float,
    y: float,
    layer: str | None = None,
    entity_type: str | None = None,
) -> EntityRef | None:
    """Resolve the entity nearest to a given point.

    Uses insert_point as center proxy and Euclidean distance.
    Optional layer/type filters narrow the candidate set.
    Returns None if no entities have an insert_point.
    """
    index = EntityIndex(context)
    return index.nearest(x, y, entity_type=entity_type, layer=layer)


def resolve_candidate_set(context: DrawingContext, prompt_hints: dict) -> list[EntityRef]:
    """Resolve a candidate set from structured prompt hints.

    Accepts a dict with optional keys:
      - "id": str — exact handle match (returns single-element list)
      - "layer": str — layer filter
      - "type": str — entity type filter
      - "text": str — text content search
      - "near_x", "near_y": float — spatial proximity center

    Filters are applied in priority order:
      1. If "id" is present and matches, return that entity only.
      2. Otherwise, combine layer/type/text filters (intersection).
      3. If near_x/near_y present, sort candidates by distance and
         return the closest match only.
    """
    # Priority 1: exact id match
    entity_id = prompt_hints.get("id")
    if entity_id:
        match = resolve_target_by_id(context, entity_id)
        if match:
            return [match]
        return []

    index = EntityIndex(context)

    # Build candidate set from layer + type filter
    layer = prompt_hints.get("layer")
    entity_type = prompt_hints.get("type")
    candidates = index.filter(layer=layer, entity_type=entity_type)
    candidate_handles = {e.handle for e in candidates}

    # Narrow by text search if provided
    text_query = prompt_hints.get("text")
    if text_query:
        text_matches = index.search_text(text_query)
        text_handles = {e.handle for e in text_matches}
        candidate_handles &= text_handles
        candidates = [e for e in candidates if e.handle in candidate_handles]

    # If spatial hint, return nearest only
    near_x = prompt_hints.get("near_x")
    near_y = prompt_hints.get("near_y")
    if near_x is not None and near_y is not None:
        # Find nearest among remaining candidates
        best = None
        best_dist = float("inf")
        for entity in candidates:
            if entity.insert_point is None:
                continue
            dx = entity.insert_point.x - float(near_x)
            dy = entity.insert_point.y - float(near_y)
            dist = dx * dx + dy * dy
            if dist < best_dist:
                best_dist = dist
                best = entity
        return [best] if best else []

    return candidates

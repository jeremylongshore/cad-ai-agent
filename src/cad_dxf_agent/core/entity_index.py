"""Entity index — fast lookup of entities by handle, layer, type, text, and spatial proximity."""

from __future__ import annotations

import math
from collections import defaultdict

from ..models.cad_schema import DrawingContext, EntityRef, EntityType


class EntityIndex:
    """In-memory index over DrawingContext entities for fast lookup.

    Supports deterministic lookup by handle, layer, type, text content,
    and spatial nearest-point queries using bbox-center distance.
    """

    def __init__(self, context: DrawingContext) -> None:
        self._by_handle: dict[str, EntityRef] = {}
        self._by_layer: dict[str, list[EntityRef]] = defaultdict(list)
        self._by_type: dict[EntityType, list[EntityRef]] = defaultdict(list)
        self._text_index: dict[str, list[EntityRef]] = defaultdict(list)
        self._all: list[EntityRef] = list(context.entities)

        for entity in context.entities:
            self._by_handle[entity.handle] = entity
            self._by_layer[entity.layer.upper()].append(entity)
            self._by_type[entity.entity_type].append(entity)

            if entity.text_content:
                for token in _normalize_tokens(entity.text_content):
                    self._text_index[token].append(entity)

    # --- Lookup by handle (aka "id") ---

    def get_by_handle(self, handle: str) -> EntityRef | None:
        """Lookup entity by DXF handle. Returns None if not found."""
        return self._by_handle.get(handle)

    def get_by_id(self, entity_id: str) -> EntityRef | None:
        """Alias for get_by_handle — lookup entity by its unique id."""
        return self._by_handle.get(entity_id)

    # --- Lookup by layer / type ---

    def get_by_layer(self, layer: str) -> list[EntityRef]:
        """Return all entities on the given layer (case-insensitive)."""
        return self._by_layer.get(layer.upper(), [])

    def get_by_type(self, entity_type: EntityType) -> list[EntityRef]:
        """Return all entities of the given type."""
        return self._by_type.get(entity_type, [])

    def filter(
        self,
        layer: str | None = None,
        entity_type: str | None = None,
    ) -> list[EntityRef]:
        """Filter entities by layer and/or type. Both are optional.

        When both are provided, returns the intersection.
        When neither is provided, returns all entities.
        """
        candidates = self._all

        if layer is not None:
            layer_set = set(
                e.handle for e in self._by_layer.get(layer.upper(), [])
            )
            candidates = [e for e in candidates if e.handle in layer_set]

        if entity_type is not None:
            try:
                etype = EntityType(entity_type)
            except ValueError:
                return []
            type_set = set(
                e.handle for e in self._by_type.get(etype, [])
            )
            candidates = [e for e in candidates if e.handle in type_set]

        return candidates

    # --- Text search ---

    def search_text(self, query: str) -> list[EntityRef]:
        """Search TEXT/MTEXT entities by normalized token match.

        Tokenizes the query and returns entities whose text content
        contains all query tokens (case-insensitive, order-independent).
        Returns results in stable insertion order.
        """
        query_tokens = _normalize_tokens(query)
        if not query_tokens:
            return []

        # Start with entities matching the first token, then intersect
        candidates: set[str] | None = None
        for token in query_tokens:
            matching_handles = {e.handle for e in self._text_index.get(token, [])}
            if candidates is None:
                candidates = matching_handles
            else:
                candidates &= matching_handles

        if not candidates:
            return []

        # Return in stable insertion order
        return [e for e in self._all if e.handle in candidates]

    # --- Spatial nearest ---

    def nearest(
        self,
        x: float,
        y: float,
        entity_type: str | None = None,
        layer: str | None = None,
    ) -> EntityRef | None:
        """Find the nearest entity to the given point using bbox-center distance.

        Uses insert_point as the center proxy. Entities without an
        insert_point are excluded. Optional layer/type filters narrow
        the candidate set.
        """
        candidates = self.filter(layer=layer, entity_type=entity_type)

        best: EntityRef | None = None
        best_dist = math.inf

        for entity in candidates:
            if entity.insert_point is None:
                continue
            dist = math.hypot(
                entity.insert_point.x - x,
                entity.insert_point.y - y,
            )
            if dist < best_dist:
                best_dist = dist
                best = entity

        return best

    # --- Utility ---

    def handles(self) -> list[str]:
        """Return all indexed handles."""
        return list(self._by_handle.keys())

    @property
    def count(self) -> int:
        """Total number of indexed entities."""
        return len(self._by_handle)


def _normalize_tokens(text: str) -> list[str]:
    """Normalize text into lowercase tokens for search indexing."""
    return text.lower().split()

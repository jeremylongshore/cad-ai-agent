"""Entity index — fast lookup of entities by handle, layer, type, text, and spatial proximity.

Uses an R-tree spatial index for O(log n) nearest-neighbor and radius queries,
replacing the O(n) linear scan that blocked large drawings.
"""

from __future__ import annotations

import math
from collections import defaultdict

from rtree import index as rtree_index

from ..models.cad_schema import DrawingContext, EntityRef, EntityType


class EntityIndex:
    """In-memory index over DrawingContext entities for fast lookup.

    Supports deterministic lookup by handle, layer, type, text content,
    and spatial queries via R-tree (nearest-point, radius window).
    """

    def __init__(self, context: DrawingContext) -> None:
        self._by_handle: dict[str, EntityRef] = {}
        self._by_layer: dict[str, list[EntityRef]] = defaultdict(list)
        self._by_type: dict[EntityType, list[EntityRef]] = defaultdict(list)
        self._text_index: dict[str, list[EntityRef]] = defaultdict(list)
        self._all: list[EntityRef] = list(context.entities)

        # R-tree spatial index for fast nearest/radius queries
        # Property 0 configures a 2D index; we store (x, y, x, y) bounding boxes
        p = rtree_index.Property()
        p.dimension = 2
        self._rtree = rtree_index.Index(properties=p)
        # Map R-tree integer IDs back to entity handles
        self._rtree_id_to_handle: dict[int, str] = {}
        rtree_id = 0

        for entity in context.entities:
            self._by_handle[entity.handle] = entity
            self._by_layer[entity.layer.upper()].append(entity)
            self._by_type[entity.entity_type].append(entity)

            # Index text content from TEXT, MTEXT, DIMENSION, MLEADER
            if entity.text_content:
                for token in _normalize_tokens(entity.text_content):
                    self._text_index[token].append(entity)

            # Insert into R-tree if entity has a position
            if entity.insert_point is not None:
                x = entity.insert_point.x
                y = entity.insert_point.y
                self._rtree.insert(rtree_id, (x, y, x, y))
                self._rtree_id_to_handle[rtree_id] = entity.handle
                rtree_id += 1

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
        limit: int | None = None,
    ) -> list[EntityRef]:
        """Filter entities by layer and/or type. Both are optional.

        When both are provided, returns the intersection.
        When neither is provided, returns all entities.
        Optional ``limit`` caps the number of results returned.
        """
        candidates = self._all

        if layer is not None:
            layer_set = set(e.handle for e in self._by_layer.get(layer.upper(), []))
            candidates = [e for e in candidates if e.handle in layer_set]

        if entity_type is not None:
            try:
                etype = EntityType(entity_type)
            except ValueError:
                return []
            type_set = set(e.handle for e in self._by_type.get(etype, []))
            candidates = [e for e in candidates if e.handle in type_set]

        if limit is not None and limit > 0:
            candidates = candidates[:limit]

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

    # --- Spatial nearest (R-tree accelerated) ---

    def nearest(
        self,
        x: float,
        y: float,
        entity_type: str | None = None,
        layer: str | None = None,
    ) -> EntityRef | None:
        """Find the nearest entity to the given point.

        Uses R-tree for fast spatial lookup. When layer/type filters are
        applied, falls back to filtered linear scan (filters narrow the
        candidate set first, then R-tree is not applicable).
        """
        if layer is not None or entity_type is not None:
            # Filtered query — use linear scan on filtered candidates
            return self._nearest_filtered(x, y, entity_type, layer)

        # Unfiltered — use R-tree nearest query
        results = list(self._rtree.nearest((x, y, x, y), 1))
        if not results:
            return None

        handle = self._rtree_id_to_handle.get(results[0])
        if handle is None:
            return None
        return self._by_handle.get(handle)

    def _nearest_filtered(
        self,
        x: float,
        y: float,
        entity_type: str | None,
        layer: str | None,
    ) -> EntityRef | None:
        """Nearest-entity with layer/type filters (linear scan on filtered set)."""
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

    # --- Spatial windowing (R-tree accelerated) ---

    def find_in_radius(
        self,
        x: float,
        y: float,
        radius: float,
        entity_type: str | None = None,
        layer: str | None = None,
    ) -> list[EntityRef]:
        """Find all entities within ``radius`` drawing units of (x, y).

        Uses R-tree bounding-box query for fast candidate retrieval,
        then exact distance check. When layer/type filters are applied,
        results are post-filtered.

        Results are sorted by distance (nearest first).
        """
        # R-tree bounding box query — get candidates in the square
        bbox = (x - radius, y - radius, x + radius, y + radius)
        rtree_hits = list(self._rtree.intersection(bbox))

        # Resolve handles and apply exact circular distance check
        r_sq = radius * radius
        results: list[tuple[float, EntityRef]] = []

        # Build filter sets if needed
        layer_set: set[str] | None = None
        type_set: set[str] | None = None
        if layer is not None:
            layer_set = {e.handle for e in self._by_layer.get(layer.upper(), [])}
        if entity_type is not None:
            try:
                etype = EntityType(entity_type)
            except ValueError:
                return []
            type_set = {e.handle for e in self._by_type.get(etype, [])}

        for rtree_id in rtree_hits:
            handle = self._rtree_id_to_handle.get(rtree_id)
            if handle is None:
                continue
            entity = self._by_handle.get(handle)
            if entity is None or entity.insert_point is None:
                continue

            # Apply filters
            if layer_set is not None and entity.handle not in layer_set:
                continue
            if type_set is not None and entity.handle not in type_set:
                continue

            # Exact distance check (R-tree gave us a square, we want a circle)
            dx = entity.insert_point.x - x
            dy = entity.insert_point.y - y
            dist_sq = dx * dx + dy * dy
            if dist_sq <= r_sq:
                results.append((dist_sq, entity))

        results.sort(key=lambda pair: pair[0])
        return [e for _, e in results]

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

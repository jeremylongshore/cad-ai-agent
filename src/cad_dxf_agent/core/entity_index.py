"""Entity index — fast lookup of entities by handle, layer, type, and spatial proximity."""

from __future__ import annotations

from collections import defaultdict

from ..models.cad_schema import DrawingContext, EntityRef, EntityType


class EntityIndex:
    """In-memory index over DrawingContext entities for fast lookup."""

    def __init__(self, context: DrawingContext) -> None:
        self._by_handle: dict[str, EntityRef] = {}
        self._by_layer: dict[str, list[EntityRef]] = defaultdict(list)
        self._by_type: dict[EntityType, list[EntityRef]] = defaultdict(list)

        for entity in context.entities:
            self._by_handle[entity.handle] = entity
            self._by_layer[entity.layer.upper()].append(entity)
            self._by_type[entity.entity_type].append(entity)

    def get_by_handle(self, handle: str) -> EntityRef | None:
        return self._by_handle.get(handle)

    def get_by_layer(self, layer: str) -> list[EntityRef]:
        return self._by_layer.get(layer.upper(), [])

    def get_by_type(self, entity_type: EntityType) -> list[EntityRef]:
        return self._by_type.get(entity_type, [])

    def handles(self) -> list[str]:
        return list(self._by_handle.keys())

    @property
    def count(self) -> int:
        return len(self._by_handle)

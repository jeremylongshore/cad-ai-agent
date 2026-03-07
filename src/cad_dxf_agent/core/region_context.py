"""Region context builder — wraps RegionAssociator to build bounded Q&A context.

Categorizes entities by type (text, dimension, block) and caps output
at max_entities to keep answer generation fast and predictable.
"""

from __future__ import annotations

from collections import Counter

from ..models.cad_schema import DrawingContext, EntityRef, EntityType
from ..models.qna_schema import RegionContext
from ..models.region_schema import BoundingBox, NormalizedRegion
from .entity_index import EntityIndex
from .region_associator import RegionAssociator

_TEXT_TYPES = frozenset({EntityType.TEXT, EntityType.MTEXT})
_DIMENSION_TYPES = frozenset({EntityType.DIMENSION, EntityType.LEADER})


class RegionContextBuilder:
    """Build RegionContext for Q&A from a drawing context and optional region."""

    def __init__(self, max_entities: int = 200, margin: float = 5.0) -> None:
        self._max_entities = max_entities
        self._margin = margin

    def build(
        self,
        context: DrawingContext,
        region: NormalizedRegion | None = None,
        index: EntityIndex | None = None,
    ) -> RegionContext:
        """Build a RegionContext from drawing entities.

        If region is provided, uses RegionAssociator to find entities
        in/near the region. Otherwise builds whole-drawing context.
        """
        if index is None:
            index = EntityIndex(context)

        if region is not None:
            return self._build_from_region(context, region, index)
        return self._build_whole_drawing(context)

    def _build_from_region(
        self,
        context: DrawingContext,
        region: NormalizedRegion,
        index: EntityIndex,
    ) -> RegionContext:
        associator = RegionAssociator(margin=self._margin)
        result = associator.associate(region, context, index)

        entities = [ae.entity for ae in result.entities]
        return self._categorize(
            entities=entities,
            total_drawing_entities=context.entity_count,
            is_whole_drawing=False,
            confidence=result.confidence,
            ambiguity_flags=list(result.ambiguity_flags),
            bounds=region.bounds,
        )

    def _build_whole_drawing(self, context: DrawingContext) -> RegionContext:
        entities = list(context.entities)
        flags: list[str] = []
        confidence = 1.0

        if not entities:
            flags.append("empty_drawing")
            confidence = 0.0

        return self._categorize(
            entities=entities,
            total_drawing_entities=context.entity_count,
            is_whole_drawing=True,
            confidence=confidence,
            ambiguity_flags=flags,
            bounds=None,
        )

    def _categorize(
        self,
        *,
        entities: list[EntityRef],
        total_drawing_entities: int,
        is_whole_drawing: bool,
        confidence: float,
        ambiguity_flags: list[str],
        bounds: BoundingBox | None,
    ) -> RegionContext:
        # Cap entities
        truncated = len(entities) > self._max_entities
        if truncated:
            entities = entities[: self._max_entities]
            ambiguity_flags.append("context_truncated")

        # Categorize by type
        text_entities = [e for e in entities if e.entity_type in _TEXT_TYPES]
        dimension_entities = [e for e in entities if e.entity_type in _DIMENSION_TYPES]
        block_refs = [e for e in entities if e.entity_type == EntityType.INSERT]

        # Layer stats
        layer_counter: Counter[str] = Counter(e.layer for e in entities)
        layers = sorted(layer_counter.keys())
        block_names = sorted({e.block_name for e in block_refs if e.block_name})

        return RegionContext(
            entities=entities,
            text_entities=text_entities,
            dimension_entities=dimension_entities,
            block_refs=block_refs,
            layers=layers,
            layer_counts=dict(layer_counter),
            block_names=block_names,
            entity_count=len(entities),
            total_drawing_entities=total_drawing_entities,
            confidence=confidence,
            ambiguity_flags=ambiguity_flags,
            is_whole_drawing=is_whole_drawing,
            bounds=bounds,
        )

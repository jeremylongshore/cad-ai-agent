"""Region-to-entity association — maps normalized regions to nearby CAD context.

For a given NormalizedRegion, finds entities inside or near the region,
identifies associated labels/text, dimensions, layers, and block references.
Ranks candidates by relevance and provides association confidence.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from enum import StrEnum

from ..models.cad_schema import DrawingContext, EntityRef, EntityType, Point2D
from ..models.region_schema import BoundingBox, NormalizedRegion
from .entity_index import EntityIndex

# Default search expansion beyond region bounds (drawing units)
_DEFAULT_MARGIN = 5.0

# Entity types considered "labels" for association purposes
_LABEL_TYPES = frozenset({EntityType.TEXT, EntityType.MTEXT})

# Entity types considered "dimensions"
_DIMENSION_TYPES = frozenset({EntityType.DIMENSION, EntityType.LEADER})


class AssociationType(StrEnum):
    """How an entity relates to the region."""

    INSIDE = "inside"
    NEARBY = "nearby"
    LABEL = "label"
    DIMENSION = "dimension"
    BLOCK_REF = "block_ref"


@dataclass
class AssociatedEntity:
    """An entity associated with a region, with distance and relation type."""

    entity: EntityRef
    distance: float
    association_type: AssociationType
    rank: int = 0


@dataclass
class AssociationResult:
    """Complete association context for a region."""

    region: NormalizedRegion
    entities: list[AssociatedEntity] = field(default_factory=list)
    layers: list[str] = field(default_factory=list)
    block_names: list[str] = field(default_factory=list)
    confidence: float = 0.0
    ambiguity_flags: list[str] = field(default_factory=list)
    entity_count: int = 0

    @property
    def inside_entities(self) -> list[AssociatedEntity]:
        return [e for e in self.entities if e.association_type == AssociationType.INSIDE]

    @property
    def nearby_entities(self) -> list[AssociatedEntity]:
        return [e for e in self.entities if e.association_type == AssociationType.NEARBY]

    @property
    def labels(self) -> list[AssociatedEntity]:
        return [e for e in self.entities if e.association_type == AssociationType.LABEL]

    @property
    def dimensions(self) -> list[AssociatedEntity]:
        return [e for e in self.entities if e.association_type == AssociationType.DIMENSION]


class RegionAssociator:
    """Associates NormalizedRegions with nearby CAD entities."""

    def __init__(self, margin: float = _DEFAULT_MARGIN) -> None:
        self._margin = margin

    def associate(
        self,
        region: NormalizedRegion,
        context: DrawingContext,
        index: EntityIndex | None = None,
    ) -> AssociationResult:
        """Find entities associated with the given region.

        Uses the EntityIndex for spatial queries. Builds one if not provided.
        Returns ranked candidates with association types and confidence.
        """
        if index is None:
            index = EntityIndex(context)

        candidates: list[AssociatedEntity] = []
        flags: list[str] = []

        # Expand search bounds by margin
        search_bounds = BoundingBox(
            min_x=region.bounds.min_x - self._margin,
            min_y=region.bounds.min_y - self._margin,
            max_x=region.bounds.max_x + self._margin,
            max_y=region.bounds.max_y + self._margin,
        )

        # Search radius: half the diagonal of the expanded bounds + margin
        search_radius = math.hypot(search_bounds.width, search_bounds.height) / 2 + self._margin

        # Find all entities within the search radius of the region center
        nearby = index.find_in_radius(region.center.x, region.center.y, search_radius)

        for entity in nearby:
            if entity.insert_point is None:
                continue

            dist = _distance_to_region(entity.insert_point, region)
            assoc_type = _classify_association(entity, dist, region)

            candidates.append(
                AssociatedEntity(
                    entity=entity,
                    distance=dist,
                    association_type=assoc_type,
                )
            )

        # Sort: inside first, then by distance
        candidates.sort(key=lambda c: (c.association_type != AssociationType.INSIDE, c.distance))

        # Assign ranks
        for i, c in enumerate(candidates):
            c.rank = i + 1

        # Collect unique layers and block names
        layers = sorted({c.entity.layer for c in candidates})
        block_names = sorted(
            {c.entity.block_name for c in candidates if c.entity.block_name is not None}
        )

        # Compute association confidence
        confidence = _compute_association_confidence(candidates, region, flags)

        return AssociationResult(
            region=region,
            entities=candidates,
            layers=layers,
            block_names=block_names,
            confidence=confidence,
            ambiguity_flags=flags,
            entity_count=len(candidates),
        )


def _distance_to_region(point: Point2D, region: NormalizedRegion) -> float:
    """Compute distance from a point to the nearest edge of the region.

    Returns 0.0 if the point is inside the region.
    """
    if region.contains_point(point):
        return 0.0

    # Distance to nearest edge of bounding box
    dx = max(region.bounds.min_x - point.x, 0, point.x - region.bounds.max_x)
    dy = max(region.bounds.min_y - point.y, 0, point.y - region.bounds.max_y)
    return math.hypot(dx, dy)


def _classify_association(
    entity: EntityRef, distance: float, region: NormalizedRegion
) -> AssociationType:
    """Classify how an entity relates to the region."""
    is_inside = distance == 0.0

    if entity.entity_type in _LABEL_TYPES:
        return AssociationType.LABEL
    if entity.entity_type in _DIMENSION_TYPES:
        return AssociationType.DIMENSION
    if entity.block_name is not None:
        return AssociationType.BLOCK_REF
    if is_inside:
        return AssociationType.INSIDE
    return AssociationType.NEARBY


def _compute_association_confidence(
    candidates: list[AssociatedEntity],
    region: NormalizedRegion,
    flags: list[str],
) -> float:
    """Compute confidence in the association result.

    Higher confidence when:
    - More entities are inside the region
    - Region has high source confidence
    - Entities are clustered (not widely scattered)
    """
    if not candidates:
        flags.append("no_entities_found")
        return 0.0

    inside_count = sum(1 for c in candidates if c.association_type == AssociationType.INSIDE)
    total = len(candidates)

    # Base confidence from region's own confidence
    confidence = region.confidence

    # Boost for entities found inside
    if inside_count > 0:
        inside_ratio = inside_count / total
        confidence *= 0.7 + 0.3 * inside_ratio
    else:
        # All entities are nearby but not inside — lower confidence
        confidence *= 0.5
        flags.append("no_entities_inside_region")

    # Penalize if too many candidates (ambiguous region)
    if total > 50:
        confidence *= 0.8
        flags.append("high_entity_count")

    return round(min(confidence, 1.0), 3)

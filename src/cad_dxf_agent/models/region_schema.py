"""Normalized region model for selection and markup interpretation.

Represents viewport selections, box/circle/freehand selections,
highlighted regions, and markup-mapped regions in a canonical form.
All regions can be converted to drawing-space coordinates for
downstream use by Q&A, compare, edit, and repeated-condition pipelines.
"""

from __future__ import annotations

import uuid
from enum import StrEnum
from typing import Any

from pydantic import BaseModel, Field

from .cad_schema import Point2D


class RegionType(StrEnum):
    """How the region was created."""

    VIEWPORT_BOX = "viewport_box"
    BOX_SELECT = "box_select"
    CIRCLE_SELECT = "circle_select"
    FREEHAND_LOOP = "freehand_loop"
    HIGHLIGHT = "highlight"
    MARKUP_MAPPED = "markup_mapped"


class CoordinateSpace(StrEnum):
    """Which coordinate space the region's values are expressed in."""

    DRAWING = "drawing"
    VIEWPORT = "viewport"
    IMAGE = "image"


class BoundingBox(BaseModel):
    """Axis-aligned bounding box in any coordinate space."""

    min_x: float
    min_y: float
    max_x: float
    max_y: float

    @property
    def width(self) -> float:
        return self.max_x - self.min_x

    @property
    def height(self) -> float:
        return self.max_y - self.min_y

    @property
    def center(self) -> Point2D:
        return Point2D(
            x=(self.min_x + self.max_x) / 2,
            y=(self.min_y + self.max_y) / 2,
        )

    @property
    def area(self) -> float:
        return self.width * self.height

    def contains_point(self, p: Point2D) -> bool:
        return self.min_x <= p.x <= self.max_x and self.min_y <= p.y <= self.max_y


class MarkupType(StrEnum):
    """Type of markup overlay annotation."""

    CIRCLE = "circle"
    BOX = "box"
    LOOP = "loop"
    ARROW = "arrow"
    HIGHLIGHT = "highlight"


class MarkupOverlay(BaseModel):
    """A single markup annotation from an image or PDF overlay.

    Source coordinates are in the overlay's native space (image pixels,
    PDF points, etc.). The markup parser maps these to drawing space.
    """

    markup_id: str = Field(default_factory=lambda: uuid.uuid4().hex[:12])
    markup_type: MarkupType
    source_points: list[Point2D] = Field(
        description="Points defining the markup shape in source coordinates"
    )
    source_metadata: dict[str, Any] = Field(
        default_factory=dict,
        description="Page number, image dimensions, DPI, etc.",
    )


class NormalizedRegion(BaseModel):
    """Canonical region in drawing-space coordinates.

    Usable by downstream systems: Q&A, compare, repeated_condition, edit_plan.
    """

    region_id: str = Field(default_factory=lambda: uuid.uuid4().hex[:12])
    source_type: RegionType
    coordinate_space: CoordinateSpace = CoordinateSpace.DRAWING
    bounds: BoundingBox
    center: Point2D
    radius: float | None = None
    polygon: list[Point2D] | None = None
    confidence: float = Field(default=1.0, ge=0.0, le=1.0)
    page_ref: str | None = Field(default=None, description="Sheet/view/layout identifier")
    viewport_metadata: dict[str, Any] = Field(default_factory=dict)
    source_markup: MarkupOverlay | None = None
    ambiguity_flags: list[str] = Field(default_factory=list)
    schema_version: str = "1.0"

    def contains_point(self, p: Point2D) -> bool:
        """Check if a point falls within this region.

        Uses polygon containment if available, otherwise falls back to bounds.
        """
        if self.source_type == RegionType.CIRCLE_SELECT and self.radius is not None:
            dx = p.x - self.center.x
            dy = p.y - self.center.y
            return (dx * dx + dy * dy) <= self.radius * self.radius
        if self.polygon and len(self.polygon) >= 3:
            return _point_in_polygon(p, self.polygon)
        return self.bounds.contains_point(p)


def _point_in_polygon(point: Point2D, polygon: list[Point2D]) -> bool:
    """Ray-casting algorithm for point-in-polygon test."""
    n = len(polygon)
    inside = False
    j = n - 1
    for i in range(n):
        pi, pj = polygon[i], polygon[j]
        if (pi.y > point.y) != (pj.y > point.y) and point.x < (
            (pj.x - pi.x) * (point.y - pi.y) / (pj.y - pi.y) + pi.x
        ):
            inside = not inside
        j = i
    return inside

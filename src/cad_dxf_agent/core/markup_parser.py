"""Markup ingestion — maps overlay annotations to drawing-space regions.

Converts markup overlays (circles, boxes, loops, arrows, highlights)
from source coordinates (image pixels, PDF points) into NormalizedRegion
objects with drawing-space coordinates and confidence scoring.
"""

from __future__ import annotations

import logging
import math
from dataclasses import dataclass

from ..models.cad_schema import Point2D
from ..models.region_schema import (
    BoundingBox,
    CoordinateSpace,
    MarkupOverlay,
    MarkupType,
    NormalizedRegion,
    RegionType,
)

logger = logging.getLogger(__name__)

# Minimum bounding-box area (drawing units²) to consider a region meaningful
_MIN_REGION_AREA = 1e-6


@dataclass(frozen=True)
class AffineTransform:
    """Simple 2D affine: drawing = scale * source + offset.

    Maps source coordinates (image/viewport) to drawing-space coordinates.
    """

    scale_x: float = 1.0
    scale_y: float = 1.0
    offset_x: float = 0.0
    offset_y: float = 0.0

    def apply(self, p: Point2D) -> Point2D:
        return Point2D(
            x=p.x * self.scale_x + self.offset_x,
            y=p.y * self.scale_y + self.offset_y,
        )

    @classmethod
    def identity(cls) -> AffineTransform:
        return cls()

    @classmethod
    def from_image_bounds(
        cls,
        image_width: float,
        image_height: float,
        drawing_min_x: float,
        drawing_min_y: float,
        drawing_max_x: float,
        drawing_max_y: float,
    ) -> AffineTransform:
        """Build transform from image pixel bounds to drawing extents."""
        if image_width <= 0 or image_height <= 0:
            return cls.identity()
        sx = (drawing_max_x - drawing_min_x) / image_width
        sy = (drawing_max_y - drawing_min_y) / image_height
        return cls(
            scale_x=sx,
            scale_y=sy,
            offset_x=drawing_min_x,
            offset_y=drawing_min_y,
        )


@dataclass
class MarkupMappingResult:
    """Result of mapping a single markup overlay to drawing space."""

    region: NormalizedRegion
    confidence: float
    ambiguity_flags: list[str]
    source_markup: MarkupOverlay


class MarkupParser:
    """Maps markup overlay annotations to drawing-space NormalizedRegions."""

    def __init__(self, transform: AffineTransform | None = None) -> None:
        self._transform = transform or AffineTransform.identity()

    def map_overlay(self, overlay: MarkupOverlay) -> MarkupMappingResult:
        """Map a single markup overlay to a drawing-space region."""
        handler = _MARKUP_HANDLERS.get(overlay.markup_type)
        if handler is None:
            return _unsupported_markup(overlay)
        return handler(overlay, self._transform)

    def map_overlays(self, overlays: list[MarkupOverlay]) -> list[MarkupMappingResult]:
        """Map multiple overlays, returning results in order."""
        return [self.map_overlay(o) for o in overlays]


def _map_circle(overlay: MarkupOverlay, transform: AffineTransform) -> MarkupMappingResult:
    """Map a circle markup to a circular drawing-space region."""
    flags: list[str] = []

    if len(overlay.source_points) < 2:
        flags.append("insufficient_points_for_circle")
        return _degenerate_result(overlay, flags)

    center_src = overlay.source_points[0]
    edge_src = overlay.source_points[1]

    center_d = transform.apply(center_src)
    edge_d = transform.apply(edge_src)

    radius = math.hypot(edge_d.x - center_d.x, edge_d.y - center_d.y)
    if radius < 1e-6:
        flags.append("zero_radius_circle")
        return _degenerate_result(overlay, flags)

    bounds = BoundingBox(
        min_x=center_d.x - radius,
        min_y=center_d.y - radius,
        max_x=center_d.x + radius,
        max_y=center_d.y + radius,
    )

    confidence = _compute_confidence(overlay, transform, bounds)
    region = NormalizedRegion(
        source_type=RegionType.MARKUP_MAPPED,
        coordinate_space=CoordinateSpace.DRAWING,
        bounds=bounds,
        center=center_d,
        radius=radius,
        confidence=confidence,
        source_markup=overlay,
        ambiguity_flags=flags,
    )
    return MarkupMappingResult(
        region=region,
        confidence=confidence,
        ambiguity_flags=flags,
        source_markup=overlay,
    )


def _map_box(overlay: MarkupOverlay, transform: AffineTransform) -> MarkupMappingResult:
    """Map a box/rectangle markup to a rectangular drawing-space region."""
    flags: list[str] = []

    if len(overlay.source_points) < 2:
        flags.append("insufficient_points_for_box")
        return _degenerate_result(overlay, flags)

    p1 = transform.apply(overlay.source_points[0])
    p2 = transform.apply(overlay.source_points[1])

    bounds = BoundingBox(
        min_x=min(p1.x, p2.x),
        min_y=min(p1.y, p2.y),
        max_x=max(p1.x, p2.x),
        max_y=max(p1.y, p2.y),
    )

    if bounds.area < _MIN_REGION_AREA:
        flags.append("degenerate_box")
        return _degenerate_result(overlay, flags)

    confidence = _compute_confidence(overlay, transform, bounds)
    region = NormalizedRegion(
        source_type=RegionType.MARKUP_MAPPED,
        coordinate_space=CoordinateSpace.DRAWING,
        bounds=bounds,
        center=bounds.center,
        confidence=confidence,
        source_markup=overlay,
        ambiguity_flags=flags,
    )
    return MarkupMappingResult(
        region=region,
        confidence=confidence,
        ambiguity_flags=flags,
        source_markup=overlay,
    )


def _map_loop(overlay: MarkupOverlay, transform: AffineTransform) -> MarkupMappingResult:
    """Map a freehand loop markup to a polygonal drawing-space region."""
    flags: list[str] = []

    if len(overlay.source_points) < 3:
        flags.append("insufficient_points_for_loop")
        return _degenerate_result(overlay, flags)

    polygon = [transform.apply(p) for p in overlay.source_points]

    xs = [p.x for p in polygon]
    ys = [p.y for p in polygon]
    bounds = BoundingBox(min_x=min(xs), min_y=min(ys), max_x=max(xs), max_y=max(ys))

    if bounds.area < _MIN_REGION_AREA:
        flags.append("degenerate_loop")
        return _degenerate_result(overlay, flags)

    center = bounds.center
    confidence = _compute_confidence(overlay, transform, bounds)

    region = NormalizedRegion(
        source_type=RegionType.MARKUP_MAPPED,
        coordinate_space=CoordinateSpace.DRAWING,
        bounds=bounds,
        center=center,
        polygon=polygon,
        confidence=confidence,
        source_markup=overlay,
        ambiguity_flags=flags,
    )
    return MarkupMappingResult(
        region=region,
        confidence=confidence,
        ambiguity_flags=flags,
        source_markup=overlay,
    )


def _map_arrow(overlay: MarkupOverlay, transform: AffineTransform) -> MarkupMappingResult:
    """Map an arrow markup — partial support.

    Arrows point to a location but don't define a region. We create a small
    region around the arrow tip with reduced confidence and an ambiguity flag.
    """
    flags: list[str] = ["arrow_partial_support"]

    if len(overlay.source_points) < 1:
        flags.append("insufficient_points_for_arrow")
        return _degenerate_result(overlay, flags)

    # Arrow tip is the last point
    tip = transform.apply(overlay.source_points[-1])

    # Create a small region around the tip (10 drawing units default)
    tip_radius = 10.0
    bounds = BoundingBox(
        min_x=tip.x - tip_radius,
        min_y=tip.y - tip_radius,
        max_x=tip.x + tip_radius,
        max_y=tip.y + tip_radius,
    )

    confidence = min(0.5, _compute_confidence(overlay, transform, bounds))
    region = NormalizedRegion(
        source_type=RegionType.MARKUP_MAPPED,
        coordinate_space=CoordinateSpace.DRAWING,
        bounds=bounds,
        center=tip,
        confidence=confidence,
        source_markup=overlay,
        ambiguity_flags=flags,
    )
    return MarkupMappingResult(
        region=region,
        confidence=confidence,
        ambiguity_flags=flags,
        source_markup=overlay,
    )


def _map_highlight(overlay: MarkupOverlay, transform: AffineTransform) -> MarkupMappingResult:
    """Map a highlight annotation — partial support.

    Highlights cover an area but boundaries are often imprecise.
    We map the bounding extent with reduced confidence.
    """
    flags: list[str] = ["highlight_partial_support"]

    if len(overlay.source_points) < 2:
        flags.append("insufficient_points_for_highlight")
        return _degenerate_result(overlay, flags)

    points = [transform.apply(p) for p in overlay.source_points]
    xs = [p.x for p in points]
    ys = [p.y for p in points]
    bounds = BoundingBox(min_x=min(xs), min_y=min(ys), max_x=max(xs), max_y=max(ys))

    if bounds.area < _MIN_REGION_AREA:
        flags.append("degenerate_highlight")
        return _degenerate_result(overlay, flags)

    confidence = min(0.6, _compute_confidence(overlay, transform, bounds))
    region = NormalizedRegion(
        source_type=RegionType.MARKUP_MAPPED,
        coordinate_space=CoordinateSpace.DRAWING,
        bounds=bounds,
        center=bounds.center,
        confidence=confidence,
        source_markup=overlay,
        ambiguity_flags=flags,
    )
    return MarkupMappingResult(
        region=region,
        confidence=confidence,
        ambiguity_flags=flags,
        source_markup=overlay,
    )


def _compute_confidence(
    overlay: MarkupOverlay,
    transform: AffineTransform,
    bounds: BoundingBox,
) -> float:
    """Compute mapping confidence based on transform quality and region size.

    Identity transform (already in drawing space) gets high confidence.
    Non-identity transforms reduce confidence proportionally.
    Very small or very large regions get penalized.
    """
    confidence = 0.95

    # Identity transform = high confidence
    is_identity = (
        transform.scale_x == 1.0
        and transform.scale_y == 1.0
        and transform.offset_x == 0.0
        and transform.offset_y == 0.0
    )
    if not is_identity:
        # Non-uniform scaling degrades confidence
        scale_ratio = (
            min(abs(transform.scale_x), abs(transform.scale_y))
            / max(abs(transform.scale_x), abs(transform.scale_y))
            if max(abs(transform.scale_x), abs(transform.scale_y)) > 0
            else 0.0
        )
        confidence *= 0.7 + 0.3 * scale_ratio  # 0.7-1.0 range

    # Very large regions are more likely to be imprecise
    if bounds.area > 1e6:
        confidence *= 0.8

    return round(confidence, 3)


def _degenerate_result(overlay: MarkupOverlay, flags: list[str]) -> MarkupMappingResult:
    """Return a zero-confidence result for degenerate/invalid markups."""
    region = NormalizedRegion(
        source_type=RegionType.MARKUP_MAPPED,
        coordinate_space=CoordinateSpace.DRAWING,
        bounds=BoundingBox(min_x=0, min_y=0, max_x=0, max_y=0),
        center=Point2D(x=0, y=0),
        confidence=0.0,
        source_markup=overlay,
        ambiguity_flags=flags,
    )
    return MarkupMappingResult(
        region=region,
        confidence=0.0,
        ambiguity_flags=flags,
        source_markup=overlay,
    )


def _unsupported_markup(overlay: MarkupOverlay) -> MarkupMappingResult:
    """Return a result for unsupported markup types."""
    flags = [f"unsupported_markup_type_{overlay.markup_type}"]
    return _degenerate_result(overlay, flags)


_MARKUP_HANDLERS = {
    MarkupType.CIRCLE: _map_circle,
    MarkupType.BOX: _map_box,
    MarkupType.LOOP: _map_loop,
    MarkupType.ARROW: _map_arrow,
    MarkupType.HIGHLIGHT: _map_highlight,
}

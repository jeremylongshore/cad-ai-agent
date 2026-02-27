"""Canonical model — quantization, normalization, and stable identity for revision workflows.

Internal base unit: inches (matching typical structural drawing units).
Quantization: configurable decimal places (default 4dp = 0.0001").

This module provides the foundation for deterministic entity identity
that does NOT rely on DXF handles.
"""

from __future__ import annotations

from dataclasses import dataclass

from ...models.cad_schema import EntityType, Point2D


@dataclass(frozen=True)
class QuantizationConfig:
    """Controls rounding and quantization for canonical geometry.

    Attributes:
        decimal_places: Number of decimal places for coordinate rounding.
            4dp = 0.0001" precision, sufficient for structural work.
        near_vertex_epsilon: Distance below which two vertices are considered
            duplicates and the second is removed.  Set to 0.0 to disable.
        spatial_bin_size: Grid cell size for spatial binning in stable ID
            computation.  Entities in the same bin get grouped for
            disambiguation.
    """

    decimal_places: int = 4
    near_vertex_epsilon: float = 0.0001
    spatial_bin_size: float = 0.25


# Module-level default instance — used when no config is passed.
DEFAULT_QUANTIZATION = QuantizationConfig()


def quantize_point(point: Point2D, config: QuantizationConfig | None = None) -> Point2D:
    """Round a point's coordinates to the configured precision.

    Returns a new Point2D with quantized coordinates.
    """
    config = config or DEFAULT_QUANTIZATION
    return Point2D(
        x=round(point.x, config.decimal_places),
        y=round(point.y, config.decimal_places),
    )


def quantize_points(
    points: list[Point2D], config: QuantizationConfig | None = None
) -> list[Point2D]:
    """Quantize a list of points."""
    config = config or DEFAULT_QUANTIZATION
    return [quantize_point(p, config) for p in points]


def quantize_value(value: float, config: QuantizationConfig | None = None) -> float:
    """Round a scalar value (radius, angle, etc.) to configured precision."""
    config = config or DEFAULT_QUANTIZATION
    return round(value, config.decimal_places)


def remove_near_duplicate_vertices(
    points: list[Point2D], config: QuantizationConfig | None = None
) -> list[Point2D]:
    """Remove consecutive near-duplicate vertices within epsilon.

    Keeps the first vertex of each cluster.  Non-consecutive duplicates
    are preserved (they may represent legitimate geometry like a closed shape
    revisiting a point).
    """
    config = config or DEFAULT_QUANTIZATION
    if config.near_vertex_epsilon <= 0.0 or len(points) < 2:
        return list(points)

    eps_sq = config.near_vertex_epsilon**2
    result: list[Point2D] = [points[0]]
    for pt in points[1:]:
        prev = result[-1]
        dist_sq = (pt.x - prev.x) ** 2 + (pt.y - prev.y) ** 2
        if dist_sq > eps_sq:
            result.append(pt)
    return result


def spatial_bin(point: Point2D, config: QuantizationConfig | None = None) -> tuple[int, int]:
    """Compute the spatial bin index for a point.

    Used for stable ID disambiguation — entities in the same bin are
    candidates for collision suffixing.
    """
    config = config or DEFAULT_QUANTIZATION
    bx = int(point.x // config.spatial_bin_size)
    by = int(point.y // config.spatial_bin_size)
    return (bx, by)


# --- Geometry normalization ---

# Entity types where start/end are interchangeable (undirected).
_UNDIRECTED_TYPES = {EntityType.LINE}

# Entity types where vertex order defines the shape (must preserve).
_ORDERED_TYPES = {
    EntityType.LWPOLYLINE,
    EntityType.POLYLINE,
    EntityType.SPLINE,
    EntityType.LEADER,
    EntityType.HATCH,
}


def canonical_points(
    points: list[Point2D],
    entity_type: EntityType,
    config: QuantizationConfig | None = None,
) -> list[Point2D]:
    """Produce canonical (normalized + quantized) points for an entity.

    Normalization rules by entity type:
    - LINE: sort endpoints so lower-x (then lower-y) comes first.
      This makes LINE(A→B) == LINE(B→A).
    - LWPOLYLINE / POLYLINE / SPLINE / LEADER / HATCH: preserve vertex
      order (defines shape), but quantize and remove near-duplicate vertices.
    - Single-point entities (TEXT, MTEXT, INSERT, CIRCLE, ARC, etc.):
      just quantize.
    """
    config = config or DEFAULT_QUANTIZATION

    # Step 1: quantize all coordinates
    quantized = quantize_points(points, config)

    # Step 2: normalize direction for undirected types (LINE)
    if entity_type in _UNDIRECTED_TYPES and len(quantized) == 2:
        return _sort_line_endpoints(quantized)

    # Step 3: remove near-duplicate consecutive vertices (polylines, hatches, etc.)
    if entity_type in _ORDERED_TYPES:
        return remove_near_duplicate_vertices(quantized, config)

    # Single-point entities (TEXT, INSERT, CIRCLE, etc.): just return quantized
    return quantized


def _sort_line_endpoints(points: list[Point2D]) -> list[Point2D]:
    """Sort LINE endpoints: lower-x first, then lower-y as tiebreaker.

    This ensures LINE(0,0 → 10,5) and LINE(10,5 → 0,0) produce
    identical canonical points.
    """
    a, b = points[0], points[1]
    if (a.x, a.y) > (b.x, b.y):
        return [b, a]
    return [a, b]

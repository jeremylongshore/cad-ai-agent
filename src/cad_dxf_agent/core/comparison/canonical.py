"""Canonical model — quantization, normalization, and stable identity for revision workflows.

Internal base unit: inches (matching typical structural drawing units).
Quantization: configurable decimal places (default 4dp = 0.0001").

This module provides the foundation for deterministic entity identity
that does NOT rely on DXF handles.
"""

from __future__ import annotations

import hashlib
import math
from collections import defaultdict
from dataclasses import dataclass
from typing import Any

from ...models.cad_schema import EntityType, Point2D
from ...models.comparison_schema import GeometrySnapshot


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


# --- Geometry signatures ---


@dataclass(frozen=True)
class GeometrySignature:
    """Noise-tolerant geometric features for entity matching.

    Unlike fingerprints (exact hash of coordinates), signatures capture
    geometric *properties* that survive small coordinate perturbations
    from re-export or unit conversion.

    All numeric features are quantized to 2dp (0.01") to absorb noise
    while still distinguishing meaningfully different geometry.
    """

    entity_type: str
    length: float = 0.0
    angle_bucket: int = 0  # degrees, bucketed to 5° increments
    midpoint_bin: tuple[int, int] = (0, 0)
    vertex_count: int = 0
    perimeter: float = 0.0
    turn_hash: int = 0  # hash of quantized turn-angle sequence
    radius: float = 0.0
    start_angle_bucket: int = 0
    end_angle_bucket: int = 0
    block_name: str = ""
    text_content: str = ""
    attrib_keys: tuple[str, ...] = ()


# Signature precision: coarser than point quantization to absorb noise.
_SIG_DECIMAL = 2  # 0.01" precision for lengths/perimeters
_ANGLE_BUCKET_SIZE = 5  # 5° buckets for directional angles
_TURN_BUCKET_SIZE = 15  # 15° buckets for turn angles (wider to absorb noise)


def compute_signature(
    entity_type: EntityType,
    points: list[Point2D],
    config: QuantizationConfig | None = None,
    *,
    text_content: str | None = None,
    block_name: str | None = None,
    attributes: dict[str, Any] | None = None,
) -> GeometrySignature:
    """Compute a noise-tolerant geometric signature for an entity.

    Signatures use coarser quantization (2dp / 5° buckets) than point
    quantization (4dp) so that small coordinate noise doesn't change
    the signature.
    """
    config = config or DEFAULT_QUANTIZATION
    etype = entity_type.value

    if etype == "LINE":
        return _sig_line(etype, points, config)
    if etype in ("LWPOLYLINE", "POLYLINE", "SPLINE", "LEADER"):
        return _sig_polyline(etype, points, config)
    if etype == "CIRCLE":
        return _sig_circle(etype, points, attributes or {}, config)
    if etype == "ARC":
        return _sig_arc(etype, points, attributes or {}, config)
    if etype == "ELLIPSE":
        return _sig_ellipse(etype, points, attributes or {}, config)
    if etype == "INSERT":
        return _sig_insert(etype, points, block_name, attributes or {}, config)
    if etype in ("TEXT", "MTEXT", "MLEADER", "DIMENSION"):
        return _sig_text(etype, points, text_content, config)
    if etype == "HATCH":
        return _sig_polyline(etype, points, config)
    if etype == "SOLID":
        return _sig_polyline(etype, points, config)

    # Fallback: just entity type + midpoint bin
    return GeometrySignature(
        entity_type=etype,
        midpoint_bin=_midpoint_bin(points, config),
        vertex_count=len(points),
    )


def _sig_line(
    etype: str, points: list[Point2D], config: QuantizationConfig
) -> GeometrySignature:
    """LINE: length + angle bucket + midpoint bin."""
    if len(points) < 2:
        return GeometrySignature(entity_type=etype)
    a, b = points[0], points[1]
    length = round(_distance(a, b), _SIG_DECIMAL)
    angle = _angle_bucket(a, b)
    mid = _midpoint_bin(points, config)
    return GeometrySignature(
        entity_type=etype, length=length, angle_bucket=angle, midpoint_bin=mid
    )


def _sig_polyline(
    etype: str, points: list[Point2D], config: QuantizationConfig
) -> GeometrySignature:
    """Polyline-like: vertex count + perimeter + turn angle sequence hash."""
    n = len(points)
    if n < 2:
        return GeometrySignature(
            entity_type=etype, vertex_count=n, midpoint_bin=_midpoint_bin(points, config)
        )
    perimeter = round(
        sum(_distance(points[i], points[i + 1]) for i in range(n - 1)),
        _SIG_DECIMAL,
    )
    turn_hash = _turn_angle_hash(points)
    mid = _midpoint_bin(points, config)
    return GeometrySignature(
        entity_type=etype,
        vertex_count=n,
        perimeter=perimeter,
        turn_hash=turn_hash,
        midpoint_bin=mid,
    )


def _sig_circle(
    etype: str,
    points: list[Point2D],
    attributes: dict[str, Any],
    config: QuantizationConfig,
) -> GeometrySignature:
    """CIRCLE: radius + center bin."""
    radius = round(float(attributes.get("radius", 0)), _SIG_DECIMAL)
    mid = _midpoint_bin(points, config)
    return GeometrySignature(entity_type=etype, radius=radius, midpoint_bin=mid)


def _sig_arc(
    etype: str,
    points: list[Point2D],
    attributes: dict[str, Any],
    config: QuantizationConfig,
) -> GeometrySignature:
    """ARC: radius + start/end angle buckets + center bin."""
    radius = round(float(attributes.get("radius", 0)), _SIG_DECIMAL)
    sa = int(float(attributes.get("start_angle", 0)) // _ANGLE_BUCKET_SIZE)
    ea = int(float(attributes.get("end_angle", 0)) // _ANGLE_BUCKET_SIZE)
    mid = _midpoint_bin(points, config)
    return GeometrySignature(
        entity_type=etype,
        radius=radius,
        start_angle_bucket=sa,
        end_angle_bucket=ea,
        midpoint_bin=mid,
    )


def _sig_ellipse(
    etype: str,
    points: list[Point2D],
    attributes: dict[str, Any],
    config: QuantizationConfig,
) -> GeometrySignature:
    """ELLIPSE: ratio + major axis angle bucket + center bin."""
    ratio = round(float(attributes.get("ratio", 0)), _SIG_DECIMAL)
    major = attributes.get("major_axis", (1, 0, 0))
    angle = int(math.degrees(math.atan2(float(major[1]), float(major[0]))) // _ANGLE_BUCKET_SIZE)
    mid = _midpoint_bin(points, config)
    return GeometrySignature(
        entity_type=etype, radius=ratio, angle_bucket=angle, midpoint_bin=mid
    )


def _sig_insert(
    etype: str,
    points: list[Point2D],
    block_name: str | None,
    attributes: dict[str, Any],
    config: QuantizationConfig,
) -> GeometrySignature:
    """INSERT: block name + attribute keys + position bin."""
    mid = _midpoint_bin(points, config)
    attrib_keys = tuple(sorted(str(k) for k in attributes.keys())) if attributes else ()
    return GeometrySignature(
        entity_type=etype,
        block_name=block_name or "",
        attrib_keys=attrib_keys,
        midpoint_bin=mid,
    )


def _sig_text(
    etype: str,
    points: list[Point2D],
    text_content: str | None,
    config: QuantizationConfig,
) -> GeometrySignature:
    """TEXT/MTEXT/MLEADER/DIMENSION: text content + position bin."""
    mid = _midpoint_bin(points, config)
    return GeometrySignature(
        entity_type=etype, text_content=text_content or "", midpoint_bin=mid
    )


# --- Signature helpers ---


def _distance(a: Point2D, b: Point2D) -> float:
    """Euclidean distance between two points."""
    return math.sqrt((a.x - b.x) ** 2 + (a.y - b.y) ** 2)


def _angle_bucket(a: Point2D, b: Point2D) -> int:
    """Angle from a to b, bucketed to 5° increments (0-71).

    Uses canonical direction: always measures from the lower-x (then y)
    endpoint to the other, so LINE direction doesn't matter.
    """
    if (a.x, a.y) > (b.x, b.y):
        a, b = b, a
    angle_deg = math.degrees(math.atan2(b.y - a.y, b.x - a.x))
    if angle_deg < 0:
        angle_deg += 360.0
    return int(angle_deg // _ANGLE_BUCKET_SIZE)


def _midpoint_bin(points: list[Point2D], config: QuantizationConfig) -> tuple[int, int]:
    """Spatial bin of the centroid of a point set."""
    if not points:
        return (0, 0)
    cx = sum(p.x for p in points) / len(points)
    cy = sum(p.y for p in points) / len(points)
    return spatial_bin(Point2D(x=cx, y=cy), config)


def _turn_angle_hash(points: list[Point2D]) -> int:
    """Hash of quantized turn angles at each interior vertex.

    Turn angles are bucketed to 5° so small noise doesn't change the hash.
    For a polyline with N points, there are N-2 interior vertices.
    """
    if len(points) < 3:
        return 0

    buckets: list[int] = []
    for i in range(1, len(points) - 1):
        prev, curr, nxt = points[i - 1], points[i], points[i + 1]
        # Vectors: incoming and outgoing
        dx1 = curr.x - prev.x
        dy1 = curr.y - prev.y
        dx2 = nxt.x - curr.x
        dy2 = nxt.y - curr.y
        # Cross product gives signed turn angle
        cross = dx1 * dy2 - dy1 * dx2
        dot = dx1 * dx2 + dy1 * dy2
        angle = math.degrees(math.atan2(cross, dot))
        buckets.append(round(angle / _TURN_BUCKET_SIZE))

    return hash(tuple(buckets))


# --- Stable ID computation ---


def compute_stable_id(
    snap: GeometrySnapshot,
    config: QuantizationConfig | None = None,
) -> str:
    """Compute a stable ID for a single entity based on its geometry.

    The ID is a short hex hash of (entity_type, layer, signature, spatial_bin).
    This produces the *base* ID before collision resolution.
    """
    config = config or DEFAULT_QUANTIZATION
    sig = compute_signature(
        snap.entity_type,
        snap.points,
        config,
        text_content=snap.text_content,
        block_name=snap.block_name,
        attributes=snap.attributes,
    )
    mid_bin = _midpoint_bin(snap.points, config)

    # Build a deterministic string from all signature fields
    parts = [
        snap.entity_type.value,
        snap.layer,
        str(sig.length),
        str(sig.angle_bucket),
        str(sig.vertex_count),
        str(sig.perimeter),
        str(sig.turn_hash),
        str(sig.radius),
        str(sig.start_angle_bucket),
        str(sig.end_angle_bucket),
        sig.block_name,
        sig.text_content,
        str(sig.attrib_keys),
        str(mid_bin),
    ]
    raw = "|".join(parts)
    digest = hashlib.sha256(raw.encode()).hexdigest()[:12]
    return f"{snap.entity_type.value}:{snap.layer}:{digest}"


def assign_stable_ids(
    snapshots: list[GeometrySnapshot],
    config: QuantizationConfig | None = None,
) -> list[GeometrySnapshot]:
    """Assign stable IDs to a list of snapshots, handling collisions.

    Entities with the same base ID get disambiguation suffixes (#0, #1, ...)
    sorted by centroid (x, y) for deterministic ordering.

    Args:
        snapshots: List of GeometrySnapshot to assign IDs to.
        config: Quantization config.

    Returns:
        New list of snapshots with stable_id populated.
    """
    config = config or DEFAULT_QUANTIZATION

    # Compute base IDs for all snapshots
    base_ids: list[str] = [compute_stable_id(s, config) for s in snapshots]

    # Group by base ID to detect collisions
    groups: dict[str, list[int]] = defaultdict(list)
    for idx, base_id in enumerate(base_ids):
        groups[base_id].append(idx)

    # Assign final IDs
    result: list[GeometrySnapshot] = []
    final_ids: dict[int, str] = {}

    for base_id, indices in groups.items():
        if len(indices) == 1:
            # No collision — use base ID as-is
            final_ids[indices[0]] = base_id
        else:
            # Collision — sort by centroid (x, y) for deterministic suffix
            sorted_indices = sorted(
                indices,
                key=lambda i: (snapshots[i].centroid.x, snapshots[i].centroid.y),
            )
            for suffix, idx in enumerate(sorted_indices):
                final_ids[idx] = f"{base_id}#{suffix}"

    # Build result list preserving original order
    for idx, snap in enumerate(snapshots):
        result.append(snap.model_copy(update={"stable_id": final_ids[idx]}))

    return result

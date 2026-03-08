"""Zone detector — finds enclosed spaces in architectural drawings.

Deterministic (no LLM). Two detection strategies:
1. Closed LWPOLYLINE extraction — entities where first vertex ≈ last vertex
2. Connected LINE tracing — build endpoint graph, find minimal cycles

Each detected zone gets area (shoelace formula), perimeter, centroid,
and a heuristic type label based on area ranges + nearby text.
"""

from __future__ import annotations

import math
from collections import defaultdict

from cad_dxf_agent.core.primitive_extractors import LayerClassification, classify_layers
from cad_dxf_agent.models.cad_schema import DrawingContext, EntityType, Point2D
from cad_dxf_agent.models.zone_schema import DetectedZone, ZoneDetectionResult

# --- Detection limits ---
_MAX_GRAPH_NODES = 500  # Skip cycle detection for graphs larger than this
_MAX_CYCLES = 50  # Stop cycle search after this many results
_MAX_CYCLE_LENGTH = 20  # Maximum edges in a single cycle

# --- Zone classification thresholds (area in drawing units²) ---
_AREA_CLOSET_MAX = 20
_AREA_BATHROOM_MAX = 80
_AREA_ROOM_MAX = 300
_AREA_LARGE_ROOM_MAX = 600

# --- Spatial search ---
_LABEL_SEARCH_RADIUS = 100  # Max distance to search for nearby text labels

# --- Aspect ratio ---
_HALLWAY_ASPECT_RATIO = 4.0  # Zones with aspect ratio above this are hallways


def detect_zones(
    context: DrawingContext,
    *,
    tolerance: float = 0.5,
) -> ZoneDetectionResult:
    """Detect enclosed zones/rooms from drawing geometry.

    Args:
        context: Drawing context with entities.
        tolerance: Distance threshold for point matching (default 0.5 units).

    Returns:
        ZoneDetectionResult with detected zones, total area, and confidence.
    """
    if not context.entities:
        return ZoneDetectionResult()

    layer_cls = classify_layers(context)
    structural_layers = _get_structural_layers(layer_cls)

    # Collect text entities for zone label inference
    text_entities = _collect_text_entities(context)

    zones: list[DetectedZone] = []

    # Strategy 1: closed LWPOLYLINE extraction
    polyline_zones = _extract_closed_polylines(context, structural_layers, tolerance)
    zones.extend(polyline_zones)

    # Strategy 2: connected LINE tracing
    line_zones = _extract_line_cycles(context, structural_layers, tolerance)
    zones.extend(line_zones)

    # Classify zone types based on area + nearby text
    for zone in zones:
        zone.inferred_type = _classify_zone(zone, text_entities)

    total_area = sum(z.area for z in zones)
    confidence = min(1.0, len(zones) * 0.2) if zones else 0.0

    return ZoneDetectionResult(
        zones=zones,
        total_area=total_area,
        zone_count=len(zones),
        confidence=confidence,
    )


def _get_structural_layers(layer_cls: LayerClassification) -> set[str]:
    """Get layer names that are likely structural (walls, etc.).

    If no structural layers are classified, accept all layers.
    """
    structural = set(layer_cls.structural)
    if not structural:
        # Fall back to all non-annotation, non-title layers
        all_layers = (
            layer_cls.structural
            + layer_cls.annotation
            + layer_cls.dimension
            + layer_cls.title_border
            + layer_cls.mep
            + layer_cls.other
        )
        structural = set(all_layers) - set(layer_cls.annotation) - set(layer_cls.title_border)
    return structural


def _collect_text_entities(
    context: DrawingContext,
) -> list[tuple[Point2D, str]]:
    """Collect (position, text) pairs from TEXT and MTEXT entities."""
    results = []
    for entity in context.entities:
        if entity.entity_type not in (EntityType.TEXT, EntityType.MTEXT):
            continue
        if entity.text_content and entity.insert_point:
            results.append((entity.insert_point, entity.text_content.strip().upper()))
    return results


def _extract_closed_polylines(
    context: DrawingContext,
    structural_layers: set[str],
    tolerance: float,
) -> list[DetectedZone]:
    """Find closed LWPOLYLINE entities and convert to zones."""
    zones = []
    for entity in context.entities:
        if entity.entity_type != EntityType.LWPOLYLINE:
            continue

        # Layer filtering: skip non-structural layers if we have structural ones
        if structural_layers and entity.layer not in structural_layers:
            continue

        vertices_raw = entity.attributes.get("vertices", [])
        if len(vertices_raw) < 3:
            continue

        vertices = [Point2D(x=v[0], y=v[1]) for v in vertices_raw]

        # Check closure: explicit is_closed flag OR first vertex ≈ last vertex
        is_closed = entity.attributes.get("is_closed", False)
        if not is_closed and not _points_close(vertices[0], vertices[-1], tolerance):
            continue

        # Remove duplicated closing vertex if present
        working = vertices[:]
        if len(working) > 1 and _points_close(working[0], working[-1], tolerance):
            working = working[:-1]

        if len(working) < 3:
            continue

        area = _shoelace_area(working)
        if area <= 0:
            continue

        perimeter = _polygon_perimeter(working)
        centroid = _polygon_centroid(working)

        zones.append(
            DetectedZone(
                boundary=working,
                area=area,
                perimeter=perimeter,
                centroid=centroid,
                source_handles=[entity.handle],
            )
        )

    return zones


def _extract_line_cycles(
    context: DrawingContext,
    structural_layers: set[str],
    tolerance: float,
) -> list[DetectedZone]:
    """Find cycles formed by connected LINE segments."""
    # Build adjacency graph from LINE endpoints
    graph: dict[tuple[float, float], list[tuple[tuple[float, float], str]]] = defaultdict(list)
    line_entities = []

    for entity in context.entities:
        if entity.entity_type != EntityType.LINE:
            continue
        if structural_layers and entity.layer not in structural_layers:
            continue
        if entity.insert_point is None:
            continue

        end_point_raw = entity.attributes.get("end_point")
        if end_point_raw is None:
            continue

        start = _snap_point(entity.insert_point.x, entity.insert_point.y, tolerance)
        end = _snap_point(end_point_raw[0], end_point_raw[1], tolerance)

        if start == end:
            continue

        graph[start].append((end, entity.handle))
        graph[end].append((start, entity.handle))
        line_entities.append(entity)

    if len(graph) < 3:
        return []

    # Find minimal cycles using DFS
    cycles = _find_minimal_cycles(graph)

    zones = []
    for cycle_points, cycle_handles in cycles:
        vertices = [Point2D(x=p[0], y=p[1]) for p in cycle_points]
        if len(vertices) < 3:
            continue

        area = _shoelace_area(vertices)
        if area <= 0:
            continue

        perimeter = _polygon_perimeter(vertices)
        centroid = _polygon_centroid(vertices)

        zones.append(
            DetectedZone(
                boundary=vertices,
                area=area,
                perimeter=perimeter,
                centroid=centroid,
                source_handles=list(cycle_handles),
                confidence=0.8,  # lower than polyline zones
            )
        )

    return zones


def _find_minimal_cycles(
    graph: dict[tuple[float, float], list[tuple[tuple[float, float], str]]],
) -> list[tuple[list[tuple[float, float]], set[str]]]:
    """Find minimal cycles in the LINE endpoint graph.

    Returns list of (ordered_vertices, handle_set) pairs.
    Uses bounded DFS to avoid combinatorial explosion.
    """
    found: list[tuple[list[tuple[float, float]], set[str]]] = []
    seen_cycles: set[frozenset[tuple[float, float]]] = set()

    nodes = list(graph.keys())
    if len(nodes) > _MAX_GRAPH_NODES:
        return []  # Too many nodes, skip cycle detection

    for start_node in nodes:
        if len(found) >= _MAX_CYCLES:
            break
        _dfs_cycles(graph, start_node, _MAX_CYCLE_LENGTH, found, seen_cycles)

    return found


def _dfs_cycles(
    graph: dict[tuple[float, float], list[tuple[tuple[float, float], str]]],
    start: tuple[float, float],
    max_depth: int,
    found: list[tuple[list[tuple[float, float]], set[str]]],
    seen_cycles: set[frozenset[tuple[float, float]]],
) -> None:
    """DFS from start to find cycles back to start."""
    # Stack: (current_node, path, handles, visited)
    stack: list[
        tuple[
            tuple[float, float],
            list[tuple[float, float]],
            set[str],
            set[tuple[float, float]],
        ]
    ] = [(start, [start], set(), {start})]

    while stack:
        if len(found) >= _MAX_CYCLES:
            return

        node, path, handles, visited = stack.pop()

        for neighbor, handle in graph[node]:
            if neighbor == start and len(path) >= 3:
                # Found a cycle
                cycle_key = frozenset(path)
                if cycle_key not in seen_cycles:
                    seen_cycles.add(cycle_key)
                    found.append((list(path), handles | {handle}))
                continue

            if neighbor in visited:
                continue
            if len(path) >= max_depth:
                continue

            stack.append((neighbor, path + [neighbor], handles | {handle}, visited | {neighbor}))


def _classify_zone(
    zone: DetectedZone,
    text_entities: list[tuple[Point2D, str]],
) -> str:
    """Classify zone type from area, aspect ratio, and nearby text labels."""
    # Check nearby text labels first — they override area heuristics
    nearby_label = _find_nearby_label(zone.centroid, text_entities, max_distance=None)
    if nearby_label is not None:
        # Use label if it contains a recognizable room type keyword
        label_type = _label_to_room_type(nearby_label)
        if label_type is not None:
            return label_type

    # Aspect ratio check for hallways/corridors
    aspect = _aspect_ratio(zone.boundary)
    if aspect > _HALLWAY_ASPECT_RATIO:
        return "hallway"

    # Area-based classification
    area = zone.area
    if area < _AREA_CLOSET_MAX:
        return "closet"
    if area < _AREA_BATHROOM_MAX:
        return "bathroom"
    if area < _AREA_ROOM_MAX:
        return "room"
    if area < _AREA_LARGE_ROOM_MAX:
        return "large_room"
    return "open_area"


def _find_nearby_label(
    centroid: Point2D,
    text_entities: list[tuple[Point2D, str]],
    max_distance: float | None,
) -> str | None:
    """Find the closest text label near a zone centroid."""
    if not text_entities:
        return None

    best_dist = float("inf")
    best_text = None

    for pos, text in text_entities:
        dist = _point_distance(centroid, pos)
        if dist < best_dist:
            if max_distance is not None and dist > max_distance:
                continue
            best_dist = dist
            best_text = text

    # Use adaptive distance threshold if max_distance not specified
    if max_distance is None and best_dist > _LABEL_SEARCH_RADIUS:
        return None

    return best_text


_ROOM_TYPE_KEYWORDS: dict[str, str] = {
    "KITCHEN": "kitchen",
    "BATH": "bathroom",
    "BATHROOM": "bathroom",
    "RESTROOM": "bathroom",
    "BEDROOM": "bedroom",
    "BED": "bedroom",
    "LIVING": "living_room",
    "FAMILY": "family_room",
    "DINING": "dining_room",
    "GARAGE": "garage",
    "CLOSET": "closet",
    "PANTRY": "pantry",
    "LAUNDRY": "laundry",
    "UTILITY": "utility",
    "OFFICE": "office",
    "STUDY": "office",
    "HALLWAY": "hallway",
    "HALL": "hallway",
    "CORRIDOR": "hallway",
    "FOYER": "foyer",
    "ENTRY": "foyer",
    "LOBBY": "lobby",
    "STAIR": "stairwell",
    "STORAGE": "storage",
    "MECHANICAL": "mechanical",
    "MECH": "mechanical",
}


def _label_to_room_type(label: str) -> str | None:
    """Map a text label to a room type keyword."""
    for keyword, room_type in _ROOM_TYPE_KEYWORDS.items():
        if keyword in label:
            return room_type
    return None


# --- Geometry helpers ---


def _points_close(a: Point2D, b: Point2D, tolerance: float) -> bool:
    dx = a.x - b.x
    dy = a.y - b.y
    return (dx * dx + dy * dy) <= tolerance * tolerance


def _point_distance(a: Point2D, b: Point2D) -> float:
    dx = a.x - b.x
    dy = a.y - b.y
    return math.sqrt(dx * dx + dy * dy)


def _snap_point(x: float, y: float, tolerance: float) -> tuple[float, float]:
    """Snap coordinates to a grid defined by tolerance for consistent hashing."""
    factor = 1.0 / tolerance
    return (round(x * factor) / factor, round(y * factor) / factor)


def _shoelace_area(vertices: list[Point2D]) -> float:
    """Compute polygon area using the shoelace formula. Returns absolute area."""
    n = len(vertices)
    if n < 3:
        return 0.0
    area = 0.0
    for i in range(n):
        j = (i + 1) % n
        area += vertices[i].x * vertices[j].y
        area -= vertices[j].x * vertices[i].y
    return abs(area) / 2.0


def _polygon_perimeter(vertices: list[Point2D]) -> float:
    """Compute polygon perimeter."""
    n = len(vertices)
    perimeter = 0.0
    for i in range(n):
        j = (i + 1) % n
        perimeter += _point_distance(vertices[i], vertices[j])
    return perimeter


def _polygon_centroid(vertices: list[Point2D]) -> Point2D:
    """Compute polygon centroid using the signed-area formula.

    This gives the true geometric centroid (center of mass) of the polygon,
    not just the average of vertices. Falls back to vertex average for
    degenerate cases where signed area is zero.
    """
    n = len(vertices)
    if n == 0:
        return Point2D(x=0, y=0)

    # Signed area (2x) for centroid weighting
    signed_area_2x = 0.0
    cx = 0.0
    cy = 0.0
    for i in range(n):
        j = (i + 1) % n
        cross = vertices[i].x * vertices[j].y - vertices[j].x * vertices[i].y
        signed_area_2x += cross
        cx += (vertices[i].x + vertices[j].x) * cross
        cy += (vertices[i].y + vertices[j].y) * cross

    if abs(signed_area_2x) < 1e-12:
        # Degenerate polygon — fall back to vertex average
        return Point2D(
            x=sum(v.x for v in vertices) / n,
            y=sum(v.y for v in vertices) / n,
        )

    factor = 1.0 / (3.0 * signed_area_2x)
    return Point2D(x=cx * factor, y=cy * factor)


def _aspect_ratio(vertices: list[Point2D]) -> float:
    """Compute bounding-box aspect ratio (max/min dimension)."""
    if len(vertices) < 2:
        return 1.0
    xs = [v.x for v in vertices]
    ys = [v.y for v in vertices]
    width = max(xs) - min(xs)
    height = max(ys) - min(ys)
    if width == 0 or height == 0:
        return 1.0
    ratio = max(width, height) / min(width, height)
    return ratio

"""Confidence scoring for entity matching — candidate search and per-type scoring."""

from __future__ import annotations

import math

from ...models.cad_schema import EntityType, Point2D
from ...models.comparison_schema import GeometrySnapshot, MatchExplanation, MatchMethod
from .canonical import GeometrySignature, QuantizationConfig, compute_signature

# --- Weight constants (alignment.py pattern) ---

# INSERT scoring weights
_BLOCK_NAME_WEIGHT = 0.5
_ATTRIB_OVERLAP_WEIGHT = 0.2
_INSERT_POSITION_WEIGHT = 0.3

# Geometry scoring weights
_LENGTH_RATIO_WEIGHT = 0.3
_ANGLE_BUCKET_WEIGHT = 0.2
_VERTEX_COUNT_WEIGHT = 0.15
_PERIMETER_RATIO_WEIGHT = 0.2
_TURN_HASH_WEIGHT = 0.15

# Text scoring weights
_TEXT_SIMILARITY_WEIGHT = 0.5
_TEXT_POSITION_WEIGHT = 0.5


def find_candidates(
    master_snap: GeometrySnapshot,
    revision_pool: list[GeometrySnapshot],
    tolerance: float,
) -> list[tuple[GeometrySnapshot, float]]:
    """Find revision entities that could match a master entity.

    Filters to same (entity_type, layer), returns candidates within
    centroid tolerance sorted by distance ascending.

    Args:
        master_snap: The master entity to find candidates for.
        revision_pool: Available revision entities.
        tolerance: Maximum centroid distance to consider.

    Returns:
        List of (revision_snap, distance) pairs sorted by distance.
    """
    m_type = master_snap.entity_type
    m_layer = master_snap.layer
    m_centroid = master_snap.centroid

    results: list[tuple[GeometrySnapshot, float]] = []
    for r_snap in revision_pool:
        if r_snap.entity_type != m_type or r_snap.layer != m_layer:
            continue
        d = _centroid_distance(m_centroid, r_snap.centroid)
        if d <= tolerance:
            results.append((r_snap, d))

    results.sort(key=lambda x: x[1])
    return results


def score_match(
    master: GeometrySnapshot,
    revision: GeometrySnapshot,
    tolerance: float,
    config: QuantizationConfig | None = None,
) -> tuple[float, MatchExplanation]:
    """Compute match confidence between two entities.

    Routes to type-specific scorers:
    - INSERT → score_insert
    - LINE, LWPOLYLINE, POLYLINE, SPLINE, etc. → score_geometry
    - TEXT, MTEXT → score_text
    - Fallback → centroid proximity only

    Returns:
        Tuple of (confidence score in [0.0, 1.0], MatchExplanation).
    """
    etype = master.entity_type

    if etype == EntityType.INSERT:
        return score_insert(master, revision, tolerance)
    if etype in (EntityType.TEXT, EntityType.MTEXT):
        return score_text(master, revision, tolerance)
    if etype in (
        EntityType.LINE,
        EntityType.LWPOLYLINE,
        EntityType.POLYLINE,
        EntityType.SPLINE,
        EntityType.HATCH,
        EntityType.SOLID,
        EntityType.LEADER,
    ):
        return score_geometry(master, revision, config)
    # Fallback: centroid proximity
    prox = _proximity_score(master.centroid, revision.centroid, tolerance)
    dist = _centroid_distance(master.centroid, revision.centroid)
    explanation = MatchExplanation(
        method=MatchMethod.spatial,
        features={"proximity": round(prox, 6)},
        distance=round(dist, 6),
        notes=[f"proximity score: {prox:.4f}"],
    )
    return prox, explanation


def score_insert(
    master: GeometrySnapshot,
    revision: GeometrySnapshot,
    tolerance: float,
) -> tuple[float, MatchExplanation]:
    """Score INSERT (block reference) match confidence.

    Weighted components:
    - block_name equality: 0.5
    - Attribute key overlap (Jaccard): 0.2
    - Position proximity (1 - dist/tolerance): 0.3

    Returns:
        Tuple of (score in [0.0, 1.0], MatchExplanation).
    """
    score = 0.0
    features: dict[str, float] = {}
    notes: list[str] = []

    # Block name match (== handles None==None correctly)
    if master.block_name == revision.block_name:
        features["block_name"] = _BLOCK_NAME_WEIGHT
        score += _BLOCK_NAME_WEIGHT
        notes.append("same block name")
    else:
        features["block_name"] = 0.0

    # Attribute key overlap (Jaccard similarity)
    m_keys = set(master.attributes.keys())
    r_keys = set(revision.attributes.keys())
    if m_keys or r_keys:
        jaccard = len(m_keys & r_keys) / len(m_keys | r_keys)
        attrib_contribution = _ATTRIB_OVERLAP_WEIGHT * jaccard
        features["attrib_overlap"] = round(attrib_contribution, 6)
        score += attrib_contribution
        intersection = len(m_keys & r_keys)
        union = len(m_keys | r_keys)
        notes.append(f"attribute overlap: {jaccard:.2f} ({intersection}/{union} keys)")
    else:
        # Both empty — perfect match on this dimension
        features["attrib_overlap"] = _ATTRIB_OVERLAP_WEIGHT
        score += _ATTRIB_OVERLAP_WEIGHT
        notes.append("no attributes (perfect overlap)")

    # Position proximity
    prox = _proximity_score(master.centroid, revision.centroid, tolerance)
    pos_contribution = _INSERT_POSITION_WEIGHT * prox
    features["position"] = round(pos_contribution, 6)
    score += pos_contribution
    dist = _centroid_distance(master.centroid, revision.centroid)
    notes.append(f"within {dist:.4f} units")

    final_score = min(1.0, score)
    explanation = MatchExplanation(
        method=MatchMethod.spatial,
        features=features,
        distance=round(dist, 6),
        notes=notes,
    )
    return final_score, explanation


def score_geometry(
    master: GeometrySnapshot,
    revision: GeometrySnapshot,
    config: QuantizationConfig | None = None,
) -> tuple[float, MatchExplanation]:
    """Score LINE/POLYLINE/etc match confidence using geometry signatures.

    Compares:
    - Length ratio (min/max): 0.3
    - Angle bucket match: 0.2
    - Vertex count match: 0.15
    - Perimeter ratio: 0.2
    - Turn hash match: 0.15

    Returns:
        Tuple of (score in [0.0, 1.0], MatchExplanation).
    """
    m_sig = _get_signature(master, config)
    r_sig = _get_signature(revision, config)

    score = 0.0
    features: dict[str, float] = {}
    notes: list[str] = []

    # Length ratio (0-1, where 1 = identical length)
    if m_sig.length > 0 or r_sig.length > 0:
        max_len = max(m_sig.length, r_sig.length)
        min_len = min(m_sig.length, r_sig.length)
        length_ratio = min_len / max_len if max_len > 0 else 1.0
        length_contribution = _LENGTH_RATIO_WEIGHT * length_ratio
        features["length_ratio"] = round(length_contribution, 6)
        score += length_contribution
        notes.append(f"length ratio: {length_ratio:.4f}")
    else:
        features["length_ratio"] = _LENGTH_RATIO_WEIGHT
        score += _LENGTH_RATIO_WEIGHT
        notes.append("length ratio: 1.0 (both zero)")

    # Angle bucket match
    if m_sig.angle_bucket == r_sig.angle_bucket:
        features["angle_bucket"] = _ANGLE_BUCKET_WEIGHT
        score += _ANGLE_BUCKET_WEIGHT
        notes.append(f"same angle bucket ({m_sig.angle_bucket})")
    else:
        features["angle_bucket"] = 0.0

    # Vertex count match
    if m_sig.vertex_count == r_sig.vertex_count:
        features["vertex_count"] = _VERTEX_COUNT_WEIGHT
        score += _VERTEX_COUNT_WEIGHT
        notes.append(f"same vertex count ({m_sig.vertex_count})")
    else:
        features["vertex_count"] = 0.0

    # Perimeter ratio
    if m_sig.perimeter > 0 or r_sig.perimeter > 0:
        max_p = max(m_sig.perimeter, r_sig.perimeter)
        min_p = min(m_sig.perimeter, r_sig.perimeter)
        perim_ratio = min_p / max_p if max_p > 0 else 1.0
        perim_contribution = _PERIMETER_RATIO_WEIGHT * perim_ratio
        features["perimeter_ratio"] = round(perim_contribution, 6)
        score += perim_contribution
        notes.append(f"perimeter ratio: {perim_ratio:.4f}")
    else:
        features["perimeter_ratio"] = _PERIMETER_RATIO_WEIGHT
        score += _PERIMETER_RATIO_WEIGHT
        notes.append("perimeter ratio: 1.0 (both zero)")

    # Turn hash match
    if m_sig.turn_hash == r_sig.turn_hash:
        features["turn_hash"] = _TURN_HASH_WEIGHT
        score += _TURN_HASH_WEIGHT
        notes.append("turn hash matches")
    else:
        features["turn_hash"] = 0.0

    dist = _centroid_distance(master.centroid, revision.centroid)
    final_score = min(1.0, score)
    explanation = MatchExplanation(
        method=MatchMethod.spatial,
        features=features,
        distance=round(dist, 6),
        notes=notes,
    )
    return final_score, explanation


def score_text(
    master: GeometrySnapshot,
    revision: GeometrySnapshot,
    tolerance: float,
) -> tuple[float, MatchExplanation]:
    """Score TEXT/MTEXT match confidence.

    Weighted components:
    - Text content Levenshtein similarity: 0.5
    - Position proximity: 0.5

    Returns:
        Tuple of (score in [0.0, 1.0], MatchExplanation).
    """
    score = 0.0
    features: dict[str, float] = {}
    notes: list[str] = []

    # Text similarity
    m_text = master.text_content or ""
    r_text = revision.text_content or ""
    sim = _levenshtein_similarity(m_text, r_text)
    text_contribution = _TEXT_SIMILARITY_WEIGHT * sim
    features["text_similarity"] = round(text_contribution, 6)
    score += text_contribution
    notes.append(f"text similarity: {sim:.4f}")

    # Position proximity
    prox = _proximity_score(master.centroid, revision.centroid, tolerance)
    pos_contribution = _TEXT_POSITION_WEIGHT * prox
    features["position"] = round(pos_contribution, 6)
    score += pos_contribution
    dist = _centroid_distance(master.centroid, revision.centroid)
    notes.append(f"within {dist:.4f} units")

    final_score = min(1.0, score)
    explanation = MatchExplanation(
        method=MatchMethod.spatial,
        features=features,
        distance=round(dist, 6),
        notes=notes,
    )
    return final_score, explanation


# --- Internal helpers ---


def _get_signature(
    snap: GeometrySnapshot, config: QuantizationConfig | None = None
) -> GeometrySignature:
    """Compute geometry signature for a snapshot."""
    return compute_signature(
        snap.entity_type,
        snap.points,
        config,
        text_content=snap.text_content,
        block_name=snap.block_name,
        attributes=snap.attributes,
    )


def _centroid_distance(a: Point2D, b: Point2D) -> float:
    """Euclidean distance between two points."""
    return math.sqrt((a.x - b.x) ** 2 + (a.y - b.y) ** 2)


def _proximity_score(a: Point2D, b: Point2D, tolerance: float) -> float:
    """1 - dist/tolerance, clamped to [0, 1]."""
    d = _centroid_distance(a, b)
    if tolerance <= 1e-9:
        return 1.0 if d < 1e-9 else 0.0
    return max(0.0, 1.0 - d / tolerance)


def _levenshtein_similarity(s1: str, s2: str) -> float:
    """Levenshtein similarity ratio (0-1, where 1 = identical)."""
    if s1 == s2:
        return 1.0
    if not s1 or not s2:
        return 0.0

    max_len = max(len(s1), len(s2))
    distance = _levenshtein_distance(s1, s2)
    return 1.0 - distance / max_len


def _levenshtein_distance(s1: str, s2: str) -> int:
    """Compute Levenshtein edit distance between two strings."""
    if len(s1) < len(s2):
        return _levenshtein_distance(s2, s1)

    prev_row = list(range(len(s2) + 1))
    for i, c1 in enumerate(s1):
        curr_row = [i + 1]
        for j, c2 in enumerate(s2):
            # Insert, delete, or substitute
            cost = 0 if c1 == c2 else 1
            curr_row.append(
                min(
                    curr_row[j] + 1,  # insert
                    prev_row[j + 1] + 1,  # delete
                    prev_row[j] + cost,  # substitute
                )
            )
        prev_row = curr_row

    return prev_row[-1]

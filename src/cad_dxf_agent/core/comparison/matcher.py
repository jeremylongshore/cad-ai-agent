"""Entity matching — fingerprint hash + greedy nearest-neighbor."""

from __future__ import annotations

import hashlib
import math
from collections import defaultdict

from ...models.cad_schema import Point2D
from ...models.comparison_schema import (
    ComparisonConfig,
    GeometrySnapshot,
    MatchResult,
)
from ...otel import get_tracer

tracer = get_tracer(__name__)


def match_entities(
    master_snaps: list[GeometrySnapshot],
    revision_snaps: list[GeometrySnapshot],
    config: ComparisonConfig | None = None,
) -> MatchResult:
    """Match entities between master and revision snapshots.

    Step 1: Exact fingerprint matching (O(n) hash lookup).
    Step 2: Greedy nearest-neighbor on centroids for leftovers.

    Args:
        master_snaps: Snapshots from the master DXF.
        revision_snaps: Snapshots from the revision DXF.
        config: Comparison configuration (tolerance, etc.).

    Returns:
        MatchResult with paired, master-only, and revision-only lists.
    """
    with tracer.start_as_current_span("cad.compare.match_entities") as span:
        span.set_attribute("cad.compare.master_count", len(master_snaps))
        span.set_attribute("cad.compare.revision_count", len(revision_snaps))

        config = config or ComparisonConfig()

        pairs: list[tuple[GeometrySnapshot, GeometrySnapshot]] = []

        # --- Step 1: Fingerprint hash matching ---
        revision_by_fp: dict[str, list[GeometrySnapshot]] = defaultdict(list)
        for snap in revision_snaps:
            fp = _fingerprint(snap)
            revision_by_fp[fp].append(snap)

        unmatched_master: list[GeometrySnapshot] = []

        for m_snap in master_snaps:
            fp = _fingerprint(m_snap)
            candidates = revision_by_fp.get(fp)
            if candidates:
                r_snap = candidates.pop(0)
                if not candidates:
                    del revision_by_fp[fp]
                pairs.append((m_snap, r_snap))
            else:
                unmatched_master.append(m_snap)

        # Collect unmatched revision snapshots
        unmatched_revision: list[GeometrySnapshot] = []
        for remaining in revision_by_fp.values():
            unmatched_revision.extend(remaining)

        # --- Step 2: Greedy nearest-neighbor on unmatched ---
        if unmatched_master and unmatched_revision:
            nn_pairs, still_master, still_revision = _greedy_nearest_neighbor(
                unmatched_master, unmatched_revision, config.tolerance
            )
            pairs.extend(nn_pairs)
            unmatched_master = still_master
            unmatched_revision = still_revision

        span.set_attribute("cad.compare.pairs_matched", len(pairs))
        span.set_attribute("cad.compare.master_unmatched", len(unmatched_master))
        span.set_attribute("cad.compare.revision_unmatched", len(unmatched_revision))

        return MatchResult(
            pairs=pairs,
            master_only=unmatched_master,
            revision_only=unmatched_revision,
        )


def _fingerprint(snap: GeometrySnapshot) -> str:
    """Compute a deterministic fingerprint for exact matching.

    Includes: entity_type, layer, rounded points, text, block_name.
    Points are kept in original order for order-dependent shapes (LWPOLYLINE,
    SPLINE, POLYLINE, LEADER, HATCH) and sorted only for LINE where
    start/end are interchangeable.
    """
    # Round points to avoid floating-point noise
    rounded_pts = [(round(p.x, 4), round(p.y, 4)) for p in snap.points]
    # Only sort for LINE — start/end order is arbitrary.
    # For LWPOLYLINE, SPLINE, etc., vertex order defines the shape.
    if snap.entity_type.value == "LINE":
        rounded_pts = sorted(rounded_pts)

    parts = [
        snap.entity_type.value,
        snap.layer,
        str(rounded_pts),
        snap.text_content or "",
        snap.block_name or "",
    ]
    raw = "|".join(parts)
    return hashlib.sha256(raw.encode()).hexdigest()


def _greedy_nearest_neighbor(
    master_snaps: list[GeometrySnapshot],
    revision_snaps: list[GeometrySnapshot],
    tolerance: float,
) -> tuple[
    list[tuple[GeometrySnapshot, GeometrySnapshot]],
    list[GeometrySnapshot],
    list[GeometrySnapshot],
]:
    """Greedy nearest-neighbor matching on centroids within tolerance.

    Groups by (entity_type, layer) first, then matches within each group.

    Returns:
        (pairs, remaining_master, remaining_revision)
    """
    pairs: list[tuple[GeometrySnapshot, GeometrySnapshot]] = []

    # Group by (entity_type, layer)
    master_groups: dict[tuple[str, str], list[GeometrySnapshot]] = defaultdict(list)
    revision_groups: dict[tuple[str, str], list[GeometrySnapshot]] = defaultdict(list)

    for snap in master_snaps:
        key = (snap.entity_type.value, snap.layer)
        master_groups[key].append(snap)

    for snap in revision_snaps:
        key = (snap.entity_type.value, snap.layer)
        revision_groups[key].append(snap)

    remaining_master: list[GeometrySnapshot] = []
    remaining_revision: list[GeometrySnapshot] = []
    matched_revision_keys: set[tuple[str, str]] = set()

    for group_key, m_list in master_groups.items():
        r_list = revision_groups.get(group_key)
        if not r_list:
            remaining_master.extend(m_list)
            continue

        matched_revision_keys.add(group_key)
        g_pairs, g_m_left, g_r_left = _match_group(m_list, r_list, tolerance)
        pairs.extend(g_pairs)
        remaining_master.extend(g_m_left)
        remaining_revision.extend(g_r_left)

    # Revision groups with no master counterpart
    for group_key, r_list in revision_groups.items():
        if group_key not in matched_revision_keys:
            remaining_revision.extend(r_list)

    return pairs, remaining_master, remaining_revision


def _match_group(
    m_list: list[GeometrySnapshot],
    r_list: list[GeometrySnapshot],
    tolerance: float,
) -> tuple[
    list[tuple[GeometrySnapshot, GeometrySnapshot]],
    list[GeometrySnapshot],
    list[GeometrySnapshot],
]:
    """Match entities within a single (type, layer) group by centroid distance."""
    pairs: list[tuple[GeometrySnapshot, GeometrySnapshot]] = []

    # Build distance candidates
    candidates: list[tuple[float, int, int]] = []
    for mi, m_snap in enumerate(m_list):
        for ri, r_snap in enumerate(r_list):
            d = _centroid_distance(m_snap.centroid, r_snap.centroid)
            if d <= tolerance:
                candidates.append((d, mi, ri))

    # Sort by distance (greedy: closest first)
    candidates.sort(key=lambda x: x[0])

    matched_m: set[int] = set()
    matched_r: set[int] = set()

    for _dist, mi, ri in candidates:
        if mi in matched_m or ri in matched_r:
            continue
        pairs.append((m_list[mi], r_list[ri]))
        matched_m.add(mi)
        matched_r.add(ri)

    m_left = [m_list[i] for i in range(len(m_list)) if i not in matched_m]
    r_left = [r_list[i] for i in range(len(r_list)) if i not in matched_r]

    return pairs, m_left, r_left


def _centroid_distance(a: Point2D, b: Point2D) -> float:
    """Euclidean distance between two points."""
    return math.sqrt((a.x - b.x) ** 2 + (a.y - b.y) ** 2)

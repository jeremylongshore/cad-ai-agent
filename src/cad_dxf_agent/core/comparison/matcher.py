"""Entity matching — fingerprint hash + confidence-scored matching."""

from __future__ import annotations

import hashlib
import math
from collections import defaultdict

from ...models.cad_schema import Point2D
from ...models.comparison_schema import (
    ComparisonConfig,
    GeometrySnapshot,
    MatchExplanation,
    MatchMethod,
    MatchResult,
    ScoredMatch,
)
from ...otel import get_tracer
from .scorer import find_candidates, score_match

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

        pairs: list[ScoredMatch] = []

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
                pairs.append(
                    ScoredMatch(
                        master=m_snap,
                        revision=r_snap,
                        confidence=1.0,
                        method=MatchMethod.fingerprint,
                    )
                )
            else:
                unmatched_master.append(m_snap)

        # Collect unmatched revision snapshots
        unmatched_revision: list[GeometrySnapshot] = []
        for remaining in revision_by_fp.values():
            unmatched_revision.extend(remaining)

        # --- Step 2: Confidence-scored matching on unmatched ---
        if unmatched_master and unmatched_revision:
            scored_pairs, still_master, still_revision = _scored_matching(
                unmatched_master, unmatched_revision, config.tolerance
            )
            pairs.extend(scored_pairs)
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


def _scored_matching(
    master_snaps: list[GeometrySnapshot],
    revision_snaps: list[GeometrySnapshot],
    tolerance: float,
) -> tuple[
    list[ScoredMatch],
    list[GeometrySnapshot],
    list[GeometrySnapshot],
]:
    """Confidence-scored matching using per-type scoring functions.

    For each master entity:
    1. find_candidates filters revision pool by (type, layer) + tolerance
    2. score_match scores each candidate using type-specific logic
    3. Global greedy assignment picks highest-score pairs first
    4. Runner-up tracking flags ambiguous matches

    Returns:
        (pairs, remaining_master, remaining_revision)
    """
    # Build scored candidates across all master entities
    # Each entry: (score, master_idx, revision_idx, explanation)
    scored_candidates: list[tuple[float, int, int, MatchExplanation]] = []

    # Index revision snaps for lookup by object identity
    rev_index: dict[int, int] = {}
    for ri, r_snap in enumerate(revision_snaps):
        rev_index[id(r_snap)] = ri

    for mi, m_snap in enumerate(master_snaps):
        candidates = find_candidates(m_snap, revision_snaps, tolerance)
        for r_snap, _dist in candidates:
            ri = rev_index[id(r_snap)]
            s, explanation = score_match(m_snap, r_snap, tolerance)
            scored_candidates.append((s, mi, ri, explanation))

    # Sort descending by score (highest confidence first)
    scored_candidates.sort(key=lambda x: -x[0])

    # Track per-master scores for runner-up computation
    scores_by_master: dict[int, list[float]] = defaultdict(list)
    for s, mi, _ri, _expl in scored_candidates:
        scores_by_master[mi].append(s)

    # Greedy assignment: highest score first, skip already-matched
    matched_m: set[int] = set()
    matched_r: set[int] = set()
    pairs: list[ScoredMatch] = []

    for s, mi, ri, explanation in scored_candidates:
        if mi in matched_m or ri in matched_r:
            continue

        # Runner-up: second-best score for this master
        master_scores = scores_by_master[mi]
        runner_up_score: float | None = None
        if len(master_scores) > 1:
            # Scores are in insertion order; find the second-best
            sorted_scores = sorted(master_scores, reverse=True)
            runner_up_score = sorted_scores[1]

        ambiguous = runner_up_score is not None and (s - runner_up_score) < 0.1

        pairs.append(
            ScoredMatch(
                master=master_snaps[mi],
                revision=revision_snaps[ri],
                confidence=s,
                method=MatchMethod.spatial,
                runner_up_score=runner_up_score,
                ambiguous=ambiguous,
                explanation=explanation,
            )
        )
        matched_m.add(mi)
        matched_r.add(ri)

    remaining_master = [master_snaps[i] for i in range(len(master_snaps)) if i not in matched_m]
    remaining_revision = [
        revision_snaps[i] for i in range(len(revision_snaps)) if i not in matched_r
    ]

    return pairs, remaining_master, remaining_revision


def _centroid_distance(a: Point2D, b: Point2D) -> float:
    """Euclidean distance between two points."""
    return math.sqrt((a.x - b.x) ** 2 + (a.y - b.y) ** 2)

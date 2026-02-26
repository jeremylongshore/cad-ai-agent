"""Change classification — categorize matched entities as added/removed/modified/moved."""

from __future__ import annotations

import math

from ...models.cad_schema import Point2D
from ...models.comparison_schema import (
    ChangeCategory,
    ComparisonConfig,
    ComparisonResult,
    EntityChange,
    GeometrySnapshot,
    MatchResult,
)


def classify_changes(
    match_result: MatchResult,
    config: ComparisonConfig | None = None,
) -> ComparisonResult:
    """Classify every entity pair/orphan into a change category.

    Args:
        match_result: Output from the matcher step.
        config: Comparison configuration.

    Returns:
        ComparisonResult with all changes classified and summary counts.
    """
    config = config or ComparisonConfig()
    changes: list[EntityChange] = []

    # Classify matched pairs
    for m_snap, r_snap in match_result.pairs:
        change = _classify_pair(m_snap, r_snap, config)
        changes.append(change)

    # Unmatched master → REMOVED
    for m_snap in match_result.master_only:
        changes.append(
            EntityChange(
                category=ChangeCategory.REMOVED,
                master_snapshot=m_snap,
                revision_snapshot=None,
            )
        )

    # Unmatched revision → ADDED
    for r_snap in match_result.revision_only:
        changes.append(
            EntityChange(
                category=ChangeCategory.ADDED,
                master_snapshot=None,
                revision_snapshot=r_snap,
            )
        )

    # Build summary
    summary = {cat.value: 0 for cat in ChangeCategory}
    for change in changes:
        summary[change.category.value] += 1

    return ComparisonResult(changes=changes, summary=summary, config=config)


def _classify_pair(
    m_snap: GeometrySnapshot,
    r_snap: GeometrySnapshot,
    config: ComparisonConfig,
) -> EntityChange:
    """Classify a single matched (master, revision) pair."""
    displacement = Point2D(
        x=r_snap.centroid.x - m_snap.centroid.x,
        y=r_snap.centroid.y - m_snap.centroid.y,
    )
    dist = math.sqrt(displacement.x**2 + displacement.y**2)

    points_match = _points_match(m_snap.points, r_snap.points, config.tolerance)
    content_match = _content_matches(m_snap, r_snap)

    if dist < config.move_threshold and points_match and content_match:
        # Everything matches — UNCHANGED
        return EntityChange(
            category=ChangeCategory.UNCHANGED,
            master_snapshot=m_snap,
            revision_snapshot=r_snap,
        )

    if (
        dist >= config.move_threshold
        and _shape_matches_after_translation(
            m_snap.points, r_snap.points, displacement, config.tolerance
        )
        and content_match
    ):
        # Same shape, shifted position — MOVED
        return EntityChange(
            category=ChangeCategory.MOVED,
            master_snapshot=m_snap,
            revision_snapshot=r_snap,
            displacement=displacement,
        )

    # Something changed — MODIFIED
    modifications = _describe_modifications(m_snap, r_snap)
    return EntityChange(
        category=ChangeCategory.MODIFIED,
        master_snapshot=m_snap,
        revision_snapshot=r_snap,
        modifications=modifications,
    )


def _points_match(a: list[Point2D], b: list[Point2D], tolerance: float) -> bool:
    """Check if two point lists match within tolerance (same count, pairwise)."""
    if len(a) != len(b):
        return False
    tol_sq = tolerance * tolerance
    for pa, pb in zip(a, b, strict=True):
        if (pa.x - pb.x) ** 2 + (pa.y - pb.y) ** 2 > tol_sq:
            return False
    return True


def _shape_matches_after_translation(
    master_pts: list[Point2D],
    revision_pts: list[Point2D],
    displacement: Point2D,
    tolerance: float,
) -> bool:
    """Check if revision points match master points translated by displacement."""
    if len(master_pts) != len(revision_pts):
        return False
    tol_sq = tolerance * tolerance
    for mp, rp in zip(master_pts, revision_pts, strict=True):
        translated_x = mp.x + displacement.x
        translated_y = mp.y + displacement.y
        if (translated_x - rp.x) ** 2 + (translated_y - rp.y) ** 2 > tol_sq:
            return False
    return True


def _content_matches(a: GeometrySnapshot, b: GeometrySnapshot) -> bool:
    """Check if text content, block name, and key attributes match."""
    if a.text_content != b.text_content:
        return False
    if a.block_name != b.block_name:
        return False
    # Check key attributes that affect identity (radius, angles, ratio)
    for key in ("radius", "start_angle", "end_angle", "ratio"):
        va = a.attributes.get(key)
        vb = b.attributes.get(key)
        if va != vb:
            if isinstance(va, (int, float)) and isinstance(vb, (int, float)):
                if not math.isclose(va, vb, abs_tol=1e-6):
                    return False
            else:
                return False
    return True


def _describe_modifications(
    m_snap: GeometrySnapshot, r_snap: GeometrySnapshot
) -> dict[str, object]:
    """Build a dict describing what changed between master and revision."""
    mods: dict[str, object] = {}

    if m_snap.text_content != r_snap.text_content:
        mods["text_content"] = {
            "from": m_snap.text_content,
            "to": r_snap.text_content,
        }

    if m_snap.block_name != r_snap.block_name:
        mods["block_name"] = {
            "from": m_snap.block_name,
            "to": r_snap.block_name,
        }

    if len(m_snap.points) != len(r_snap.points):
        mods["point_count"] = {
            "from": len(m_snap.points),
            "to": len(r_snap.points),
        }
    else:
        changed_points = []
        for i, (mp, rp) in enumerate(zip(m_snap.points, r_snap.points, strict=True)):
            dist = math.sqrt((mp.x - rp.x) ** 2 + (mp.y - rp.y) ** 2)
            if dist > 1e-6:
                changed_points.append(i)
        if changed_points:
            mods["changed_point_indices"] = changed_points

    for key in ("radius", "start_angle", "end_angle", "ratio"):
        va = m_snap.attributes.get(key)
        vb = r_snap.attributes.get(key)
        if va != vb:
            mods[key] = {"from": va, "to": vb}

    return mods

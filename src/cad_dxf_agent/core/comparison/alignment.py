"""Alignment ladder — auto-align shifted or rotated revision drawings to master.

Pipeline: identity check → anchor-based → feature-based → fail with guidance.
Each step computes a rigid transform (translation + rotation) and scores it.
The first step that meets the confidence threshold wins.

Uses Kabsch algorithm (SVD-based) for rigid body alignment from paired points.
"""

from __future__ import annotations

import fnmatch
import logging
import math
from collections import defaultdict
from collections.abc import Callable

import numpy as np

from ...models.cad_schema import EntityType, Point2D
from ...models.comparison_schema import (
    AlignmentAttempt,
    AlignmentConfig,
    AlignmentDiagnostics,
    AlignmentMethod,
    AlignmentResult,
    GeometrySnapshot,
)
from ...otel import get_tracer

logger = logging.getLogger(__name__)
tracer = get_tracer(__name__)

# Confidence scoring weights
_OVERLAP_WEIGHT = 0.4
_RESIDUAL_WEIGHT = 0.3
_INLIER_WEIGHT = 0.3


# ---------------------------------------------------------------------------
# Core math: Kabsch rigid alignment
# ---------------------------------------------------------------------------


def _kabsch(master_pts: np.ndarray, revision_pts: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    """Compute optimal rigid transform (R, t) aligning revision to master.

    Minimizes sum of ||master[i] - (R @ revision[i] + t)||^2.

    Args:
        master_pts: (N, 2) array of master points.
        revision_pts: (N, 2) array of corresponding revision points.

    Returns:
        (R, t) where R is (2, 2) rotation matrix, t is (2,) translation vector.
        Transform: aligned = R @ revision + t
    """
    assert master_pts.shape == revision_pts.shape
    assert master_pts.shape[1] == 2

    # Centroids
    cm = master_pts.mean(axis=0)
    cr = revision_pts.mean(axis=0)

    # Center the points
    qm = master_pts - cm
    qr = revision_pts - cr

    # Cross-covariance matrix
    H = qr.T @ qm  # (2, 2)

    # SVD
    U, _S, Vt = np.linalg.svd(H)

    # Optimal rotation (handle reflection)
    d = np.linalg.det(Vt.T @ U.T)
    sign_matrix = np.diag([1.0, float(np.sign(d))])
    R = Vt.T @ sign_matrix @ U.T

    # Translation
    t = cm - R @ cr

    return R, t


def _rotation_to_degrees(R: np.ndarray) -> float:
    """Extract rotation angle in degrees from a 2×2 rotation matrix."""
    return float(math.degrees(math.atan2(R[1, 0], R[0, 0])))


def _transform_point(point: Point2D, R: np.ndarray, t: np.ndarray) -> Point2D:
    """Apply rigid transform to a single point."""
    p = np.array([point.x, point.y])
    tp = R @ p + t
    return Point2D(x=float(tp[0]), y=float(tp[1]))


def _transform_snapshots(
    snapshots: list[GeometrySnapshot],
    R: np.ndarray,
    t: np.ndarray,
) -> list[GeometrySnapshot]:
    """Apply rigid transform to all points in a list of snapshots."""
    result = []
    for snap in snapshots:
        new_points = [_transform_point(p, R, t) for p in snap.points]
        result.append(snap.model_copy(update={"points": new_points}))
    return result


# ---------------------------------------------------------------------------
# Scoring: RMS residual, overlap, confidence
# ---------------------------------------------------------------------------


def _rms_residual(
    master_pts: np.ndarray,
    revision_pts: np.ndarray,
    R: np.ndarray,
    t: np.ndarray,
) -> float:
    """Compute RMS residual after applying transform to revision points."""
    aligned = (R @ revision_pts.T).T + t
    residuals = np.linalg.norm(master_pts - aligned, axis=1)
    return float(np.sqrt(np.mean(residuals**2)))


def _count_inliers(
    master_pts: np.ndarray,
    revision_pts: np.ndarray,
    R: np.ndarray,
    t: np.ndarray,
    tolerance: float,
) -> int:
    """Count pairs where aligned revision is within tolerance of master."""
    aligned = (R @ revision_pts.T).T + t
    dists = np.linalg.norm(master_pts - aligned, axis=1)
    return int(np.sum(dists <= tolerance))


def _overlap_ratio(
    master_snaps: list[GeometrySnapshot],
    revision_snaps: list[GeometrySnapshot],
    R: np.ndarray,
    t: np.ndarray,
    tolerance: float,
) -> float:
    """Fraction of master centroids with a nearby revision centroid.

    Uses vectorized pairwise distance computation (O(M*N) memory but
    fast via numpy broadcasting). For typical CAD drawings (<5K entities)
    this is efficient without a k-d tree.
    """
    if not master_snaps:
        return 0.0
    m_c = np.array([[s.centroid.x, s.centroid.y] for s in master_snaps])
    r_c = np.array([[s.centroid.x, s.centroid.y] for s in revision_snaps])
    if r_c.size == 0:
        return 0.0
    aligned_rev = (R @ r_c.T).T + t
    # Vectorized: (M, 1, 2) - (1, N, 2) → (M, N) distances
    diffs = m_c[:, np.newaxis, :] - aligned_rev[np.newaxis, :, :]
    dists = np.linalg.norm(diffs, axis=2)  # (M, N)
    matched = int(np.sum(dists.min(axis=1) <= tolerance))
    return matched / len(m_c)


def score_alignment(
    master_pts: np.ndarray,
    revision_pts: np.ndarray,
    R: np.ndarray,
    t: np.ndarray,
    master_snaps: list[GeometrySnapshot],
    revision_snaps: list[GeometrySnapshot],
    tolerance: float,
) -> AlignmentDiagnostics:
    """Compute all diagnostic metrics for an alignment."""
    rms = _rms_residual(master_pts, revision_pts, R, t)
    inliers = _count_inliers(master_pts, revision_pts, R, t, tolerance)
    overlap = _overlap_ratio(master_snaps, revision_snaps, R, t, tolerance)
    return AlignmentDiagnostics(
        rms_residual=round(rms, 6),
        overlap_ratio=round(overlap, 4),
        match_count=len(master_pts),
        inlier_count=inliers,
    )


def compute_confidence(diagnostics: AlignmentDiagnostics, max_residual: float) -> float:
    """Combine diagnostics into a single confidence score (0-1).

    Heuristic: weighted average of overlap ratio, residual quality,
    and inlier ratio.
    """
    if diagnostics.match_count == 0:
        return 0.0
    # Residual score: 1.0 when rms=0, 0.0 when rms >= max_residual
    residual_score = max(0.0, 1.0 - diagnostics.rms_residual / max_residual)
    inlier_ratio = diagnostics.inlier_count / diagnostics.match_count
    confidence = (
        _OVERLAP_WEIGHT * diagnostics.overlap_ratio
        + _RESIDUAL_WEIGHT * residual_score
        + _INLIER_WEIGHT * inlier_ratio
    )
    return round(min(1.0, max(0.0, confidence)), 4)


# ---------------------------------------------------------------------------
# Step 1: Identity check (already aligned)
# ---------------------------------------------------------------------------


def _try_identity(
    master_snaps: list[GeometrySnapshot],
    revision_snaps: list[GeometrySnapshot],
    config: AlignmentConfig,
) -> AlignmentResult | None:
    """Check if drawings are already aligned (identity transform)."""
    R = np.eye(2)
    t = np.zeros(2)
    tolerance = config.max_residual

    if not master_snaps or not revision_snaps:
        return None

    m_pts = np.array([[s.centroid.x, s.centroid.y] for s in master_snaps])

    # Quick check: are centroid clouds roughly the same?
    overlap = _overlap_ratio(master_snaps, revision_snaps, R, t, tolerance)
    if overlap < config.confidence_threshold:
        return None

    diag = AlignmentDiagnostics(
        rms_residual=0.0,
        overlap_ratio=round(overlap, 4),
        match_count=min(len(m_pts), len(revision_snaps)),
        inlier_count=int(overlap * len(m_pts)),
    )
    confidence = compute_confidence(diag, config.max_residual)
    if confidence < config.confidence_threshold:
        return None

    return AlignmentResult(
        method=AlignmentMethod.identity,
        confidence=confidence,
        translation=(0.0, 0.0),
        rotation_deg=0.0,
        rotation_center=(0.0, 0.0),
        diagnostics=diag,
    )


# ---------------------------------------------------------------------------
# Step 2: Anchor-based alignment (shared INSERT blocks)
# ---------------------------------------------------------------------------


def _find_anchor_pairs(
    master_snaps: list[GeometrySnapshot],
    revision_snaps: list[GeometrySnapshot],
    config: AlignmentConfig,
) -> list[tuple[GeometrySnapshot, GeometrySnapshot]]:
    """Find shared INSERT blocks that serve as alignment anchors.

    Matches by block_name. When multiple inserts share a block_name,
    matches greedily by closest centroid distance.
    """
    patterns = config.anchor_layer_patterns

    def _is_anchor(snap: GeometrySnapshot) -> bool:
        if snap.entity_type != EntityType.INSERT:
            return False
        if not snap.block_name:
            return False
        if not patterns:
            return True
        return any(fnmatch.fnmatch(snap.layer.upper(), p.upper()) for p in patterns)

    master_inserts = [s for s in master_snaps if _is_anchor(s)]
    revision_inserts = [s for s in revision_snaps if _is_anchor(s)]

    if not master_inserts or not revision_inserts:
        return []

    # Group by block_name
    m_by_block: dict[str, list[GeometrySnapshot]] = defaultdict(list)
    r_by_block: dict[str, list[GeometrySnapshot]] = defaultdict(list)
    for s in master_inserts:
        m_by_block[s.block_name or ""].append(s)
    for s in revision_inserts:
        r_by_block[s.block_name or ""].append(s)

    pairs: list[tuple[GeometrySnapshot, GeometrySnapshot]] = []
    for block_name in m_by_block:
        m_list = m_by_block[block_name]
        r_list = r_by_block.get(block_name, [])
        if not r_list:
            continue

        # Greedy closest centroid matching
        used_r: set[int] = set()
        for m_snap in m_list:
            best_d = float("inf")
            best_ri = -1
            for ri, r_snap in enumerate(r_list):
                if ri in used_r:
                    continue
                d = math.sqrt(
                    (m_snap.centroid.x - r_snap.centroid.x) ** 2
                    + (m_snap.centroid.y - r_snap.centroid.y) ** 2
                )
                if d < best_d:
                    best_d = d
                    best_ri = ri
            if best_ri >= 0:
                pairs.append((m_snap, r_list[best_ri]))
                used_r.add(best_ri)

    return pairs


def try_anchor_alignment(
    master_snaps: list[GeometrySnapshot],
    revision_snaps: list[GeometrySnapshot],
    config: AlignmentConfig,
) -> AlignmentResult | None:
    """Attempt alignment using shared INSERT block anchors."""
    pairs = _find_anchor_pairs(master_snaps, revision_snaps, config)
    if len(pairs) < 2:
        return None

    m_pts = np.array([[s.centroid.x, s.centroid.y] for s, _ in pairs])
    r_pts = np.array([[s.centroid.x, s.centroid.y] for _, s in pairs])

    R, t = _kabsch(m_pts, r_pts)
    diag = score_alignment(
        m_pts,
        r_pts,
        R,
        t,
        master_snaps,
        revision_snaps,
        config.max_residual,
    )
    confidence = compute_confidence(diag, config.max_residual)

    if confidence < config.confidence_threshold:
        return None

    rot_deg = _rotation_to_degrees(R)
    rc = r_pts.mean(axis=0)

    return AlignmentResult(
        method=AlignmentMethod.anchor,
        confidence=confidence,
        translation=(float(t[0]), float(t[1])),
        rotation_deg=round(rot_deg, 6),
        rotation_center=(float(rc[0]), float(rc[1])),
        diagnostics=diag,
    )


# ---------------------------------------------------------------------------
# Step 3: Feature-based alignment (geometry endpoints/corners/centroids)
# ---------------------------------------------------------------------------

# Entity types whose individual vertices are used as feature points.
_VERTEX_TYPES = {EntityType.LINE, EntityType.LWPOLYLINE, EntityType.POLYLINE}


def _extract_feature_points(
    snaps: list[GeometrySnapshot],
) -> np.ndarray:
    """Extract distinctive feature points from entity geometry.

    Uses endpoints of LINE entities and vertices of polylines as features.
    Falls back to centroids if no good features found.
    """
    pts: list[tuple[float, float]] = []

    for snap in snaps:
        if snap.entity_type in _VERTEX_TYPES:
            for p in snap.points:
                pts.append((p.x, p.y))
        else:
            pts.append((snap.centroid.x, snap.centroid.y))

    if not pts:
        return np.empty((0, 2))

    return np.array(pts)


def _match_features_nn(
    m_features: np.ndarray,
    r_features: np.ndarray,
    tolerance: float,
) -> list[tuple[int, int]]:
    """Match feature points by nearest-neighbor within tolerance.

    Returns list of (master_idx, revision_idx) pairs.
    """
    if m_features.size == 0 or r_features.size == 0:
        return []

    pairs: list[tuple[float, int, int]] = []
    for mi in range(len(m_features)):
        dists = np.linalg.norm(r_features - m_features[mi], axis=1)
        best_ri = int(np.argmin(dists))
        best_d = float(dists[best_ri])
        pairs.append((best_d, mi, best_ri))

    # Sort by distance, greedy match
    pairs.sort()
    used_m: set[int] = set()
    used_r: set[int] = set()
    matched: list[tuple[int, int]] = []

    for d, mi, ri in pairs:
        if mi in used_m or ri in used_r:
            continue
        if d > tolerance:
            break
        matched.append((mi, ri))
        used_m.add(mi)
        used_r.add(ri)

    return matched


def _ransac_rigid(
    m_pts: np.ndarray,
    r_pts: np.ndarray,
    tolerance: float,
    max_iterations: int = 50,
    min_inlier_ratio: float = 0.5,
) -> tuple[np.ndarray, np.ndarray, np.ndarray] | None:
    """RANSAC-like robust rigid alignment from feature matches.

    Samples random pairs of points, computes Kabsch, scores by inlier count.

    Returns:
        (R, t, inlier_mask) or None if no good model found.
    """
    n = len(m_pts)
    if n < 2:
        return None

    best_inliers: np.ndarray | None = None
    best_count = 0
    best_R: np.ndarray | None = None
    best_t: np.ndarray | None = None

    rng = np.random.default_rng(42)  # deterministic seed
    sample_size = min(3, n)

    for _ in range(min(max_iterations, n * (n - 1) // 2)):
        indices = rng.choice(n, size=sample_size, replace=False)
        R_cand, t_cand = _kabsch(m_pts[indices], r_pts[indices])

        aligned = (R_cand @ r_pts.T).T + t_cand
        dists = np.linalg.norm(m_pts - aligned, axis=1)
        inliers = dists <= tolerance
        count = int(np.sum(inliers))

        if count > best_count:
            best_count = count
            best_inliers = inliers
            best_R = R_cand
            best_t = t_cand

    if best_count < max(2, int(min_inlier_ratio * n)):
        return None

    assert best_R is not None and best_t is not None
    assert best_inliers is not None

    # Refit on all inliers
    inlier_idx = np.where(best_inliers)[0]
    R_final, t_final = _kabsch(m_pts[inlier_idx], r_pts[inlier_idx])

    return R_final, t_final, best_inliers


def try_feature_alignment(
    master_snaps: list[GeometrySnapshot],
    revision_snaps: list[GeometrySnapshot],
    config: AlignmentConfig,
) -> AlignmentResult | None:
    """Attempt alignment using geometry feature points with RANSAC."""
    m_features = _extract_feature_points(master_snaps)
    r_features = _extract_feature_points(revision_snaps)

    if len(m_features) < 2 or len(r_features) < 2:
        return None

    # Generous tolerance for initial feature correspondences
    search_radius = max(config.max_residual * 10, 50.0)
    matches = _match_features_nn(m_features, r_features, search_radius)

    if len(matches) < 2:
        return None

    m_matched = np.array([m_features[mi] for mi, _ in matches])
    r_matched = np.array([r_features[ri] for _, ri in matches])

    # RANSAC for robust alignment
    result = _ransac_rigid(m_matched, r_matched, config.max_residual)
    if result is None:
        return None

    R, t, _inlier_mask = result
    diag = score_alignment(
        m_matched,
        r_matched,
        R,
        t,
        master_snaps,
        revision_snaps,
        config.max_residual,
    )
    confidence = compute_confidence(diag, config.max_residual)

    if confidence < config.confidence_threshold:
        return None

    rot_deg = _rotation_to_degrees(R)
    rc = r_matched.mean(axis=0)

    return AlignmentResult(
        method=AlignmentMethod.feature,
        confidence=confidence,
        translation=(float(t[0]), float(t[1])),
        rotation_deg=round(rot_deg, 6),
        rotation_center=(float(rc[0]), float(rc[1])),
        diagnostics=diag,
    )


# ---------------------------------------------------------------------------
# Manual alignment from user-supplied control points
# ---------------------------------------------------------------------------


def try_manual_alignment(
    master_snaps: list[GeometrySnapshot],
    revision_snaps: list[GeometrySnapshot],
    config: AlignmentConfig,
) -> AlignmentResult:
    """Compute alignment from user-supplied control point pairs.

    Args:
        master_snaps: Canonical snapshots from master DXF.
        revision_snaps: Canonical snapshots from revision DXF.
        config: Alignment configuration (must have control_points set).

    Returns:
        AlignmentResult with method=manual. Always returns a result
        (user points are trusted); confidence reflects geometric quality.
    """
    assert config.control_points is not None
    pairs = config.control_points

    m_pts = np.array([mp for mp, _rp in pairs])
    r_pts = np.array([rp for _mp, rp in pairs])

    if len(pairs) == 1:
        # Pure translation: t = master_pt - revision_pt, R = I
        R = np.eye(2)
        t = m_pts[0] - r_pts[0]
    else:
        # 2+ points: rigid transform via Kabsch
        R, t = _kabsch(m_pts, r_pts)

    rot_deg = _rotation_to_degrees(R)
    rc = r_pts.mean(axis=0)

    diag = score_alignment(m_pts, r_pts, R, t, master_snaps, revision_snaps, config.max_residual)
    confidence = compute_confidence(diag, config.max_residual)

    # Manual control points: trust the user's correspondence assertion.
    # Confidence floor based on control-point fit quality, not full-drawing overlap.
    if len(pairs) >= 2:
        transformed = (R @ r_pts.T).T + t
        cp_residuals = np.linalg.norm(m_pts - transformed, axis=1)
        cp_rms = float(np.sqrt(np.mean(cp_residuals**2)))
        cp_score = max(0.0, 1.0 - cp_rms / config.max_residual)
        confidence = max(confidence, 0.5 * cp_score + 0.2)
    elif len(pairs) == 1:
        confidence = max(confidence, 0.7)

    return AlignmentResult(
        method=AlignmentMethod.manual,
        confidence=confidence,
        translation=(float(t[0]), float(t[1])),
        rotation_deg=round(rot_deg, 6),
        rotation_center=(float(rc[0]), float(rc[1])),
        diagnostics=diag,
    )


# ---------------------------------------------------------------------------
# Ladder orchestrator
# ---------------------------------------------------------------------------

# Type alias for alignment method functions
_AlignFn = Callable[
    [list[GeometrySnapshot], list[GeometrySnapshot], AlignmentConfig],
    AlignmentResult | None,
]

# Ordered list of (method_name, function) to try
_LADDER_STEPS: list[tuple[str, _AlignFn]] = [
    ("identity", _try_identity),
    ("anchor", try_anchor_alignment),
    ("feature", try_feature_alignment),
]


def align_drawings(
    master_snaps: list[GeometrySnapshot],
    revision_snaps: list[GeometrySnapshot],
    config: AlignmentConfig,
) -> AlignmentResult:
    """Run the alignment ladder: identity → anchor → feature → fail.

    Tries each method in order. First one that meets the confidence
    threshold wins. If all fail, returns a failed result with guidance.

    Args:
        master_snaps: Canonical snapshots from master DXF.
        revision_snaps: Canonical snapshots from revision DXF.
        config: Alignment configuration.

    Returns:
        AlignmentResult (always — check confidence and guidance
        for failures).
    """
    with tracer.start_as_current_span("cad.compare.align_drawings") as span:
        attempts: list[AlignmentAttempt] = []

        # Manual control points take priority over the automatic ladder
        if config.control_points:
            logger.info("Alignment: using %d manual control points", len(config.control_points))
            manual_result = try_manual_alignment(master_snaps, revision_snaps, config)
            attempts.append(
                AlignmentAttempt(
                    method="manual",
                    success=True,
                    confidence=manual_result.confidence,
                )
            )
            manual_result.diagnostics.attempts = attempts
            span.set_attribute("cad.align.method", "manual")
            span.set_attribute("cad.align.confidence", manual_result.confidence)
            return manual_result

        for method_name, method_fn in _LADDER_STEPS:
            logger.info("Alignment: trying %s", method_name)
            result = method_fn(master_snaps, revision_snaps, config)

            attempts.append(
                AlignmentAttempt(
                    method=method_name,
                    success=result is not None,
                    confidence=result.confidence if result else 0.0,
                )
            )

            if result is not None:
                result.diagnostics.attempts = attempts
                span.set_attribute("cad.align.method", method_name)
                span.set_attribute("cad.align.confidence", result.confidence)
                logger.info(
                    "Alignment: %s accepted (confidence=%.4f)",
                    method_name,
                    result.confidence,
                )
                return result

        # All methods failed
        span.set_attribute("cad.align.method", "none")
        span.set_attribute("cad.align.confidence", 0.0)
        logger.warning("Alignment: all automatic methods failed")

        return AlignmentResult(
            method=AlignmentMethod.identity,
            confidence=0.0,
            translation=(0.0, 0.0),
            rotation_deg=0.0,
            rotation_center=(0.0, 0.0),
            diagnostics=AlignmentDiagnostics(attempts=attempts),
            guidance=(
                "Automatic alignment failed. The drawings may have "
                "significant differences in coordinate systems. Try "
                "supplying 2-3 control point pairs (matching features "
                "in both drawings) to enable manual alignment."
            ),
        )


def apply_alignment(
    revision_snaps: list[GeometrySnapshot],
    alignment: AlignmentResult,
) -> list[GeometrySnapshot]:
    """Apply alignment transform to revision snapshots.

    If alignment confidence is 0 or method is identity with no
    transform, returns the original snapshots unchanged.
    """
    # No-op for identity with no actual transform
    if (
        alignment.method == AlignmentMethod.identity
        and alignment.translation == (0.0, 0.0)
        and alignment.rotation_deg == 0.0
    ):
        return revision_snaps

    # Build transform matrices
    tx, ty = alignment.translation
    angle_rad = math.radians(alignment.rotation_deg)
    cos_a = math.cos(angle_rad)
    sin_a = math.sin(angle_rad)

    R = np.array([[cos_a, -sin_a], [sin_a, cos_a]])
    t = np.array([tx, ty])

    return _transform_snapshots(revision_snaps, R, t)

"""Tests for the alignment ladder (E2: cad-31i).

Covers:
  cad-31i.1 — Schema contract validation
  cad-31i.2 — Anchor-based alignment
  cad-31i.3 — Feature-based alignment
  cad-31i.4 — Alignment quality scoring
  cad-31i.6 — Ladder orchestrator
"""

from __future__ import annotations

import math

import numpy as np
import pytest

from cad_dxf_agent.core.comparison.alignment import (
    _extract_feature_points,
    _kabsch,
    _match_features_nn,
    _ransac_rigid,
    align_drawings,
    apply_alignment,
    compute_confidence,
    score_alignment,
    try_anchor_alignment,
    try_feature_alignment,
    try_manual_alignment,
)
from cad_dxf_agent.core.comparison.geometry import extract_snapshots
from cad_dxf_agent.models.cad_schema import EntityType, Point2D
from cad_dxf_agent.models.comparison_schema import (
    AlignmentConfig,
    AlignmentDiagnostics,
    AlignmentMethod,
    AlignmentResult,
    ComparisonConfig,
    ComparisonResult,
    GeometrySnapshot,
)

from ..helpers.comparison_factory import (
    make_anchor_pair,
    make_identical_pair,
    make_offset_pair,
    make_rotated_pair,
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_snap(
    x: float,
    y: float,
    entity_type: EntityType = EntityType.LINE,
    layer: str = "STRUCTURAL",
    handle: str = "FF",
    points: list[Point2D] | None = None,
    block_name: str | None = None,
) -> GeometrySnapshot:
    """Quick snapshot builder for unit tests."""
    if points is None:
        points = [Point2D(x=x, y=y)]
    return GeometrySnapshot(
        handle=handle,
        entity_type=entity_type,
        layer=layer,
        points=points,
        block_name=block_name,
    )


def _make_insert(x: float, y: float, block_name: str, layer: str = "GRID") -> GeometrySnapshot:
    """Quick INSERT snapshot for anchor tests."""
    return GeometrySnapshot(
        handle="FF",
        entity_type=EntityType.INSERT,
        layer=layer,
        points=[Point2D(x=x, y=y)],
        block_name=block_name,
    )


# ---------------------------------------------------------------------------
# cad-31i.1: Schema contract validation
# ---------------------------------------------------------------------------


class TestAlignmentSchema:
    """Schema contract tests (cad-31i.1)."""

    def test_alignment_method_values(self):
        assert AlignmentMethod.identity == "identity"
        assert AlignmentMethod.translation == "translation"
        assert AlignmentMethod.rigid == "rigid"
        assert AlignmentMethod.anchor == "anchor"
        assert AlignmentMethod.feature == "feature"
        assert AlignmentMethod.manual == "manual"

    def test_alignment_config_defaults(self):
        cfg = AlignmentConfig()
        assert cfg.enabled is False
        assert cfg.confidence_threshold == 0.7
        assert cfg.max_residual == 1.0
        assert len(cfg.anchor_layer_patterns) > 0

    def test_alignment_config_custom(self):
        cfg = AlignmentConfig(enabled=True, confidence_threshold=0.9, max_residual=0.5)
        assert cfg.enabled is True
        assert cfg.confidence_threshold == 0.9

    def test_alignment_config_validation(self):
        from pydantic import ValidationError

        with pytest.raises(ValidationError):
            AlignmentConfig(confidence_threshold=1.5)
        with pytest.raises(ValidationError):
            AlignmentConfig(confidence_threshold=-0.1)
        with pytest.raises(ValidationError):
            AlignmentConfig(max_residual=0.0)

    def test_alignment_result_defaults(self):
        r = AlignmentResult(method=AlignmentMethod.identity, confidence=1.0)
        assert r.translation == (0.0, 0.0)
        assert r.rotation_deg == 0.0
        assert r.rotation_center == (0.0, 0.0)
        assert r.diagnostics.rms_residual == 0.0
        assert r.guidance is None

    def test_alignment_result_with_guidance(self):
        r = AlignmentResult(
            method=AlignmentMethod.identity, confidence=0.0, guidance="Try manual alignment"
        )
        assert r.guidance == "Try manual alignment"

    def test_alignment_diagnostics(self):
        d = AlignmentDiagnostics(
            rms_residual=0.1, overlap_ratio=0.95, match_count=10, inlier_count=9
        )
        assert d.rms_residual == 0.1
        assert d.overlap_ratio == 0.95

    def test_comparison_config_has_alignment(self):
        cfg = ComparisonConfig()
        assert cfg.alignment.enabled is False

    def test_comparison_config_alignment_enabled(self):
        cfg = ComparisonConfig(alignment=AlignmentConfig(enabled=True))
        assert cfg.alignment.enabled is True

    def test_comparison_result_has_alignment_result(self):
        r = ComparisonResult()
        assert r.alignment_result is None

    def test_comparison_result_with_alignment(self):
        ar = AlignmentResult(method=AlignmentMethod.anchor, confidence=0.95)
        r = ComparisonResult(alignment_result=ar)
        assert r.alignment_result is not None
        assert r.alignment_result.method == AlignmentMethod.anchor


# ---------------------------------------------------------------------------
# Core math: Kabsch
# ---------------------------------------------------------------------------


class TestKabsch:
    """Kabsch rigid alignment tests."""

    def test_identity_transform(self):
        """Identical point sets should produce identity."""
        pts = np.array([[0, 0], [1, 0], [0, 1]], dtype=float)
        R, t = _kabsch(pts, pts)
        np.testing.assert_allclose(R, np.eye(2), atol=1e-10)
        np.testing.assert_allclose(t, [0, 0], atol=1e-10)

    def test_pure_translation(self):
        """Translated points should recover translation vector."""
        master = np.array([[0, 0], [10, 0], [0, 10]], dtype=float)
        offset = np.array([5, 3])
        revision = master - offset  # revision is shifted left/down
        R, t = _kabsch(master, revision)
        np.testing.assert_allclose(R, np.eye(2), atol=1e-10)
        np.testing.assert_allclose(t, offset, atol=1e-10)

    def test_pure_rotation(self):
        """Rotated points should recover rotation angle."""
        angle = math.radians(30)
        R_true = np.array([[math.cos(angle), -math.sin(angle)], [math.sin(angle), math.cos(angle)]])
        master = np.array([[0, 0], [10, 0], [0, 10], [10, 10]], dtype=float)
        # Rotate around centroid
        cm = master.mean(axis=0)
        revision = ((R_true @ (master - cm).T).T) + cm
        # But Kabsch finds R,t such that master = R @ revision + t
        # So we need: R_inv @ (master - t) = revision
        R_found, t_found = _kabsch(master, revision)
        # Verify aligned = R @ revision + t ≈ master
        aligned = (R_found @ revision.T).T + t_found
        np.testing.assert_allclose(aligned, master, atol=1e-10)

    def test_rotation_plus_translation(self):
        """Combined rotation and translation."""
        angle = math.radians(45)
        R_true = np.array([[math.cos(angle), -math.sin(angle)], [math.sin(angle), math.cos(angle)]])
        t_true = np.array([10, -5])
        master = np.array([[0, 0], [20, 0], [0, 20], [20, 20]], dtype=float)
        revision = (np.linalg.inv(R_true) @ (master - t_true).T).T
        R_found, t_found = _kabsch(master, revision)
        aligned = (R_found @ revision.T).T + t_found
        np.testing.assert_allclose(aligned, master, atol=1e-10)


# ---------------------------------------------------------------------------
# cad-31i.4: Scoring
# ---------------------------------------------------------------------------


class TestScoring:
    """Alignment quality scoring tests (cad-31i.4)."""

    def test_perfect_alignment_rms_zero(self):
        pts = np.array([[0, 0], [10, 0], [5, 5]], dtype=float)
        R = np.eye(2)
        t = np.zeros(2)
        diag = score_alignment(pts, pts, R, t, [], [], 1.0)
        assert diag.rms_residual == 0.0
        assert diag.match_count == 3
        assert diag.inlier_count == 3

    def test_translated_alignment_scoring(self):
        master = np.array([[0, 0], [10, 0]], dtype=float)
        revision = master - np.array([5, 3])
        R = np.eye(2)
        t = np.array([5, 3])
        diag = score_alignment(master, revision, R, t, [], [], 1.0)
        assert diag.rms_residual < 0.001
        assert diag.inlier_count == 2

    def test_confidence_perfect(self):
        diag = AlignmentDiagnostics(
            rms_residual=0.0, overlap_ratio=1.0, match_count=10, inlier_count=10
        )
        c = compute_confidence(diag, max_residual=1.0)
        assert c == 1.0

    def test_confidence_zero_matches(self):
        diag = AlignmentDiagnostics(
            rms_residual=0.0, overlap_ratio=0.0, match_count=0, inlier_count=0
        )
        c = compute_confidence(diag, max_residual=1.0)
        assert c == 0.0

    def test_confidence_mediocre(self):
        diag = AlignmentDiagnostics(
            rms_residual=0.5, overlap_ratio=0.5, match_count=10, inlier_count=5
        )
        c = compute_confidence(diag, max_residual=1.0)
        assert 0.2 < c < 0.8

    def test_confidence_bounded(self):
        """Confidence must be in [0, 1]."""
        diag = AlignmentDiagnostics(
            rms_residual=100.0, overlap_ratio=0.0, match_count=1, inlier_count=0
        )
        c = compute_confidence(diag, max_residual=1.0)
        assert 0.0 <= c <= 1.0


# ---------------------------------------------------------------------------
# cad-31i.2: Anchor alignment
# ---------------------------------------------------------------------------


class TestAnchorAlignment:
    """Anchor-based alignment tests (cad-31i.2)."""

    def test_anchor_pair_detection(self):
        """Matching INSERT blocks should be found as anchor pairs."""
        from cad_dxf_agent.core.comparison.alignment import _find_anchor_pairs

        m = [
            _make_insert(0, 0, "GRID_BUBBLE", "GRID"),
            _make_insert(100, 0, "GRID_BUBBLE", "GRID"),
            _make_insert(0, 100, "GRID_BUBBLE", "GRID"),
        ]
        r = [
            _make_insert(5, 3, "GRID_BUBBLE", "GRID"),
            _make_insert(105, 3, "GRID_BUBBLE", "GRID"),
            _make_insert(5, 103, "GRID_BUBBLE", "GRID"),
        ]
        cfg = AlignmentConfig(anchor_layer_patterns=["GRID*"])
        pairs = _find_anchor_pairs(m, r, cfg)
        assert len(pairs) == 3

    def test_anchor_pair_no_inserts(self):
        """No INSERT entities → no anchor pairs."""
        from cad_dxf_agent.core.comparison.alignment import _find_anchor_pairs

        m = [_make_snap(0, 0)]
        r = [_make_snap(5, 3)]
        cfg = AlignmentConfig()
        pairs = _find_anchor_pairs(m, r, cfg)
        assert len(pairs) == 0

    def test_anchor_alignment_pure_translation(self):
        """Anchors shifted by uniform offset → recover translation."""
        m = [
            _make_insert(0, 0, "GRID_BUBBLE", "GRID"),
            _make_insert(100, 0, "GRID_BUBBLE", "GRID"),
            _make_insert(0, 100, "GRID_BUBBLE", "GRID"),
        ]
        r = [
            _make_insert(5, 3, "GRID_BUBBLE", "GRID"),
            _make_insert(105, 3, "GRID_BUBBLE", "GRID"),
            _make_insert(5, 103, "GRID_BUBBLE", "GRID"),
        ]
        cfg = AlignmentConfig(enabled=True, confidence_threshold=0.5, max_residual=10.0)
        result = try_anchor_alignment(m, r, cfg)
        assert result is not None
        assert result.method == AlignmentMethod.anchor
        assert result.confidence > 0.5
        # Translation should be approximately (-5, -3) since we align revision→master
        # Actually Kabsch finds R,t such that master = R @ revision + t
        # So t ≈ (-5, -3) when R ≈ I
        assert abs(result.translation[0] - (-5.0)) < 0.1
        assert abs(result.translation[1] - (-3.0)) < 0.1

    def test_anchor_alignment_too_few_anchors(self):
        """Less than 2 anchors → returns None."""
        m = [_make_insert(0, 0, "GRID_BUBBLE", "GRID")]
        r = [_make_insert(5, 3, "GRID_BUBBLE", "GRID")]
        cfg = AlignmentConfig(enabled=True, confidence_threshold=0.5, max_residual=10.0)
        result = try_anchor_alignment(m, r, cfg)
        assert result is None

    def test_anchor_alignment_with_dxf_files(self, tmp_path):
        """Test anchor alignment using real DXF file pair."""
        master, revision = make_anchor_pair(tmp_path, dx=10.0, dy=-5.0)
        m_snaps = extract_snapshots(master)
        r_snaps = extract_snapshots(revision)
        cfg = AlignmentConfig(enabled=True, confidence_threshold=0.3, max_residual=20.0)
        result = try_anchor_alignment(m_snaps, r_snaps, cfg)
        assert result is not None
        assert result.method == AlignmentMethod.anchor
        assert result.confidence > 0.3


# ---------------------------------------------------------------------------
# cad-31i.3: Feature alignment
# ---------------------------------------------------------------------------


class TestFeatureAlignment:
    """Feature-based alignment tests (cad-31i.3)."""

    def test_extract_features_from_lines(self):
        """LINE endpoints should be extracted as features."""
        snaps = [
            GeometrySnapshot(
                handle="1",
                entity_type=EntityType.LINE,
                layer="S",
                points=[Point2D(x=0, y=0), Point2D(x=10, y=0)],
            ),
            GeometrySnapshot(
                handle="2",
                entity_type=EntityType.LINE,
                layer="S",
                points=[Point2D(x=0, y=0), Point2D(x=0, y=10)],
            ),
        ]
        features = _extract_feature_points(snaps)
        assert len(features) == 4  # 2 endpoints per line

    def test_extract_features_from_polyline(self):
        """Polyline vertices should be extracted as features."""
        snaps = [
            GeometrySnapshot(
                handle="1",
                entity_type=EntityType.LWPOLYLINE,
                layer="S",
                points=[
                    Point2D(x=0, y=0),
                    Point2D(x=10, y=0),
                    Point2D(x=10, y=10),
                    Point2D(x=0, y=10),
                ],
            ),
        ]
        features = _extract_feature_points(snaps)
        assert len(features) == 4

    def test_feature_nn_matching(self):
        """Nearby features should match."""
        m = np.array([[0, 0], [10, 0], [5, 5]], dtype=float)
        r = np.array([[0.1, 0.1], [10.1, 0.1], [5.1, 5.1]], dtype=float)
        matches = _match_features_nn(m, r, tolerance=1.0)
        assert len(matches) == 3

    def test_feature_nn_no_match(self):
        """Far-apart features shouldn't match."""
        m = np.array([[0, 0], [10, 0]], dtype=float)
        r = np.array([[100, 100], [200, 200]], dtype=float)
        matches = _match_features_nn(m, r, tolerance=1.0)
        assert len(matches) == 0

    def test_ransac_rigid_pure_translation(self):
        """RANSAC should recover pure translation."""
        master = np.array([[0, 0], [10, 0], [0, 10], [10, 10], [5, 5]], dtype=float)
        offset = np.array([3, 4])
        revision = master - offset
        result = _ransac_rigid(master, revision, tolerance=1.0)
        assert result is not None
        R, t, inliers = result
        np.testing.assert_allclose(R, np.eye(2), atol=0.1)
        np.testing.assert_allclose(t, offset, atol=0.1)

    def test_ransac_with_outliers(self):
        """RANSAC should be robust to outlier matches."""
        master = np.array([[0, 0], [10, 0], [0, 10], [10, 10], [5, 5], [999, 999]], dtype=float)
        offset = np.array([2, 3])
        revision = master.copy() - offset
        # Add outlier: last point is garbage
        revision[-1] = [0, 0]
        result = _ransac_rigid(master, revision, tolerance=1.0)
        assert result is not None
        R, t, inliers = result
        # Most points should be inliers
        assert np.sum(inliers) >= 4

    def test_ransac_too_few_points(self):
        """Less than 2 points → returns None."""
        master = np.array([[0, 0]], dtype=float)
        revision = np.array([[1, 1]], dtype=float)
        result = _ransac_rigid(master, revision, tolerance=1.0)
        assert result is None

    def test_feature_alignment_translated_pair(self):
        """Feature alignment on uniformly translated drawing."""
        dx, dy = 5.0, 3.0
        master = [
            GeometrySnapshot(
                handle="1",
                entity_type=EntityType.LINE,
                layer="S",
                points=[Point2D(x=0, y=0), Point2D(x=100, y=0)],
            ),
            GeometrySnapshot(
                handle="2",
                entity_type=EntityType.LINE,
                layer="S",
                points=[Point2D(x=0, y=0), Point2D(x=0, y=100)],
            ),
            GeometrySnapshot(
                handle="3",
                entity_type=EntityType.LINE,
                layer="S",
                points=[Point2D(x=100, y=0), Point2D(x=100, y=100)],
            ),
        ]
        revision = [
            GeometrySnapshot(
                handle="1",
                entity_type=EntityType.LINE,
                layer="S",
                points=[Point2D(x=0 + dx, y=0 + dy), Point2D(x=100 + dx, y=0 + dy)],
            ),
            GeometrySnapshot(
                handle="2",
                entity_type=EntityType.LINE,
                layer="S",
                points=[Point2D(x=0 + dx, y=0 + dy), Point2D(x=0 + dx, y=100 + dy)],
            ),
            GeometrySnapshot(
                handle="3",
                entity_type=EntityType.LINE,
                layer="S",
                points=[
                    Point2D(x=100 + dx, y=0 + dy),
                    Point2D(x=100 + dx, y=100 + dy),
                ],
            ),
        ]
        cfg = AlignmentConfig(enabled=True, confidence_threshold=0.3, max_residual=10.0)
        result = try_feature_alignment(master, revision, cfg)
        assert result is not None
        assert result.method == AlignmentMethod.feature
        assert result.confidence > 0.3

    def test_feature_alignment_with_dxf_offset_pair(self, tmp_path):
        """Feature alignment using real offset DXF pair."""
        master_path, rev_path = make_offset_pair(tmp_path, dx=8.0, dy=4.0)
        m_snaps = extract_snapshots(master_path)
        r_snaps = extract_snapshots(rev_path)
        cfg = AlignmentConfig(enabled=True, confidence_threshold=0.3, max_residual=20.0)
        result = try_feature_alignment(m_snaps, r_snaps, cfg)
        assert result is not None
        assert result.confidence > 0.3


# ---------------------------------------------------------------------------
# cad-31i.6: Ladder orchestrator
# ---------------------------------------------------------------------------


class TestLadder:
    """Alignment ladder orchestrator tests (cad-31i.6)."""

    def test_identical_drawings_use_identity(self, tmp_path):
        """Identical drawings should be detected as identity alignment."""
        master, revision = make_identical_pair(tmp_path)
        m_snaps = extract_snapshots(master)
        r_snaps = extract_snapshots(revision)
        cfg = AlignmentConfig(enabled=True, confidence_threshold=0.5, max_residual=1.0)
        result = align_drawings(m_snaps, r_snaps, cfg)
        assert result.method == AlignmentMethod.identity
        assert result.confidence > 0.5
        assert result.guidance is None

    def test_offset_pair_aligned(self, tmp_path):
        """Offset pair should be aligned by anchor or feature method."""
        master, revision = make_offset_pair(tmp_path, dx=15.0, dy=12.0)
        m_snaps = extract_snapshots(master)
        r_snaps = extract_snapshots(revision)
        # Tight max_residual so identity check fails (offset > residual)
        cfg = AlignmentConfig(enabled=True, confidence_threshold=0.3, max_residual=5.0)
        result = align_drawings(m_snaps, r_snaps, cfg)
        assert result.confidence > 0.3
        assert result.method in (AlignmentMethod.anchor, AlignmentMethod.feature)
        assert result.guidance is None

    def test_rotated_pair_aligned(self, tmp_path):
        """Rotated pair should be aligned by anchor or feature method."""
        master, revision = make_rotated_pair(tmp_path, angle_deg=10.0)
        m_snaps = extract_snapshots(master)
        r_snaps = extract_snapshots(revision)
        cfg = AlignmentConfig(enabled=True, confidence_threshold=0.3, max_residual=20.0)
        result = align_drawings(m_snaps, r_snaps, cfg)
        assert result.confidence > 0.3
        assert result.guidance is None

    def test_all_methods_fail_gives_guidance(self):
        """When no alignment works, result has guidance text."""
        # Two completely different drawings
        m = [_make_snap(0, 0), _make_snap(1, 1)]
        r = [_make_snap(1000, 1000), _make_snap(2000, 2000)]
        cfg = AlignmentConfig(enabled=True, confidence_threshold=0.99, max_residual=0.01)
        result = align_drawings(m, r, cfg)
        assert result.confidence == 0.0
        assert result.guidance is not None
        assert "control point" in result.guidance.lower()

    def test_ladder_records_attempts(self):
        """Every ladder step should be recorded in diagnostics.attempts."""
        m = [_make_snap(0, 0), _make_snap(10, 10)]
        r = [_make_snap(0, 0), _make_snap(10, 10)]
        cfg = AlignmentConfig(enabled=True, confidence_threshold=0.5, max_residual=5.0)
        result = align_drawings(m, r, cfg)
        assert len(result.diagnostics.attempts) >= 1
        assert result.diagnostics.attempts[0].method == "identity"

    def test_ladder_stops_at_first_success(self, tmp_path):
        """Ladder should stop at the first successful method."""
        master, revision = make_identical_pair(tmp_path)
        m_snaps = extract_snapshots(master)
        r_snaps = extract_snapshots(revision)
        cfg = AlignmentConfig(enabled=True, confidence_threshold=0.5, max_residual=1.0)
        result = align_drawings(m_snaps, r_snaps, cfg)
        # Identity should succeed, so only 1 attempt recorded
        assert len(result.diagnostics.attempts) == 1
        assert result.diagnostics.attempts[0].method == "identity"

    def test_empty_master_fails_gracefully(self):
        """Empty master should fail without error."""
        r = [_make_snap(0, 0)]
        cfg = AlignmentConfig(enabled=True, confidence_threshold=0.5, max_residual=1.0)
        result = align_drawings([], r, cfg)
        assert result.confidence == 0.0
        assert result.guidance is not None

    def test_empty_revision_fails_gracefully(self):
        """Empty revision should fail without error."""
        m = [_make_snap(0, 0)]
        cfg = AlignmentConfig(enabled=True, confidence_threshold=0.5, max_residual=1.0)
        result = align_drawings(m, [], cfg)
        assert result.confidence == 0.0
        assert result.guidance is not None


# ---------------------------------------------------------------------------
# apply_alignment
# ---------------------------------------------------------------------------


class TestApplyAlignment:
    """Tests for applying alignment transform to snapshots."""

    def test_identity_noop(self):
        """Identity alignment should return original snapshots unchanged."""
        snaps = [_make_snap(10, 20)]
        ar = AlignmentResult(method=AlignmentMethod.identity, confidence=1.0)
        result = apply_alignment(snaps, ar)
        assert result[0].points[0].x == 10.0
        assert result[0].points[0].y == 20.0

    def test_translation_applied(self):
        """Translation should shift all points."""
        snaps = [
            GeometrySnapshot(
                handle="1",
                entity_type=EntityType.LINE,
                layer="S",
                points=[Point2D(x=0, y=0), Point2D(x=10, y=0)],
            )
        ]
        ar = AlignmentResult(
            method=AlignmentMethod.translation,
            confidence=0.9,
            translation=(5.0, 3.0),
            rotation_deg=0.0,
        )
        result = apply_alignment(snaps, ar)
        assert abs(result[0].points[0].x - 5.0) < 0.001
        assert abs(result[0].points[0].y - 3.0) < 0.001
        assert abs(result[0].points[1].x - 15.0) < 0.001

    def test_rotation_applied(self):
        """90° rotation should swap coordinates."""
        snaps = [
            GeometrySnapshot(
                handle="1",
                entity_type=EntityType.LINE,
                layer="S",
                points=[Point2D(x=10, y=0)],
            )
        ]
        ar = AlignmentResult(
            method=AlignmentMethod.rigid,
            confidence=0.9,
            translation=(0.0, 0.0),
            rotation_deg=90.0,
        )
        result = apply_alignment(snaps, ar)
        assert abs(result[0].points[0].x - 0.0) < 0.001
        assert abs(result[0].points[0].y - 10.0) < 0.001

    def test_apply_preserves_non_point_fields(self):
        """Alignment should only change points, not other fields."""
        snaps = [
            GeometrySnapshot(
                handle="ABC",
                entity_type=EntityType.TEXT,
                layer="NOTES",
                points=[Point2D(x=5, y=5)],
                text_content="Hello",
                stable_id="TEXT:NOTES:abc123",
            )
        ]
        ar = AlignmentResult(
            method=AlignmentMethod.translation,
            confidence=0.9,
            translation=(1.0, 1.0),
        )
        result = apply_alignment(snaps, ar)
        assert result[0].handle == "ABC"
        assert result[0].text_content == "Hello"
        assert result[0].stable_id == "TEXT:NOTES:abc123"
        assert result[0].entity_type == EntityType.TEXT


# ---------------------------------------------------------------------------
# cad-31i.5: Manual control-point alignment
# ---------------------------------------------------------------------------


class TestManualAlignment:
    """Manual control-point alignment tests (cad-31i.5)."""

    def test_manual_pure_translation(self):
        """Single control point → pure translation, no rotation."""
        m = [_make_snap(0, 0), _make_snap(10, 10)]
        r = [_make_snap(5, 3), _make_snap(15, 13)]
        cfg = AlignmentConfig(
            enabled=True,
            confidence_threshold=0.3,
            max_residual=10.0,
            control_points=[((0.0, 0.0), (5.0, 3.0))],
        )
        result = try_manual_alignment(m, r, cfg)
        assert result.method == AlignmentMethod.manual
        assert abs(result.translation[0] - (-5.0)) < 0.001
        assert abs(result.translation[1] - (-3.0)) < 0.001
        assert abs(result.rotation_deg) < 0.001

    def test_manual_two_points(self):
        """Two control points → rigid transform via Kabsch."""
        cfg = AlignmentConfig(
            enabled=True,
            confidence_threshold=0.3,
            max_residual=10.0,
            control_points=[
                ((0.0, 0.0), (5.0, 3.0)),
                ((100.0, 0.0), (105.0, 3.0)),
            ],
        )
        m = [_make_snap(0, 0), _make_snap(100, 0)]
        r = [_make_snap(5, 3), _make_snap(105, 3)]
        result = try_manual_alignment(m, r, cfg)
        assert result.method == AlignmentMethod.manual
        assert abs(result.translation[0] - (-5.0)) < 0.1
        assert abs(result.translation[1] - (-3.0)) < 0.1

    def test_manual_with_offset_pair(self, tmp_path):
        """Offset DXF pair + correct control points → high confidence."""
        master_path, rev_path = make_offset_pair(tmp_path, dx=5.0, dy=3.0)
        m_snaps = extract_snapshots(master_path)
        r_snaps = extract_snapshots(rev_path)
        cfg = AlignmentConfig(
            enabled=True,
            confidence_threshold=0.3,
            max_residual=20.0,
            control_points=[
                ((0.0, 0.0), (5.0, 3.0)),
                ((100.0, 0.0), (105.0, 3.0)),
            ],
        )
        result = try_manual_alignment(m_snaps, r_snaps, cfg)
        assert result.method == AlignmentMethod.manual
        assert result.confidence > 0.3

    def test_manual_bypasses_ladder(self):
        """Control points set → ladder skipped, manual method returned."""
        m = [_make_snap(0, 0), _make_snap(10, 10)]
        r = [_make_snap(0, 0), _make_snap(10, 10)]  # identical = identity would win
        cfg = AlignmentConfig(
            enabled=True,
            confidence_threshold=0.3,
            max_residual=10.0,
            control_points=[((0.0, 0.0), (1.0, 1.0))],  # bogus offset
        )
        result = align_drawings(m, r, cfg)
        assert result.method == AlignmentMethod.manual
        # Only one attempt recorded (manual), not identity/anchor/feature
        assert len(result.diagnostics.attempts) == 1
        assert result.diagnostics.attempts[0].method == "manual"

    def test_manual_bad_points_still_returns(self):
        """Wrong control points → result still returned, low confidence."""
        m = [_make_snap(0, 0), _make_snap(10, 10)]
        r = [_make_snap(500, 500), _make_snap(600, 600)]
        cfg = AlignmentConfig(
            enabled=True,
            confidence_threshold=0.3,
            max_residual=1.0,
            control_points=[((0.0, 0.0), (999.0, 999.0))],  # wrong
        )
        result = try_manual_alignment(m, r, cfg)
        assert result.method == AlignmentMethod.manual
        # Result is returned (not None) but overlap should be zero
        assert result.diagnostics.overlap_ratio == 0.0

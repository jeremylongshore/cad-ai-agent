"""Tests for comparison/scorer.py — candidate search and confidence scoring."""

from __future__ import annotations

from cad_dxf_agent.core.comparison.scorer import (
    find_candidates,
    score_geometry,
    score_insert,
    score_match,
    score_text,
)
from cad_dxf_agent.models.cad_schema import EntityType, Point2D
from cad_dxf_agent.models.comparison_schema import GeometrySnapshot


def _snap(
    handle: str = "A",
    entity_type: EntityType = EntityType.LINE,
    layer: str = "S",
    points: list[Point2D] | None = None,
    text_content: str | None = None,
    block_name: str | None = None,
    attributes: dict | None = None,
) -> GeometrySnapshot:
    """Shorthand snapshot builder for tests."""
    return GeometrySnapshot(
        handle=handle,
        entity_type=entity_type,
        layer=layer,
        points=points or [Point2D(x=0, y=0)],
        text_content=text_content,
        block_name=block_name,
        attributes=attributes or {},
    )


class TestFindCandidates:
    """Tests for find_candidates()."""

    def test_filters_by_type_and_layer(self):
        master = _snap(entity_type=EntityType.LINE, layer="S")
        pool = [
            _snap(handle="R1", entity_type=EntityType.LINE, layer="S"),
            _snap(handle="R2", entity_type=EntityType.TEXT, layer="S", text_content="x"),
            _snap(handle="R3", entity_type=EntityType.LINE, layer="NOTES"),
        ]
        result = find_candidates(master, pool, tolerance=10.0)
        assert len(result) == 1
        assert result[0][0].handle == "R1"

    def test_filters_by_distance(self):
        master = _snap(points=[Point2D(x=0, y=0)])
        pool = [
            _snap(handle="R1", points=[Point2D(x=1, y=0)]),  # dist=1
            _snap(handle="R2", points=[Point2D(x=5, y=0)]),  # dist=5
            _snap(handle="R3", points=[Point2D(x=100, y=0)]),  # dist=100
        ]
        result = find_candidates(master, pool, tolerance=6.0)
        assert len(result) == 2
        assert result[0][0].handle == "R1"
        assert result[1][0].handle == "R2"

    def test_sorted_by_distance(self):
        master = _snap(points=[Point2D(x=0, y=0)])
        pool = [
            _snap(handle="R1", points=[Point2D(x=5, y=0)]),
            _snap(handle="R2", points=[Point2D(x=1, y=0)]),
            _snap(handle="R3", points=[Point2D(x=3, y=0)]),
        ]
        result = find_candidates(master, pool, tolerance=10.0)
        dists = [d for _, d in result]
        assert dists == sorted(dists)

    def test_empty_pool(self):
        master = _snap()
        assert find_candidates(master, [], tolerance=10.0) == []

    def test_no_matches_within_tolerance(self):
        master = _snap(points=[Point2D(x=0, y=0)])
        pool = [_snap(handle="R1", points=[Point2D(x=100, y=100)])]
        assert find_candidates(master, pool, tolerance=1.0) == []

    def test_returns_distance(self):
        master = _snap(points=[Point2D(x=0, y=0)])
        pool = [_snap(handle="R1", points=[Point2D(x=3, y=4)])]
        result = find_candidates(master, pool, tolerance=10.0)
        assert len(result) == 1
        assert abs(result[0][1] - 5.0) < 0.001  # 3-4-5 triangle


class TestScoreInsert:
    """Tests for score_insert()."""

    def test_identical_inserts_perfect_score(self):
        m = _snap(
            entity_type=EntityType.INSERT,
            block_name="COL_A",
            attributes={"tag1": "v1"},
        )
        r = _snap(
            entity_type=EntityType.INSERT,
            block_name="COL_A",
            attributes={"tag1": "v1"},
        )
        score = score_insert(m, r, tolerance=1.0)
        assert score == 1.0

    def test_different_block_name_loses_weight(self):
        m = _snap(entity_type=EntityType.INSERT, block_name="COL_A")
        r = _snap(entity_type=EntityType.INSERT, block_name="COL_B")
        score = score_insert(m, r, tolerance=1.0)
        assert score < 1.0
        # Should be missing the 0.5 block_name weight
        assert score <= 0.5 + 0.01

    def test_position_proximity_affects_score(self):
        m = _snap(entity_type=EntityType.INSERT, block_name="COL_A", points=[Point2D(x=0, y=0)])
        r_close = _snap(
            entity_type=EntityType.INSERT,
            block_name="COL_A",
            points=[Point2D(x=0.1, y=0)],
        )
        r_far = _snap(
            entity_type=EntityType.INSERT,
            block_name="COL_A",
            points=[Point2D(x=5, y=0)],
        )
        close_score = score_insert(m, r_close, tolerance=10.0)
        far_score = score_insert(m, r_far, tolerance=10.0)
        assert close_score > far_score

    def test_attribute_overlap_jaccard(self):
        m = _snap(
            entity_type=EntityType.INSERT,
            block_name="X",
            attributes={"a": 1, "b": 2, "c": 3},
        )
        r = _snap(
            entity_type=EntityType.INSERT,
            block_name="X",
            attributes={"a": 1, "b": 2, "d": 4},
        )
        score = score_insert(m, r, tolerance=1.0)
        # Jaccard of {a,b,c} vs {a,b,d} = 2/4 = 0.5
        # block_name(0.5) + attrib(0.2 * 0.5=0.1) + pos(0.3 * 1.0=0.3) = 0.9
        assert 0.85 < score < 0.95

    def test_both_no_attributes_full_attrib_score(self):
        m = _snap(entity_type=EntityType.INSERT, block_name="X")
        r = _snap(entity_type=EntityType.INSERT, block_name="X")
        score = score_insert(m, r, tolerance=1.0)
        assert score == 1.0


class TestScoreGeometry:
    """Tests for score_geometry()."""

    def test_identical_lines_perfect_score(self):
        pts = [Point2D(x=0, y=0), Point2D(x=10, y=0)]
        m = _snap(entity_type=EntityType.LINE, points=pts)
        r = _snap(entity_type=EntityType.LINE, points=pts)
        score = score_geometry(m, r)
        assert score == 1.0

    def test_different_length_reduces_score(self):
        m = _snap(entity_type=EntityType.LINE, points=[Point2D(x=0, y=0), Point2D(x=10, y=0)])
        r = _snap(entity_type=EntityType.LINE, points=[Point2D(x=0, y=0), Point2D(x=20, y=0)])
        score = score_geometry(m, r)
        assert score < 1.0

    def test_different_angle_reduces_score(self):
        m = _snap(entity_type=EntityType.LINE, points=[Point2D(x=0, y=0), Point2D(x=10, y=0)])
        r = _snap(entity_type=EntityType.LINE, points=[Point2D(x=0, y=0), Point2D(x=0, y=10)])
        score = score_geometry(m, r)
        # Same length but different angle
        assert score < 1.0

    def test_polyline_vertex_count_matters(self):
        m = _snap(
            entity_type=EntityType.LWPOLYLINE,
            points=[Point2D(x=0, y=0), Point2D(x=10, y=0), Point2D(x=10, y=10)],
        )
        r_same = _snap(
            entity_type=EntityType.LWPOLYLINE,
            points=[Point2D(x=0, y=0), Point2D(x=10, y=0), Point2D(x=10, y=10)],
        )
        r_diff = _snap(
            entity_type=EntityType.LWPOLYLINE,
            points=[
                Point2D(x=0, y=0),
                Point2D(x=5, y=0),
                Point2D(x=10, y=0),
                Point2D(x=10, y=10),
            ],
        )
        same_score = score_geometry(m, r_same)
        diff_score = score_geometry(m, r_diff)
        assert same_score > diff_score


class TestScoreText:
    """Tests for score_text()."""

    def test_identical_text_perfect_score(self):
        m = _snap(entity_type=EntityType.TEXT, text_content="Hello", points=[Point2D(x=5, y=5)])
        r = _snap(entity_type=EntityType.TEXT, text_content="Hello", points=[Point2D(x=5, y=5)])
        score = score_text(m, r, tolerance=1.0)
        assert score == 1.0

    def test_different_text_reduces_score(self):
        m = _snap(entity_type=EntityType.TEXT, text_content="REV A", points=[Point2D(x=5, y=5)])
        r = _snap(entity_type=EntityType.TEXT, text_content="REV B", points=[Point2D(x=5, y=5)])
        score = score_text(m, r, tolerance=1.0)
        assert 0.5 < score < 1.0  # Similar text + same position

    def test_completely_different_text_low_score(self):
        m = _snap(entity_type=EntityType.TEXT, text_content="ABCDEF", points=[Point2D(x=5, y=5)])
        r = _snap(entity_type=EntityType.TEXT, text_content="XYZ", points=[Point2D(x=5, y=5)])
        score = score_text(m, r, tolerance=1.0)
        assert score < 0.8

    def test_position_affects_text_score(self):
        m = _snap(entity_type=EntityType.TEXT, text_content="Hello", points=[Point2D(x=0, y=0)])
        r_close = _snap(
            entity_type=EntityType.TEXT, text_content="Hello", points=[Point2D(x=0.1, y=0)]
        )
        r_far = _snap(
            entity_type=EntityType.TEXT, text_content="Hello", points=[Point2D(x=5, y=0)]
        )
        close_score = score_text(m, r_close, tolerance=10.0)
        far_score = score_text(m, r_far, tolerance=10.0)
        assert close_score > far_score

    def test_empty_text_match(self):
        m = _snap(entity_type=EntityType.TEXT, text_content=None)
        r = _snap(entity_type=EntityType.TEXT, text_content=None)
        score = score_text(m, r, tolerance=1.0)
        # Both None → both coerced to "" → identical → similarity=1.0, position=1.0
        assert score == 1.0


class TestScoreMatch:
    """Tests for the top-level score_match dispatch."""

    def test_routes_insert(self):
        m = _snap(entity_type=EntityType.INSERT, block_name="X")
        r = _snap(entity_type=EntityType.INSERT, block_name="X")
        score = score_match(m, r, tolerance=1.0)
        assert score == 1.0

    def test_routes_text(self):
        m = _snap(entity_type=EntityType.TEXT, text_content="Hi")
        r = _snap(entity_type=EntityType.TEXT, text_content="Hi")
        score = score_match(m, r, tolerance=1.0)
        assert score == 1.0

    def test_routes_line(self):
        pts = [Point2D(x=0, y=0), Point2D(x=10, y=0)]
        m = _snap(entity_type=EntityType.LINE, points=pts)
        r = _snap(entity_type=EntityType.LINE, points=pts)
        score = score_match(m, r, tolerance=1.0)
        assert score == 1.0

    def test_routes_mtext(self):
        m = _snap(entity_type=EntityType.MTEXT, text_content="Note")
        r = _snap(entity_type=EntityType.MTEXT, text_content="Note")
        score = score_match(m, r, tolerance=1.0)
        assert score == 1.0

    def test_fallback_uses_proximity(self):
        """Entity types without specific scoring fall back to proximity."""
        m = _snap(entity_type=EntityType.CIRCLE, points=[Point2D(x=0, y=0)])
        r = _snap(entity_type=EntityType.CIRCLE, points=[Point2D(x=0, y=0)])
        score = score_match(m, r, tolerance=1.0)
        assert score == 1.0

    def test_all_scores_in_range(self):
        """Every score function returns values in [0, 1]."""
        pts = [Point2D(x=0, y=0), Point2D(x=10, y=0)]
        cases = [
            (
                _snap(entity_type=EntityType.LINE, points=pts),
                _snap(entity_type=EntityType.LINE, points=pts),
            ),
            (
                _snap(entity_type=EntityType.INSERT, block_name="A"),
                _snap(entity_type=EntityType.INSERT, block_name="B"),
            ),
            (
                _snap(entity_type=EntityType.TEXT, text_content="X"),
                _snap(entity_type=EntityType.TEXT, text_content="Y"),
            ),
        ]
        for m, r in cases:
            score = score_match(m, r, tolerance=10.0)
            assert 0.0 <= score <= 1.0, f"Score {score} out of range for {m.entity_type}"

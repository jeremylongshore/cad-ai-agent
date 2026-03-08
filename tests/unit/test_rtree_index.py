"""Tests for the R-tree spatial index upgrade and ENTITY_CAP raise.

Covers:
- nearest() — unfiltered (R-tree path) and filtered (linear-scan path)
- find_in_radius() — R-tree bbox + exact circular distance check
- Consistency between R-tree and brute-force linear scan
- ENTITY_CAP is now 5000 (was 500)
- build_planner_context truncation behaviour at the new threshold
- Performance smoke tests on large drawings (5000 entities)
"""

from __future__ import annotations

import math
from pathlib import Path

import pytest

from cad_dxf_agent.core.dxf_reader import load_dxf
from cad_dxf_agent.core.entity_index import EntityIndex
from cad_dxf_agent.core.semantic_model import ENTITY_CAP, build_planner_context
from cad_dxf_agent.models.cad_schema import DrawingContext, EntityRef, EntityType, Point2D
from tests.helpers.dxf_factory import (
    create_dense_drawing,
    create_overlapping_drawing,
    create_structural_drawing,
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _dist(a: EntityRef, qx: float, qy: float) -> float:
    """Euclidean distance from entity insert_point to query point."""
    assert a.insert_point is not None
    return math.hypot(a.insert_point.x - qx, a.insert_point.y - qy)


def _brute_force_nearest(
    context: DrawingContext,
    x: float,
    y: float,
    entity_type: str | None = None,
    layer: str | None = None,
) -> EntityRef | None:
    """O(n) reference implementation for nearest()."""
    candidates = [e for e in context.entities if e.insert_point is not None]
    if entity_type is not None:
        try:
            etype = EntityType(entity_type)
        except ValueError:
            return None
        candidates = [e for e in candidates if e.entity_type == etype]
    if layer is not None:
        candidates = [e for e in candidates if e.layer.upper() == layer.upper()]

    if not candidates:
        return None
    return min(candidates, key=lambda e: math.hypot(e.insert_point.x - x, e.insert_point.y - y))  # type: ignore[union-attr]


def _brute_force_in_radius(
    context: DrawingContext,
    x: float,
    y: float,
    radius: float,
    entity_type: str | None = None,
    layer: str | None = None,
) -> list[EntityRef]:
    """O(n) reference implementation for find_in_radius()."""
    candidates = [e for e in context.entities if e.insert_point is not None]
    if entity_type is not None:
        try:
            etype = EntityType(entity_type)
        except ValueError:
            return []
        candidates = [e for e in candidates if e.entity_type == etype]
    if layer is not None:
        candidates = [e for e in candidates if e.layer.upper() == layer.upper()]

    r_sq = radius * radius
    hits = [
        e
        for e in candidates
        if (e.insert_point.x - x) ** 2 + (e.insert_point.y - y) ** 2 <= r_sq  # type: ignore[union-attr]
    ]
    hits.sort(key=lambda e: math.hypot(e.insert_point.x - x, e.insert_point.y - y))  # type: ignore[union-attr]
    return hits


def _make_entity(
    handle: str,
    x: float,
    y: float,
    layer: str = "TEST",
    entity_type: EntityType = EntityType.LINE,
    text: str | None = None,
) -> EntityRef:
    """Minimal EntityRef factory for unit-level tests."""
    return EntityRef(
        handle=handle,
        entity_type=entity_type,
        layer=layer,
        insert_point=Point2D(x=x, y=y),
        text_content=text,
    )


def _make_context(entities: list[EntityRef], file_path: str = "test.dxf") -> DrawingContext:
    return DrawingContext(file_path=file_path, entities=entities)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def known_context() -> DrawingContext:
    """Small drawing with entities at predictable positions.

    Layout (x, y):
      A  (0, 0)   LINE   LAYER_A
      B  (3, 4)   TEXT   LAYER_B    — dist from origin = 5.0
      C  (10, 0)  LINE   LAYER_A    — dist from origin = 10.0
      D  (10, 10) TEXT   LAYER_B    — dist from origin ≈ 14.14
      E  (0, 5)   INSERT LAYER_A    — dist from origin = 5.0
    """
    return _make_context(
        [
            _make_entity("A", 0.0, 0.0, layer="LAYER_A", entity_type=EntityType.LINE),
            _make_entity("B", 3.0, 4.0, layer="LAYER_B", entity_type=EntityType.TEXT, text="hello"),
            _make_entity("C", 10.0, 0.0, layer="LAYER_A", entity_type=EntityType.LINE),
            _make_entity(
                "D", 10.0, 10.0, layer="LAYER_B", entity_type=EntityType.TEXT, text="world"
            ),
            _make_entity("E", 0.0, 5.0, layer="LAYER_A", entity_type=EntityType.INSERT),
        ]
    )


@pytest.fixture
def known_index(known_context: DrawingContext) -> EntityIndex:
    return EntityIndex(known_context)


@pytest.fixture
def empty_context() -> DrawingContext:
    return _make_context([])


@pytest.fixture
def empty_index(empty_context: DrawingContext) -> EntityIndex:
    return EntityIndex(empty_context)


@pytest.fixture
def structural_context(tmp_path: Path) -> DrawingContext:
    """200+ entity structural drawing loaded into a DrawingContext."""
    dxf_path = create_structural_drawing(tmp_path)
    return load_dxf(dxf_path)


@pytest.fixture
def dense_context_1000(tmp_path: Path) -> DrawingContext:
    """1000-entity dense drawing loaded into a DrawingContext."""
    dxf_path = create_dense_drawing(tmp_path, count=1000)
    return load_dxf(dxf_path)


@pytest.fixture
def overlapping_context(tmp_path: Path) -> DrawingContext:
    """Drawing with multiple entities sharing identical coordinates."""
    dxf_path = create_overlapping_drawing(tmp_path)
    return load_dxf(dxf_path)


# ---------------------------------------------------------------------------
# 1. nearest() — R-tree unfiltered path
# ---------------------------------------------------------------------------


class TestNearestUnfiltered:
    """nearest() with no filters uses the R-tree fast path."""

    def test_returns_closest_entity(self, known_index: EntityIndex) -> None:
        """Query point at origin returns entity A (handle 'A') at (0,0)."""
        result = known_index.nearest(0.0, 0.0)
        assert result is not None
        assert result.handle == "A"

    def test_off_grid_query_returns_nearest(self, known_index: EntityIndex) -> None:
        """Query close to (3,4) returns entity B."""
        result = known_index.nearest(3.1, 4.1)
        assert result is not None
        assert result.handle == "B"

    def test_equidistant_returns_one_result(self, known_index: EntityIndex) -> None:
        """Query equidistant from two entities returns exactly one EntityRef."""
        # B is at (3,4) dist=5; E is at (0,5) dist=5 — both distance 5 from origin
        # R-tree breaks ties deterministically; we just assert we get one valid result
        result = known_index.nearest(0.0, 0.0)
        assert result is not None
        assert result.insert_point is not None

    def test_empty_context_returns_none(self, empty_index: EntityIndex) -> None:
        """nearest() on empty drawing returns None."""
        assert empty_index.nearest(0.0, 0.0) is None

    def test_overlapping_entities_returns_one(self, overlapping_context: DrawingContext) -> None:
        """When multiple entities share the same coordinates, one is returned."""
        index = EntityIndex(overlapping_context)
        result = index.nearest(10.0, 10.0)
        assert result is not None
        # Result must be one of the entities actually at (10, 10)
        assert result.insert_point is not None
        dist = math.hypot(result.insert_point.x - 10.0, result.insert_point.y - 10.0)
        assert dist < 1e-6

    def test_no_insert_point_entities_not_returned(self) -> None:
        """Entities without insert_point are not indexed and cannot be nearest."""
        e_no_pos = EntityRef(
            handle="NP",
            entity_type=EntityType.LINE,
            layer="L",
            insert_point=None,
        )
        e_with_pos = _make_entity("WP", 5.0, 5.0)
        ctx = _make_context([e_no_pos, e_with_pos])
        index = EntityIndex(ctx)
        result = index.nearest(0.0, 0.0)
        assert result is not None
        assert result.handle == "WP"

    def test_single_entity_always_nearest(self) -> None:
        """Drawing with one entity — nearest always returns it regardless of distance."""
        ctx = _make_context([_make_entity("SOLO", 1000.0, 1000.0)])
        index = EntityIndex(ctx)
        result = index.nearest(0.0, 0.0)
        assert result is not None
        assert result.handle == "SOLO"

    def test_nearest_on_structural_drawing(self, structural_context: DrawingContext) -> None:
        """nearest() on 200+ entity drawing returns a valid result."""
        index = EntityIndex(structural_context)
        result = index.nearest(0.0, 0.0)
        assert result is not None
        assert result.insert_point is not None


# ---------------------------------------------------------------------------
# 2. nearest() — filtered (linear-scan) path
# ---------------------------------------------------------------------------


class TestNearestFiltered:
    """nearest() with layer or type filter falls back to filtered linear scan."""

    def test_layer_filter_returns_only_that_layer(self, known_index: EntityIndex) -> None:
        """nearest() with layer='LAYER_B' returns an entity on LAYER_B."""
        result = known_index.nearest(0.0, 0.0, layer="LAYER_B")
        assert result is not None
        assert result.layer.upper() == "LAYER_B"

    def test_layer_filter_closest_on_layer(self, known_index: EntityIndex) -> None:
        """nearest() picks the closest LAYER_B entity to (0,0).

        B is at (3,4) dist=5; D is at (10,10) dist≈14.14 — B must win.
        """
        result = known_index.nearest(0.0, 0.0, layer="LAYER_B")
        assert result is not None
        assert result.handle == "B"

    def test_type_filter_returns_only_that_type(self, known_index: EntityIndex) -> None:
        """nearest() with entity_type='TEXT' returns a TEXT entity."""
        result = known_index.nearest(0.0, 0.0, entity_type="TEXT")
        assert result is not None
        assert result.entity_type == EntityType.TEXT

    def test_type_filter_closest_text(self, known_index: EntityIndex) -> None:
        """nearest() TEXT to origin picks B at (3,4) over D at (10,10)."""
        result = known_index.nearest(0.0, 0.0, entity_type="TEXT")
        assert result is not None
        assert result.handle == "B"

    def test_combined_layer_and_type_filter(self, known_index: EntityIndex) -> None:
        """nearest() with both layer and type filters applies intersection."""
        # Only LINE on LAYER_A: A at (0,0) and C at (10,0)
        result = known_index.nearest(9.0, 0.0, layer="LAYER_A", entity_type="LINE")
        assert result is not None
        assert result.handle == "C"
        assert result.entity_type == EntityType.LINE
        assert result.layer == "LAYER_A"

    def test_layer_with_no_match_returns_none(self, known_index: EntityIndex) -> None:
        """nearest() with layer that has no entities returns None."""
        result = known_index.nearest(0.0, 0.0, layer="NONEXISTENT")
        assert result is None

    def test_type_with_no_match_returns_none(self, known_index: EntityIndex) -> None:
        """nearest() with type that has no entities returns None."""
        result = known_index.nearest(0.0, 0.0, entity_type="MTEXT")
        assert result is None

    def test_invalid_type_filter_returns_none(self, known_index: EntityIndex) -> None:
        """nearest() with invalid entity_type string returns None."""
        result = known_index.nearest(0.0, 0.0, entity_type="VIEWPORT")
        assert result is None

    def test_layer_filter_case_insensitive(self, known_index: EntityIndex) -> None:
        """Layer filter is case-insensitive."""
        upper = known_index.nearest(0.0, 0.0, layer="LAYER_B")
        lower = known_index.nearest(0.0, 0.0, layer="layer_b")
        assert upper is not None
        assert lower is not None
        assert upper.handle == lower.handle

    def test_filtered_nearest_on_structural_drawing(
        self, structural_context: DrawingContext
    ) -> None:
        """Filtered nearest() works on 200+ entity drawing."""
        index = EntityIndex(structural_context)
        result = index.nearest(0.0, 0.0, layer="NOTES")
        assert result is not None
        assert result.layer.upper() == "NOTES"


# ---------------------------------------------------------------------------
# 3. find_in_radius() tests
# ---------------------------------------------------------------------------


class TestFindInRadius:
    """find_in_radius() uses R-tree bbox + exact circular distance filter."""

    def test_returns_entities_within_radius(self, known_index: EntityIndex) -> None:
        """Entities within radius=6 of origin: A(0,0), B(3,4), E(0,5)."""
        results = known_index.find_in_radius(0.0, 0.0, radius=6.0)
        handles = {e.handle for e in results}
        assert "A" in handles  # dist=0
        assert "B" in handles  # dist=5
        assert "E" in handles  # dist=5
        assert "C" not in handles  # dist=10 > 6
        assert "D" not in handles  # dist≈14.14 > 6

    def test_excludes_entities_outside_radius(self, known_index: EntityIndex) -> None:
        """Tight radius=1 from origin only catches A at (0,0)."""
        results = known_index.find_in_radius(0.0, 0.0, radius=1.0)
        assert len(results) == 1
        assert results[0].handle == "A"

    def test_circular_not_square(self, known_index: EntityIndex) -> None:
        """Radius check is circular, not the R-tree bounding square.

        Query: center=(0,0), radius=4.9
        B is at (3,4): dist=5.0 > 4.9 — must NOT be included.
        C is at (10,0): dist=10 > 4.9 — must NOT be included.
        """
        results = known_index.find_in_radius(0.0, 0.0, radius=4.9)
        handles = {e.handle for e in results}
        assert "B" not in handles  # dist=5.0 exceeds radius 4.9
        assert "A" in handles  # dist=0 always inside

    def test_results_sorted_by_distance(self, known_index: EntityIndex) -> None:
        """Results are sorted nearest-first by exact Euclidean distance."""
        results = known_index.find_in_radius(0.0, 0.0, radius=15.0)
        assert len(results) >= 2
        dists = [_dist(e, 0.0, 0.0) for e in results]
        assert dists == sorted(dists)

    def test_empty_result_when_no_entities_in_radius(self, known_index: EntityIndex) -> None:
        """Query point far from all entities returns empty list."""
        results = known_index.find_in_radius(9999.0, 9999.0, radius=1.0)
        assert results == []

    def test_large_radius_returns_all_positioned_entities(
        self, known_index: EntityIndex, known_context: DrawingContext
    ) -> None:
        """Radius large enough to encompass the drawing returns all entities with positions."""
        positioned_count = sum(1 for e in known_context.entities if e.insert_point is not None)
        results = known_index.find_in_radius(0.0, 0.0, radius=100.0)
        assert len(results) == positioned_count

    def test_radius_zero_returns_only_exact_match(self, known_index: EntityIndex) -> None:
        """Radius=0 only returns entities at exact coordinates."""
        results = known_index.find_in_radius(0.0, 0.0, radius=0.0)
        assert all(
            e.insert_point is not None and e.insert_point.x == 0.0 and e.insert_point.y == 0.0
            for e in results
        )

    def test_empty_context_returns_empty_list(self, empty_index: EntityIndex) -> None:
        """find_in_radius() on empty drawing returns empty list."""
        assert empty_index.find_in_radius(0.0, 0.0, radius=100.0) == []

    def test_layer_filter(self, known_index: EntityIndex) -> None:
        """Layer filter restricts results to specified layer."""
        results = known_index.find_in_radius(0.0, 0.0, radius=15.0, layer="LAYER_B")
        assert all(e.layer.upper() == "LAYER_B" for e in results)
        handles = {e.handle for e in results}
        assert "B" in handles
        assert "D" in handles
        assert "A" not in handles  # LAYER_A

    def test_type_filter(self, known_index: EntityIndex) -> None:
        """Type filter restricts results to specified entity type."""
        results = known_index.find_in_radius(0.0, 0.0, radius=15.0, entity_type="LINE")
        assert all(e.entity_type == EntityType.LINE for e in results)
        handles = {e.handle for e in results}
        assert "A" in handles
        assert "C" in handles
        assert "B" not in handles  # TEXT

    def test_combined_layer_and_type_filter(self, known_index: EntityIndex) -> None:
        """Combined layer+type filter returns intersection."""
        # LAYER_A + INSERT: only E at (0,5)
        results = known_index.find_in_radius(
            0.0, 0.0, radius=15.0, layer="LAYER_A", entity_type="INSERT"
        )
        assert len(results) == 1
        assert results[0].handle == "E"

    def test_invalid_entity_type_returns_empty(self, known_index: EntityIndex) -> None:
        """Invalid entity_type string returns empty list."""
        results = known_index.find_in_radius(0.0, 0.0, radius=100.0, entity_type="VIEWPORT")
        assert results == []

    def test_layer_filter_case_insensitive(self, known_index: EntityIndex) -> None:
        """Layer filter in find_in_radius is case-insensitive."""
        upper = known_index.find_in_radius(0.0, 0.0, radius=15.0, layer="LAYER_B")
        lower = known_index.find_in_radius(0.0, 0.0, radius=15.0, layer="layer_b")
        assert {e.handle for e in upper} == {e.handle for e in lower}

    def test_overlapping_drawing_all_at_same_point_returned(
        self, overlapping_context: DrawingContext
    ) -> None:
        """Entities sharing identical coordinates are all returned within a small radius."""
        index = EntityIndex(overlapping_context)
        # Multiple entities at (10, 10) — tight radius should catch all of them
        results = index.find_in_radius(10.0, 10.0, radius=0.5)
        assert len(results) >= 2


# ---------------------------------------------------------------------------
# 4. Consistency tests — R-tree vs brute-force linear scan
# ---------------------------------------------------------------------------


class TestRtreeConsistency:
    """R-tree results must match the brute-force reference implementation."""

    @pytest.mark.parametrize(
        "qx, qy",
        [
            (0.0, 0.0),
            (5.0, 2.5),
            (3.0, 4.0),
            (10.0, 0.0),
            (10.0, 10.0),
            (50.0, 50.0),  # far from all entities
        ],
    )
    def test_nearest_matches_brute_force(
        self, known_index: EntityIndex, known_context: DrawingContext, qx: float, qy: float
    ) -> None:
        """nearest() result matches O(n) brute-force for multiple query points."""
        rtree_result = known_index.nearest(qx, qy)
        bf_result = _brute_force_nearest(known_context, qx, qy)

        if bf_result is None:
            assert rtree_result is None
        else:
            assert rtree_result is not None
            # Both must be equidistant from the query point (handles ties)
            rtree_dist = _dist(rtree_result, qx, qy)
            bf_dist = _dist(bf_result, qx, qy)
            assert abs(rtree_dist - bf_dist) < 1e-9

    @pytest.mark.parametrize(
        "qx, qy, radius",
        [
            (0.0, 0.0, 6.0),
            (0.0, 0.0, 4.9),
            (5.0, 2.5, 3.0),
            (0.0, 0.0, 100.0),
            (0.0, 0.0, 0.0),
            (9999.0, 9999.0, 1.0),
        ],
    )
    def test_find_in_radius_matches_brute_force(
        self,
        known_index: EntityIndex,
        known_context: DrawingContext,
        qx: float,
        qy: float,
        radius: float,
    ) -> None:
        """find_in_radius() result set matches O(n) brute-force."""
        rtree_results = known_index.find_in_radius(qx, qy, radius)
        bf_results = _brute_force_in_radius(known_context, qx, qy, radius)

        assert {e.handle for e in rtree_results} == {e.handle for e in bf_results}

    def test_nearest_consistency_on_dense_drawing(self, dense_context_1000: DrawingContext) -> None:
        """R-tree nearest() matches brute-force across multiple queries on 1000-entity drawing."""
        index = EntityIndex(dense_context_1000)
        query_points = [(0.0, 0.0), (25.0, 25.0), (100.0, 50.0), (500.0, 500.0)]

        for qx, qy in query_points:
            rtree_result = index.nearest(qx, qy)
            bf_result = _brute_force_nearest(dense_context_1000, qx, qy)

            assert rtree_result is not None, f"R-tree returned None at ({qx},{qy})"
            assert bf_result is not None, f"Brute-force returned None at ({qx},{qy})"
            rtree_dist = _dist(rtree_result, qx, qy)
            bf_dist = _dist(bf_result, qx, qy)
            assert abs(rtree_dist - bf_dist) < 1e-9, (
                f"Distance mismatch at ({qx},{qy}): rtree={rtree_dist} bf={bf_dist}"
            )

    def test_radius_consistency_on_dense_drawing(self, dense_context_1000: DrawingContext) -> None:
        """R-tree find_in_radius() result sets match brute-force on 1000-entity drawing."""
        index = EntityIndex(dense_context_1000)
        # Grid spacing is 5.0, so radius=6 will catch entities in immediate neighbourhood
        test_cases = [
            (0.0, 0.0, 6.0),
            (25.0, 25.0, 8.0),
            (0.0, 0.0, 1000.0),  # catch everything
        ]

        for qx, qy, radius in test_cases:
            rtree_handles = {e.handle for e in index.find_in_radius(qx, qy, radius)}
            bf_handles = {
                e.handle for e in _brute_force_in_radius(dense_context_1000, qx, qy, radius)
            }
            assert rtree_handles == bf_handles, (
                f"Handle mismatch at ({qx},{qy}) r={radius}: "
                f"rtree={len(rtree_handles)} bf={len(bf_handles)}"
            )

    def test_filtered_nearest_matches_brute_force_on_structural(
        self, structural_context: DrawingContext
    ) -> None:
        """Filtered nearest() on 200+ entity drawing matches brute-force."""
        index = EntityIndex(structural_context)
        # Layer filter
        qx, qy = 15.0, 15.0
        rtree_result = index.nearest(qx, qy, layer="NOTES")
        bf_result = _brute_force_nearest(structural_context, qx, qy, layer="NOTES")
        if bf_result is None:
            assert rtree_result is None
        else:
            assert rtree_result is not None
            assert abs(_dist(rtree_result, qx, qy) - _dist(bf_result, qx, qy)) < 1e-9


# ---------------------------------------------------------------------------
# 5. ENTITY_CAP tests
# ---------------------------------------------------------------------------


class TestEntityCap:
    """ENTITY_CAP was raised from 500 to 5000."""

    def test_entity_cap_value(self) -> None:
        """ENTITY_CAP is exactly 5000."""
        assert ENTITY_CAP == 5000

    def test_no_truncation_below_cap(self, dense_context_1000: DrawingContext) -> None:
        """build_planner_context does not truncate when entity count < 5000."""
        ctx = build_planner_context(dense_context_1000)
        assert "entities_truncated" not in ctx
        # entity list length must equal the actual entity count
        assert len(ctx["entities"]) == dense_context_1000.entity_count

    def test_no_truncation_at_exactly_cap(self) -> None:
        """build_planner_context does not truncate when entity count == ENTITY_CAP."""
        entities = [_make_entity(str(i), float(i), 0.0) for i in range(ENTITY_CAP)]
        ctx = _make_context(entities)
        result = build_planner_context(ctx)
        assert "entities_truncated" not in result
        assert len(result["entities"]) == ENTITY_CAP

    def test_truncation_above_cap(self) -> None:
        """build_planner_context truncates entity list when count > 5000."""
        overflow = ENTITY_CAP + 500
        entities = [_make_entity(str(i), float(i), 0.0) for i in range(overflow)]
        ctx = _make_context(entities)
        result = build_planner_context(ctx)
        assert result.get("entities_truncated") is True
        assert len(result["entities"]) == ENTITY_CAP
        assert result["total_entity_count"] == overflow

    def test_entity_count_field_reflects_full_count_when_truncated(self) -> None:
        """entity_count in context reflects full drawing count, not the capped list."""
        overflow = ENTITY_CAP + 1
        entities = [_make_entity(str(i), float(i), 0.0) for i in range(overflow)]
        ctx = _make_context(entities)
        result = build_planner_context(ctx)
        # entity_count comes from DrawingContext.entity_count — always the true count
        assert result["entity_count"] == overflow

    def test_old_cap_500_would_have_truncated_1000(
        self, dense_context_1000: DrawingContext
    ) -> None:
        """Regression: 1000-entity drawing no longer truncated (was truncated at old cap=500)."""
        ctx = build_planner_context(dense_context_1000)
        # With the old cap of 500, this would have set entities_truncated=True.
        # With the new cap of 5000 it must not.
        assert ctx.get("entities_truncated") is not True
        assert len(ctx["entities"]) == dense_context_1000.entity_count


# ---------------------------------------------------------------------------
# 6. Performance smoke tests — correctness under load, not timing
# ---------------------------------------------------------------------------


class TestPerformanceSmoke:
    """Verify that large-drawing operations complete without error or timeout.

    These are correctness-under-load checks, not micro-benchmarks.
    They assert that results are plausible rather than measuring wall time.
    """

    def test_entity_index_construction_5000(self, tmp_path: Path) -> None:
        """EntityIndex construction with 5000 entities completes without error."""
        dxf_path = create_dense_drawing(tmp_path, count=5000, filename="dense_5000.dxf")
        context = load_dxf(dxf_path)
        index = EntityIndex(context)
        assert index.count == context.entity_count
        assert index.count >= 5000

    def test_nearest_on_5000_entity_drawing(self, tmp_path: Path) -> None:
        """nearest() on 5000-entity drawing returns a valid result."""
        dxf_path = create_dense_drawing(tmp_path, count=5000, filename="dense_5000_near.dxf")
        context = load_dxf(dxf_path)
        index = EntityIndex(context)
        result = index.nearest(0.0, 0.0)
        assert result is not None
        assert result.insert_point is not None

    def test_find_in_radius_on_5000_entity_drawing(self, tmp_path: Path) -> None:
        """find_in_radius() on 5000-entity drawing returns non-empty results."""
        dxf_path = create_dense_drawing(tmp_path, count=5000, filename="dense_5000_rad.dxf")
        context = load_dxf(dxf_path)
        index = EntityIndex(context)
        # Grid spacing is 5.0 — radius=8 should hit several neighbours
        results = index.find_in_radius(25.0, 25.0, radius=8.0)
        assert len(results) > 0
        # All returned entities must actually be within the radius
        for entity in results:
            assert entity.insert_point is not None
            dist = math.hypot(entity.insert_point.x - 25.0, entity.insert_point.y - 25.0)
            assert dist <= 8.0 + 1e-9

    def test_repeated_nearest_queries_5000(self, tmp_path: Path) -> None:
        """100 nearest() queries on 5000-entity drawing all return valid results."""
        dxf_path = create_dense_drawing(tmp_path, count=5000, filename="dense_5000_rep.dxf")
        context = load_dxf(dxf_path)
        index = EntityIndex(context)
        for i in range(100):
            qx = float(i * 3)
            qy = float(i * 2)
            result = index.nearest(qx, qy)
            assert result is not None, f"nearest() returned None for query ({qx},{qy})"

    def test_build_planner_context_with_1000_entities_no_error(
        self, dense_context_1000: DrawingContext
    ) -> None:
        """build_planner_context with 1000 entities completes and is not truncated."""
        result = build_planner_context(dense_context_1000)
        assert "entities" in result
        assert len(result["entities"]) == dense_context_1000.entity_count

    def test_entity_index_filter_on_5000_drawing(self, tmp_path: Path) -> None:
        """filter() on 5000-entity index returns plausible subset without error."""
        dxf_path = create_dense_drawing(tmp_path, count=5000, filename="dense_5000_filt.dxf")
        context = load_dxf(dxf_path)
        index = EntityIndex(context)
        # dense_drawing uses layers: LAYER_A, LAYER_B, LAYER_C, STRUCTURAL, NOTES
        layer_a = index.filter(layer="LAYER_A")
        assert len(layer_a) > 0
        assert all(e.layer.upper() == "LAYER_A" for e in layer_a)

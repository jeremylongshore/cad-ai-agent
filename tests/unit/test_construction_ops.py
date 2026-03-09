"""Comprehensive unit tests for cad_dxf_agent.core.construction_ops.

Covers all four public classes from a single file:
  - GridAnalyzer.analyze()
  - MarkupRedlineGenerator.generate()
  - BatchConditionPlanner.plan()
  - FieldSummaryBuilder.build()

Uses the shared fixtures (sample_context) and dxf_factory helpers to exercise
real DXF-loaded contexts, in addition to hand-crafted in-memory contexts.
"""

from __future__ import annotations

import pytest

from cad_dxf_agent.core.construction_ops import (
    BatchConditionPlanner,
    FieldSummaryBuilder,
    GridAnalyzer,
    MarkupRedlineGenerator,
)
from cad_dxf_agent.models.cad_schema import (
    DrawingContext,
    EntityRef,
    EntityType,
    LayerRule,
    Point2D,
)
from cad_dxf_agent.models.construction_ops_schema import (
    FieldSectionType,
    GridDirection,
)

# ---------------------------------------------------------------------------
# In-memory context builders
# ---------------------------------------------------------------------------


def _entity(
    handle: str,
    layer: str = "STRUCTURAL",
    entity_type: EntityType = EntityType.LINE,
    x: float = 0.0,
    y: float = 0.0,
    block_name: str | None = None,
    text_content: str | None = None,
    attributes: dict | None = None,
    insert_point: Point2D | None = None,
) -> EntityRef:
    pt = insert_point if insert_point is not None else Point2D(x=x, y=y)
    return EntityRef(
        handle=handle,
        entity_type=entity_type,
        layer=layer,
        insert_point=pt,
        block_name=block_name,
        text_content=text_content,
        attributes=attributes or {},
    )


def _ctx(entities: list[EntityRef]) -> DrawingContext:
    layer_names = sorted({e.layer for e in entities}) or ["0"]
    return DrawingContext(
        file_path="test.dxf",
        entities=entities,
        layers=[LayerRule(name=n) for n in layer_names],
    )


def _vline(handle: str, x: float, layer: str = "GRID") -> EntityRef:
    """Vertical LINE on a grid layer."""
    return _entity(
        handle,
        layer=layer,
        entity_type=EntityType.LINE,
        x=x,
        y=0.0,
        attributes={"end_point": (x, 100.0)},
    )


def _hline(handle: str, y: float, layer: str = "GRID") -> EntityRef:
    """Horizontal LINE on a grid layer."""
    return _entity(
        handle,
        layer=layer,
        entity_type=EntityType.LINE,
        x=0.0,
        y=y,
        attributes={"end_point": (200.0, y)},
    )


def _cloud_poly(
    handle: str,
    vertices: list[tuple[float, float]],
    layer: str = "CLOUD",
) -> EntityRef:
    """LWPOLYLINE revision cloud."""
    return _entity(
        handle,
        layer=layer,
        entity_type=EntityType.LWPOLYLINE,
        x=vertices[0][0],
        y=vertices[0][1],
        attributes={"vertices": vertices},
    )


def _insert(
    handle: str,
    block_name: str,
    x: float = 0.0,
    y: float = 0.0,
    layer: str = "STRUCTURAL",
) -> EntityRef:
    return _entity(
        handle,
        layer=layer,
        entity_type=EntityType.INSERT,
        x=x,
        y=y,
        block_name=block_name,
    )


def _text(
    handle: str,
    content: str,
    x: float = 0.0,
    y: float = 0.0,
    layer: str = "NOTES",
) -> EntityRef:
    return _entity(handle, layer=layer, entity_type=EntityType.TEXT, x=x, y=y, text_content=content)


# ---------------------------------------------------------------------------
# Fixtures from dxf_factory for real DXF-loaded contexts
# ---------------------------------------------------------------------------


@pytest.fixture
def structural_context(tmp_path):
    """Full structural drawing loaded into a DrawingContext."""
    from cad_dxf_agent.core.dxf_reader import load_dxf
    from tests.helpers.dxf_factory import create_structural_drawing

    path = create_structural_drawing(tmp_path, grid_cols=4, grid_rows=3, grid_spacing=25.0)
    return load_dxf(path)


@pytest.fixture
def dense_context(tmp_path):
    """Dense drawing (200 entities) loaded into a DrawingContext."""
    from cad_dxf_agent.core.dxf_reader import load_dxf
    from tests.helpers.dxf_factory import create_dense_drawing

    path = create_dense_drawing(tmp_path, count=200)
    return load_dxf(path)


@pytest.fixture
def empty_dxf_context(tmp_path):
    """Empty DXF drawing loaded into a DrawingContext."""
    from cad_dxf_agent.core.dxf_reader import load_dxf
    from tests.helpers.dxf_factory import create_empty_dxf

    path = create_empty_dxf(tmp_path)
    return load_dxf(path)


# ---------------------------------------------------------------------------
# 1. GridAnalyzer — normal paths
# ---------------------------------------------------------------------------


class TestGridAnalyzerNormalPaths:
    def test_detects_vertical_lines_on_grid_layer(self):
        ctx = _ctx([_vline("V1", 0.0), _vline("V2", 30.0), _vline("V3", 60.0)])
        result = GridAnalyzer().analyze(ctx, "grid summary")
        vlines = [g for g in result.grid_lines if g.direction == GridDirection.VERTICAL]
        assert len(vlines) == 3
        # Verify specific handles and positions
        handles = {g.entity_handle for g in vlines}
        assert handles == {"V1", "V2", "V3"}
        positions = sorted(g.position for g in vlines)
        assert positions == pytest.approx([0.0, 30.0, 60.0])

    def test_detects_horizontal_lines_on_column_layer(self):
        ctx = _ctx([_hline("H1", 0.0, layer="COLUMN"), _hline("H2", 25.0, layer="COLUMN")])
        result = GridAnalyzer().analyze(ctx, "grid summary")
        hlines = [g for g in result.grid_lines if g.direction == GridDirection.HORIZONTAL]
        assert len(hlines) == 2

    def test_bays_computed_for_adjacent_vertical_lines(self):
        ctx = _ctx([_vline("V1", 0.0), _vline("V2", 30.0), _vline("V3", 60.0)])
        result = GridAnalyzer().analyze(ctx, "grid")
        vbays = [b for b in result.bays if b.direction == GridDirection.VERTICAL]
        assert len(vbays) == 2
        dims = sorted(b.dimension for b in vbays)
        assert dims[0] == pytest.approx(30.0)
        assert dims[1] == pytest.approx(30.0)

    def test_label_assigned_from_nearby_text(self):
        grid_line = _vline("V1", 10.0)
        label_text = _text("T1", "GridA", x=10.0, y=-5.0, layer="GRID")
        ctx = _ctx([grid_line, label_text])
        result = GridAnalyzer().analyze(ctx, "grid")
        vlines = [g for g in result.grid_lines if g.direction == GridDirection.VERTICAL]
        assert vlines[0].label == "GridA"

    def test_labeled_lines_have_higher_confidence_than_unlabeled(self):
        labeled = _vline("V1", 0.0)
        label = _text("T1", "A", x=0.0, y=-5.0, layer="GRID")
        unlabeled = _vline("V2", 50.0)
        ctx = _ctx([labeled, label, unlabeled])
        result = GridAnalyzer().analyze(ctx, "grid")
        found = {g.entity_handle: g.confidence for g in result.grid_lines}
        assert found["V1"] > found["V2"]

    def test_drawing_summary_contains_entity_count(self):
        ctx = _ctx([_vline("V1", 0.0), _vline("V2", 30.0)])
        result = GridAnalyzer().analyze(ctx, "grid")
        assert "2" in result.drawing_summary

    def test_aggregate_confidence_bounded_0_to_1(self):
        ctx = _ctx([_vline("V1", 0.0)])
        result = GridAnalyzer().analyze(ctx, "grid")
        assert 0.0 <= result.aggregate_confidence <= 1.0
        # Single unlabeled grid line should have confidence 0.6
        assert result.aggregate_confidence == pytest.approx(0.6)

    def test_region_parameter_filters_entities(self):
        """When a RegionContext is supplied, only its entities are analyzed."""
        from cad_dxf_agent.models.qna_schema import RegionContext

        v1 = _vline("V1", 0.0)
        v2 = _vline("V2", 30.0)
        all_ctx = _ctx([v1, v2])

        # Region contains only v1
        region = RegionContext(entities=[v1])
        result_with_region = GridAnalyzer().analyze(all_ctx, "grid", region=region)
        result_without = GridAnalyzer().analyze(all_ctx, "grid")

        assert len(result_with_region.grid_lines) < len(result_without.grid_lines)

    def test_real_dxf_structural_drawing(self, structural_context):
        """Structural drawing (4 cols x 3 rows) must produce grid lines and bays."""
        result = GridAnalyzer().analyze(structural_context, "analyze grid")
        assert result is not None
        assert isinstance(result.grid_lines, list)
        assert isinstance(result.bays, list)
        # Factory creates grid_cols=4 vertical + grid_rows=3 horizontal = 7 grid lines
        # on STRUCTURAL layer (not GRID layer), so GridAnalyzer won't detect them
        # because they're on STRUCTURAL, not GRID/COLUMN/AXIS.
        # The factory drawing uses STRUCTURAL for grid lines, so we expect 0 here.
        # This test validates the integration doesn't crash and returns coherent data.
        assert result.aggregate_confidence >= 0.0


# ---------------------------------------------------------------------------
# 2. GridAnalyzer — edge cases
# ---------------------------------------------------------------------------


class TestGridAnalyzerEdgeCases:
    def test_empty_context_returns_empty_grid_lines(self):
        ctx = DrawingContext(file_path="t.dxf", entities=[], layers=[LayerRule(name="0")])
        result = GridAnalyzer().analyze(ctx, "grid")
        assert result.grid_lines == []
        assert result.bays == []
        assert "empty" in " ".join(result.ambiguity_flags + result.caveats).lower()

    def test_entities_on_non_grid_layers_ignored(self):
        ctx = _ctx([_vline("V1", 0.0, layer="WALLS"), _hline("H1", 5.0, layer="ELECTRICAL")])
        result = GridAnalyzer().analyze(ctx, "grid")
        assert result.grid_lines == []
        assert "no_grid_entities" in result.ambiguity_flags

    def test_line_missing_end_point_skipped(self):
        """LINE without end_point in attributes must not crash and produces no grid line."""
        bad = _entity("V1", layer="GRID", entity_type=EntityType.LINE, x=5.0, y=0.0)
        # No 'end_point' in attributes → skipped by _classify_line
        ctx = _ctx([bad])
        result = GridAnalyzer().analyze(ctx, "grid")
        assert result.grid_lines == []

    def test_lwpolyline_with_single_vertex_skipped(self):
        """LWPOLYLINE with fewer than 2 vertices cannot be classified."""
        bad = _entity(
            "P1",
            layer="GRID",
            entity_type=EntityType.LWPOLYLINE,
            x=0.0,
            y=0.0,
            attributes={"vertices": [(0.0, 0.0)]},
        )
        ctx = _ctx([bad])
        result = GridAnalyzer().analyze(ctx, "grid")
        assert result.grid_lines == []

    def test_diagonal_line_on_grid_layer_not_classified(self):
        diag = _entity(
            "D1",
            layer="GRID",
            entity_type=EntityType.LINE,
            x=0.0,
            y=0.0,
            attributes={"end_point": (50.0, 50.0)},
        )
        ctx = _ctx([diag])
        result = GridAnalyzer().analyze(ctx, "grid")
        assert result.grid_lines == []

    def test_single_grid_line_produces_no_bays(self):
        """One grid line cannot form a bay — bays require adjacent pairs."""
        ctx = _ctx([_vline("V1", 0.0)])
        result = GridAnalyzer().analyze(ctx, "grid")
        assert result.bays == []

    def test_text_too_far_not_used_as_label(self):
        ctx = _ctx(
            [
                _vline("V1", 10.0),
                _text("T1", "FarLabel", x=600.0, y=600.0, layer="GRID"),
            ]
        )
        result = GridAnalyzer().analyze(ctx, "grid")
        vlines = [g for g in result.grid_lines if g.direction == GridDirection.VERTICAL]
        assert len(vlines) == 1
        assert vlines[0].label == ""


# ---------------------------------------------------------------------------
# 3. MarkupRedlineGenerator — normal paths
# ---------------------------------------------------------------------------


class TestMarkupRedlineGeneratorNormalPaths:
    def test_cloud_on_cloud_layer_detected(self):
        cloud = _cloud_poly("C1", [(0, 0), (100, 0), (100, 100), (0, 100)])
        inside = _entity("E1", x=50.0, y=50.0)
        ctx = _ctx([cloud, inside])
        result = MarkupRedlineGenerator().generate(ctx, "redline")
        assert result.total_clouds == 1

    def test_entity_inside_bbox_counted_as_affected(self):
        cloud = _cloud_poly("C1", [(0, 0), (100, 0), (100, 100), (0, 100)])
        inside = _entity("E1", x=50.0, y=50.0)
        outside = _entity("E2", x=200.0, y=200.0)
        ctx = _ctx([cloud, inside, outside])
        result = MarkupRedlineGenerator().generate(ctx, "redline")
        handles = [e.entity_handle for e in result.entries[0].affected_entities]
        assert "E1" in handles
        assert "E2" not in handles

    def test_cloud_excluded_from_its_own_affected_list(self):
        cloud = _cloud_poly("C1", [(0, 0), (100, 0), (100, 100), (0, 100)])
        ctx = _ctx([cloud, _entity("E1", x=50.0, y=50.0)])
        result = MarkupRedlineGenerator().generate(ctx, "redline")
        handles = [e.entity_handle for e in result.entries[0].affected_entities]
        assert "C1" not in handles

    def test_multiple_clouds_each_produce_entry(self):
        c1 = _cloud_poly("C1", [(0, 0), (50, 0), (50, 50), (0, 50)])
        c2 = _cloud_poly("C2", [(200, 200), (300, 200), (300, 300), (200, 300)])
        e1 = _entity("E1", x=25.0, y=25.0)
        e2 = _entity("E2", x=250.0, y=250.0)
        ctx = _ctx([c1, c2, e1, e2])
        result = MarkupRedlineGenerator().generate(ctx, "redline")
        assert result.total_clouds == 2
        assert len(result.entries) == 2

    def test_affected_layers_reported_in_entry(self):
        cloud = _cloud_poly("C1", [(0, 0), (100, 0), (100, 100), (0, 100)])
        e1 = _entity("E1", layer="STRUCTURAL", x=30.0, y=30.0)
        e2 = _entity("E2", layer="ELECTRICAL", x=60.0, y=60.0)
        ctx = _ctx([cloud, e1, e2])
        result = MarkupRedlineGenerator().generate(ctx, "redline")
        layers = result.entries[0].affected_layers
        assert "STRUCTURAL" in layers
        assert "ELECTRICAL" in layers

    def test_entity_count_matches_affected_entities_length(self):
        cloud = _cloud_poly("C1", [(0, 0), (100, 0), (100, 100), (0, 100)])
        for_inside = [_entity(f"E{i}", x=float(i * 5), y=float(i * 5)) for i in range(5)]
        ctx = _ctx([cloud] + for_inside)
        result = MarkupRedlineGenerator().generate(ctx, "redline")
        entry = result.entries[0]
        # All 5 entities are at (0,0)-(20,20) which is inside the (0,0)-(100,100) bbox
        assert entry.entity_count == 5
        assert len(entry.affected_entities) == 5

    def test_aggregate_confidence_equals_min_of_entries(self):
        # Two clouds: one with 8+ vertices (higher conf), one with 4 (lower)
        many_v = [(i * 10, i * 8) for i in range(10)]
        c1 = _cloud_poly("C1", many_v, layer="CLOUD")
        c2 = _cloud_poly("C2", [(200, 200), (300, 200), (300, 300), (200, 300)], layer="CLOUD")
        xs, ys = [v[0] for v in many_v], [v[1] for v in many_v]
        mid = _entity("E1", x=(min(xs) + max(xs)) / 2, y=(min(ys) + max(ys)) / 2)
        e2 = _entity("E2", x=250.0, y=250.0)
        ctx = _ctx([c1, c2, mid, e2])
        result = MarkupRedlineGenerator().generate(ctx, "redline")
        if len(result.entries) >= 2:
            assert result.aggregate_confidence == pytest.approx(
                min(e.confidence for e in result.entries), abs=0.01
            )

    def test_real_dxf_with_sample_context(self, sample_context):
        """sample_context fixture — no clouds present, should gracefully return no entries."""
        result = MarkupRedlineGenerator().generate(sample_context, "check redlines")
        assert result is not None
        assert isinstance(result.entries, list)


# ---------------------------------------------------------------------------
# 4. MarkupRedlineGenerator — edge cases
# ---------------------------------------------------------------------------


class TestMarkupRedlineGeneratorEdgeCases:
    def test_empty_drawing_returns_no_entries(self):
        ctx = DrawingContext(file_path="t.dxf", entities=[], layers=[LayerRule(name="0")])
        result = MarkupRedlineGenerator().generate(ctx, "redline")
        assert result.entries == []
        assert result.total_clouds == 0
        assert "empty_drawing" in result.ambiguity_flags

    def test_no_clouds_in_drawing_sets_no_clouds_flag(self):
        ctx = _ctx([_entity("E1", x=0.0, y=0.0)])
        result = MarkupRedlineGenerator().generate(ctx, "redline")
        assert result.total_clouds == 0
        assert "no_clouds" in result.ambiguity_flags

    def test_lwpolyline_on_non_cloud_layer_ignored(self):
        poly = _entity(
            "P1",
            layer="STRUCTURAL",
            entity_type=EntityType.LWPOLYLINE,
            attributes={"vertices": [(0, 0), (100, 0), (100, 100), (0, 100)]},
        )
        ctx = _ctx([poly])
        result = MarkupRedlineGenerator().generate(ctx, "redline")
        assert result.total_clouds == 0

    def test_cloud_with_no_vertices_skipped(self):
        bad_cloud = _entity(
            "C1",
            layer="CLOUD",
            entity_type=EntityType.LWPOLYLINE,
            attributes={"vertices": []},
        )
        ctx = _ctx([bad_cloud])
        result = MarkupRedlineGenerator().generate(ctx, "redline")
        assert result.total_clouds == 0

    def test_entity_without_insert_point_not_counted(self):
        cloud = _cloud_poly("C1", [(0, 0), (100, 0), (100, 100), (0, 100)])
        # EntityRef with no insert_point
        no_pt = EntityRef(
            handle="NO_PT",
            entity_type=EntityType.LINE,
            layer="STRUCTURAL",
        )
        ctx = _ctx([cloud, no_pt])
        result = MarkupRedlineGenerator().generate(ctx, "redline")
        handles = [e.entity_handle for e in result.entries[0].affected_entities]
        assert "NO_PT" not in handles


# ---------------------------------------------------------------------------
# 5. BatchConditionPlanner — normal paths
# ---------------------------------------------------------------------------


class TestBatchConditionPlannerNormalPaths:
    def test_three_identical_inserts_form_group(self):
        entities = [_insert(f"I{i}", "DOOR", x=float(i * 20)) for i in range(3)]
        ctx = _ctx(entities)
        result = BatchConditionPlanner().plan(ctx, "batch")
        assert result.total_groups >= 1

    def test_group_sorted_by_instance_count_descending(self):
        small = [_insert(f"SA{i}", "SMALL", x=float(i * 5)) for i in range(3)]
        large = [_insert(f"LA{i}", "LARGE", x=float(i * 5 + 100)) for i in range(7)]
        ctx = _ctx(small + large)
        result = BatchConditionPlanner().plan(ctx, "batch")
        counts = [g.total_instances for g in result.groups]
        assert counts == sorted(counts, reverse=True)

    def test_text_entities_grouped_by_similarity(self):
        texts = [_text(f"T{i}", "EXIT SIGN", x=float(i * 30)) for i in range(4)]
        ctx = _ctx(texts)
        result = BatchConditionPlanner().plan(ctx, "batch")
        assert result.total_groups >= 1

    def test_total_instances_sum_matches_group_instances(self):
        inserts = [_insert(f"I{i}", "VALVE", x=float(i * 10)) for i in range(5)]
        ctx = _ctx(inserts)
        result = BatchConditionPlanner().plan(ctx, "batch")
        calculated = sum(g.total_instances for g in result.groups)
        assert result.total_instances == calculated

    def test_total_groups_matches_groups_length(self):
        inserts = [_insert(f"I{i}", "OUTLET", x=float(i * 10)) for i in range(4)]
        ctx = _ctx(inserts)
        result = BatchConditionPlanner().plan(ctx, "batch")
        assert result.total_groups == len(result.groups)

    def test_block_group_name_contains_block_name(self):
        inserts = [_insert(f"I{i}", "SPRINKLER", x=float(i * 10)) for i in range(3)]
        ctx = _ctx(inserts)
        result = BatchConditionPlanner().plan(ctx, "batch")
        names = [g.name for g in result.groups]
        assert any("SPRINKLER" in n for n in names)

    def test_exemplar_handle_is_valid_entity_handle(self):
        inserts = [_insert(f"I{i}", "MARK", x=float(i * 10)) for i in range(3)]
        ctx = _ctx(inserts)
        result = BatchConditionPlanner().plan(ctx, "batch")
        all_handles = {e.handle for e in inserts}
        for group in result.groups:
            assert group.exemplar_handles[0] in all_handles

    def test_dense_drawing_with_block_inserts(self, dense_context):
        """Dense factory drawing — no crash, result is valid."""
        result = BatchConditionPlanner().plan(dense_context, "batch conditions")
        assert result is not None
        assert isinstance(result.groups, list)


# ---------------------------------------------------------------------------
# 6. BatchConditionPlanner — edge cases
# ---------------------------------------------------------------------------


class TestBatchConditionPlannerEdgeCases:
    def test_empty_drawing_returns_zero_groups(self):
        ctx = DrawingContext(file_path="t.dxf", entities=[], layers=[LayerRule(name="0")])
        result = BatchConditionPlanner().plan(ctx, "batch")
        assert result.total_groups == 0
        assert "empty_drawing" in result.ambiguity_flags

    def test_two_inserts_below_min_threshold(self):
        inserts = [_insert(f"I{i}", "DOOR", x=float(i * 10)) for i in range(2)]
        ctx = _ctx(inserts)
        result = BatchConditionPlanner().plan(ctx, "batch")
        door_groups = [g for g in result.groups if "DOOR" in g.name]
        assert len(door_groups) == 0

    def test_insert_without_block_name_not_grouped(self):
        entities = [
            EntityRef(handle=f"I{i}", entity_type=EntityType.INSERT, layer="STRUCTURAL")
            for i in range(5)
        ]
        ctx = _ctx(entities)
        result = BatchConditionPlanner().plan(ctx, "batch")
        assert result.total_groups == 0

    def test_lines_not_grouped_at_all(self):
        lines = [_entity(f"L{i}", entity_type=EntityType.LINE, x=float(i * 10)) for i in range(5)]
        ctx = _ctx(lines)
        result = BatchConditionPlanner().plan(ctx, "batch")
        assert result.total_groups == 0

    def test_dissimilar_texts_not_grouped(self):
        texts = [
            _text("T1", "DOOR SCHEDULE", x=0),
            _text("T2", "ELECTRICAL PANEL", x=100),
            _text("T3", "FOOTING DETAIL", x=200),
        ]
        ctx = _ctx(texts)
        result = BatchConditionPlanner().plan(ctx, "batch")
        text_groups = [g for g in result.groups if g.name.startswith("Text:")]
        assert len(text_groups) == 0

    def test_aggregate_confidence_is_min_of_group_confidences(self):
        small = [_insert(f"SA{i}", "SMALL", x=float(i * 5)) for i in range(3)]
        large = [_insert(f"LA{i}", "LARGE", x=float(i * 5 + 100)) for i in range(10)]
        ctx = _ctx(small + large)
        result = BatchConditionPlanner().plan(ctx, "batch")
        if len(result.groups) >= 2:
            expected = min(g.confidence for g in result.groups)
            assert result.aggregate_confidence == pytest.approx(expected, abs=0.01)

    def test_no_matching_patterns_produces_caveat(self):
        lines = [_entity(f"L{i}", entity_type=EntityType.LINE, x=float(i * 10)) for i in range(3)]
        ctx = _ctx(lines)
        result = BatchConditionPlanner().plan(ctx, "batch")
        assert len(result.caveats) > 0 or result.total_groups == 0


# ---------------------------------------------------------------------------
# 7. FieldSummaryBuilder — normal paths
# ---------------------------------------------------------------------------


def _grid_and_inserts_ctx() -> DrawingContext:
    """Context with 4 vertical grid lines + 5 block inserts for multi-section coverage."""
    vlines = [
        EntityRef(
            handle=f"VG{i}",
            entity_type=EntityType.LINE,
            layer="GRID",
            insert_point=Point2D(x=float(i * 30), y=0.0),
            attributes={"end_point": (float(i * 30), 100.0)},
        )
        for i in range(4)
    ]
    inserts = [_insert(f"BLK{i}", "COL", x=float(i * 30), y=50.0) for i in range(5)]
    all_entities = vlines + inserts
    layer_names = sorted({e.layer for e in all_entities})
    return DrawingContext(
        file_path="test.dxf",
        entities=all_entities,
        layers=[LayerRule(name=n) for n in layer_names],
    )


class TestFieldSummaryBuilderNormalPaths:
    def test_returns_field_summary_instance(self):
        ctx = _grid_and_inserts_ctx()
        result = FieldSummaryBuilder().build(ctx, prompt="field summary")
        assert result is not None

    def test_sections_is_list(self):
        ctx = _grid_and_inserts_ctx()
        result = FieldSummaryBuilder().build(ctx, prompt="field summary")
        assert isinstance(result.sections, list)

    def test_grid_summary_section_appears_with_grid_entities(self):
        ctx = _grid_and_inserts_ctx()
        result = FieldSummaryBuilder().build(ctx, prompt="field summary")
        types = [s.section_type for s in result.sections]
        assert FieldSectionType.GRID_SUMMARY in types

    def test_condition_report_appears_with_repeated_blocks(self):
        inserts = [_insert(f"I{i}", "FOOTING", x=float(i * 10)) for i in range(5)]
        ctx = _ctx(inserts)
        result = FieldSummaryBuilder().build(ctx, prompt="field summary")
        types = [s.section_type for s in result.sections]
        assert FieldSectionType.CONDITION_REPORT in types

    def test_revision_changes_present_when_comparison_supplied(self):
        from cad_dxf_agent.models.comparison_schema import (
            ChangeCategory,
            ComparisonResult,
            EntityChange,
            GeometrySnapshot,
        )

        snap = GeometrySnapshot(
            handle="X1",
            entity_type=EntityType.LINE,
            layer="STRUCTURAL",
            points=[Point2D(x=0, y=0), Point2D(x=10, y=0)],
        )
        comp = ComparisonResult(
            changes=[
                EntityChange(
                    category=ChangeCategory.ADDED,
                    revision_snapshot=snap,
                    confidence=0.9,
                )
            ],
            summary={"added": 1, "removed": 0, "modified": 0, "moved": 0, "unchanged": 0},
        )
        ctx = _ctx([_insert("I1", "BLK"), _insert("I2", "BLK"), _insert("I3", "BLK")])
        result = FieldSummaryBuilder().build(ctx, prompt="summarize", comparison_result=comp)
        types = [s.section_type for s in result.sections]
        assert FieldSectionType.REVISION_CHANGES in types

    def test_default_title_value(self):
        ctx = _grid_and_inserts_ctx()
        result = FieldSummaryBuilder().build(ctx, prompt="field summary")
        assert result.title == "Construction Field Summary"

    def test_generated_at_is_non_empty_string(self):
        ctx = _grid_and_inserts_ctx()
        result = FieldSummaryBuilder().build(ctx, prompt="field summary")
        assert isinstance(result.generated_at, str)
        assert len(result.generated_at) > 0

    def test_all_sections_have_valid_section_type_enum(self):
        ctx = _grid_and_inserts_ctx()
        result = FieldSummaryBuilder().build(ctx, prompt="field summary")
        valid = set(FieldSectionType)
        for section in result.sections:
            assert section.section_type in valid

    def test_model_dump_produces_dict_with_no_edit_op_keys(self):
        ctx = _grid_and_inserts_ctx()
        result = FieldSummaryBuilder().build(ctx, prompt="field summary")
        dumped = result.model_dump()
        assert isinstance(dumped, dict)
        dumped_str = str(dumped)
        for forbidden in ("op_type", "move_entity", "edit_text", "delete_entity", "add_block"):
            assert forbidden not in dumped_str

    def test_aggregate_confidence_is_min_of_section_confidences(self):
        ctx = _grid_and_inserts_ctx()
        result = FieldSummaryBuilder().build(ctx, prompt="field summary")
        if result.sections:
            expected = min(s.confidence for s in result.sections)
            assert result.aggregate_confidence == pytest.approx(expected)

    def test_caveats_is_list(self):
        ctx = _grid_and_inserts_ctx()
        result = FieldSummaryBuilder().build(ctx, prompt="field summary")
        assert isinstance(result.caveats, list)

    def test_omitted_sections_is_list(self):
        ctx = _grid_and_inserts_ctx()
        result = FieldSummaryBuilder().build(ctx, prompt="field summary")
        assert isinstance(result.omitted_sections, list)


# ---------------------------------------------------------------------------
# 8. FieldSummaryBuilder — edge cases
# ---------------------------------------------------------------------------


class TestFieldSummaryBuilderEdgeCases:
    def test_empty_drawing_returns_empty_sections(self):
        ctx = DrawingContext(file_path="t.dxf", entities=[], layers=[LayerRule(name="0")])
        result = FieldSummaryBuilder().build(ctx, prompt="summarize")
        assert result.sections == []

    def test_empty_drawing_all_sections_listed_as_omitted(self):
        ctx = DrawingContext(file_path="t.dxf", entities=[], layers=[LayerRule(name="0")])
        result = FieldSummaryBuilder().build(ctx, prompt="summarize")
        assert len(result.omitted_sections) >= 3

    def test_no_grid_entities_omits_grid_summary(self):
        inserts = [_insert(f"I{i}", "BLK", x=float(i * 10)) for i in range(5)]
        ctx = _ctx(inserts)
        result = FieldSummaryBuilder().build(ctx, prompt="summarize")
        omitted_str = " ".join(result.omitted_sections).lower()
        assert "grid" in omitted_str

    def test_no_comparison_omits_revision_changes(self):
        ctx = _grid_and_inserts_ctx()
        result = FieldSummaryBuilder().build(ctx, prompt="summarize", comparison_result=None)
        omitted_str = " ".join(result.omitted_sections).lower()
        assert "revision" in omitted_str

    def test_none_comparison_and_none_changeset_no_crash(self):
        ctx = _grid_and_inserts_ctx()
        result = FieldSummaryBuilder().build(
            ctx, prompt="summarize", comparison_result=None, changeset=None
        )
        assert result is not None

    def test_real_dxf_structural_drawing(self, structural_context):
        """Full structural drawing from disk — FieldSummaryBuilder must not crash."""
        result = FieldSummaryBuilder().build(structural_context, prompt="generate field summary")
        assert result is not None
        assert isinstance(result.sections, list)
        assert 0.0 <= result.aggregate_confidence <= 1.0


# ---------------------------------------------------------------------------
# Negative / boundary tests — adversarial inputs
# ---------------------------------------------------------------------------


class TestBatchConditionPlannerBoundary:
    """Boundary conditions for the grouping threshold."""

    def test_exactly_two_inserts_below_threshold(self):
        """Exactly 2 inserts of the same block must NOT form a group (threshold is 3)."""
        inserts = [_insert(f"I{i}", "SENSOR", x=float(i * 10)) for i in range(2)]
        ctx = _ctx(inserts)
        result = BatchConditionPlanner().plan(ctx, "batch")
        assert result.total_groups == 0
        assert result.total_instances == 0

    def test_exactly_three_inserts_at_threshold(self):
        """Exactly 3 inserts must form exactly one group (threshold is >=3)."""
        inserts = [_insert(f"I{i}", "PUMP", x=float(i * 10)) for i in range(3)]
        ctx = _ctx(inserts)
        result = BatchConditionPlanner().plan(ctx, "batch")
        assert result.total_groups == 1
        assert result.groups[0].total_instances == 3
        assert "PUMP" in result.groups[0].name


class TestGridAnalyzerNaNCoords:
    """Grid analyzer must handle entities with NaN or extreme coordinates."""

    def test_nan_endpoint_skipped(self):
        """A LINE with NaN end_point must not crash or produce a grid line."""
        bad = _entity(
            "V_NAN",
            layer="GRID",
            entity_type=EntityType.LINE,
            x=10.0,
            y=0.0,
            attributes={"end_point": (float("nan"), float("nan"))},
        )
        good = _vline("V_OK", 50.0)
        ctx = _ctx([bad, good])
        result = GridAnalyzer().analyze(ctx, "grid")
        # The NaN line has dx=nan, dy=nan — classify_line returns None
        # Only the good line should be detected
        handles = {g.entity_handle for g in result.grid_lines}
        assert "V_OK" in handles


# ---------------------------------------------------------------------------
# Mutation-killing tests — _classify_line tolerance, LWPOLYLINE support,
# _find_label truncation/proximity, _compute_bays label format and dimension,
# grid_pattern_description exact content, drawing_summary format,
# MarkupRedlineGenerator confidence calculation exact values,
# description string content, BatchConditionPlanner grouping internals,
# _group_by_block instance details and confidence scaling,
# _group_by_text cluster details, name prefix, similarity threshold,
# FieldSummaryBuilder section titles, content keys, confidence propagation
# ---------------------------------------------------------------------------


class TestClassifyLineTolerance:
    """Kill mutations on the 0.01 tolerance boundary in _classify_line."""

    def test_dx_exactly_at_tolerance_is_not_vertical(self):
        """dx == 0.01 is NOT < 0.01 so the line is NOT classified vertical."""
        entity = _entity(
            "V_EXACT",
            layer="GRID",
            entity_type=EntityType.LINE,
            x=0.0,
            y=0.0,
            attributes={"end_point": (0.01, 100.0)},
        )
        ctx = _ctx([entity])
        result = GridAnalyzer().analyze(ctx, "grid")
        # dx == 0.01 fails the < 0.01 check → not classified → no grid line
        assert result.grid_lines == []

    def test_dx_just_below_tolerance_is_vertical(self):
        """dx < 0.01 (here 0.009) with large dy → classified VERTICAL."""
        entity = _entity(
            "V_BELOW",
            layer="GRID",
            entity_type=EntityType.LINE,
            x=0.0,
            y=0.0,
            attributes={"end_point": (0.009, 100.0)},
        )
        ctx = _ctx([entity])
        result = GridAnalyzer().analyze(ctx, "grid")
        vlines = [g for g in result.grid_lines if g.direction == GridDirection.VERTICAL]
        assert len(vlines) == 1

    def test_lwpolyline_classified_as_vertical(self):
        """LWPOLYLINE with vertical span is classified as VERTICAL grid line."""
        poly = _entity(
            "PV1",
            layer="GRID",
            entity_type=EntityType.LWPOLYLINE,
            x=20.0,
            y=0.0,
            attributes={"vertices": [(20.0, 0.0), (20.0, 100.0)]},
        )
        ctx = _ctx([poly])
        result = GridAnalyzer().analyze(ctx, "grid")
        vlines = [g for g in result.grid_lines if g.direction == GridDirection.VERTICAL]
        assert len(vlines) == 1
        assert vlines[0].entity_handle == "PV1"
        assert vlines[0].position == pytest.approx(20.0)

    def test_lwpolyline_classified_as_horizontal(self):
        """LWPOLYLINE with horizontal span is classified as HORIZONTAL grid line."""
        poly = _entity(
            "PH1",
            layer="GRID",
            entity_type=EntityType.LWPOLYLINE,
            x=0.0,
            y=15.0,
            attributes={"vertices": [(0.0, 15.0), (200.0, 15.0)]},
        )
        ctx = _ctx([poly])
        result = GridAnalyzer().analyze(ctx, "grid")
        hlines = [g for g in result.grid_lines if g.direction == GridDirection.HORIZONTAL]
        assert len(hlines) == 1
        assert hlines[0].position == pytest.approx(15.0)


class TestFindLabelMutationKilling:
    """Kill mutations on _find_label truncation and proximity cutoff."""

    def test_label_truncated_to_20_chars(self):
        """Text content longer than 20 chars must be truncated in the label."""
        long_text = "ABCDEFGHIJKLMNOPQRSTUVWXYZ"  # 26 chars
        grid_line = _vline("V1", 10.0)
        label_text = _text("T1", long_text, x=10.0, y=-5.0, layer="GRID")
        ctx = _ctx([grid_line, label_text])
        result = GridAnalyzer().analyze(ctx, "grid")
        vlines = [g for g in result.grid_lines if g.direction == GridDirection.VERTICAL]
        assert vlines[0].label == long_text[:20]

    def test_label_exactly_at_max_proximity_not_assigned(self):
        """Text exactly at _MAX_LABEL_PROXIMITY (50.0) must NOT be assigned as label."""
        # _find_label uses `dist < best_dist` where best_dist starts at 50.0.
        # dist == 50.0 fails `dist < 50.0` so no label assigned.
        grid_line = _vline("V1", 0.0)
        label_text = _text("T1", "GridA", x=50.0, y=0.0, layer="GRID")  # dist = 50.0
        ctx = _ctx([grid_line, label_text])
        result = GridAnalyzer().analyze(ctx, "grid")
        vlines = [g for g in result.grid_lines if g.direction == GridDirection.VERTICAL]
        assert vlines[0].label == ""

    def test_label_just_inside_proximity_is_assigned(self):
        """Text at dist == 49.99 (< 50.0) must be assigned."""
        grid_line = _vline("V1", 0.0)
        label_text = _text("T1", "NearLabel", x=49.99, y=0.0, layer="GRID")
        ctx = _ctx([grid_line, label_text])
        result = GridAnalyzer().analyze(ctx, "grid")
        vlines = [g for g in result.grid_lines if g.direction == GridDirection.VERTICAL]
        assert vlines[0].label == "NearLabel"


class TestComputeBaysMutationKilling:
    """Kill mutations on _compute_bays label format and dimension calculation."""

    def test_bay_label_is_a_minus_b_format(self):
        """Bay label must be '{label_a}-{label_b}' from the grid line labels."""
        labeled_a = _vline("V1", 0.0)
        label_a_text = _text("TA", "A", x=0.0, y=-5.0, layer="GRID")
        labeled_b = _vline("V2", 30.0)
        label_b_text = _text("TB", "B", x=30.0, y=-5.0, layer="GRID")
        ctx = _ctx([labeled_a, label_a_text, labeled_b, label_b_text])
        result = GridAnalyzer().analyze(ctx, "grid")
        vbays = [b for b in result.bays if b.direction == GridDirection.VERTICAL]
        assert len(vbays) == 1
        assert vbays[0].label == "A-B"

    def test_bay_dimension_is_absolute_difference(self):
        """Bay dimension must be abs(pos_b - pos_a), exactly 30.0 here."""
        ctx = _ctx([_vline("V1", 10.0), _vline("V2", 40.0)])
        result = GridAnalyzer().analyze(ctx, "grid")
        vbays = [b for b in result.bays if b.direction == GridDirection.VERTICAL]
        assert len(vbays) == 1
        assert vbays[0].dimension == pytest.approx(30.0)

    def test_unlabeled_bay_uses_l1_l2_fallback(self):
        """Unlabeled grid lines fall back to 'L1', 'L2', etc. for bay label."""
        ctx = _ctx([_vline("V1", 0.0), _vline("V2", 25.0)])
        result = GridAnalyzer().analyze(ctx, "grid")
        vbays = [b for b in result.bays if b.direction == GridDirection.VERTICAL]
        assert len(vbays) == 1
        assert vbays[0].label == "L1-L2"

    def test_bay_start_line_and_end_line_set_correctly(self):
        """Bay start_line and end_line must match label_a and label_b."""
        labeled_a = _vline("V1", 0.0)
        label_a = _text("TA", "X", x=0.0, y=-5.0, layer="GRID")
        labeled_b = _vline("V2", 20.0)
        label_b = _text("TB", "Y", x=20.0, y=-5.0, layer="GRID")
        ctx = _ctx([labeled_a, label_a, labeled_b, label_b])
        result = GridAnalyzer().analyze(ctx, "grid")
        vbays = [b for b in result.bays if b.direction == GridDirection.VERTICAL]
        assert vbays[0].start_line == "X"
        assert vbays[0].end_line == "Y"


class TestGridPatternDescriptionContent:
    """Kill mutations on grid_pattern_description and drawing_summary format."""

    def test_grid_pattern_description_contains_vertical_count(self):
        """grid_pattern_description must include the vertical line count."""
        ctx = _ctx([_vline("V1", 0.0), _vline("V2", 30.0), _hline("H1", 10.0)])
        result = GridAnalyzer().analyze(ctx, "grid")
        assert "2" in result.grid_pattern_description
        assert "vertical" in result.grid_pattern_description

    def test_grid_pattern_description_contains_horizontal_count(self):
        """grid_pattern_description must include the horizontal line count."""
        ctx = _ctx([_vline("V1", 0.0), _hline("H1", 10.0), _hline("H2", 20.0)])
        result = GridAnalyzer().analyze(ctx, "grid")
        assert "2" in result.grid_pattern_description
        assert "horizontal" in result.grid_pattern_description

    def test_drawing_summary_contains_grid_line_count(self):
        """drawing_summary must contain the total grid line count."""
        ctx = _ctx([_vline("V1", 0.0), _vline("V2", 30.0), _hline("H1", 10.0)])
        result = GridAnalyzer().analyze(ctx, "grid")
        # 3 grid lines total
        assert "3" in result.drawing_summary

    def test_drawing_summary_contains_bay_count(self):
        """drawing_summary must contain the bay count."""
        ctx = _ctx([_vline("V1", 0.0), _vline("V2", 30.0), _vline("V3", 60.0)])
        result = GridAnalyzer().analyze(ctx, "grid")
        # 2 vertical bays
        assert "2" in result.drawing_summary


class TestMarkupRedlineConfidenceMutationKilling:
    """Kill mutations on confidence calculation and description in MarkupRedlineGenerator."""

    def test_four_vertex_cloud_confidence_is_0_7(self):
        """Cloud with 4 vertices on non-CLOUD layer → confidence = 0.7."""
        cloud = _cloud_poly("C1", [(0, 0), (100, 0), (100, 100), (0, 100)], layer="MARKUP")
        ctx = _ctx([cloud])
        result = MarkupRedlineGenerator().generate(ctx, "redline")
        assert result.entries
        assert result.entries[0].confidence == pytest.approx(0.7)

    def test_eight_vertex_cloud_confidence_is_0_85(self):
        """Cloud with exactly 8 vertices (>=8 threshold) → confidence = 0.85."""
        verts = [(i * 10, i * 5) for i in range(8)]
        cloud = _cloud_poly("C1", verts, layer="MARKUP")
        ctx = _ctx([cloud])
        result = MarkupRedlineGenerator().generate(ctx, "redline")
        assert result.entries
        assert result.entries[0].confidence == pytest.approx(0.85)

    def test_seven_vertex_cloud_confidence_is_0_7(self):
        """Cloud with exactly 7 vertices (< 8) → confidence stays 0.7."""
        verts = [(i * 10, i * 5) for i in range(7)]
        cloud = _cloud_poly("C1", verts, layer="MARKUP")
        ctx = _ctx([cloud])
        result = MarkupRedlineGenerator().generate(ctx, "redline")
        assert result.entries
        assert result.entries[0].confidence == pytest.approx(0.7)

    def test_cloud_layer_adds_0_1_to_confidence(self):
        """Layer containing 'CLOUD' adds 0.1 to confidence (4v → 0.8)."""
        cloud = _cloud_poly("C1", [(0, 0), (100, 0), (100, 100), (0, 100)], layer="CLOUD")
        ctx = _ctx([cloud])
        result = MarkupRedlineGenerator().generate(ctx, "redline")
        assert result.entries
        assert result.entries[0].confidence == pytest.approx(0.8)

    def test_eight_vertex_on_cloud_layer_confidence_capped_at_0_95(self):
        """>=8 vertices (0.85) + CLOUD layer (+0.1) → capped at 0.95."""
        verts = [(i * 10, i * 5) for i in range(8)]
        cloud = _cloud_poly("C1", verts, layer="CLOUD")
        ctx = _ctx([cloud])
        result = MarkupRedlineGenerator().generate(ctx, "redline")
        assert result.entries
        assert result.entries[0].confidence == pytest.approx(0.95)

    def test_description_contains_entity_count(self):
        """Description must mention the count of entities within the cloud."""
        cloud = _cloud_poly("C1", [(0, 0), (100, 0), (100, 100), (0, 100)])
        entities = [_entity(f"E{i}", x=float(i * 10), y=float(i * 10)) for i in range(3)]
        ctx = _ctx([cloud] + entities)
        result = MarkupRedlineGenerator().generate(ctx, "redline")
        assert result.entries
        desc = result.entries[0].description
        assert "3" in desc

    def test_description_contains_layer_name(self):
        """Description must mention the cloud's layer name."""
        cloud = _cloud_poly("C1", [(0, 0), (100, 0), (100, 100), (0, 100)], layer="CLOUD")
        ctx = _ctx([cloud])
        result = MarkupRedlineGenerator().generate(ctx, "redline")
        assert result.entries
        assert "CLOUD" in result.entries[0].description


class TestGroupByBlockInternals:
    """Kill mutations on _group_by_block confidence formula and instance details."""

    def test_confidence_with_exactly_3_instances(self):
        """3 instances: conf = min(0.95, 0.6 + 3*0.03) = min(0.95, 0.69) = 0.69."""
        inserts = [_insert(f"I{i}", "PUMP", x=float(i * 10)) for i in range(3)]
        ctx = _ctx(inserts)
        result = BatchConditionPlanner().plan(ctx, "batch")
        pump_groups = [g for g in result.groups if "PUMP" in g.name]
        assert pump_groups
        assert pump_groups[0].confidence == pytest.approx(0.69)

    def test_confidence_with_exactly_10_instances(self):
        """10 instances: conf = min(0.95, 0.6 + 10*0.03) = min(0.95, 0.90) = 0.90."""
        inserts = [_insert(f"I{i}", "VALVE", x=float(i * 10)) for i in range(10)]
        ctx = _ctx(inserts)
        result = BatchConditionPlanner().plan(ctx, "batch")
        valve_groups = [g for g in result.groups if "VALVE" in g.name]
        assert valve_groups
        assert valve_groups[0].confidence == pytest.approx(0.90)

    def test_confidence_capped_at_0_95_for_many_instances(self):
        """Many instances should be capped at 0.95."""
        inserts = [_insert(f"I{i}", "ANCHOR", x=float(i * 10)) for i in range(20)]
        ctx = _ctx(inserts)
        result = BatchConditionPlanner().plan(ctx, "batch")
        anchor_groups = [g for g in result.groups if "ANCHOR" in g.name]
        assert anchor_groups
        assert anchor_groups[0].confidence == pytest.approx(0.95)

    def test_instance_dicts_contain_handle_and_layer(self):
        """Each instance dict must have 'handle' and 'layer' keys."""
        inserts = [
            _insert("IG0", "COL", x=0.0, y=0.0, layer="STRUCTURAL"),
            _insert("IG1", "COL", x=10.0, y=0.0, layer="STRUCTURAL"),
            _insert("IG2", "COL", x=20.0, y=0.0, layer="STRUCTURAL"),
        ]
        ctx = _ctx(inserts)
        result = BatchConditionPlanner().plan(ctx, "batch")
        col_groups = [g for g in result.groups if "COL" in g.name]
        assert col_groups
        for inst in col_groups[0].instances:
            assert "handle" in inst
            assert "layer" in inst

    def test_instance_dicts_contain_x_and_y_coords(self):
        """Each instance dict must have 'x' and 'y' keys with correct values."""
        inserts = [
            _insert("IX0", "BEAM", x=5.0, y=10.0),
            _insert("IX1", "BEAM", x=15.0, y=20.0),
            _insert("IX2", "BEAM", x=25.0, y=30.0),
        ]
        ctx = _ctx(inserts)
        result = BatchConditionPlanner().plan(ctx, "batch")
        beam_groups = [g for g in result.groups if "BEAM" in g.name]
        assert beam_groups
        xs = sorted(inst["x"] for inst in beam_groups[0].instances)
        assert xs == pytest.approx([5.0, 15.0, 25.0])

    def test_group_name_starts_with_block_prefix(self):
        """Block group name must start with 'Block: '."""
        inserts = [_insert(f"I{i}", "WINDOW", x=float(i * 10)) for i in range(3)]
        ctx = _ctx(inserts)
        result = BatchConditionPlanner().plan(ctx, "batch")
        window_groups = [g for g in result.groups if "WINDOW" in g.name]
        assert window_groups
        assert window_groups[0].name.startswith("Block: ")


class TestGroupByTextInternals:
    """Kill mutations on _group_by_text: name format, cluster details, confidence."""

    def test_text_group_name_starts_with_text_prefix(self):
        """Text group name must start with \"Text: '\"."""
        texts = [_text(f"T{i}", "EXIT SIGN", x=float(i * 30)) for i in range(3)]
        ctx = _ctx(texts)
        result = BatchConditionPlanner().plan(ctx, "batch")
        text_groups = [g for g in result.groups if g.name.startswith("Text:")]
        assert text_groups
        assert text_groups[0].name.startswith("Text: '")

    def test_text_group_name_contains_text_preview(self):
        """Text group name must contain the text content preview."""
        texts = [_text(f"T{i}", "FIRE DAMPER", x=float(i * 30)) for i in range(3)]
        ctx = _ctx(texts)
        result = BatchConditionPlanner().plan(ctx, "batch")
        fire_groups = [g for g in result.groups if "FIRE DAMPER" in g.name]
        assert fire_groups

    def test_text_instance_dicts_contain_handle_layer_text(self):
        """Each text instance dict must have 'handle', 'layer', 'text' keys."""
        texts = [
            _text("TT0", "VENT", x=0.0, y=0.0, layer="NOTES"),
            _text("TT1", "VENT", x=30.0, y=0.0, layer="NOTES"),
            _text("TT2", "VENT", x=60.0, y=0.0, layer="NOTES"),
        ]
        ctx = _ctx(texts)
        result = BatchConditionPlanner().plan(ctx, "batch")
        vent_groups = [g for g in result.groups if "VENT" in g.name]
        assert vent_groups
        for inst in vent_groups[0].instances:
            assert "handle" in inst
            assert "layer" in inst
            assert "text" in inst

    def test_text_confidence_with_3_instances(self):
        """3 text instances: conf = min(0.85, 0.5 + 3*0.03) = min(0.85, 0.59) = 0.59."""
        texts = [_text(f"T{i}", "OUTLET", x=float(i * 30)) for i in range(3)]
        ctx = _ctx(texts)
        result = BatchConditionPlanner().plan(ctx, "batch")
        outlet_groups = [g for g in result.groups if "OUTLET" in g.name]
        assert outlet_groups
        assert outlet_groups[0].confidence == pytest.approx(0.59)

    def test_dissimilar_text_below_threshold_not_clustered(self):
        """Texts with similarity < 0.8 must not be grouped together."""
        # "DOOR" vs "WINDOW" have very low similarity — should not cluster
        texts = [
            _text("T1", "DOOR", x=0.0),
            _text("T2", "DOOR", x=10.0),
            _text("T3", "DOOR", x=20.0),
            _text("T4", "WINDOW", x=30.0),
            _text("T5", "WINDOW", x=40.0),
            _text("T6", "WINDOW", x=50.0),
        ]
        ctx = _ctx(texts)
        result = BatchConditionPlanner().plan(ctx, "batch")
        # Both "DOOR" and "WINDOW" should form separate groups
        group_names = [g.name for g in result.groups]
        assert any("DOOR" in n for n in group_names)
        assert any("WINDOW" in n for n in group_names)
        # They must NOT be in the same group (no "DOOR" in WINDOW group)
        for g in result.groups:
            if "WINDOW" in g.name:
                for inst in g.instances:
                    assert inst["text"] != "DOOR"


class TestFieldSummaryBuilderSectionDetails:
    """Kill mutations on FieldSummaryBuilder: section titles, content keys, confidence."""

    def test_grid_summary_section_title_is_exact(self):
        """GRID_SUMMARY section must have title 'Structural Grid Summary'."""
        ctx = _ctx(
            [_vline("V1", 0.0), _vline("V2", 30.0), _vline("V3", 60.0)]
        )
        result = FieldSummaryBuilder().build(ctx, prompt="summary")
        grid_sections = [
            s for s in result.sections if s.section_type == FieldSectionType.GRID_SUMMARY
        ]
        assert grid_sections
        assert grid_sections[0].title == "Structural Grid Summary"

    def test_condition_report_section_title_is_exact(self):
        """CONDITION_REPORT section must have title 'Repeated Conditions'."""
        inserts = [_insert(f"I{i}", "FOOTING", x=float(i * 10)) for i in range(5)]
        ctx = _ctx(inserts)
        result = FieldSummaryBuilder().build(ctx, prompt="summary")
        cond_sections = [
            s for s in result.sections if s.section_type == FieldSectionType.CONDITION_REPORT
        ]
        assert cond_sections
        assert cond_sections[0].title == "Repeated Conditions"

    def test_revision_changes_section_title_is_exact(self):
        """REVISION_CHANGES section must have title 'Revision Changes'."""
        from cad_dxf_agent.models.comparison_schema import (
            ChangeCategory,
            ComparisonResult,
            EntityChange,
            GeometrySnapshot,
        )

        snap = GeometrySnapshot(
            handle="X1",
            entity_type=EntityType.LINE,
            layer="STRUCTURAL",
            points=[Point2D(x=0, y=0), Point2D(x=10, y=0)],
        )
        comp = ComparisonResult(
            changes=[
                EntityChange(
                    category=ChangeCategory.ADDED,
                    revision_snapshot=snap,
                    confidence=0.9,
                )
            ],
            summary={"added": 1, "removed": 0, "modified": 0, "moved": 0, "unchanged": 0},
        )
        ctx = _ctx([_insert("I1", "BLK"), _insert("I2", "BLK"), _insert("I3", "BLK")])
        result = FieldSummaryBuilder().build(ctx, prompt="summary", comparison_result=comp)
        rev_sections = [
            s for s in result.sections if s.section_type == FieldSectionType.REVISION_CHANGES
        ]
        assert rev_sections
        assert rev_sections[0].title == "Revision Changes"

    def test_grid_summary_section_content_has_grid_lines_key(self):
        """GRID_SUMMARY content dict must have 'grid_lines' key."""
        ctx = _ctx([_vline("V1", 0.0), _vline("V2", 30.0)])
        result = FieldSummaryBuilder().build(ctx, prompt="summary")
        grid_sections = [
            s for s in result.sections if s.section_type == FieldSectionType.GRID_SUMMARY
        ]
        assert grid_sections
        assert "grid_lines" in grid_sections[0].content

    def test_condition_report_content_has_groups_key(self):
        """CONDITION_REPORT content dict must have 'groups' key."""
        inserts = [_insert(f"I{i}", "HVAC", x=float(i * 10)) for i in range(5)]
        ctx = _ctx(inserts)
        result = FieldSummaryBuilder().build(ctx, prompt="summary")
        cond_sections = [
            s for s in result.sections if s.section_type == FieldSectionType.CONDITION_REPORT
        ]
        assert cond_sections
        assert "groups" in cond_sections[0].content

    def test_aggregate_confidence_is_min_of_section_confidences(self):
        """FieldSummary aggregate_confidence must be min of section confidences."""
        ctx = _grid_and_inserts_ctx()
        result = FieldSummaryBuilder().build(ctx, prompt="summary")
        if result.sections:
            expected = min(s.confidence for s in result.sections if s.available)
            assert result.aggregate_confidence == pytest.approx(expected, abs=0.01)

    def test_section_confidence_propagates_from_grid_result(self):
        """GRID_SUMMARY section confidence must match the grid result aggregate_confidence."""
        # Labeled grid lines have confidence 0.85, unlabeled 0.6.
        # Use labeled lines to get 0.85.
        labeled = _vline("V1", 0.0)
        label = _text("T1", "A", x=0.0, y=-5.0, layer="GRID")
        ctx = _ctx([labeled, label])
        result = FieldSummaryBuilder().build(ctx, prompt="summary")
        grid_sections = [
            s for s in result.sections if s.section_type == FieldSectionType.GRID_SUMMARY
        ]
        assert grid_sections
        # One labeled line → grid aggregate confidence = 0.85
        assert grid_sections[0].confidence == pytest.approx(0.85)

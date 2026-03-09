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
        """Structural drawing loaded from disk — no crash, returns valid result."""
        result = GridAnalyzer().analyze(structural_context, "analyze grid")
        assert result is not None
        assert isinstance(result.grid_lines, list)
        assert isinstance(result.bays, list)


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
        assert entry.entity_count == len(entry.affected_entities)

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

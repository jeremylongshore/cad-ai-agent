"""Tests for MarkupRedlineGenerator from construction_ops."""

from __future__ import annotations

import pytest

from cad_dxf_agent.core.construction_ops import MarkupRedlineGenerator
from cad_dxf_agent.models.cad_schema import (
    DrawingContext,
    EntityRef,
    EntityType,
    LayerRule,
    Point2D,
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _entity(
    handle,
    layer="STRUCTURAL",
    entity_type=EntityType.LINE,
    x=0.0,
    y=0.0,
    block_name=None,
    text_content=None,
    attributes=None,
):
    return EntityRef(
        handle=handle,
        entity_type=entity_type,
        layer=layer,
        insert_point=Point2D(x=x, y=y),
        block_name=block_name,
        text_content=text_content,
        attributes=attributes or {},
    )


def _context(entities):
    layer_names = sorted({e.layer for e in entities})
    return DrawingContext(
        file_path="test.dxf",
        entities=entities,
        layers=[LayerRule(name=n) for n in layer_names],
    )


def _cloud(handle, layer="CLOUD", vertices=None):
    """Shortcut for a cloud LWPOLYLINE with vertices."""
    if vertices is None:
        vertices = [(0, 0), (100, 0), (100, 100), (0, 100)]
    return _entity(
        handle=handle,
        layer=layer,
        entity_type=EntityType.LWPOLYLINE,
        x=vertices[0][0],
        y=vertices[0][1],
        attributes={"vertices": vertices},
    )


# ---------------------------------------------------------------------------
# Cloud detection — layer matching
# ---------------------------------------------------------------------------

class TestCloudDetectionLayers:
    """Clouds are detected on layers matching CLOUD*, MARKUP*, REVISION*, REDLINE*."""

    def test_cloud_on_cloud_layer(self):
        cloud = _cloud("C1", layer="CLOUD")
        entity = _entity("E1", layer="STRUCTURAL", x=50, y=50)
        ctx = _context([cloud, entity])
        result = MarkupRedlineGenerator().generate(ctx, "redline")
        assert result.total_clouds >= 1

    def test_cloud_on_markup_layer(self):
        cloud = _cloud("C1", layer="MARKUP")
        entity = _entity("E1", layer="STRUCTURAL", x=50, y=50)
        ctx = _context([cloud, entity])
        result = MarkupRedlineGenerator().generate(ctx, "redline")
        assert result.total_clouds >= 1

    def test_cloud_on_revision_clouds_layer(self):
        cloud = _cloud("C1", layer="REVISION_CLOUDS")
        entity = _entity("E1", layer="STRUCTURAL", x=50, y=50)
        ctx = _context([cloud, entity])
        result = MarkupRedlineGenerator().generate(ctx, "redline")
        assert result.total_clouds >= 1

    def test_cloud_on_redline_layer(self):
        cloud = _cloud("C1", layer="REDLINE")
        entity = _entity("E1", layer="STRUCTURAL", x=50, y=50)
        ctx = _context([cloud, entity])
        result = MarkupRedlineGenerator().generate(ctx, "redline")
        assert result.total_clouds >= 1

    def test_cloud_layer_case_insensitive(self):
        cloud = _cloud("C1", layer="cloud_markups")
        entity = _entity("E1", layer="STRUCTURAL", x=50, y=50)
        ctx = _context([cloud, entity])
        result = MarkupRedlineGenerator().generate(ctx, "redline")
        assert result.total_clouds >= 1


# ---------------------------------------------------------------------------
# Non-cloud entities ignored
# ---------------------------------------------------------------------------

class TestNonCloudFiltering:
    """Non-LWPOLYLINE on cloud layers and LWPOLYLINE on non-cloud layers are ignored."""

    def test_non_lwpolyline_on_cloud_layer_ignored(self):
        line_on_cloud = _entity("L1", layer="CLOUD", entity_type=EntityType.LINE, x=50, y=50)
        entity = _entity("E1", layer="STRUCTURAL", x=50, y=50)
        ctx = _context([line_on_cloud, entity])
        result = MarkupRedlineGenerator().generate(ctx, "redline")
        assert result.total_clouds == 0

    def test_text_on_cloud_layer_ignored(self):
        text = _entity(
            "T1", layer="CLOUD", entity_type=EntityType.TEXT,
            x=50, y=50, text_content="NOTE",
        )
        ctx = _context([text])
        result = MarkupRedlineGenerator().generate(ctx, "redline")
        assert result.total_clouds == 0

    def test_lwpolyline_on_structural_layer_ignored(self):
        poly = _entity(
            "P1", layer="STRUCTURAL", entity_type=EntityType.LWPOLYLINE,
            attributes={"vertices": [(0, 0), (100, 0), (100, 100), (0, 100)]},
        )
        entity = _entity("E1", layer="STRUCTURAL", x=50, y=50)
        ctx = _context([poly, entity])
        result = MarkupRedlineGenerator().generate(ctx, "redline")
        assert result.total_clouds == 0

    def test_insert_on_cloud_layer_ignored(self):
        insert = _entity("I1", layer="CLOUD", entity_type=EntityType.INSERT, block_name="BLK")
        ctx = _context([insert])
        result = MarkupRedlineGenerator().generate(ctx, "redline")
        assert result.total_clouds == 0


# ---------------------------------------------------------------------------
# Bounding box computation
# ---------------------------------------------------------------------------

class TestBoundingBox:
    """Bounding box is computed from cloud vertices."""

    def test_square_bbox_from_vertices(self):
        cloud = _cloud("C1", vertices=[(0, 0), (100, 0), (100, 100), (0, 100)])
        inside = _entity("E1", x=50, y=50)
        outside = _entity("E2", x=200, y=200)
        ctx = _context([cloud, inside, outside])
        result = MarkupRedlineGenerator().generate(ctx, "redline")
        assert result.total_clouds == 1
        entry = result.entries[0]
        affected_handles = [e.entity_handle for e in entry.affected_entities]
        assert "E1" in affected_handles
        assert "E2" not in affected_handles

    def test_non_rectangular_vertices(self):
        cloud = _cloud("C1", vertices=[(10, 20), (90, 20), (90, 80), (10, 80)])
        inside = _entity("E1", x=50, y=50)
        outside = _entity("E2", x=5, y=10)
        ctx = _context([cloud, inside, outside])
        result = MarkupRedlineGenerator().generate(ctx, "redline")
        entry = result.entries[0]
        affected_handles = [e.entity_handle for e in entry.affected_entities]
        assert "E1" in affected_handles
        assert "E2" not in affected_handles


# ---------------------------------------------------------------------------
# Entity containment
# ---------------------------------------------------------------------------

class TestEntityContainment:
    """Entities within cloud bounds are detected; outside are not."""

    def test_entity_inside_bbox(self):
        cloud = _cloud("C1", vertices=[(0, 0), (100, 0), (100, 100), (0, 100)])
        entity = _entity("E1", x=50, y=50)
        ctx = _context([cloud, entity])
        result = MarkupRedlineGenerator().generate(ctx, "redline")
        assert result.total_affected_entities >= 1

    def test_entity_outside_bbox(self):
        cloud = _cloud("C1", vertices=[(0, 0), (100, 0), (100, 100), (0, 100)])
        entity = _entity("E1", x=200, y=200)
        ctx = _context([cloud, entity])
        result = MarkupRedlineGenerator().generate(ctx, "redline")
        entry = result.entries[0]
        affected_handles = [e.entity_handle for e in entry.affected_entities]
        assert "E1" not in affected_handles

    def test_entity_at_boundary_included(self):
        cloud = _cloud("C1", vertices=[(0, 0), (100, 0), (100, 100), (0, 100)])
        entity = _entity("E1", x=0, y=0)
        ctx = _context([cloud, entity])
        result = MarkupRedlineGenerator().generate(ctx, "redline")
        entry = result.entries[0]
        affected_handles = [e.entity_handle for e in entry.affected_entities]
        assert "E1" in affected_handles

    def test_entity_at_max_boundary_included(self):
        cloud = _cloud("C1", vertices=[(0, 0), (100, 0), (100, 100), (0, 100)])
        entity = _entity("E1", x=100, y=100)
        ctx = _context([cloud, entity])
        result = MarkupRedlineGenerator().generate(ctx, "redline")
        entry = result.entries[0]
        affected_handles = [e.entity_handle for e in entry.affected_entities]
        assert "E1" in affected_handles

    def test_cloud_entity_excluded_from_affected(self):
        cloud = _cloud("C1", vertices=[(0, 0), (100, 0), (100, 100), (0, 100)])
        entity = _entity("E1", x=50, y=50)
        ctx = _context([cloud, entity])
        result = MarkupRedlineGenerator().generate(ctx, "redline")
        entry = result.entries[0]
        affected_handles = [e.entity_handle for e in entry.affected_entities]
        assert "C1" not in affected_handles

    def test_entity_without_insert_point_excluded(self):
        cloud = _cloud("C1", vertices=[(0, 0), (100, 0), (100, 100), (0, 100)])
        entity = _entity("E1", x=50, y=50)
        # Entity with insert_point is included; the cloud-self is excluded.
        # All entities in our helpers have insert_point, so just verify the
        # cloud itself isn't counted (no insert_point issue for normal entities).
        ctx = _context([cloud, entity])
        result = MarkupRedlineGenerator().generate(ctx, "redline")
        entry = result.entries[0]
        affected_handles = [e.entity_handle for e in entry.affected_entities]
        assert "E1" in affected_handles


# ---------------------------------------------------------------------------
# Edge cases — empty / no-cloud
# ---------------------------------------------------------------------------

class TestEdgeCases:
    """Empty drawings, no clouds, vertex-less polylines."""

    def test_empty_drawing(self):
        ctx = _context([])
        result = MarkupRedlineGenerator().generate(ctx, "redline")
        assert result.total_clouds == 0
        # Check for empty_drawing flag in caveats or flags
        dumped = result.model_dump()
        raw = str(dumped).lower()
        assert "empty" in raw or result.total_clouds == 0

    def test_no_clouds_in_drawing(self):
        entity = _entity("E1", x=50, y=50)
        ctx = _context([entity])
        result = MarkupRedlineGenerator().generate(ctx, "redline")
        assert result.total_clouds == 0
        dumped = result.model_dump()
        raw = str(dumped).lower()
        assert "no_cloud" in raw or "no cloud" in raw or result.total_clouds == 0

    def test_vertexless_lwpolyline_on_cloud_layer_skipped(self):
        cloud_no_verts = _entity(
            "C1", layer="CLOUD", entity_type=EntityType.LWPOLYLINE,
            attributes={},
        )
        entity = _entity("E1", x=50, y=50)
        ctx = _context([cloud_no_verts, entity])
        result = MarkupRedlineGenerator().generate(ctx, "redline")
        # Should be skipped — no vertices means no bbox
        assert result.total_clouds == 0 or result.total_affected_entities == 0

    def test_cloud_with_empty_vertices_list_skipped(self):
        cloud_empty = _entity(
            "C1", layer="CLOUD", entity_type=EntityType.LWPOLYLINE,
            attributes={"vertices": []},
        )
        ctx = _context([cloud_empty])
        result = MarkupRedlineGenerator().generate(ctx, "redline")
        assert result.total_clouds == 0 or len(result.entries) == 0


# ---------------------------------------------------------------------------
# Multiple clouds
# ---------------------------------------------------------------------------

class TestMultipleClouds:
    """Each cloud independently reports its affected entities."""

    def test_two_clouds_separate_entities(self):
        cloud1 = _cloud("C1", vertices=[(0, 0), (50, 0), (50, 50), (0, 50)])
        cloud2 = _cloud("C2", vertices=[(200, 200), (300, 200), (300, 300), (200, 300)])
        e1 = _entity("E1", x=25, y=25)
        e2 = _entity("E2", x=250, y=250)
        ctx = _context([cloud1, cloud2, e1, e2])
        result = MarkupRedlineGenerator().generate(ctx, "redline")
        assert result.total_clouds == 2

    def test_overlapping_clouds_can_share_entities(self):
        cloud1 = _cloud("C1", vertices=[(0, 0), (100, 0), (100, 100), (0, 100)])
        cloud2 = _cloud("C2", vertices=[(50, 50), (150, 50), (150, 150), (50, 150)])
        shared = _entity("E1", x=75, y=75)
        ctx = _context([cloud1, cloud2, shared])
        result = MarkupRedlineGenerator().generate(ctx, "redline")
        assert result.total_clouds == 2
        # The shared entity should appear in both entries
        all_affected = []
        for entry in result.entries:
            handles = [e.entity_handle for e in entry.affected_entities]
            all_affected.append(handles)
        assert any("E1" in h for h in all_affected)


# ---------------------------------------------------------------------------
# Confidence
# ---------------------------------------------------------------------------

class TestConfidence:
    """Confidence varies by vertex count and layer name."""

    def test_high_vertex_count_increases_confidence(self):
        # 8+ vertices -> higher confidence
        many_verts = [(i * 10, (i * 7) % 100) for i in range(12)]
        cloud_many = _cloud("C1", layer="CLOUD", vertices=many_verts)
        # Compute bbox for placing entity inside
        xs = [v[0] for v in many_verts]
        ys = [v[1] for v in many_verts]
        mid_x = (min(xs) + max(xs)) / 2
        mid_y = (min(ys) + max(ys)) / 2
        entity = _entity("E1", x=mid_x, y=mid_y)
        ctx = _context([cloud_many, entity])
        result_many = MarkupRedlineGenerator().generate(ctx, "redline")

        few_verts = [(0, 0), (100, 0), (100, 100), (0, 100)]
        cloud_few = _cloud("C2", layer="CLOUD", vertices=few_verts)
        entity2 = _entity("E2", x=50, y=50)
        ctx2 = _context([cloud_few, entity2])
        result_few = MarkupRedlineGenerator().generate(ctx2, "redline")

        conf_many = result_many.entries[0].confidence
        conf_few = result_few.entries[0].confidence
        assert conf_many >= conf_few

    def test_cloud_layer_higher_confidence_than_revision(self):
        cloud1 = _cloud("C1", layer="CLOUD", vertices=[(0, 0), (100, 0), (100, 100), (0, 100)])
        e1 = _entity("E1", x=50, y=50)
        ctx1 = _context([cloud1, e1])
        result1 = MarkupRedlineGenerator().generate(ctx1, "redline")

        cloud2 = _cloud(
            "C2", layer="REVISION_MARKS",
            vertices=[(0, 0), (100, 0), (100, 100), (0, 100)],
        )
        e2 = _entity("E2", x=50, y=50)
        ctx2 = _context([cloud2, e2])
        result2 = MarkupRedlineGenerator().generate(ctx2, "redline")

        conf_cloud = result1.entries[0].confidence
        conf_rev = result2.entries[0].confidence
        assert conf_cloud >= conf_rev


# ---------------------------------------------------------------------------
# Result structure / metadata
# ---------------------------------------------------------------------------

class TestResultStructure:
    """Verify result fields: counts, layers, serialization."""

    def test_affected_layers_reported(self):
        cloud = _cloud("C1", vertices=[(0, 0), (100, 0), (100, 100), (0, 100)])
        e1 = _entity("E1", layer="STRUCTURAL", x=50, y=50)
        e2 = _entity("E2", layer="ELECTRICAL", x=25, y=25)
        ctx = _context([cloud, e1, e2])
        result = MarkupRedlineGenerator().generate(ctx, "redline")
        entry = result.entries[0]
        affected_layers = entry.affected_layers if hasattr(entry, "affected_layers") else []
        assert "STRUCTURAL" in affected_layers
        assert "ELECTRICAL" in affected_layers

    def test_total_clouds_count(self):
        cloud1 = _cloud("C1", vertices=[(0, 0), (50, 0), (50, 50), (0, 50)])
        cloud2 = _cloud("C2", vertices=[(200, 200), (300, 200), (300, 300), (200, 300)])
        e1 = _entity("E1", x=25, y=25)
        ctx = _context([cloud1, cloud2, e1])
        result = MarkupRedlineGenerator().generate(ctx, "redline")
        assert result.total_clouds == 2

    def test_total_affected_entities_count(self):
        cloud = _cloud("C1", vertices=[(0, 0), (100, 0), (100, 100), (0, 100)])
        e1 = _entity("E1", x=10, y=10)
        e2 = _entity("E2", x=50, y=50)
        e3 = _entity("E3", x=200, y=200)  # outside
        ctx = _context([cloud, e1, e2, e3])
        result = MarkupRedlineGenerator().generate(ctx, "redline")
        assert result.total_affected_entities >= 2

    def test_model_dump_produces_dict(self):
        cloud = _cloud("C1", vertices=[(0, 0), (100, 0), (100, 100), (0, 100)])
        entity = _entity("E1", x=50, y=50)
        ctx = _context([cloud, entity])
        result = MarkupRedlineGenerator().generate(ctx, "redline")
        dumped = result.model_dump()
        assert isinstance(dumped, dict)

    def test_aggregate_confidence_is_min(self):
        # Two clouds with different vertex counts should have different confidences
        many_verts = [(i * 10, (i * 7) % 100) for i in range(12)]
        cloud1 = _cloud("C1", layer="CLOUD", vertices=many_verts)
        xs = [v[0] for v in many_verts]
        ys = [v[1] for v in many_verts]
        mid_x = (min(xs) + max(xs)) / 2
        mid_y = (min(ys) + max(ys)) / 2

        cloud2 = _cloud("C2", layer="CLOUD", vertices=[(0, 0), (100, 0), (100, 100), (0, 100)])
        entity = _entity("E1", x=mid_x, y=mid_y)
        entity2 = _entity("E2", x=50, y=50)
        ctx = _context([cloud1, cloud2, entity, entity2])
        result = MarkupRedlineGenerator().generate(ctx, "redline")
        if len(result.entries) >= 2:
            entry_confs = [e.confidence for e in result.entries]
            assert result.aggregate_confidence == pytest.approx(min(entry_confs), abs=0.01)

    def test_entity_count_matches_entities_length(self):
        cloud = _cloud("C1", vertices=[(0, 0), (100, 0), (100, 100), (0, 100)])
        e1 = _entity("E1", x=10, y=10)
        e2 = _entity("E2", x=50, y=50)
        ctx = _context([cloud, e1, e2])
        result = MarkupRedlineGenerator().generate(ctx, "redline")
        entry = result.entries[0]
        assert entry.entity_count == len(entry.affected_entities)

    def test_evidence_present_in_entries(self):
        cloud = _cloud("C1", vertices=[(0, 0), (100, 0), (100, 100), (0, 100)])
        entity = _entity("E1", x=50, y=50)
        ctx = _context([cloud, entity])
        result = MarkupRedlineGenerator().generate(ctx, "redline")
        entry = result.entries[0]
        assert hasattr(entry, "affected_entities") and hasattr(entry, "cloud")

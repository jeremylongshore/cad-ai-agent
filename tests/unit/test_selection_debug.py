"""Tests for selection debug tooling (EPIC-CAD-03.4)."""

import json

from cad_dxf_agent.core.region_associator import RegionAssociator
from cad_dxf_agent.core.selection_debug import (
    build_debug_payload,
    format_debug_text,
)
from cad_dxf_agent.models.cad_schema import (
    DrawingContext,
    EntityRef,
    EntityType,
    LayerRule,
    Point2D,
)
from cad_dxf_agent.models.region_schema import (
    BoundingBox,
    MarkupOverlay,
    MarkupType,
    NormalizedRegion,
    RegionType,
)


def _build_result():
    """Build a typical association result for debug testing."""
    entities = [
        EntityRef(
            handle="A1",
            entity_type=EntityType.LINE,
            layer="STRUCTURAL",
            insert_point=Point2D(x=50, y=50),
        ),
        EntityRef(
            handle="T1",
            entity_type=EntityType.TEXT,
            layer="NOTES",
            insert_point=Point2D(x=60, y=60),
            text_content="Column A-1",
        ),
        EntityRef(
            handle="D1",
            entity_type=EntityType.DIMENSION,
            layer="DIMENSIONS",
            insert_point=Point2D(x=70, y=70),
            text_content="24'-0\"",
        ),
        EntityRef(
            handle="I1",
            entity_type=EntityType.INSERT,
            layer="STRUCTURAL",
            insert_point=Point2D(x=40, y=40),
            block_name="COL_MARK",
        ),
    ]
    context = DrawingContext(
        file_path="test.dxf",
        entities=entities,
        layers=[
            LayerRule(name="STRUCTURAL"),
            LayerRule(name="NOTES"),
            LayerRule(name="DIMENSIONS"),
        ],
    )
    markup = MarkupOverlay(
        markup_id="mk-001",
        markup_type=MarkupType.CIRCLE,
        source_points=[Point2D(x=50, y=50), Point2D(x=80, y=50)],
    )
    region = NormalizedRegion(
        region_id="rgn-test-001",
        source_type=RegionType.MARKUP_MAPPED,
        bounds=BoundingBox(min_x=20, min_y=20, max_x=80, max_y=80),
        center=Point2D(x=50, y=50),
        radius=30.0,
        confidence=0.85,
        source_markup=markup,
        ambiguity_flags=["test_flag"],
    )
    return RegionAssociator().associate(region, context)


class TestBuildDebugPayload:
    def test_payload_is_json_serializable(self):
        result = _build_result()
        payload = build_debug_payload(result)
        # Must not raise
        serialized = json.dumps(payload)
        assert isinstance(serialized, str)

    def test_payload_has_region(self):
        result = _build_result()
        payload = build_debug_payload(result)
        assert "region" in payload
        assert payload["region"]["region_id"] == "rgn-test-001"
        assert payload["region"]["source_type"] == "markup_mapped"

    def test_payload_has_mapped_coordinates(self):
        result = _build_result()
        payload = build_debug_payload(result)
        coords = payload["mapped_coordinates"]
        assert coords["bounds"]["min_x"] == 20
        assert coords["bounds"]["max_x"] == 80
        assert coords["center"]["x"] == 50
        assert coords["center"]["y"] == 50
        assert coords["radius"] == 30.0
        assert coords["area"] > 0

    def test_payload_has_associated_entities(self):
        result = _build_result()
        payload = build_debug_payload(result)
        entities = payload["associated_entities"]
        assert len(entities) >= 1
        first = entities[0]
        assert "handle" in first
        assert "entity_type" in first
        assert "layer" in first
        assert "association_type" in first
        assert "distance" in first
        assert "rank" in first

    def test_payload_has_summary(self):
        result = _build_result()
        payload = build_debug_payload(result)
        summary = payload["summary"]
        assert "entity_count" in summary
        assert "inside_count" in summary
        assert "nearby_count" in summary
        assert "label_count" in summary
        assert "dimension_count" in summary
        assert "layers" in summary
        assert "block_names" in summary

    def test_payload_has_confidence(self):
        result = _build_result()
        payload = build_debug_payload(result)
        conf = payload["confidence"]
        assert "region_confidence" in conf
        assert "association_confidence" in conf
        assert conf["region_confidence"] == 0.85

    def test_payload_has_ambiguity_signals(self):
        result = _build_result()
        payload = build_debug_payload(result)
        assert "test_flag" in payload["ambiguity_signals"]

    def test_source_markup_in_region(self):
        result = _build_result()
        payload = build_debug_payload(result)
        assert payload["region"]["source_markup"]["markup_id"] == "mk-001"
        assert payload["region"]["source_markup"]["markup_type"] == "circle"

    def test_text_content_in_entities(self):
        result = _build_result()
        payload = build_debug_payload(result)
        entities = payload["associated_entities"]
        text_entities = [e for e in entities if "text" in e]
        assert len(text_entities) >= 1

    def test_block_name_in_entities(self):
        result = _build_result()
        payload = build_debug_payload(result)
        entities = payload["associated_entities"]
        block_entities = [e for e in entities if "block_name" in e]
        assert len(block_entities) >= 1


class TestFormatDebugText:
    def test_contains_region_info(self):
        result = _build_result()
        text = format_debug_text(result)
        assert "Selection Debug" in text
        assert "markup_mapped" in text
        assert "Bounds:" in text
        assert "Center:" in text

    def test_contains_confidence(self):
        result = _build_result()
        text = format_debug_text(result)
        assert "Region confidence:" in text
        assert "Association confidence:" in text

    def test_contains_entity_counts(self):
        result = _build_result()
        text = format_debug_text(result)
        assert "Entity count:" in text
        assert "Inside:" in text
        assert "Nearby:" in text
        assert "Labels:" in text

    def test_contains_layers(self):
        result = _build_result()
        text = format_debug_text(result)
        assert "Layers:" in text

    def test_contains_ambiguity(self):
        result = _build_result()
        text = format_debug_text(result)
        assert "test_flag" in text

    def test_contains_top_entities(self):
        result = _build_result()
        text = format_debug_text(result)
        assert "Top entities" in text

    def test_radius_shown_for_circle(self):
        result = _build_result()
        text = format_debug_text(result)
        assert "Radius:" in text


class TestEmptyResult:
    def test_empty_debug_payload(self):
        region = NormalizedRegion(
            source_type=RegionType.BOX_SELECT,
            bounds=BoundingBox(min_x=0, min_y=0, max_x=10, max_y=10),
            center=Point2D(x=5, y=5),
        )
        context = DrawingContext(file_path="empty.dxf")
        result = RegionAssociator().associate(region, context)
        payload = build_debug_payload(result)
        assert payload["summary"]["entity_count"] == 0
        assert payload["confidence"]["association_confidence"] == 0.0

    def test_empty_debug_text(self):
        region = NormalizedRegion(
            source_type=RegionType.BOX_SELECT,
            bounds=BoundingBox(min_x=0, min_y=0, max_x=10, max_y=10),
            center=Point2D(x=5, y=5),
        )
        context = DrawingContext(file_path="empty.dxf")
        result = RegionAssociator().associate(region, context)
        text = format_debug_text(result)
        assert "Entity count: 0" in text
        assert "no_entities_found" in text

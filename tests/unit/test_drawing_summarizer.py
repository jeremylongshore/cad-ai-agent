"""Tests for the drawing summarizer (EPIC-CAD-24)."""

from __future__ import annotations

from cad_dxf_agent.core.drawing_summarizer import (
    DrawingSummary,
    summarize_drawing,
)
from cad_dxf_agent.llm.stage_handlers.summarize_handler import SummarizeHandler
from cad_dxf_agent.models.cad_schema import (
    DrawingContext,
    EntityRef,
    EntityType,
    LayerRule,
    Point2D,
)
from cad_dxf_agent.models.objective_schema import (
    ObjectiveClassification,
    ObjectiveTag,
    RequestClass,
)
from cad_dxf_agent.models.zone_schema import DetectedZone, ZoneDetectionResult

# --- Helpers ---


def _make_entity(
    handle: str,
    entity_type: EntityType = EntityType.LINE,
    layer: str = "0",
    insert_point: Point2D | None = None,
    text_content: str | None = None,
    block_name: str | None = None,
    attributes: dict | None = None,
) -> EntityRef:
    return EntityRef(
        handle=handle,
        entity_type=entity_type,
        layer=layer,
        space="Model",
        insert_point=insert_point,
        text_content=text_content,
        block_name=block_name,
        attributes=attributes or {},
    )


def _make_context(
    entities: list[EntityRef] | None = None,
    layers: list[str] | None = None,
) -> DrawingContext:
    layer_rules = [LayerRule(name=n, color=1) for n in (layers or ["0"])]
    return DrawingContext(
        file_path="test.dxf",
        entities=entities or [],
        layers=layer_rules,
    )


def _make_zone(
    zone_id: str = "z1",
    area: float = 200.0,
    inferred_type: str | None = "room",
) -> DetectedZone:
    return DetectedZone(
        zone_id=zone_id,
        boundary=[
            Point2D(x=0, y=0),
            Point2D(x=20, y=0),
            Point2D(x=20, y=10),
            Point2D(x=0, y=10),
        ],
        area=area,
        perimeter=60.0,
        centroid=Point2D(x=10, y=5),
        inferred_type=inferred_type,
        source_handles=["h1"],
    )


def _make_zones_result(
    zones: list[DetectedZone] | None = None,
) -> ZoneDetectionResult:
    zone_list = zones or []
    return ZoneDetectionResult(
        zones=zone_list,
        total_area=sum(z.area for z in zone_list),
        zone_count=len(zone_list),
        confidence=0.8,
    )


# ===================================================================
# Schema Tests
# ===================================================================


class TestDrawingSummarySchema:
    """Test DrawingSummary model."""

    def test_summary_defaults(self):
        s = DrawingSummary(headline="Test", drawing_type="unknown")
        assert s.entity_count == 0
        assert s.rooms == []
        assert s.plain_description == ""

    def test_summary_with_rooms(self):
        from cad_dxf_agent.core.drawing_summarizer import RoomSummary

        s = DrawingSummary(
            headline="Test",
            drawing_type="Residential",
            rooms=[
                RoomSummary(name="Bedroom", area=150.0, zone_id="z1"),
                RoomSummary(name="Kitchen", area=100.0, zone_id="z2"),
            ],
            room_count=2,
        )
        assert s.room_count == 2
        assert s.rooms[0].name == "Bedroom"


# ===================================================================
# summarize_drawing() Tests
# ===================================================================


class TestSummarizeDrawing:
    """Test the summarize_drawing() function."""

    def test_empty_drawing(self):
        context = _make_context()
        zones = _make_zones_result()
        summary = summarize_drawing(context, zones=zones)

        assert isinstance(summary, DrawingSummary)
        assert summary.entity_count == 0
        assert summary.room_count == 0
        assert "0 entities" in summary.headline

    def test_drawing_with_rooms(self):
        entities = [
            _make_entity("l1", EntityType.LINE, "STRUCTURAL"),
            _make_entity("l2", EntityType.LINE, "STRUCTURAL"),
            _make_entity("t1", EntityType.TEXT, "NOTES",
                         text_content="BEDROOM"),
        ]
        bedroom = _make_zone("z1", area=1500.0, inferred_type="bedroom")
        kitchen = _make_zone("z2", area=1000.0, inferred_type="kitchen")

        context = _make_context(entities=entities, layers=["STRUCTURAL", "NOTES"])
        zones = _make_zones_result([bedroom, kitchen])

        summary = summarize_drawing(context, zones=zones)

        assert summary.room_count == 2
        assert summary.total_area == 2500.0
        assert len(summary.rooms) == 2
        room_names = {r.name for r in summary.rooms}
        assert "Bedroom" in room_names
        assert "Kitchen" in room_names

    def test_headline_includes_drawing_type(self):
        context = _make_context(entities=[
            _make_entity("l1", EntityType.LINE, "STRUCTURAL"),
        ], layers=["STRUCTURAL"])
        zones = _make_zones_result()

        summary = summarize_drawing(context, zones=zones)

        # Should contain the detected family type
        assert len(summary.headline) > 0
        assert summary.drawing_type != ""

    def test_key_features_include_symbols(self):
        entities = [
            _make_entity("d1", EntityType.INSERT, "DOORS",
                         block_name="DOOR_36"),
            _make_entity("d2", EntityType.INSERT, "DOORS",
                         block_name="DOOR_36"),
            _make_entity("w1", EntityType.INSERT, "WINDOWS",
                         block_name="WIN_48"),
        ]
        context = _make_context(entities=entities, layers=["DOORS", "WINDOWS"])
        zones = _make_zones_result()

        summary = summarize_drawing(context, zones=zones)

        # Should mention symbols
        features_text = " ".join(summary.key_features)
        assert "symbol" in features_text.lower() or "DOOR" in features_text

    def test_key_features_include_text_count(self):
        entities = [
            _make_entity("t1", EntityType.TEXT, "NOTES",
                         text_content="Note 1"),
            _make_entity("t2", EntityType.MTEXT, "NOTES",
                         text_content="Note 2"),
        ]
        context = _make_context(entities=entities, layers=["NOTES"])
        zones = _make_zones_result()

        summary = summarize_drawing(context, zones=zones)

        features_text = " ".join(summary.key_features)
        assert "text" in features_text.lower()

    def test_layer_breakdown(self):
        entities = [
            _make_entity("l1", EntityType.LINE, "WALLS"),
            _make_entity("l2", EntityType.LINE, "WALLS"),
            _make_entity("t1", EntityType.TEXT, "NOTES"),
        ]
        context = _make_context(entities=entities, layers=["WALLS", "NOTES"])
        zones = _make_zones_result()

        summary = summarize_drawing(context, zones=zones)

        assert len(summary.layer_breakdown) >= 2
        # Should contain layer names and counts
        breakdown_text = " ".join(summary.layer_breakdown)
        assert "WALLS" in breakdown_text
        assert "NOTES" in breakdown_text

    def test_plain_description_is_readable(self):
        entities = [
            _make_entity("l1", EntityType.LINE, "STRUCTURAL"),
            _make_entity("l2", EntityType.LINE, "STRUCTURAL"),
        ]
        bedroom = _make_zone("z1", area=1500.0, inferred_type="bedroom")
        context = _make_context(entities=entities, layers=["STRUCTURAL"])
        zones = _make_zones_result([bedroom])

        summary = summarize_drawing(context, zones=zones)

        assert len(summary.plain_description) > 0
        assert "entities" in summary.plain_description.lower()
        assert "1500" in summary.plain_description  # area

    def test_no_zones_description(self):
        entities = [_make_entity("l1", EntityType.LINE, "0")]
        context = _make_context(entities=entities)
        zones = _make_zones_result()

        summary = summarize_drawing(context, zones=zones)

        assert "No enclosed spaces" in summary.plain_description

    def test_room_types_in_features(self):
        zones_list = [
            _make_zone("z1", area=1500.0, inferred_type="bedroom"),
            _make_zone("z2", area=1000.0, inferred_type="kitchen"),
            _make_zone("z3", area=500.0, inferred_type="bathroom"),
        ]
        context = _make_context(entities=[
            _make_entity("l1", EntityType.LINE, "0"),
        ])
        zones = _make_zones_result(zones_list)

        summary = summarize_drawing(context, zones=zones)

        features_text = " ".join(summary.key_features)
        assert "bedroom" in features_text.lower()
        assert "kitchen" in features_text.lower()


# ===================================================================
# SummarizeHandler Stage Handler Tests
# ===================================================================


class TestSummarizeHandler:
    """Test the SummarizeHandler stage handler."""

    def test_handler_no_context(self):
        handler = SummarizeHandler()
        classification = ObjectiveClassification(
            request_class=RequestClass.SUMMARIZE,
            objective_tag=ObjectiveTag.CUSTOMER_COMMUNICATION,
            confidence=0.9,
        )
        result = handler.execute(classification, {}, "summarize this")
        assert "No drawing context" in result["summary"]

    def test_handler_with_drawing_context(self):
        handler = SummarizeHandler()
        classification = ObjectiveClassification(
            request_class=RequestClass.SUMMARIZE,
            objective_tag=ObjectiveTag.CUSTOMER_COMMUNICATION,
            confidence=0.9,
        )
        context = _make_context(entities=[
            _make_entity("l1", EntityType.LINE, "STRUCTURAL"),
            _make_entity("l2", EntityType.LINE, "STRUCTURAL"),
        ], layers=["STRUCTURAL"])
        zones = _make_zones_result()

        result = handler.execute(
            classification,
            {"drawing_context": context, "zones": zones},
            "summarize this drawing",
        )

        assert "summary" in result
        assert "drawing_type" in result
        assert "entity_count" in result
        assert result["entity_count"] == 2

    def test_handler_with_zones(self):
        handler = SummarizeHandler()
        classification = ObjectiveClassification(
            request_class=RequestClass.SUMMARIZE,
            objective_tag=ObjectiveTag.CUSTOMER_COMMUNICATION,
            confidence=0.9,
        )
        context = _make_context(entities=[
            _make_entity("l1", EntityType.LINE, "0"),
        ])
        bedroom = _make_zone("z1", area=1500.0, inferred_type="bedroom")
        zones = _make_zones_result([bedroom])

        result = handler.execute(
            classification,
            {"drawing_context": context, "zones": zones},
            "explain this drawing",
        )

        assert result["room_count"] == 1
        assert len(result["rooms"]) == 1
        assert result["rooms"][0]["name"] == "Bedroom"

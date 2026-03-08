"""Tests for the RFI generator (EPIC-CAD-25)."""

from __future__ import annotations

from cad_dxf_agent.core.rfi_generator import (
    _check_dimensions_near_doors,
    _check_empty_layers,
    _check_symbols_without_legend,
    _check_unclosed_boundaries,
    _check_unlabeled_rooms,
    generate_rfi,
)
from cad_dxf_agent.models.cad_schema import (
    DrawingContext,
    EntityRef,
    EntityType,
    LayerRule,
    Point2D,
    TextGeometry,
)
from cad_dxf_agent.models.rfi_schema import (
    RFICategory,
    RFIReport,
    RFISeverity,
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
    text_geometry: TextGeometry | None = None,
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
        text_geometry=text_geometry,
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


class TestRFISchema:
    """Test RFI models."""

    def test_rfi_report_defaults(self):
        report = RFIReport()
        assert report.total_items == 0
        assert report.critical_count == 0
        assert report.items == []

    def test_severity_enum(self):
        assert RFISeverity.CRITICAL == "critical"
        assert RFISeverity.MAJOR == "major"
        assert RFISeverity.MINOR == "minor"

    def test_category_enum(self):
        assert RFICategory.MISSING_DIMENSION == "missing_dimension"
        assert RFICategory.AMBIGUOUS_SYMBOL == "ambiguous_symbol"


# ===================================================================
# Unlabeled Rooms Check
# ===================================================================


class TestUnlabeledRooms:
    """Test detection of rooms without labels."""

    def test_unlabeled_room_flagged(self):
        zone = _make_zone("z1", area=200.0, inferred_type=None)
        context = _make_context()
        zones = _make_zones_result([zone])

        items = _check_unlabeled_rooms(context, zones, 0)
        assert len(items) == 1
        assert items[0].severity == RFISeverity.MAJOR
        assert items[0].category == RFICategory.MISSING_LABEL
        assert items[0].zone_id == "z1"

    def test_labeled_room_not_flagged(self):
        zone = _make_zone("z1", area=200.0, inferred_type="bedroom")
        context = _make_context()
        zones = _make_zones_result([zone])

        items = _check_unlabeled_rooms(context, zones, 0)
        assert len(items) == 0

    def test_multiple_unlabeled_rooms(self):
        zone_list = [
            _make_zone("z1", inferred_type=None),
            _make_zone("z2", inferred_type="kitchen"),
            _make_zone("z3", inferred_type=None),
        ]
        context = _make_context()
        zones = _make_zones_result(zone_list)

        items = _check_unlabeled_rooms(context, zones, 0)
        assert len(items) == 2


# ===================================================================
# Dimensions Near Doors Check
# ===================================================================


class TestDimensionsNearDoors:
    """Test detection of doors without nearby dimensions."""

    def test_door_without_dimension_flagged(self):
        door = _make_entity(
            "d1",
            EntityType.INSERT,
            "DOORS",
            insert_point=Point2D(x=100, y=100),
            block_name="DOOR_36",
        )
        context = _make_context(entities=[door])
        zones = _make_zones_result()

        items = _check_dimensions_near_doors(context, zones, 0)
        assert len(items) == 1
        assert items[0].severity == RFISeverity.CRITICAL
        assert items[0].category == RFICategory.MISSING_DIMENSION

    def test_door_with_nearby_dimension_not_flagged(self):
        door = _make_entity(
            "d1",
            EntityType.INSERT,
            "DOORS",
            insert_point=Point2D(x=100, y=100),
            block_name="DOOR_36",
        )
        dim = _make_entity(
            "dim1",
            EntityType.DIMENSION,
            "DIM",
            insert_point=Point2D(x=105, y=100),
        )
        context = _make_context(entities=[door, dim])
        zones = _make_zones_result()

        items = _check_dimensions_near_doors(context, zones, 0)
        assert len(items) == 0

    def test_non_door_inserts_ignored(self):
        insert = _make_entity(
            "i1",
            EntityType.INSERT,
            "FIXTURES",
            insert_point=Point2D(x=100, y=100),
            block_name="TOILET",
        )
        context = _make_context(entities=[insert])
        zones = _make_zones_result()

        items = _check_dimensions_near_doors(context, zones, 0)
        assert len(items) == 0


# ===================================================================
# Symbols Without Legend Check
# ===================================================================


class TestSymbolsWithoutLegend:
    """Test detection of block symbols without legend entries."""

    def test_symbol_without_legend_flagged(self):
        insert = _make_entity(
            "i1",
            EntityType.INSERT,
            "SYMBOLS",
            block_name="FIRE_EXT_A",
        )
        context = _make_context(entities=[insert])
        zones = _make_zones_result()

        items = _check_symbols_without_legend(context, zones, 0)
        assert len(items) == 1
        assert items[0].category == RFICategory.AMBIGUOUS_SYMBOL
        assert "FIRE_EXT_A" in items[0].question

    def test_symbol_with_legend_not_flagged(self):
        insert = _make_entity(
            "i1",
            EntityType.INSERT,
            "SYMBOLS",
            block_name="OUTLET",
        )
        legend_text = _make_entity(
            "t1",
            EntityType.TEXT,
            "NOTES",
            text_content="OUTLET - Standard 120V duplex receptacle",
        )
        context = _make_context(entities=[insert, legend_text])
        zones = _make_zones_result()

        items = _check_symbols_without_legend(context, zones, 0)
        assert len(items) == 0

    def test_no_inserts_no_findings(self):
        context = _make_context(
            entities=[
                _make_entity("l1", EntityType.LINE, "WALLS"),
            ]
        )
        zones = _make_zones_result()

        items = _check_symbols_without_legend(context, zones, 0)
        assert len(items) == 0


# ===================================================================
# Empty Layers Check
# ===================================================================


class TestEmptyLayers:
    """Test detection of layers without entities."""

    def test_empty_layer_flagged(self):
        entities = [_make_entity("l1", EntityType.LINE, "WALLS")]
        context = _make_context(
            entities=entities,
            layers=["WALLS", "ELECTRICAL", "PLUMBING"],
        )
        zones = _make_zones_result()

        items = _check_empty_layers(context, zones, 0)
        assert len(items) == 2  # ELECTRICAL and PLUMBING
        categories = {i.category for i in items}
        assert RFICategory.INCOMPLETE_SECTION in categories

    def test_all_layers_populated_no_findings(self):
        entities = [
            _make_entity("l1", EntityType.LINE, "WALLS"),
            _make_entity("t1", EntityType.TEXT, "NOTES"),
        ]
        context = _make_context(entities=entities, layers=["WALLS", "NOTES"])
        zones = _make_zones_result()

        items = _check_empty_layers(context, zones, 0)
        assert len(items) == 0

    def test_layer_0_not_flagged(self):
        context = _make_context(entities=[], layers=["0"])
        zones = _make_zones_result()

        items = _check_empty_layers(context, zones, 0)
        assert len(items) == 0


# ===================================================================
# Unclosed Boundaries Check
# ===================================================================


class TestUnclosedBoundaries:
    """Test detection of nearly-closed polylines."""

    def test_nearly_closed_polyline_flagged(self):
        poly = _make_entity(
            "p1",
            EntityType.LWPOLYLINE,
            "WALLS",
            insert_point=Point2D(x=0, y=0),
            attributes={
                "vertices": [[0, 0], [100, 0], [100, 100], [2, 0]],
                "is_closed": False,
            },
        )
        context = _make_context(entities=[poly])
        zones = _make_zones_result()

        items = _check_unclosed_boundaries(context, zones, 0)
        assert len(items) == 1
        assert items[0].severity == RFISeverity.MAJOR

    def test_clearly_open_polyline_not_flagged(self):
        poly = _make_entity(
            "p1",
            EntityType.LWPOLYLINE,
            "WALLS",
            insert_point=Point2D(x=0, y=0),
            attributes={
                "vertices": [[0, 0], [100, 0], [100, 100], [50, 100]],
                "is_closed": False,
            },
        )
        context = _make_context(entities=[poly])
        zones = _make_zones_result()

        items = _check_unclosed_boundaries(context, zones, 0)
        # Gap is ~50 units — too large, not flagged
        assert len(items) == 0

    def test_closed_polyline_not_flagged(self):
        poly = _make_entity(
            "p1",
            EntityType.LWPOLYLINE,
            "WALLS",
            attributes={
                "vertices": [[0, 0], [100, 0], [100, 100], [0, 100]],
                "is_closed": True,
            },
        )
        context = _make_context(entities=[poly])
        zones = _make_zones_result()

        items = _check_unclosed_boundaries(context, zones, 0)
        assert len(items) == 0


# ===================================================================
# Full RFI Generation
# ===================================================================


class TestGenerateRFI:
    """Integration tests for generate_rfi()."""

    def test_empty_drawing(self):
        context = _make_context()
        zones = _make_zones_result()
        report = generate_rfi(context, zones=zones)

        assert isinstance(report, RFIReport)
        assert report.total_items == 0
        assert len(report.checks_run) > 0

    def test_drawing_with_issues(self):
        entities = [
            _make_entity(
                "d1",
                EntityType.INSERT,
                "DOORS",
                insert_point=Point2D(x=50, y=50),
                block_name="DOOR_36",
            ),
            _make_entity("i1", EntityType.INSERT, "FIXTURES", block_name="CUSTOM_WIDGET"),
            _make_entity("l1", EntityType.LINE, "WALLS"),
        ]
        context = _make_context(
            entities=entities,
            layers=["DOORS", "FIXTURES", "WALLS", "ELECTRICAL"],
        )
        zone = _make_zone("z1", inferred_type=None)
        zones = _make_zones_result([zone])

        report = generate_rfi(context, zones=zones)

        assert report.total_items > 0
        # Should have: unlabeled room, door without dimension,
        # symbols without legend, empty ELECTRICAL layer
        assert report.critical_count >= 1  # Door without dimension
        assert report.major_count >= 1  # Unlabeled room

    def test_rfi_ids_sequential(self):
        entities = [
            _make_entity(
                "d1",
                EntityType.INSERT,
                "DOORS",
                insert_point=Point2D(x=50, y=50),
                block_name="DOOR_36",
            ),
            _make_entity(
                "d2",
                EntityType.INSERT,
                "DOORS",
                insert_point=Point2D(x=150, y=50),
                block_name="DR-SINGLE",
            ),
        ]
        context = _make_context(entities=entities)
        zones = _make_zones_result()

        report = generate_rfi(context, zones=zones)

        rfi_ids = [i.rfi_id for i in report.items]
        # All should be unique
        assert len(rfi_ids) == len(set(rfi_ids))

    def test_severity_counts_accurate(self):
        context = _make_context(
            entities=[
                _make_entity(
                    "d1",
                    EntityType.INSERT,
                    "DOORS",
                    insert_point=Point2D(x=50, y=50),
                    block_name="EXIT_DOOR",
                ),
            ],
            layers=["DOORS", "UNUSED_LAYER"],
        )
        zones = _make_zones_result()
        report = generate_rfi(context, zones=zones)

        total = report.critical_count + report.major_count + report.minor_count
        assert total == report.total_items

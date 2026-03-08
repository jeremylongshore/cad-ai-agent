"""Tests for the takeoff engine (EPIC-CAD-23)."""

from __future__ import annotations

from cad_dxf_agent.core.takeoff_engine import (
    _count_by_layer,
    _count_symbols,
    _entity_length,
    _measure_linear,
    _measure_zone_areas,
    generate_takeoff,
)
from cad_dxf_agent.models.cad_schema import (
    DrawingContext,
    EntityRef,
    EntityType,
    LayerRule,
    Point2D,
)
from cad_dxf_agent.models.takeoff_schema import (
    TakeoffCategory,
    TakeoffReport,
    TakeoffReportItem,
)
from cad_dxf_agent.models.zone_schema import DetectedZone, ZoneDetectionResult

# --- Helpers ---


def _make_entity(
    handle: str,
    entity_type: EntityType = EntityType.LINE,
    layer: str = "0",
    insert_point: Point2D | None = None,
    block_name: str | None = None,
    attributes: dict | None = None,
) -> EntityRef:
    return EntityRef(
        handle=handle,
        entity_type=entity_type,
        layer=layer,
        space="Model",
        insert_point=insert_point,
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
    perimeter: float = 60.0,
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
        perimeter=perimeter,
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


class TestTakeoffSchema:
    """Test TakeoffReport and TakeoffReportItem models."""

    def test_report_item_creation(self):
        item = TakeoffReportItem(
            name="DOOR_36",
            category=TakeoffCategory.SYMBOL,
            quantity=5,
            unit="ea",
            source_layer="DOORS",
        )
        assert item.name == "DOOR_36"
        assert item.category == TakeoffCategory.SYMBOL
        assert item.quantity == 5

    def test_report_by_category(self):
        report = TakeoffReport(
            items=[
                TakeoffReportItem(
                    name="Door", category=TakeoffCategory.SYMBOL,
                    quantity=3, unit="ea",
                ),
                TakeoffReportItem(
                    name="Wall", category=TakeoffCategory.LINEAR,
                    quantity=120.0, unit="ft",
                ),
                TakeoffReportItem(
                    name="Door2", category=TakeoffCategory.SYMBOL,
                    quantity=2, unit="ea",
                ),
            ],
            total_items=3,
        )
        by_cat = report.by_category
        assert len(by_cat["symbol"]) == 2
        assert len(by_cat["linear"]) == 1

    def test_report_csv_export(self):
        report = TakeoffReport(
            items=[
                TakeoffReportItem(
                    name="DOOR_36", category=TakeoffCategory.SYMBOL,
                    quantity=5, unit="ea", source_layer="DOORS",
                ),
            ],
            total_items=1,
        )
        rows = report.to_csv_rows()
        assert len(rows) == 2  # header + 1 data row
        assert rows[0][0] == "Category"
        assert rows[1][0] == "symbol"
        assert rows[1][1] == "DOOR_36"

    def test_category_enum_values(self):
        assert TakeoffCategory.SYMBOL == "symbol"
        assert TakeoffCategory.LINEAR == "linear"
        assert TakeoffCategory.AREA == "area"
        assert TakeoffCategory.COUNT == "count"

    def test_empty_report_csv(self):
        report = TakeoffReport()
        rows = report.to_csv_rows()
        assert len(rows) == 1  # header only


# ===================================================================
# Symbol Counting
# ===================================================================


class TestCountSymbols:
    """Test INSERT block counting."""

    def test_count_blocks(self):
        entities = [
            _make_entity("d1", EntityType.INSERT, "DOORS", block_name="DOOR_36"),
            _make_entity("d2", EntityType.INSERT, "DOORS", block_name="DOOR_36"),
            _make_entity("w1", EntityType.INSERT, "WINDOWS", block_name="WIN_48"),
        ]
        context = _make_context(entities=entities)
        items = _count_symbols(context)

        assert len(items) == 2  # DOOR_36 and WIN_48
        door_item = next(i for i in items if i.name == "DOOR_36")
        assert door_item.quantity == 2
        assert door_item.category == TakeoffCategory.SYMBOL
        assert door_item.unit == "ea"

    def test_no_inserts(self):
        entities = [_make_entity("l1", EntityType.LINE, "WALLS")]
        context = _make_context(entities=entities)
        items = _count_symbols(context)
        assert len(items) == 0

    def test_insert_without_block_name_ignored(self):
        entities = [
            _make_entity("i1", EntityType.INSERT, "0"),
        ]
        context = _make_context(entities=entities)
        items = _count_symbols(context)
        assert len(items) == 0


# ===================================================================
# Linear Measurements
# ===================================================================


class TestMeasureLinear:
    """Test linear measurement extraction."""

    def test_line_length(self):
        line = _make_entity(
            "l1", EntityType.LINE, "WALLS",
            insert_point=Point2D(x=0, y=0),
            attributes={"end_point": [30, 40]},
        )
        length = _entity_length(line)
        assert abs(length - 50.0) < 0.01  # 3-4-5 triangle

    def test_polyline_length(self):
        poly = _make_entity(
            "p1", EntityType.LWPOLYLINE, "WALLS",
            attributes={
                "vertices": [[0, 0], [10, 0], [10, 10]],
                "is_closed": False,
            },
        )
        length = _entity_length(poly)
        assert abs(length - 20.0) < 0.01

    def test_closed_polyline_includes_closing_segment(self):
        poly = _make_entity(
            "p1", EntityType.LWPOLYLINE, "WALLS",
            attributes={
                "vertices": [[0, 0], [10, 0], [10, 10], [0, 10]],
                "is_closed": True,
            },
        )
        length = _entity_length(poly)
        assert abs(length - 40.0) < 0.01

    def test_measure_linear_per_layer(self):
        entities = [
            _make_entity("l1", EntityType.LINE, "WALLS",
                         insert_point=Point2D(x=0, y=0),
                         attributes={"end_point": [10, 0]}),
            _make_entity("l2", EntityType.LINE, "WALLS",
                         insert_point=Point2D(x=10, y=0),
                         attributes={"end_point": [20, 0]}),
            _make_entity("l3", EntityType.LINE, "PIPES",
                         insert_point=Point2D(x=0, y=0),
                         attributes={"end_point": [5, 0]}),
        ]
        context = _make_context(entities=entities)
        items = _measure_linear(context)

        walls_item = next(i for i in items if i.source_layer == "WALLS")
        assert walls_item.quantity == 20.0
        assert walls_item.category == TakeoffCategory.LINEAR

        pipes_item = next(i for i in items if i.source_layer == "PIPES")
        assert pipes_item.quantity == 5.0

    def test_non_linear_entities_ignored(self):
        entities = [
            _make_entity("t1", EntityType.TEXT, "NOTES"),
            _make_entity("i1", EntityType.INSERT, "DOORS", block_name="DOOR"),
        ]
        context = _make_context(entities=entities)
        items = _measure_linear(context)
        assert len(items) == 0

    def test_line_without_endpoint_zero_length(self):
        line = _make_entity(
            "l1", EntityType.LINE, "WALLS",
            insert_point=Point2D(x=0, y=0),
        )
        assert _entity_length(line) == 0.0


# ===================================================================
# Zone Area Measurements
# ===================================================================


class TestMeasureZoneAreas:
    """Test zone area extraction."""

    def test_single_zone(self):
        zone = _make_zone(zone_id="z1", area=1500.0, inferred_type="bedroom")
        zones = _make_zones_result([zone])
        items = _measure_zone_areas(zones)

        assert len(items) == 1
        assert items[0].category == TakeoffCategory.AREA
        assert items[0].quantity == 1500.0
        assert items[0].unit == "sq_drawing_units"
        assert items[0].zone_id == "z1"
        assert "Bedroom" in items[0].name

    def test_multiple_zones(self):
        zones_list = [
            _make_zone("z1", area=1500.0, inferred_type="bedroom"),
            _make_zone("z2", area=2000.0, inferred_type="kitchen"),
            _make_zone("z3", area=800.0, inferred_type="bathroom"),
        ]
        zones = _make_zones_result(zones_list)
        items = _measure_zone_areas(zones)

        assert len(items) == 3
        total_area = sum(i.quantity for i in items)
        assert abs(total_area - 4300.0) < 0.01

    def test_no_zones(self):
        zones = _make_zones_result()
        items = _measure_zone_areas(zones)
        assert len(items) == 0

    def test_unknown_zone_type(self):
        zone = _make_zone("z1", area=500.0, inferred_type=None)
        zones = _make_zones_result([zone])
        items = _measure_zone_areas(zones)

        assert len(items) == 1
        assert "Unknown" in items[0].name


# ===================================================================
# Layer Entity Counting
# ===================================================================


class TestCountByLayer:
    """Test per-layer entity counting."""

    def test_counts_non_insert_entities(self):
        entities = [
            _make_entity("l1", EntityType.LINE, "WALLS"),
            _make_entity("l2", EntityType.LINE, "WALLS"),
            _make_entity("l3", EntityType.LINE, "WALLS"),
            _make_entity("t1", EntityType.TEXT, "NOTES"),
            _make_entity("t2", EntityType.TEXT, "NOTES"),
        ]
        context = _make_context(entities=entities)
        items = _count_by_layer(context)

        assert len(items) == 2
        walls_item = next(i for i in items if i.source_layer == "WALLS")
        assert walls_item.quantity == 3

    def test_inserts_excluded(self):
        entities = [
            _make_entity("d1", EntityType.INSERT, "DOORS", block_name="DOOR"),
            _make_entity("d2", EntityType.INSERT, "DOORS", block_name="DOOR"),
        ]
        context = _make_context(entities=entities)
        items = _count_by_layer(context)
        assert len(items) == 0

    def test_single_entity_layer_excluded(self):
        entities = [
            _make_entity("l1", EntityType.LINE, "WALLS"),
        ]
        context = _make_context(entities=entities)
        items = _count_by_layer(context)
        assert len(items) == 0  # Only 1 entity, below threshold of 2


# ===================================================================
# Full Takeoff Generation
# ===================================================================


class TestGenerateTakeoff:
    """Integration tests for generate_takeoff()."""

    def test_empty_drawing(self):
        context = _make_context()
        zones = _make_zones_result()
        report = generate_takeoff(context, zones=zones)

        assert isinstance(report, TakeoffReport)
        assert report.total_items == 0
        assert report.entity_count == 0

    def test_full_drawing(self):
        entities = [
            # Doors (symbols)
            _make_entity("d1", EntityType.INSERT, "DOORS",
                         insert_point=Point2D(x=10, y=0),
                         block_name="DOOR_36"),
            _make_entity("d2", EntityType.INSERT, "DOORS",
                         insert_point=Point2D(x=50, y=0),
                         block_name="DOOR_36"),
            # Walls (lines)
            _make_entity("l1", EntityType.LINE, "WALLS",
                         insert_point=Point2D(x=0, y=0),
                         attributes={"end_point": [100, 0]}),
            _make_entity("l2", EntityType.LINE, "WALLS",
                         insert_point=Point2D(x=100, y=0),
                         attributes={"end_point": [100, 50]}),
            # Text
            _make_entity("t1", EntityType.TEXT, "NOTES"),
            _make_entity("t2", EntityType.TEXT, "NOTES"),
        ]
        bedroom = _make_zone("z1", area=5000.0, inferred_type="bedroom")
        kitchen = _make_zone("z2", area=3000.0, inferred_type="kitchen")

        context = _make_context(entities=entities, layers=["DOORS", "WALLS", "NOTES"])
        zones = _make_zones_result([bedroom, kitchen])

        report = generate_takeoff(context, zones=zones)

        assert report.total_items > 0
        assert report.zone_count == 2
        assert report.entity_count == 6

        by_cat = report.by_category
        assert "symbol" in by_cat
        assert "linear" in by_cat
        assert "area" in by_cat

        # Check symbol count
        door_items = [i for i in by_cat["symbol"] if i.name == "DOOR_36"]
        assert len(door_items) == 1
        assert door_items[0].quantity == 2

        # Check linear measurement
        wall_items = [i for i in by_cat["linear"] if i.source_layer == "WALLS"]
        assert len(wall_items) == 1
        expected_length = 100.0 + 50.0
        assert abs(wall_items[0].quantity - expected_length) < 0.01

        # Check area measurements
        assert len(by_cat["area"]) == 2

    def test_csv_export_integration(self):
        entities = [
            _make_entity("d1", EntityType.INSERT, "DOORS",
                         insert_point=Point2D(x=10, y=0),
                         block_name="DOOR_36"),
        ]
        context = _make_context(entities=entities)
        zones = _make_zones_result()

        report = generate_takeoff(context, zones=zones)
        rows = report.to_csv_rows()

        assert len(rows) >= 2  # header + at least 1 data row
        assert rows[0] == ["Category", "Name", "Quantity", "Unit",
                           "Layer", "Zone", "Notes"]

    def test_polyline_linear_measurement(self):
        entities = [
            _make_entity("p1", EntityType.LWPOLYLINE, "WALLS",
                         attributes={
                             "vertices": [[0, 0], [100, 0], [100, 50]],
                             "is_closed": False,
                         }),
        ]
        context = _make_context(entities=entities)
        zones = _make_zones_result()

        report = generate_takeoff(context, zones=zones)
        linear_items = [i for i in report.items
                        if i.category == TakeoffCategory.LINEAR]

        assert len(linear_items) == 1
        assert abs(linear_items[0].quantity - 150.0) < 0.01

    def test_diagonal_line_measurement(self):
        entities = [
            _make_entity("l1", EntityType.LINE, "WALLS",
                         insert_point=Point2D(x=0, y=0),
                         attributes={"end_point": [30, 40]}),
        ]
        context = _make_context(entities=entities)
        zones = _make_zones_result()

        report = generate_takeoff(context, zones=zones)
        linear_items = [i for i in report.items
                        if i.category == TakeoffCategory.LINEAR]

        assert len(linear_items) == 1
        assert abs(linear_items[0].quantity - 50.0) < 0.01  # 3-4-5

    def test_report_entity_handles_limited(self):
        """Verify entity handle lists are bounded to prevent huge payloads."""
        entities = [
            _make_entity(f"l{i}", EntityType.LINE, "WALLS",
                         insert_point=Point2D(x=i * 10, y=0),
                         attributes={"end_point": [i * 10 + 10, 0]})
            for i in range(50)
        ]
        context = _make_context(entities=entities)
        zones = _make_zones_result()

        report = generate_takeoff(context, zones=zones)

        for item in report.items:
            assert len(item.entity_handles) <= 50

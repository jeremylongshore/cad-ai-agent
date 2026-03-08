"""Tests for compliance rules engine (EPIC-CAD-21)."""

from __future__ import annotations

import pytest

from cad_dxf_agent.models.cad_schema import (
    DrawingContext,
    EntityRef,
    EntityType,
    LayerRule,
    Point2D,
)
from cad_dxf_agent.models.compliance_schema import (
    ADA_PROFILE,
    BUILTIN_PROFILES,
    IBC_PROFILE,
    RESIDENTIAL_PROFILE,
    ComplianceCategory,
    ComplianceFinding,
    ComplianceProfile,
    ComplianceReport,
    ComplianceSeverity,
    ComplianceThresholds,
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
    zone_id: str = "test-zone",
    area: float = 200.0,
    inferred_type: str | None = "room",
    boundary: list[Point2D] | None = None,
    source_handles: list[str] | None = None,
) -> DetectedZone:
    if boundary is None:
        # Default 10x20 rectangle
        boundary = [
            Point2D(x=0, y=0),
            Point2D(x=20, y=0),
            Point2D(x=20, y=10),
            Point2D(x=0, y=10),
        ]
    return DetectedZone(
        zone_id=zone_id,
        boundary=boundary,
        area=area,
        perimeter=sum(
            (
                (boundary[i].x - boundary[(i + 1) % len(boundary)].x) ** 2
                + (boundary[i].y - boundary[(i + 1) % len(boundary)].y) ** 2
            )
            ** 0.5
            for i in range(len(boundary))
        ),
        centroid=Point2D(
            x=sum(p.x for p in boundary) / len(boundary),
            y=sum(p.y for p in boundary) / len(boundary),
        ),
        inferred_type=inferred_type,
        source_handles=source_handles or ["h1"],
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


class TestComplianceSchema:
    """Test Pydantic models for compliance."""

    def test_finding_model(self):
        f = ComplianceFinding(
            rule_id="TEST-001",
            category=ComplianceCategory.DOOR,
            severity=ComplianceSeverity.VIOLATION,
            title="Test finding",
            description="A test finding",
        )
        assert f.rule_id == "TEST-001"
        assert f.category == ComplianceCategory.DOOR
        assert f.severity == ComplianceSeverity.VIOLATION
        assert f.entity_handles == []
        assert f.measured_value is None

    def test_finding_with_evidence(self):
        f = ComplianceFinding(
            rule_id="TEST-002",
            category=ComplianceCategory.ROOM_SIZE,
            severity=ComplianceSeverity.WARNING,
            title="Room too small",
            description="Room area is 50",
            zone_id="z1",
            entity_handles=["h1", "h2"],
            measured_value=50.0,
            required_value=70.0,
            unit="sq_ft",
        )
        assert f.zone_id == "z1"
        assert len(f.entity_handles) == 2
        assert f.measured_value == 50.0

    def test_report_score_all_pass(self):
        r = ComplianceReport(
            profile_name="test",
            pass_count=10,
            violation_count=0,
            warning_count=0,
        )
        assert r.passed is True
        assert r.score == 100

    def test_report_score_with_violations(self):
        r = ComplianceReport(
            profile_name="test",
            pass_count=7,
            violation_count=2,
            warning_count=1,
        )
        assert r.passed is False
        assert r.score == 70

    def test_report_score_empty(self):
        r = ComplianceReport(profile_name="test")
        assert r.score == 0

    def test_thresholds_defaults(self):
        t = ComplianceThresholds()
        assert t.min_door_width == 36.0
        assert t.min_hallway_width == 44.0
        assert t.min_habitable_room_area == 70.0 * 144

    def test_profile_creation(self):
        p = ComplianceProfile(
            name="custom",
            description="Custom profile",
            thresholds=ComplianceThresholds(min_door_width=32.0),
        )
        assert p.name == "custom"
        assert p.thresholds.min_door_width == 32.0

    def test_builtin_profiles_exist(self):
        assert "ada" in BUILTIN_PROFILES
        assert "ibc-2021" in BUILTIN_PROFILES
        assert "residential" in BUILTIN_PROFILES

    def test_ada_profile_categories(self):
        assert ComplianceCategory.ACCESSIBILITY in ADA_PROFILE.enabled_categories
        assert ComplianceCategory.DOOR in ADA_PROFILE.enabled_categories

    def test_ibc_profile_all_categories(self):
        assert len(IBC_PROFILE.enabled_categories) == len(ComplianceCategory)

    def test_residential_profile_thresholds(self):
        assert RESIDENTIAL_PROFILE.thresholds.min_door_width == 32.0
        assert RESIDENTIAL_PROFILE.thresholds.min_hallway_width == 36.0

    def test_severity_enum_values(self):
        assert ComplianceSeverity.VIOLATION == "violation"
        assert ComplianceSeverity.WARNING == "warning"
        assert ComplianceSeverity.PASS == "pass"  # noqa: S105

    def test_category_enum_values(self):
        assert ComplianceCategory.ACCESSIBILITY == "accessibility"
        assert ComplianceCategory.EGRESS == "egress"
        assert ComplianceCategory.DOOR == "door"


# ===================================================================
# check_compliance() Public API
# ===================================================================


class TestCheckCompliance:
    """Test the check_compliance() public API."""

    def test_empty_drawing(self):
        from cad_dxf_agent.core.compliance_rules import check_compliance

        context = _make_context()
        zones = _make_zones_result()
        report = check_compliance(context, "ada", zones=zones)

        assert isinstance(report, ComplianceReport)
        assert report.profile_name == "ada"
        assert len(report.checks_run) > 0

    def test_unknown_profile_raises(self):
        from cad_dxf_agent.core.compliance_rules import check_compliance

        context = _make_context()
        with pytest.raises(ValueError, match="Unknown profile"):
            check_compliance(context, "nonexistent")

    def test_custom_profile_object(self):
        from cad_dxf_agent.core.compliance_rules import check_compliance

        profile = ComplianceProfile(
            name="my-profile",
            description="Custom",
            enabled_categories=[ComplianceCategory.DOOR],
        )
        context = _make_context()
        zones = _make_zones_result()
        report = check_compliance(context, profile, zones=zones)
        assert report.profile_name == "my-profile"

    def test_report_counts_accurate(self):
        from cad_dxf_agent.core.compliance_rules import check_compliance

        # Drawing with a small bedroom zone and a door
        door = _make_entity(
            "d1",
            EntityType.INSERT,
            "DOORS",
            insert_point=Point2D(x=5, y=5),
            block_name="DOOR_36",
            attributes={"width": 36.0},
        )
        context = _make_context(
            entities=[door],
            layers=["DOORS"],
        )
        bedroom = _make_zone(
            zone_id="z1",
            area=5000.0,  # Below 70*144 = 10080 threshold
            inferred_type="bedroom",
        )
        zones = _make_zones_result([bedroom])

        report = check_compliance(context, "ibc-2021", zones=zones)

        total = report.violation_count + report.warning_count + report.pass_count
        assert total == len(report.findings)

    def test_checks_run_matches_enabled_categories(self):
        from cad_dxf_agent.core.compliance_rules import check_compliance

        profile = ComplianceProfile(
            name="door-only",
            description="Only door checks",
            enabled_categories=[ComplianceCategory.DOOR],
        )
        context = _make_context()
        zones = _make_zones_result()
        report = check_compliance(context, profile, zones=zones)

        # Only door-related checks should run
        for check_name in report.checks_run:
            assert "door" in check_name


# ===================================================================
# Door Width Checks
# ===================================================================


class TestDoorWidthChecks:
    """Test door width compliance checks."""

    def test_door_width_violation(self):
        from cad_dxf_agent.core.compliance_rules import _check_door_widths

        door = _make_entity(
            "d1",
            EntityType.INSERT,
            "DOORS",
            insert_point=Point2D(x=10, y=10),
            block_name="DOOR_30",
            attributes={"width": 30.0},
        )
        context = _make_context(entities=[door])
        thresholds = ComplianceThresholds(min_door_width=36.0)
        zones = _make_zones_result()

        findings = _check_door_widths(context, zones, None, thresholds)

        violations = [f for f in findings if f.severity == ComplianceSeverity.VIOLATION]
        assert len(violations) == 1
        assert violations[0].rule_id == "DOOR-WIDTH-001"
        assert violations[0].measured_value == 30.0
        assert violations[0].required_value == 36.0
        assert "d1" in violations[0].entity_handles

    def test_door_width_pass(self):
        from cad_dxf_agent.core.compliance_rules import _check_door_widths

        door = _make_entity(
            "d1",
            EntityType.INSERT,
            "DOORS",
            insert_point=Point2D(x=10, y=10),
            block_name="DOOR_36",
            attributes={"width": 36.0},
        )
        context = _make_context(entities=[door])
        thresholds = ComplianceThresholds(min_door_width=36.0)
        zones = _make_zones_result()

        findings = _check_door_widths(context, zones, None, thresholds)

        passes = [f for f in findings if f.severity == ComplianceSeverity.PASS]
        assert len(passes) == 1

    def test_no_doors_no_findings(self):
        from cad_dxf_agent.core.compliance_rules import _check_door_widths

        line = _make_entity("l1", EntityType.LINE, "WALLS")
        context = _make_context(entities=[line])
        thresholds = ComplianceThresholds()
        zones = _make_zones_result()

        findings = _check_door_widths(context, zones, None, thresholds)
        assert len(findings) == 0

    def test_door_without_width_attribute(self):
        from cad_dxf_agent.core.compliance_rules import _check_door_widths

        door = _make_entity(
            "d1",
            EntityType.INSERT,
            "DOORS",
            insert_point=Point2D(x=10, y=10),
            block_name="DOOR_STANDARD",
            attributes={},
        )
        context = _make_context(entities=[door])
        thresholds = ComplianceThresholds()
        zones = _make_zones_result()

        findings = _check_door_widths(context, zones, None, thresholds)
        # No width extracted = no finding
        assert len(findings) == 0

    def test_door_width_from_x_scale(self):
        from cad_dxf_agent.core.compliance_rules import _check_door_widths

        door = _make_entity(
            "d1",
            EntityType.INSERT,
            "DOORS",
            insert_point=Point2D(x=10, y=10),
            block_name="DR-1",
            attributes={"x_scale": 32.0},
        )
        context = _make_context(entities=[door])
        thresholds = ComplianceThresholds(min_door_width=36.0)
        zones = _make_zones_result()

        findings = _check_door_widths(context, zones, None, thresholds)
        violations = [f for f in findings if f.severity == ComplianceSeverity.VIOLATION]
        assert len(violations) == 1
        assert violations[0].measured_value == 32.0

    def test_multiple_doors_mixed(self):
        from cad_dxf_agent.core.compliance_rules import _check_door_widths

        doors = [
            _make_entity(
                "d1",
                EntityType.INSERT,
                "DOORS",
                insert_point=Point2D(x=0, y=0),
                block_name="DOOR_30",
                attributes={"width": 30.0},
            ),
            _make_entity(
                "d2",
                EntityType.INSERT,
                "DOORS",
                insert_point=Point2D(x=50, y=0),
                block_name="DOOR_36",
                attributes={"width": 36.0},
            ),
            _make_entity(
                "d3",
                EntityType.INSERT,
                "DOORS",
                insert_point=Point2D(x=100, y=0),
                block_name="ENTRY_42",
                attributes={"width": 42.0},
            ),
        ]
        context = _make_context(entities=doors)
        thresholds = ComplianceThresholds(min_door_width=36.0)
        zones = _make_zones_result()

        findings = _check_door_widths(context, zones, None, thresholds)
        violations = [f for f in findings if f.severity == ComplianceSeverity.VIOLATION]
        passes = [f for f in findings if f.severity == ComplianceSeverity.PASS]
        assert len(violations) == 1  # DOOR_30
        assert len(passes) == 2  # DOOR_36, ENTRY_42


# ===================================================================
# Hallway Width Checks
# ===================================================================


class TestHallwayWidthChecks:
    """Test corridor width compliance checks."""

    def test_narrow_hallway_violation(self):
        from cad_dxf_agent.core.compliance_rules import _check_hallway_widths

        # Hallway that is 30 wide (below 44 minimum)
        hallway = _make_zone(
            zone_id="hall1",
            area=900.0,
            inferred_type="hallway",
            boundary=[
                Point2D(x=0, y=0),
                Point2D(x=30, y=0),  # 30 wide
                Point2D(x=30, y=300),
                Point2D(x=0, y=300),
            ],
        )
        context = _make_context()
        zones = _make_zones_result([hallway])
        thresholds = ComplianceThresholds(min_hallway_width=44.0)

        findings = _check_hallway_widths(context, zones, None, thresholds)
        violations = [f for f in findings if f.severity == ComplianceSeverity.VIOLATION]
        assert len(violations) == 1
        assert violations[0].measured_value == 30.0

    def test_wide_hallway_pass(self):
        from cad_dxf_agent.core.compliance_rules import _check_hallway_widths

        hallway = _make_zone(
            zone_id="hall2",
            area=4800.0,
            inferred_type="hallway",
            boundary=[
                Point2D(x=0, y=0),
                Point2D(x=48, y=0),  # 48 wide
                Point2D(x=48, y=100),
                Point2D(x=0, y=100),
            ],
        )
        context = _make_context()
        zones = _make_zones_result([hallway])
        thresholds = ComplianceThresholds(min_hallway_width=44.0)

        findings = _check_hallway_widths(context, zones, None, thresholds)
        passes = [f for f in findings if f.severity == ComplianceSeverity.PASS]
        assert len(passes) == 1

    def test_non_hallway_zones_ignored(self):
        from cad_dxf_agent.core.compliance_rules import _check_hallway_widths

        room = _make_zone(zone_id="r1", area=200.0, inferred_type="bedroom")
        context = _make_context()
        zones = _make_zones_result([room])
        thresholds = ComplianceThresholds()

        findings = _check_hallway_widths(context, zones, None, thresholds)
        assert len(findings) == 0


# ===================================================================
# Room Area Checks
# ===================================================================


class TestRoomAreaChecks:
    """Test room area compliance checks."""

    def test_small_bedroom_violation(self):
        from cad_dxf_agent.core.compliance_rules import _check_room_areas

        bedroom = _make_zone(
            zone_id="bed1",
            area=5000.0,  # Below 70*144=10080 threshold
            inferred_type="bedroom",
        )
        context = _make_context()
        zones = _make_zones_result([bedroom])
        thresholds = ComplianceThresholds()

        findings = _check_room_areas(context, zones, None, thresholds)
        violations = [f for f in findings if f.severity == ComplianceSeverity.VIOLATION]
        assert len(violations) == 1
        assert violations[0].rule_id == "ROOM-AREA-001"
        assert "Bedroom" in violations[0].title

    def test_adequate_bedroom_pass(self):
        from cad_dxf_agent.core.compliance_rules import _check_room_areas

        bedroom = _make_zone(
            zone_id="bed2",
            area=15000.0,  # Above 10080 threshold
            inferred_type="bedroom",
        )
        context = _make_context()
        zones = _make_zones_result([bedroom])
        thresholds = ComplianceThresholds()

        findings = _check_room_areas(context, zones, None, thresholds)
        passes = [f for f in findings if f.severity == ComplianceSeverity.PASS]
        assert len(passes) == 1

    def test_small_bathroom_warning(self):
        from cad_dxf_agent.core.compliance_rules import _check_room_areas

        bathroom = _make_zone(
            zone_id="bath1",
            area=2000.0,  # Below 35*144=5040
            inferred_type="bathroom",
        )
        context = _make_context()
        zones = _make_zones_result([bathroom])
        thresholds = ComplianceThresholds()

        findings = _check_room_areas(context, zones, None, thresholds)
        warnings = [f for f in findings if f.severity == ComplianceSeverity.WARNING]
        assert len(warnings) == 1
        assert warnings[0].rule_id == "ROOM-AREA-002"

    def test_hallway_not_checked_for_area(self):
        from cad_dxf_agent.core.compliance_rules import _check_room_areas

        hallway = _make_zone(
            zone_id="h1",
            area=500.0,
            inferred_type="hallway",
        )
        context = _make_context()
        zones = _make_zones_result([hallway])
        thresholds = ComplianceThresholds()

        findings = _check_room_areas(context, zones, None, thresholds)
        assert len(findings) == 0

    def test_multiple_room_types(self):
        from cad_dxf_agent.core.compliance_rules import _check_room_areas

        rooms = [
            _make_zone("r1", area=5000.0, inferred_type="bedroom"),  # violation
            _make_zone("r2", area=15000.0, inferred_type="living_room"),  # pass
            _make_zone("r3", area=8000.0, inferred_type="kitchen"),  # violation
        ]
        context = _make_context()
        zones = _make_zones_result(rooms)
        thresholds = ComplianceThresholds()

        findings = _check_room_areas(context, zones, None, thresholds)
        violations = [f for f in findings if f.severity == ComplianceSeverity.VIOLATION]
        passes = [f for f in findings if f.severity == ComplianceSeverity.PASS]
        assert len(violations) == 2
        assert len(passes) == 1


# ===================================================================
# Egress Checks
# ===================================================================


class TestEgressChecks:
    """Test room egress compliance checks."""

    def test_room_with_nearby_door_passes(self):
        from cad_dxf_agent.core.compliance_rules import _check_egress

        door = _make_entity(
            "d1",
            EntityType.INSERT,
            "DOORS",
            insert_point=Point2D(x=5, y=5),
            block_name="DOOR_36",
        )
        room = _make_zone(
            zone_id="r1",
            area=200.0,
            inferred_type="bedroom",
            boundary=[
                Point2D(x=0, y=0),
                Point2D(x=20, y=0),
                Point2D(x=20, y=10),
                Point2D(x=0, y=10),
            ],
        )
        context = _make_context(entities=[door])
        zones = _make_zones_result([room])
        thresholds = ComplianceThresholds()

        findings = _check_egress(context, zones, None, thresholds)
        passes = [f for f in findings if f.severity == ComplianceSeverity.PASS]
        assert len(passes) == 1
        assert passes[0].rule_id == "EGRESS-001"

    def test_room_without_egress_warning(self):
        from cad_dxf_agent.core.compliance_rules import _check_egress

        # Room with no doors or windows anywhere
        room = _make_zone(
            zone_id="r1",
            area=200.0,
            inferred_type="bedroom",
            boundary=[
                Point2D(x=0, y=0),
                Point2D(x=20, y=0),
                Point2D(x=20, y=10),
                Point2D(x=0, y=10),
            ],
        )
        context = _make_context(entities=[])
        zones = _make_zones_result([room])
        thresholds = ComplianceThresholds()

        findings = _check_egress(context, zones, None, thresholds)
        warnings = [f for f in findings if f.severity == ComplianceSeverity.WARNING]
        assert len(warnings) == 1
        assert "lack egress" in warnings[0].title

    def test_room_with_nearby_window_passes(self):
        from cad_dxf_agent.core.compliance_rules import _check_egress

        window = _make_entity(
            "w1",
            EntityType.INSERT,
            "WINDOWS",
            insert_point=Point2D(x=10, y=0),
            block_name="WINDOW_36x48",
        )
        room = _make_zone(
            zone_id="r1",
            area=200.0,
            inferred_type="bedroom",
            boundary=[
                Point2D(x=0, y=0),
                Point2D(x=20, y=0),
                Point2D(x=20, y=10),
                Point2D(x=0, y=10),
            ],
        )
        context = _make_context(entities=[window])
        zones = _make_zones_result([room])
        thresholds = ComplianceThresholds()

        findings = _check_egress(context, zones, None, thresholds)
        passes = [f for f in findings if f.severity == ComplianceSeverity.PASS]
        assert len(passes) == 1

    def test_hallway_not_checked_for_egress(self):
        from cad_dxf_agent.core.compliance_rules import _check_egress

        hallway = _make_zone("h1", area=500.0, inferred_type="hallway")
        context = _make_context()
        zones = _make_zones_result([hallway])
        thresholds = ComplianceThresholds()

        findings = _check_egress(context, zones, None, thresholds)
        assert len(findings) == 0


# ===================================================================
# Door Count Checks
# ===================================================================


class TestDoorCountChecks:
    """Test door count compliance checks."""

    def test_rooms_without_doors_warning(self):
        from cad_dxf_agent.core.compliance_rules import _check_door_count

        room = _make_zone("r1", area=200.0, inferred_type="bedroom")
        context = _make_context()
        zones = _make_zones_result([room])
        thresholds = ComplianceThresholds()

        findings = _check_door_count(context, zones, None, thresholds)
        warnings = [f for f in findings if f.severity == ComplianceSeverity.WARNING]
        assert len(warnings) == 1
        assert "No doors detected" in warnings[0].title

    def test_rooms_with_doors_pass(self):
        from cad_dxf_agent.core.compliance_rules import _check_door_count

        door = _make_entity(
            "d1",
            EntityType.INSERT,
            "DOORS",
            insert_point=Point2D(x=10, y=10),
            block_name="DOOR_36",
        )
        room = _make_zone("r1", area=200.0, inferred_type="bedroom")
        context = _make_context(entities=[door])
        zones = _make_zones_result([room])
        thresholds = ComplianceThresholds()

        findings = _check_door_count(context, zones, None, thresholds)
        passes = [f for f in findings if f.severity == ComplianceSeverity.PASS]
        assert len(passes) == 1
        assert "1 door(s)" in passes[0].title

    def test_no_zones_no_check(self):
        from cad_dxf_agent.core.compliance_rules import _check_door_count

        context = _make_context()
        zones = _make_zones_result()
        thresholds = ComplianceThresholds()

        findings = _check_door_count(context, zones, None, thresholds)
        assert len(findings) == 0


# ===================================================================
# Dead-End Corridor Checks
# ===================================================================


class TestDeadEndCorridorChecks:
    """Test dead-end corridor compliance checks."""

    def test_long_corridor_warning(self):
        from cad_dxf_agent.core.compliance_rules import _check_dead_end_corridors

        # Corridor 300 units long (exceeds 240 default limit)
        hallway = _make_zone(
            zone_id="hall1",
            area=9000.0,
            inferred_type="hallway",
            boundary=[
                Point2D(x=0, y=0),
                Point2D(x=30, y=0),
                Point2D(x=30, y=300),
                Point2D(x=0, y=300),
            ],
        )
        context = _make_context()
        zones = _make_zones_result([hallway])
        thresholds = ComplianceThresholds(max_dead_end_corridor_length=240.0)

        findings = _check_dead_end_corridors(context, zones, None, thresholds)
        warnings = [f for f in findings if f.severity == ComplianceSeverity.WARNING]
        assert len(warnings) == 1
        assert warnings[0].measured_value == 300.0

    def test_short_corridor_no_warning(self):
        from cad_dxf_agent.core.compliance_rules import _check_dead_end_corridors

        hallway = _make_zone(
            zone_id="hall2",
            area=4800.0,
            inferred_type="hallway",
            boundary=[
                Point2D(x=0, y=0),
                Point2D(x=48, y=0),
                Point2D(x=48, y=100),
                Point2D(x=0, y=100),
            ],
        )
        context = _make_context()
        zones = _make_zones_result([hallway])
        thresholds = ComplianceThresholds(max_dead_end_corridor_length=240.0)

        findings = _check_dead_end_corridors(context, zones, None, thresholds)
        assert len(findings) == 0


# ===================================================================
# Block Detection Helpers
# ===================================================================


class TestBlockDetection:
    """Test door/window block detection from INSERT names."""

    def test_detect_door_blocks(self):
        from cad_dxf_agent.core.compliance_rules import (
            _DOOR_PATTERNS,
            _find_blocks_by_pattern,
        )

        entities = [
            _make_entity("d1", EntityType.INSERT, "DOORS", block_name="DOOR_36"),
            _make_entity("d2", EntityType.INSERT, "DOORS", block_name="DR-SINGLE"),
            _make_entity("d3", EntityType.INSERT, "DOORS", block_name="ENTRY_MAIN"),
            _make_entity("w1", EntityType.INSERT, "WINDOWS", block_name="WINDOW_48"),
            _make_entity("l1", EntityType.LINE, "WALLS"),
        ]
        context = _make_context(entities=entities)

        doors = _find_blocks_by_pattern(context, _DOOR_PATTERNS)
        assert len(doors) == 3
        handles = {d.handle for d in doors}
        assert handles == {"d1", "d2", "d3"}

    def test_detect_window_blocks(self):
        from cad_dxf_agent.core.compliance_rules import (
            _WINDOW_PATTERNS,
            _find_blocks_by_pattern,
        )

        entities = [
            _make_entity("w1", EntityType.INSERT, "WINDOWS", block_name="WINDOW_36x48"),
            _make_entity("w2", EntityType.INSERT, "WINDOWS", block_name="WNDW-DH"),
            _make_entity("w3", EntityType.INSERT, "WINDOWS", block_name="GLAZING_PANEL"),
            _make_entity("d1", EntityType.INSERT, "DOORS", block_name="DOOR_36"),
        ]
        context = _make_context(entities=entities)

        windows = _find_blocks_by_pattern(context, _WINDOW_PATTERNS)
        assert len(windows) == 3

    def test_non_insert_entities_ignored(self):
        from cad_dxf_agent.core.compliance_rules import (
            _DOOR_PATTERNS,
            _find_blocks_by_pattern,
        )

        entities = [
            _make_entity("t1", EntityType.TEXT, "NOTES", text_content="DOOR SCHEDULE"),
            _make_entity("l1", EntityType.LINE, "WALLS"),
        ]
        context = _make_context(entities=entities)

        doors = _find_blocks_by_pattern(context, _DOOR_PATTERNS)
        assert len(doors) == 0


# ===================================================================
# Helper Function Tests
# ===================================================================


class TestHelperFunctions:
    """Test internal helper functions."""

    def test_extract_dimension_from_width_attribute(self):
        from cad_dxf_agent.core.compliance_rules import (
            _extract_dimension_from_attributes,
        )

        assert _extract_dimension_from_attributes({"width": 36.0}) == 36.0
        assert _extract_dimension_from_attributes({"WIDTH": 42}) == 42.0
        assert _extract_dimension_from_attributes({"w": "30"}) == 30.0

    def test_extract_dimension_from_x_scale(self):
        from cad_dxf_agent.core.compliance_rules import (
            _extract_dimension_from_attributes,
        )

        assert _extract_dimension_from_attributes({"x_scale": 36.0}) == 36.0

    def test_extract_dimension_none_when_missing(self):
        from cad_dxf_agent.core.compliance_rules import (
            _extract_dimension_from_attributes,
        )

        assert _extract_dimension_from_attributes({}) is None
        assert _extract_dimension_from_attributes({"color": "red"}) is None

    def test_zone_min_dimension(self):
        from cad_dxf_agent.core.compliance_rules import _zone_min_dimension

        zone = _make_zone(
            boundary=[
                Point2D(x=0, y=0),
                Point2D(x=48, y=0),
                Point2D(x=48, y=100),
                Point2D(x=0, y=100),
            ],
        )
        assert _zone_min_dimension(zone) == 48.0

    def test_zone_max_dimension(self):
        from cad_dxf_agent.core.compliance_rules import _zone_max_dimension

        zone = _make_zone(
            boundary=[
                Point2D(x=0, y=0),
                Point2D(x=48, y=0),
                Point2D(x=48, y=100),
                Point2D(x=0, y=100),
            ],
        )
        assert _zone_max_dimension(zone) == 100.0


# ===================================================================
# Integration: Full Profile Checks
# ===================================================================


class TestFullProfileChecks:
    """Integration tests running full profiles on realistic scenarios."""

    def test_ada_profile_on_non_compliant_drawing(self):
        from cad_dxf_agent.core.compliance_rules import check_compliance

        # Small door + narrow hallway
        door = _make_entity(
            "d1",
            EntityType.INSERT,
            "DOORS",
            insert_point=Point2D(x=10, y=10),
            block_name="DOOR_30",
            attributes={"width": 30.0},
        )
        hallway = _make_zone(
            zone_id="hall1",
            area=9000.0,
            inferred_type="hallway",
            boundary=[
                Point2D(x=0, y=0),
                Point2D(x=30, y=0),
                Point2D(x=30, y=300),
                Point2D(x=0, y=300),
            ],
        )
        context = _make_context(entities=[door], layers=["DOORS"])
        zones = _make_zones_result([hallway])

        report = check_compliance(context, "ada", zones=zones)

        assert report.profile_name == "ada"
        assert report.violation_count >= 1  # narrow door
        assert not report.passed

    def test_ibc_profile_on_compliant_drawing(self):
        from cad_dxf_agent.core.compliance_rules import check_compliance

        # Good door + good hallway + good room
        door = _make_entity(
            "d1",
            EntityType.INSERT,
            "DOORS",
            insert_point=Point2D(x=10, y=5),
            block_name="DOOR_36",
            attributes={"width": 36.0},
        )
        hallway = _make_zone(
            zone_id="hall1",
            area=5000.0,
            inferred_type="hallway",
            boundary=[
                Point2D(x=0, y=0),
                Point2D(x=50, y=0),
                Point2D(x=50, y=100),
                Point2D(x=0, y=100),
            ],
        )
        bedroom = _make_zone(
            zone_id="bed1",
            area=15000.0,  # Above 10080 threshold
            inferred_type="bedroom",
            boundary=[
                Point2D(x=0, y=0),
                Point2D(x=150, y=0),
                Point2D(x=150, y=100),
                Point2D(x=0, y=100),
            ],
        )
        context = _make_context(entities=[door], layers=["DOORS"])
        zones = _make_zones_result([hallway, bedroom])

        report = check_compliance(context, "ibc-2021", zones=zones)

        assert report.violation_count == 0
        assert report.pass_count > 0
        assert report.passed
        assert report.score > 0

    def test_residential_profile(self):
        from cad_dxf_agent.core.compliance_rules import check_compliance

        door = _make_entity(
            "d1",
            EntityType.INSERT,
            "DOORS",
            insert_point=Point2D(x=10, y=10),
            block_name="DOOR_32",
            attributes={"width": 32.0},
        )
        context = _make_context(entities=[door], layers=["DOORS"])
        room = _make_zone("r1", area=15000.0, inferred_type="bedroom")
        zones = _make_zones_result([room])

        report = check_compliance(context, "residential", zones=zones)

        assert report.profile_name == "residential"
        # 32" door meets residential 32" minimum
        door_violations = [
            f
            for f in report.findings
            if f.rule_id == "DOOR-WIDTH-001" and f.severity == ComplianceSeverity.VIOLATION
        ]
        assert len(door_violations) == 0

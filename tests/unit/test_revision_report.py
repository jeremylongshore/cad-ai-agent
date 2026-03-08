"""Tests for the revision report (EPIC-CAD-26)."""

from __future__ import annotations

from cad_dxf_agent.core.comparison.changelog import ChangeLog, ChangeLogEntry
from cad_dxf_agent.core.revision_report import (
    RevisionReport,
    ZoneDelta,
    _build_headline,
    _categorize_changes,
    _compute_zone_deltas,
    generate_revision_report,
)
from cad_dxf_agent.models.cad_schema import (
    DrawingContext,
    EntityRef,
    LayerRule,
    Point2D,
)
from cad_dxf_agent.models.zone_schema import DetectedZone, ZoneDetectionResult

# --- Helpers ---


def _make_context(
    entities: list[EntityRef] | None = None,
    layers: list[str] | None = None,
    file_path: str = "test.dxf",
) -> DrawingContext:
    layer_rules = [LayerRule(name=n, color=1) for n in (layers or ["0"])]
    return DrawingContext(
        file_path=file_path,
        entities=entities or [],
        layers=layer_rules,
    )


def _make_entry(
    category: str = "modified",
    entity_type: str = "LINE",
    layer: str = "WALLS",
    description: str = "Wall moved 10 units",
) -> ChangeLogEntry:
    return ChangeLogEntry(
        category=category,
        entity_type=entity_type,
        layer=layer,
        description=description,
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


class TestRevisionReportSchema:
    """Test RevisionReport model."""

    def test_report_defaults(self):
        r = RevisionReport(headline="Test")
        assert r.total_changes == 0
        assert r.zone_deltas == []
        assert r.area_change == 0.0

    def test_zone_delta_model(self):
        d = ZoneDelta(
            zone_type="bedroom",
            status="added",
            new_area=1500.0,
            area_change=1500.0,
        )
        assert d.zone_type == "bedroom"
        assert d.status == "added"


# ===================================================================
# Change Categorization
# ===================================================================


class TestCategorizeChanges:
    """Test changelog entry categorization."""

    def test_group_by_category(self):
        entries = [
            _make_entry("added", description="New wall"),
            _make_entry("added", description="New door"),
            _make_entry("modified", description="Wall moved"),
            _make_entry("removed", description="Old fixture removed"),
        ]
        categories = _categorize_changes(entries)

        cat_dict = {c.category: c for c in categories}
        assert cat_dict["added"].count == 2
        assert cat_dict["modified"].count == 1
        assert cat_dict["removed"].count == 1

    def test_layers_affected(self):
        entries = [
            _make_entry("modified", layer="WALLS"),
            _make_entry("modified", layer="DOORS"),
            _make_entry("modified", layer="WALLS"),
        ]
        categories = _categorize_changes(entries)

        assert len(categories) == 1
        assert set(categories[0].layers_affected) == {"WALLS", "DOORS"}

    def test_empty_changelog(self):
        categories = _categorize_changes([])
        assert len(categories) == 0

    def test_sample_descriptions_limited(self):
        entries = [_make_entry("added", description=f"Item {i}") for i in range(10)]
        categories = _categorize_changes(entries)

        assert len(categories[0].sample_descriptions) <= 5


# ===================================================================
# Zone Delta Computation
# ===================================================================


class TestComputeZoneDeltas:
    """Test zone-based area delta computation."""

    def test_room_added(self):
        old_zones = _make_zones_result()
        new_zones = _make_zones_result(
            [
                _make_zone("z1", area=1500.0, inferred_type="bedroom"),
            ]
        )
        deltas = _compute_zone_deltas(old_zones, new_zones)

        assert len(deltas) == 1
        assert deltas[0].status == "added"
        assert deltas[0].zone_type == "bedroom"
        assert deltas[0].new_area == 1500.0

    def test_room_removed(self):
        old_zones = _make_zones_result(
            [
                _make_zone("z1", area=1500.0, inferred_type="bedroom"),
            ]
        )
        new_zones = _make_zones_result()
        deltas = _compute_zone_deltas(old_zones, new_zones)

        assert len(deltas) == 1
        assert deltas[0].status == "removed"
        assert deltas[0].old_area == 1500.0
        assert deltas[0].area_change == -1500.0

    def test_room_resized(self):
        old_zones = _make_zones_result(
            [
                _make_zone("z1", area=1000.0, inferred_type="kitchen"),
            ]
        )
        new_zones = _make_zones_result(
            [
                _make_zone("z1", area=1200.0, inferred_type="kitchen"),
            ]
        )
        deltas = _compute_zone_deltas(old_zones, new_zones)

        assert len(deltas) == 1
        assert deltas[0].status == "resized"
        assert deltas[0].area_change == 200.0

    def test_room_unchanged(self):
        zone = _make_zone("z1", area=1000.0, inferred_type="bedroom")
        old_zones = _make_zones_result([zone])
        new_zones = _make_zones_result([zone])
        deltas = _compute_zone_deltas(old_zones, new_zones)

        assert len(deltas) == 1
        assert deltas[0].status == "unchanged"

    def test_mixed_changes(self):
        old_zones = _make_zones_result(
            [
                _make_zone("z1", area=1000.0, inferred_type="bedroom"),
                _make_zone("z2", area=500.0, inferred_type="bathroom"),
            ]
        )
        new_zones = _make_zones_result(
            [
                _make_zone("z1", area=1200.0, inferred_type="bedroom"),
                _make_zone("z3", area=800.0, inferred_type="kitchen"),
            ]
        )
        deltas = _compute_zone_deltas(old_zones, new_zones)

        statuses = {d.status for d in deltas}
        assert "resized" in statuses  # bedroom
        assert "removed" in statuses  # bathroom
        assert "added" in statuses  # kitchen


# ===================================================================
# Headline Building
# ===================================================================


class TestBuildHeadline:
    """Test headline generation."""

    def test_headline_with_changes(self):
        changelog = ChangeLog(entries=[_make_entry(), _make_entry()])
        deltas = [
            ZoneDelta(zone_type="bedroom", status="added", new_area=1500.0, area_change=1500.0),
        ]
        headline = _build_headline(changelog, deltas, 1500.0)

        assert "2 change(s)" in headline
        assert "1 room(s) added" in headline
        assert "+1500" in headline

    def test_headline_no_changes(self):
        changelog = ChangeLog(entries=[])
        headline = _build_headline(changelog, [], 0.0)
        assert "0 change(s)" in headline

    def test_headline_negative_area(self):
        changelog = ChangeLog(entries=[_make_entry()])
        deltas = [
            ZoneDelta(zone_type="closet", status="removed", old_area=50.0, area_change=-50.0),
        ]
        headline = _build_headline(changelog, deltas, -50.0)
        assert "-50" in headline


# ===================================================================
# Full Report Generation
# ===================================================================


class TestGenerateRevisionReport:
    """Integration tests for generate_revision_report()."""

    def test_empty_drawings(self):
        master = _make_context(file_path="master.dxf")
        revision = _make_context(file_path="revision.dxf")
        changelog = ChangeLog(entries=[])
        master_zones = _make_zones_result()
        revision_zones = _make_zones_result()

        report = generate_revision_report(
            master,
            revision,
            changelog,
            master_zones=master_zones,
            revision_zones=revision_zones,
        )

        assert isinstance(report, RevisionReport)
        assert report.total_changes == 0
        assert report.area_change == 0.0
        assert "0 change(s)" in report.headline

    def test_report_with_changes_and_zones(self):
        master = _make_context(file_path="master.dxf")
        revision = _make_context(file_path="revision.dxf")
        changelog = ChangeLog(
            entries=[
                _make_entry("added", description="New wall added"),
                _make_entry("modified", description="Wall moved"),
                _make_entry("removed", description="Old fixture removed"),
            ]
        )
        master_zones = _make_zones_result(
            [
                _make_zone("z1", area=1000.0, inferred_type="bedroom"),
            ]
        )
        revision_zones = _make_zones_result(
            [
                _make_zone("z1", area=1200.0, inferred_type="bedroom"),
                _make_zone("z2", area=800.0, inferred_type="kitchen"),
            ]
        )

        report = generate_revision_report(
            master,
            revision,
            changelog,
            master_zones=master_zones,
            revision_zones=revision_zones,
        )

        assert report.total_changes == 3
        assert len(report.change_categories) == 3
        assert report.old_zone_count == 1
        assert report.new_zone_count == 2
        assert report.area_change == 1000.0  # +200 resize + 800 new

    def test_plain_summary_readable(self):
        master = _make_context(file_path="floor_plan_v1.dxf")
        revision = _make_context(file_path="floor_plan_v2.dxf")
        changelog = ChangeLog(
            entries=[
                _make_entry("added", description="New bedroom wall"),
            ]
        )
        master_zones = _make_zones_result()
        revision_zones = _make_zones_result(
            [
                _make_zone("z1", area=1500.0, inferred_type="bedroom"),
            ]
        )

        report = generate_revision_report(
            master,
            revision,
            changelog,
            master_zones=master_zones,
            revision_zones=revision_zones,
        )

        assert "floor_plan_v1.dxf" in report.plain_summary
        assert "1 change(s)" in report.plain_summary
        assert "added" in report.plain_summary.lower()

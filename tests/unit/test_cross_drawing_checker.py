"""Tests for the cross-drawing consistency checker (EPIC-CAD-22)."""

from __future__ import annotations

from cad_dxf_agent.models.cad_schema import (
    DrawingContext,
    EntityRef,
    EntityType,
    LayerRule,
    Point2D,
)
from cad_dxf_agent.models.consistency_schema import (
    ConsistencyCategory,
    ConsistencyFinding,
    ConsistencyReport,
    ConsistencySeverity,
    SheetInfo,
)

# --- Helpers ---


def _make_context(
    file_path: str = "sheet.dxf",
    entities: list[EntityRef] | None = None,
    layers: list[str] | None = None,
    blocks: list[str] | None = None,
) -> DrawingContext:
    layer_rules = [LayerRule(name=n, color=1) for n in (layers or ["0"])]
    return DrawingContext(
        file_path=file_path,
        entities=entities or [],
        layers=layer_rules,
        blocks=blocks or [],
    )


def _text_entity(
    handle: str,
    text: str,
    layer: str = "LABELS",
    x: float = 0.0,
    y: float = 0.0,
) -> EntityRef:
    return EntityRef(
        handle=handle,
        entity_type=EntityType.TEXT,
        layer=layer,
        insert_point=Point2D(x=x, y=y),
        text_content=text,
    )


def _insert_entity(
    handle: str,
    block_name: str,
    layer: str = "0",
    x: float = 0.0,
    y: float = 0.0,
) -> EntityRef:
    return EntityRef(
        handle=handle,
        entity_type=EntityType.INSERT,
        layer=layer,
        insert_point=Point2D(x=x, y=y),
        block_name=block_name,
    )


def _line_entity(
    handle: str,
    layer: str = "WALLS",
    x: float = 0.0,
    y: float = 0.0,
) -> EntityRef:
    return EntityRef(
        handle=handle,
        entity_type=EntityType.LINE,
        layer=layer,
        insert_point=Point2D(x=x, y=y),
    )


# ===================================================================
# Schema Tests
# ===================================================================


class TestConsistencySchemas:
    """Test Pydantic models for consistency checking."""

    def test_sheet_info_defaults(self):
        info = SheetInfo(file_path="test.dxf", family="unknown")
        assert info.layer_count == 0
        assert info.room_labels == []
        assert info.block_names == []

    def test_consistency_finding_minimal(self):
        f = ConsistencyFinding(
            finding_id="abc123",
            category=ConsistencyCategory.ROOM_LABELS,
            severity=ConsistencySeverity.WARNING,
            title="Label mismatch",
            description="Room labels differ",
            sheet_a="a.dxf",
        )
        assert f.sheet_b is None
        assert f.entity_handles == []

    def test_report_passed_no_errors(self):
        report = ConsistencyReport(
            sheets=[SheetInfo(file_path="a.dxf", family="unknown")],
            error_count=0,
            warning_count=2,
        )
        assert report.passed is True

    def test_report_failed_with_errors(self):
        report = ConsistencyReport(
            sheets=[SheetInfo(file_path="a.dxf", family="unknown")],
            error_count=1,
        )
        assert report.passed is False

    def test_report_score_perfect(self):
        report = ConsistencyReport(
            sheets=[SheetInfo(file_path="a.dxf", family="unknown")],
        )
        assert report.score == 1.0

    def test_report_score_with_errors(self):
        report = ConsistencyReport(
            sheets=[SheetInfo(file_path="a.dxf", family="unknown")],
            error_count=3,
            warning_count=4,
        )
        # 1.0 - (3*0.2 + 4*0.05) = 1.0 - 0.8 = 0.2
        assert abs(report.score - 0.2) < 0.01

    def test_report_score_clamped_to_zero(self):
        report = ConsistencyReport(
            sheets=[SheetInfo(file_path="a.dxf", family="unknown")],
            error_count=10,
        )
        assert report.score == 0.0


# ===================================================================
# Room Label Consistency
# ===================================================================


class TestRoomLabelConsistency:
    """Test room label comparison across sheets."""

    def test_matching_labels_no_findings(self):
        from cad_dxf_agent.core.cross_drawing_checker import check_consistency

        sheet_a = _make_context(
            "floor_plan.dxf",
            entities=[
                _text_entity("h1", "Kitchen"),
                _text_entity("h2", "Bedroom"),
            ],
        )
        sheet_b = _make_context(
            "electrical.dxf",
            entities=[
                _text_entity("h3", "Kitchen"),
                _text_entity("h4", "Bedroom"),
            ],
        )
        report = check_consistency([sheet_a, sheet_b])

        label_findings = [
            f
            for f in report.findings
            if f.category == ConsistencyCategory.ROOM_LABELS
            and f.severity == ConsistencySeverity.WARNING
        ]
        assert len(label_findings) == 0

    def test_mismatched_labels_flagged(self):
        from cad_dxf_agent.core.cross_drawing_checker import check_consistency

        sheet_a = _make_context(
            "floor_plan.dxf",
            entities=[
                _text_entity("h1", "Kitchen"),
                _text_entity("h2", "Bedroom"),
            ],
        )
        sheet_b = _make_context(
            "electrical.dxf",
            entities=[
                _text_entity("h3", "Kitchen"),
                # No "Bedroom" label
            ],
        )
        report = check_consistency([sheet_a, sheet_b])

        label_warnings = [
            f
            for f in report.findings
            if f.category == ConsistencyCategory.ROOM_LABELS
            and f.severity == ConsistencySeverity.WARNING
        ]
        assert len(label_warnings) >= 1
        assert any("bedroom" in f.description.lower() for f in label_warnings)

    def test_no_labels_info_finding(self):
        from cad_dxf_agent.core.cross_drawing_checker import check_consistency

        sheet_a = _make_context("plan.dxf", entities=[_line_entity("h1")])
        sheet_b = _make_context("elec.dxf", entities=[_line_entity("h2")])
        report = check_consistency([sheet_a, sheet_b])

        info_findings = [
            f
            for f in report.findings
            if f.category == ConsistencyCategory.ROOM_LABELS
            and f.severity == ConsistencySeverity.INFO
        ]
        # At least one info about no room labels found
        assert len(info_findings) >= 1


# ===================================================================
# Layer Naming Consistency
# ===================================================================


class TestLayerNamingConsistency:
    """Test layer naming convention checks."""

    def test_case_mismatch_flagged(self):
        from cad_dxf_agent.core.cross_drawing_checker import check_consistency

        sheet_a = _make_context(
            "plan.dxf",
            layers=["WALLS", "DOORS", "ELECTRICAL"],
        )
        sheet_b = _make_context(
            "elec.dxf",
            layers=["walls", "DOORS", "ELECTRICAL"],
        )
        report = check_consistency([sheet_a, sheet_b])

        layer_findings = [
            f for f in report.findings if f.category == ConsistencyCategory.LAYER_NAMING
        ]
        assert len(layer_findings) >= 1
        assert any("case" in f.description.lower() for f in layer_findings)

    def test_unique_layers_noted(self):
        from cad_dxf_agent.core.cross_drawing_checker import check_consistency

        sheet_a = _make_context(
            "plan.dxf",
            layers=["WALLS", "DOORS", "PLUMBING"],
        )
        sheet_b = _make_context(
            "elec.dxf",
            layers=["WALLS", "ELECTRICAL"],
        )
        report = check_consistency([sheet_a, sheet_b])

        layer_findings = [
            f for f in report.findings if f.category == ConsistencyCategory.LAYER_NAMING
        ]
        # Should note layers unique to one sheet
        assert len(layer_findings) >= 1


# ===================================================================
# Block Consistency
# ===================================================================


class TestBlockConsistency:
    """Test block usage consistency across sheets."""

    def test_shared_blocks_no_findings(self):
        from cad_dxf_agent.core.cross_drawing_checker import check_consistency

        sheet_a = _make_context(
            "plan.dxf",
            entities=[_insert_entity("h1", "DOOR_36")],
            blocks=["DOOR_36"],
        )
        sheet_b = _make_context(
            "elec.dxf",
            entities=[_insert_entity("h2", "DOOR_36")],
            blocks=["DOOR_36"],
        )
        report = check_consistency([sheet_a, sheet_b])

        block_warnings = [
            f
            for f in report.findings
            if f.category == ConsistencyCategory.BLOCK_CONSISTENCY
            and f.severity == ConsistencySeverity.WARNING
        ]
        assert len(block_warnings) == 0

    def test_missing_block_flagged(self):
        from cad_dxf_agent.core.cross_drawing_checker import check_consistency

        # 3 sheets, block in 2 of 3 (>50%)
        sheet_a = _make_context(
            "plan.dxf",
            entities=[_insert_entity("h1", "DOOR_36")],
            blocks=["DOOR_36"],
        )
        sheet_b = _make_context(
            "elec.dxf",
            entities=[_insert_entity("h2", "DOOR_36")],
            blocks=["DOOR_36"],
        )
        sheet_c = _make_context(
            "rcp.dxf",
            entities=[_line_entity("h3")],
            blocks=[],
        )
        report = check_consistency([sheet_a, sheet_b, sheet_c])

        block_findings = [
            f for f in report.findings if f.category == ConsistencyCategory.BLOCK_CONSISTENCY
        ]
        assert len(block_findings) >= 1


# ===================================================================
# Entity Count Consistency
# ===================================================================


class TestEntityCountConsistency:
    """Test entity count anomaly detection."""

    def test_empty_sheet_flagged(self):
        from cad_dxf_agent.core.cross_drawing_checker import check_consistency

        sheet_a = _make_context(
            "plan.dxf",
            entities=[_line_entity(f"h{i}") for i in range(10)],
        )
        sheet_b = _make_context("empty.dxf", entities=[])
        report = check_consistency([sheet_a, sheet_b])

        count_errors = [
            f
            for f in report.findings
            if f.category == ConsistencyCategory.ENTITY_COUNTS
            and f.severity == ConsistencySeverity.ERROR
        ]
        assert len(count_errors) >= 1

    def test_similar_counts_no_findings(self):
        from cad_dxf_agent.core.cross_drawing_checker import check_consistency

        sheet_a = _make_context(
            "plan.dxf",
            entities=[_line_entity(f"h{i}") for i in range(10)],
        )
        sheet_b = _make_context(
            "elec.dxf",
            entities=[_line_entity(f"h{i}", layer="ELEC") for i in range(8)],
        )
        report = check_consistency([sheet_a, sheet_b])

        count_warnings = [
            f
            for f in report.findings
            if f.category == ConsistencyCategory.ENTITY_COUNTS
            and f.severity == ConsistencySeverity.WARNING
        ]
        assert len(count_warnings) == 0


# ===================================================================
# Coordinate Alignment
# ===================================================================


class TestCoordinateAlignment:
    """Test coordinate system alignment checks."""

    def test_overlapping_drawings_ok(self):
        from cad_dxf_agent.core.cross_drawing_checker import check_consistency

        sheet_a = _make_context(
            "plan.dxf",
            entities=[
                _line_entity("h1", x=0, y=0),
                _line_entity("h2", x=100, y=100),
            ],
        )
        sheet_b = _make_context(
            "elec.dxf",
            entities=[
                _line_entity("h3", x=10, y=10),
                _line_entity("h4", x=90, y=90),
            ],
        )
        report = check_consistency([sheet_a, sheet_b])

        coord_errors = [
            f
            for f in report.findings
            if f.category == ConsistencyCategory.COORDINATE_ALIGNMENT
            and f.severity == ConsistencySeverity.ERROR
        ]
        assert len(coord_errors) == 0

    def test_non_overlapping_flagged(self):
        from cad_dxf_agent.core.cross_drawing_checker import check_consistency

        sheet_a = _make_context(
            "plan.dxf",
            entities=[
                _line_entity("h1", x=0, y=0),
                _line_entity("h2", x=100, y=100),
            ],
        )
        sheet_b = _make_context(
            "elec.dxf",
            entities=[
                _line_entity("h3", x=10000, y=10000),
                _line_entity("h4", x=10100, y=10100),
            ],
        )
        report = check_consistency([sheet_a, sheet_b])

        coord_findings = [
            f for f in report.findings if f.category == ConsistencyCategory.COORDINATE_ALIGNMENT
        ]
        assert len(coord_findings) >= 1


# ===================================================================
# Full Integration
# ===================================================================


class TestCheckConsistencyIntegration:
    """Integration tests for the full check_consistency() pipeline."""

    def test_single_sheet_minimal(self):
        from cad_dxf_agent.core.cross_drawing_checker import check_consistency

        sheet = _make_context(
            "plan.dxf",
            entities=[_line_entity("h1")],
        )
        report = check_consistency([sheet])

        assert isinstance(report, ConsistencyReport)
        assert len(report.sheets) == 1
        assert len(report.checks_run) >= 1

    def test_consistent_set_passes(self):
        from cad_dxf_agent.core.cross_drawing_checker import check_consistency

        entities_a = [
            _text_entity("h1", "Kitchen"),
            _text_entity("h2", "Bedroom"),
            _line_entity("h3", x=0, y=0),
            _line_entity("h4", x=50, y=50),
            _insert_entity("h5", "DOOR_36"),
        ]
        entities_b = [
            _text_entity("h6", "Kitchen"),
            _text_entity("h7", "Bedroom"),
            _line_entity("h8", x=5, y=5),
            _line_entity("h9", x=45, y=45),
            _insert_entity("h10", "DOOR_36"),
        ]

        sheet_a = _make_context(
            "floor_plan.dxf",
            entities=entities_a,
            layers=["WALLS", "LABELS"],
            blocks=["DOOR_36"],
        )
        sheet_b = _make_context(
            "electrical.dxf",
            entities=entities_b,
            layers=["WALLS", "LABELS"],
            blocks=["DOOR_36"],
        )
        report = check_consistency([sheet_a, sheet_b])

        # Should have no errors for a well-coordinated set
        assert report.error_count == 0
        assert report.passed is True

    def test_inconsistent_set_has_findings(self):
        from cad_dxf_agent.core.cross_drawing_checker import check_consistency

        sheet_a = _make_context(
            "plan.dxf",
            entities=[
                _text_entity("h1", "Kitchen"),
                _line_entity("h2", x=0, y=0),
            ],
            layers=["WALLS"],
        )
        sheet_b = _make_context(
            "elec.dxf",
            entities=[
                _text_entity("h3", "Office"),
                _line_entity("h4", x=5000, y=5000),
            ],
            layers=["walls"],
        )
        report = check_consistency([sheet_a, sheet_b])

        assert len(report.findings) > 0
        categories = {f.category for f in report.findings}
        # Should flag at least label mismatch and possibly layer case
        assert len(categories) >= 1

    def test_report_checks_run_populated(self):
        from cad_dxf_agent.core.cross_drawing_checker import check_consistency

        report = check_consistency(
            [
                _make_context("a.dxf", entities=[_line_entity("h1")]),
                _make_context("b.dxf", entities=[_line_entity("h2")]),
            ]
        )

        assert "room_labels" in report.checks_run
        assert "layer_naming" in report.checks_run
        assert "block_consistency" in report.checks_run
        assert "entity_counts" in report.checks_run
        assert "coordinate_alignment" in report.checks_run

    def test_three_sheet_set(self):
        from cad_dxf_agent.core.cross_drawing_checker import check_consistency

        common = [
            _text_entity("h1", "Kitchen"),
            _line_entity("h2", x=10, y=10),
        ]
        sheet_a = _make_context("plan.dxf", entities=common, layers=["WALLS"])
        sheet_b = _make_context(
            "rcp.dxf",
            entities=[
                _text_entity("h3", "Kitchen"),
                _line_entity("h4", x=15, y=15),
            ],
            layers=["WALLS"],
        )
        sheet_c = _make_context(
            "elec.dxf",
            entities=[
                _text_entity("h5", "Kitchen"),
                _line_entity("h6", x=20, y=20),
            ],
            layers=["WALLS"],
        )
        report = check_consistency([sheet_a, sheet_b, sheet_c])

        assert len(report.sheets) == 3
        assert isinstance(report, ConsistencyReport)

    def test_empty_input_list(self):
        from cad_dxf_agent.core.cross_drawing_checker import check_consistency

        report = check_consistency([])
        assert isinstance(report, ConsistencyReport)
        assert len(report.sheets) == 0
        assert len(report.findings) == 0

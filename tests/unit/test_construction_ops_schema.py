"""Tests for construction_ops_schema Pydantic models."""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from cad_dxf_agent.models.cad_schema import Point2D
from cad_dxf_agent.models.response_schema import EvidenceRef
from cad_dxf_agent.models.construction_ops_schema import (
    BatchConditionResult,
    Bay,
    ConditionGroup,
    FieldSection,
    FieldSectionType,
    FieldSummary,
    GridDirection,
    GridLine,
    GridSummaryResult,
    RedlineEntry,
    RedlineReportResult,
    RevisionCloudInfo,
)


# ---------------------------------------------------------------------------
# GridDirection enum
# ---------------------------------------------------------------------------


class TestGridDirection:
    def test_horizontal_value(self):
        assert GridDirection.HORIZONTAL == "horizontal"

    def test_vertical_value(self):
        assert GridDirection.VERTICAL == "vertical"

    def test_members(self):
        assert set(GridDirection) == {GridDirection.HORIZONTAL, GridDirection.VERTICAL}


# ---------------------------------------------------------------------------
# GridLine
# ---------------------------------------------------------------------------


class TestGridLine:
    def test_create_minimal(self):
        gl = GridLine(
            direction=GridDirection.VERTICAL,
            label="A",
            position=10.0,
            layer="GRID",
            entity_handle="1A",
        )
        assert gl.direction == GridDirection.VERTICAL
        assert gl.label == "A"
        assert gl.position == 10.0
        assert gl.layer == "GRID"
        assert gl.entity_handle == "1A"

    def test_confidence_default(self):
        gl = GridLine(
            direction=GridDirection.HORIZONTAL,
            label="1",
            position=0.0,
            layer="GRID",
            entity_handle="2B",
        )
        assert 0.0 <= gl.confidence <= 1.0

    def test_confidence_bounds_valid(self):
        gl = GridLine(
            direction=GridDirection.HORIZONTAL,
            label="1",
            position=5.0,
            layer="GRID",
            entity_handle="3C",
            confidence=0.0,
        )
        assert gl.confidence == 0.0
        gl2 = GridLine(
            direction=GridDirection.HORIZONTAL,
            label="1",
            position=5.0,
            layer="GRID",
            entity_handle="3C",
            confidence=1.0,
        )
        assert gl2.confidence == 1.0

    def test_confidence_out_of_range_high(self):
        with pytest.raises(ValidationError):
            GridLine(
                direction=GridDirection.HORIZONTAL,
                label="1",
                position=5.0,
                layer="GRID",
                entity_handle="3C",
                confidence=1.5,
            )

    def test_confidence_out_of_range_low(self):
        with pytest.raises(ValidationError):
            GridLine(
                direction=GridDirection.HORIZONTAL,
                label="1",
                position=5.0,
                layer="GRID",
                entity_handle="3C",
                confidence=-0.1,
            )

    def test_serialization_roundtrip(self):
        gl = GridLine(
            direction=GridDirection.VERTICAL,
            label="B",
            position=25.5,
            layer="COLUMN_GRID",
            entity_handle="FF",
            confidence=0.85,
        )
        data = gl.model_dump()
        assert data["direction"] == "vertical"
        restored = GridLine.model_validate(data)
        assert restored == gl


# ---------------------------------------------------------------------------
# Bay
# ---------------------------------------------------------------------------


class TestBay:
    def test_create(self):
        bay = Bay(
            label="A-B",
            direction=GridDirection.VERTICAL,
            start_line="A",
            end_line="B",
            dimension=30.0,
            unit="ft",
        )
        assert bay.dimension == 30.0
        assert bay.unit == "ft"

    def test_serialization(self):
        bay = Bay(
            label="1-2",
            direction=GridDirection.HORIZONTAL,
            start_line="1",
            end_line="2",
            dimension=24.0,
            unit="ft",
        )
        data = bay.model_dump()
        assert data["direction"] == "horizontal"


# ---------------------------------------------------------------------------
# GridSummaryResult
# ---------------------------------------------------------------------------


class TestGridSummaryResult:
    def test_create_minimal(self):
        result = GridSummaryResult(
            grid_lines=[],
            bays=[],
            drawing_summary="Empty grid",
            grid_pattern_description="None detected",
            methodology="heuristic",
            aggregate_confidence=0.5,
        )
        assert result.grid_lines == []
        assert result.bays == []
        assert result.ambiguity_flags == []
        assert result.caveats == []

    def test_aggregate_confidence_out_of_range(self):
        with pytest.raises(ValidationError):
            GridSummaryResult(
                grid_lines=[],
                bays=[],
                drawing_summary="x",
                grid_pattern_description="x",
                methodology="heuristic",
                aggregate_confidence=2.0,
            )


# ---------------------------------------------------------------------------
# RevisionCloudInfo
# ---------------------------------------------------------------------------


class TestRevisionCloudInfo:
    def test_create(self):
        rc = RevisionCloudInfo(
            cloud_handle="A1",
            layer="REVISION",
            bounds=(Point2D(x=0, y=0), Point2D(x=100, y=100)),
            vertex_count=20,
        )
        assert rc.cloud_handle == "A1"
        assert rc.vertex_count == 20
        assert rc.bounds[0].x == 0
        assert rc.bounds[1].y == 100


# ---------------------------------------------------------------------------
# RedlineEntry
# ---------------------------------------------------------------------------


class TestRedlineEntry:
    def test_create(self):
        cloud = RevisionCloudInfo(
            cloud_handle="B2",
            layer="REV",
            bounds=(Point2D(x=0, y=0), Point2D(x=50, y=50)),
            vertex_count=12,
        )
        entry = RedlineEntry(
            cloud=cloud,
            affected_entities=[
                EvidenceRef(entity_handle="E1", description="entity 1"),
                EvidenceRef(entity_handle="E2", description="entity 2"),
            ],
            affected_layers=["WALL", "DOOR"],
            entity_count=2,
            description="Two entities changed",
            confidence=0.9,
        )
        assert entry.entity_count == 2
        assert len(entry.affected_layers) == 2


# ---------------------------------------------------------------------------
# RedlineReportResult
# ---------------------------------------------------------------------------


class TestRedlineReportResult:
    def test_defaults(self):
        result = RedlineReportResult(
            entries=[],
            total_clouds=0,
            total_affected_entities=0,
            methodology="spatial",
            aggregate_confidence=0.7,
        )
        assert result.ambiguity_flags == []
        assert result.caveats == []

    def test_aggregate_confidence_out_of_range(self):
        with pytest.raises(ValidationError):
            RedlineReportResult(
                entries=[],
                total_clouds=0,
                total_affected_entities=0,
                methodology="spatial",
                aggregate_confidence=-0.5,
            )


# ---------------------------------------------------------------------------
# ConditionGroup & BatchConditionResult
# ---------------------------------------------------------------------------


class TestConditionGroup:
    def test_create(self):
        cg = ConditionGroup(
            name="Fire extinguisher",
            exemplar_handles=["H1", "H2"],
            instances=[{"handle": "H1", "x": 10}, {"handle": "H2", "x": 20}],
            total_instances=2,
            confidence=0.95,
        )
        assert cg.total_instances == 2
        assert cg.caveats == []


class TestBatchConditionResult:
    def test_create_empty(self):
        result = BatchConditionResult(
            groups=[],
            total_groups=0,
            total_instances=0,
            methodology="clustering",
            aggregate_confidence=0.5,
        )
        assert result.ambiguity_flags == []

    def test_aggregate_confidence_out_of_range(self):
        with pytest.raises(ValidationError):
            BatchConditionResult(
                groups=[],
                total_groups=0,
                total_instances=0,
                methodology="clustering",
                aggregate_confidence=1.1,
            )


# ---------------------------------------------------------------------------
# FieldSectionType enum
# ---------------------------------------------------------------------------


class TestFieldSectionType:
    def test_all_members(self):
        expected = {
            "grid_summary",
            "takeoff_summary",
            "revision_changes",
            "layout_notes",
            "condition_report",
            "general_notes",
        }
        assert {m.value for m in FieldSectionType} == expected


# ---------------------------------------------------------------------------
# FieldSection & FieldSummary
# ---------------------------------------------------------------------------


class TestFieldSection:
    def test_create(self):
        fs = FieldSection(
            section_type=FieldSectionType.GRID_SUMMARY,
            title="Grid Summary",
            content={"lines": 5},
            available=True,
            confidence=0.8,
        )
        assert fs.available is True
        assert fs.content == {"lines": 5}
        assert fs.caveats == []


class TestFieldSummary:
    def test_create_minimal(self):
        section = FieldSection(
            section_type=FieldSectionType.GENERAL_NOTES,
            title="Notes",
            content={},
            available=True,
            confidence=0.6,
        )
        summary = FieldSummary(
            title="Field Report",
            sections=[section],
            generated_at="2026-03-07T00:00:00Z",
            aggregate_confidence=0.6,
        )
        assert len(summary.sections) == 1
        assert summary.ambiguity_flags == []
        assert summary.omitted_sections == []
        assert summary.caveats == []

    def test_aggregate_confidence_out_of_range(self):
        with pytest.raises(ValidationError):
            FieldSummary(
                title="Bad",
                sections=[],
                generated_at="2026-03-07T00:00:00Z",
                aggregate_confidence=5.0,
            )

    def test_serialization_roundtrip(self):
        section = FieldSection(
            section_type=FieldSectionType.TAKEOFF_SUMMARY,
            title="Takeoff",
            content={"doors": 12},
            available=True,
            confidence=0.75,
            caveats=["estimate only"],
        )
        summary = FieldSummary(
            title="Field Summary",
            sections=[section],
            generated_at="2026-03-07T12:00:00Z",
            aggregate_confidence=0.75,
            ambiguity_flags=["partial_data"],
            omitted_sections=["layout_notes"],
            caveats=["draft"],
        )
        data = summary.model_dump()
        restored = FieldSummary.model_validate(data)
        assert restored.title == summary.title
        assert restored.sections[0].content == {"doors": 12}
        assert restored.caveats == ["draft"]

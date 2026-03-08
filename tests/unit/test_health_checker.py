"""Tests for the drawing health checker — deterministic quality analysis.

Covers all 7 deterministic checks, score computation, the public API
(check_drawing_health), the HealthHandler stage handler, and schema models.
"""

from __future__ import annotations

import pytest

from cad_dxf_agent.core.entity_index import EntityIndex
from cad_dxf_agent.core.health_checker import (
    _check_dimension_coverage,
    _check_entity_type_distribution,
    _check_inconsistent_text_heights,
    _check_missing_text_content,
    _check_orphan_layers,
    _check_overlapping_entities,
    _check_polylines_missing_geometry,
    _compute_score,
    check_drawing_health,
)
from cad_dxf_agent.models.cad_schema import (
    DrawingContext,
    EntityRef,
    EntityType,
    LayerRule,
    Point2D,
    TextGeometry,
)
from cad_dxf_agent.models.health_schema import (
    HealthCategory,
    HealthIssue,
    HealthReport,
    HealthSeverity,
)

# ---------------------------------------------------------------------------
# Helpers — build DrawingContext programmatically
# ---------------------------------------------------------------------------


def _make_entity(
    handle: str,
    entity_type: EntityType,
    layer: str = "STRUCTURAL",
    x: float | None = None,
    y: float | None = None,
    text_content: str | None = None,
    text_height: float | None = None,
) -> EntityRef:
    """Build a minimal EntityRef for testing."""
    point = Point2D(x=x, y=y) if x is not None and y is not None else None
    tg = None
    if text_height is not None:
        tg = TextGeometry(height=text_height)
    return EntityRef(
        handle=handle,
        entity_type=entity_type,
        layer=layer,
        insert_point=point,
        text_content=text_content,
        text_geometry=tg,
    )


def _make_context(
    entities: list[EntityRef] | None = None,
    layers: list[str] | None = None,
) -> DrawingContext:
    """Build a DrawingContext with optional entity and layer lists."""
    ents = entities or []
    layer_names = layers or list({e.layer for e in ents})
    layer_infos = [
        LayerRule(name=n, color=1)
        for n in layer_names
    ]
    return DrawingContext(
        file_path="test.dxf",
        entities=ents,
        layers=layer_infos,
        blocks=[],
        metadata={},
    )


# ===================================================================
# Tests: HealthSchema models
# ===================================================================


class TestHealthSchema:
    """Validate Pydantic models for health reporting."""

    def test_health_severity_values(self):
        assert HealthSeverity.CRITICAL == "critical"
        assert HealthSeverity.WARNING == "warning"
        assert HealthSeverity.INFO == "info"

    def test_health_category_values(self):
        assert HealthCategory.GEOMETRY == "geometry"
        assert HealthCategory.TEXT == "text"
        assert HealthCategory.LAYER == "layer"
        assert HealthCategory.OVERLAP == "overlap"
        assert HealthCategory.DIMENSION == "dimension"
        assert HealthCategory.ZONE == "zone"
        assert HealthCategory.GENERAL == "general"

    def test_health_issue_construction(self):
        issue = HealthIssue(
            severity=HealthSeverity.WARNING,
            category=HealthCategory.TEXT,
            title="Test issue",
            description="Some problem",
            check_name="test_check",
        )
        assert issue.severity == HealthSeverity.WARNING
        assert issue.evidence == []

    def test_health_report_properties(self):
        issues = [
            HealthIssue(
                severity=HealthSeverity.CRITICAL,
                category=HealthCategory.GENERAL,
                title="c1",
                description="critical 1",
            ),
            HealthIssue(
                severity=HealthSeverity.CRITICAL,
                category=HealthCategory.GENERAL,
                title="c2",
                description="critical 2",
            ),
            HealthIssue(
                severity=HealthSeverity.WARNING,
                category=HealthCategory.TEXT,
                title="w1",
                description="warning",
            ),
            HealthIssue(
                severity=HealthSeverity.INFO,
                category=HealthCategory.LAYER,
                title="i1",
                description="info",
            ),
        ]
        report = HealthReport(
            score=55.0,
            issues=issues,
            checks_run=["a", "b"],
            entity_count=50,
            layer_count=3,
        )
        assert report.critical_count == 2
        assert report.warning_count == 1
        assert report.info_count == 1

    def test_health_report_summary_no_issues(self):
        report = HealthReport(
            score=100.0, issues=[], checks_run=["a"], entity_count=10
        )
        assert "no issues found" in report.summary

    def test_health_report_summary_with_issues(self):
        report = HealthReport(
            score=75.0,
            issues=[
                HealthIssue(
                    severity=HealthSeverity.WARNING,
                    category=HealthCategory.TEXT,
                    title="t",
                    description="d",
                ),
            ],
            checks_run=["a"],
            entity_count=10,
        )
        assert "1 warning" in report.summary
        assert "75/100" in report.summary

    def test_health_report_score_bounds(self):
        """Score must be 0-100."""
        report = HealthReport(score=0.0, entity_count=5)
        assert report.score == 0.0
        report2 = HealthReport(score=100.0, entity_count=5)
        assert report2.score == 100.0

        with pytest.raises(ValueError):
            HealthReport(score=-1.0, entity_count=5)

        with pytest.raises(ValueError):
            HealthReport(score=101.0, entity_count=5)


# ===================================================================
# Tests: Score computation
# ===================================================================


class TestComputeScore:
    """Test the _compute_score function."""

    def test_no_issues_perfect_score(self):
        assert _compute_score([], entity_count=100) == 100.0

    def test_empty_drawing_zero_score(self):
        assert _compute_score([], entity_count=0) == 0.0

    def test_single_critical(self):
        issues = [
            HealthIssue(
                severity=HealthSeverity.CRITICAL,
                category=HealthCategory.GENERAL,
                title="t",
                description="d",
            )
        ]
        assert _compute_score(issues, entity_count=10) == 80.0

    def test_single_warning(self):
        issues = [
            HealthIssue(
                severity=HealthSeverity.WARNING,
                category=HealthCategory.TEXT,
                title="t",
                description="d",
            )
        ]
        assert _compute_score(issues, entity_count=10) == 95.0

    def test_single_info(self):
        issues = [
            HealthIssue(
                severity=HealthSeverity.INFO,
                category=HealthCategory.LAYER,
                title="t",
                description="d",
            )
        ]
        assert _compute_score(issues, entity_count=10) == 99.0

    def test_critical_capped_at_60(self):
        """4 critical issues should deduct 60 (capped), not 80."""
        issues = [
            HealthIssue(
                severity=HealthSeverity.CRITICAL,
                category=HealthCategory.GENERAL,
                title=f"c{i}",
                description="d",
            )
            for i in range(4)
        ]
        assert _compute_score(issues, entity_count=10) == 40.0

    def test_warning_capped_at_30(self):
        """7 warnings should deduct 30 (capped), not 35."""
        issues = [
            HealthIssue(
                severity=HealthSeverity.WARNING,
                category=HealthCategory.TEXT,
                title=f"w{i}",
                description="d",
            )
            for i in range(7)
        ]
        assert _compute_score(issues, entity_count=10) == 70.0

    def test_info_capped_at_10(self):
        """15 info issues should deduct 10 (capped), not 15."""
        issues = [
            HealthIssue(
                severity=HealthSeverity.INFO,
                category=HealthCategory.LAYER,
                title=f"i{i}",
                description="d",
            )
            for i in range(15)
        ]
        assert _compute_score(issues, entity_count=10) == 90.0

    def test_mixed_severities(self):
        """1 critical (-20) + 1 warning (-5) + 1 info (-1) = 74."""
        issues = [
            HealthIssue(
                severity=HealthSeverity.CRITICAL,
                category=HealthCategory.GENERAL,
                title="c",
                description="d",
            ),
            HealthIssue(
                severity=HealthSeverity.WARNING,
                category=HealthCategory.TEXT,
                title="w",
                description="d",
            ),
            HealthIssue(
                severity=HealthSeverity.INFO,
                category=HealthCategory.LAYER,
                title="i",
                description="d",
            ),
        ]
        assert _compute_score(issues, entity_count=10) == 74.0

    def test_max_deductions_floor_at_zero(self):
        """Score never goes below 0."""
        issues = [
            HealthIssue(
                severity=HealthSeverity.CRITICAL,
                category=HealthCategory.GENERAL,
                title=f"c{i}",
                description="d",
            )
            for i in range(4)  # -60
        ] + [
            HealthIssue(
                severity=HealthSeverity.WARNING,
                category=HealthCategory.TEXT,
                title=f"w{i}",
                description="d",
            )
            for i in range(7)  # -30
        ] + [
            HealthIssue(
                severity=HealthSeverity.INFO,
                category=HealthCategory.LAYER,
                title=f"i{i}",
                description="d",
            )
            for i in range(15)  # -10
        ]
        # Total deductions: 60 + 30 + 10 = 100
        assert _compute_score(issues, entity_count=10) == 0.0


# ===================================================================
# Tests: Individual checks
# ===================================================================


class TestCheckUnclosedPolylines:
    """Test _check_polylines_missing_geometry."""

    def test_no_polylines_no_issues(self):
        ctx = _make_context(
            entities=[
                _make_entity("1", EntityType.LINE, x=0, y=0),
            ]
        )
        idx = EntityIndex(ctx)
        issues = _check_polylines_missing_geometry(ctx, idx)
        assert issues == []

    def test_polylines_with_position_no_issue(self):
        """Polylines with insert_point shouldn't flag (we skip them)."""
        ctx = _make_context(
            entities=[
                _make_entity("1", EntityType.LWPOLYLINE, x=10, y=10),
            ]
        )
        idx = EntityIndex(ctx)
        issues = _check_polylines_missing_geometry(ctx, idx)
        assert issues == []

    def test_polylines_without_position_flagged(self):
        """Polylines missing insert_point should be flagged as INFO."""
        ctx = _make_context(
            entities=[
                _make_entity("1", EntityType.LWPOLYLINE),  # no x,y
                _make_entity("2", EntityType.LWPOLYLINE),  # no x,y
            ]
        )
        idx = EntityIndex(ctx)
        issues = _check_polylines_missing_geometry(ctx, idx)
        assert len(issues) == 1
        assert issues[0].severity == HealthSeverity.INFO
        assert issues[0].category == HealthCategory.GEOMETRY
        assert "2 polyline" in issues[0].description
        assert len(issues[0].evidence) == 2

    def test_evidence_capped_at_5(self):
        """Only first 5 polylines appear in evidence."""
        ents = [
            _make_entity(str(i), EntityType.LWPOLYLINE)
            for i in range(10)
        ]
        ctx = _make_context(entities=ents)
        idx = EntityIndex(ctx)
        issues = _check_polylines_missing_geometry(ctx, idx)
        assert len(issues) == 1
        assert len(issues[0].evidence) == 5


class TestCheckInconsistentTextHeights:
    """Test _check_inconsistent_text_heights."""

    def test_consistent_heights_no_issue(self):
        """All text at same height on a layer = no issue."""
        ctx = _make_context(
            entities=[
                _make_entity(
                    "1", EntityType.TEXT, layer="NOTES",
                    x=0, y=0, text_height=3.0,
                ),
                _make_entity(
                    "2", EntityType.TEXT, layer="NOTES",
                    x=10, y=0, text_height=3.0,
                ),
            ]
        )
        idx = EntityIndex(ctx)
        issues = _check_inconsistent_text_heights(ctx, idx)
        assert issues == []

    def test_two_heights_no_issue(self):
        """Two distinct heights on a layer is OK (title vs body)."""
        ctx = _make_context(
            entities=[
                _make_entity(
                    "1", EntityType.TEXT, layer="NOTES",
                    x=0, y=0, text_height=3.0,
                ),
                _make_entity(
                    "2", EntityType.TEXT, layer="NOTES",
                    x=10, y=0, text_height=5.0,
                ),
            ]
        )
        idx = EntityIndex(ctx)
        issues = _check_inconsistent_text_heights(ctx, idx)
        assert issues == []

    def test_three_heights_flagged(self):
        """Three distinct heights on a single layer = WARNING."""
        ctx = _make_context(
            entities=[
                _make_entity(
                    "1", EntityType.TEXT, layer="NOTES",
                    x=0, y=0, text_height=3.0,
                ),
                _make_entity(
                    "2", EntityType.TEXT, layer="NOTES",
                    x=10, y=0, text_height=3.0,
                ),
                _make_entity(
                    "3", EntityType.TEXT, layer="NOTES",
                    x=20, y=0, text_height=5.0,
                ),
                _make_entity(
                    "4", EntityType.TEXT, layer="NOTES",
                    x=30, y=0, text_height=8.0,
                ),
            ]
        )
        idx = EntityIndex(ctx)
        issues = _check_inconsistent_text_heights(ctx, idx)
        assert len(issues) == 1
        assert issues[0].severity == HealthSeverity.WARNING
        assert issues[0].category == HealthCategory.TEXT
        assert "NOTES" in issues[0].title

    def test_no_text_geometry_skipped(self):
        """Text without text_geometry should be skipped gracefully."""
        ctx = _make_context(
            entities=[
                _make_entity("1", EntityType.TEXT, layer="NOTES", x=0, y=0),
                _make_entity("2", EntityType.TEXT, layer="NOTES", x=10, y=0),
            ]
        )
        idx = EntityIndex(ctx)
        issues = _check_inconsistent_text_heights(ctx, idx)
        assert issues == []

    def test_zero_height_skipped(self):
        """Text with height=0 should be ignored."""
        ctx = _make_context(
            entities=[
                _make_entity(
                    "1", EntityType.TEXT, layer="NOTES",
                    x=0, y=0, text_height=0.0,
                ),
                _make_entity(
                    "2", EntityType.TEXT, layer="NOTES",
                    x=10, y=0, text_height=3.0,
                ),
            ]
        )
        idx = EntityIndex(ctx)
        issues = _check_inconsistent_text_heights(ctx, idx)
        assert issues == []

    def test_multiple_layers_independent(self):
        """Inconsistency on one layer shouldn't affect clean layers."""
        ctx = _make_context(
            entities=[
                # NOTES: 3 distinct heights → flagged
                _make_entity("1", EntityType.TEXT, "NOTES", 0, 0, text_height=3.0),
                _make_entity("2", EntityType.TEXT, "NOTES", 10, 0, text_height=5.0),
                _make_entity("3", EntityType.TEXT, "NOTES", 20, 0, text_height=8.0),
                # LABELS: consistent → not flagged
                _make_entity("4", EntityType.TEXT, "LABELS", 0, 10, text_height=2.0),
                _make_entity("5", EntityType.TEXT, "LABELS", 10, 10, text_height=2.0),
            ],
            layers=["NOTES", "LABELS"],
        )
        idx = EntityIndex(ctx)
        issues = _check_inconsistent_text_heights(ctx, idx)
        assert len(issues) == 1
        assert "NOTES" in issues[0].title


class TestCheckOrphanLayers:
    """Test _check_orphan_layers."""

    def test_no_orphans(self):
        """All layers have entities = no issue."""
        ctx = _make_context(
            entities=[
                _make_entity("1", EntityType.LINE, layer="STRUCTURAL", x=0, y=0),
            ],
            layers=["STRUCTURAL"],
        )
        idx = EntityIndex(ctx)
        issues = _check_orphan_layers(ctx, idx)
        assert issues == []

    def test_orphan_layer_flagged(self):
        """Defined layer with zero entities = INFO."""
        ctx = _make_context(
            entities=[
                _make_entity("1", EntityType.LINE, layer="STRUCTURAL", x=0, y=0),
            ],
            layers=["STRUCTURAL", "ELECTRICAL", "PLUMBING"],
        )
        idx = EntityIndex(ctx)
        issues = _check_orphan_layers(ctx, idx)
        assert len(issues) == 1
        assert issues[0].severity == HealthSeverity.INFO
        assert issues[0].category == HealthCategory.LAYER
        assert "2 orphan" in issues[0].title
        assert "ELECTRICAL" in issues[0].description
        assert "PLUMBING" in issues[0].description

    def test_system_layers_excluded(self):
        """Layer '0' and 'DEFPOINTS' should not be flagged as orphans."""
        ctx = _make_context(
            entities=[
                _make_entity("1", EntityType.LINE, layer="STRUCTURAL", x=0, y=0),
            ],
            layers=["STRUCTURAL", "0", "Defpoints"],
        )
        idx = EntityIndex(ctx)
        issues = _check_orphan_layers(ctx, idx)
        assert issues == []

    def test_many_orphans_truncated(self):
        """Evidence should be capped at 10 items."""
        layer_names = [f"ORPHAN_{i}" for i in range(15)]
        ctx = _make_context(
            entities=[
                _make_entity("1", EntityType.LINE, layer="ACTIVE", x=0, y=0),
            ],
            layers=["ACTIVE"] + layer_names,
        )
        idx = EntityIndex(ctx)
        issues = _check_orphan_layers(ctx, idx)
        assert len(issues) == 1
        assert len(issues[0].evidence) == 10
        assert "(and more)" in issues[0].description


class TestCheckOverlappingEntities:
    """Test _check_overlapping_entities."""

    def test_no_overlaps(self):
        """Entities at distinct positions = no issue."""
        ctx = _make_context(
            entities=[
                _make_entity("1", EntityType.LINE, x=0, y=0),
                _make_entity("2", EntityType.LINE, x=100, y=100),
            ]
        )
        idx = EntityIndex(ctx)
        issues = _check_overlapping_entities(ctx, idx)
        assert issues == []

    def test_overlapping_same_layer(self):
        """Two entities at same position, same layer = WARNING."""
        ctx = _make_context(
            entities=[
                _make_entity("1", EntityType.LINE, layer="A", x=10, y=10),
                _make_entity("2", EntityType.TEXT, layer="A", x=10, y=10,
                             text_content="X"),
            ],
            layers=["A"],
        )
        idx = EntityIndex(ctx)
        issues = _check_overlapping_entities(ctx, idx)
        assert len(issues) == 1
        assert issues[0].severity == HealthSeverity.WARNING
        assert issues[0].category == HealthCategory.OVERLAP

    def test_same_position_different_layers_no_overlap(self):
        """Entities at same position but different layers are NOT overlaps."""
        ctx = _make_context(
            entities=[
                _make_entity("1", EntityType.LINE, layer="A", x=10, y=10),
                _make_entity("2", EntityType.LINE, layer="B", x=10, y=10),
            ],
            layers=["A", "B"],
        )
        idx = EntityIndex(ctx)
        issues = _check_overlapping_entities(ctx, idx)
        assert issues == []

    def test_entities_without_position_skipped(self):
        """Entities with no insert_point should be skipped."""
        ctx = _make_context(
            entities=[
                _make_entity("1", EntityType.LINE),  # no position
                _make_entity("2", EntityType.LINE),  # no position
            ]
        )
        idx = EntityIndex(ctx)
        issues = _check_overlapping_entities(ctx, idx)
        assert issues == []

    def test_multiple_overlap_groups(self):
        """Multiple groups of overlapping entities."""
        ctx = _make_context(
            entities=[
                # Group 1 at (10, 10)
                _make_entity("1", EntityType.LINE, layer="A", x=10, y=10),
                _make_entity("2", EntityType.LINE, layer="A", x=10, y=10),
                # Group 2 at (50, 50)
                _make_entity("3", EntityType.LINE, layer="A", x=50, y=50),
                _make_entity("4", EntityType.LINE, layer="A", x=50, y=50),
            ],
            layers=["A"],
        )
        idx = EntityIndex(ctx)
        issues = _check_overlapping_entities(ctx, idx)
        assert len(issues) == 1
        assert "2 location(s)" in issues[0].title


class TestCheckMissingTextContent:
    """Test _check_missing_text_content."""

    def test_non_text_entities_skipped(self):
        """Non-text entities should be ignored."""
        ctx = _make_context(
            entities=[
                _make_entity("1", EntityType.LINE, x=0, y=0),
            ]
        )
        idx = EntityIndex(ctx)
        issues = _check_missing_text_content(ctx, idx)
        assert issues == []

    def test_text_with_content_ok(self):
        """Text with real content = no issue."""
        ctx = _make_context(
            entities=[
                _make_entity(
                    "1", EntityType.TEXT, x=0, y=0,
                    text_content="Hello World",
                ),
            ]
        )
        idx = EntityIndex(ctx)
        issues = _check_missing_text_content(ctx, idx)
        assert issues == []

    def test_empty_text_flagged(self):
        """TEXT with empty content = WARNING."""
        ctx = _make_context(
            entities=[
                _make_entity(
                    "1", EntityType.TEXT, x=0, y=0,
                    text_content="",
                ),
            ]
        )
        idx = EntityIndex(ctx)
        issues = _check_missing_text_content(ctx, idx)
        assert len(issues) == 1
        assert issues[0].severity == HealthSeverity.WARNING
        assert issues[0].category == HealthCategory.TEXT

    def test_whitespace_only_text_flagged(self):
        """Text with only whitespace = WARNING."""
        ctx = _make_context(
            entities=[
                _make_entity(
                    "1", EntityType.MTEXT, x=0, y=0,
                    text_content="   \n  ",
                ),
            ]
        )
        idx = EntityIndex(ctx)
        issues = _check_missing_text_content(ctx, idx)
        assert len(issues) == 1

    def test_none_text_content_flagged(self):
        """Text with None text_content = WARNING."""
        ctx = _make_context(
            entities=[
                _make_entity("1", EntityType.TEXT, x=0, y=0),  # text_content=None
            ]
        )
        idx = EntityIndex(ctx)
        issues = _check_missing_text_content(ctx, idx)
        assert len(issues) == 1

    def test_singular_plural_in_title(self):
        """1 empty text = 'entity', 2+ = 'entities'."""
        single = _make_context(
            entities=[
                _make_entity("1", EntityType.TEXT, x=0, y=0, text_content=""),
            ]
        )
        idx = EntityIndex(single)
        issues = _check_missing_text_content(single, idx)
        assert "1 empty text entity" in issues[0].title

        multi = _make_context(
            entities=[
                _make_entity("1", EntityType.TEXT, x=0, y=0, text_content=""),
                _make_entity("2", EntityType.TEXT, x=10, y=0, text_content=""),
            ]
        )
        idx2 = EntityIndex(multi)
        issues2 = _check_missing_text_content(multi, idx2)
        assert "2 empty text entities" in issues2[0].title

    def test_evidence_capped_at_10(self):
        """Only first 10 empty texts appear in evidence."""
        ents = [
            _make_entity(
                str(i), EntityType.TEXT, x=i * 10.0, y=0,
                text_content="",
            )
            for i in range(15)
        ]
        ctx = _make_context(entities=ents)
        idx = EntityIndex(ctx)
        issues = _check_missing_text_content(ctx, idx)
        assert len(issues[0].evidence) == 10


class TestCheckDimensionCoverage:
    """Test _check_dimension_coverage."""

    def test_drawing_with_dimensions_ok(self):
        """Drawing with geometry and dimensions = no issue."""
        ents = [
            _make_entity(str(i), EntityType.LINE, x=i * 10.0, y=0)
            for i in range(15)
        ] + [
            _make_entity(f"d{i}", EntityType.DIMENSION, x=i * 10.0, y=-5)
            for i in range(5)
        ]
        ctx = _make_context(entities=ents)
        idx = EntityIndex(ctx)
        issues = _check_dimension_coverage(ctx, idx)
        assert issues == []

    def test_no_dimensions_with_geometry_warning(self):
        """10+ geometric entities and 0 dimensions = WARNING."""
        ents = [
            _make_entity(str(i), EntityType.LINE, x=i * 10.0, y=0)
            for i in range(12)
        ]
        ctx = _make_context(entities=ents)
        idx = EntityIndex(ctx)
        issues = _check_dimension_coverage(ctx, idx)
        assert len(issues) == 1
        assert issues[0].severity == HealthSeverity.WARNING
        assert issues[0].category == HealthCategory.DIMENSION
        assert "No dimensions found" in issues[0].title

    def test_few_geometry_entities_no_issue(self):
        """Less than 10 geometric entities = no dimension check."""
        ents = [
            _make_entity(str(i), EntityType.LINE, x=i * 10.0, y=0)
            for i in range(5)
        ]
        ctx = _make_context(entities=ents)
        idx = EntityIndex(ctx)
        issues = _check_dimension_coverage(ctx, idx)
        assert issues == []

    def test_low_dimension_ratio_info(self):
        """20+ geometry with <5% dimensions = INFO."""
        ents = [
            _make_entity(str(i), EntityType.LINE, x=i * 5.0, y=0)
            for i in range(25)
        ]
        # Add 0 dimensions (less than 5% of 25 = 1.25, so 0 triggers WARNING)
        # Add 1 dimension = 4% < 5% → triggers INFO
        ents.append(_make_entity("d0", EntityType.DIMENSION, x=0, y=-5))
        ctx = _make_context(entities=ents)
        idx = EntityIndex(ctx)
        issues = _check_dimension_coverage(ctx, idx)
        assert len(issues) == 1
        assert issues[0].severity == HealthSeverity.INFO
        assert "Low dimension coverage" in issues[0].title

    def test_polylines_count_as_geometry(self):
        """LWPOLYLINE entities should count toward geometry total."""
        ents = [
            _make_entity(str(i), EntityType.LWPOLYLINE, x=i * 5.0, y=0)
            for i in range(12)
        ]
        ctx = _make_context(entities=ents)
        idx = EntityIndex(ctx)
        issues = _check_dimension_coverage(ctx, idx)
        assert len(issues) == 1
        assert issues[0].severity == HealthSeverity.WARNING


class TestCheckEntityTypeDistribution:
    """Test _check_entity_type_distribution."""

    def test_empty_drawing_critical(self):
        """Zero entities = CRITICAL."""
        ctx = _make_context(entities=[], layers=["STRUCTURAL"])
        idx = EntityIndex(ctx)
        issues = _check_entity_type_distribution(ctx, idx)
        assert len(issues) == 1
        assert issues[0].severity == HealthSeverity.CRITICAL
        assert "Empty drawing" in issues[0].title

    def test_mixed_entities_ok(self):
        """Mix of text and geometry = no issue."""
        ctx = _make_context(
            entities=[
                _make_entity("1", EntityType.LINE, x=0, y=0),
                _make_entity("2", EntityType.TEXT, x=10, y=0,
                             text_content="Note"),
            ]
        )
        idx = EntityIndex(ctx)
        issues = _check_entity_type_distribution(ctx, idx)
        assert issues == []

    def test_text_only_drawing_info(self):
        """All text, no geometry, 5+ entities = INFO."""
        ents = [
            _make_entity(
                str(i), EntityType.TEXT, x=i * 10.0, y=0,
                text_content=f"Text {i}",
            )
            for i in range(8)
        ]
        ctx = _make_context(entities=ents)
        idx = EntityIndex(ctx)
        issues = _check_entity_type_distribution(ctx, idx)
        assert len(issues) == 1
        assert issues[0].severity == HealthSeverity.INFO
        assert "Text-only drawing" in issues[0].title

    def test_text_only_few_entities_no_issue(self):
        """Text-only but <= 5 entities shouldn't flag."""
        ents = [
            _make_entity(
                str(i), EntityType.TEXT, x=i * 10.0, y=0,
                text_content="X",
            )
            for i in range(3)
        ]
        ctx = _make_context(entities=ents)
        idx = EntityIndex(ctx)
        issues = _check_entity_type_distribution(ctx, idx)
        assert issues == []

    def test_geometry_only_ok(self):
        """Geometry-only drawings are fine (structural drawings often are)."""
        ctx = _make_context(
            entities=[
                _make_entity("1", EntityType.LINE, x=0, y=0),
                _make_entity("2", EntityType.CIRCLE, x=10, y=10),
            ]
        )
        idx = EntityIndex(ctx)
        issues = _check_entity_type_distribution(ctx, idx)
        assert issues == []

    def test_mtext_counts_as_text(self):
        """MTEXT should count toward text total."""
        ents = [
            _make_entity(
                str(i), EntityType.MTEXT, x=i * 10.0, y=0,
                text_content=f"Note {i}",
            )
            for i in range(8)
        ]
        ctx = _make_context(entities=ents)
        idx = EntityIndex(ctx)
        issues = _check_entity_type_distribution(ctx, idx)
        assert len(issues) == 1
        assert "Text-only" in issues[0].title


# ===================================================================
# Tests: Public API — check_drawing_health
# ===================================================================


class TestCheckDrawingHealth:
    """Integration tests for the main check_drawing_health function."""

    def test_clean_drawing_perfect_score(self):
        """A well-formed drawing should get a high score."""
        # Lines + text + dimensions = healthy
        ents = [
            _make_entity(str(i), EntityType.LINE, x=i * 10.0, y=0)
            for i in range(15)
        ] + [
            _make_entity(
                f"t{i}", EntityType.TEXT, x=i * 10.0, y=10,
                text_content=f"Label {i}", text_height=3.0,
            )
            for i in range(5)
        ] + [
            _make_entity(f"d{i}", EntityType.DIMENSION, x=i * 10.0, y=-5)
            for i in range(5)
        ]
        ctx = _make_context(entities=ents, layers=["STRUCTURAL"])
        report = check_drawing_health(ctx, include_zones=False)

        assert isinstance(report, HealthReport)
        assert report.score >= 90.0
        assert report.entity_count == 25
        assert len(report.checks_run) == 7  # All 7 checks
        assert report.layer_count == 1

    def test_empty_drawing_low_score(self):
        """Empty drawing should score 0."""
        ctx = _make_context(entities=[], layers=["STRUCTURAL"])
        report = check_drawing_health(ctx, include_zones=False)
        assert report.score == 0.0
        assert report.critical_count >= 1

    def test_problematic_drawing_low_score(self):
        """Drawing with many issues should have a low score."""
        ents = (
            # Empty text entities (WARNING)
            [
                _make_entity(
                    f"e{i}", EntityType.TEXT, x=i * 10.0, y=0,
                    text_content="",
                )
                for i in range(5)
            ]
            # Inconsistent text heights (WARNING)
            + [
                _make_entity(
                    f"h{i}", EntityType.TEXT, layer="NOTES",
                    x=i * 10.0, y=20, text_height=float(i + 1),
                )
                for i in range(4)
            ]
            # Lines but no dimensions (WARNING)
            + [
                _make_entity(f"l{i}", EntityType.LINE, x=i * 10.0, y=40)
                for i in range(15)
            ]
        )
        ctx = _make_context(
            entities=ents,
            layers=["STRUCTURAL", "NOTES", "ORPHAN_A", "ORPHAN_B"],
        )
        report = check_drawing_health(ctx, include_zones=False)
        assert report.score < 90.0
        assert report.warning_count >= 2

    def test_all_check_names_recorded(self):
        """All 7 check names should appear in checks_run."""
        ctx = _make_context(
            entities=[
                _make_entity("1", EntityType.LINE, x=0, y=0),
            ]
        )
        report = check_drawing_health(ctx, include_zones=False)
        expected_checks = {
            "_check_polylines_missing_geometry",
            "_check_inconsistent_text_heights",
            "_check_orphan_layers",
            "_check_overlapping_entities",
            "_check_missing_text_content",
            "_check_dimension_coverage",
            "_check_entity_type_distribution",
        }
        assert expected_checks == set(report.checks_run)

    def test_include_zones_false_skips_zone_check(self):
        """When include_zones=False, zone check should not run."""
        ctx = _make_context(
            entities=[
                _make_entity("1", EntityType.LINE, x=0, y=0),
            ]
        )
        report = check_drawing_health(ctx, include_zones=False)
        assert "check_unnamed_zones" not in report.checks_run

    def test_report_serializes_to_dict(self):
        """HealthReport should round-trip through model_dump."""
        ctx = _make_context(
            entities=[
                _make_entity("1", EntityType.LINE, x=0, y=0),
                _make_entity("2", EntityType.TEXT, x=10, y=0,
                             text_content=""),
            ]
        )
        report = check_drawing_health(ctx, include_zones=False)
        data = report.model_dump()
        assert isinstance(data, dict)
        assert "score" in data
        assert "issues" in data
        assert isinstance(data["issues"], list)

        # Round-trip
        report2 = HealthReport(**data)
        assert report2.score == report.score
        assert len(report2.issues) == len(report.issues)


# ===================================================================
# Tests: HealthHandler stage handler
# ===================================================================


class TestHealthHandler:
    """Test the stage handler wrapper for the health checker."""

    def test_execute_with_drawing_context(self):
        from cad_dxf_agent.llm.stage_handlers.health_handler import HealthHandler
        from cad_dxf_agent.models.objective_schema import (
            ObjectiveClassification,
            RequestClass,
        )

        handler = HealthHandler()
        ctx = _make_context(
            entities=[
                _make_entity("1", EntityType.LINE, x=0, y=0),
            ]
        )
        classification = ObjectiveClassification(
            request_class=RequestClass.VALIDATE,
            confidence=0.9,
        )
        result = handler.execute(
            classification=classification,
            context={"drawing_context": ctx},
            prompt="check drawing health",
        )

        assert "health_report" in result
        assert "health_score" in result
        assert "health_issues" in result
        assert "checks_run" in result
        assert "summary" in result
        assert isinstance(result["health_report"], dict)
        assert isinstance(result["health_score"], float)

    def test_execute_without_drawing_context(self):
        from cad_dxf_agent.llm.stage_handlers.health_handler import HealthHandler
        from cad_dxf_agent.models.objective_schema import (
            ObjectiveClassification,
            RequestClass,
        )

        handler = HealthHandler()
        classification = ObjectiveClassification(
            request_class=RequestClass.VALIDATE,
            confidence=0.9,
        )
        result = handler.execute(
            classification=classification,
            context={},
            prompt="check drawing health",
        )
        assert result["health_report"] is None
        assert "No drawing context" in result["summary"]

    def test_execute_with_dict_context(self):
        """Handler should accept DrawingContext as a dict (deserialized)."""
        from cad_dxf_agent.llm.stage_handlers.health_handler import HealthHandler
        from cad_dxf_agent.models.objective_schema import (
            ObjectiveClassification,
            RequestClass,
        )

        handler = HealthHandler()
        ctx = _make_context(
            entities=[
                _make_entity("1", EntityType.LINE, x=0, y=0),
            ]
        )
        classification = ObjectiveClassification(
            request_class=RequestClass.VALIDATE,
            confidence=0.9,
        )
        # Pass as dict instead of DrawingContext
        result = handler.execute(
            classification=classification,
            context={"drawing_context": ctx.model_dump()},
            prompt="check drawing health",
        )
        assert result["health_report"] is not None
        assert isinstance(result["health_score"], float)

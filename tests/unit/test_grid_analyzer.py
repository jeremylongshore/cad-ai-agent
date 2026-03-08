"""Tests for GridAnalyzer from cad_dxf_agent.core.construction_ops."""

from __future__ import annotations

import pytest

from cad_dxf_agent.core.construction_ops import GridAnalyzer
from cad_dxf_agent.models.cad_schema import (
    DrawingContext,
    EntityRef,
    EntityType,
    LayerRule,
    Point2D,
)
from cad_dxf_agent.models.construction_ops_schema import GridDirection

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _entity(
    handle: str,
    layer: str = "GRID",
    entity_type: EntityType = EntityType.LINE,
    x: float = 0.0,
    y: float = 0.0,
    block_name: str | None = None,
    text_content: str | None = None,
    attributes: dict | None = None,
) -> EntityRef:
    return EntityRef(
        handle=handle,
        entity_type=entity_type,
        layer=layer,
        insert_point=Point2D(x=x, y=y),
        block_name=block_name,
        text_content=text_content,
        attributes=attributes or {},
    )


def _context(entities: list[EntityRef]) -> DrawingContext:
    layer_names = sorted({e.layer for e in entities})
    return DrawingContext(
        file_path="test.dxf",
        entities=entities,
        layers=[LayerRule(name=n) for n in layer_names],
    )


# ---------------------------------------------------------------------------
# Basic instantiation
# ---------------------------------------------------------------------------


class TestGridAnalyzerInit:
    def test_instantiate(self):
        analyzer = GridAnalyzer()
        assert analyzer is not None

    def test_has_analyze_method(self):
        analyzer = GridAnalyzer()
        assert callable(getattr(analyzer, "analyze", None))


# ---------------------------------------------------------------------------
# Empty / no-grid drawings
# ---------------------------------------------------------------------------


class TestEmptyDrawing:
    def test_empty_entities_returns_empty_result(self):
        ctx = _context([])
        # Provide at least one layer so DrawingContext is valid
        ctx = DrawingContext(
            file_path="test.dxf",
            entities=[],
            layers=[LayerRule(name="0")],
        )
        analyzer = GridAnalyzer()
        result = analyzer.analyze(ctx, "grid summary")
        assert result.grid_lines == []
        assert result.bays == []
        # Should flag that the drawing is empty
        has_empty_flag = any("empty" in str(f).lower() for f in result.ambiguity_flags) or any(
            "empty" in str(c).lower() for c in result.caveats
        )
        assert has_empty_flag, "Expected an 'empty' flag or caveat for empty drawing"

    def test_no_grid_layer_entities(self):
        """Entities exist but none are on grid-related layers."""
        entities = [
            _entity(
                "1",
                layer="WALL",
                entity_type=EntityType.LINE,
                x=0,
                y=0,
                attributes={"end_point": (100, 0)},
            ),
            _entity(
                "2",
                layer="DOOR",
                entity_type=EntityType.LINE,
                x=50,
                y=50,
                attributes={"end_point": (50, 100)},
            ),
        ]
        ctx = _context(entities)
        analyzer = GridAnalyzer()
        result = analyzer.analyze(ctx, "grid summary")
        assert result.grid_lines == []
        has_no_grid_caveat = any("grid" in str(c).lower() for c in result.caveats) or any(
            "grid" in str(f).lower() for f in result.ambiguity_flags
        )
        assert has_no_grid_caveat, "Expected caveat about no grid entities"


# ---------------------------------------------------------------------------
# Vertical line detection
# ---------------------------------------------------------------------------


class TestVerticalLineDetection:
    def test_vertical_line_classified(self):
        """A vertical LINE (same x, different y) should be classified VERTICAL."""
        entities = [
            _entity(
                "V1",
                layer="GRID",
                entity_type=EntityType.LINE,
                x=10.0,
                y=0.0,
                attributes={"end_point": (10.0, 100.0)},
            ),
        ]
        ctx = _context(entities)
        analyzer = GridAnalyzer()
        result = analyzer.analyze(ctx, "grid summary")
        assert len(result.grid_lines) >= 1
        vlines = [gl for gl in result.grid_lines if gl.direction == GridDirection.VERTICAL]
        assert len(vlines) >= 1
        assert vlines[0].position == pytest.approx(10.0)

    def test_multiple_vertical_lines(self):
        entities = [
            _entity(
                "V1",
                layer="GRID",
                entity_type=EntityType.LINE,
                x=0.0,
                y=0.0,
                attributes={"end_point": (0.0, 100.0)},
            ),
            _entity(
                "V2",
                layer="GRID",
                entity_type=EntityType.LINE,
                x=30.0,
                y=0.0,
                attributes={"end_point": (30.0, 100.0)},
            ),
            _entity(
                "V3",
                layer="GRID",
                entity_type=EntityType.LINE,
                x=60.0,
                y=0.0,
                attributes={"end_point": (60.0, 100.0)},
            ),
        ]
        ctx = _context(entities)
        analyzer = GridAnalyzer()
        result = analyzer.analyze(ctx, "grid summary")
        vlines = [gl for gl in result.grid_lines if gl.direction == GridDirection.VERTICAL]
        assert len(vlines) == 3


# ---------------------------------------------------------------------------
# Horizontal line detection
# ---------------------------------------------------------------------------


class TestHorizontalLineDetection:
    def test_horizontal_line_classified(self):
        """A horizontal LINE (same y, different x) should be classified HORIZONTAL."""
        entities = [
            _entity(
                "H1",
                layer="GRID",
                entity_type=EntityType.LINE,
                x=0.0,
                y=20.0,
                attributes={"end_point": (100.0, 20.0)},
            ),
        ]
        ctx = _context(entities)
        analyzer = GridAnalyzer()
        result = analyzer.analyze(ctx, "grid summary")
        assert len(result.grid_lines) >= 1
        hlines = [gl for gl in result.grid_lines if gl.direction == GridDirection.HORIZONTAL]
        assert len(hlines) >= 1
        assert hlines[0].position == pytest.approx(20.0)

    def test_multiple_horizontal_lines(self):
        entities = [
            _entity(
                "H1",
                layer="GRID",
                entity_type=EntityType.LINE,
                x=0.0,
                y=0.0,
                attributes={"end_point": (100.0, 0.0)},
            ),
            _entity(
                "H2",
                layer="GRID",
                entity_type=EntityType.LINE,
                x=0.0,
                y=24.0,
                attributes={"end_point": (100.0, 24.0)},
            ),
        ]
        ctx = _context(entities)
        analyzer = GridAnalyzer()
        result = analyzer.analyze(ctx, "grid summary")
        hlines = [gl for gl in result.grid_lines if gl.direction == GridDirection.HORIZONTAL]
        assert len(hlines) == 2


# ---------------------------------------------------------------------------
# Diagonal lines skipped
# ---------------------------------------------------------------------------


class TestDiagonalLineSkipped:
    def test_diagonal_not_classified(self):
        """A diagonal LINE should not produce a grid line."""
        entities = [
            _entity(
                "D1",
                layer="GRID",
                entity_type=EntityType.LINE,
                x=0.0,
                y=0.0,
                attributes={"end_point": (100.0, 100.0)},
            ),
        ]
        ctx = _context(entities)
        analyzer = GridAnalyzer()
        result = analyzer.analyze(ctx, "grid summary")
        assert len(result.grid_lines) == 0

    def test_diagonal_among_others(self):
        """Diagonal lines are skipped, but valid H/V lines still detected."""
        entities = [
            _entity(
                "V1",
                layer="GRID",
                entity_type=EntityType.LINE,
                x=10.0,
                y=0.0,
                attributes={"end_point": (10.0, 100.0)},
            ),
            _entity(
                "D1",
                layer="GRID",
                entity_type=EntityType.LINE,
                x=0.0,
                y=0.0,
                attributes={"end_point": (50.0, 50.0)},
            ),
            _entity(
                "H1",
                layer="GRID",
                entity_type=EntityType.LINE,
                x=0.0,
                y=40.0,
                attributes={"end_point": (100.0, 40.0)},
            ),
        ]
        ctx = _context(entities)
        analyzer = GridAnalyzer()
        result = analyzer.analyze(ctx, "grid summary")
        assert len(result.grid_lines) == 2


# ---------------------------------------------------------------------------
# LWPOLYLINE detection
# ---------------------------------------------------------------------------


class TestPolylineDetection:
    def test_vertical_polyline(self):
        """A vertical LWPOLYLINE should be detected as a vertical grid line."""
        entities = [
            _entity(
                "P1",
                layer="GRID",
                entity_type=EntityType.LWPOLYLINE,
                x=15.0,
                y=0.0,
                attributes={"vertices": [(15.0, 0.0), (15.0, 200.0)]},
            ),
        ]
        ctx = _context(entities)
        analyzer = GridAnalyzer()
        result = analyzer.analyze(ctx, "grid summary")
        vlines = [gl for gl in result.grid_lines if gl.direction == GridDirection.VERTICAL]
        assert len(vlines) >= 1

    def test_horizontal_polyline(self):
        """A horizontal LWPOLYLINE should be detected as a horizontal grid line."""
        entities = [
            _entity(
                "P2",
                layer="GRID",
                entity_type=EntityType.LWPOLYLINE,
                x=0.0,
                y=50.0,
                attributes={"vertices": [(0.0, 50.0), (200.0, 50.0)]},
            ),
        ]
        ctx = _context(entities)
        analyzer = GridAnalyzer()
        result = analyzer.analyze(ctx, "grid summary")
        hlines = [gl for gl in result.grid_lines if gl.direction == GridDirection.HORIZONTAL]
        assert len(hlines) >= 1


# ---------------------------------------------------------------------------
# Bay computation
# ---------------------------------------------------------------------------


class TestBayComputation:
    def test_bay_between_vertical_lines(self):
        """Two vertical lines at x=0 and x=30 should produce a bay of dimension 30."""
        entities = [
            _entity(
                "V1",
                layer="GRID",
                entity_type=EntityType.LINE,
                x=0.0,
                y=0.0,
                attributes={"end_point": (0.0, 100.0)},
            ),
            _entity(
                "V2",
                layer="GRID",
                entity_type=EntityType.LINE,
                x=30.0,
                y=0.0,
                attributes={"end_point": (30.0, 100.0)},
            ),
        ]
        ctx = _context(entities)
        analyzer = GridAnalyzer()
        result = analyzer.analyze(ctx, "grid summary")
        assert len(result.bays) >= 1
        bay = result.bays[0]
        assert bay.dimension == pytest.approx(30.0)

    def test_bay_between_horizontal_lines(self):
        """Two horizontal lines at y=0 and y=24 should produce a bay of dimension 24."""
        entities = [
            _entity(
                "H1",
                layer="GRID",
                entity_type=EntityType.LINE,
                x=0.0,
                y=0.0,
                attributes={"end_point": (200.0, 0.0)},
            ),
            _entity(
                "H2",
                layer="GRID",
                entity_type=EntityType.LINE,
                x=0.0,
                y=24.0,
                attributes={"end_point": (200.0, 24.0)},
            ),
        ]
        ctx = _context(entities)
        analyzer = GridAnalyzer()
        result = analyzer.analyze(ctx, "grid summary")
        hbays = [b for b in result.bays if b.direction == GridDirection.HORIZONTAL]
        assert len(hbays) >= 1
        assert hbays[0].dimension == pytest.approx(24.0)

    def test_multiple_bays_sorted(self):
        """Three vertical lines produce two bays with correct dimensions."""
        entities = [
            _entity(
                "V1",
                layer="GRID",
                entity_type=EntityType.LINE,
                x=0.0,
                y=0.0,
                attributes={"end_point": (0.0, 100.0)},
            ),
            _entity(
                "V2",
                layer="GRID",
                entity_type=EntityType.LINE,
                x=20.0,
                y=0.0,
                attributes={"end_point": (20.0, 100.0)},
            ),
            _entity(
                "V3",
                layer="GRID",
                entity_type=EntityType.LINE,
                x=55.0,
                y=0.0,
                attributes={"end_point": (55.0, 100.0)},
            ),
        ]
        ctx = _context(entities)
        analyzer = GridAnalyzer()
        result = analyzer.analyze(ctx, "grid summary")
        vbays = [b for b in result.bays if b.direction == GridDirection.VERTICAL]
        assert len(vbays) == 2
        dims = sorted([b.dimension for b in vbays])
        assert dims[0] == pytest.approx(20.0)
        assert dims[1] == pytest.approx(35.0)


# ---------------------------------------------------------------------------
# Label extraction from nearby TEXT
# ---------------------------------------------------------------------------


class TestLabelExtraction:
    def test_label_from_nearby_text(self):
        """TEXT entity near a grid line should provide the label."""
        entities = [
            _entity(
                "V1",
                layer="GRID",
                entity_type=EntityType.LINE,
                x=10.0,
                y=0.0,
                attributes={"end_point": (10.0, 100.0)},
            ),
            _entity(
                "T1", layer="GRID", entity_type=EntityType.TEXT, x=10.0, y=-10.0, text_content="A"
            ),
        ]
        ctx = _context(entities)
        analyzer = GridAnalyzer()
        result = analyzer.analyze(ctx, "grid summary")
        vlines = [gl for gl in result.grid_lines if gl.direction == GridDirection.VERTICAL]
        assert len(vlines) >= 1
        assert vlines[0].label == "A"

    def test_no_label_caveat(self):
        """Grid lines without nearby labels should produce a caveat."""
        entities = [
            _entity(
                "V1",
                layer="GRID",
                entity_type=EntityType.LINE,
                x=10.0,
                y=0.0,
                attributes={"end_point": (10.0, 100.0)},
            ),
        ]
        ctx = _context(entities)
        analyzer = GridAnalyzer()
        result = analyzer.analyze(ctx, "grid summary")
        has_label_caveat = any(
            "label" in str(c).lower() or "no label" in str(c).lower() for c in result.caveats
        )
        assert has_label_caveat, "Expected caveat about missing labels"

    def test_text_too_far_not_used_as_label(self):
        """TEXT entity far from a grid line should not be used as label."""
        entities = [
            _entity(
                "V1",
                layer="GRID",
                entity_type=EntityType.LINE,
                x=10.0,
                y=0.0,
                attributes={"end_point": (10.0, 100.0)},
            ),
            # Place text far away (> 50 units threshold)
            _entity(
                "T1", layer="GRID", entity_type=EntityType.TEXT, x=500.0, y=500.0, text_content="Z"
            ),
        ]
        ctx = _context(entities)
        analyzer = GridAnalyzer()
        result = analyzer.analyze(ctx, "grid summary")
        vlines = [gl for gl in result.grid_lines if gl.direction == GridDirection.VERTICAL]
        assert len(vlines) >= 1
        # Label should NOT be "Z" since text is too far away
        assert vlines[0].label != "Z"


# ---------------------------------------------------------------------------
# Layer matching (case-insensitive, multiple layer names)
# ---------------------------------------------------------------------------


class TestLayerMatching:
    def test_case_insensitive_grid_layer(self):
        """Layer named 'grid_lines' should match grid detection."""
        entities = [
            _entity(
                "V1",
                layer="grid_lines",
                entity_type=EntityType.LINE,
                x=5.0,
                y=0.0,
                attributes={"end_point": (5.0, 80.0)},
            ),
        ]
        ctx = _context(entities)
        analyzer = GridAnalyzer()
        result = analyzer.analyze(ctx, "grid summary")
        assert len(result.grid_lines) >= 1

    def test_column_grid_layer(self):
        """Entities on COLUMN_GRID layer should be detected."""
        entities = [
            _entity(
                "V1",
                layer="COLUMN_GRID",
                entity_type=EntityType.LINE,
                x=25.0,
                y=0.0,
                attributes={"end_point": (25.0, 100.0)},
            ),
        ]
        ctx = _context(entities)
        analyzer = GridAnalyzer()
        result = analyzer.analyze(ctx, "grid summary")
        assert len(result.grid_lines) >= 1

    def test_axis_layer(self):
        """Entities on AXIS layer should be detected as grid lines."""
        entities = [
            _entity(
                "H1",
                layer="AXIS",
                entity_type=EntityType.LINE,
                x=0.0,
                y=15.0,
                attributes={"end_point": (100.0, 15.0)},
            ),
        ]
        ctx = _context(entities)
        analyzer = GridAnalyzer()
        result = analyzer.analyze(ctx, "grid summary")
        assert len(result.grid_lines) >= 1
        assert result.grid_lines[0].direction == GridDirection.HORIZONTAL


# ---------------------------------------------------------------------------
# Result metadata
# ---------------------------------------------------------------------------


class TestResultMetadata:
    def test_result_has_methodology(self):
        entities = [
            _entity(
                "V1",
                layer="GRID",
                entity_type=EntityType.LINE,
                x=0.0,
                y=0.0,
                attributes={"end_point": (0.0, 100.0)},
            ),
        ]
        ctx = _context(entities)
        analyzer = GridAnalyzer()
        result = analyzer.analyze(ctx, "grid summary")
        assert result.methodology is not None
        assert len(result.methodology) > 0

    def test_result_has_aggregate_confidence(self):
        entities = [
            _entity(
                "V1",
                layer="GRID",
                entity_type=EntityType.LINE,
                x=0.0,
                y=0.0,
                attributes={"end_point": (0.0, 100.0)},
            ),
        ]
        ctx = _context(entities)
        analyzer = GridAnalyzer()
        result = analyzer.analyze(ctx, "grid summary")
        assert 0.0 <= result.aggregate_confidence <= 1.0

    def test_result_has_drawing_summary(self):
        entities = [
            _entity(
                "V1",
                layer="GRID",
                entity_type=EntityType.LINE,
                x=0.0,
                y=0.0,
                attributes={"end_point": (0.0, 100.0)},
            ),
            _entity(
                "V2",
                layer="GRID",
                entity_type=EntityType.LINE,
                x=30.0,
                y=0.0,
                attributes={"end_point": (30.0, 100.0)},
            ),
        ]
        ctx = _context(entities)
        analyzer = GridAnalyzer()
        result = analyzer.analyze(ctx, "grid summary")
        assert result.drawing_summary is not None
        assert len(result.drawing_summary) > 0

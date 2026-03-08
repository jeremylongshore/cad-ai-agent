"""Anti-regression tests for the construction operations pipeline.

These tests guard invariants that must never break:
- No EditOperation objects leak into construction-ops results
- All generators are deterministic (no LLM calls)
- All results carry confidence, caveats, ambiguity_flags
- Results don't carry risk_level (that's a web-layer PlatformResponse concern)
- OCR-derived takeoff items must not claim high confidence
- All results are serialisable via model_dump()
- All generators handle empty drawings without crashing
"""

from __future__ import annotations

import pytest

from cad_dxf_agent.core.construction_ops import (
    BatchConditionPlanner,
    FieldSummaryBuilder,
    GridAnalyzer,
    MarkupRedlineGenerator,
)
from cad_dxf_agent.models.cad_schema import (
    DrawingContext,
    EntityRef,
    EntityType,
    LayerRule,
    Point2D,
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _entity(
    handle,
    layer="STRUCTURAL",
    entity_type=EntityType.INSERT,
    x=0.0,
    y=0.0,
    block_name="MARK",
    text_content=None,
    attributes=None,
):
    return EntityRef(
        handle=handle,
        entity_type=entity_type,
        layer=layer,
        insert_point=Point2D(x=x, y=y),
        block_name=block_name,
        text_content=text_content,
        attributes=attributes or {},
    )


def _context(entities):
    layer_names = sorted({e.layer for e in entities})
    return DrawingContext(
        file_path="test.dxf",
        entities=entities,
        layers=[LayerRule(name=n) for n in layer_names],
    )


def _rich_context():
    """20 block inserts spread across a wide area."""
    entities = [
        _entity(f"H{i:03d}", layer="STRUCTURAL", block_name="COL", x=float(i * 5), y=0.0)
        for i in range(20)
    ]
    return _context(entities)


def _grid_context():
    """Context with grid lines on GRID layer."""
    entities = [
        # Vertical grid lines
        EntityRef(
            handle=f"VG{i}",
            entity_type=EntityType.LINE,
            layer="GRID",
            insert_point=Point2D(x=float(i * 30), y=0.0),
            attributes={"end_point": (float(i * 30), 100.0)},
        )
        for i in range(3)
    ] + [
        # Some block inserts
        _entity(f"BLK{i}", block_name="COL", x=float(i * 30), y=50.0)
        for i in range(5)
    ]
    return _context(entities)


def _cloud_context():
    """Context with revision clouds on CLOUD layer."""
    entities = [
        EntityRef(
            handle="CLD1",
            entity_type=EntityType.LWPOLYLINE,
            layer="CLOUD",
            insert_point=Point2D(x=0.0, y=0.0),
            attributes={"vertices": [(0, 0), (100, 0), (100, 100), (0, 100)]},
        ),
        _entity("E1", x=50.0, y=50.0),
    ]
    return _context(entities)


def _empty_context():
    return _context([])


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

GENERATORS_AND_CONTEXTS = [
    ("grid", lambda: GridAnalyzer().analyze(_grid_context(), "grid")),
    ("redline", lambda: MarkupRedlineGenerator().generate(_cloud_context(), "redline")),
    ("condition", lambda: BatchConditionPlanner().plan(_rich_context(), "batch")),
    ("field_summary", lambda: FieldSummaryBuilder().build(_rich_context(), prompt="Summarize")),
]

GENERATOR_IDS = [g[0] for g in GENERATORS_AND_CONTEXTS]


# ---------------------------------------------------------------------------
# Tests: no EditOperation objects in results
# ---------------------------------------------------------------------------


class TestNoEditOperationLeak:
    """Construction-ops results must never contain EditOperation objects."""

    @pytest.mark.parametrize("name,factory", GENERATORS_AND_CONTEXTS, ids=GENERATOR_IDS)
    def test_no_operations_key_in_model_dump(self, name, factory):
        result = factory()
        dumped = result.model_dump()
        assert "operations" not in dumped, (
            f"{name} result contains 'operations' key in model_dump()"
        )

    @pytest.mark.parametrize("name,factory", GENERATORS_AND_CONTEXTS, ids=GENERATOR_IDS)
    def test_no_edit_operation_strings_in_dump(self, name, factory):
        result = factory()
        dumped_str = str(result.model_dump())
        for forbidden in ("op_type", "move_entity", "edit_text", "delete_entity", "add_block"):
            assert forbidden not in dumped_str, (
                f"{name} result contains '{forbidden}' in serialised output"
            )


# ---------------------------------------------------------------------------
# Tests: no LLM calls (deterministic generators)
# ---------------------------------------------------------------------------


class TestDeterministicGenerators:
    """All generators must produce results without any LLM calls."""

    def test_grid_analyzer_returns_result(self):
        result = GridAnalyzer().analyze(_grid_context(), "grid")
        assert result is not None

    def test_redline_generator_returns_result(self):
        result = MarkupRedlineGenerator().generate(_cloud_context(), "redline")
        assert result is not None

    def test_condition_planner_returns_result(self):
        result = BatchConditionPlanner().plan(_rich_context(), "batch")
        assert result is not None

    def test_field_summary_builder_returns_result(self):
        result = FieldSummaryBuilder().build(_rich_context(), prompt="Summarize")
        assert result is not None


# ---------------------------------------------------------------------------
# Tests: confidence, caveats, ambiguity_flags
# ---------------------------------------------------------------------------


class TestResultMetadata:
    """All results must carry confidence (>= 0), caveats (list), ambiguity_flags (list)."""

    @pytest.mark.parametrize("name,factory", GENERATORS_AND_CONTEXTS, ids=GENERATOR_IDS)
    def test_confidence_non_negative(self, name, factory):
        result = factory()
        # FieldSummary uses aggregate_confidence; others use confidence
        conf = getattr(result, "aggregate_confidence", None) or getattr(result, "confidence", None)
        assert conf is not None, f"{name} result has no confidence attribute"
        assert conf >= 0.0, f"{name} confidence is negative: {conf}"

    @pytest.mark.parametrize("name,factory", GENERATORS_AND_CONTEXTS, ids=GENERATOR_IDS)
    def test_caveats_is_list(self, name, factory):
        result = factory()
        assert isinstance(result.caveats, list), f"{name} caveats is not a list"

    @pytest.mark.parametrize("name,factory", GENERATORS_AND_CONTEXTS, ids=GENERATOR_IDS)
    def test_ambiguity_flags_is_list(self, name, factory):
        result = factory()
        assert isinstance(result.ambiguity_flags, list), f"{name} ambiguity_flags is not a list"


# ---------------------------------------------------------------------------
# Tests: no risk_level field on result schemas
# ---------------------------------------------------------------------------


class TestNoRiskLevel:
    """Construction-ops result schemas must not have a risk_level field.

    risk_level belongs on PlatformResponse at the web layer, not on
    the domain result objects themselves.
    """

    @pytest.mark.parametrize("name,factory", GENERATORS_AND_CONTEXTS, ids=GENERATOR_IDS)
    def test_no_risk_level_field(self, name, factory):
        result = factory()
        assert not hasattr(result, "risk_level"), (
            f"{name} result has risk_level attribute — this belongs on PlatformResponse"
        )


# ---------------------------------------------------------------------------
# Tests: OCR-derived takeoff items must not have high confidence
# ---------------------------------------------------------------------------


class TestOCRConfidenceBound:
    """If takeoff section contains OCR-derived text provenance items, their
    confidence must not be 'high' — OCR text cannot become exact truth."""

    def test_ocr_items_not_high_confidence(self):
        builder = FieldSummaryBuilder()
        result = builder.build(_rich_context(), prompt="Summarize takeoff")
        for section in result.sections:
            dumped = section.model_dump()
            items = dumped.get("items", [])
            if not isinstance(items, list):
                continue
            for item in items:
                if not isinstance(item, dict):
                    continue
                provenance = item.get("provenance", "")
                if "ocr" in str(provenance).lower():
                    item_conf = item.get("confidence", 0)
                    assert item_conf != "high" and item_conf < 1.0, (
                        f"OCR-derived takeoff item has improperly high confidence: {item}"
                    )


# ---------------------------------------------------------------------------
# Tests: serialisability
# ---------------------------------------------------------------------------


class TestSerialisability:
    """All four generators produce results that model_dump() to dict."""

    @pytest.mark.parametrize("name,factory", GENERATORS_AND_CONTEXTS, ids=GENERATOR_IDS)
    def test_model_dump_returns_dict(self, name, factory):
        result = factory()
        dumped = result.model_dump()
        assert isinstance(dumped, dict), f"{name} model_dump() did not return dict"


# ---------------------------------------------------------------------------
# Tests: empty-drawing robustness
# ---------------------------------------------------------------------------


class TestEmptyDrawingRobustness:
    """All four generators must handle an empty drawing context without crashing."""

    def test_grid_analyzer_empty(self):
        result = GridAnalyzer().analyze(_empty_context(), "grid")
        assert result is not None

    def test_redline_generator_empty(self):
        result = MarkupRedlineGenerator().generate(_empty_context(), "redline")
        assert result is not None

    def test_condition_planner_empty(self):
        result = BatchConditionPlanner().plan(_empty_context(), "batch")
        assert result is not None

    def test_field_summary_builder_empty(self):
        result = FieldSummaryBuilder().build(_empty_context(), prompt="Summarize")
        assert result is not None

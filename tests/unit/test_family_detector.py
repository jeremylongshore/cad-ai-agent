"""Tests for document family heuristic detector."""

from cad_dxf_agent.core.family_detector import (
    FamilyDetectionResult,
    detect_document_family,
)
from cad_dxf_agent.models.cad_schema import (
    DrawingContext,
    EntityRef,
    EntityType,
    LayerRule,
    Point2D,
)
from cad_dxf_agent.models.objective_schema import DocumentFamilyHint


def _make_context(
    *,
    layers: list[str] | None = None,
    blocks: list[str] | None = None,
    texts: list[tuple[str, str]] | None = None,
) -> DrawingContext:
    """Build a minimal DrawingContext with given layers, blocks, and texts."""
    layer_rules = [LayerRule(name=n) for n in (layers or ["0"])]
    entities: list[EntityRef] = []
    handle_counter = 1

    for text, layer in (texts or []):
        entities.append(EntityRef(
            handle=hex(handle_counter),
            entity_type=EntityType.TEXT,
            layer=layer,
            text_content=text,
            insert_point=Point2D(x=0, y=0),
        ))
        handle_counter += 1

    return DrawingContext(
        file_path="test.dxf",
        entities=entities,
        layers=layer_rules,
        blocks=blocks or [],
    )


class TestFamilyDetection:
    """Test document family detection from drawing signals."""

    def test_structural_drawing(self):
        ctx = _make_context(
            layers=["STRUCTURAL", "COLUMN_GRID", "BEAM", "NOTES"],
            blocks=["COLUMN_MARK"],
            texts=[
                ("Column C-4", "NOTES"),
                ("Beam B-12", "NOTES"),
                ("Foundation detail", "NOTES"),
            ],
        )
        result = detect_document_family(ctx)
        assert result.family == DocumentFamilyHint.STRUCTURAL
        assert result.confidence > 0.0
        assert result.signal_count >= 2

    def test_landscape_drawing(self):
        ctx = _make_context(
            layers=["PLANTING", "IRRIGATION", "LANDSCAPE", "HARDSCAPE"],
            blocks=["TREE_24", "SHRUB_5GAL"],
            texts=[
                ("Red Oak Tree", "PLANTING"),
                ("Irrigation zone 3", "IRRIGATION"),
            ],
        )
        result = detect_document_family(ctx)
        assert result.family == DocumentFamilyHint.LANDSCAPE

    def test_electrical_drawing(self):
        ctx = _make_context(
            layers=["E-POWER", "E-LIGHTING", "ELECTRICAL"],
            blocks=["OUTLET_DUPLEX", "SWITCH_3WAY"],
            texts=[
                ("Panel A - 200A", "E-POWER"),
                ("Circuit 14", "E-POWER"),
            ],
        )
        result = detect_document_family(ctx)
        assert result.family == DocumentFamilyHint.ELECTRICAL

    def test_residential_drawing(self):
        ctx = _make_context(
            layers=["WALLS", "DOORS", "WINDOWS", "NOTES"],
            texts=[
                ("Master Bedroom", "NOTES"),
                ("Kitchen", "NOTES"),
                ("Living Room", "NOTES"),
                ("Garage", "NOTES"),
                ("Bathroom", "NOTES"),
            ],
        )
        result = detect_document_family(ctx)
        assert result.family == DocumentFamilyHint.RESIDENTIAL_ARCHITECTURAL

    def test_commercial_drawing(self):
        ctx = _make_context(
            layers=["WALLS", "DOORS", "NOTES"],
            texts=[
                ("Lobby", "NOTES"),
                ("Elevator 1", "NOTES"),
                ("Office Suite 200", "NOTES"),
                ("Conference Room", "NOTES"),
            ],
        )
        result = detect_document_family(ctx)
        assert result.family == DocumentFamilyHint.COMMERCIAL_ARCHITECTURAL

    def test_plumbing_drawing(self):
        ctx = _make_context(
            layers=["P-SANITARY", "P-WATER", "PLUMBING"],
            texts=[
                ("Hot water riser", "P-WATER"),
                ("Toilet fixture", "P-SANITARY"),
                ("Drain pipe", "P-SANITARY"),
            ],
        )
        result = detect_document_family(ctx)
        assert result.family == DocumentFamilyHint.PLUMBING

    def test_mechanical_drawing(self):
        ctx = _make_context(
            layers=["M-DUCT", "MECHANICAL", "M-EQUIPMENT"],
            texts=[
                ("Supply duct", "M-DUCT"),
                ("Air handler AHU-1", "M-EQUIPMENT"),
                ("Return diffuser", "M-DUCT"),
            ],
        )
        result = detect_document_family(ctx)
        assert result.family == DocumentFamilyHint.MECHANICAL

    def test_unknown_for_empty_drawing(self):
        ctx = _make_context(layers=["0"])
        result = detect_document_family(ctx)
        assert result.family == DocumentFamilyHint.UNKNOWN
        assert result.confidence == 0.0

    def test_unknown_for_ambiguous_drawing(self):
        ctx = _make_context(
            layers=["MISC", "GENERAL", "LINES"],
        )
        result = detect_document_family(ctx)
        assert result.family == DocumentFamilyHint.UNKNOWN

    def test_below_threshold_returns_unknown(self):
        """Single match below _MIN_SIGNAL_THRESHOLD returns unknown."""
        ctx = _make_context(
            layers=["RANDOM_LAYER"],
            texts=[("one column mention", "RANDOM_LAYER")],
        )
        result = detect_document_family(ctx)
        # Even with 1 match, should be UNKNOWN (threshold is 2)
        assert result.family == DocumentFamilyHint.UNKNOWN

    def test_runner_up_populated(self):
        """When multiple families match, runner_up is set."""
        ctx = _make_context(
            layers=["STRUCTURAL", "PLUMBING", "COLUMN_GRID"],
            texts=[
                ("Column A", "STRUCTURAL"),
                ("Beam detail", "STRUCTURAL"),
                ("Pipe riser", "PLUMBING"),
                ("Drain line", "PLUMBING"),
            ],
        )
        result = detect_document_family(ctx)
        assert result.runner_up is not None


class TestDetectionResult:
    def test_result_fields(self):
        result = FamilyDetectionResult(
            family=DocumentFamilyHint.STRUCTURAL,
            confidence=0.85,
            signal_count=5,
            top_signals=["column", "beam"],
        )
        assert result.family == DocumentFamilyHint.STRUCTURAL
        assert result.confidence == 0.85
        assert result.signal_count == 5

    def test_confidence_range(self):
        ctx = _make_context(
            layers=["STRUCTURAL", "BEAM", "COLUMN"],
            texts=[
                ("Column C-4", "STRUCTURAL"),
                ("Beam B-12", "STRUCTURAL"),
                ("Steel detail", "STRUCTURAL"),
            ],
        )
        result = detect_document_family(ctx)
        assert 0.0 <= result.confidence <= 1.0

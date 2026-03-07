"""Anti-regression tests for design-ops pipeline.

Invariants enforced here:
- LayoutRecommender, RevisionSummarizer, TakeoffGenerator, and ScopeBuilder
  NEVER produce edit operations of any kind.
- OCR-derived text quantities are always capped at ESTIMATE_ONLY confidence.
- All result models are fully serializable via model_dump().
- No EditOperation or OpType references appear in any output.
"""

from __future__ import annotations

from cad_dxf_agent.core.design_ops import (
    LayoutRecommender,
    RevisionSummarizer,
    ScopeBuilder,
    TakeoffGenerator,
)
from cad_dxf_agent.models.cad_schema import (
    DrawingContext,
    EntityRef,
    EntityType,
    LayerRule,
    Point2D,
    TextGeometry,
    TextProvenance,
)
from cad_dxf_agent.models.design_ops_schema import TakeoffConfidence

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _entity(
    handle: str,
    layer: str = "STRUCTURAL",
    entity_type: EntityType = EntityType.INSERT,
    block_name: str | None = "MARK",
    x: float = 0.0,
    y: float = 0.0,
    text_content: str | None = None,
    text_geometry: TextGeometry | None = None,
) -> EntityRef:
    return EntityRef(
        handle=handle,
        entity_type=entity_type,
        layer=layer,
        block_name=block_name,
        insert_point=Point2D(x=x, y=y),
        text_content=text_content,
        text_geometry=text_geometry,
    )


def _context(entities: list[EntityRef]) -> DrawingContext:
    layer_names = sorted({e.layer for e in entities})
    return DrawingContext(
        file_path="test.dxf",
        entities=entities,
        layers=[LayerRule(name=n) for n in layer_names],
    )


def _rich_context() -> DrawingContext:
    """20 block inserts spread across a wide area to trigger density/block recs."""
    entities = [
        _entity(f"H{i:03d}", layer="STRUCTURAL", block_name="COL", x=float(i * 5), y=0.0)
        for i in range(20)
    ]
    return _context(entities)


def _ocr_text_entity(handle: str, text: str, layer: str = "NOTES") -> EntityRef:
    tg = TextGeometry.for_provenance(TextProvenance.RASTER_OCR_TEXT, height=2.5)
    return _entity(
        handle=handle,
        layer=layer,
        entity_type=EntityType.TEXT,
        block_name=None,
        text_content=text,
        text_geometry=tg,
    )


def _native_text_entity(handle: str, text: str, layer: str = "NOTES") -> EntityRef:
    tg = TextGeometry.for_provenance(TextProvenance.NATIVE_CAD_TEXT, height=2.5)
    return _entity(
        handle=handle,
        layer=layer,
        entity_type=EntityType.TEXT,
        block_name=None,
        text_content=text,
        text_geometry=tg,
    )


def _comparison_with_adds() -> object:
    from cad_dxf_agent.models.comparison_schema import (
        ChangeCategory,
        ComparisonResult,
        EntityChange,
        GeometrySnapshot,
    )

    snap = GeometrySnapshot(
        handle="CMP1",
        entity_type=EntityType.LINE,
        layer="STRUCTURAL",
        points=[Point2D(x=0, y=0), Point2D(x=10, y=0)],
    )
    return ComparisonResult(
        changes=[
            EntityChange(category=ChangeCategory.ADDED, revision_snapshot=snap, confidence=0.85)
        ],
        summary={"added": 1, "removed": 0, "modified": 0, "moved": 0, "unchanged": 0},
    )


# ---------------------------------------------------------------------------
# No operations in model_dump() — four analyzers
# ---------------------------------------------------------------------------


class TestNoEditOperationsInOutput:
    def test_layout_recommender_has_no_operations_key(self):
        ctx = _rich_context()
        result = LayoutRecommender().recommend(ctx, "suggest improvements")
        dumped = result.model_dump()
        assert "operations" not in dumped, (
            "LayoutRecommendationResult must not contain an 'operations' key"
        )

    def test_revision_summarizer_has_no_operations_key(self):
        comparison = _comparison_with_adds()
        result = RevisionSummarizer().summarize(comparison_result=comparison)
        dumped = result.model_dump()
        assert "operations" not in dumped, (
            "CustomerRevisionSummary must not contain an 'operations' key"
        )

    def test_takeoff_generator_has_no_operations_key(self):
        ctx = _rich_context()
        result = TakeoffGenerator().generate(ctx, "estimate columns")
        dumped = result.model_dump()
        assert "operations" not in dumped, (
            "TakeoffCandidateResult must not contain an 'operations' key"
        )

    def test_scope_builder_has_no_operations_key(self):
        ctx = _rich_context()
        result = ScopeBuilder().build(ctx, "scope of work")
        dumped = result.model_dump()
        assert "operations" not in dumped, "ScopeSummary must not contain an 'operations' key"

    def test_no_op_type_in_layout_output(self):
        ctx = _rich_context()
        result = LayoutRecommender().recommend(ctx, "suggest improvements")
        dumped_str = str(result.model_dump())
        assert "op_type" not in dumped_str

    def test_no_op_type_in_takeoff_output(self):
        ctx = _rich_context()
        result = TakeoffGenerator().generate(ctx, "takeoff estimate")
        dumped_str = str(result.model_dump())
        assert "op_type" not in dumped_str

    def test_no_edit_operation_class_in_scope_output(self):
        """Verify no EditOperation or OpType values appear in any section content."""
        ctx = _rich_context()
        comparison = _comparison_with_adds()
        scope = ScopeBuilder().build(ctx, "scope of work", comparison_result=comparison)
        for section in scope.sections:
            content_str = str(section.content)
            assert "EditOperation" not in content_str
            # OpType string values: move_entity, edit_text, delete_entity, add_block
            for op_val in ("move_entity", "edit_text", "delete_entity", "add_block"):
                assert op_val not in content_str, (
                    f"Section '{section.section_type}' content references op_type '{op_val}'"
                )


# ---------------------------------------------------------------------------
# OCR text provenance: confidence caps
# ---------------------------------------------------------------------------


class TestOCRTextConfidenceCap:
    def test_ocr_text_quantity_is_estimate_only(self):
        entities = [_ocr_text_entity("T1", "12 ea columns")]
        ctx = _context(entities)
        result = TakeoffGenerator().generate(ctx, "takeoff estimate")
        ocr_items = [
            item for item in result.items if item.confidence == TakeoffConfidence.ESTIMATE_ONLY
        ]
        assert len(ocr_items) >= 1, "OCR-derived quantity must be ESTIMATE_ONLY"

    def test_ocr_text_quantity_has_provenance_warning(self):
        entities = [_ocr_text_entity("T1", "12 ea columns")]
        ctx = _context(entities)
        result = TakeoffGenerator().generate(ctx, "takeoff estimate")
        assert len(result.provenance_warnings) >= 1

    def test_ocr_text_quantity_has_caveat_about_ocr(self):
        entities = [_ocr_text_entity("T1", "12 ea columns")]
        ctx = _context(entities)
        result = TakeoffGenerator().generate(ctx, "takeoff estimate")
        ocr_items = [
            item for item in result.items if item.confidence == TakeoffConfidence.ESTIMATE_ONLY
        ]
        assert len(ocr_items) >= 1
        ocr_item = ocr_items[0]
        assert any("OCR" in c or "inaccurate" in c for c in ocr_item.caveats)

    def test_many_ocr_matches_cannot_become_high_confidence(self):
        """Flooding OCR text into the drawing must never yield HIGH confidence items."""
        entities = [_ocr_text_entity(f"T{i}", f"{i + 1} ea columns") for i in range(30)]
        ctx = _context(entities)
        result = TakeoffGenerator().generate(ctx, "takeoff estimate")
        for item in result.items:
            # Text-derived items originating from OCR must stay at ESTIMATE_ONLY
            if item.text_provenance is not None:
                assert item.confidence != TakeoffConfidence.HIGH, (
                    f"OCR item '{item.name}' must not reach HIGH confidence"
                )

    def test_native_cad_text_not_downgraded_to_estimate_only(self):
        """Native CAD text quantities must not be penalised to ESTIMATE_ONLY."""
        entities = [_native_text_entity("T1", "5 ea beams")]
        ctx = _context(entities)
        result = TakeoffGenerator().generate(ctx, "takeoff estimate")
        native_items = [
            item for item in result.items if item.text_provenance == TextProvenance.NATIVE_CAD_TEXT
        ]
        assert len(native_items) >= 1
        for item in native_items:
            assert item.confidence != TakeoffConfidence.ESTIMATE_ONLY, (
                "Native CAD text quantity was incorrectly downgraded to ESTIMATE_ONLY"
            )


# ---------------------------------------------------------------------------
# Low-confidence propagation to layout recommendations
# ---------------------------------------------------------------------------


class TestLowConfidencePropagation:
    def test_low_trust_text_adds_caveat_to_layout_result(self):
        entities = [_entity(f"I{i}", block_name="COL", x=float(i * 5)) for i in range(20)] + [
            _ocr_text_entity("T1", "notes here", layer="NOTES")
        ]
        ctx = _context(entities)
        result = LayoutRecommender().recommend(ctx, "suggest improvements")
        # Low-trust text triggers a GENERAL_OBSERVATION recommendation with caveats
        all_caveats = [c for rec in result.recommendations for c in rec.caveats]
        # At minimum the limitations list or rec caveats should mention text
        assert result.limitations or all_caveats or result.ambiguity_flags


# ---------------------------------------------------------------------------
# Empty-drawing robustness
# ---------------------------------------------------------------------------


class TestEmptyDrawingRobustness:
    def test_layout_recommender_empty_drawing_does_not_crash(self):
        ctx = _context([])
        result = LayoutRecommender().recommend(ctx, "suggest improvements")
        assert result is not None

    def test_revision_summarizer_no_data_does_not_crash(self):
        result = RevisionSummarizer().summarize()
        assert result is not None
        assert result.headline != ""

    def test_takeoff_generator_empty_drawing_does_not_crash(self):
        ctx = _context([])
        result = TakeoffGenerator().generate(ctx, "takeoff estimate")
        assert result is not None

    def test_scope_builder_empty_drawing_does_not_crash(self):
        ctx = _context([])
        result = ScopeBuilder().build(ctx, "scope of work")
        assert result is not None


# ---------------------------------------------------------------------------
# Serialisability
# ---------------------------------------------------------------------------


class TestSerialisation:
    def test_layout_result_serialisable(self):
        ctx = _rich_context()
        result = LayoutRecommender().recommend(ctx, "suggest improvements")
        dumped = result.model_dump()
        assert isinstance(dumped, dict)

    def test_revision_summary_serialisable(self):
        comparison = _comparison_with_adds()
        result = RevisionSummarizer().summarize(comparison_result=comparison)
        dumped = result.model_dump()
        assert isinstance(dumped, dict)

    def test_takeoff_result_serialisable(self):
        ctx = _rich_context()
        result = TakeoffGenerator().generate(ctx, "takeoff estimate")
        dumped = result.model_dump()
        assert isinstance(dumped, dict)

    def test_scope_result_serialisable(self):
        ctx = _rich_context()
        comparison = _comparison_with_adds()
        result = ScopeBuilder().build(ctx, "scope of work", comparison_result=comparison)
        dumped = result.model_dump()
        assert isinstance(dumped, dict)


# ---------------------------------------------------------------------------
# Confidence bounds for sparse evidence
# ---------------------------------------------------------------------------


class TestSparseEvidenceConfidence:
    def test_sparse_drawing_confidence_below_one(self):
        """With only one entity, aggregate confidence must be strictly below 1.0."""
        entities = [_entity("H001", block_name="COL")]
        ctx = _context(entities)
        result = LayoutRecommender().recommend(ctx, "suggest improvements")
        # Either no recommendations (empty = 0.0) or confidence < 1.0
        assert result.aggregate_confidence < 1.0

    def test_layout_recommendations_have_bounded_confidence(self):
        """Every individual recommendation confidence must be in [0, 1]."""
        ctx = _rich_context()
        result = LayoutRecommender().recommend(ctx, "suggest improvements")
        for rec in result.recommendations:
            assert 0.0 <= rec.confidence <= 1.0, (
                f"Recommendation '{rec.title}' has out-of-bounds confidence {rec.confidence}"
            )

"""Tests for LayoutRecommender (design_ops EPIC-CAD-09).

Covers:
- Empty drawing path
- Non-empty drawing produces recommendations
- Layer concentration detection (>60%, >10 entities)
- No concentration when evenly distributed
- Block placement pattern detection (3+ repeated blocks)
- Entity density calculation
- Low-trust text detection (RASTER_OCR_TEXT)
- No low-trust warning when all text is native CAD
- Region context reduces confidence
- Truncated context adds ambiguity flag
- Sparse text evidence reduces confidence
- Aggregate confidence is min of all recommendations
- Drawing summary content
- Anti-regression: no EditOperation objects in result
"""

from __future__ import annotations

from cad_dxf_agent.core.design_ops import LayoutRecommender
from cad_dxf_agent.models.cad_schema import (
    DrawingContext,
    EntityRef,
    EntityType,
    LayerRule,
    Point2D,
    TextGeometry,
    TextProvenance,
)
from cad_dxf_agent.models.design_ops_schema import RecommendationType
from cad_dxf_agent.models.qna_schema import RegionContext

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _entity(
    handle: str,
    layer: str = "STRUCTURAL",
    entity_type: EntityType = EntityType.LINE,
    text: str | None = None,
    block_name: str | None = None,
    x: float = 0.0,
    y: float = 0.0,
    text_geometry: TextGeometry | None = None,
) -> EntityRef:
    return EntityRef(
        handle=handle,
        entity_type=entity_type,
        layer=layer,
        text_content=text,
        block_name=block_name,
        insert_point=Point2D(x=x, y=y) if (x or y) else None,
        text_geometry=text_geometry,
    )


def _context(entities: list[EntityRef], layers: list[str] | None = None) -> DrawingContext:
    layer_names = layers or sorted({e.layer for e in entities})
    return DrawingContext(
        file_path="test.dxf",
        entities=entities,
        layers=[LayerRule(name=n) for n in layer_names],
    )


def _region(
    entities: list[EntityRef],
    *,
    is_whole_drawing: bool = False,
    ambiguity_flags: list[str] | None = None,
) -> RegionContext:
    layers = sorted({e.layer for e in entities})
    layer_counts = {}
    for e in entities:
        layer_counts[e.layer] = layer_counts.get(e.layer, 0) + 1
    return RegionContext(
        entities=entities,
        text_entities=[e for e in entities if e.entity_type in (EntityType.TEXT, EntityType.MTEXT)],
        dimension_entities=[],
        block_refs=[e for e in entities if e.entity_type == EntityType.INSERT],
        layers=layers,
        layer_counts=layer_counts,
        block_names=sorted({e.block_name for e in entities if e.block_name}),
        entity_count=len(entities),
        total_drawing_entities=100,
        confidence=0.8,
        ambiguity_flags=ambiguity_flags or [],
        is_whole_drawing=is_whole_drawing,
    )


_recommender = LayoutRecommender()


# ---------------------------------------------------------------------------
# Empty drawing
# ---------------------------------------------------------------------------


class TestEmptyDrawing:
    def test_empty_drawing_returns_empty_recommendations(self):
        ctx = _context([])
        result = _recommender.recommend(ctx, "analyze layout")
        assert result.recommendations == []

    def test_empty_drawing_sets_empty_drawing_flag(self):
        ctx = _context([])
        result = _recommender.recommend(ctx, "analyze layout")
        assert "empty_drawing" in result.ambiguity_flags

    def test_empty_drawing_summary_describes_empty(self):
        ctx = _context([])
        result = _recommender.recommend(ctx, "analyze layout")
        assert "empty" in result.drawing_summary.lower()


# ---------------------------------------------------------------------------
# Non-empty drawing produces recommendations
# ---------------------------------------------------------------------------


class TestNonEmptyDrawing:
    def test_drawing_with_entities_returns_result(self):
        entities = [_entity(f"H{i}", x=float(i), y=float(i)) for i in range(5)]
        ctx = _context(entities)
        result = _recommender.recommend(ctx, "analyze layout")
        # Result should be a valid LayoutRecommendationResult with a drawing_summary
        assert result.drawing_summary != ""

    def test_drawing_with_many_entities_has_nonzero_summary_count(self):
        entities = [_entity(f"H{i}", x=float(i * 10), y=float(i * 10)) for i in range(15)]
        ctx = _context(entities)
        result = _recommender.recommend(ctx, "analyze layout")
        assert "15 entities" in result.drawing_summary


# ---------------------------------------------------------------------------
# Layer concentration
# ---------------------------------------------------------------------------


class TestLayerConcentration:
    def test_detects_concentration_above_60_percent_with_more_than_10_entities(self):
        # 9 of 11 entities on STRUCTURAL = 81.8%
        dominant = [_entity(f"S{i}", layer="STRUCTURAL") for i in range(9)]
        others = [_entity(f"O{i}", layer="NOTES") for i in range(2)]
        ctx = _context(dominant + others)
        result = _recommender.recommend(ctx, "check layers")
        types = [r.type for r in result.recommendations]
        assert RecommendationType.GENERAL_OBSERVATION in types
        titles = [r.title for r in result.recommendations]
        assert any("STRUCTURAL" in t for t in titles)

    def test_no_concentration_warning_when_evenly_distributed(self):
        # 5 entities per layer, 4 layers = 25% each — no concentration
        entities = []
        for layer in ("A", "B", "C", "D"):
            for i in range(5):
                entities.append(_entity(f"{layer}{i}", layer=layer))
        ctx = _context(entities)
        result = _recommender.recommend(ctx, "check layers")
        titles = [r.title for r in result.recommendations]
        assert not any("concentration" in t.lower() for t in titles)

    def test_no_concentration_warning_when_total_is_10_or_fewer(self):
        # 8 of 10 on one layer = 80%, but total == 10 so threshold not met (> 10 required)
        dominant = [_entity(f"S{i}", layer="STRUCTURAL") for i in range(8)]
        others = [_entity(f"O{i}", layer="NOTES") for i in range(2)]
        ctx = _context(dominant + others)
        result = _recommender.recommend(ctx, "check layers")
        titles = [r.title for r in result.recommendations]
        assert not any("concentration" in t.lower() for t in titles)


# ---------------------------------------------------------------------------
# Block placement patterns
# ---------------------------------------------------------------------------


class TestBlockPlacementPatterns:
    def test_detects_repeated_block_with_3_or_more_instances(self):
        inserts = [
            _entity(f"I{i}", entity_type=EntityType.INSERT, block_name="COL-A", x=float(i * 5))
            for i in range(4)
        ]
        ctx = _context(inserts)
        result = _recommender.recommend(ctx, "find patterns")
        types = [r.type for r in result.recommendations]
        assert RecommendationType.REGION_USAGE in types
        titles = [r.title for r in result.recommendations]
        assert any("COL-A" in t for t in titles)

    def test_no_block_recommendation_for_fewer_than_3_instances(self):
        inserts = [
            _entity(f"I{i}", entity_type=EntityType.INSERT, block_name="COL-A", x=float(i * 5))
            for i in range(2)
        ]
        ctx = _context(inserts)
        result = _recommender.recommend(ctx, "find patterns")
        types = [r.type for r in result.recommendations]
        assert RecommendationType.REGION_USAGE not in types

    def test_block_recommendation_confidence_is_high(self):
        # Block recs start at 0.90. A drawing with no text entities triggers the
        # sparse_text_evidence penalty (-0.15), landing at 0.75. Add 3+ text
        # entities so the sparse penalty does not fire and confidence stays at 0.90.
        inserts = [
            _entity(f"I{i}", entity_type=EntityType.INSERT, block_name="BEAM", x=float(i * 5))
            for i in range(5)
        ]
        text_ents = [
            _entity(
                f"T{i}", entity_type=EntityType.TEXT, text=f"Label {i}", x=float(i * 50), y=100.0
            )
            for i in range(3)
        ]
        ctx = _context(inserts + text_ents)
        result = _recommender.recommend(ctx, "find patterns")
        block_recs = [
            r for r in result.recommendations if r.type == RecommendationType.REGION_USAGE
        ]
        assert block_recs, "Expected at least one REGION_USAGE recommendation"
        assert all(r.confidence >= 0.8 for r in block_recs)


# ---------------------------------------------------------------------------
# Entity density
# ---------------------------------------------------------------------------


class TestEntityDensity:
    def test_high_density_produces_placement_guidance(self):
        # 10 entities in a 3x3 area → density > 0.1
        entities = [_entity(f"E{i}", x=float(i % 3), y=float(i // 3)) for i in range(10)]
        ctx = _context(entities)
        result = _recommender.recommend(ctx, "check density")
        types = [r.type for r in result.recommendations]
        assert RecommendationType.PLACEMENT_GUIDANCE in types

    def test_low_density_produces_no_density_recommendation(self):
        # 5 entities spread across 1000 units — density far below 0.1
        entities = [_entity(f"E{i}", x=float(i * 200), y=0.0) for i in range(5)]
        ctx = _context(entities)
        result = _recommender.recommend(ctx, "check density")
        types = [r.type for r in result.recommendations]
        assert RecommendationType.PLACEMENT_GUIDANCE not in types


# ---------------------------------------------------------------------------
# Low-trust text detection
# ---------------------------------------------------------------------------


class TestLowTrustTextDetection:
    def test_ocr_text_triggers_low_trust_warning(self):
        ocr_geom = TextGeometry.for_provenance(TextProvenance.RASTER_OCR_TEXT)
        text_ent = _entity(
            "T1",
            entity_type=EntityType.TEXT,
            text="12 pcs",
            text_geometry=ocr_geom,
        )
        ctx = _context([text_ent])
        result = _recommender.recommend(ctx, "check text")
        types = [r.type for r in result.recommendations]
        assert RecommendationType.GENERAL_OBSERVATION in types
        titles = [r.title for r in result.recommendations]
        assert any("low-trust" in t.lower() for t in titles)

    def test_native_cad_text_produces_no_low_trust_warning(self):
        native_geom = TextGeometry.for_provenance(TextProvenance.NATIVE_CAD_TEXT)
        text_ent = _entity(
            "T1",
            entity_type=EntityType.TEXT,
            text="Footing schedule",
            text_geometry=native_geom,
        )
        ctx = _context([text_ent])
        result = _recommender.recommend(ctx, "check text")
        titles = [r.title for r in result.recommendations]
        assert not any("low-trust" in t.lower() for t in titles)

    def test_no_text_entities_skips_text_analysis(self):
        entities = [_entity(f"L{i}") for i in range(5)]
        ctx = _context(entities)
        result = _recommender.recommend(ctx, "check text")
        # No crash and no low-trust recommendation
        titles = [r.title for r in result.recommendations]
        assert not any("low-trust" in t.lower() for t in titles)


# ---------------------------------------------------------------------------
# Region context effects
# ---------------------------------------------------------------------------


class TestRegionContext:
    def test_partial_region_adds_partial_region_flag(self):
        # Need enough entities that there's at least one recommendation to downgrade
        inserts = [
            _entity(f"I{i}", entity_type=EntityType.INSERT, block_name="DOOR", x=float(i))
            for i in range(4)
        ]
        ctx = _context(inserts)
        region = _region(inserts, is_whole_drawing=False)
        result = _recommender.recommend(ctx, "check region", region=region)
        assert "partial_region" in result.ambiguity_flags

    def test_whole_drawing_region_no_partial_flag(self):
        entities = [_entity(f"E{i}", x=float(i)) for i in range(5)]
        ctx = _context(entities)
        region = _region(entities, is_whole_drawing=True)
        result = _recommender.recommend(ctx, "check region", region=region)
        assert "partial_region" not in result.ambiguity_flags

    def test_partial_region_reduces_confidence_of_recommendations(self):
        # Build a scenario that produces a high-confidence block recommendation,
        # then verify confidence is reduced when a partial region is supplied.
        inserts = [
            _entity(f"I{i}", entity_type=EntityType.INSERT, block_name="COL", x=float(i * 5))
            for i in range(4)
        ]
        ctx = _context(inserts)

        result_no_region = _recommender.recommend(ctx, "p")
        block_recs_no_region = [
            r for r in result_no_region.recommendations if r.type == RecommendationType.REGION_USAGE
        ]

        region = _region(inserts, is_whole_drawing=False)
        result_with_region = _recommender.recommend(ctx, "p", region=region)
        block_recs_with_region = [
            r
            for r in result_with_region.recommendations
            if r.type == RecommendationType.REGION_USAGE
        ]

        if block_recs_no_region and block_recs_with_region:
            assert block_recs_with_region[0].confidence < block_recs_no_region[0].confidence

    def test_truncated_context_adds_context_truncated_flag(self):
        entities = [
            _entity(f"I{i}", entity_type=EntityType.INSERT, block_name="BEAM", x=float(i))
            for i in range(4)
        ]
        ctx = _context(entities)
        region = _region(entities, ambiguity_flags=["context_truncated"])
        result = _recommender.recommend(ctx, "check", region=region)
        assert "context_truncated" in result.ambiguity_flags


# ---------------------------------------------------------------------------
# Sparse text evidence
# ---------------------------------------------------------------------------


class TestSparseTextEvidence:
    def test_fewer_than_3_text_entities_adds_sparse_flag(self):
        # 2 text entities + several lines → sparse
        entities = [
            _entity("T1", entity_type=EntityType.TEXT, text="Label A"),
            _entity("T2", entity_type=EntityType.TEXT, text="Label B"),
            _entity("L1"),
            _entity("L2"),
            _entity("L3"),
        ]
        ctx = _context(entities)
        result = _recommender.recommend(ctx, "check labels")
        assert "sparse_text_evidence" in result.ambiguity_flags

    def test_three_or_more_text_entities_no_sparse_flag(self):
        entities = [
            _entity(f"T{i}", entity_type=EntityType.TEXT, text=f"Label {i}") for i in range(4)
        ]
        # Add some spread so density doesn't kick in
        for i, e in enumerate(entities):
            e.insert_point = Point2D(x=float(i * 100), y=0.0)
        ctx = _context(entities)
        result = _recommender.recommend(ctx, "check labels")
        assert "sparse_text_evidence" not in result.ambiguity_flags

    def test_sparse_text_reduces_recommendation_confidence(self):
        # Block recs start at 0.90; after sparse (-0.15) should be ≤ 0.75
        inserts = [
            _entity(f"I{i}", entity_type=EntityType.INSERT, block_name="DOOR", x=float(i * 5))
            for i in range(4)
        ]
        # Only 1 text entity — sparse
        text_ent = _entity("T1", entity_type=EntityType.TEXT, text="Note")
        ctx = _context(inserts + [text_ent])
        result = _recommender.recommend(ctx, "check")
        block_recs = [
            r for r in result.recommendations if r.type == RecommendationType.REGION_USAGE
        ]
        if block_recs:
            assert block_recs[0].confidence <= 0.75


# ---------------------------------------------------------------------------
# Aggregate confidence
# ---------------------------------------------------------------------------


class TestAggregateConfidence:
    def test_aggregate_confidence_is_min_of_all_recommendations(self):
        # Produce both a block rec (0.90) and an OCR-text rec (0.60)
        # after sparse reduction (2 text entities → -0.15 each), OCR rec = 0.45, block = 0.75
        # aggregate = min = 0.45
        inserts = [
            _entity(f"I{i}", entity_type=EntityType.INSERT, block_name="COL", x=float(i * 5))
            for i in range(4)
        ]
        ocr_geom = TextGeometry.for_provenance(TextProvenance.RASTER_OCR_TEXT)
        text_ents = [
            _entity("T1", entity_type=EntityType.TEXT, text="OCR label", text_geometry=ocr_geom),
            _entity("T2", entity_type=EntityType.TEXT, text="Another label"),
        ]
        ctx = _context(inserts + text_ents)
        result = _recommender.recommend(ctx, "analyze")
        if result.recommendations:
            expected_min = min(r.confidence for r in result.recommendations)
            assert abs(result.aggregate_confidence - round(expected_min, 2)) < 1e-6

    def test_empty_recommendations_give_zero_aggregate_confidence(self):
        ctx = _context([])
        result = _recommender.recommend(ctx, "analyze")
        assert result.aggregate_confidence == 0.0


# ---------------------------------------------------------------------------
# Drawing summary
# ---------------------------------------------------------------------------


class TestDrawingSummary:
    def test_summary_includes_entity_count(self):
        entities = [_entity(f"E{i}", x=float(i)) for i in range(7)]
        ctx = _context(entities)
        result = _recommender.recommend(ctx, "summarize")
        assert "7" in result.drawing_summary

    def test_summary_includes_layer_count(self):
        entities = [
            _entity("E1", layer="A"),
            _entity("E2", layer="B"),
            _entity("E3", layer="C"),
        ]
        ctx = _context(entities)
        result = _recommender.recommend(ctx, "summarize")
        assert "3" in result.drawing_summary


# ---------------------------------------------------------------------------
# Anti-regression: no edit operations
# ---------------------------------------------------------------------------


class TestNoEditOperationsProduced:
    def test_result_has_no_operations_attribute(self):
        entities = [_entity(f"E{i}", x=float(i)) for i in range(5)]
        ctx = _context(entities)
        result = _recommender.recommend(ctx, "layout advice")
        assert not hasattr(result, "operations")

    def test_result_has_no_edit_operation_objects(self):
        from cad_dxf_agent.models.ops_schema import EditOperation

        entities = [_entity(f"E{i}", x=float(i)) for i in range(5)]
        ctx = _context(entities)
        result = _recommender.recommend(ctx, "layout advice")
        # Walk the recommendations and assert none contain EditOperation instances
        for rec in result.recommendations:
            assert not isinstance(rec, EditOperation)
            for ev in rec.evidence:
                assert not isinstance(ev, EditOperation)

    def test_design_ops_never_returns_edit_operation_type(self):
        from cad_dxf_agent.models.ops_schema import EditOperation

        # Even with a complex drawing, LayoutRecommender must not produce EditOperations
        inserts = [
            _entity(f"I{i}", entity_type=EntityType.INSERT, block_name="BEAM", x=float(i * 5))
            for i in range(5)
        ]
        dominant = [_entity(f"S{i}", layer="DOMINANT") for i in range(10)]
        entities = inserts + dominant
        ctx = _context(entities)
        result = _recommender.recommend(ctx, "redesign layout")

        def _contains_edit_op(obj: object) -> bool:
            if isinstance(obj, EditOperation):
                return True
            if isinstance(obj, list):
                return any(_contains_edit_op(item) for item in obj)
            return False

        assert not _contains_edit_op(result.recommendations)

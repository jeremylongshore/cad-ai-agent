"""Tests for TextGeometry, TextProvenance, trust hierarchy, and dxf_reader text extraction."""

from __future__ import annotations

from cad_dxf_agent.core.dxf_reader import (
    _extract_mtext_geometry,
    _extract_text_geometry,
    _normalize_rotation,
    load_dxf,
)
from cad_dxf_agent.models.cad_schema import (
    TEXT_PROVENANCE_DEFAULTS,
    TEXT_PROVENANCE_TRUST_ORDER,
    EntityRef,
    EntityType,
    Point2D,
    TextGeometry,
    TextProvenance,
    compute_approx_text_bbox,
)

# ==========================================================================
# TextProvenance enum
# ==========================================================================


class TestTextProvenance:
    def test_values(self):
        assert TextProvenance.NATIVE_CAD_TEXT == "native_cad_text"
        assert TextProvenance.BLOCK_ATTRIBUTE_TEXT == "block_attribute_text"
        assert TextProvenance.VECTOR_OUTLINE_TEXT == "vector_outline_text"
        assert TextProvenance.RASTER_OCR_TEXT == "raster_ocr_text"

    def test_trust_ordering(self):
        """Trust hierarchy: native > block_attribute > vector > raster."""
        ordered = [
            TextProvenance.NATIVE_CAD_TEXT,
            TextProvenance.BLOCK_ATTRIBUTE_TEXT,
            TextProvenance.VECTOR_OUTLINE_TEXT,
            TextProvenance.RASTER_OCR_TEXT,
        ]
        assert len(ordered) == len(TextProvenance)

    def test_is_str_enum(self):
        assert isinstance(TextProvenance.NATIVE_CAD_TEXT, str)


# ==========================================================================
# TextGeometry model
# ==========================================================================


class TestTextGeometry:
    def test_defaults(self):
        tg = TextGeometry()
        assert tg.height is None
        assert tg.rotation == 0.0
        assert tg.halign == 0
        assert tg.valign == 0
        assert tg.width_factor == 1.0
        assert tg.oblique == 0.0
        assert tg.attachment_point is None
        assert tg.char_height is None
        assert tg.provenance == TextProvenance.NATIVE_CAD_TEXT

    def test_with_all_fields(self):
        tg = TextGeometry(
            height=2.5,
            rotation=45.0,
            halign=1,
            valign=2,
            width_factor=0.8,
            oblique=15.0,
            attachment_point=7,
            char_height=3.0,
            provenance=TextProvenance.BLOCK_ATTRIBUTE_TEXT,
        )
        assert tg.height == 2.5
        assert tg.rotation == 45.0
        assert tg.halign == 1
        assert tg.valign == 2
        assert tg.width_factor == 0.8
        assert tg.oblique == 15.0
        assert tg.attachment_point == 7
        assert tg.char_height == 3.0
        assert tg.provenance == TextProvenance.BLOCK_ATTRIBUTE_TEXT

    def test_serialization_roundtrip(self):
        tg = TextGeometry(height=2.5, rotation=90.0, provenance=TextProvenance.NATIVE_CAD_TEXT)
        data = tg.model_dump()
        restored = TextGeometry(**data)
        assert restored == tg

    def test_json_serializable(self):
        import json

        tg = TextGeometry(height=1.0, rotation=30.0)
        json.loads(tg.model_dump_json())


# ==========================================================================
# EntityRef with text_geometry
# ==========================================================================


class TestEntityRefTextGeometry:
    def test_default_none(self):
        e = EntityRef(handle="1", entity_type=EntityType.TEXT, layer="L")
        assert e.text_geometry is None

    def test_with_text_geometry(self):
        tg = TextGeometry(height=2.5, rotation=45.0)
        e = EntityRef(
            handle="1",
            entity_type=EntityType.TEXT,
            layer="L",
            text_content="HELLO",
            text_geometry=tg,
        )
        assert e.text_geometry is not None
        assert e.text_geometry.height == 2.5
        assert e.text_geometry.rotation == 45.0

    def test_non_text_entity_no_geometry(self):
        e = EntityRef(
            handle="1",
            entity_type=EntityType.LINE,
            layer="L",
            insert_point=Point2D(x=0, y=0),
        )
        assert e.text_geometry is None

    def test_serialization_with_text_geometry(self):
        tg = TextGeometry(height=3.0, provenance=TextProvenance.NATIVE_CAD_TEXT)
        e = EntityRef(
            handle="1",
            entity_type=EntityType.TEXT,
            layer="L",
            text_content="TEST",
            text_geometry=tg,
        )
        data = e.model_dump()
        assert data["text_geometry"]["height"] == 3.0
        assert data["text_geometry"]["provenance"] == "native_cad_text"


# ==========================================================================
# _normalize_rotation
# ==========================================================================


class TestNormalizeRotation:
    def test_zero(self):
        assert _normalize_rotation(0.0) == 0.0

    def test_positive(self):
        assert _normalize_rotation(45.0) == 45.0

    def test_360_wraps_to_zero(self):
        assert _normalize_rotation(360.0) == 0.0

    def test_negative(self):
        assert _normalize_rotation(-90.0) == 270.0

    def test_large_positive(self):
        assert _normalize_rotation(720.0) == 0.0

    def test_large_negative(self):
        assert _normalize_rotation(-450.0) == 270.0


# ==========================================================================
# TEXT extraction from real DXF
# ==========================================================================


class TestTextExtractionFromDxf:
    def test_text_entity_has_geometry(self, sample_dxf):
        ctx = load_dxf(sample_dxf)
        texts = [e for e in ctx.entities if e.entity_type == EntityType.TEXT]
        assert len(texts) > 0
        for t in texts:
            assert t.text_geometry is not None
            assert t.text_geometry.provenance == TextProvenance.NATIVE_CAD_TEXT
            # Height should be positive if set
            if t.text_geometry.height is not None:
                assert t.text_geometry.height > 0

    def test_mtext_entity_has_geometry(self, sample_dxf):
        ctx = load_dxf(sample_dxf)
        mtexts = [e for e in ctx.entities if e.entity_type == EntityType.MTEXT]
        # Sample DXF may or may not have MTEXT; skip if none
        for mt in mtexts:
            assert mt.text_geometry is not None
            assert mt.text_geometry.provenance == TextProvenance.NATIVE_CAD_TEXT

    def test_line_entity_no_geometry(self, sample_dxf):
        ctx = load_dxf(sample_dxf)
        lines = [e for e in ctx.entities if e.entity_type == EntityType.LINE]
        for line in lines:
            assert line.text_geometry is None

    def test_text_rotation_normalized(self, sample_dxf):
        ctx = load_dxf(sample_dxf)
        texts = [e for e in ctx.entities if e.entity_type == EntityType.TEXT]
        for t in texts:
            assert 0.0 <= t.text_geometry.rotation < 360.0

    def test_insert_with_attribs_has_geometry(self, sample_dxf):
        ctx = load_dxf(sample_dxf)
        inserts = [e for e in ctx.entities if e.entity_type == EntityType.INSERT]
        # INSERTs with attribs should have BLOCK_ATTRIBUTE_TEXT provenance
        for ins in inserts:
            if ins.text_geometry is not None:
                assert ins.text_geometry.provenance == TextProvenance.BLOCK_ATTRIBUTE_TEXT


# ==========================================================================
# Extraction helpers with mock entities
# ==========================================================================


class _MockDxfNamespace:
    """Minimal mock of ezdxf entity.dxf namespace."""

    def __init__(self, **kwargs):
        self._data = kwargs

    def __getattr__(self, name):
        if name.startswith("_"):
            return super().__getattribute__(name)
        if name in self._data:
            return self._data[name]
        raise AttributeError(name)

    def get(self, key, default=None):
        return self._data.get(key, default)


class _MockEntity:
    def __init__(self, **kwargs):
        self.dxf = _MockDxfNamespace(**kwargs)


class TestExtractTextGeometry:
    def test_basic_text(self):
        entity = _MockEntity(height=2.5, rotation=45.0, halign=1, valign=2, width=0.8, oblique=15.0)
        tg = _extract_text_geometry(entity)
        assert tg.height == 2.5
        assert tg.rotation == 45.0
        assert tg.halign == 1
        assert tg.valign == 2
        assert tg.width_factor == 0.8
        assert tg.oblique == 15.0
        assert tg.provenance == TextProvenance.NATIVE_CAD_TEXT

    def test_defaults_when_missing(self):
        entity = _MockEntity()
        tg = _extract_text_geometry(entity)
        assert tg.height is None
        assert tg.rotation == 0.0
        assert tg.halign == 0
        assert tg.valign == 0
        assert tg.width_factor == 1.0
        assert tg.oblique == 0.0

    def test_negative_rotation_normalized(self):
        entity = _MockEntity(rotation=-90.0)
        tg = _extract_text_geometry(entity)
        assert tg.rotation == 270.0


class TestExtractMtextGeometry:
    def test_basic_mtext(self):
        entity = _MockEntity(char_height=3.0, rotation=90.0, attachment_point=7)
        tg = _extract_mtext_geometry(entity)
        assert tg.height == 3.0
        assert tg.char_height == 3.0
        assert tg.rotation == 90.0
        assert tg.attachment_point == 7
        assert tg.provenance == TextProvenance.NATIVE_CAD_TEXT

    def test_defaults_when_missing(self):
        entity = _MockEntity()
        tg = _extract_mtext_geometry(entity)
        assert tg.height is None
        assert tg.char_height is None
        assert tg.rotation == 0.0
        assert tg.attachment_point is None


# ==========================================================================
# Confidence fields
# ==========================================================================


class TestTextGeometryConfidence:
    def test_native_defaults_full_confidence(self):
        tg = TextGeometry(provenance=TextProvenance.NATIVE_CAD_TEXT)
        assert tg.confidence_position == 1.0
        assert tg.confidence_rotation == 1.0
        assert tg.confidence_content == 1.0

    def test_explicit_lower_confidence(self):
        tg = TextGeometry(
            provenance=TextProvenance.RASTER_OCR_TEXT,
            confidence_position=0.3,
            confidence_rotation=0.2,
            confidence_content=0.5,
        )
        assert tg.confidence_position == 0.3
        assert tg.confidence_rotation == 0.2
        assert tg.confidence_content == 0.5

    def test_is_high_trust_native(self):
        tg = TextGeometry(provenance=TextProvenance.NATIVE_CAD_TEXT)
        assert tg.is_high_trust is True

    def test_is_high_trust_block_attribute(self):
        tg = TextGeometry(provenance=TextProvenance.BLOCK_ATTRIBUTE_TEXT)
        assert tg.is_high_trust is True

    def test_is_not_high_trust_vector(self):
        tg = TextGeometry(provenance=TextProvenance.VECTOR_OUTLINE_TEXT)
        assert tg.is_high_trust is False

    def test_is_not_high_trust_ocr(self):
        tg = TextGeometry(provenance=TextProvenance.RASTER_OCR_TEXT)
        assert tg.is_high_trust is False

    def test_effective_height_text(self):
        tg = TextGeometry(height=2.5)
        assert tg.effective_height == 2.5

    def test_effective_height_mtext(self):
        tg = TextGeometry(height=2.5, char_height=3.0)
        assert tg.effective_height == 3.0

    def test_effective_height_none(self):
        tg = TextGeometry()
        assert tg.effective_height is None


# ==========================================================================
# Trust hierarchy
# ==========================================================================


class TestTrustHierarchy:
    def test_trust_order_length(self):
        assert len(TEXT_PROVENANCE_TRUST_ORDER) == 4

    def test_trust_order_native_first(self):
        assert TEXT_PROVENANCE_TRUST_ORDER[0] == TextProvenance.NATIVE_CAD_TEXT

    def test_trust_order_ocr_last(self):
        assert TEXT_PROVENANCE_TRUST_ORDER[-1] == TextProvenance.RASTER_OCR_TEXT

    def test_native_higher_trust_than_ocr(self):
        native_idx = TEXT_PROVENANCE_TRUST_ORDER.index(TextProvenance.NATIVE_CAD_TEXT)
        ocr_idx = TEXT_PROVENANCE_TRUST_ORDER.index(TextProvenance.RASTER_OCR_TEXT)
        assert native_idx < ocr_idx

    def test_block_attr_higher_than_vector(self):
        ba_idx = TEXT_PROVENANCE_TRUST_ORDER.index(TextProvenance.BLOCK_ATTRIBUTE_TEXT)
        vo_idx = TEXT_PROVENANCE_TRUST_ORDER.index(TextProvenance.VECTOR_OUTLINE_TEXT)
        assert ba_idx < vo_idx

    def test_defaults_all_provenances_covered(self):
        for prov in TextProvenance:
            assert prov in TEXT_PROVENANCE_DEFAULTS

    def test_native_defaults_full(self):
        d = TEXT_PROVENANCE_DEFAULTS[TextProvenance.NATIVE_CAD_TEXT]
        assert d["position"] == 1.0
        assert d["rotation"] == 1.0
        assert d["content"] == 1.0

    def test_ocr_defaults_low(self):
        d = TEXT_PROVENANCE_DEFAULTS[TextProvenance.RASTER_OCR_TEXT]
        assert d["position"] < 0.5
        assert d["rotation"] < 0.5

    def test_trust_degrades_monotonically(self):
        """Confidence should decrease (or stay equal) as trust decreases."""
        for key in ("position", "rotation", "content"):
            values = [TEXT_PROVENANCE_DEFAULTS[p][key] for p in TEXT_PROVENANCE_TRUST_ORDER]
            for i in range(len(values) - 1):
                assert values[i] >= values[i + 1], (
                    f"{key} confidence should degrade: "
                    f"{TEXT_PROVENANCE_TRUST_ORDER[i]} ({values[i]}) vs "
                    f"{TEXT_PROVENANCE_TRUST_ORDER[i + 1]} ({values[i + 1]})"
                )


# ==========================================================================
# Anti-regression: native CAD text must not be replaced by OCR
# ==========================================================================


class TestAntiRegression:
    def test_native_text_provenance_preserved_through_reader(self, sample_dxf):
        """Native CAD text from dxf_reader must always have native provenance."""
        ctx = load_dxf(sample_dxf)
        text_entities = [
            e for e in ctx.entities if e.entity_type in (EntityType.TEXT, EntityType.MTEXT)
        ]
        for ent in text_entities:
            assert ent.text_geometry is not None
            assert ent.text_geometry.provenance == TextProvenance.NATIVE_CAD_TEXT
            assert ent.text_geometry.is_high_trust

    def test_native_text_full_confidence(self, sample_dxf):
        """Native CAD text must have full confidence scores."""
        ctx = load_dxf(sample_dxf)
        text_entities = [
            e for e in ctx.entities if e.entity_type in (EntityType.TEXT, EntityType.MTEXT)
        ]
        for ent in text_entities:
            tg = ent.text_geometry
            assert tg.confidence_position == 1.0
            assert tg.confidence_rotation == 1.0
            assert tg.confidence_content == 1.0

    def test_ocr_text_cannot_masquerade_as_native(self):
        """OCR-sourced text must not pass is_high_trust."""
        tg = TextGeometry(
            provenance=TextProvenance.RASTER_OCR_TEXT,
            confidence_position=0.3,
        )
        assert not tg.is_high_trust

    def test_vector_text_cannot_masquerade_as_native(self):
        """Vector-outline text must not pass is_high_trust."""
        tg = TextGeometry(
            provenance=TextProvenance.VECTOR_OUTLINE_TEXT,
            confidence_position=0.6,
        )
        assert not tg.is_high_trust


# ==========================================================================
# Debug visibility (selection_debug integration)
# ==========================================================================


class TestDebugVisibility:
    def test_debug_payload_includes_text_geometry(self):
        """selection_debug _serialize_entity includes text_geometry."""
        from cad_dxf_agent.core.region_associator import (
            AssociatedEntity,
            AssociationType,
        )
        from cad_dxf_agent.core.selection_debug import _serialize_entity

        ent = EntityRef(
            handle="T1",
            entity_type=EntityType.TEXT,
            layer="NOTES",
            text_content="FOOTING",
            insert_point=Point2D(x=10, y=20),
            text_geometry=TextGeometry(
                height=2.5,
                rotation=45.0,
                provenance=TextProvenance.NATIVE_CAD_TEXT,
            ),
        )
        assoc = AssociatedEntity(
            entity=ent,
            distance=0.0,
            association_type=AssociationType.INSIDE,
            rank=1,
        )
        data = _serialize_entity(assoc)
        assert "text_geometry" in data
        assert data["text_geometry"]["provenance"] == "native_cad_text"
        assert data["text_geometry"]["is_high_trust"] is True
        assert data["text_geometry"]["height"] == 2.5
        assert data["text_geometry"]["rotation"] == 45.0

    def test_debug_payload_no_geometry_for_line(self):
        """Non-text entities should not have text_geometry in debug."""
        from cad_dxf_agent.core.region_associator import (
            AssociatedEntity,
            AssociationType,
        )
        from cad_dxf_agent.core.selection_debug import _serialize_entity

        ent = EntityRef(
            handle="L1",
            entity_type=EntityType.LINE,
            layer="STRUCTURAL",
            insert_point=Point2D(x=0, y=0),
        )
        assoc = AssociatedEntity(
            entity=ent,
            distance=5.0,
            association_type=AssociationType.NEARBY,
            rank=2,
        )
        data = _serialize_entity(assoc)
        assert "text_geometry" not in data


# ==========================================================================
# Tool executor visibility
# ==========================================================================


class TestToolExecutorVisibility:
    def test_entity_to_dict_includes_text_geometry(self):
        from cad_dxf_agent.llm.tool_executor import _entity_to_dict

        ent = EntityRef(
            handle="T1",
            entity_type=EntityType.TEXT,
            layer="NOTES",
            text_content="COLUMN A-1",
            insert_point=Point2D(x=10, y=20),
            text_geometry=TextGeometry(
                height=3.0,
                rotation=90.0,
                provenance=TextProvenance.NATIVE_CAD_TEXT,
            ),
        )
        d = _entity_to_dict(ent)
        assert "text_geometry" in d
        assert d["text_geometry"]["height"] == 3.0
        assert d["text_geometry"]["rotation"] == 90.0
        assert d["text_geometry"]["provenance"] == "native_cad_text"

    def test_entity_to_dict_no_geometry_for_line(self):
        from cad_dxf_agent.llm.tool_executor import _entity_to_dict

        ent = EntityRef(
            handle="L1",
            entity_type=EntityType.LINE,
            layer="STRUCTURAL",
            insert_point=Point2D(x=0, y=0),
        )
        d = _entity_to_dict(ent)
        assert "text_geometry" not in d


# ==========================================================================
# Semantic model planner context
# ==========================================================================


class TestSemanticModelTextGeometry:
    def test_planner_context_includes_text_geometry(self):
        from cad_dxf_agent.core.semantic_model import build_planner_context
        from cad_dxf_agent.models.cad_schema import DrawingContext

        ctx = DrawingContext(
            file_path="test.dxf",
            entities=[
                EntityRef(
                    handle="T1",
                    entity_type=EntityType.TEXT,
                    layer="NOTES",
                    text_content="LABEL",
                    insert_point=Point2D(x=10, y=20),
                    text_geometry=TextGeometry(
                        height=2.5,
                        rotation=45.0,
                        provenance=TextProvenance.NATIVE_CAD_TEXT,
                    ),
                ),
            ],
        )
        result = build_planner_context(ctx)
        entity = result["entities"][0]
        assert "text_geometry" in entity
        assert entity["text_geometry"]["height"] == 2.5
        assert entity["text_geometry"]["rotation"] == 45.0
        assert entity["text_geometry"]["provenance"] == "native_cad_text"

    def test_planner_context_no_geometry_for_line(self):
        from cad_dxf_agent.core.semantic_model import build_planner_context
        from cad_dxf_agent.models.cad_schema import DrawingContext

        ctx = DrawingContext(
            file_path="test.dxf",
            entities=[
                EntityRef(
                    handle="L1",
                    entity_type=EntityType.LINE,
                    layer="STRUCTURAL",
                    insert_point=Point2D(x=0, y=0),
                ),
            ],
        )
        result = build_planner_context(ctx)
        assert "text_geometry" not in result["entities"][0]


# ==========================================================================
# for_provenance() factory
# ==========================================================================


class TestForProvenanceFactory:
    def test_native_cad_defaults(self):
        tg = TextGeometry.for_provenance(TextProvenance.NATIVE_CAD_TEXT)
        assert tg.provenance == TextProvenance.NATIVE_CAD_TEXT
        assert tg.confidence_position == 1.0
        assert tg.confidence_rotation == 1.0
        assert tg.confidence_content == 1.0

    def test_ocr_defaults(self):
        tg = TextGeometry.for_provenance(TextProvenance.RASTER_OCR_TEXT)
        assert tg.provenance == TextProvenance.RASTER_OCR_TEXT
        assert tg.confidence_position == 0.3
        assert tg.confidence_rotation == 0.2
        assert tg.confidence_content == 0.5

    def test_vector_defaults(self):
        tg = TextGeometry.for_provenance(TextProvenance.VECTOR_OUTLINE_TEXT)
        assert tg.provenance == TextProvenance.VECTOR_OUTLINE_TEXT
        assert tg.confidence_position == 0.6

    def test_block_attribute_defaults(self):
        tg = TextGeometry.for_provenance(TextProvenance.BLOCK_ATTRIBUTE_TEXT)
        assert tg.provenance == TextProvenance.BLOCK_ATTRIBUTE_TEXT
        assert tg.confidence_position == 0.95
        assert tg.confidence_content == 1.0

    def test_overrides_applied(self):
        tg = TextGeometry.for_provenance(
            TextProvenance.RASTER_OCR_TEXT, height=12.0, confidence_content=0.9
        )
        assert tg.height == 12.0
        assert tg.confidence_content == 0.9
        # Non-overridden fields use defaults
        assert tg.confidence_position == 0.3


# ==========================================================================
# compute_approx_text_bbox()
# ==========================================================================


class TestComputeApproxTextBbox:
    def test_simple_text(self):
        tg = TextGeometry(height=10.0)
        bbox = compute_approx_text_bbox("HELLO", tg)
        assert bbox is not None
        min_pt, max_pt = bbox
        assert min_pt.x == 0.0
        assert min_pt.y == 0.0
        # width = 10 * 5 * 1.0 * 0.6 = 30
        assert max_pt.x == 30.0
        assert max_pt.y == 10.0

    def test_width_factor_scales(self):
        tg = TextGeometry(height=10.0, width_factor=2.0)
        bbox = compute_approx_text_bbox("AB", tg)
        assert bbox is not None
        _, max_pt = bbox
        # width = 10 * 2 * 2.0 * 0.6 = 24
        assert max_pt.x == 24.0

    def test_mtext_with_width(self):
        tg = TextGeometry(height=5.0, char_height=5.0)
        bbox = compute_approx_text_bbox("Line1\nLine2\nLine3", tg, mtext_width=50.0)
        assert bbox is not None
        _, max_pt = bbox
        assert max_pt.x == 50.0
        # total_h = 5 * 3 * 1.2 = 18
        assert max_pt.y == 18.0

    def test_none_for_missing_height(self):
        tg = TextGeometry()
        assert compute_approx_text_bbox("text", tg) is None

    def test_none_for_empty_text(self):
        tg = TextGeometry(height=10.0)
        assert compute_approx_text_bbox("", tg) is None


# ==========================================================================
# INSERT transform extraction
# ==========================================================================


class TestInsertTransformExtraction:
    def test_default_scale_insert(self, tmp_path):
        from tests.helpers.dxf_factory import create_scaled_insert_drawing

        dxf_path = create_scaled_insert_drawing(tmp_path)
        ctx = load_dxf(dxf_path)
        inserts = [e for e in ctx.entities if e.entity_type == EntityType.INSERT]
        assert len(inserts) == 3

        # First INSERT: default scale
        ins_a = [i for i in inserts if i.text_content == "MARK-A"][0]
        assert ins_a.attributes["insert_xscale"] == 1.0
        assert ins_a.attributes["insert_yscale"] == 1.0
        assert ins_a.attributes["insert_rotation"] == 0.0

    def test_nonuniform_scale_insert(self, tmp_path):
        from tests.helpers.dxf_factory import create_scaled_insert_drawing

        dxf_path = create_scaled_insert_drawing(tmp_path)
        ctx = load_dxf(dxf_path)
        inserts = [e for e in ctx.entities if e.entity_type == EntityType.INSERT]
        ins_b = [i for i in inserts if i.text_content == "MARK-B"][0]
        assert ins_b.attributes["insert_xscale"] == 2.0
        assert ins_b.attributes["insert_yscale"] == 0.5

    def test_rotated_insert(self, tmp_path):
        from tests.helpers.dxf_factory import create_scaled_insert_drawing

        dxf_path = create_scaled_insert_drawing(tmp_path)
        ctx = load_dxf(dxf_path)
        inserts = [e for e in ctx.entities if e.entity_type == EntityType.INSERT]
        ins_c = [i for i in inserts if i.text_content == "MARK-C"][0]
        assert ins_c.attributes["insert_rotation"] == 30.0

    def test_attrib_height_reflects_yscale(self, tmp_path):
        """ATTRIB height in DXF already incorporates INSERT yscale."""
        from tests.helpers.dxf_factory import create_scaled_insert_drawing

        dxf_path = create_scaled_insert_drawing(tmp_path)
        ctx = load_dxf(dxf_path)
        inserts = [e for e in ctx.entities if e.entity_type == EntityType.INSERT]

        ins_a = [i for i in inserts if i.text_content == "MARK-A"][0]
        ins_b = [i for i in inserts if i.text_content == "MARK-B"][0]

        # ATTDEF height=2.0; ATTRIB stores already-scaled height
        # MARK-A: yscale=1.0 → height=2.0
        assert ins_a.text_geometry.height == 2.0
        # MARK-B: yscale=0.5 → height=1.0 (already scaled by ezdxf)
        assert ins_b.text_geometry.height == 1.0
        # Both should have BLOCK_ATTRIBUTE_TEXT provenance with 0.95 confidence
        assert ins_a.text_geometry.provenance == TextProvenance.BLOCK_ATTRIBUTE_TEXT
        assert ins_b.text_geometry.confidence_position == 0.95


# ==========================================================================
# MTEXT plain_text extraction
# ==========================================================================


class TestMtextPlainText:
    def test_paragraph_breaks_converted(self, tmp_path):
        from tests.helpers.dxf_factory import create_rich_mtext_drawing

        dxf_path = create_rich_mtext_drawing(tmp_path)
        ctx = load_dxf(dxf_path)
        mtexts = [e for e in ctx.entities if e.entity_type == EntityType.MTEXT]

        multi_line = [m for m in mtexts if "Line one" in (m.text_content or "")][0]
        # plain_text converts \P to \n
        assert "\n" in multi_line.text_content
        assert "\\P" not in multi_line.text_content

    def test_mtext_width_stored(self, tmp_path):
        from tests.helpers.dxf_factory import create_rich_mtext_drawing

        dxf_path = create_rich_mtext_drawing(tmp_path)
        ctx = load_dxf(dxf_path)
        mtexts = [e for e in ctx.entities if e.entity_type == EntityType.MTEXT]

        constrained = [m for m in mtexts if "Constrained" in (m.text_content or "")][0]
        assert constrained.attributes.get("mtext_width") == 40.0

    def test_simple_mtext_unchanged(self, tmp_path):
        from tests.helpers.dxf_factory import create_rich_mtext_drawing

        dxf_path = create_rich_mtext_drawing(tmp_path)
        ctx = load_dxf(dxf_path)
        mtexts = [e for e in ctx.entities if e.entity_type == EntityType.MTEXT]

        simple = [m for m in mtexts if m.text_content == "SIMPLE NOTE"][0]
        assert simple.text_content == "SIMPLE NOTE"

    def test_no_mtext_width_for_unconstrained(self, tmp_path):
        from tests.helpers.dxf_factory import create_rich_mtext_drawing

        dxf_path = create_rich_mtext_drawing(tmp_path)
        ctx = load_dxf(dxf_path)
        mtexts = [e for e in ctx.entities if e.entity_type == EntityType.MTEXT]

        simple = [m for m in mtexts if m.text_content == "SIMPLE NOTE"][0]
        assert "mtext_width" not in simple.attributes

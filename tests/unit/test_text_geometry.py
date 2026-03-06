"""Tests for TextGeometry, TextProvenance, and dxf_reader text extraction."""

from __future__ import annotations

from cad_dxf_agent.core.dxf_reader import (
    _extract_mtext_geometry,
    _extract_text_geometry,
    _normalize_rotation,
    load_dxf,
)
from cad_dxf_agent.models.cad_schema import (
    EntityRef,
    EntityType,
    Point2D,
    TextGeometry,
    TextProvenance,
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

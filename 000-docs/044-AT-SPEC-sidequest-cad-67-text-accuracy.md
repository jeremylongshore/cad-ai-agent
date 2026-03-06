# 044-AT-SPEC: SIDEQUEST-CAD-67 -- Text / Label Positional Accuracy

## Problem Statement

User feedback: "Text, such as labels and size labels, must be positioned accurately. Texts extracted through vector contour detection / OCR do not have accurate position, size, or orientation."

Text entities in the system were treated as opaque strings with an insertion point. The `EntityRef` model discarded text height, rotation, alignment, width factor, oblique angle, and attachment point -- all properties that ezdxf makes available from native DXF TEXT and MTEXT entities.

## User Impact

- Labels appear spatially wrong when text height/rotation is ignored
- Size labels lose scale context
- Title block text loses alignment anchoring
- Construction users cannot trust annotation placement
- Compare workflows cannot detect text geometry changes (resized, rotated labels)
- Q&A answers lack text size/orientation context

## Root Cause Analysis

### Audit Findings

| Text Path | Status Before | Issue |
|-----------|---------------|-------|
| `dxf_reader.py` TEXT | insert_point + text only | Lost height, rotation, halign, valign, width_factor, oblique |
| `dxf_reader.py` MTEXT | insert_point + text only | Lost char_height, rotation, attachment_point |
| `dxf_reader.py` INSERT | insert_point + block_name | ATTRIB text not extracted at all |
| `comparison/geometry.py` | Same losses | GeometrySnapshot mirrored the reader gaps |
| `semantic_model.py` | "text" key only | Planner never saw text geometry |
| `tool_executor.py` | "text" key only | Agent tools never returned text geometry |
| `selection_debug.py` | text_content only | Debug output had no provenance/geometry |
| PDF converter | No text extraction | Geometry only -- by design |
| OCR module | Does not exist | No OCR in codebase |
| Vector contour text | Does not exist | No contour-to-text in codebase |

**Root cause**: `EntityRef` was a lossy model. The DXF reader extracted only `insert_point` and `text_content`, discarding all text rendering geometry that ezdxf provides.

**Clarification**: OCR and vector contour text extraction do not exist in the codebase. The user's feedback about these sources relates to future capabilities. The immediate fix is preserving native CAD text geometry that is already available.

## Architecture Changes

### New Types (cad_schema.py)

```python
class TextProvenance(StrEnum):
    NATIVE_CAD_TEXT = "native_cad_text"         # Highest trust
    BLOCK_ATTRIBUTE_TEXT = "block_attribute_text"
    VECTOR_OUTLINE_TEXT = "vector_outline_text"  # Future
    RASTER_OCR_TEXT = "raster_ocr_text"          # Future, lowest trust

class TextGeometry(BaseModel):
    height: float | None
    rotation: float           # Normalized to [0, 360)
    halign: int               # TEXT horizontal alignment
    valign: int               # TEXT vertical alignment
    width_factor: float       # Character width scale
    oblique: float            # Oblique angle in degrees
    attachment_point: int     # MTEXT attachment (1-9)
    char_height: float        # MTEXT character height
    provenance: TextProvenance
    confidence_position: float   # [0-1], 1.0 for native CAD
    confidence_rotation: float   # [0-1], 1.0 for native CAD
    confidence_content: float    # [0-1], 1.0 for native CAD

    @property effective_height -> float | None  # char_height or height
    @property is_high_trust -> bool             # native or block_attribute
```

### Trust Hierarchy

| Rank | Provenance | Position Conf | Rotation Conf | Content Conf | Use Case |
|------|-----------|---------------|---------------|-------------|----------|
| 1 | `native_cad_text` | 1.0 | 1.0 | 1.0 | DXF TEXT/MTEXT entities |
| 2 | `block_attribute_text` | 0.95 | 0.95 | 1.0 | INSERT ATTRIB text |
| 3 | `vector_outline_text` | 0.6 | 0.5 | 0.7 | Future: exploded text recovery |
| 4 | `raster_ocr_text` | 0.3 | 0.2 | 0.5 | Future: OCR fallback |

**Enforcement rule**: `is_high_trust` returns True only for native_cad_text and block_attribute_text. Lower-trust sources must never silently masquerade as exact CAD text.

### Files Changed

| File | Change |
|------|--------|
| `models/cad_schema.py` | Added TextProvenance, TextGeometry, TEXT_PROVENANCE_TRUST_ORDER, TEXT_PROVENANCE_DEFAULTS; EntityRef gains text_geometry field |
| `core/dxf_reader.py` | TEXT extracts height/rotation/halign/valign/width_factor/oblique; MTEXT extracts char_height/rotation/attachment_point; INSERT extracts ATTRIB text with geometry |
| `core/semantic_model.py` | Planner context includes text_geometry (height, rotation, provenance) |
| `core/selection_debug.py` | Debug payload and text output include provenance, confidence, is_high_trust |
| `core/qna_pipeline.py` | Entity descriptions include height and rotation when present |
| `core/comparison/geometry.py` | GeometrySnapshot captures text geometry from TEXT/MTEXT |
| `core/comparison/classifier.py` | Detects text_height and text_rotation modifications between master/revision |
| `models/comparison_schema.py` | GeometrySnapshot gains text_geometry field |
| `llm/tool_executor.py` | Agent tool results include text_geometry (height, rotation, provenance) |

### Downstream Integration

| Surface | How Text Geometry Is Used |
|---------|--------------------------|
| EPIC-CAD-03 (Selection) | Debug payload shows provenance + confidence for selected text entities |
| EPIC-CAD-04 (Q&A) | Evidence descriptions include text height/rotation |
| EPIC-CAD-06 (Compare) | Detects text height/rotation changes as distinct modifications |
| EPIC-CAD-07 (Edit Planning) | Planner context includes text geometry for targeting decisions |
| EPIC-CAD-10 (Construction) | Construction annotations preserve height/rotation/alignment |

## Tests Added

55 tests in `tests/unit/test_text_geometry.py`:

| Test Class | Count | Coverage |
|-----------|-------|----------|
| TestTextProvenance | 3 | Enum values, ordering, str type |
| TestTextGeometry | 4 | Defaults, all fields, serialization, JSON |
| TestEntityRefTextGeometry | 4 | None default, with geometry, non-text, serialization |
| TestNormalizeRotation | 6 | Zero, positive, 360, negative, large values |
| TestTextExtractionFromDxf | 5 | TEXT/MTEXT geometry, LINE no geometry, rotation normalized, INSERT attribs |
| TestExtractTextGeometry | 3 | Full extraction, defaults, negative rotation |
| TestExtractMtextGeometry | 2 | Full extraction, defaults |
| TestTextGeometryConfidence | 9 | Confidence defaults, explicit values, is_high_trust, effective_height |
| TestTrustHierarchy | 9 | Order, coverage, defaults, monotonic degradation |
| TestAntiRegression | 4 | Native provenance preserved, full confidence, OCR/vector masquerade blocked |
| TestDebugVisibility | 2 | selection_debug includes/excludes text_geometry |
| TestToolExecutorVisibility | 2 | tool_executor includes/excludes text_geometry |
| TestSemanticModelTextGeometry | 2 | Planner context includes/excludes text_geometry |

## Known Limitations

1. **OCR and vector contour text paths do not exist** -- enum values and confidence defaults are future-proofing only
2. **MTEXT rich formatting** (bold, italic, font changes) is not parsed -- only char_height and attachment_point
3. **Block transform composition** (nested INSERT scales/rotations) is not applied to ATTRIB text geometry
4. **Text bounding box** is not computed -- would require font metrics not available without rendering
5. **Style table** (text style names, fonts) is not extracted

## Follow-on Recommendations

1. When OCR or vector contour text is added, use `TextProvenance.RASTER_OCR_TEXT` / `VECTOR_OUTLINE_TEXT` with appropriate confidence defaults
2. Consider computing approximate text bounding boxes using height + text length + width_factor
3. Consider extracting text style references for font-aware rendering
4. Block transform composition for ATTRIB positions should be addressed in EPIC-CAD-09/10

## Recommendation

**GO** -- The primary extraction gap (losing native CAD text geometry) is fixed. All downstream surfaces receive text geometry. Trust hierarchy is modeled and enforced. Anti-regression tests prevent future quality degradation. OCR/vector paths are future-proofed but not needed for current product capabilities.

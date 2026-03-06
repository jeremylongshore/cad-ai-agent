# 043 — EPIC-CAD-03 After Action Report (AAR)

**Epic:** EPIC-CAD-03 — Selection + Markup Interpretation Foundation
**Bead:** cad-wd2
**Status:** DONE
**Date:** 2026-03-06
**Phase:** 1 (Foundation) — 3 of 3 epics complete. Phase 1 COMPLETE.

---

## 1. Files Created/Updated

### Source Files (4)

| File | Action | Purpose |
|------|--------|---------|
| `src/cad_dxf_agent/models/region_schema.py` | Created | NormalizedRegion, BoundingBox, RegionType (6), CoordinateSpace (3), MarkupOverlay, MarkupType (5) |
| `src/cad_dxf_agent/core/markup_parser.py` | Created | MarkupParser, AffineTransform, handlers for circle/box/loop/arrow/highlight |
| `src/cad_dxf_agent/core/region_associator.py` | Created | RegionAssociator, AssociationType (5), AssociationResult with confidence |
| `src/cad_dxf_agent/core/selection_debug.py` | Created | build_debug_payload(), format_debug_text() for engineering verification |

### Test Files (4)

| File | Tests | Purpose |
|------|-------|---------|
| `tests/unit/test_region_schema.py` | 27 | BoundingBox, NormalizedRegion, containment, point-in-polygon, serialization, malformed rejection |
| `tests/unit/test_markup_parser.py` | 31 | All 5 markup types, AffineTransform, confidence scoring, degenerate inputs, batch |
| `tests/unit/test_region_associator.py` | 19 | Inside/nearby association, type classification, ranking, layers/blocks, confidence |
| `tests/unit/test_selection_debug.py` | 16 | JSON payload structure, text formatting, entity details, ambiguity, empty results |

### Docs Updated (2)

| File | Change |
|------|--------|
| `000-docs/041-PM-STAT-implementation-status.md` | EPIC-03 DONE, Phase 1 COMPLETE |
| `000-docs/000-INDEX.md` | Added doc 043 |

**Total EPIC-03 tests: 93**

---

## 2. Branch

| Branch | Status |
|--------|--------|
| `feature/epic-cad-03-selection-markup` | Squash-merged → main (PR #77) |

---

## 3. Commits

1. `feat(selection): add normalized region model for viewport and canvas selections`
2. `feat(markup): ingest markup overlays and map them into drawing-space regions`
3. `feat(selection): associate selected regions with nearby CAD entities and labels`
4. `feat(debug): add selection and markup debug inspection tooling`
5. `test(selection): add fixture coverage for region mapping and entity association`
6. `docs(status): update implementation status for EPIC-CAD-03`

---

## 4. Example Normalized Region Payloads

### Box Selection

```json
{
  "region_id": "a1b2c3d4e5f6",
  "source_type": "box_select",
  "coordinate_space": "drawing",
  "bounds": {"min_x": 10.0, "min_y": 20.0, "max_x": 50.0, "max_y": 60.0},
  "center": {"x": 30.0, "y": 40.0},
  "confidence": 1.0,
  "schema_version": "1.0"
}
```

### Circle Selection

```json
{
  "region_id": "f6e5d4c3b2a1",
  "source_type": "circle_select",
  "coordinate_space": "drawing",
  "bounds": {"min_x": -10.0, "min_y": -10.0, "max_x": 10.0, "max_y": 10.0},
  "center": {"x": 0.0, "y": 0.0},
  "radius": 10.0,
  "confidence": 1.0,
  "schema_version": "1.0"
}
```

### Freehand Loop

```json
{
  "region_id": "1a2b3c4d5e6f",
  "source_type": "freehand_loop",
  "coordinate_space": "drawing",
  "bounds": {"min_x": 0.0, "min_y": 0.0, "max_x": 20.0, "max_y": 20.0},
  "center": {"x": 10.0, "y": 10.0},
  "polygon": [
    {"x": 0, "y": 0}, {"x": 20, "y": 0},
    {"x": 20, "y": 20}, {"x": 0, "y": 20}
  ],
  "confidence": 1.0,
  "schema_version": "1.0"
}
```

---

## 5. Example Markup Mapping Payload

### Circle Markup → Drawing Region

**Input:**
```json
{
  "markup_id": "mk-001",
  "markup_type": "circle",
  "source_points": [
    {"x": 500, "y": 500},
    {"x": 600, "y": 500}
  ],
  "source_metadata": {"page": 1, "dpi": 150}
}
```

**Output (with AffineTransform scale 0.1):**
```json
{
  "region": {
    "source_type": "markup_mapped",
    "coordinate_space": "drawing",
    "bounds": {"min_x": 40.0, "min_y": 40.0, "max_x": 60.0, "max_y": 60.0},
    "center": {"x": 50.0, "y": 50.0},
    "radius": 10.0,
    "confidence": 0.95
  },
  "ambiguity_flags": []
}
```

### Arrow Markup (partial support)

```json
{
  "region": {
    "source_type": "markup_mapped",
    "bounds": {"min_x": 40.0, "min_y": 40.0, "max_x": 60.0, "max_y": 60.0},
    "center": {"x": 50.0, "y": 50.0},
    "confidence": 0.5
  },
  "ambiguity_flags": ["arrow_partial_support"]
}
```

---

## 6. Example Associated-Entity Payload

```json
{
  "region": {"region_id": "rgn-001", "source_type": "box_select"},
  "entities": [
    {"rank": 1, "handle": "A1", "entity_type": "LINE", "layer": "STRUCTURAL",
     "association_type": "inside", "distance": 0.0},
    {"rank": 2, "handle": "T1", "entity_type": "TEXT", "layer": "NOTES",
     "association_type": "label", "distance": 0.0, "text": "Column A-1"},
    {"rank": 3, "handle": "D1", "entity_type": "DIMENSION", "layer": "DIMENSIONS",
     "association_type": "dimension", "distance": 0.0, "text": "24'-0\""},
    {"rank": 4, "handle": "I1", "entity_type": "INSERT", "layer": "STRUCTURAL",
     "association_type": "block_ref", "distance": 0.0, "block_name": "COL_MARK"}
  ],
  "layers": ["DIMENSIONS", "NOTES", "STRUCTURAL"],
  "block_names": ["COL_MARK"],
  "confidence": 0.855,
  "entity_count": 4
}
```

---

## 7. Debug Output Example

```
=== Selection Debug: rgn-test-001 ===
Source type: markup_mapped
Coordinate space: drawing
Bounds: (20.00, 20.00) → (80.00, 80.00)
Center: (50.00, 50.00)
Area: 3600.00
Radius: 30.00
Region confidence: 0.850
Association confidence: 0.855
Entity count: 4
  Inside: 1
  Nearby: 0
  Labels: 1
  Dimensions: 1
Layers: DIMENSIONS, NOTES, STRUCTURAL
Blocks: COL_MARK
Ambiguity: test_flag

--- Top entities ---
  #1 [inside] A1 LINE layer=STRUCTURAL dist=0.00
  #2 [label] T1 Column A-1 layer=NOTES dist=0.00
  #3 [dimension] D1 24'-0" layer=DIMENSIONS dist=0.00
  #4 [block_ref] I1 COL_MARK layer=STRUCTURAL dist=0.00
```

---

## 8. Top 3 Risks Before EPIC-CAD-04

| # | Risk | Severity | Mitigation |
|---|------|----------|------------|
| 1 | **No real markup samples** — all tests use synthetic coordinates. Real-world markup (scanned PDFs, photo overlays) may have noise, skew, or partial visibility | HIGH | Collect 3-5 real markup samples before EPIC-04. Validate AffineTransform handles rotation/skew or add a more general transform. |
| 2 | **Entity spatial indexing is O(n)** — `find_in_radius` scans all entities linearly. Large drawings (5000+ entities) will be slow for region association | MEDIUM | Acceptable for now. If profiling shows bottleneck in EPIC-04, add R-tree spatial index behind the same `EntityIndex` API. |
| 3 | **Arrow and highlight are partial** — confidence capped at 0.5/0.6. Downstream Q&A may need to handle ambiguous regions gracefully | LOW | Ambiguity flags are explicit. EPIC-04 Q&A pipeline should check flags and either ask for clarification or widen search radius. |

---

## 9. Recommendation for EPIC-CAD-04

**Recommendation: GO**

**Rationale:**
- Canonical `NormalizedRegion` model implemented with 6 source types
- Markup overlays convert to drawing-space regions with confidence scoring
- Entity association finds inside/nearby entities, labels, dimensions, block refs
- Confidence and ambiguity are explicit, not implied
- Debug tooling provides structured + text output for verification
- 93 fixture-backed tests cover normalization, mapping, and association
- All 1515 existing tests still pass (zero regressions)
- `make check` clean (lint, format, typecheck)

**Phase 1 is COMPLETE.** All 3 foundation epics (01, 02, 03) are done.

**Prerequisites for EPIC-04:**
1. Region Q&A pipeline that uses `RegionAssociator` to build grounded context
2. Golden trajectories for `region_qa` task family
3. Wire `NormalizedRegion` into `PlatformRequest.selected_regions`

---

## Related Documents

- [036-AT-SPEC-response-contracts-taxonomy.md](036-AT-SPEC-response-contracts-taxonomy.md) — Contracts spec
- [041-PM-STAT-implementation-status.md](041-PM-STAT-implementation-status.md) — Living status tracker
- [042-PM-AAR-epic-cad-02-aar.md](042-PM-AAR-epic-cad-02-aar.md) — EPIC-02 AAR

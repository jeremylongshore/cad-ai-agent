# 051 — EPIC-CAD-10 After Action Report

**Epic:** EPIC-CAD-10 Construction Drawing Workflow Pack
**Bead:** cad-8p2
**Status:** DONE
**Date:** 2026-03-07
**Branch:** `feature/epic-cad-10-construction-ops`
**PR:** TBD

---

## 1. Objective

Add four deterministic construction-specific workflows: grid/bay structural summary,
markup-to-redline structured reports, batch repeated-condition detection, and field
summary combining all analyses. All outputs surface confidence, caveats, and evidence.
No LLM calls. Construction users move from 31% to 83% capability coverage.

---

## 2. Deliverables

### New Source Files (2)

| File | Purpose |
|------|---------|
| `src/cad_dxf_agent/models/construction_ops_schema.py` | All Pydantic schemas: GridDirection, GridLine, Bay, GridSummaryResult, RevisionCloudInfo, RedlineEntry, RedlineReportResult, ConditionGroup, BatchConditionResult, FieldSectionType, FieldSection, FieldSummary |
| `src/cad_dxf_agent/core/construction_ops.py` | Four classes: GridAnalyzer, MarkupRedlineGenerator, BatchConditionPlanner, FieldSummaryBuilder |

### Modified Source Files (5)

| File | Change |
|------|--------|
| `src/cad_dxf_agent/core/dxf_reader.py` | Store LINE `end_point` and LWPOLYLINE `vertices` in entity attributes |
| `src/cad_dxf_agent/llm/intent_router.py` | Extended patterns for grid/bay, batch condition, field summary prompts |
| `src/cad_dxf_agent/llm/capability_registry.py` | Added `MARKUP_INTERPRETATION` to `_DEFAULT_ENABLED` |
| `src/cad_dxf_agent/llm/response_builder.py` | Added `markup_redline()` static method |
| `web/backend/main.py` | Added MARKUP_INTERPRETATION dispatch, batch condition sub-dispatch, grid/field summary sub-dispatch in DESIGN_ASSIST |

### Frontend (1 modified)

| File | Purpose |
|------|---------|
| `web/frontend/src/components/DesignOpsPanel.jsx` | Added GridTable, RedlineList, ConditionGroupList components; unified `renderSection()` for EPIC-09 + EPIC-10 section types; standalone renderers for grid, redline, condition data shapes |

### Test Files (8)

| File | Tests |
|------|-------|
| `tests/unit/test_construction_ops_schema.py` | 25 schema validation tests |
| `tests/unit/test_grid_analyzer.py` | 24 grid analysis tests |
| `tests/unit/test_markup_redline_generator.py` | 32 redline generation tests |
| `tests/unit/test_batch_condition_planner.py` | 30 batch condition tests |
| `tests/unit/test_field_summary_builder.py` | 23 field summary assembly tests |
| `tests/unit/test_construction_ops_anti_regression.py` | 37 anti-regression guards |
| `tests/web/test_construction_ops_endpoints.py` | 23 web endpoint tests |
| **Total** | **194 new tests** |

### Golden Trajectories (4)

- `construction_ops_grid_summary.json`
- `construction_ops_markup_redline.json`
- `construction_ops_batch_condition.json`
- `construction_ops_field_summary.json`

---

## 3. Architecture Decisions

1. **Parallel file structure to EPIC-09** — `construction_ops_schema.py` + `construction_ops.py` mirrors `design_ops_schema.py` + `design_ops.py`. Keeps construction and design domains separate at ~150 lines schema + ~350 lines generators each.

2. **No new TaskFamily enums** — Reused existing families with sub-dispatch:
   - Grid/Bay: `DESIGN_ASSIST` keyword sub-dispatch ("grid", "bay", "column grid")
   - Markup-to-Redline: `MARKUP_INTERPRETATION` (enabled in registry, new dispatch block)
   - Batch Conditions: `REPEATED_CONDITION` (batch sub-dispatch when no exemplar handles)
   - Field Summary: `DESIGN_ASSIST` keyword sub-dispatch ("field summary", "field report")

3. **LINE/LWPOLYLINE vertex storage** — Stored `end_point` for LINE and `vertices` for LWPOLYLINE in entity attributes during DXF load. Surgical 2-line change to `dxf_reader.py`, no schema changes needed.

4. **Bounding box containment for cloud detection** — MarkupRedlineGenerator computes AABB from LWPOLYLINE vertices and finds entities within bounds. Simple, fast, no spatial index needed for typical revision cloud counts.

5. **FieldSummaryBuilder composes all generators** — Runs GridAnalyzer, TakeoffGenerator (EPIC-09), BatchConditionPlanner, and optionally RevisionSummarizer (EPIC-09) + LayoutRecommender (EPIC-09). Omits sections cleanly when no relevant data exists.

---

## 4. Metrics

| Metric | Before | After |
|--------|--------|-------|
| Total tests | 2,249+ | 2,422+ |
| Golden trajectories | 23 | 27 |
| Task families tested | 8 | 9 |
| Source files | — | +2 new, 5 modified |
| Test files | — | +8 new |
| Frontend components | — | +3 sub-components (GridTable, RedlineList, ConditionGroupList) |

---

## 5. What Went Well

- **EPIC-09 pattern reuse** — Schema + generator + web dispatch + anti-regression structure directly reusable. Implementation was fast and predictable.
- **Comprehensive anti-regression** — 37 tests guard: no EditOperation leakage, no LLM calls, confidence/caveats/ambiguity_flags present, no risk_level on domain models, OCR items capped, all serializable, all handle empty drawings.
- **Frontend extension** — DesignOpsPanel.jsx absorbed new section types cleanly through the unified `renderSection()` function. No new component files needed.
- **dxf_reader change was surgical** — 2 lines added for vertex storage; all existing reader tests still pass.

---

## 6. What Could Improve

- **Module size trajectory** — `construction_ops.py` at ~350 lines is fine, but combined with `design_ops.py` (~400 lines), the `core/` directory now has 8+ generator classes. If Phase 5 adds more, consider a `core/generators/` package.
- **Bounding box is AABB** — Axis-aligned bounding box for cloud containment is simple but can over-match for non-rectangular revision clouds. A convex hull check would be more precise but adds complexity for marginal benefit.
- **Sub-dispatch chain in main.py** — The DESIGN_ASSIST block now has 4 keyword checks (field → grid → scope → layout). This is manageable but approaching the threshold where a sub-router pattern would be cleaner.

---

## 7. Phase 4 Status

- EPIC-09: DONE (PR #88)
- EPIC-10: DONE
- Phase 4 gate: 2/2 COMPLETE
- Next: Phase 5 (EPIC-11 Session Durability, EPIC-12 Eval Harness)

---

## Related Documents

- [041-PM-STAT](041-PM-STAT-implementation-status.md) — Implementation status tracker
- [050-PM-AAR](050-PM-AAR-epic-cad-09-aar.md) — EPIC-09 AAR (design operations, companion epic)
- [036-AT-SPEC](036-AT-SPEC-response-contracts-taxonomy.md) — Response contracts (TaskFamily, PlatformResponse)

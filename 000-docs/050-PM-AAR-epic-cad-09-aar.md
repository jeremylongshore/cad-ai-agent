# 050 — EPIC-CAD-09 After Action Report

**Epic:** EPIC-CAD-09 Design Operations Workflow Pack
**Bead:** cad-ady (parent) + cad-ady.2 through cad-ady.5 (children)
**Status:** DONE
**Date:** 2026-03-07
**Branch:** `feature/epic-cad-09-design-operations`
**PR:** #88

---

## 1. Objective

Add bounded, typed, evidence-grounded outputs for four design operations workflows:
layout recommendations, revision summaries, takeoff candidates, and scope-style summaries.
All deterministic (no LLM). All outputs surface confidence, caveats, and evidence.

---

## 2. Deliverables

### New Source Files (2)

| File | Purpose |
|------|---------|
| `src/cad_dxf_agent/models/design_ops_schema.py` | All Pydantic schemas: RecommendationType, LayoutRecommendation, LayoutRecommendationResult, ChangeSummaryEntry, CustomerRevisionSummary, TakeoffConfidence, TakeoffItem, TakeoffCandidateResult, ScopeSectionType, ScopeSection, ScopeSummary |
| `src/cad_dxf_agent/core/design_ops.py` | Four classes: LayoutRecommender, RevisionSummarizer, TakeoffGenerator, ScopeBuilder |

### Modified Source Files (5)

| File | Change |
|------|--------|
| `src/cad_dxf_agent/llm/capability_registry.py` | Added DESIGN_ASSIST, SUMMARY, TAKEOFF_ESTIMATE to `_DEFAULT_ENABLED` |
| `src/cad_dxf_agent/llm/intent_router.py` | Extended patterns for design-ops prompts (layout, placement, scope, revision summary, etc.) |
| `src/cad_dxf_agent/llm/response_builder.py` | Added `design_assist()`, `summary_result()`, `takeoff_result()` static methods |
| `web/backend/main.py` | Added dispatch for 3 task families in `/api/v2/prompt` handler |
| `web/frontend/src/components/ChatPanel.jsx` | Renders DesignOpsPanel for design-ops responses |

### Frontend (1)

| File | Purpose |
|------|---------|
| `web/frontend/src/components/DesignOpsPanel.jsx` | Scope sections, recommendations, takeoff tables, revision summaries with confidence badges and caveats |

### Test Files (8)

| File | Tests |
|------|-------|
| `tests/unit/test_design_ops_schema.py` | 34 schema validation tests |
| `tests/unit/test_layout_recommender.py` | 30 layout recommendation tests |
| `tests/unit/test_revision_summarizer.py` | 22 revision summary tests |
| `tests/unit/test_takeoff_generator.py` | 27 takeoff generation tests |
| `tests/unit/test_scope_builder.py` | 20 scope assembly tests |
| `tests/unit/test_design_ops_anti_regression.py` | 23 anti-regression guards |
| `tests/web/test_design_ops_endpoints.py` | 20 web endpoint tests |
| **Total** | **176 new tests** |

### Golden Trajectories (4)

- `design_ops_layout_recommendation.json`
- `design_ops_revision_summary.json`
- `design_ops_takeoff_candidate.json`
- `design_ops_scope_summary.json`

---

## 3. Architecture Decisions

1. **Single module, four classes** — All design-ops logic in `core/design_ops.py` rather than a separate `workflows/` package. Keeps imports simple and matches existing `core/` convention.

2. **Deterministic-only** — No LLM calls. Layout recommendations analyze entity distribution; revision summaries translate structured diffs; takeoff counts blocks/layers/text labels; scope assembles all three. Confidence and caveats are first-class.

3. **OCR provenance enforcement (SQ67)** — TakeoffGenerator checks `TextGeometry.is_high_trust`. OCR-derived quantities are capped at `ESTIMATE_ONLY` confidence with mandatory provenance warnings. Anti-regression tests prevent this from silently weakening.

4. **Reuse existing routing infrastructure** — TaskFamily enums (DESIGN_ASSIST, SUMMARY, TAKEOFF_ESTIMATE) and PlatformResponse envelope from EPIC-02 used as-is. Only added dispatch blocks and response builder methods.

---

## 4. Metrics

| Metric | Before | After |
|--------|--------|-------|
| Total tests | 2,144 | 2,249+ |
| Golden trajectories | 19 | 23 |
| Task families tested | 5 | 8 |
| Source files | — | +2 new, 5 modified |
| Test files | — | +8 new, 3 modified |
| Frontend components | — | +1 (DesignOpsPanel) |

---

## 5. What Went Well

- **Schema-first design** — Writing `design_ops_schema.py` first made the generator classes straightforward to implement and test.
- **Anti-regression coverage** — 23 dedicated anti-regression tests catch silent confidence inflation, missing caveats, and accidental edit operation leakage.
- **Existing infrastructure reuse** — TaskFamily enum, PlatformResponse, intent router patterns, and web dispatch all extended cleanly without breaking existing tests.
- **Text provenance integration** — SQ67 enforcement from SIDEQUEST-CAD-67 carried through naturally to takeoff confidence scoring.

---

## 6. What Could Improve

- **Trajectory filter fragility** — Integration test trajectory loader broke when new JSON files (without `expected_turns`) were added. Fixed by checking key existence instead of task_family values. Consider a schema version field in trajectory files.
- **Large module size** — `design_ops.py` has four classes (~400 lines). If EPIC-10 adds more, consider splitting into `core/design_ops/` package.

---

## 7. Phase 4 Status

- EPIC-09: DONE
- EPIC-10 (Construction Drawing Workflow Pack): NOT STARTED
- Phase 4 gate: 1/2 complete

---

## Related Documents

- [041-PM-STAT](041-PM-STAT-implementation-status.md) — Implementation status tracker
- [036-AT-SPEC](036-AT-SPEC-response-contracts-taxonomy.md) — Response contracts (TaskFamily, PlatformResponse)
- [044-AT-SPEC](044-AT-SPEC-sidequest-cad-67-text-accuracy.md) — Text provenance (SQ67, TextGeometry)

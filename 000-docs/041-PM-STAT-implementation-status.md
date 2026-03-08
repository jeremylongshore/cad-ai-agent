# 041 — Implementation Status Tracker

**Status:** Living document (updated per epic)
**Date:** 2026-03-05
**Scope:** Track implementation progress across all 12 epics + architecture review gate.

---

## 1. Epic Status Overview

| # | Epic | Bead ID | Status | Branch | PR | Key Deliverables | Tests |
|---|------|---------|--------|--------|----|-----------------|-------|
| 01 | Capability Audit + Architecture Baseline | cad-uns | DONE | `feature/epic-cad-01-capability-audit` | #71 | 8 docs (034-041), beads task tree | N/A (docs only) |
| 02 | Core Contracts + Routing Foundation | cad-d9a | DONE | `feature/epic-cad-02-core-contracts-routing` | #74, #75 | `response_schema.py`, `intent_router.py`, `capability_registry.py`, `response_builder.py`, `/api/v2/prompt` | 140 tests — unit (37 schema + 48 router + 10 registry + 18 builder), web (12 v2 endpoint), integration (5 pipeline) + 50-entry golden routing file |
| 03 | Selection + Markup Interpretation Foundation | cad-wd2 | DONE | `feature/epic-cad-03-selection-markup` | #77 | `region_schema.py`, `markup_parser.py`, `region_associator.py`, `selection_debug.py` | 93 tests — unit (27 schema + 31 parser + 19 associator + 16 debug) |
| 04 | Region Q&A Vertical Slice | cad-grx | DONE | `feature/epic-cad-04-region-qna` | #78 | `qna_pipeline.py`, `region_context.py`, `qna_schema.py`, `/api/v2/qna`, QnaPanel frontend | 509 tests — unit (356 pipeline + 133 schema), integration (126 qna), 6 golden trajectories (qna family) |
| — | SIDEQUEST-CAD-67: Text Positional Accuracy | cad-xiw | DONE | `feature/sidequest-cad-67-text-accuracy` | #79 | `TextProvenance` enum, `TextGeometry` model, trust hierarchy, enhanced TEXT/MTEXT/INSERT extraction, downstream wiring (selection, Q&A, compare, planner) | 788+ unit tests (test_text_geometry.py) + 534 e2e tests (test_text_accuracy_e2e.py) |
| 05 | Repeated-Condition Detection | cad-ccd | DONE | `feature/epic-cad-05-repeated-conditions` | #81 | `repeated_condition_schema.py`, `repeated_condition.py`, web endpoint, 4 golden trajectories | 63 tests — unit (38 detection + 19 schema), integration (6 factory DXF) |
| 06 | Compare + Diff Service Hardening | cad-3e4 | DONE | `feature/epic-cad-06-compare-diff` | #82 | `comparison_schema.py` (MatchSummary, DiffSummaryData, ComparePackage), scorer text-trust, changelog enrichment, `export_compare_package()`, web endpoint hardening | 15 tests — unit (9 schema + 2 anti-regression), regression (13 comparison pipeline) |
| — | ARCH-REVIEW-01 | cad-sfw | DONE | `feature/arch-review-cad-01` | — | [046-AT-AUDT](046-AT-AUDT-arch-review-cad-01.md): 10-dimension review, CONDITIONAL GO for EPIC-07, 3 prerequisites, 2 constraints | N/A (review output is ADR document) |
| 07 | Structured Edit Planning | cad-9ug | DONE | `feature/epic-cad-07-edit-planning` | #85 | `plan_schema.py` (EditPlan, EditAction, 5 action types), `plan_builder.py` (deterministic, no LLM), `plan_validator.py` (protected layers, text trust, move limits), `text_utils.py` (shared utilities) | 109 tests — unit (25 schema + 30 builder + 20 validator + 16 text_utils), anti-regression (15), golden (10) |
| 08 | Preview + Apply Workflow | cad-6zz | DONE | `feature/epic-cad-08-preview-apply` | #86 | `preview_schema.py`, `apply_schema.py`, `plan_converter.py`, `preview_builder.py`, `apply_pipeline.py`, web endpoints (`/api/v2/preview`, `/approve`, `/apply`), `PreviewPanel.jsx`, session-scoped audit trail | 105 tests — unit (12 preview schema + 20 preview builder + 16 apply schema + 15 apply pipeline + 15 plan converter), anti-regression (8), golden (4), web (15) |
| 09 | Design Operations Workflow Pack | cad-ady | DONE | `feature/epic-cad-09-design-operations` | #88 | `design_ops_schema.py`, `design_ops.py` (LayoutRecommender, RevisionSummarizer, TakeoffGenerator, ScopeBuilder), `DesignOpsPanel.jsx`, web dispatch for 3 task families, intent router patterns | 176 tests — unit (34 schema + 30 layout + 22 revision + 27 takeoff + 20 scope + 23 anti-regression), web (20 endpoint), 4 golden trajectories |
| 10 | Construction Drawing Workflow Pack | cad-8p2 | DONE | `feature/epic-cad-10-construction-ops` | TBD | `construction_ops_schema.py`, `construction_ops.py` (GridAnalyzer, MarkupRedlineGenerator, BatchConditionPlanner, FieldSummaryBuilder), DesignOpsPanel extensions, intent router + registry + dispatch wiring | 194 tests — unit (25 schema + 24 grid + 32 redline + 30 condition + 23 field + 37 anti-regression), web (23 endpoint), 4 golden trajectories |
| 11 | Session Durability + Scale Readiness | cad-36p | DONE | `feature/epic-cad-11-session-durability` | #90 | `core/session_store.py` (SessionStore ABC + InMemorySessionStore + GCSSessionStore), SessionMetadata bridge, zero-disruption migration | 58 tests — unit (29 store + 19 bridge), web (10 durability) |
| 12 | Evaluation Harness + Quality Governance | cad-m7d | DONE | `feature/epic-cad-12-eval-harness` | TBD | `models/scorecard_schema.py`, `tests/eval/scorecard_entries.json` (32 entries), `tests/eval/test_scorecard.py`, `scripts/run_eval.py`, Makefile scorecard targets | 42 tests — eval (5 structure + 32 classification + 5 schema). 96.9% intent accuracy. |

---

## 2. Phase Progress

| Phase | Epics | Status | Gate |
|-------|-------|--------|------|
| **Phase 1: Foundation** | 01, 02, 03 | 3/3 COMPLETE | Contracts locked, regions normalized, `make check` green |
| **Phase 2: Core Intelligence** | 04, 05, 06 | 3/3 COMPLETE (+ SQ67 done) | Golden trajectories pass per family |
| **Architecture Review** | ARCH-REVIEW-01 | COMPLETE | CONDITIONAL GO — doc 046 published, 3 prerequisites for EPIC-07 |
| **Phase 3: Structured Editing** | 07, 08 | 2/2 COMPLETE | EPIC-07 DONE (edit plan schema + builder + validator). EPIC-08 DONE (preview + apply workflow, PR #86). Phase gate: structured edit plans validated, previewed, and applied end-to-end. |
| **Phase 4: Workflow Packs** | 09, 10 | 2/2 COMPLETE | EPIC-09 DONE (design-ops: layout, revision, takeoff, scope). EPIC-10 DONE (construction-ops: grid/bay, markup-to-redline, batch conditions, field summary). Key files: `core/design_ops.py`, `models/design_ops_schema.py`, `core/construction_ops.py`, `models/construction_ops_schema.py` |
| **Phase 5: Production Readiness** | 11, 12 | 2/2 COMPLETE | EPIC-11 DONE (SessionStore ABC + InMemory/GCS impls, zero-disruption migration, PR #90). EPIC-12 DONE (scorecard schema, 32 entries, eval runner, 96.9% accuracy). Key files: `core/session_store.py`, `models/scorecard_schema.py`, `tests/eval/`, `scripts/run_eval.py` |

---

## 3. Dependency Chain Status

```
EPIC-01 (DONE) → EPIC-02 (DONE)
                    ├──> EPIC-03 (DONE) → EPIC-04 (DONE) + SQ67 (DONE) → EPIC-05 (DONE)
                    └──> EPIC-06 (DONE)
              EPIC-04 + 05 + 06 → ARCH-REVIEW-01
                                    ├──> EPIC-07 → EPIC-08
                                    └──> EPIC-11
              EPIC-04 + 08 → EPIC-09
              EPIC-03 + 06 + 07 → EPIC-10
              EPIC-04..10 → EPIC-12
```

**Critical path:** ALL PHASES COMPLETE. Phase 1 (01-03), Phase 2 (04-06 + SQ67), ARCH-REVIEW-01, Phase 3 (07-08), Phase 4 (09-10), Phase 5 (11-12). 12/12 epics DONE.

---

## 4. Document Inventory (EPIC-01 Outputs)

| Doc # | Title | Status |
|-------|-------|--------|
| 034 | Capability Audit | DONE — 9 task families, 6 technical layers, 3 user classes |
| 035 | Target Architecture | DONE — 7-layer architecture, workflow mappings |
| 036 | Response Contracts + Taxonomy | DONE — TaskFamily, ResponseType, PlatformResponse, per-family detail |
| 037 | Evaluation Plan | DONE — 5-tier strategy, 25+ trajectories, scorecard schema |
| 038 | Drawing Intelligence Roadmap | DONE — 12 epics, 5 phases, dependency graph |
| 039 | Intent Router Design (ADR) | DONE — Hybrid heuristic+LLM, task family boundaries |
| 040 | Scale Readiness Assessment | DONE — Bottlenecks, migration path, observability gaps |
| 041 | Implementation Status Tracker | DONE — This document; living tracker for all 12 epics |

---

## 5. Test Metrics Baseline

| Metric | Current (post-SQ67) | Target (all epics) |
|--------|-------------------|-------------------|
| Total tests | 2,468+ (collected) | 2000+ |
| Coverage | ~95% | 70%+ |
| Golden trajectories | 27 (edit_plan 5 + qna 6 + repeated_condition 4 + preview_apply 4 + design_ops 4 + construction_ops 4) | 25+ (all 9 families) |
| Scorecard entries | 32 | 32+ |
| Task families tested | 9 (edit_plan + compare + qna + repeated_condition + preview_apply + design_assist + summary + takeoff_estimate + markup_interpretation) | 9 |
| Scorecard pass rate (mock) | 100% (42/42 tests) | 100% |
| Scorecard pass rate (eval runner) | 96.9% (31/32 — 1 expected edge case) | >= 95% |

---

## 6. Risk Summary

| Risk | Epic(s) | Status | Mitigation |
|------|---------|--------|------------|
| Response contract churn | 02 | RESOLVED — schemas implemented and tested | Stabilized in EPIC-02 with 29 unit tests |
| Intent router accuracy | 02, 04 | RESOLVED — heuristic router implemented | 50-entry golden file, 0.95 confidence, conservative thresholds |
| Markup entity detection | 03 | DEFERRED — no training data | Collect real samples before EPIC-03 |
| 500-entity context cap | 03, 04 | ACTIVE — silent information loss | Token-budget context builder in EPIC-03 |
| Ephemeral session storage | 11 | KNOWN — lost on restart | Durable state migration in EPIC-11 |
| Large drawing performance | 06, 11 | ACTIVE — blocks request thread | Background execution in EPIC-11 |
| Domain-specific prompt templates may not generalize | 09 | DEFERRED | Start with narrow domain templates; collect user feedback before broadening |
| Construction drawing conventions vary by region | 10 | DEFERRED | Parameterize region-specific conventions; validate with multiple regional samples |
| Migration from in-memory to persistent sessions may break existing tests | 11 | DEFERRED | Implement session store behind ABC; keep in-memory impl for test compatibility |
| Eval harness depends on quality of golden trajectories from prior epics | 12 | DEFERRED | Gate EPIC-12 on trajectory count threshold (25+); validate trajectory coverage per family |

---

## 7. Per-Epic Next Steps

| # | Epic | Next Step |
|---|------|-----------|
| 01 | Capability Audit + Architecture Baseline | Completed |
| 02 | Core Contracts + Routing Foundation | DONE — PR #74 + #75 merged, bead closed. AAR: [042-PM-AAR](042-PM-AAR-epic-cad-02-aar.md) |
| 03 | Selection + Markup Interpretation Foundation | DONE — PR merged, bead closed. AAR: [043-PM-AAR](043-PM-AAR-epic-cad-03-aar.md) |
| 04 | Region Q&A Vertical Slice | DONE — PR #78 merged. Deterministic Q&A pipeline, region context builder, 6 golden trajectories, QnaPanel frontend. |
| — | SIDEQUEST-CAD-67 | DONE — PR #79 merged. TextGeometry + TextProvenance models, enhanced extraction, trust hierarchy, downstream wiring, 788+ tests. Doc: [044-AT-SPEC](044-AT-SPEC-sidequest-cad-67-text-accuracy.md) |
| 05 | Repeated-Condition Detection | DONE — PR #81. Similarity scoring model (6 signals, text-trust weighting), ConditionDetector with spatial clustering, preview/approval workflow, web endpoint, 63 tests, 4 golden trajectories. Doc: [045-AT-SPEC](045-AT-SPEC-repeated-condition-scoring.md) |
| 06 | Compare + Diff Service Hardening | DONE — PR #82 merged. Typed compare schema, scorer text-trust, changelog enrichment, export package, web endpoint hardening. 15 tests. Compliance audit: 2 anti-regression tests added. |
| — | ARCH-REVIEW-01 | DONE — doc 046 published. CONDITIONAL GO for EPIC-07 with 3 prerequisites (upload size, text_utils extraction, truncation confidence) |
| 07 | Structured Edit Planning | DONE — PR #85. EditPlan schema (5 action types), deterministic plan builder (no LLM), plan validator (protected layers, text trust, move limits), shared text_utils. 109 new tests. All 3 ARCH-REVIEW prerequisites satisfied. |
| 08 | Preview + Apply Workflow | DONE — PR #86. AAR: [049-PM-AAR](049-PM-AAR-epic-cad-08-aar.md) |
| 09 | Design Operations Workflow Pack | DONE — PR #88. AAR: [050-PM-AAR](050-PM-AAR-epic-cad-09-aar.md) |
| 10 | Construction Drawing Workflow Pack | DONE — PR TBD. AAR: [051-PM-AAR](051-PM-AAR-epic-cad-10-aar.md) |
| 11 | Session Durability + Scale Readiness | DONE — PR #90. SessionStore ABC + InMemorySessionStore + GCSSessionStore. SessionMetadata bridge (to_metadata/from_metadata). Zero-disruption migration (200+ existing web tests pass unchanged). 58 new tests. AAR: [052-PM-AAR](052-PM-AAR-epic-cad-11-aar.md) |
| 12 | Evaluation Harness + Quality Governance | DONE — PR TBD. Scorecard schema (ScoreVerdict, ScorecardEntry, ScorecardResult, ScorecardSummary). 32 entries × 9 task families. Eval runner (scripts/run_eval.py). 42 new tests. 96.9% intent classification accuracy. AAR: [053-PM-AAR](053-PM-AAR-epic-cad-12-aar.md) |

---

## 8. Global Next Actions

1. **ALL 12 EPICS COMPLETE** — Full Drawing Intelligence Platform delivered across 5 phases.
2. **Phase 5 COMPLETE** — EPIC-11 (Session Durability, PR #90) + EPIC-12 (Eval Harness). 100 new tests. SessionStore ABC with GCS backend. 32-entry capability scorecard at 96.9% accuracy.
3. **Next:** Merge remaining PRs (#90, EPIC-12 PR). Monitor Gemini review comments. Close beads.

---

## Related Documents

- 034-AT-AUDT — Capability audit baseline
- 038-PM-PLAN — Roadmap and phasing
- 040-AT-AUDT — Scale readiness assessment

---

## Changelog

| Date | Change |
|------|--------|
| 2026-03-05 | Initial creation with EPIC-01 complete, all other epics NOT STARTED |
| 2026-03-06 | Audit hardening: fixed doc count (6→8), added Tests column, mapped risks to epics, added Phase 4-5 risks, added per-epic Next Steps, added concrete file paths for Phases 3-5, clarified ARCH-REVIEW-01 output format, added this changelog |
| 2026-03-06 | EPIC-02 DONE: 140 new tests, 7 new/modified files, response contracts + intent router + capability registry + response builder + /api/v2/prompt endpoint |
| 2026-03-06 | EPIC-02 AAR: updated PR refs (TBD→#74,#75), test count (112→140), critical path (EPIC-03 is next gate), added AAR doc 042 |
| 2026-03-06 | EPIC-03 DONE: 93 new tests, 4 new source files (region_schema, markup_parser, region_associator, selection_debug). Phase 1 COMPLETE. |
| 2026-03-06 | EPIC-04 DONE: PR #78 merged. Deterministic Q&A pipeline (qna_pipeline.py, region_context.py, qna_schema.py), 509 new tests, 6 golden trajectories, QnaPanel frontend. |
| 2026-03-06 | SIDEQUEST-CAD-67 DONE: PR #79 merged. TextGeometry + TextProvenance models, enhanced TEXT/MTEXT/INSERT extraction, trust hierarchy, downstream wiring to selection/Q&A/compare/planner. 788+ unit tests + 534 e2e tests. Doc 044 added. |
| 2026-03-06 | Test count: ~1462 → ~1760. Golden trajectories: 5 → 11. Task families tested: 2 → 3 (added qna). |
| 2026-03-06 | EPIC-05 started: Repeated-Condition Detection (in progress). |
| 2026-03-06 | EPIC-05 DONE: PR #81. Similarity scoring model (6 weighted signals), ConditionDetector with spatial clustering, preview/approval workflow, web endpoint. 63 new tests (38 unit + 19 schema + 6 integration). 4 golden trajectories. Doc 045 added. Test count: ~1760→~1823. Golden trajectories: 11→15. Task families: 3→4. Phase 2: 2/3 complete. |
| 2026-03-07 | ARCH-REVIEW-01 DONE: 10-dimension architecture review. CONDITIONAL GO for EPIC-07. Doc 046 published. Test count: 1,924. Coverage: 95.24%. Prerequisites: upload size validation (P0), extract text_utils (P1), truncation confidence (P1). |
| 2026-03-07 | EPIC-07 DONE: PR #85. 4 new source files (plan_schema.py, plan_builder.py, plan_validator.py, text_utils.py). 109 new tests (25 schema + 30 builder + 20 validator + 15 anti-regression + 10 golden + 16 text_utils). All 3 ARCH-REVIEW prerequisites satisfied. Test count: 1,760 collected, all pass. Phase 3: 1/2 complete. Doc 048 added. |
| 2026-03-07 | EPIC-08 DONE: PR #86. 5 new source files (preview_schema, apply_schema, plan_converter, preview_builder, apply_pipeline). 105 new tests. 3 web endpoints. Phase 3: 2/2 COMPLETE. Total tests: 2,144. Golden trajectories: 19. Task families: 5. Doc 049 added. |
| 2026-03-07 | EPIC-09 DONE: PR #88. 2 new source files (design_ops_schema.py, design_ops.py — 4 classes). 176 new tests (156 unit + 20 web). 4 golden trajectories. 3 task families wired (design_assist, summary, takeoff_estimate). DesignOpsPanel.jsx frontend. Phase 4: 1/2 complete. Total tests: 2,249+. Golden trajectories: 23. Task families: 8. Doc 050 added. |
| 2026-03-07 | EPIC-10 DONE: 2 new source files (construction_ops_schema.py, construction_ops.py — 4 classes). 194 new tests (171 unit + 23 web). 4 golden trajectories. 1 new task family wired (markup_interpretation), 2 existing extended (design_assist grid/field, repeated_condition batch). dxf_reader LINE/LWPOLYLINE vertex storage. DesignOpsPanel.jsx extended. Phase 4: 2/2 COMPLETE. Total tests: 2,422+. Golden trajectories: 27. Task families: 9. Doc 051 added. |
| 2026-03-07 | EPIC-11 DONE: PR #90. SessionStore ABC + InMemorySessionStore + GCSSessionStore. SessionMetadata bridge. Zero-disruption migration (200+ web tests pass unchanged). 58 new tests (29 store + 19 bridge + 10 web durability). Doc 052 added. |
| 2026-03-07 | EPIC-12 DONE: Scorecard schema (4 models), 32 entries × 9 families, eval runner, Makefile targets. 42 new tests. 96.9% intent accuracy. ALL 12 EPICS COMPLETE. Phase 5: 2/2 COMPLETE. Total tests: 2,468+. Scorecard entries: 32. Doc 053 added. |

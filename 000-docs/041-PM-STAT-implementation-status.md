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
| 06 | Compare + Diff Service Hardening | cad-3e4 | NOT STARTED | — | — | Typed compare schema, alignment diagnostics, regression fixtures | TBD — unit (typed schema), regression fixtures, integration (alignment diagnostics) |
| — | ARCH-REVIEW-01 | cad-sfw | NOT STARTED | — | — | Post-EPIC-06 quality/scalability review; ADR with keep/change/remove decisions per module | N/A (review output is ADR document) |
| 07 | Structured Edit Planning | cad-9ug | NOT STARTED | — | — | `models/plan_schema.py` (EditPlan), `llm/plan_builder.py`, constraint validation | TBD — unit (plan schema, constraint validation), golden trajectories (structured_edit family) |
| 08 | Preview + Apply Workflow | cad-6zz | NOT STARTED | — | — | `web/backend/routes/preview.py`, `web/frontend/src/components/PreviewPanel.jsx`, audit trail | TBD — unit (preview generation, audit trail), integration (preview→apply round-trip), web API tests |
| 09 | Design Operations Workflow Pack | cad-ady | NOT STARTED | — | — | `workflows/design_ops.py`, prompt templates for layout/revision/takeoff | TBD — golden trajectories (design_ops families), scorecard entries, live API tests |
| 10 | Construction Drawing Workflow Pack | cad-8p2 | NOT STARTED | — | — | `workflows/construction.py`, prompt templates for grid/bay/markup/batch | TBD — golden trajectories (construction families), scorecard entries, live API tests |
| 11 | Session Durability + Scale Readiness | cad-36p | NOT STARTED | — | — | `core/session_store.py` (ABC + GCS impl), durable metadata model, tracing/metrics | TBD — unit (session store, metadata model), integration (persistence round-trip), migration tests |
| 12 | Evaluation Harness + Quality Governance | cad-m7d | NOT STARTED | — | — | `tests/eval/` fixture packs, `scripts/run_eval.py`, scorecard JSON schema, CI regression | TBD — meta-tests (scorecard schema validation), CI smoke (eval harness runs clean) |

---

## 2. Phase Progress

| Phase | Epics | Status | Gate |
|-------|-------|--------|------|
| **Phase 1: Foundation** | 01, 02, 03 | 3/3 COMPLETE | Contracts locked, regions normalized, `make check` green |
| **Phase 2: Core Intelligence** | 04, 05, 06 | 2/3 complete (+ SQ67 done) | Golden trajectories pass per family |
| **Architecture Review** | ARCH-REVIEW-01 | Not started | ADR document with keep/change/remove decisions per module |
| **Phase 3: Structured Editing** | 07, 08 | 0/2 complete | Edit plan + apply produce audit metadata. Key files: `src/cad_dxf_agent/llm/plan_builder.py`, `src/cad_dxf_agent/models/plan_schema.py`, `web/frontend/src/components/PreviewPanel.jsx`, `web/backend/routes/preview.py` |
| **Phase 4: Workflow Packs** | 09, 10 | 0/2 complete | Domain scorecard entries pass. Key files: `src/cad_dxf_agent/workflows/design_ops.py`, `src/cad_dxf_agent/workflows/construction.py`, domain-specific prompt templates |
| **Phase 5: Production Readiness** | 11, 12 | 0/2 complete | Durable sessions + full scorecard green. Key files: `src/cad_dxf_agent/core/session_store.py` (GCS integration), `tests/eval/`, `scripts/run_eval.py`, scorecard schema |

---

## 3. Dependency Chain Status

```
EPIC-01 (DONE) → EPIC-02 (DONE)
                    ├──> EPIC-03 (DONE) → EPIC-04 (DONE) + SQ67 (DONE) → EPIC-05 (IN PROGRESS)
                    └──> EPIC-06
              EPIC-04 + 05 + 06 → ARCH-REVIEW-01
                                    ├──> EPIC-07 → EPIC-08
                                    └──> EPIC-11
              EPIC-04 + 08 → EPIC-09
              EPIC-03 + 06 + 07 → EPIC-10
              EPIC-04..10 → EPIC-12
```

**Critical path:** Phase 1 COMPLETE. EPIC-04 + SQ67 + EPIC-05 DONE.
EPIC-06 (Compare + Diff Hardening) is the last Phase 2 epic before ARCH-REVIEW-01.

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
| Total tests | ~1823 | 2000+ |
| Coverage | 65% | 70%+ |
| Golden trajectories | 15 (edit_plan 5 + qna 6 + repeated_condition 4) | 25+ (all 9 families) |
| Scorecard entries | 0 | 32+ |
| Task families tested | 4 (edit_plan + compare + qna + repeated_condition) | 9 |
| Scorecard pass rate (mock) | N/A | 100% |
| Scorecard pass rate (live) | N/A | >= 95% |

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
| 06 | Compare + Diff Service Hardening | Audit existing `core/comparison/` for untyped returns; define typed `CompareResult` schema |
| — | ARCH-REVIEW-01 | Collect module-level metrics (coupling, test coverage, API surface); draft ADR template with keep/change/remove columns |
| 07 | Structured Edit Planning | Define `EditPlan` schema in `plan_schema.py`; implement plan builder with constraint pre-checks |
| 08 | Preview + Apply Workflow | Wire preview generation into web backend route; implement frontend `PreviewPanel` component |
| 09 | Design Operations Workflow Pack | Draft prompt templates for layout recommendations; implement `design_ops.py` workflow module |
| 10 | Construction Drawing Workflow Pack | Gather sample construction drawings for regional convention analysis; draft grid/bay extraction logic |
| 11 | Session Durability + Scale Readiness | Audit current in-memory session lifecycle; define `SessionStore` ABC with GCS-backed implementation |
| 12 | Evaluation Harness + Quality Governance | Define scorecard JSON schema; scaffold `tests/eval/` directory with first fixture pack |

---

## 8. Global Next Actions

1. **Begin EPIC-06** — Compare + Diff Service Hardening (last Phase 2 epic)
2. **Prep ARCH-REVIEW-01** — After EPIC-06 complete
3. **Begin Phase 3** — EPIC-07 (Structured Edit Planning) after architecture review

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

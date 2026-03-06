# 041 — Implementation Status Tracker

**Status:** Living document (updated per epic)
**Date:** 2026-03-05
**Scope:** Track implementation progress across all 12 epics + architecture review gate.

---

## 1. Epic Status Overview

| # | Epic | Bead ID | Status | Branch | PR | Key Deliverables |
|---|------|---------|--------|--------|----|-----------------|
| 01 | Capability Audit + Architecture Baseline | cad-uns | DONE | `feature/epic-cad-01-capability-audit` | #71 | 6 docs (034-040), beads task tree |
| 02 | Core Contracts + Routing Foundation | cad-d9a | NOT STARTED | — | — | `response_schema.py`, `intent_router.py`, TaskFamily/ResponseType enums |
| 03 | Selection + Markup Interpretation Foundation | cad-wd2 | NOT STARTED | — | — | Region model, markup overlay ingestion, entity association |
| 04 | Region Q&A Vertical Slice | cad-grx | NOT STARTED | — | — | Region context builder, grounded Q&A pipeline, golden tests |
| 05 | Repeated-Condition Detection | cad-ccd | NOT STARTED | — | — | Similarity scoring, candidate search, preview/approval workflow |
| 06 | Compare + Diff Service Hardening | cad-3e4 | NOT STARTED | — | — | Typed compare schema, alignment diagnostics, regression fixtures |
| — | ARCH-REVIEW-01 | cad-sfw | NOT STARTED | — | — | Post-EPIC-06 quality/scalability review |
| 07 | Structured Edit Planning | cad-9ug | NOT STARTED | — | — | Edit plan schema, plan builder, constraint validation |
| 08 | Preview + Apply Workflow | cad-6zz | NOT STARTED | — | — | Preview pipeline, apply pipeline, audit trail |
| 09 | Design Operations Workflow Pack | cad-ady | NOT STARTED | — | — | Layout recommendations, revision summaries, takeoff candidates |
| 10 | Construction Drawing Workflow Pack | cad-8p2 | NOT STARTED | — | — | Grid/bay summaries, markup-to-redline, batch plans |
| 11 | Session Durability + Scale Readiness | cad-36p | NOT STARTED | — | — | State audit, durable metadata model, tracing/metrics |
| 12 | Evaluation Harness + Quality Governance | cad-m7d | NOT STARTED | — | — | Capability scorecard, fixture packs, CI regression |

---

## 2. Phase Progress

| Phase | Epics | Status | Gate |
|-------|-------|--------|------|
| **Phase 1: Foundation** | 01, 02, 03 | 1/3 complete | Contracts locked, `make check` green |
| **Phase 2: Core Intelligence** | 04, 05, 06 | 0/3 complete | Golden trajectories pass per family |
| **Architecture Review** | ARCH-REVIEW-01 | Not started | Written review with keep/change/remove |
| **Phase 3: Structured Editing** | 07, 08 | 0/2 complete | Edit plan + apply produce audit metadata |
| **Phase 4: Workflow Packs** | 09, 10 | 0/2 complete | Domain scorecard entries pass |
| **Phase 5: Production Readiness** | 11, 12 | 0/2 complete | Durable sessions + full scorecard green |

---

## 3. Dependency Chain Status

```
EPIC-01 (DONE) → EPIC-02 (next)
                    ├──> EPIC-03 → EPIC-04 → EPIC-05
                    └──> EPIC-06
              EPIC-04 + 05 + 06 → ARCH-REVIEW-01
                                    ├──> EPIC-07 → EPIC-08
                                    └──> EPIC-11
              EPIC-04 + 08 → EPIC-09
              EPIC-03 + 06 + 07 → EPIC-10
              EPIC-04..10 → EPIC-12
```

**Critical path:** EPIC-02 is the next gate. All downstream work is blocked until
contracts and routing foundation are in place.

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

---

## 5. Test Metrics Baseline

| Metric | Current (v0.5.0) | Target (all epics) |
|--------|-------------------|-------------------|
| Total tests | ~1351 | 1500+ |
| Coverage | 65% | 70%+ |
| Golden trajectories | 5 (edit_plan only) | 25+ (all 9 families) |
| Scorecard entries | 0 | 32+ |
| Task families tested | 1 | 9 |
| Scorecard pass rate (mock) | N/A | 100% |
| Scorecard pass rate (live) | N/A | >= 95% |

---

## 6. Risk Summary

| Risk | Status | Mitigation |
|------|--------|------------|
| Response contract churn | ACTIVE — schemas are "proposed" | Stabilize in EPIC-02, mark v2 |
| Intent router accuracy | ACTIVE — no router exists yet | Conservative thresholds in EPIC-02 |
| Markup entity detection | DEFERRED — no training data | Collect real samples before EPIC-03 |
| 500-entity context cap | ACTIVE — silent information loss | Token-budget context builder in EPIC-03 |
| Ephemeral session storage | KNOWN — lost on restart | Durable state migration in EPIC-11 |
| Large drawing performance | ACTIVE — blocks request thread | Background execution in EPIC-11 |

---

## 7. Next Actions

1. **Merge PR #71** — EPIC-01 docs into main
2. **Begin EPIC-02** — implement `response_schema.py` and `intent_router.py`
3. **Create feature branch** `feature/epic-cad-02-contracts-routing`
4. **First code deliverables:** TaskFamily enum, ResponseType enum, PlatformResponse model

---

## Related Documents

- 034-AT-AUDT — Capability audit baseline
- 038-PM-PLAN — Roadmap and phasing
- 040-AT-SPEC — Scale readiness assessment

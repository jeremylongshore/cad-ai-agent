# 038 — Drawing Intelligence Platform Roadmap

**Status:** Proposed
**Date:** 2026-03-05
**Depends on:** 034 (audit), 035 (architecture), 036 (contracts), 037 (eval), 039 (intent router)

---

## 1. Phased Rollout

### Phase 1: Foundation (EPICs 01-03)

Lock contracts, build routing and response infrastructure. No new user-visible features.

| Epic | Title | Deliverables | Gate |
|------|-------|-------------|------|
| **EPIC-01** | Capability Audit + Architecture Baseline | 6 docs (034-039), capability matrix | Docs reviewed, `make check` green |
| **EPIC-02** | Core Contracts + Routing Foundation | `response_schema.py`, `intent_router.py`, TaskFamily/ResponseType enums, unit tests | All contract invariant tests pass |
| **EPIC-03** | Selection + Markup Interpretation Foundation | Region model, markup overlay ingestion, entity association, debug tooling | New query tests pass, existing tests unbroken |

### Phase 2: Core Intelligence (EPICs 04-06)

First new task families: Q&A, repeated-condition detection, compare hardening.

| Epic | Title | Deliverables | Gate |
|------|-------|-------------|------|
| **EPIC-04** | Region Q&A Vertical Slice | Region context builder, grounded Q&A pipeline, UI rendering, golden tests | 5+ Q&A golden trajectories pass |
| **EPIC-05** | Repeated-Condition Detection | Similarity scoring, candidate search, preview/approval workflow, realistic fixtures | Repeated-condition scorecard entries pass |
| **EPIC-06** | Compare + Diff Service Hardening | Typed compare schema, alignment diagnostics, changelog, export bundle, regression fixtures | Compare golden trajectories pass |

### Mandatory Architecture Review (after Phase 2)

| Review | Title | Deliverables | Gate |
|--------|-------|-------------|------|
| **ARCH-REVIEW-01** | Post-EPIC-06 Architecture Review | Quality assessment, scalability review, LLM/tool boundary review, published decision | Written review with keep/change/remove recommendations |

### Phase 3: Structured Editing (EPICs 07-08)

Safe edit planning and apply workflows.

| Epic | Title | Deliverables | Gate |
|------|-------|-------------|------|
| **EPIC-07** | Structured Edit Planning | Edit plan schema, plan builder, constraint validation, golden tests | Safe/unsafe edit plan cases covered |
| **EPIC-08** | Preview + Apply Workflow | Preview pipeline, apply pipeline, audit trail, UI approval/export | Applied edits produce audit metadata |

### Phase 4: Workflow Packs (EPICs 09-10)

Domain-specific features for both user workflow classes.

| Epic | Title | Deliverables | Gate |
|------|-------|-------------|------|
| **EPIC-09** | Design Operations Workflow Pack | Layout recommendations, revision summaries, takeoff candidates, scope outputs | Design-ops scorecard entries pass |
| **EPIC-10** | Construction Drawing Workflow Pack | Grid/bay summaries, markup-to-redline, batch repeated-condition plans, field summaries | Construction scorecard entries pass |

### Phase 5: Production Readiness (EPICs 11-12)

Scale hardening and evaluation governance.

| Epic | Title | Deliverables | Gate |
|------|-------|-------------|------|
| **EPIC-11** | Session Durability + Scale Readiness | State audit, durable metadata model, tracing/metrics, scale smoke tests | Clear path beyond in-process sessions |
| **EPIC-12** | Evaluation Harness + Quality Governance | Capability scorecard, domain fixture packs, confidence tracking, CI regression | Full scorecard green, live regression <5% failure |

---

## 2. Dependency Graph

```
EPIC-01 (Capability Audit)
    |
    v
EPIC-02 (Contracts + Router)
    |
    ├──> EPIC-03 (Selection + Markup)
    |        |
    |        └──> EPIC-04 (Region Q&A)
    |                  |
    |                  └──> EPIC-05 (Repeated-Condition)
    |
    └──> EPIC-06 (Compare Hardening)
              |
    EPIC-04 + 05 + 06
              |
              v
         ARCH-REVIEW-01
              |
              ├──> EPIC-07 (Edit Planning)
              |        |
              |        └──> EPIC-08 (Preview + Apply)
              |
              ├──> EPIC-11 (Scale Readiness)
              |
    EPIC-04 + 08 ──> EPIC-09 (Design Ops Pack)
    EPIC-03 + 06 + 07 ──> EPIC-10 (Construction Pack)
              |
    EPIC-04..10
              |
              v
         EPIC-12 (Eval + Governance)
```

**Critical path:** EPIC-01 → 02 → 03 → 04 (Region Q&A is the first user-visible feature).

**Parallel tracks after EPIC-02:**
- Track A: Selection → Q&A → Repeated-Condition (read-only features)
- Track B: Compare Hardening (existing pipeline upgrade)
- Both converge at ARCH-REVIEW-01 before edit planning begins

---

## 3. Gate Criteria

Each epic must satisfy its gate before the next dependent epic begins.

| Gate Type | Criteria | Verified By |
|-----------|----------|------------|
| **Tests green** | `make check` passes, no regressions | CI (GitHub Actions) |
| **Coverage stable** | Coverage >= 65% (threshold in pyproject.toml) | `make test-cov` |
| **Golden trajectories** | All relevant trajectories pass with mock provider | `pytest tests/eval/` |
| **Scorecard entries** | New task family entries pass at mock tier | `make scorecard` |
| **Docs updated** | CLAUDE.md, 000-INDEX.md reflect new capabilities | Manual review |
| **PR reviewed** | Feature branch PR approved and merged | GitHub PR review |

---

## 4. Risk Register

| Risk | Impact | Likelihood | Mitigation |
|------|--------|-----------|------------|
| **Response contract churn** | High — breaks frontend/tests | Medium | Mark all 036 schemas as "proposed" until EPIC-02 stabilizes |
| **Intent router accuracy** | High — wrong pipeline = bad results | Medium | Conservative confidence threshold (0.9), fallback to edit_plan |
| **Gemini API changes** | Medium — breaks live provider | Low | Provider ABC insulates; mock tests always run |
| **Scope creep per epic** | Medium — delays cascade | High | Each epic has explicit deliverables list; no unplanned features |
| **Markup entity detection** | High — no training data exists | High | EPIC-09 deferred to Phase 3; collect real markup samples first |
| **V2 entity types** | Medium — 9 types read-only | Low | V2 types loaded but not edited; expand incrementally per epic |
| **Eval cost** | Low — API calls cost money | Low | Mock scorecard free; live scorecard only on push to main |
| **Large drawing perf** | Medium — 500 entity cap | Medium | Context builder token budgeting in EPIC-03 |

---

## 5. Success Criteria (Platform-Wide)

When all 12 epics are complete:

| Metric | Target |
|--------|--------|
| Task families supported | 9/9 |
| Golden trajectories | 25+ |
| Scorecard entries | 32+ |
| Scorecard pass rate (mock) | 100% |
| Scorecard pass rate (live) | >= 95% |
| Test count | 1500+ |
| Coverage | >= 70% |
| API versions | v1 (stable) + v2 (PlatformResponse) |
| Response types | 6 (all with typed envelopes) |

---

## Related Documents

- 034-AT-AUDT — Capability audit (baseline for EPIC-01)
- 035-AT-ARCH — Target architecture (what we're building toward)
- 036-AT-SPEC — Response contracts (implemented in EPIC-02)
- 037-TQ-SPEC — Evaluation plan (implemented in EPIC-12, incremental per epic)
- 039-AT-ADEC — Intent router (implemented in EPIC-02)

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
| **EPIC-03** | Selection Engine Upgrades | Regex text search, bbox query, find-similar, extended EntityIndex | New query tests pass, existing tests unbroken |

### Phase 2: Core Intelligence (EPICs 04-06)

First new task families: Q&A, summary, enhanced edits.

| Epic | Title | Deliverables | Gate |
|------|-------|-------------|------|
| **EPIC-04** | Q&A Pipeline | `answer` tool, Q&A context strategy, read-only safety check | 5+ Q&A golden trajectories pass |
| **EPIC-05** | Summary + Statistics | `summarize_drawing` tool, DrawingStats response | Summary scorecard entries pass |
| **EPIC-06** | Enhanced Edit Safety | Cross-op conflict detection, impact estimation, `protected_blocks` enforcement | Safety unit tests, no regressions |

### Phase 3: Advanced Intelligence (EPICs 07-09)

Domain-specific capabilities: compare integration, pattern search, markup.

| Epic | Title | Deliverables | Gate |
|------|-------|-------------|------|
| **EPIC-07** | Compare Pipeline Integration | Compare routed through intent router, PlatformResponse for diffs | Compare golden trajectories pass |
| **EPIC-08** | Repeated Condition Search | `find_pattern` tool, regex/spatial pattern matching | Pattern search scorecard entries pass |
| **EPIC-09** | Markup Interpretation | Cloud/arrow detection, markup entity classification | Markup golden trajectories pass |

### Phase 4: Specialized Outputs (EPICs 10-11)

Construction-drawing-specific features.

| Epic | Title | Deliverables | Gate |
|------|-------|-------------|------|
| **EPIC-10** | Takeoff + Estimation | `count_entities` tool, block-based quantity extraction | Takeoff scorecard entries pass |
| **EPIC-11** | Design Assist | Suggestion engine, rule-based recommendations | Design assist golden trajectories pass |

### Phase 5: Production (EPIC 12)

Full evaluation harness, production hardening, API v2 rollout.

| Epic | Title | Deliverables | Gate |
|------|-------|-------------|------|
| **EPIC-12** | Eval Harness + Production Readiness | `make scorecard` target, live regression CI, API v2 endpoints, v1 deprecation plan | Full scorecard green, live regression <5% failure |

---

## 2. Dependency Graph

```
EPIC-01 (Audit + Docs)
    |
    v
EPIC-02 (Contracts + Router) ──────────────────────────────┐
    |                                                       |
    ├──> EPIC-03 (Selection Upgrades)                       |
    |        |                                              |
    |        ├──> EPIC-04 (Q&A Pipeline)                    |
    |        |        |                                     |
    |        |        └──> EPIC-05 (Summary)                |
    |        |                                              |
    |        ├──> EPIC-08 (Repeated Condition)              |
    |        |                                              |
    |        └──> EPIC-09 (Markup Interpretation)           |
    |                                                       |
    ├──> EPIC-06 (Edit Safety) ──────┐                      |
    |                                |                      |
    ├──> EPIC-07 (Compare Integration)                      |
    |                                |                      |
    └──> EPIC-10 (Takeoff) ──────────┤                      |
         EPIC-11 (Design Assist) ────┘                      |
                                     |                      |
                                     v                      |
                               EPIC-12 (Eval + Production) <┘
```

**Critical path:** EPIC-01 → 02 → 03 → 04 (Q&A is the first user-visible feature).

**Parallel tracks after EPIC-02:**
- Track A: Selection → Q&A → Summary (read-only features)
- Track B: Edit Safety → Compare Integration (edit features)
- Track C: Selection → Repeated Condition / Markup (search features)

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

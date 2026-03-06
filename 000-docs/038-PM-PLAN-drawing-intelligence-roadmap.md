# 038 — Drawing Intelligence Platform Roadmap

**Status:** Proposed
**Date:** 2026-03-05
**Depends on:** 034 (audit), 035 (architecture), 036 (contracts), 037 (eval), 039 (intent router)

---

## 1. Phased Rollout

### Phase 1: Foundation (EPICs 01-03)

Lock contracts, build routing and response infrastructure. No new user-visible features.

| Epic | Title | Size | Deliverables | Gate |
|------|-------|------|-------------|------|
| **EPIC-01** | Capability Audit + Architecture Baseline | S | 6 docs (034-039), capability matrix | Docs reviewed, `make check` green |
| **EPIC-02** | Core Contracts + Routing Foundation | M | `response_schema.py`, `intent_router.py`, TaskFamily/ResponseType enums, unit tests | All contract invariant tests pass |
| **EPIC-03** | Selection + Markup Interpretation Foundation | L | Region model, markup overlay ingestion, entity association, debug tooling | New query tests pass, existing tests unbroken |

### Phase 2: Core Intelligence (EPICs 04-06)

First new task families: Q&A, repeated-condition detection, compare hardening.

| Epic | Title | Size | Deliverables | Gate |
|------|-------|------|-------------|------|
| **EPIC-04** | Region Q&A Vertical Slice | L | Region context builder, grounded Q&A pipeline, UI rendering, golden tests | 5+ Q&A golden trajectories pass |
| **EPIC-05** | Repeated-Condition Detection | M | Similarity scoring, candidate search, preview/approval workflow, realistic fixtures | Repeated-condition scorecard entries pass |
| **EPIC-06** | Compare + Diff Service Hardening | M | Typed compare schema, alignment diagnostics, changelog, export bundle, regression fixtures | Compare golden trajectories pass |

### Mandatory Architecture Review (after Phase 2)

| Review | Title | Size | Deliverables | Gate |
|--------|-------|------|-------------|------|
| **ARCH-REVIEW-01** | Post-EPIC-06 Architecture Review | S | Quality assessment, scalability review, LLM/tool boundary review, published decision | Written review with keep/change/remove recommendations |

### Phase 3: Structured Editing (EPICs 07-08)

Safe edit planning and apply workflows.

| Epic | Title | Size | Deliverables | Gate |
|------|-------|------|-------------|------|
| **EPIC-07** | Structured Edit Planning | L | Edit plan schema, plan builder, constraint validation, golden tests | Safe/unsafe edit plan cases covered |
| **EPIC-08** | Preview + Apply Workflow | M | Preview pipeline, apply pipeline, audit trail, UI approval/export | Applied edits produce audit metadata |

### Phase 4: Workflow Packs (EPICs 09-10)

Domain-specific features for three user workflow classes: Design Operations, Construction Drawing, and General Review. EPIC-09 and EPIC-10 provide dedicated workflow packs for Design Ops and Construction respectively. General Review users are served by capabilities already delivered in earlier phases — Q&A (EPIC-04), compare/diff (EPIC-06), and summary capabilities — so no dedicated workflow pack is needed for that class.

| Epic | Title | Size | Deliverables | Gate |
|------|-------|------|-------------|------|
| **EPIC-09** | Design Operations Workflow Pack | L | Layout recommendations, revision summaries, takeoff candidates, scope outputs | Design-ops scorecard entries pass |
| **EPIC-10** | Construction Drawing Workflow Pack | L | Grid/bay summaries, markup-to-redline, batch repeated-condition plans, field summaries | Construction scorecard entries pass |

### Phase 5: Production Readiness (EPICs 11-12)

Scale hardening and evaluation governance.

| Epic | Title | Size | Deliverables | Gate |
|------|-------|------|-------------|------|
| **EPIC-11** | Session Durability + Scale Readiness | XL | State audit, durable metadata model, tracing/metrics, scale smoke tests | Clear path beyond in-process sessions |
| **EPIC-12** | Evaluation Harness + Quality Governance | M | Capability scorecard, domain fixture packs, confidence tracking, CI regression | Full scorecard green, live regression <5% failure |

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
- Track C: General Review — served by Q&A (EPIC-04) + Compare (EPIC-06) + summaries; no dedicated workflow pack required
- All three tracks converge at ARCH-REVIEW-01 before edit planning begins

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

| Risk | Impact | Likelihood | Phase(s) | Mitigation |
|------|--------|-----------|----------|------------|
| **Response contract churn** | High — breaks frontend/tests | Medium | 1 | Mark all 036 schemas as "proposed" until EPIC-02 stabilizes |
| **Intent router accuracy** | High — wrong pipeline = bad results | Medium | 1-2 | Conservative confidence threshold (0.9), fallback to edit_plan |
| **Gemini API changes** | Medium — breaks live provider | Low | All | Provider ABC insulates; mock tests always run |
| **Scope creep per epic** | Medium — delays cascade | High | All | Each epic has explicit deliverables list; no unplanned features |
| **Markup entity detection** | High — no training data exists | High | 1, 4 | EPIC-03 builds foundation; EPIC-09 deferred to Phase 4; collect real markup samples first |
| **V2 entity types** | Medium — 9 types read-only | Low | 2-3 | V2 types loaded but not edited; expand incrementally per epic |
| **Eval cost** | Low — API calls cost money | Low | 2-5 | Mock scorecard free; live scorecard only on push to main |
| **Large drawing perf** | Medium — 500 entity cap | Medium | 1-2 | Context builder token budgeting in EPIC-03 |

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

## 6. Per-Phase Success Criteria

### Phase 1: Foundation

1. Intent router classifies all 9 task families with >= 90% accuracy on mock inputs
2. `PlatformResponse` envelope adopted as the sole response contract for new capabilities
3. 10+ golden trajectories passing (baseline set covering routing and selection)
4. Region model can associate entities to a user-selected area in test fixtures
5. All Phase 1 gate criteria met; `make check` green, coverage >= 65%

### Phase 2: Core Intelligence

1. 3 new task families operational: Q&A, repeated-condition detection, compare
2. 15+ golden trajectories passing across all implemented families
3. Capability scorecard pass rate >= 50% on mock provider
4. No regressions in existing edit pipeline tests
5. ARCH-REVIEW-01 completed with published keep/change/remove recommendations

### Phase 3: Structured Editing

1. Edit workflows pass >= 85% of golden trajectories on live Gemini
2. End-to-end scenarios complete: prompt -> plan -> validate -> preview -> apply -> save-as
3. Unsafe edit plans reliably rejected by constraint validation
4. Audit trail metadata attached to every applied edit
5. 20+ golden trajectories passing

### Phase 4: Workflow Packs

1. Design Operations scorecard entries pass per-class quality bars
2. Construction Drawing scorecard entries pass per-class quality bars
3. General Review users covered by Q&A + compare + summary (no gaps)
4. 25+ golden trajectories passing across all task families
5. Domain-specific fixture packs created for both workflow packs

### Phase 5: Production Readiness

1. Session durability implemented — state survives process restart
2. Eval harness runs automatically in CI on every push to main
3. Full capability scorecard green at mock tier, >= 95% at live tier
4. Tracing and metrics operational in production (Cloud Trace)
5. Scale smoke tests pass with drawings containing 500+ entities

---

## 7. Release Strategy

### Shippable Milestones

| Milestone | Phase | Description |
|-----------|-------|-------------|
| **Internal Alpha** | Phase 1 | Contracts and routing validated internally. Not user-visible. |
| **Beta (Read-Only Intelligence)** | Phase 2 | Q&A, compare, and repeated-condition detection available to users. No editing capabilities exposed. Safe to deploy — all features are read-only. |
| **GA (Safe Editing)** | Phase 3 | Structured edit planning and preview/apply workflows enabled. Full pipeline operational with audit trail. First release where users can modify drawings. |
| **Domain Packs** | Phase 4 | Design Ops and Construction workflow packs shipped incrementally. Each pack is independently deployable once its scorecard entries pass. |
| **Production Hardened** | Phase 5 | Session durability, automated eval governance, and scale readiness. Platform considered production-grade. |

### Hold Conditions

The following conditions would cause a release hold:

- **ARCH-REVIEW-01 finds fundamental issues** — If the architecture review identifies structural problems (e.g., LLM/tool boundary violations, unscalable patterns), Phase 3 work pauses until remediation is complete.
- **Quality gate failures** — Any phase whose scorecard pass rate drops below its target blocks progression to the next phase.
- **Edit safety regression** — If applied edits corrupt DXF output or violate protected-layer rules, editing features are disabled until root cause is fixed.
- **Live API pass rate below 85%** — Indicates prompt/schema drift; requires investigation before GA release.

### Incremental vs Full Launch

Releases are incremental, not big-bang:

- **Phase 2 (Beta)** is the first external release point. Read-only intelligence features (Q&A, compare, repeated-condition) can ship independently as each epic completes.
- **Phase 3 (GA)** gates on all edit safety tests passing. EPIC-07 (planning) and EPIC-08 (preview/apply) ship together since planning without apply has no user value.
- **Phase 4** workflow packs are independently deployable — EPIC-09 (Design Ops) and EPIC-10 (Construction) can ship on separate timelines based on which domain has more user demand.
- **Phase 5** is operational hardening. The platform is functional after Phase 4; Phase 5 makes it durable and governable at scale.

---

## Related Documents

- 034-AT-AUDT — Capability audit (baseline for EPIC-01)
- 035-AT-ARCH — Target architecture (what we're building toward)
- 036-AT-SPEC — Response contracts (implemented in EPIC-02)
- 037-TQ-SPEC — Evaluation plan (implemented in EPIC-12, incremental per epic)
- 039-AT-ADEC — Intent router (implemented in EPIC-02)

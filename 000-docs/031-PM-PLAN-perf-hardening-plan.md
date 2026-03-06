# CAD DXF Agent — Performance Hardening Plan

**Program Epic:** `cad-uao` — Program — CAD DXF Agent Performance & Engineer Usability
**Status:** [NOT STARTED]
**Owner:** Claude (all phases)

---

## Phase Plan

| Phase | Branch | PR Title | Depends On | Status |
|-------|--------|----------|------------|--------|
| 01 | `feature/perf-phase-01-responsive-pipeline` | Phase 01: Responsive pipeline + progress timings | none | [NOT STARTED] |
| 02 | `feature/perf-phase-02-support-report` | Phase 02: DXF stats + support coverage + actionable warnings | Phase 01 DONE | [NOT STARTED] |
| 03 | `feature/perf-phase-03-selection-disambiguation` | Phase 03: Faster selection + deterministic disambiguation + pin target | Phase 02 DONE | [NOT STARTED] |
| 04 | `feature/perf-phase-04-operability` | Phase 04: Perf budgets + DXF zoo + repro bundles + runbook | Phase 03 DONE | [NOT STARTED] |
| 05 | `feature/perf-phase-05-history-export` | Phase 05: Scalable history + async save/export | Phase 04 DONE | [NOT STARTED] |
| 06 | `feature/perf-phase-06-validation-otel` | Phase 06: Validator perf + OTEL overhead controls | Phase 05 DONE | [NOT STARTED] |

### Program Control Epics (Cross-Cutting)

| Epic | Bead ID | Area |
|------|---------|------|
| Branch/Commit/PR Hygiene | `cad-uao.7` | infra |
| Perf Benchmarks & Budgets | `cad-uao.8` | perf |
| Reproducibility & Evidence | `cad-uao.9` | perf |
| Documentation & Runbooks | `cad-uao.10` | docs |

---

## Phase 01 — Responsive Pipeline & Progress UI [NOT STARTED]

**Bead:** `cad-uao.1`
**Branch:** `feature/perf-phase-01-responsive-pipeline`
**PR Title:** Phase 01: Responsive pipeline + progress timings
**Goal:** Eliminate UI freezes during pipeline execution. Show real-time stage progress with timings. Establish headless GUI smoke testing in CI.
**Risk:** HIGH — touches MainWindow (578 lines), PySide6 threading model requires careful signal/slot wiring.
**Rollback:** Revert branch. UI reverts to synchronous pipeline (no data loss possible).

### Epic 01.1 — Off-Main-Thread Execution Pipeline [NOT STARTED]

**Bead:** `cad-uao.1.1`
**Outcome:** Pipeline stages run in a QThread worker. UI never blocks for >50ms during pipeline execution.

| # | Task | Bead ID | Depends On | Owner | Status |
|---|------|---------|------------|-------|--------|
| 1 | Introduce PipelineWorker QThread wrapper | `cad-uao.1.1.1` | — | core/ui | [NOT STARTED] |
| 2 | Move load/plan/validate/apply/save into PipelineWorker | `cad-uao.1.1.2` | 1.1.1 | ui | [NOT STARTED] |
| 3 | Ensure deterministic ordering and cancellation | `cad-uao.1.1.3` | 1.1.2 | ui | [NOT STARTED] |
| 4 | Integration test: pipeline runs headless on fixture | `cad-uao.1.1.4` | 1.1.2 | test | [NOT STARTED] |

**Task 1 Acceptance:**
- `PipelineWorker(QThread)` class in `src/cad_dxf_agent/core/pipeline_worker.py`
- Signals: `stage_started(str)`, `stage_completed(str, float)`, `pipeline_finished(result)`, `pipeline_error(str)`
- Accepts callable pipeline function + args
- Unit test verifies signal emission order

**Task 2 Acceptance:**
- `MainWindow._on_plan()` dispatches to PipelineWorker instead of inline calls
- `MainWindow._on_apply()` dispatches to PipelineWorker
- UI buttons disabled during execution, re-enabled on finish/error
- No `QApplication.processEvents()` hacks

**Task 3 Acceptance:**
- Cancellation: user can cancel mid-pipeline (Cancel button or Escape)
- Cancellation rolls back cleanly — no partial changeset, no half-applied ops
- Double-dispatch guard: starting a new pipeline while one is running is rejected
- Test: start plan, cancel during planner, verify clean state

**Task 4 Acceptance:**
- `tests/integration/test_pipeline_worker.py` exists
- Uses `QT_QPA_PLATFORM=offscreen` (CI-safe)
- Verifies signal sequence on create_minimal_dxf fixture
- Passes in <5 seconds

### Epic 01.2 — Progress Timings + Stage Telemetry [NOT STARTED]

**Bead:** `cad-uao.1.2`
**Outcome:** Engineers see exactly which stage is running and how long each took. Timings can be copied for bug reports.

| # | Task | Bead ID | Depends On | Owner | Status |
|---|------|---------|------------|-------|--------|
| 1 | Expose stage boundaries and durations | `cad-uao.1.2.1` | 1.1.2 | perf | [NOT STARTED] |
| 2 | UI progress indicator with stage labels | `cad-uao.1.2.2` | 1.2.1 | ui | [NOT STARTED] |
| 3 | Timings panel view with copy-to-clipboard | `cad-uao.1.2.3` | 1.2.2 | ui | [NOT STARTED] |

**Task 1 Acceptance:**
- `StageTimings` dataclass: `{stage_name: str, duration_ms: float, timestamp: datetime}`
- PipelineWorker emits `stage_timing` signal per stage
- Timings accumulate in result object
- Unit test: all durations > 0, stages in order

**Task 2 Acceptance:**
- QProgressBar (indeterminate) + QLabel("Loading DXF...") during execution
- Label updates per stage: "Loading DXF...", "Building context...", "Running planner...", "Validating...", "Applying changes...", "Saving..."
- Progress bar hides on completion/error

**Task 3 Acceptance:**
- Collapsible "Timings" section below status log
- Table: Stage | Duration (ms)
- "Copy" button → clipboard (markdown table format)
- Updates after each pipeline run

### Epic 01.3 — GUI Smoke Tests (Minimal Headless) [NOT STARTED]

**Bead:** `cad-uao.1.3`
**Outcome:** Basic GUI functionality tested in CI without a display server.

| # | Task | Bead ID | Depends On | Owner | Status |
|---|------|---------|------------|-------|--------|
| 1 | Headless startup test | `cad-uao.1.3.1` | — | test | [NOT STARTED] |
| 2 | Load fixture + trigger plan smoke | `cad-uao.1.3.2` | 1.3.1 | test | [NOT STARTED] |
| 3 | Wire GUI smoke tests into CI | `cad-uao.1.3.3` | 1.3.2 | ci | [NOT STARTED] |

**Task 1 Acceptance:**
- `tests/smoke/test_gui_smoke.py` with `@pytest.mark.smoke`
- MainWindow instantiates and shows under offscreen platform
- Test completes in <5 seconds, no crash

**Task 2 Acceptance:**
- Opens minimal DXF, triggers mock planner, verifies ops checkboxes populated
- Passes headless

**Task 3 Acceptance:**
- CI runs GUI smoke on ubuntu with `QT_QPA_PLATFORM=offscreen`
- PySide6 installed in CI for this job
- Windows skipped for GUI tests

---

## Commit Plan — Phase 01

**Branch:** `feature/perf-phase-01-responsive-pipeline`
**Target:** 8 atomic commits

| # | Commit Message | Beads | Files |
|---|---------------|-------|-------|
| 1 | `feat(core): add PipelineWorker QThread wrapper` | cad-uao.1.1.1 | `src/cad_dxf_agent/core/pipeline_worker.py`, `tests/unit/test_pipeline_worker.py` |
| 2 | `refactor(ui): dispatch plan/apply through PipelineWorker` | cad-uao.1.1.2 | `src/cad_dxf_agent/ui/main_window.py` |
| 3 | `feat(ui): add cancellation and double-dispatch guard` | cad-uao.1.1.3 | `src/cad_dxf_agent/ui/main_window.py`, `src/cad_dxf_agent/core/pipeline_worker.py` |
| 4 | `test(integration): pipeline worker headless integration test` | cad-uao.1.1.4 | `tests/integration/test_pipeline_worker.py` |
| 5 | `feat(perf): expose stage timings from PipelineWorker` | cad-uao.1.2.1 | `src/cad_dxf_agent/core/pipeline_worker.py` |
| 6 | `feat(ui): add progress indicator with stage labels` | cad-uao.1.2.2 | `src/cad_dxf_agent/ui/main_window.py` |
| 7 | `feat(ui): add timings panel with copy-to-clipboard` | cad-uao.1.2.3 | `src/cad_dxf_agent/ui/main_window.py` |
| 8 | `test(smoke): headless GUI smoke tests + CI wiring` | cad-uao.1.3.1, cad-uao.1.3.2, cad-uao.1.3.3 | `tests/smoke/test_gui_smoke.py`, `.github/workflows/ci.yml` |

**PR Description Template:**
```markdown
## Phase 01: Responsive Pipeline & Progress Timings

**Beads:** cad-uao.1 (Phase 01), cad-uao.1.1, cad-uao.1.2, cad-uao.1.3

### Summary
- Move pipeline execution (load/plan/validate/apply/save) to QThread worker
- UI never blocks during pipeline execution
- Real-time progress indicator with stage labels
- Timings panel with copy-to-clipboard
- Headless GUI smoke tests in CI

### Perf Impact
| Metric | Before | After |
|--------|--------|-------|
| UI responsiveness during plan | BLOCKED (5-30s freeze) | <50ms response |
| Stage visibility | None | Real-time labels + timings |
| GUI test coverage | 0% | Basic smoke coverage |

### Risk + Rollback
- Risk: QThread signal/slot wiring is PySide6-specific; tested with offscreen
- Rollback: revert branch; no data model changes
```

---

## Phase 02 — Drawing Stats + Support Report + Actionable Warnings [NOT STARTED]

**Bead:** `cad-uao.2`
**Branch:** `feature/perf-phase-02-support-report`
**Depends On:** Phase 01 DONE

### Epic 02.1 — Drawing Stats Panel (Engineer-Facing)

**Outcome:** On load, engineers see entity counts by type, layer summary, block nesting depth, unsupported coverage %, and estimated edit cost heuristic.

| # | Task | Owner | Status |
|---|------|-------|--------|
| 1 | Compute stats: entities by type, layers, blocks, nested depth | core | [NOT STARTED] |
| 2 | Compute unsupported coverage + counts | core | [NOT STARTED] |
| 3 | Compute estimated edit cost heuristic | core | [NOT STARTED] |
| 4 | UI panel and export to JSON | ui | [NOT STARTED] |
| 5 | Tests for stats correctness (fixtures) | test | [NOT STARTED] |

### Epic 02.2 — Support Report on Load

**Outcome:** Structured support report artifact generated on every DXF load. UI entrypoint. Early warning if unsupported > threshold.

| # | Task | Owner | Status |
|---|------|-------|--------|
| 1 | Generate support report artifact on load | core | [NOT STARTED] |
| 2 | UI entrypoint: "Support Report" | ui | [NOT STARTED] |
| 3 | Warn early when unsupported > threshold | core | [NOT STARTED] |

### Epic 02.3 — Actionable Warnings (Replace Silent Skips)

**Outcome:** Every skipped/unsupported entity produces a structured warning with code, entity ref, and suggested alternative action.

| # | Task | Owner | Status |
|---|------|-------|--------|
| 1 | Standardize warning structure: code, entity, suggested action | core | [NOT STARTED] |
| 2 | Map top unsupported types to suggested alternatives | core | [NOT STARTED] |
| 3 | Update validators to emit actionable warnings | core | [NOT STARTED] |
| 4 | Golden tests for warnings output | test | [NOT STARTED] |

---

## Phase 03 — Deterministic Selection + Disambiguation + Target Pinning [NOT STARTED]

**Bead:** `cad-uao.3`
**Branch:** `feature/perf-phase-03-selection-disambiguation`
**Depends On:** Phase 02 DONE

### Epic 03.1 — Two-Stage Selection (Fast Shortlist → Refine)

**Outcome:** Entity selection is two-stage: fast heuristic shortlist, then ranked refinement. Selection time on 1000-entity fixture < 50ms.

| # | Task | Owner | Status |
|---|------|-------|--------|
| 1 | Shortlist heuristic: layer/type/blockname/text tags | core | [NOT STARTED] |
| 2 | Refine ranking: distance/bbox similarity/proximity to text | core | [NOT STARTED] |
| 3 | Perf test: selection time on large synthetic fixture | perf | [NOT STARTED] |

### Epic 03.2 — Deterministic Disambiguation Output

**Outcome:** When target is ambiguous, planner returns top N candidates with "why" fields. Structured result type. Golden fixture for ambiguous targets.

| # | Task | Owner | Status |
|---|------|-------|--------|
| 1 | Return top N candidates with "why" fields | core | [NOT STARTED] |
| 2 | Structured "needs disambiguation" result type | core | [NOT STARTED] |
| 3 | Golden fixture: ambiguous targets | test | [NOT STARTED] |

### Epic 03.3 — Pin Target UI (Engineer Bypass)

**Outcome:** User can click an entity to "pin" it as the target, bypassing disambiguation entirely.

| # | Task | Owner | Status |
|---|------|-------|--------|
| 1 | Click-to-pin entity + show handle/id | ui | [NOT STARTED] |
| 2 | Pinned target flows into planner/ops | core | [NOT STARTED] |
| 3 | Tests: pin survives edits / invalidates safely | test | [NOT STARTED] |

---

## Phase 04 — Operability: Budgets + DXF Zoo + Repro Bundles + Runbook [NOT STARTED]

**Bead:** `cad-uao.4`
**Branch:** `feature/perf-phase-04-operability`
**Depends On:** Phase 03 DONE

### Epic 04.1 — Performance Budgets + CI Enforcement

**Outcome:** Defined budgets per stage per entity scale. Benchmark harness. CI gate fails on regression.

| # | Task | Owner | Status |
|---|------|-------|--------|
| 1 | Define budgets: load/index/apply/save per entity scale | perf | [NOT STARTED] |
| 2 | Add benchmark harness + baseline fixtures | perf | [NOT STARTED] |
| 3 | CI gate: fail if regressions > threshold | ci | [NOT STARTED] |

**Budget Targets (Initial):**
| Stage | 200 entities | 1000 entities | 5000 entities |
|-------|-------------|---------------|---------------|
| Load DXF | <200ms | <500ms | <2000ms |
| Build index | <50ms | <200ms | <500ms |
| Validate (10 ops) | <20ms | <50ms | <100ms |
| Apply (10 ops) | <100ms | <200ms | <500ms |
| Save DXF | <200ms | <500ms | <2000ms |

### Epic 04.2 — DXF Zoo + Synthetic Generator Suite

**Outcome:** Curated collection of nasty real-world DXF patterns + parameterized synthetic generator for scale testing.

| # | Task | Owner | Status |
|---|------|-------|--------|
| 1 | Curate nasty DXF zoo fixtures + metadata | test | [NOT STARTED] |
| 2 | Extend synthetic generator (size tiers) | test | [NOT STARTED] |
| 3 | Run zoo in CI smoke (subset) | ci | [NOT STARTED] |

### Epic 04.3 — Repro Bundle Export (One-Click Debugging)

**Outcome:** Single-click exports a .zip containing: input DXF hash, drawing stats, planner context snapshot, ChangeSet JSON, validation results, stage timings.

| # | Task | Owner | Status |
|---|------|-------|--------|
| 1 | Bundle contents: hash, stats, context, changeset, validation, timings | core | [NOT STARTED] |
| 2 | UI button: Export Repro Bundle | ui | [NOT STARTED] |
| 3 | CLI/Headless export path | core | [NOT STARTED] |
| 4 | Golden test: bundle schema stability | test | [NOT STARTED] |

### Epic 04.4 — Troubleshooting Runbook

**Outcome:** Markdown runbook with symptom → cause → diagnostics → fix matrix. Includes "how to file a bug" template with repro bundle.

| # | Task | Owner | Status |
|---|------|-------|--------|
| 1 | Symptom → cause → diagnostics → fix matrix | docs | [NOT STARTED] |
| 2 | Bug report template with repro bundle | docs | [NOT STARTED] |

---

## Phase 05 — History + Save/Export [NOT STARTED]

**Bead:** `cad-uao.5`
**Branch:** `feature/perf-phase-05-history-export`
**Depends On:** Phase 04 DONE

### Epic 05.1 — Delta-Based Undo/Redo + Checkpoints

**Outcome:** Replace full-doc snapshot history with delta-based ops + periodic checkpoints. Configurable history cap. 200-op stress test passes within memory budget.

Current state: `edit_history.py` (124 lines) stores full DXF bytes per edit (~100KB each for 200-entity drawing). Unbounded growth.

| # | Task | Owner | Status |
|---|------|-------|--------|
| 1 | Design history delta schema | core | [NOT STARTED] |
| 2 | Implement inverse ops for common operations | core | [NOT STARTED] |
| 3 | Checkpoint snapshots every N ops | core | [NOT STARTED] |
| 4 | Configurable history cap | core | [NOT STARTED] |
| 5 | Stress test: 200 ops memory/time | perf | [NOT STARTED] |

### Epic 05.2 — Async Save/Export + Debounce + Caching

**Outcome:** Save and export operations run in background worker. Optional debounced save mode. Export results cached by revision id.

| # | Task | Owner | Status |
|---|------|-------|--------|
| 1 | Move save/export to worker | core | [NOT STARTED] |
| 2 | Debounced/batched save mode | core | [NOT STARTED] |
| 3 | Export caching keyed by revision id | core | [NOT STARTED] |
| 4 | Benchmarks: save/export on large fixture | perf | [NOT STARTED] |

---

## Phase 06 — Validator Performance + OTEL Hardening [NOT STARTED]

**Bead:** `cad-uao.6`
**Branch:** `feature/perf-phase-06-validation-otel`
**Depends On:** Phase 05 DONE

### Epic 06.1 — Validator Scaling Improvements

**Outcome:** Validators use precomputed lookups, short-circuit on first blocker. Micro-benchmarks in CI ensure no regressions.

| # | Task | Owner | Status |
|---|------|-------|--------|
| 1 | Precompute common lookups (protected layers set, handle→entity map) | core | [NOT STARTED] |
| 2 | Short-circuit blocker checks (stop on first blocker per op) | core | [NOT STARTED] |
| 3 | Validator micro-benchmarks in CI | perf | [NOT STARTED] |

### Epic 06.2 — OTEL Overhead Controls + Visibility

**Outcome:** Tracing uses sampling + coarse spans. Default off in production. UI indicator shows tracing state. Perf test measures OTEL on/off overhead delta.

| # | Task | Owner | Status |
|---|------|-------|--------|
| 1 | Sampling policy + coarse spans only | infra | [NOT STARTED] |
| 2 | OTEL default off + visible UI indicator | ui | [NOT STARTED] |
| 3 | Perf test: OTEL on/off overhead delta | perf | [NOT STARTED] |

---

## Dependency Map (Critical Links)

```
Phase 01 (cad-uao.1)
  └── no deps (starts immediately)
       ├── Task 1.1.1 (PipelineWorker wrapper) → first
       ├── Task 1.1.2 (move pipeline to worker) → depends on 1.1.1
       ├── Task 1.1.3 (cancellation) → depends on 1.1.2
       ├── Task 1.1.4 (integration test) → depends on 1.1.2
       ├── Task 1.2.1 (stage timings) → depends on 1.1.2
       ├── Task 1.2.2 (progress UI) → depends on 1.2.1
       ├── Task 1.2.3 (timings panel) → depends on 1.2.2
       ├── Task 1.3.1 (headless startup) → no deps
       ├── Task 1.3.2 (load+plan smoke) → depends on 1.3.1
       └── Task 1.3.3 (CI wiring) → depends on 1.3.2

Phase 02 (cad-uao.2) → depends on Phase 01 DONE
Phase 03 (cad-uao.3) → depends on Phase 02 DONE
Phase 04 (cad-uao.4) → depends on Phase 03 DONE
Phase 05 (cad-uao.5) → depends on Phase 04 DONE
Phase 06 (cad-uao.6) → depends on Phase 05 DONE

Cross-cutting:
  - Any task needing timings → depends on cad-uao.1.2.1
  - Any task needing stats/support → depends on Phase 02 Epic 02.1
  - Any perf CI gating → depends on Phase 04 Epic 04.1
```

---

## Progress Markers & Completion Annotation Templates

### Task Completion Note Template
```markdown
## Completion: [TASK TITLE]
**Bead:** cad-uao.X.Y.Z
**Status:** DONE
**Files Changed:**
- src/cad_dxf_agent/core/pipeline_worker.py (new)
- tests/unit/test_pipeline_worker.py (new)

**How to Test:**
- `pytest tests/unit/test_pipeline_worker.py -v`
- `QT_QPA_PLATFORM=offscreen pytest tests/integration/test_pipeline_worker.py -v`

**Before/After (if perf):**
- UI responsiveness: BLOCKED (30s) → <50ms
- Pipeline total: ~200ms → ~200ms (no regression)

**Follow-ups Created:**
- (none, or new bead IDs)
```

### Phase Completion Summary Template
```markdown
## Phase Completion: Phase XX — [Title]
**Bead:** cad-uao.X
**CI:** green (link)
**PR:** merged (#XX)

**Performance Deltas:**
| Metric | Before | After | Delta |
|--------|--------|-------|-------|
| UI freeze during plan | 5-30s | <50ms | -99% |

**User-Visible Improvements:**
- Real-time progress indicator during pipeline
- Stage timings visible and copyable

**Regression Risks Addressed:**
- Double-dispatch guard prevents race conditions
- Cancellation tested with golden fixture
```

---

## Definition of Done — Entire Program

All of the following must be true:

1. All 6 phase epics marked `[DONE]` in beads
2. All phase PRs merged to main
3. CI green across all workflows (lint, typecheck, test matrix, security, GUI smoke)
4. Performance budgets defined and enforced in CI (Phase 04+)
5. DXF zoo fixtures + synthetic generator available (Phase 04+)
6. Repro bundle export functional (Phase 04+)
7. Troubleshooting runbook committed (Phase 04+)
8. Undo/redo scalable to 200 ops within memory budget (Phase 05)
9. OTEL overhead < 5% with tracing on (Phase 06)
10. Coverage remains ≥ 65% (threshold in pyproject.toml)
11. No known P0/P1 bugs open
12. `bd sync` — all beads state committed and pushed

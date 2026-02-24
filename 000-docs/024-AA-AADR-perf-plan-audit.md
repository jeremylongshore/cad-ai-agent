# AADR: Performance Hardening Plan Audit

**Doc ID:** 024-AA-AADR
**Date:** 2026-02-23
**Scope:** `cad-uao` program — 6 phases, 4 program controls, 24 beads

## Purpose

Audited the 24 beads in `cad-uao` (6 phases, 4 program controls, 3 sub-epics, 10 tasks) against the actual codebase to identify items that already exist in code, process overhead with no code deliverable, and genuine gaps missed by the original plan. Results inform a restructure from 6 phases (~50 tasks) down to 4 phases (~30 tasks).

---

## 1. KILL LIST — Items to Delete from Beads

### 1.1 Phase 06 Is ~80% Already Done

| Bead | Task | Why Kill | Evidence |
|------|------|----------|----------|
| Epic 06.1 task 1 | Precompute common lookups | **Already exists.** `entity_index.py` builds `_by_handle`, `_by_layer`, `_by_type`, `_text_index` dicts in `__init__`. All O(1). | `entity_index.py:18-33` |
| Epic 06.1 task 2 | Short-circuit blocker checks | **Already exists.** `validators.py` returns early on first blocker per operation (unsupported op → missing handle → entity not found → protected layer). | `validators.py:53-81` |
| Epic 06.2 task 1 | Sampling + coarse spans only | **Already exists.** OTEL uses one span per pipeline stage (not per-entity). `_NoOpTracer` when disabled. | `otel.py:108-117`, `validators.py:27-28` |
| Epic 06.2 task 2 | OTEL default off + UI indicator | **Already off by default.** `OTEL_ENABLED` defaults to empty string → `False`. | `settings.py:36` |

**Net effect:** Phase 06 shrinks to just **validator micro-benchmarks** (task 3) and **OTEL overhead delta test** (task 3). Not worth a whole phase. Fold remainder into Phase 04 (operability).

### 1.2 Program Control Epics — 3 of 4 Are Process Noise

| Bead | Epic | Why Kill |
|------|------|----------|
| `cad-uao.7` | Branch/Commit/PR Hygiene | **Already implemented.** Pre-commit hooks, CI lint/format/type/test, conventional commits in CLAUDE.md. No code deliverable. |
| `cad-uao.9` | Reproducibility & Evidence | **Already covered** by OTEL tracing + CI artifacts. "Evidence templates" = documentation, not code. Redundant with Phase 04 repro bundles. |
| `cad-uao.10` | Documentation & Runbooks | **Already exists.** `023-AA-AUDT-appaudit-devops-playbook.md` IS the runbook. Phase 04 Epic 04.4 already plans a troubleshooting runbook. Duplicate. |

**Keep:** `cad-uao.8` (Perf Benchmarks & Budgets) — real code work, but should merge into Phase 04 Epic 04.1.

### 1.3 Phase 03 — Selection/Disambiguation Is Half-Baked

| Bead | Task | Issue |
|------|------|-------|
| Epic 03.1 task 1 | Shortlist heuristic | **Already exists.** `selectors.py:resolve_candidate_set()` (lines 64-122) does multi-stage resolution: exact ID → layer+type+text intersection → spatial proximity. |
| Epic 03.3 | Pin Target UI | **Requires canvas/viewport rendering** which doesn't exist. `MainWindow` has no entity click targets — it's a text log + checkboxes. This is a V2 feature, not a perf hardening task. |

### 1.4 Phase 02 — Partially Redundant

| Bead | Task | Issue |
|------|------|-------|
| Epic 02.1 task 2 | Compute unsupported coverage | **Already exists.** `DrawingContext.unsupported_entity_types` is populated by `dxf_reader.load_dxf()`. Coverage = `len(unsupported) / len(all_dxf_types)`. Trivial computation. |

---

## 2. GAP LIST — Things Missing from the Plan

### Gap 1: No Hybrid Planner

The mega prompt specifically asked for **"Hybrid planning (deterministic first; LLM on low confidence)"**. The plan has zero tasks for this. This is arguably the highest-impact perf item — skip LLM entirely for obvious operations (e.g., "delete entity X" where X is an exact handle).

### Gap 2: No Planner Timeout/Retry Controls

The mega prompt asked for **"Strict timeouts + bounded retries + fail-fast"** and **"Determinism controls (pinned model, temperature, strict JSON)"**. None of these exist as tasks. Currently `agent_provider.py` has `MAX_AGENT_TURNS = 10` (line 33) but no timeout, no retry backoff, no temperature pinning.

### Gap 3: No Planner Trace View

The mega prompt asked for a **"Planner Trace view (latency breakdown + outcomes)"** — a dev tools panel showing what the LLM did, how long each turn took, what tools it called. Not in the plan.

### Gap 4: context_builder Already Does Progressive Disclosure

`context_builder.py` has `subset_context()` (line 37) and `token_economy_summary()`. The plan should use these as the foundation for "progressive context disclosure" rather than building something new.

### Gap 5: Edit History Caps Are Trivial

Adding `max_snapshots` to `EditHistory.__init__` and pruning oldest on push is ~10 lines. Shouldn't be a 5-task epic. The delta-based history (Phase 05) is much more complex and questionable ROI for v0.1.

### Gap 6: Save/Export Debounce Is Premature

Users edit once, save once. There's no auto-save or rapid-fire editing loop. "Debounced/batched saves" solves a problem that doesn't exist yet.

---

## 3. RECOMMENDED RESTRUCTURE

### Before: 6 Phases, 10 Program Epics, ~50 Tasks

Phases 01-06 + 4 program control epics. Sequential chain. Heavy process overhead.

### After: 4 Phases, ~30 Tasks

| Phase | What | Rationale |
|-------|------|-----------|
| **01** | Responsive Pipeline + Progress UI | Unchanged. Biggest perceived win. Genuinely new work. |
| **02** | Drawing Stats + Actionable Warnings + Planner Controls | Merge current P02 + planner timeout/retry/hybrid planning from the gaps. Drop "Support Report" (just a JSON export of stats). |
| **03** | Operability: Budgets + Zoo + Repro Bundles + History Caps | Merge current P04 + history caps from P05 + validator micro-benchmarks from P06. Drop runbook epic (already exists). |
| **04** | Selection Refinement + Planner Trace | What remains of P03 (disambiguation output, ranking refinement) + planner trace view. Drop pin-target (needs canvas). |

### Delete Entirely

| Item | Reason |
|------|--------|
| Phase 05 | Delta history = over-engineering for v0.1; save debounce = premature; async save folded into P01 worker |
| Phase 06 | Already implemented except micro-benchmarks, which go to P03 |
| Program Control 7 | Process overhead, no code deliverable |
| Program Control 9 | Covered by OTEL + CI, redundant with P04 repro bundles |
| Program Control 10 | Duplicate of existing runbook doc (023) |
| Program Control 8 | Merge into P03 (perf budgets become part of operability) |

### Beads to Close

```bash
# Already-done items
bd close cad-uao.7 --reason "Already implemented: pre-commit hooks + CI + CLAUDE.md conventions"
bd close cad-uao.9 --reason "Covered by OTEL + CI artifacts + Phase 04 repro bundles"
bd close cad-uao.10 --reason "Duplicate: appaudit playbook (023) already exists as runbook"

# Phases to fold/drop
bd close cad-uao.6 --reason "80% already implemented. Remaining tasks folded into Phase 04"
bd close cad-uao.5 --reason "Delta history = over-engineering for v0.1. History caps folded into Phase 04. Save debounce premature."
```

### New Tasks to Create (From Gaps)

```bash
# Under Phase 02 — planner hardening
bd create --type task --title "Add planner timeout + bounded retries + fail-fast" --parent cad-uao.2
bd create --type task --title "Pin model version + temperature in provider config" --parent cad-uao.2
bd create --type task --title "Hybrid planner: deterministic-first for obvious ops" --parent cad-uao.2

# Under Phase 04 (renumbered to 03) — operability
bd create --type task --title "Add max_snapshots cap to EditHistory" --parent cad-uao.4
bd create --type task --title "Validator micro-benchmarks in CI" --parent cad-uao.4

# Under Phase 03 (renumbered to 04) — selection + planner trace
bd create --type task --title "Planner Trace view: turn-by-turn latency + tool calls" --parent cad-uao.3
```

---

## 4. VERIFICATION CHECKLIST

After restructure is applied:

- [ ] `bd children cad-uao` shows 4 phase epics + 1 program control (P08 merged)
- [ ] `bd dep tree cad-uao` shows clean sequential chain
- [ ] Total tasks drops from ~50 to ~30
- [ ] No tasks duplicate existing code
- [ ] All mega-prompt requirements covered: hybrid planner, timeouts, planner trace, budgets, zoo, repro
- [ ] Closed beads have evidence-based `--reason` values

---

## 5. SOURCE REFERENCE INDEX

All claims in this audit are backed by verified source locations:

| Module | File | Key Lines | What's There |
|--------|------|-----------|--------------|
| Entity Index | `src/cad_dxf_agent/core/entity_index.py` | 18-33 | O(1) dict lookups by handle, layer, type, text |
| Validators | `src/cad_dxf_agent/core/validators.py` | 53-81 | Early-return on first blocker per op |
| OTEL | `src/cad_dxf_agent/otel.py` | 108-117, 172-177 | `_NoOpTracer` fallback, one span per stage |
| Settings | `src/cad_dxf_agent/settings.py` | 36 | `OTEL_ENABLED` defaults to `""` → False |
| Selectors | `src/cad_dxf_agent/core/selectors.py` | 64-122 | Multi-stage candidate resolution |
| Agent Provider | `src/cad_dxf_agent/llm/agent_provider.py` | 33 | `MAX_AGENT_TURNS = 10`, no timeout/retry |
| Context Builder | `src/cad_dxf_agent/core/context_builder.py` | 37-55 | `subset_context()` progressive disclosure |

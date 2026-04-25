# TEST_AUDIT.md — cad-ai-agent

**Date**: 2026-04-22
**Branch**: main
**Auditor**: `/audit-tests` (Intent Solutions SOP)
**Harness**: `@intentsolutions/audit-harness` — **not installed** (npm latest: 0.1.0; vendored install path applies — no pnpm in this repo)

---

## Grade

**B+ (84 / 100)**

Strong code-level test discipline (4,687 tests, 91% unit coverage, 10 tiers, mature CI) held back by missing Intent Solutions SOP traceability artifacts (`TESTING.md`, `RTM.md`, `PERSONAS.md`, `JOURNEYS.md`) and service-grade L5 gaps (load, DAST, a11y).

---

## Classification

- **Dominant type**: `service` — FastAPI backend on Cloud Run is the production surface
- **Overlays**: `frontend` (React + Vite SPA at `web/frontend/`), `cli` (`cad-revision`, `cad-dxf-agent` console scripts), `desktop` (PySide6 shell at `src/cad_dxf_agent/ui/`, excluded from coverage)
- **Monorepo**: no (no `pnpm-workspace.yaml` / `turbo.json` / `nx.json`); polyglot two-build-graph repo — Python package + `web/frontend` npm package

## Applicable layers (service + frontend + cli matrix)

L1, L2, L3, L4-integration, L4-contract, L5-perf, L5-sec-dyn, L5-a11y (frontend overlay), L6-smoke, L7-acceptance.
BDD/Gherkin (L6) is **⭕ optional** for this stack — Playwright already delivers the journey layer.

## Waived

L5-chaos (acceptable at current scale — P2 advisory only).

---

## Per-layer map

| Layer | Status | Notes |
|---|---|---|
| **L0 — harness** | ❌ absent | No `.audit-harness/`, no `.harness-hash`, not in `[dev]`. **P0**. |
| **L1 — git hooks & CI** | ⚠ partial | `.pre-commit-config.yaml` (ruff, whitespace, private-key, large-file, no-commit-to-main, forbid-`.env`); 8 GH Actions workflows. Missing: commitlint (epic/bead trailer enforcement), gitleaks, harness hash-verify. **P1**. |
| **L2 — static analysis** | ⚠ partial | ruff (E,F,W,I,N,UP,S,B,A,SIM), ruff-format, mypy strict-ish, bandit, pip-audit. Missing: CodeQL/Semgrep SAST, Trivy container scan for `web/backend/Dockerfile`, frontend ESLint config, import-linter (module boundaries). **P1**. |
| **L3 — unit & function** | ✅ installed | pytest 8+, ~3,600 unit tests, `fail_under=65` enforced, pytest-benchmark, syrupy snapshots, mutmut configured. Measured coverage: **91% unit-tier** (well above 65 floor). Residual gap: mutmut not wired into CI; Hypothesis not declared in `[dev]` despite `property` marker. **P1 residual**. |
| **L4 — integration & regression** | ✅ installed | 12 integration files + 39 web/API TestClient suites. Residual gap: no OpenAPI contract tests (schemathesis) — SPA↔API drift uncaught. **P1**. |
| **L5 — system quality** | ⚠ partial | pytest-benchmark covers 2 hot paths (validator, repeated-condition); bandit SAST; canary monitoring. Missing: k6/Locust load test against Cloud Run, ZAP/Nuclei DAST, axe-core a11y for frontend overlay. **P1** (service+frontend). |
| **L6 — E2E / BDD** | ⚠ partial | Playwright with 10 scripts (realworld, conversations, canary, profiles, headed/debug), Python `tests/e2e/` (33 tests with real DXF), GUI tests. Missing: smoke-tag separation in Playwright; no BDD `features/*.feature` (P2 — optional for this stack). **P1** for smoke-tag, **P2** for BDD. |
| **L7 — acceptance & business** | ❌ absent | No `TESTING.md`, `RTM.md`, `PERSONAS.md`, `JOURNEYS.md`, or `@acceptance` tags. `tests/eval/` scorecard (96.9% intent accuracy) partially fills the role but is not RTM-linked. **P1**. |

---

## Quality gate results

| Gate | Status | Value / Threshold | Notes |
|---|---|---|---|
| Coverage | ✅ PASS | 91% line / 65% floor | Unit-tier only, 11,535 stmts / 1,017 missed. `scorecard_schema.py` at 0% (64 stmts, candidate for deletion or test). |
| CRAP (prod) | ⚠ REVIEW | max 600 / floor 30 | 13 blockers. Top 3: `ui/main_window._on_open` (CRAP=240, cov=0 by policy exclusion), `dxf_reader._parse_entity` (CRAP=58.9, cov=85%), `comparison/geometry._extract_one` (CRAP=44). UI entries are excluded-by-design; core parsers warrant P1 refactor beads but are well-tested. |
| CRAP (test) | ⚠ ARTIFACT | max 342 / floor 15 | 2,183 "blockers" — radon counts test functions as uncovered. Known tool limitation against pytest suites. **P2 — tool-level false positive.** |
| Architecture | ❌ SKIP | 0 / 0 | `arch-check.sh` reports `tool=none, status=not-configured`. No `.dependency-cruiser.js`, `.importlinter`, `deptrac.yaml`. **L2 gap.** |
| Bias count | ⚠ WARN | 365 / 4,279 tests = 8.5 per 100 | Exceeds informational floor (5/100). Most hits are `is not None`-style soft assertions across 229 test files. **P1.** |
| Gherkin lint | — SKIP | 0 `.feature` files | Expected for pipeline-style codebase. |
| Mutation | ⚠ CONFIGURED NOT GATED | 3 paths pinned / not run in CI | `core/design_ops.py`, `core/construction_ops.py`, `core/comparison/geometry.py`. **P1 — gate not wired.** |

---

## Gap inventory

### P0 (1)

| Gap | Layer | Remediation |
|---|---|---|
| `@intentsolutions/audit-harness` not installed — blocks hash-pinning, escape-scan, CRAP/arch/bias/gherkin-lint gates | L0 | `curl -sSL https://raw.githubusercontent.com/jeremylongshore/audit-harness/main/install.sh \| bash` (Python/vendored path — no pnpm) |

### P1 (7)

| Gap | Layer | Remediation |
|---|---|---|
| Commitlint + gitleaks + harness hash-verify hook missing | L1 | Add to `.pre-commit-config.yaml` and CI workflow |
| CodeQL/Semgrep SAST + Trivy container scan + frontend ESLint + import-linter missing | L2 | Multi-tool install — service-grade minimum |
| Mutmut configured but not gated in CI; Hypothesis not in `[dev]` | L3 | Add CI job; declare Hypothesis as explicit dep |
| No OpenAPI contract tests (schemathesis) — SPA↔API drift uncaught | L4-contract | `pip install schemathesis`; add to CI |
| No load testing (k6/Locust), no DAST (ZAP), no frontend a11y (axe-core) | L5 | Public service + frontend requires all three |
| Playwright smoke-tag separation not visible in config | L6 | Add `--grep @smoke` filter to canary workflow |
| `TESTING.md`, `RTM.md`, `PERSONAS.md`, `JOURNEYS.md` absent | L7 | **Retrofit**, not greenfield seed — see "RTM retrofit" below |

### P2 (2)

| Gap | Layer | Remediation |
|---|---|---|
| No BDD `features/*.feature` | L6 | Optional — flag when AEC compliance epics need non-engineer-authored acceptance criteria |
| No visual regression (Percy / Chromatic) | L6 | Defer — frontend is dashboard, not brand-critical |

---

## RTM retrofit guidance

This is **not a greenfield scaffold**. The repo already has the raw material for a dense traceability matrix — the scaffolder should harvest from existing docs, not synthesize defaults.

- **~85–110 MUST requirements** derivable from: Epic Registry (31 epics × 2–3 acceptance criteria in `CLAUDE.md`), 4 ADRs (`004`, `005`, `006`, `039`), 10 AT-SPEC/AT-ARCH contract specs in `000-docs/`, 30 Pydantic schema contract boundaries in `src/cad_dxf_agent/models/`.
- **5 MUST requirements already well-covered** (sample):
  - "LLM never emits raw DXF" (ADR 005) → `tests/unit/test_apply_schema.py`, `test_changeset_snapshot.py`
  - "Protected layers cannot be edited" (CLAUDE.md) → `tests/unit/test_applier.py::test_protected_layer_reject`
  - "Original DXF never modified" (ADR 004) → `tests/unit/test_apply_pipeline.py`, `test_apply_anti_regression.py`
  - "Revision notes are deterministic" (ADR 006) → `tests/unit/test_revision_notes*.py`
  - "Two-axis intent classification" (EPIC-13) → `tests/unit/test_objective_classifier*.py`, `tests/eval/` scorecard
- **Estimated uncovered MUST count**: ~10–15 — edge cases in tenant isolation, EPIC-31 Phase 2 deferred path, OTel cardinality, Firestore allowlist failure modes.
- **Personas**: `000-docs/072-TQ-TEST-realworld-user-profiles.md` already contains 25 canonical profiles. Collapse to 5 archetypes: Design Author, Reviewer/Compliance Officer, Estimator/Coordinator, Field/Operator, Platform Admin.
- **Journeys**: 7 candidates — Edit happy path, Analysis (no mutation), Agent-mode tool loop, `cad-revision diff`, Web session lifecycle, Protected-layer rejection, Document persistence (EPIC-15/30).

**Recommendation**: when `implement-tests` runs, it should emit retrofit-aware skeletons with `<!-- RETROFIT — harvest from CLAUDE.md Epic Registry + ADRs + 072-TQ-TEST-realworld-user-profiles.md -->` banners, **not** generic seeded defaults. Generic seeds would regress fidelity relative to the existing 000-docs inventory.

---

## Escape-scan

- **Exit code**: 0 (clean)
- **Pending diff**: 3 modified files (`README.md`, `installer/setup.iss`, `pyproject.toml`) + 1 untracked (`000-docs/076-AA-AUDT-appaudit-devops-playbook.md`)
- **Diff nature**: URL-only — GitHub repo rename `cad-dxf-agent` → `cad-ai-agent`. No touches to `fail_under`, `.feature` files, architecture configs, test files, mutation pragmas, or `.harness-hash`.
- **Hash manifest**: absent (`no_manifest` — fresh repo per Step 1 grammar; NOT a halt condition).
- **Halt recommended**: no.

---

## Freshness

- `audit-harness` installed: **none**; npm latest: `0.1.0`
- Action: install via vendored path as first step of `implement-tests` handoff.

---

## Install order (topological)

1. **L0-harness** — `curl install.sh | bash` (vendored, Python project, no pnpm)
2. **L1**: commitlint + gitleaks + harness hash-verify hook
3. **L2**: CodeQL (or Semgrep) + Trivy (Dockerfile) + ESLint (frontend) + import-linter (Python boundaries)
4. **L3**: mutmut CI wire + CRAP gate + Hypothesis declared in `[dev]`
5. **L4**: schemathesis (OpenAPI contract) + optional Pact (SPA↔API)
6. **L5**: k6 smoke load + ZAP baseline + axe-core (frontend)
7. **L6**: Playwright smoke-tag split (optional `features/` for AEC compliance acceptance)
8. **L7**: `TESTING.md` → `RTM.md` → `PERSONAS.md` → `JOURNEYS.md` (retrofit from 000-docs, not generic seeds)

---

## Observational data for TESTING.md

When `tests/TESTING.md` is created by `implement-tests`, seed it with these observed values:

```yaml
Classification: service
Overlays: [frontend, cli, desktop]
Compliance overlay: (none declared — candidate: AEC/AIA documentation standards if productized)
Thresholds:
  coverage.line: 65          # project policy — below SOP default of 80; engineer-declared
  coverage.branch: (unset)
  mutation.kill_rate: (unset — mutmut configured, 3 paths, not gated)
  crap.prod_max: 30          # SOP default
  crap.test_max: 15          # SOP default (artifact: test CRAP spikes from radon limitation)
  crap.project_avg: 10       # SOP default
  bias.per_hundred: 5        # informational floor; current: 8.5 — P1
Waived layers:
  - L5-chaos (scale not yet demanding)
Frameworks:
  - pytest 8+ (markers: smoke slow integration live_api gui property benchmark web web_live e2e)
  - ruff 0.5+ (E,F,W,I,N,UP,S,B,A,SIM)
  - mypy 1.10+
  - bandit + pip-audit
  - mutmut (configured, not gated)
  - syrupy (snapshots)
  - pytest-benchmark (2 hot paths)
  - Playwright (frontend e2e, 10 scripts)
Installed gates:
  - pre-commit: ruff, ruff-format, whitespace, private-key, large-file, no-commit-to-main, forbid-.env
  - CI: ci.yml, security.yml, deploy-web.yml, canary-monitoring.yml, build-windows.yml, gemini-review.yml, publish-pypi.yml, release-dryrun.yml
Last audit: 2026-04-22 (B+ 84/100)
```

---

## Handoff status

- **Branch**: `main` (protected)
- **P0/P1 gaps**: yes (1 P0, 7 P1)
- **SOP requires**: `AskUserQuestion` before dispatching `implement-tests`

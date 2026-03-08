# Test Audit — cad-dxf-agent
> Branch: feature/epic-cad-13-document-family · Audited: 2026-03-07
> **Remediated:** pip-audit --local fix, pip CVE patched, E2E skip visibility added

---

## What Is Working Well

### Coverage & Structure
- **93.5% line coverage** across 8,550 lines of source — well above the 65% threshold enforced in CI
- **161 test files** covering 107 source files across 10 test tiers (unit, integration, web, benchmark, e2e, eval, smoke, property, GUI, live)
- Test directory structure mirrors source layout — unit tests map 1:1 to modules making gaps immediately visible
- **2,696 tests pass** with only 5 skipped (pipeline workers requiring optional dependencies)
- 3 syrupy snapshots guard against accidental ChangeSet structure regressions

### CI/CD Integration
- **7 GitHub Actions workflows**: CI (lint + typecheck + test matrix), security (bandit + pip-audit), deploy-web, build-windows, publish-pypi, release-dryrun, gemini-review
- CI runs on every push to main and every PR — no manual triggers needed
- **Test matrix**: Ubuntu × Python 3.11 + 3.12 with coverage reporting
- Benchmarks run automatically on push to main (pytest-benchmark with JSON artifact upload)
- Coverage artifact uploaded per CI run for tracking

### Test Quality Signals
- **ScriptedAgentProvider** (fake backend pattern) — tests LLM loop behavior without API calls
- **Golden trajectories** (5 JSON fixtures) validate correct agent behavior per prompt type
- **Property tests** (Hypothesis-based) for fuzz testing validators and schema boundaries
- **DXF factory** (programmatic builders) — no stored DXF files, deterministic test data
- **ChangeSet factory** — one-liner builders for move, delete, edit_text, add_block operations
- Live API tests (11 files) verify real Gemini integration via WIF in CI

### Security & Dependencies
- **Pre-commit hooks** enforce: ruff lint + format, trailing whitespace, no .env commits, no direct commits to main, detect-private-key, check-merge-conflict
- **Security workflow** runs bandit (SAST) + pip-audit (`--local`) on every push/PR
- Zero dependency vulnerabilities after pip upgrade (pip-audit clean with `--local` flag)
- `.env` files blocked from commits by pre-commit hook

### Documentation & Conventions
- CLAUDE.md documents all test tiers, commands, and patterns comprehensively
- Makefile provides `test`, `test-cov`, `test-unit`, `test-integration`, `test-web`, `test-live` targets
- Test helpers are centralized in `tests/helpers/` (dxf_factory, changeset_factory, scripted_provider)
- Fixtures centralized in `tests/conftest.py` and `tests/fixtures/`

---

## What Could Be Better

---

### P1 — Core Functionality at Risk

#### No frontend tests whatsoever
**What exists:** `web/frontend/` is a React + Vite SPA with components for file upload, drawing viewer, prompt input, chat history, comparison workflow, and settings. Zero test files exist.

**What is missing:** No unit tests, no component tests, no integration tests for the entire frontend codebase. No vitest/jest configuration. No test script in package.json.

**Why it matters:** The frontend handles user-facing drawing interaction, file uploads, and prompt workflows. A regression in the viewer, upload flow, or prompt dispatch is invisible until a user reports it. The backend has 93% coverage while the frontend has 0%.

**What to add:**
- Install vitest + @testing-library/react
- Component tests for critical paths: upload flow, prompt submission, drawing viewer, comparison panel
- API mock layer (MSW or vitest mocks) to test frontend in isolation

---

#### 26 source files lack dedicated test files
**What exists:** The gap mapping found 26 `.py` files without corresponding `test_*.py` files. Key untested modules include:

| File | Risk |
|------|------|
| `core/design_ops.py` | Layout recommender + scope builder — design assist responses |
| `core/construction_ops.py` | Markup redline + batch condition — construction workflow |
| `llm/planner.py` | Orchestrates LLM planning — central to edit workflow |
| `llm/mock_provider.py` | Mock LLM provider used by all CI tests |
| `llm/prompt_templates.py` | Prompt construction — drift could silently break LLM responses |
| `llm/response_parser.py` | Parses LLM output into ChangeSet — failure means broken edits |
| `llm/vision_describer.py` | 33% coverage — image description for vision pipeline |
| `cli/main.py`, `cli/commands.py` | Revision CLI entry points |
| `core/comparison/*.py` (6 files) | Comparison pipeline internals (tested at integration level but no unit tests) |

**What is missing:** Dedicated unit test files for these modules. Some are exercised via integration tests but have no isolated unit coverage.

**Why it matters:** Without unit tests, refactoring or extending these modules risks silent regression. The comparison pipeline has 6 untested modules that are only covered by integration-level testing — subtle bugs in matching, scoring, or classification could go undetected.

**What to add:** Prioritize test files for:
1. `test_planner.py` — mock provider injection, error handling, timeout behavior
2. `test_response_parser.py` — malformed LLM output, edge cases, partial responses
3. `test_design_ops.py` — layout recommender logic, scope builder
4. `test_construction_ops.py` — markup redline, batch condition planning
5. `test_prompt_templates.py` — template rendering, variable injection

---

### P2 — Quality and Reliability Gaps

#### No API contract validation
**What exists:** FastAPI backend with ~15 endpoints. Web tests use TestClient to verify behavior, but no formal schema contract tests exist.

**What is missing:** OpenAPI spec validation — no automated check that the running server matches a declared API contract. Consumers (frontend, future integrations) build against ad-hoc knowledge.

**Why it matters:** API response shape changes can break the frontend silently. A contract test would catch field removals, type changes, or missing fields before they reach production.

**What to add:** Export OpenAPI spec from FastAPI (`app.openapi()`) and add a contract validation test:
```python
# tests/web/test_api_contract.py
def test_openapi_spec_is_valid(client):
    resp = client.get("/openapi.json")
    assert resp.status_code == 200
    spec = resp.json()
    assert "paths" in spec
    # Validate key endpoint schemas match expected shapes
```

---

#### No gitleaks / secret scanning in CI
**What exists:** Pre-commit hooks include `detect-private-key` (basic) and `.env` file blocking. The security workflow runs bandit + pip-audit.

**What is missing:** `gitleaks` or equivalent deep secret scanning (regex-based, checks git history). The pre-commit `detect-private-key` only catches SSH keys, not API keys, tokens, or passwords.

**Why it matters:** API keys or tokens accidentally committed in earlier history would not be caught by current tooling. The `.env` blocking prevents new commits but does not audit past history.

**What to add:** Add gitleaks as a pre-commit hook and CI step:
```yaml
# .pre-commit-config.yaml
- repo: https://github.com/gitleaks/gitleaks
  rev: v8.18.0
  hooks:
    - id: gitleaks
```

---

#### Coverage badge not in README
**What exists:** Coverage is 93.5% and enforced at 65% in CI. Coverage report is uploaded as artifact.

**What is missing:** No coverage badge in README. No Codecov/Coveralls integration for trend tracking.

**Why it matters:** Coverage trends over time are invisible. The badge signals project health to contributors and stakeholders.

**What to add:** Add Codecov GitHub Action step + badge to README.

---

### P3 — Hardening and Observability

#### No accessibility tests
**What is missing:** No WCAG compliance checks for the web frontend. No axe-core, pa11y, or accessibility assertions.

**Why it matters:** The web app is a drawing viewer tool — accessibility failures could exclude users with screen readers or motor impairments. Catching these early is cheap.

**What to add:** Add axe-core to future frontend component tests once vitest is set up.

---

#### No mutation testing
**What is missing:** No mutmut or similar mutation testing to validate test quality.

**Why it matters:** 93.5% coverage is impressive, but mutation testing reveals whether tests actually assert correctness or just execute code paths without meaningful checks. Particularly valuable for validators and the edit engine where silent wrong behavior is worse than failure.

**What to add:** `mutmut run --paths-to-mutate=src/cad_dxf_agent/core/validators.py` as a periodic quality gate.

---

#### No visual regression testing for web frontend
**What is missing:** No screenshot comparison for the drawing viewer, comparison overlay, or chat interface.

**Why it matters:** CSS or layout changes in the drawing viewer could break the visual representation without any test catching it.

**What to add:** Playwright snapshot tests once frontend testing infrastructure is established.

---

## Summary Scorecard

| Area | Status | Priority |
|------|--------|----------|
| Unit test coverage | 93.5% — Excellent | — |
| Integration tests | Present (78+ tests) | — |
| E2E tests | Present (1 file, limited) | P2 |
| Web backend tests | Present (123+ tests) | — |
| Frontend tests | Missing entirely | P1 |
| API contract tests | Missing | P2 |
| CI pipeline | Fully configured (7 workflows) | — |
| Coverage gates | Enforced at 65% | — |
| Security scanning | Present (bandit + pip-audit) | — |
| Secret detection | Basic (detect-private-key only) | P2 |
| Dependency audit | Clean (pip-audit) | — |
| Performance baseline | Present (pytest-benchmark) | — |
| Accessibility tests | Missing | P3 |
| Mutation testing | Missing | P3 |
| Visual regression | Missing | P3 |
| Property/fuzz tests | Present (7 tests) | — |
| Live API tests | Present (11 files via WIF) | — |
| Golden trajectories | Present (5 fixtures) | — |

---

*Generated by audit-tests skill · https://github.com/jeremylongshore/cad-dxf-agent*

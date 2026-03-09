# 071-TQ-TEST — Production Quality Proof System

**Created:** 2026-03-09
**Category:** TQ (Testing & Quality)
**Type:** TEST (Test Documentation)

## Purpose

Prove the system works end-to-end — not with mocks, but with real Gemini API
handling real prompts against real drawings through the actual web UI. Every prompt
captures the AI's response, pipeline traces, operations, and screenshots showing
what the user would see.

**Core principle: No mocks. Real Gemini. Real proof.**

## Architecture

```
Playwright (headless Chromium)
  → Frontend (Vite dev, VITE_DEV_AUTH=1)
    → Backend (FastAPI, CAD_LLM_PROVIDER=gemini, CAD_WEB_DEV_MODE=1)
      → Real Gemini API (gemini-2.5-flash via Vertex AI)
      → InMemorySpanExporter (OTel trace capture)
    ← PlatformResponse JSON intercepted via page.route()
  → Screenshots saved per prompt
  → Response records saved as JSON
  → Quality scored per category rubric
```

## Components

### A. Playwright E2E Tests

| File | Tests | Purpose |
|------|-------|---------|
| `web/frontend/e2e/realworld-prompts.spec.js` | 118 | Every prompt from `realworld_prompts.json` through real Gemini |
| `web/frontend/e2e/realworld-conversations.spec.js` | 15 | Multi-turn conversations (follow-ups, corrections, undo) |
| `web/frontend/e2e/realworld-canary.spec.js` | 20 | Critical subset for daily production monitoring |

### B. Backend Debug Routes

**File:** `web/backend/debug_routes.py`

OTel trace capture endpoints, gated behind `CAD_WEB_DEV_MODE=1`:

- `GET /api/debug/traces` — All InMemorySpanExporter spans as JSON
- `DELETE /api/debug/traces` — Clear accumulated spans

Integrated in `web/backend/main.py` lifespan: when both `CAD_WEB_DEV_MODE=1` and
`OTEL_ENABLED=1`, uses `init_otel_testing(InMemorySpanExporter())` instead of the
normal exporter, and mounts the debug router.

### C. Quality Scoring

**File:** `web/frontend/e2e/helpers/quality-scorer.js`

Automated 0.0–1.0 scoring per prompt category:

| Category | Rubric |
|----------|--------|
| edit (move, delete, text, etc.) | 0.5 if ops produced + 0.25 type match + 0.25 count match |
| qna/query | 0.5 if message + 0.25 mentions drawing facts + 0.25 substantive |
| summary/health/compliance | 0.5 if message + 0.25 layer names + 0.25 entity types |
| needs_clarification | 1.0 if no ops + message; 0.0 if ops produced |
| adversarial | 1.0 if no crash; 0.0 if crash |
| protected | 1.0 if validator blockers; 0.5 if warned; 0.0 if nothing |

### D. Scorecard & Regression Gate

**File:** `web/frontend/e2e/realworld-report.js`

Post-run script that:
1. Reads all `test-results/realworld-responses/*.json`
2. Computes accuracy, quality average, timing (avg/p50/p95), per-category breakdown
3. Saves timestamped scorecard to `test-results/scorecard-history/`
4. Compares against previous run for regressions
5. **Exit code 1** if accuracy drops >5% or falls below 80%

**Thresholds:** `web/frontend/realworld-thresholds.json`
```json
{ "min_accuracy": 0.80, "max_p95_ms": 30000, "max_regression_pct": 5 }
```

### E. Production Canary Monitoring

**File:** `.github/workflows/canary-monitoring.yml`

Daily at 8am UTC:
1. Run 20 canary prompts against production
2. Upload results as GitHub artifacts (30-day retention)
3. Fail the workflow if any canary crashes/times out

### F. Dev-Auth Bypass

For headless Chrome E2E testing (Google sign-in popup can't work):

- `web/frontend/src/hooks/useAuth.js`: When `VITE_DEV_AUTH=1`, returns synthetic
  dev-user (uid: `dev-user`, email: `dev@localhost`) without Firebase
- `web/frontend/src/lib/api.js`: When `VITE_DEV_AUTH=1`, sends `dev-token` instead
  of Firebase ID token
- Backend's `CAD_WEB_DEV_MODE=1` accepts any token and returns synthetic dev-user

## Test Data

### Drawing Fixtures

All 118 prompts use real committed DXF files (no factory-generated drawings):

| Fixture name | File | Entities |
|-------------|------|----------|
| structural | `tests/fixtures/dxf_zoo/r2000_blocks.dxf` | 50 (blocks, text, inserts) |
| overlapping | `tests/fixtures/dxf_zoo/r2018_polylines.dxf` | polylines, modern format |
| empty_layers | `tests/fixtures/dxf_zoo/r12_basic.dxf` | minimal R12 |

### Conversation Scripts

`tests/fixtures/realworld_conversations.json` — 15 conversations, 40 total turns:

- Edit follow-ups (3): move → repeat → adjust
- Analysis drill-down (3): layers → count → detail
- Mixed intent (3): ask → edit → verify
- Error recovery (3): wrong ref → clarify → succeed
- Undo/correction (3): edit → reverse → fix

### Canary Prompts

`tests/fixtures/realworld_canary.json` — 20 prompts, one per capability:
move, delete, text, add_block, rotate, copy, scale, batch, qna (2), summary,
health, compliance, takeoff, protected, ambiguous, adversarial, add_line, mirror,
conversational.

## Per-Test Output

Each prompt generates `test-results/realworld-responses/{prompt_id}.json`:

```json
{
  "prompt_id": "rw-move-001",
  "prompt": "Move the column at grid A-1 two feet to the east",
  "response": {
    "task_family": "edit_plan",
    "message": "Moved the BOLT block...",
    "operations": [{ "op_type": "move_entity", ... }],
    "audit": { "llm_time_ms": 10391, "router_confidence": 0.95 }
  },
  "screenshots": { "loaded": "...-loaded.png", "response": "...-response.png" },
  "traces": [{ "name": "cad.web.v2_prompt", "duration_ns": ... }],
  "quality": { "score": 0.95, "breakdown": { ... } },
  "assertions": { "no_crash": true, "behavior_match": true },
  "duration_ms": 14400
}
```

## Assertion Tiers

| Tier | What | Hard fail? |
|------|------|-----------|
| 1 | No crash, no 500, response within 120s | Yes |
| 2 | `produces_ops` → ops >= 1 | Yes |
| 2 | `must_not_produce_ops` → ops == 0 | Yes |
| 2 | `answer_only`/`report` → non-empty message | Yes |
| 3 | `task_family` matches expected | Recorded, scored |
| 3 | `op_types` match expected | Recorded, scored |
| 3 | Quality rubric score | Recorded, scored |

## Running

```bash
# Full suite (118 prompts, ~30 min)
cd web/frontend && npm run e2e:realworld

# Scorecard + regression check
npm run e2e:realworld:report

# Multi-turn conversations (~10 min)
npm run e2e:conversations

# Production canary
TARGET=production npm run e2e:canary

# Single prompt
REALWORLD=1 npx playwright test --grep "rw-move-001"
```

### Environment

The Playwright config (`playwright.config.js`) handles everything when `REALWORLD=1`:

- Backend: `CAD_WEB_DEV_MODE=1 OTEL_ENABLED=1 CAD_LLM_PROVIDER=gemini CAD_GCP_PROJECT=cad-dxf-agent`
- Frontend: `VITE_DEV_AUTH=1 npm run dev`
- Timeouts: 120s per test (Gemini cold start + LLM reasoning)

## Files Summary

### Created
| File | Purpose |
|------|---------|
| `web/backend/debug_routes.py` | OTel trace debug endpoints |
| `web/frontend/e2e/realworld-prompts.spec.js` | 118 real Gemini E2E tests |
| `web/frontend/e2e/realworld-conversations.spec.js` | 15 multi-turn tests |
| `web/frontend/e2e/realworld-canary.spec.js` | 20 production canary tests |
| `web/frontend/e2e/realworld-report.js` | Scorecard + regression gate |
| `web/frontend/e2e/helpers/quality-scorer.js` | Quality rubrics |
| `tests/fixtures/realworld_conversations.json` | Conversation scripts |
| `tests/fixtures/realworld_canary.json` | Canary prompt subset |
| `web/frontend/realworld-thresholds.json` | CI regression thresholds |
| `.github/workflows/canary-monitoring.yml` | Daily production monitoring |

### Modified
| File | Change |
|------|--------|
| `web/backend/main.py` | Lifespan: InMemorySpanExporter + debug routes in dev mode |
| `web/frontend/playwright.config.js` | REALWORLD=1 flag, VITE_DEV_AUTH, 120s timeouts |
| `web/frontend/package.json` | 4 new npm scripts |
| `web/frontend/e2e/global-setup.js` | Fixture download before browser launch |
| `web/frontend/src/hooks/useAuth.js` | VITE_DEV_AUTH bypass for headless E2E |
| `web/frontend/src/lib/api.js` | Dev-token for VITE_DEV_AUTH mode |

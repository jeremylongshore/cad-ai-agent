# Release Report: cad-dxf-agent v0.3.0

## Executive Summary

- **Version**: 0.3.0
- **Release Date**: 2026-02-25
- **Release Type**: Minor
- **Approved By**: jeremy (SHA: 642d27b)
- **Previous Version**: 0.2.0 (2026-02-24)

This release closes the two weakest observability gaps identified in the production AI agent audit (Observability 7/10, State 6/10). OpenTelemetry was already instrumented across the pipeline (7 spans) but never initialized in the web backend — all spans were no-ops in production. v0.3.0 wires `init_otel()` into the FastAPI lifespan and adds a Google Cloud Trace exporter for native GCP observability.

## Changes Included

### Features
- **Wire OTel in web backend** (#32): Call `init_otel(service_name="cad-dxf-web")` in FastAPI lifespan startup. All 7 existing pipeline spans (`cad.load_dxf`, `cad.build_context`, `cad.run_planner`, `cad.validate`, etc.) now fire for web requests when `OTEL_ENABLED=true`.
- **Google Cloud Trace exporter** (#33): New `OTEL_EXPORTER=gcp-trace` option uses `opentelemetry-exporter-gcp-trace` with ADC — zero config on Cloud Run. Graceful fallback to console exporter if package not installed.

### Infrastructure
- Added `gcp-trace` optional dependency group in `pyproject.toml`
- Added `opentelemetry-api`, `opentelemetry-sdk`, `opentelemetry-exporter-gcp-trace` to `web/backend/requirements.txt`
- Added `.firebase/` to `.gitignore`

### Testing
- `tests/web/test_web_otel.py`: 2 new tests — spans propagate through upload-plan flow, endpoints work with OTel disabled
- `tests/unit/test_otel.py`: 2 new tests — GCP exporter selection with mock, graceful fallback when package missing
- Ruff format compliance across 9 files

### Documentation
- Updated `CLAUDE.md` config table: `OTEL_EXPORTER` now documents `gcp-trace` value
- Updated `settings.py` inline comment documenting valid exporter values

### Breaking Changes
- None

## Pull Requests

| PR | Title | Branch | Status |
|----|-------|--------|--------|
| #32 | feat(otel): wire OpenTelemetry init in web backend | `feat/otel-web-backend` | Merged (squash) |
| #33 | feat(otel): add Google Cloud Trace exporter | `feat/otel-gcp-trace` | Merged (squash, rebased for conflict) |

## Commits

| SHA | Message |
|-----|---------|
| `979bfd2` | feat(otel): wire OpenTelemetry init in web backend lifespan (#32) |
| `b29ae34` | feat(otel): add Google Cloud Trace exporter option (#33) |
| `c03cf66` | style(otel): fix ruff format on gcp-trace warning line |
| `d721c01` | style: run ruff format across codebase |
| `2def454` | chore(beads): close cad-o7b observability gaps |
| `642d27b` | chore: add .firebase/ to gitignore |
| `42b953b` | chore(release): prepare v0.3.0 |

## Metrics

| Metric | Value |
|--------|-------|
| Commits | 8 (including release commit) |
| Files Changed | 22 |
| Lines Added | +314 |
| Lines Removed | -57 |
| Contributors | 2 |
| Days Since Last Release | <1 |
| Test Count | 578 (was 573) |
| Coverage | 68% |

## Quality Gates

| Gate | Status |
|------|--------|
| Lint (ruff check) | PASS (0 new errors) |
| Format (ruff format) | PASS |
| Typecheck (mypy) | PASS (44 source files) |
| Unit + Web + Integration Tests | PASS (539 passed, 12 skipped) |
| Live API Tests | PASS (38/39 — 1 pre-existing timeout) |
| Smoke Test | PASS |
| Secrets Scan | PASS |
| Beads Sync | PASS (cad-o7b closed) |

## Observability Impact

### Before v0.3.0
- Pipeline spans instrumented but never initialized in web backend
- Only `console` and generic `otlp` exporters available
- Production web requests produced zero traces

### After v0.3.0
- All 7 pipeline spans fire for every web request when `OTEL_ENABLED=true`
- Native Google Cloud Trace support via `OTEL_EXPORTER=gcp-trace`
- Zero-config on Cloud Run (uses ADC)

### Activation on Cloud Run
```bash
# Set environment variables on Cloud Run service:
OTEL_ENABLED=true
OTEL_EXPORTER=gcp-trace
```

No code changes or image rebuilds needed — controlled entirely via env vars.

## Rollback Procedure

```bash
# Remove release
git push origin --delete v0.3.0
git tag -d v0.3.0
gh release delete v0.3.0 --yes

# Revert changes
git revert HEAD
git push origin main
```

## Post-Release Checklist

- [x] Tag exists locally and on remote
- [x] GitHub release created
- [x] Version consistency verified (__init__.py = 0.3.0, tag = v0.3.0)
- [x] CHANGELOG updated with [0.3.0] section
- [x] Beads task closed (cad-o7b)
- [ ] Activate on Cloud Run (`OTEL_ENABLED=true`, `OTEL_EXPORTER=gcp-trace`)
- [ ] Verify traces appear in Cloud Trace console
- [ ] Monitor error rates for 24h

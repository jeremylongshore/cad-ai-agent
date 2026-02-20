# 011-AA-AACR — OpenTelemetry Instrumentation AAR

**Date:** 2026-02-20
**Category:** AA (After Action & Review)
**Type:** AACR (After Action Review)

## Summary

Added OpenTelemetry distributed tracing instrumentation to the cad-dxf-agent pipeline. All 7 pipeline stages now emit spans with structured attributes. The instrumentation is off by default, CI-safe, and works without OTel packages installed (graceful degradation via no-op fallbacks).

## What Was Done

1. **Dependencies** — Added `otel` optional dependency group (`opentelemetry-api`, `opentelemetry-sdk`, `opentelemetry-exporter-otlp`, `opentelemetry-semantic-conventions`) and OTel SDK/API to dev group for testing.

2. **Bootstrap module** (`src/cad_dxf_agent/otel.py`) — Created with:
   - `init_otel()` — configures TracerProvider with console or OTLP exporter
   - `get_tracer()` — returns a `_LazyTracer` that delegates to the current provider
   - `span()` — ergonomic context manager wrapper
   - `init_otel_testing()` / `reset_otel()` — test infrastructure
   - All imports guarded with `try/except` for graceful degradation

3. **Settings** — Added `OTEL_ENABLED`, `OTEL_EXPORTER`, `OTEL_EXPORTER_OTLP_ENDPOINT` to `Settings`.

4. **Pipeline instrumentation** — Added spans to:
   - `dxf_reader.load_dxf()` → `cad.load_dxf`
   - `semantic_model.build_planner_context()` → `cad.build_context`
   - `planner.run_planner()` → `cad.run_planner`
   - `validators.validate_changeset()` → `cad.validate`
   - `edit_engine.apply_changeset()` → `cad.apply_changeset`
   - `edit_engine.save()` → `cad.save`
   - `revision_notes.insert_revision_note()` → `cad.revision_note`

5. **Tests** — 5 CI-safe tests using `InMemorySpanExporter` (no network).

6. **Documentation** — Updated README, CLAUDE.md, `.env.example`.

## Key Decisions

### _LazyTracer pattern
OTel's `trace.set_tracer_provider()` can only be called once globally. Module-level `tracer = get_tracer(__name__)` captures a reference at import time. We solved this by returning a `_LazyTracer` that looks up the current `_provider` at call time, enabling test isolation without fighting OTel's global state.

### Privacy-safe attributes
No full file paths, no drawing text content, no API keys in span attributes. Only basenames, counts, and boolean flags.

### Off by default
`OTEL_ENABLED` must be explicitly set. When unset, all tracing is no-op with zero overhead.

## What Went Well

- Clean separation: `otel.py` owns all tracing concerns, pipeline modules just import `get_tracer`
- Zero impact on existing tests (all 41 pre-existing tests continue to pass)
- Graceful degradation: app works fine without OTel packages installed

## Lessons Learned

- OTel's `set_tracer_provider()` is designed for single initialization; tests that need to swap providers must use an internal provider reference pattern
- `InMemorySpanExporter` import path varies by OTel SDK version (`in_memory_span_exporter` vs `in_memory`)
- Module-level tracer references need lazy delegation for testability

## Metrics

- **Files created:** 3 (otel.py, test_otel.py, this AAR)
- **Files modified:** 12
- **New tests:** 5
- **Existing tests affected:** 0
- **Spans instrumented:** 7

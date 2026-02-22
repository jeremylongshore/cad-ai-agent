# AAR: v0.2.0 Testing Infrastructure

**Doc ID:** 022-AA-AACR
**Date:** 2026-02-21
**Branch:** `test/v2-testing-infrastructure`

## What Was Built

Comprehensive testing infrastructure to close critical gaps identified in the v0.1.0 release (222 tests, zero integration tests, zero coverage on dxf_writer/edit_engine/preview_model).

### Test Count Delta

| Metric | Before | After | Delta |
|--------|--------|-------|-------|
| Total tests | 222 | 297 | +75 |
| Unit tests | ~218 | ~282 | +64 |
| Integration tests | 0 | 15 | +15 |
| Coverage | ~50% | ~68% | +18pp |
| fail_under threshold | 50% | 65% | +15pp |

### New Test Files

| File | Tests | Covers |
|------|-------|--------|
| `test_dxf_writer.py` | 7 | save-as, copy, path guards, round-trip |
| `test_edit_engine.py` | 10 | move/edit_text/delete/add_block with DXF reload |
| `test_preview_model.py` | 10 | descriptions, validity, summary |
| `test_semantic_model.py` | 9 | planner context, compact context |
| `test_settings.py` | 6 | env var parsing, api keys |
| `test_changeset_snapshot.py` | 3 | syrupy snapshot regression |
| `test_validators.py` (extended) | +9 | delete, add_block, distance, Inf, empty |
| `test_dxf_reader.py` (extended) | +5 | HATCH, SPLINE, ELLIPSE, unsupported, empty |
| `test_pipeline_integration.py` | 5 | full pipeline flows |
| `test_undo_redo_integration.py` | 2 | EditHistory + EditEngine |
| `test_agent_loop_integration.py` | 8 | ScriptedAgentProvider + golden trajectories |

### New Infrastructure

- **ScriptedAgentProvider** — fake-backend pattern for LLM testing without API calls
- **DXF factory** — programmatic structural drawing builder (grids, columns, dimensions)
- **ChangeSet factory** — one-liner test data builders
- **5 golden trajectory fixtures** — JSON-documented correct agent behavior
- **syrupy snapshots** — ChangeSet structure regression tests

### Key Decisions

1. **ScriptedAgentProvider over VCR cassettes** — cassettes require a real API, scripted replays test behavior deterministically. VCR deferred to when real Gemini integration testing begins.
2. **Programmatic DXF factories over stored files** — reproducible, parameterizable, no binary blobs in git.
3. **Coverage threshold 65% not 80%** — UI module (main_window.py) has 0% and rightfully so (PySide6 requires display server). 65% is achievable without testing the GUI.
4. **Golden trajectories as JSON** — machine-readable, versionable, parametrized via pytest.

## Verification

- `make check` passes (lint + format + typecheck + test + smoke)
- `make test-cov` shows 67.74% coverage (above 65% threshold)
- `pytest tests/integration/ -v` — 15/15 pass
- All 297 tests pass in ~27s

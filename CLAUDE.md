# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What This Project Is

Local-first DXF layout editor that uses LLM-assisted planning to edit 2D CAD drawings via natural-language prompts. The LLM returns structured JSON operations (never raw DXF) which are validated and applied deterministically. Original files are never modified (save-as workflow).

## Commands

```bash
# Install (editable + dev deps + pre-commit hooks)
pip install -e ".[dev]" && pre-commit install

# Run all quality checks (lint → format → typecheck → tests → smoke)
make check

# Individual checks
make lint          # ruff check src/ tests/
make format        # ruff format src/ tests/
make typecheck     # mypy src/
make test          # pytest -v
make test-cov      # pytest --cov=cad_dxf_agent --cov-report=term-missing -v
make smoke         # python scripts/smoke_test.py (full pipeline, no API key)
make security      # bandit -r src/ -ll && pip-audit

# Run single test
pytest tests/unit/test_validators.py -v
pytest tests/unit/test_validators.py::test_name -v

# Launch desktop app (requires PySide6: pip install -e ".[gui]")
make run           # python -m cad_dxf_agent.app

# Web app (local dev)
cd web/frontend && npm run dev                         # Frontend on :3000
CAD_WEB_DEV_MODE=1 uvicorn web.backend.main:app --port 8322  # Backend on :8322

# Web app (deploy)
cd web/frontend && npm run build && firebase deploy --only hosting  # Frontend
gcloud builds submit --config web/backend/cloudbuild.yaml .        # Backend
```

Mock mode (`CAD_LLM_PROVIDER=mock`, the default) works without any API key. All tests and the smoke test use mock mode.

### Live API Tests

Live tests in `tests/live/` hit real Gemini via Vertex AI on the `cad-dxf-agent` GCP project.

```bash
# Local: set ADC + run with project env var
gcloud auth application-default login
CAD_GCP_PROJECT=cad-dxf-agent pytest tests/live/ -v -m live_api -s

# CI: runs automatically on push to main via WIF (tokenless, no secrets)
```

## Architecture

### Pipeline Flow

```
User Prompt → Planner → ChangeSet → Validator → Preview → EditEngine → Save-As DXF
                                                                    ↘ RevisionNotes
```

1. **dxf_reader** loads DXF via `ezdxf` into a `DrawingContext` (Pydantic model with `EntityRef` list)
2. **semantic_model** builds a JSON-serializable context summary for the planner (no raw DXF exposed)
3. **planner** routes to a `PlannerProvider` (currently only `MockProvider`) which returns a `ChangeSet`
4. **validators** check every operation against `RuleConfig` — protected layers block edits, move distances warn
5. **preview_model** generates human-readable descriptions of proposed changes
6. **edit_engine** applies validated ops to a working copy of the DXF via `ezdxf`
7. **revision_notes** inserts deterministic (never LLM-generated) notes on the `AI_REV_NOTES` layer
8. **dxf_writer** saves to a new file path (original untouched)

### Key Architectural Rules

- **LLM never touches DXF directly** (see `000-docs/005-AT-ADEC-llm-plans-not-dxf.md`). It returns structured `EditOperation` objects with `OpType` enum: `move_entity`, `edit_text`, `delete_entity`, `add_block`. Invalid/unsupported ops reject the entire changeset.
- **Protected layers** (TITLE, TITLEBLOCK, SEAL, REVISION) cannot be edited. The validator blocks any operation targeting entities on these layers.
- **Revision notes are deterministic** — generated from operation metadata, never from freeform LLM output.
- **V1 entity types**: LINE, LWPOLYLINE, TEXT, MTEXT, INSERT only. All other types are skipped during load.

### Source Layout

```
src/cad_dxf_agent/
  models/         # Pydantic schemas: cad_schema, ops_schema, config_schema, changes_schema
  core/           # DXF I/O, validation, editing, preview, revision notes, entity index
  llm/            # Planner orchestrator, provider ABC, mock provider, prompt templates
  ui/             # PySide6 desktop shell (MainWindow)
  api/            # Local HTTP API (scaffolded, not wired)
  settings.py     # Env-based config (all CAD_* prefixed)
  app.py          # Entry point
```

### Data Models (Pydantic)

- `DrawingContext` — normalized view of a loaded DXF (entities, layers, blocks, metadata)
- `EntityRef` — single entity with handle, type, layer, position, text content, block name, attributes
- `EditOperation` — one op with `OpType`, target handle, layer, params dict
- `ChangeSet` — batch of operations from a single prompt
- `ValidationResult` — blockers (prevent apply) and warnings (informational)
- `RuleConfig` — protected layers, max move distance, coordinate tolerance

### Provider Pattern

`PlannerProvider` ABC in `llm/providers.py` → implement `plan(prompt, drawing_context) → ChangeSet`. Only `MockProvider` is wired. Real providers (OpenAI, Anthropic, Google) are scaffolded in `planner.py` but not implemented.

## Configuration

All settings via environment variables (`.env` file, `.gitignore`d):

| Variable | Default | Purpose |
|----------|---------|---------|
| `CAD_LLM_PROVIDER` | `mock` | Planner backend |
| `CAD_PROTECTED_LAYERS` | `TITLE,TITLEBLOCK,SEAL,REVISION` | Comma-separated protected layers |
| `CAD_REVISION_NOTES_ENABLED` | `true` | Insert revision notes after edits |
| `CAD_REVISION_NOTES_LAYER` | `AI_REV_NOTES` | Layer name for revision notes |
| `OTEL_ENABLED` | _(unset)_ | Enable OpenTelemetry tracing (`1`, `true`, `yes`) |
| `OTEL_EXPORTER` | `console` | Span exporter: `console` or `otlp` |
| `OTEL_EXPORTER_OTLP_ENDPOINT` | _(unset)_ | OTLP collector endpoint (e.g., `http://localhost:4317`) |

### Observability (OpenTelemetry)

Optional tracing via `otel.py` bootstrap module. Off by default, CI-safe (no network). Each pipeline stage emits a span (e.g., `cad.load_dxf`, `cad.run_planner`, `cad.validate`). No full file paths or drawing text in span attributes. Install extras: `pip install -e ".[otel]"`.

## Testing

### Test Tiers

| Tier | Location | Count | What |
|------|----------|-------|------|
| Unit | `tests/unit/` | ~270 | Schemas, validators, reader, writer, engine, preview, settings, semantic model, snapshots |
| Integration | `tests/integration/` | ~15 | Full pipeline, undo/redo, agent loop with ScriptedAgentProvider |
| Smoke | `tests/smoke/` + `scripts/smoke_test.py` | ~5 | End-to-end pipeline via mock planner |

### LLM Testing Patterns

- **ScriptedAgentProvider** (`tests/helpers/scripted_provider.py`): replay canned tool-call sequences through the real `ToolExecutor`. Industry "fake backend" pattern — tests behavior, not implementation.
- **Golden trajectories** (`tests/fixtures/trajectories/*.json`): JSON files documenting correct agent behavior per prompt type (Google ADK pattern). 5 trajectories: move, delete, edit_text, add_block, protected_layer_reject.
- **Snapshot tests** (`tests/unit/test_changeset_snapshot.py`): syrupy snapshots catch accidental ChangeSet structure changes when prompts evolve. Run `--snapshot-update` to accept intentional changes.

### Test Helpers

- `tests/helpers/dxf_factory.py` — programmatic DXF builders (structural drawings with 200+ entities, minimal, empty). No stored DXF files.
- `tests/helpers/changeset_factory.py` — one-liner `make_move()`, `make_delete()`, `make_edit_text()`, `make_add_block()` builders.
- `tests/conftest.py` — `sample_dxf`, `sample_context`, `rule_config` fixtures.

### Running Tests

```bash
make test            # All tests
make test-unit       # Unit tests only
make test-integration # Integration tests only
make test-cov        # All tests with coverage report
```

- Pytest markers: `@pytest.mark.smoke`, `@pytest.mark.slow`, `@pytest.mark.integration`
- Coverage threshold: 65% (`fail_under` in pyproject.toml)

## CI

GitHub Actions on push/PR to main: lint, format check, mypy, tests (matrix: ubuntu+windows, Python 3.11+3.12). Pre-commit hooks enforce ruff, trailing whitespace, no `.env` commits, no direct commits to main.

## Task Tracking

This project uses `bd` (beads) for issue tracking. Run `bd ready` to find available work. See `000-docs/001-DR-GUID-agent-instructions.md` for the full session workflow. All project docs are in `000-docs/` — see `000-docs/000-INDEX.md` for the full inventory.

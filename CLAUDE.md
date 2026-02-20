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
```

Mock mode (`CAD_LLM_PROVIDER=mock`, the default) works without any API key. All tests and the smoke test use mock mode.

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
- `EntityRef` — single entity with handle, type, layer, position, text content
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

## Testing

- **Unit tests** (`tests/unit/`): schemas, validators, parser, reader — no DXF files on disk
- **Smoke tests** (`tests/smoke/`): end-to-end pipeline via `test_e2e_mock.py`
- **Standalone smoke** (`scripts/smoke_test.py`): creates DXF, runs full pipeline, verifies output
- **Fixtures** in `tests/conftest.py`: `sample_dxf` creates a temp DXF with all V1 entity types; `sample_context` loads it; `rule_config` provides default rules
- Pytest markers: `@pytest.mark.smoke`, `@pytest.mark.slow`
- Coverage threshold: 50% (`fail_under` in pyproject.toml)

## CI

GitHub Actions on push/PR to main: lint, format check, mypy, tests (matrix: ubuntu+windows, Python 3.11+3.12). Pre-commit hooks enforce ruff, trailing whitespace, no `.env` commits, no direct commits to main.

## Task Tracking

This project uses `bd` (beads) for issue tracking. Run `bd ready` to find available work. See `000-docs/001-DR-GUID-agent-instructions.md` for the full session workflow. All project docs are in `000-docs/` — see `000-docs/000-INDEX.md` for the full inventory.

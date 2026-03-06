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
make smoke         # python scripts/smoke_test.py (full pipeline, uses mock provider)
make security      # bandit -r src/ -ll && pip-audit

# Run single test
pytest tests/unit/test_validators.py -v
pytest tests/unit/test_validators.py::test_name -v

# Launch desktop app (requires PySide6: pip install -e ".[gui]")
make run           # python -m cad_dxf_agent.app

# Web app (local dev)
cd web/frontend && npm run dev                         # Frontend on :3000
CAD_WEB_DEV_MODE=1 uvicorn web.backend.main:app --port 8322  # Backend on :8322

# Web app (deploy) — AUTOMATIC via GitHub Actions
# Push to main touching web/** or src/** triggers .github/workflows/deploy-web.yml
# which builds Docker image, pushes to Artifact Registry, deploys Cloud Run + Firebase Hosting.
# Just merge to main and it deploys. Check: gh run list --workflow=deploy-web.yml

# Manual deploy (only if GH Actions is broken):
cd web/frontend && npm run build && firebase deploy --only hosting --project cad-dxf-agent
gcloud run deploy cad-dxf-web \
  --source . --dockerfile web/backend/Dockerfile \
  --region us-central1 --project cad-dxf-agent \
  --allow-unauthenticated --memory 1Gi --cpu 1 --timeout 300 \
  --service-account cad-dxf-web-run@cad-dxf-agent.iam.gserviceaccount.com \
  --set-env-vars CAD_LLM_PROVIDER=gemini,CAD_GCP_PROJECT=cad-dxf-agent,OTEL_ENABLED=1,OTEL_EXPORTER=gcp-trace
```

**Deploy notes:**
- **Normal path**: merge to main → GH Actions auto-deploys both frontend + backend via WIF
- **Manual gotcha**: always use `--project cad-dxf-agent` (local gcloud may point to `hustleapp-production`)
- **Do NOT** use `gcloud builds submit --config cloudbuild.yaml` — `$SHORT_SHA` is only set by triggers, not manual submits
- Check deploy status: `gh run list --workflow=deploy-web.yml`

```bash
# Revision CLI
cad-revision diff master.dxf revision.dxf --output-dir ./out
cad-revision bundle master.dxf revision.dxf --output-dir ./bundle --approve-all

# Build desktop executable
make build
```

### Dev Environment

Dev mirrors production. Use Gemini (Vertex AI) locally — not mock mode.

```bash
# One-time: authenticate with GCP
gcloud auth application-default login

# .env (gitignored) — production-like config:
CAD_LLM_PROVIDER=gemini
CAD_GCP_PROJECT=cad-dxf-agent
```

CI tests use mock mode for determinism and speed, but local dev and `tests/live/` hit real Gemini:

```bash
# Live API tests
CAD_GCP_PROJECT=cad-dxf-agent pytest tests/live/ -v -m live_api -s

# CI: live tests run automatically on push to main via WIF (tokenless, no secrets)
```

## Architecture

### Pipeline Flow

```
User Prompt → Planner → ChangeSet → Validator → Preview → EditEngine → Save-As DXF
                                                                    ↘ RevisionNotes
```

1. **dxf_reader** loads DXF via `ezdxf` into a `DrawingContext` (Pydantic model with `EntityRef` list)
2. **semantic_model** builds a JSON-serializable context summary for the planner (no raw DXF exposed)
3. **planner** routes to a `PlannerProvider` (Gemini in prod/dev, mock in CI) which returns a `ChangeSet`
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
    comparison/   # Revision diff engine: alignment, matching, changelog, bundle, overlay
  llm/            # Planner orchestrator, provider ABC, mock/gemini providers, prompt templates
  cli/            # Revision CLI (cad-revision diff/align/apply/bundle/explain)
  ui/             # PySide6 desktop shell (MainWindow)
  settings.py     # Env-based config (all CAD_* prefixed)
  app.py          # Desktop entry point
```

### Data Models (Pydantic)

- `DrawingContext` — normalized view of a loaded DXF (entities, layers, blocks, metadata)
- `EntityRef` — single entity with handle, type, layer, position, text content, block name, attributes
- `EditOperation` — one op with `OpType`, target handle, layer, params dict
- `ChangeSet` — batch of operations from a single prompt
- `ValidationResult` — blockers (prevent apply) and warnings (informational)
- `RuleConfig` — protected layers, max move distance, coordinate tolerance

### Provider Pattern

`PlannerProvider` ABC in `llm/providers.py` → implement `plan(prompt, drawing_context) → ChangeSet`. Two providers: `GeminiProvider` (Vertex AI tool-use with vision, used in dev and prod) and `MockProvider` (keyword-matching, CI/tests only). Set via `CAD_LLM_PROVIDER=gemini|mock`.

## Configuration

All settings via environment variables (`.env` file, `.gitignore`d):

| Variable | Default | Purpose |
|----------|---------|---------|
| `CAD_LLM_PROVIDER` | `mock` | Planner backend (`gemini` for dev/prod, `mock` for CI only) |
| `CAD_PROTECTED_LAYERS` | `TITLE,TITLEBLOCK,SEAL,REVISION` | Comma-separated protected layers |
| `CAD_REVISION_NOTES_ENABLED` | `true` | Insert revision notes after edits |
| `CAD_REVISION_NOTES_LAYER` | `AI_REV_NOTES` | Layer name for revision notes |
| `OTEL_ENABLED` | _(unset)_ | Enable OpenTelemetry tracing (`1`, `true`, `yes`) |
| `OTEL_EXPORTER` | `console` | Span exporter: `console`, `otlp`, or `gcp-trace` |
| `OTEL_EXPORTER_OTLP_ENDPOINT` | _(unset)_ | OTLP collector endpoint (e.g., `http://localhost:4317`) |

### Observability (OpenTelemetry)

Optional tracing via `otel.py` bootstrap module. Off by default, CI-safe (no network). Each pipeline stage emits a span (e.g., `cad.load_dxf`, `cad.run_planner`, `cad.validate`). No full file paths or drawing text in span attributes. Install extras: `pip install -e ".[otel]"`.

## Testing

### Test Tiers

| Tier | Location | Count | What |
|------|----------|-------|------|
| Unit | `tests/unit/` | ~1069 | Schemas, validators, reader, writer, engine, preview, settings, semantic model, snapshots, comparison |
| Integration | `tests/integration/` | ~78 | Full pipeline, undo/redo, agent loop with ScriptedAgentProvider |
| Web | `tests/web/` | ~123 | FastAPI backend endpoints (TestClient) |
| Benchmark | `tests/benchmark/` | ~15 | Performance micro-benchmarks (pytest-benchmark) |
| GUI | `tests/gui/` | ~10 | PySide6 UI tests (require `QT_QPA_PLATFORM=offscreen`) |
| Property | `tests/property/` | ~7 | Fuzz/property tests (randomized, bounded runtime) |
| Smoke | `tests/smoke/` + `scripts/smoke_test.py` | ~7 | End-to-end pipeline via mock planner |
| Live | `tests/live/` | varies | Real Gemini API tests (require ADC + `cad-dxf-agent` GCP project) |

Total: ~1351 tests collected.

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
make test              # All tests
make test-unit         # Unit tests only
make test-integration  # Integration tests only
make test-web          # Web backend API tests only
make test-live         # Live Gemini API tests (require ADC)
make test-cov          # All tests with coverage report
```

- Pytest markers: `@pytest.mark.smoke`, `@pytest.mark.slow`, `@pytest.mark.integration`
- Coverage threshold: 65% (`fail_under` in pyproject.toml)

## CI

GitHub Actions on push/PR to main: lint, format check, mypy, tests (matrix: ubuntu+windows, Python 3.11+3.12). Pre-commit hooks enforce ruff, trailing whitespace, no `.env` commits, no direct commits to main.

## Commit & PR Conventions

### Commit Messages

Use conventional commits with epic/bead references:

```
<type>(scope): <description>

[body]

Epic: epic-cad-NN
Bead: cad-XXX
Co-Authored-By: Claude Opus 4.6 <noreply@anthropic.com>
```

**Types:** `feat`, `fix`, `docs`, `style`, `refactor`, `test`, `chore`
**Scope:** module or area (e.g., `router`, `contracts`, `eval`, `compare`)
**Epic trailer:** Always include when work is part of an epic (e.g., `Epic: epic-cad-02`)
**Bead trailer:** Include the bead ID being worked on (e.g., `Bead: cad-d9a`)

Examples:
```
feat(router): add hybrid heuristic+LLM intent classification

Epic: epic-cad-02
Bead: cad-d9a

docs(epic-01): enhance capability audit with user workflow matrix

Epic: epic-cad-01
Bead: cad-uns
```

### Pull Requests

- **Title:** `<type>: <short description>` (under 70 chars)
- **Body must include:**
  - `## Epic` — which epic this PR belongs to (e.g., EPIC-CAD-02)
  - `## Bead(s)` — bead IDs addressed (e.g., cad-d9a, cad-d9a.1)
  - `## Summary` — 1-3 bullet points
  - `## Test plan` — how changes were verified
  - `## Docs` — which 000-docs were created/updated (if any)
- **Branch naming:** `feature/epic-cad-NN-short-description`

### Workflow

1. `bd update <id> --status in_progress` before starting work
2. Work on feature branch (`feature/epic-cad-NN-*`)
3. Include Epic/Bead trailers in every commit
4. Push, create PR with epic/bead references in body
5. After merge: `bd close <id> --reason "merged PR #NN"` → `bd sync`

## Task Tracking

This project uses `bd` (beads) for issue tracking. Run `bd ready` to find available work. See `000-docs/001-DR-GUID-agent-instructions.md` for the full session workflow. All project docs are in `000-docs/` — see `000-docs/000-INDEX.md` for the full inventory.

### Epic Registry

| Epic | Bead | Title | Phase |
|------|------|-------|-------|
| EPIC-CAD-01 | cad-uns | Capability Audit + Architecture Baseline | 1 |
| EPIC-CAD-02 | cad-d9a | Core Contracts + Routing Foundation | 1 |
| EPIC-CAD-03 | cad-wd2 | Selection + Markup Interpretation Foundation | 1 |
| EPIC-CAD-04 | cad-grx | Region Q&A Vertical Slice | 2 |
| EPIC-CAD-05 | cad-ccd | Repeated-Condition Detection | 2 |
| EPIC-CAD-06 | cad-3e4 | Compare + Diff Service Hardening | 2 |
| ARCH-REVIEW-01 | cad-sfw | Post-EPIC-06 Architecture Review | — |
| EPIC-CAD-07 | cad-9ug | Structured Edit Planning | 3 |
| EPIC-CAD-08 | cad-6zz | Preview + Apply Workflow | 3 |
| EPIC-CAD-09 | cad-ady | Design Operations Workflow Pack | 4 |
| EPIC-CAD-10 | cad-8p2 | Construction Drawing Workflow Pack | 4 |
| EPIC-CAD-11 | cad-36p | Session Durability + Scale Readiness | 5 |
| EPIC-CAD-12 | cad-m7d | Evaluation Harness + Quality Governance | 5 |

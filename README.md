# cad-dxf-agent v0.11.0

Drawing Intelligence Platform for AEC professionals — edit, analyze, and validate 2D DXF drawings using natural-language prompts. The LLM returns structured JSON operations (never raw DXF), which are validated and applied deterministically. Original files are never modified (save-as workflow).

[![CI](https://github.com/jeremylongshore/cad-dxf-agent/actions/workflows/ci.yml/badge.svg)](https://github.com/jeremylongshore/cad-dxf-agent/actions/workflows/ci.yml) [![License: MIT](https://img.shields.io/badge/License-MIT-blue.svg)](https://github.com/jeremylongshore/cad-dxf-agent/blob/main/LICENSE)

**Links:** [Gist One-Pager](https://gist.github.com/jeremylongshore/0303189683f9547c79e1fc1fc68be711) · [Docs](000-docs/000-INDEX.md)

## What Is This?

**cad-dxf-agent** is a multi-capability platform that handles DXF drawings through natural language. Describe what you need — an edit, a compliance check, a quantity takeoff, a health report — and the platform classifies your intent, selects the right processing pipeline, and delivers structured results.

### Capabilities

| Capability | Description |
|------------|-------------|
| **Edit** | Move, rotate, copy, scale, mirror, delete entities; add lines, polylines, circles, arcs, text, blocks |
| **Compliance** | ADA/IBC/custom rule validation with findings and remediation guidance |
| **Health Report** | Drawing quality metrics — layer hygiene, entity stats, potential issues |
| **Quantity Takeoff** | Automated extraction of counts, lengths, areas from drawing entities |
| **Summary** | Plain-English structured narrative of drawing contents |
| **RFI Generation** | Automated Request For Information based on detected ambiguities |
| **Zone Detection** | Closed-loop room/area detection with area calculation |
| **Revision Comparison** | Diff two DXF versions, review changes, apply approved edits |
| **Agent Mode** | Iterative multi-turn tool-use loop for complex requests (max 10 turns) |

### Key Principles

- **Safe edits** — The LLM planner returns structured operations only. It never touches raw DXF data.
- **Two-axis intent classification** — Every prompt is classified by *what* (edit, analyze, compare, query, generate) and *why* (compliance, coordination, documentation, estimation, quality, general).
- **Protected layers** — Configurable layers (TITLE, TITLEBLOCK, SEAL, REVISION) cannot be edited. Enforced at both validator and tool executor levels.
- **Save-as workflow** — Original files are always preserved.
- **Mock mode** — The full pipeline works without an API key for testing and development.

## Scope

| Supported | Not Yet |
|-----------|---------|
| DXF files (2D) | DWG native editing |
| Model space + paper space layouts | 3D entities |
| LINE, LWPOLYLINE, TEXT, MTEXT, INSERT, CIRCLE, ARC | Dimension regeneration |
| 13 edit operations (move, edit_text, delete, add_block, rotate, copy, scale, mirror, add_line, add_polyline, add_circle, add_arc, add_text) | Xrefs |
| Compliance validation (ADA/IBC/custom) | Title block revision table |
| Health reports + quality metrics | |
| Automated quantity takeoff | |
| Plain-English drawing summaries | |
| RFI generation | |
| Zone/room detection with area calc | |
| Agent-mode iterative tool-use | |
| Protected layers + AI revision notes | |
| Revision comparison (CLI + web) | |
| Web app (Firebase + Cloud Run, auto-deploy) | |
| Desktop app (Windows + Linux) | |
| Gemini vision pipeline (Vertex AI) | |
| OpenTelemetry tracing (console, OTLP, GCP Trace) | |

For full details see:
- [Full Application Audit (v0.9.0)](https://gist.github.com/jeremylongshore/0303189683f9547c79e1fc1fc68be711) — complete feature documentation, architecture, and DevOps playbook
- [000-docs/ index](000-docs/000-INDEX.md) — complete documentation inventory (60+ docs)
- [V1 Blueprint](000-docs/007-AT-ARCH-v1-blueprint.md) — engineering architecture and module map
- [ADR: LLM Plans, Not DXF Edits](000-docs/005-AT-ADEC-llm-plans-not-dxf.md) — core architectural decision

## Quickstart

### Prerequisites

- Python 3.11 or 3.12
- pip

### Install

```bash
git clone https://github.com/jeremylongshore/cad-dxf-agent.git
cd cad-dxf-agent
python -m venv .venv
source .venv/bin/activate  # Windows: .venv\Scripts\activate
pip install -e ".[dev]"
pre-commit install
```

### Run Tests (Mock Mode — No API Key Needed)

```bash
# All tests (~4500 tests across 10 tiers)
make test

# With coverage (65% threshold)
make test-cov

# By tier
make test-unit         # ~3600 unit tests
make test-integration  # ~100 integration tests
make test-web          # ~420 web API tests
make test-e2e          # ~33 end-to-end tests
make test-live         # ~42 live Gemini API tests (requires ADC)

# Eval scorecard (intent classification accuracy)
make scorecard         # mock mode
make scorecard-live    # real Gemini

# Smoke test
make smoke
```

### Run All Quality Checks

```bash
make check
```

This runs: lint → format check → type check → tests → smoke test.

### Individual Quality Commands

```bash
make lint        # ruff check
make format      # ruff format
make typecheck   # mypy
make test        # pytest
make smoke       # smoke test script
make security    # bandit + pip-audit
```

### Launch the Desktop App

```bash
make run
# or: python -m cad_dxf_agent.app
```

This opens the PySide6 desktop window. You can:
1. Click **Open DXF** to load a file
2. Type a prompt (e.g., "Move the column east by 2 feet")
3. Click **Plan & Preview** to see proposed changes
4. Click **Apply & Save As** to save the edited DXF

### Web App

The web app is deployed at [cad-dxf-agent.web.app](https://cad-dxf-agent.web.app).

For local development:

```bash
# Frontend (React + Vite)
cd web/frontend && npm run dev    # http://localhost:3000

# Backend (FastAPI)
CAD_WEB_DEV_MODE=1 uvicorn web.backend.main:app --port 8322
```

**Deploy:** Push to `main` → GitHub Actions auto-deploys both frontend (Firebase Hosting) and backend (Cloud Run) via Workload Identity Federation. No manual deploy steps needed. Check status: `gh run list --workflow=deploy-web.yml`

## Testing Without an API Key (Mock Mode)

The default LLM provider is `mock`, which uses simple keyword matching to generate operations. This lets you test the entire pipeline offline:

```bash
# Set in .env or environment (this is the default):
export CAD_LLM_PROVIDER=mock

# Run the smoke test:
python scripts/smoke_test.py
```

The mock provider responds to keywords like "move", "delete", "text", "rename" in your prompt.

## Using Gemini (Vertex AI)

The production planner uses Gemini via Vertex AI:

```bash
# Authenticate with GCP
gcloud auth application-default login

# Set environment
export CAD_LLM_PROVIDER=gemini
export CAD_GCP_PROJECT=cad-dxf-agent

# Run
python -m cad_dxf_agent.app
```

The planner uses tool-use with vision capabilities — it can analyze DXF renders and plan operations based on visual inspection. For complex multi-step requests, the agent mode runs an iterative tool-use loop (up to 10 turns) with 20+ query and edit tools.

**Notes:**
- Requires `google-cloud-aiplatform` (included in `[gemini]` extras)
- API credentials are handled via Application Default Credentials (ADC)
- Mock provider (`CAD_LLM_PROVIDER=mock`) still works for offline testing

## AI Revision Notes

When enabled (default), the tool inserts a revision note on the `AI_REV_NOTES` layer after applying edits. Notes are generated deterministically from the operations — never from freeform LLM output.

Examples:
- `REV 8 - Column shift`
- `REV 8 - Moved entity east 2'-0"`
- `REV 5 - Updated text to 'New Label'; Deleted entity`

Configure via environment variables:
```bash
CAD_REVISION_NOTES_ENABLED=true   # true/false
CAD_REVISION_NOTES_LAYER=AI_REV_NOTES
```

Protected layers (TITLE, TITLEBLOCK, SEAL, REVISION) are **never** modified. The real title block revision table is out of scope for V1.

## Revision Workflow

Compare two DXF versions, review structural changes, and apply approved edits to produce a new drawing.

### CLI

```bash
cad-revision <command> [options]
```

| Command | What it does |
|---------|-------------|
| `cad-revision diff` | Compare two DXFs and output a changelog |
| `cad-revision align` | Check/preview alignment transform only |
| `cad-revision dry-run` | Full pipeline without writing any files |
| `cad-revision apply` | Apply approved changes to a new DXF |
| `cad-revision bundle` | Produce a zip with DXF + overlay + changelog |
| `cad-revision explain` | Human-readable explanation of changes |

Quick example:

```bash
# Compare and generate changelog
cad-revision diff master.dxf revision.dxf --output-dir ./out

# Full bundle with all changes auto-approved
cad-revision bundle master.dxf revision.dxf --output-dir ./bundle --approve-all
```

**Global flags:** `--json`, `--verbose`, `--version`

**Exit codes:** 0 = no changes, 1 = changes found, 2 = error

**Manual control points** (for drawings with large coordinate offsets):

```bash
cad-revision diff master.dxf revision.dxf \
  --control-points "100,200:105,205" "300,400:305,405"
```

### Web App

The web revision workflow is a 5-step wizard in the **Compare** tab:

1. **Upload** — Upload a revision DXF to compare against the current master
2. **Align** — Automatic alignment (or manual control points if confidence is low)
3. **Review** — Approve or reject each detected change
4. **Apply** — Apply approved changes to produce a new DXF
5. **Download** — Download a bundle (.zip) containing the updated master, diff overlay, changelog, and metadata

### Troubleshooting

- **Units mismatch** — Master in inches, revision in mm → low alignment confidence. Convert both files to matching units first.
- **Partial revisions** — Revision contains only a subset of the drawing → alignment may fail. Use manual control points (`--control-points` in CLI, or the manual alignment UI in the web app).
- **Xrefs and dynamic blocks** — Not yet supported. These are detected and skipped with a warning message.

## Protected Layers

By default, these layers are protected and cannot be edited:
- `TITLE`
- `TITLEBLOCK`
- `SEAL`
- `REVISION`

Customize via environment variable:
```bash
CAD_PROTECTED_LAYERS=TITLE,TITLEBLOCK,SEAL,REVISION,CUSTOM_LAYER
```

Any operation targeting an entity on a protected layer will be blocked by the validator.

## Observability (OpenTelemetry)

Optional distributed tracing for pipeline performance insights. Off by default, CI-safe (no network calls when disabled).

### Enable

```bash
# Install OTel extras
pip install -e ".[otel]"

# Enable console exporter (prints spans to stdout)
OTEL_ENABLED=1 python scripts/smoke_test.py

# Send to an OTLP collector (Jaeger, Grafana Tempo, etc.)
OTEL_ENABLED=1 OTEL_EXPORTER=otlp OTEL_EXPORTER_OTLP_ENDPOINT=http://localhost:4317 python scripts/smoke_test.py

# GCP Cloud Trace (production)
OTEL_ENABLED=1 OTEL_EXPORTER=gcp-trace python scripts/smoke_test.py
```

### Spans Emitted

| Span Name | Attributes |
|-----------|------------|
| `cad.load_dxf` | `cad.file.name`, `cad.entities.count`, `cad.layers.count` |
| `cad.build_context` | `cad.entities.count` |
| `cad.run_planner` | `cad.mode`, `cad.ops.count` |
| `cad.validate` | `cad.ops.count`, `cad.validation.valid`, `cad.validation.blockers` |
| `cad.apply_changeset` | `cad.ops.count`, `cad.ops.success_count` |
| `cad.save` | `cad.save.output_basename` |
| `cad.revision_note` | `cad.revision.layer` |

**Privacy:** No full file paths, no drawing text content, no API keys are ever included in span attributes.

### Environment Variables

| Variable | Default | Purpose |
|----------|---------|---------|
| `OTEL_ENABLED` | _(unset)_ | Enable tracing (`1`, `true`, `yes`) |
| `OTEL_EXPORTER` | `console` | Exporter type: `console`, `otlp`, or `gcp-trace` |
| `OTEL_EXPORTER_OTLP_ENDPOINT` | _(unset)_ | OTLP collector URL |

## Architecture

### Request Flow

```
User Prompt
  → ObjectiveClassifier (2-axis: RequestClass × ObjectiveTag)
  → StrategyRegistry (maps classification → StagePipelineDefinition)
  → StageExecutor (runs ordered stages: deterministic + LLM)
  → ResponseBuilder (PlatformResponse envelope)
```

For **edit requests**, the stage pipeline includes:
```
Planner → ChangeSet → Validator → Preview → EditEngine → Save-As DXF + RevisionNotes
```

For **analysis requests** (compliance, health, takeoff, summary, RFI, zones), the pipeline runs deterministic extractors without the edit flow.

### Two-Axis Intent Classification

Every prompt is classified on two independent axes:

1. **RequestClass** — *what* the user wants done: `edit`, `analyze`, `compare`, `query`, `generate`
2. **ObjectiveTag** — *why* they want it: `compliance`, `coordination`, `documentation`, `estimation`, `quality`, `general`

The `StrategyRegistry` maps each (RequestClass, ObjectiveTag) pair to a `StagePipelineDefinition` — an ordered list of `StageHandler` implementations.

### Agent Mode

For complex requests, the `AgentProvider` runs an iterative tool-use loop:

1. Sends prompt + drawing context + tool definitions to Gemini
2. Gemini returns tool calls (query tools: list entities, find by layer; edit tools: move, delete, add)
3. `ToolExecutor` dispatches each call, enforcing protected-layer rules
4. Results feed back to Gemini for next iteration (max 10 turns)
5. Final ChangeSet extracted from accumulated tool calls

20+ tools split into query (read-only) and edit (state-changing) categories.

## Project Structure

```
cad-dxf-agent/
  src/cad_dxf_agent/
    app.py                  # Desktop entry point
    settings.py             # Env-based configuration
    otel.py                 # OpenTelemetry bootstrap
    core/                   # 41 modules — DXF I/O, validation, editing, analysis
    llm/                    # 22 modules — intent classification, planning, agent loop
    models/                 # 30 Pydantic schemas
    cli/                    # Revision CLI (cad-revision)
    ui/                     # PySide6 desktop UI
  web/
    frontend/               # React + Vite SPA (Firebase Hosting)
    backend/                # FastAPI on Cloud Run (20+ endpoints)
  tests/
    unit/                   # ~3600 unit tests
    integration/            # ~100 integration tests
    web/                    # ~420 web API tests
    eval/                   # ~240 eval scorecard tests
    live/                   # ~42 live Gemini API tests
    e2e/                    # ~33 end-to-end tests
    benchmark/              # ~19 performance benchmarks
    gui/                    # ~10 PySide6 UI tests
    property/               # ~7 fuzz/property tests
    smoke/                  # ~7 smoke tests
  scripts/
    smoke_test.py           # Standalone smoke test
  000-docs/                 # All project docs (60+ files)
```

## Documentation

All docs live in [`000-docs/`](000-docs/000-INDEX.md) using flat chronological filing.

Key references:
- [V1 Blueprint](000-docs/007-AT-ARCH-v1-blueprint.md) — architecture, module map, scope
- [ADR: Local-First Architecture](000-docs/004-AT-ADEC-local-first-architecture.md)
- [ADR: LLM Plans, Not DXF Edits](000-docs/005-AT-ADEC-llm-plans-not-dxf.md)
- [ADR: AI Revision Notes on Safe Layer](000-docs/006-AT-ADEC-ai-revision-notes.md)

## License

MIT — see [LICENSE](LICENSE).

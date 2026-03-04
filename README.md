# cad-dxf-agent

Local-first DXF layout editor with LLM-assisted prompt-to-edit planning, validation, preview, and safe save-as DXF workflow.

## What Is This?

**cad-dxf-agent** lets you edit 2D DXF drawings using natural-language prompts. Describe what you want changed, and the tool plans, validates, previews, and applies the edit — saving the result as a new DXF file. Your original drawing is never modified.

### Key Principles

- **Local-first** — DXF processing happens entirely on your machine. No cloud required.
- **Safe edits** — The LLM planner returns structured operations only. It never touches raw DXF data.
- **Protected layers** — Configurable layers (TITLE, TITLEBLOCK, SEAL, REVISION) cannot be edited.
- **Save-as workflow** — Original files are always preserved.
- **Mock mode** — The full pipeline works without an API key for testing and development.

## Scope

| Supported | Not Yet |
|-----------|---------|
| DXF files | DWG native editing |
| Model space + paper space layouts | 3D entities |
| LINE, LWPOLYLINE, TEXT, MTEXT, INSERT, CIRCLE, ARC, etc. | Dimension regeneration |
| move, edit_text, delete, add_block | Xrefs |
| Protected layers | Title block revision table |
| AI revision notes (safe layer) | |
| Revision comparison pipeline (CLI + web) | |
| Web app (Firebase + Cloud Run) | |
| Desktop app (Windows + Linux) | |
| Gemini vision pipeline (Vertex AI) | |

For full details see:
- [Full Application Audit (v0.5.0)](https://gist.github.com/jeremylongshore/0303189683f9547c79e1fc1fc68be711) — complete feature documentation, architecture, API reference, and tech stack
- [V1 Blueprint](000-docs/007-AT-ARCH-v1-blueprint.md) — engineering architecture and module map
- [PRD Addendum](000-docs/008-PP-PROD-prd-addendum.md) — product requirements and acceptance criteria

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
# All tests (~573 tests)
make test

# With coverage (68%+)
make test-cov

# Web API tests only
make test-web

# Smoke test only
make smoke

# Or directly:
pytest -v
python scripts/smoke_test.py
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

Deploy:
```bash
# Frontend to Firebase Hosting
cd web/frontend && npm run build && firebase deploy --only hosting

# Backend to Cloud Run
gcloud builds submit --config web/backend/cloudbuild.yaml .
```

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

The planner uses tool-use with vision capabilities — it can analyze DXF renders and plan operations based on visual inspection.

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

# Or send to an OTLP collector (Jaeger, Grafana Tempo, etc.)
OTEL_ENABLED=1 OTEL_EXPORTER_OTLP_ENDPOINT=http://localhost:4317 python scripts/smoke_test.py
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
| `OTEL_EXPORTER` | `console` | Exporter type: `console` or `otlp` |
| `OTEL_EXPORTER_OTLP_ENDPOINT` | _(unset)_ | OTLP collector URL |

## Project Structure

```
cad-dxf-agent/
  src/cad_dxf_agent/
    app.py                  # Desktop entry point
    settings.py             # Env-based configuration
    otel.py                 # OpenTelemetry bootstrap
    core/                   # DXF processing, validation, editing
    llm/                    # Planner, providers, prompts
    models/                 # Pydantic schemas
    ui/                     # PySide6 desktop UI
  web/
    frontend/               # React + Vite SPA (Firebase Hosting)
    backend/                # FastAPI (Cloud Run)
  tests/
    unit/                   # ~270 unit tests
    integration/            # ~15 integration tests
    web/                    # ~65 web API tests
    live/                   # Live Gemini API tests
  scripts/
    smoke_test.py           # Standalone smoke test
  000-docs/                 # All project docs
```

## Documentation

All docs live in [`000-docs/`](000-docs/000-INDEX.md) using flat chronological filing.

- [V1 Blueprint](000-docs/007-AT-ARCH-v1-blueprint.md) — architecture, module map, scope
- [PRD Addendum](000-docs/008-PP-PROD-prd-addendum.md) — product requirements, acceptance criteria
- [Beads V1 Plan](000-docs/009-PM-TASK-v1-beads-plan.md) — epics, tasks, dependencies
- [ADR 0001: Local-First Architecture](000-docs/004-AT-ADEC-local-first-architecture.md)
- [ADR 0002: LLM Plans, Not DXF Edits](000-docs/005-AT-ADEC-llm-plans-not-dxf.md)
- [ADR 0003: AI Revision Notes on Safe Layer](000-docs/006-AT-ADEC-ai-revision-notes.md)
- [Phase 1 AAR](000-docs/010-AA-AACR-phase-01-aar.md) — after action review

## License

MIT — see [LICENSE](LICENSE).

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

## V1 Scope

| Supported | Not in V1 |
|-----------|-----------|
| DXF files | DWG native editing |
| 2D model space | Paper space / layouts |
| LINE, LWPOLYLINE, TEXT, MTEXT, INSERT | 3D entities |
| move, edit_text, delete, add_block | Dimension regeneration |
| Protected layers | Xrefs |
| AI revision notes (safe layer) | Title block revision table |
| Windows + Linux | Cloud deployment |

For full details see:
- [V1 Blueprint](docs/specs/v1-blueprint.md) — engineering architecture and module map
- [PRD Addendum](docs/specs/prd-addendum-v1.md) — product requirements and acceptance criteria

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
# All tests
make test

# With coverage
make test-cov

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

## Testing Without an API Key (Mock Mode)

The default LLM provider is `mock`, which uses simple keyword matching to generate operations. This lets you test the entire pipeline offline:

```bash
# Set in .env or environment (this is the default):
export CAD_LLM_PROVIDER=mock

# Run the smoke test:
python scripts/smoke_test.py
```

The mock provider responds to keywords like "move", "delete", "text", "rename" in your prompt.

## Testing With a Real LLM

To use a real LLM provider, set the appropriate environment variables:

```bash
# Copy the example env file
cp .env.example .env

# Edit .env:
CAD_LLM_PROVIDER=openai          # or: anthropic, google
CAD_OPENAI_API_KEY=sk-...        # your API key
```

**Caveats:**
- Real LLM providers are scaffolded but not fully implemented in V1. Only the mock provider is wired.
- API keys are never logged or committed. The `.env` file is in `.gitignore`.

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

## Project Structure

```
cad-dxf-agent/
  src/cad_dxf_agent/
    app.py                  # Entry point
    settings.py             # Env-based configuration
    core/
      dxf_reader.py         # DXF → DrawingContext
      dxf_writer.py         # Save-as new DXF
      entity_index.py       # Fast entity lookups
      semantic_model.py     # Planner context builder
      validators.py         # Operation validation
      edit_engine.py        # Apply operations
      revision_notes.py     # AI revision note generation
      preview_model.py      # Change preview
    llm/
      planner.py            # Planner orchestrator
      providers.py          # Provider interface
      mock_provider.py      # Offline mock planner
      response_parser.py    # JSON → ChangeSet
      prompt_templates.py   # LLM prompt templates
    models/
      cad_schema.py         # Entity, layer, drawing context
      ops_schema.py         # Operations, changesets
      config_schema.py      # Rule and revision config
      changes_schema.py     # Validation results
    ui/
      main_window.py        # PySide6 desktop shell
    api/
      local_api.py          # Local HTTP API (scaffolded)
  tests/
    unit/                   # Schema, validator, parser, reader tests
    integration/            # Integration tests
    smoke/                  # End-to-end pipeline tests
    fixtures/               # Test fixture helpers
  scripts/
    smoke_test.py           # Standalone smoke test
  docs/
    specs/                  # V1 blueprint, PRD addendum
    beads/                  # Beads epic/task plan
    adr/                    # Architecture Decision Records
```

## Documentation

- [V1 Blueprint](docs/specs/v1-blueprint.md) — architecture, module map, scope
- [PRD Addendum](docs/specs/prd-addendum-v1.md) — product requirements, acceptance criteria
- [Beads V1 Plan](docs/beads/v1-beads-plan.md) — epics, tasks, dependencies
- [ADR 0001: Local-First Architecture](docs/adr/0001-local-first-architecture.md)
- [ADR 0002: LLM Plans, Not DXF Edits](docs/adr/0002-llm-plans-not-dxf-edits.md)
- [ADR 0003: AI Revision Notes on Safe Layer](docs/adr/0003-ai-revision-notes-safe-layer.md)

## License

MIT — see [LICENSE](LICENSE).

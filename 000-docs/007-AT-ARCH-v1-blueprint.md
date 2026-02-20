# V1 Blueprint — cad-dxf-agent

## Product Summary

**cad-dxf-agent** is a local-first desktop application for prompt-driven DXF layout editing. Users describe edits in natural language, and the tool translates them into safe, validated, deterministic operations on 2D DXF drawings.

## Architecture

```
User Prompt
    │
    ▼
┌──────────────┐
│  LLM Planner │  (or Mock Planner for offline use)
│  (structured │
│   ops JSON)  │
└──────┬───────┘
       │
       ▼
┌──────────────┐
│  Validator   │  Checks protected layers, coords, params
└──────┬───────┘
       │
       ▼
┌──────────────┐
│  Preview     │  Human-readable summary of proposed changes
└──────┬───────┘
       │ (user approves)
       ▼
┌──────────────┐
│  Edit Engine │  Applies ops to DXF via ezdxf
└──────┬───────┘
       │
       ▼
┌──────────────┐
│  Rev Notes   │  Optional AI_REV_NOTES layer insertion
└──────┬───────┘
       │
       ▼
┌──────────────┐
│  Save-As     │  New DXF file (original untouched)
└──────────────┘
```

## V1 Scope

### Supported
| Feature | Details |
|---------|---------|
| File format | DXF only |
| Space | Model space only |
| Dimensions | 2D only |
| Entity types | LINE, LWPOLYLINE, TEXT, MTEXT, INSERT |
| Operations | move_entity, edit_text, delete_entity, add_block |
| Protected layers | TITLE, TITLEBLOCK, SEAL, REVISION (configurable) |
| Save mode | Save-as new DXF (never overwrites original) |
| AI revision notes | Deterministic notes on AI_REV_NOTES layer |
| LLM providers | Mock (offline), OpenAI, Anthropic, Google (pluggable) |
| Platform | Windows-first, Linux supported |

### Not in V1
- DWG native editing
- Paper space / layout tabs
- Xrefs
- Automatic dimension regeneration
- Title block revision table writing
- 3D entities
- Cloud-hosted deployment
- Local/offline LLM (future phase)

## Key Modules

| Module | Path | Purpose |
|--------|------|---------|
| DXF Reader | `core/dxf_reader.py` | Load DXF → DrawingContext |
| DXF Writer | `core/dxf_writer.py` | Save-as new DXF |
| Entity Index | `core/entity_index.py` | Fast entity lookup by handle/layer/type |
| Semantic Model | `core/semantic_model.py` | Build planner context summary |
| Validators | `core/validators.py` | Rule-based operation validation |
| Edit Engine | `core/edit_engine.py` | Apply validated ops to DXF |
| Revision Notes | `core/revision_notes.py` | Deterministic note generation + insertion |
| Preview Model | `core/preview_model.py` | Human-readable change preview |
| Planner | `llm/planner.py` | Orchestrate prompt → changeset |
| Mock Provider | `llm/mock_provider.py` | Offline testing provider |
| Response Parser | `llm/response_parser.py` | Parse/validate LLM JSON output |
| Main Window | `ui/main_window.py` | PySide6 desktop shell |

## Security Principles
1. LLM never edits raw DXF
2. Protected layers enforced by validator
3. Save-as only (original preserved)
4. No hardcoded API keys
5. Safe logging (no key leakage)

## Test Strategy
- Unit tests for schemas, validators, revision notes, parser
- Smoke tests for full pipeline with mock planner
- All tests work without an API key
- CI runs lint (ruff), types (mypy), tests (pytest), security (bandit, pip-audit)

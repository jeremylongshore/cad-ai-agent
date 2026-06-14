# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What This Project Is

Drawing Intelligence Platform built on DXF. Started as a local-first DXF layout editor with LLM-assisted planning; now a multi-capability platform that handles edits, compliance checks, quantity takeoffs, health reports, drawing summaries, RFI generation, and zone detection — all via natural-language prompts. The LLM returns structured JSON operations (never raw DXF) which are validated and applied deterministically. Original files are never modified (save-as workflow).

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

# Eval scorecard (intent classification accuracy)
make scorecard          # mock mode

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
  --allow-unauthenticated --memory 8Gi --cpu 4 --timeout 600 \
  --service-account cad-dxf-web-run@cad-dxf-agent.iam.gserviceaccount.com \
  --set-env-vars OTEL_ENABLED=1,OTEL_EXPORTER=gcp-trace
  # The deployed backend runs `mock` unless you set CAD_LLM_PROVIDER to a
  # bring-your-own provider (e.g. CAD_LLM_PROVIDER=my_providers:MyProvider).
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

### Dev Environment + LLM provider

Local dev and CI default to `CAD_LLM_PROVIDER=mock` (keyword matching, no key).
The LLM is **pluggable** — `get_provider()` (`llm/planner.py`) loads any
`PlannerProvider` (`llm/providers.py`) from a dotted import path. For real-AI
dev, implement one and point the env var at it:

```bash
# .env (gitignored):
CAD_LLM_PROVIDER=my_providers:MyProvider   # package.module:ClassName
```

A bad path or non-`PlannerProvider` class raises at startup (no silent mock
fallback). Bare unknown names (no `:`/`.`) still fall back to mock.

> The bundled Gemini/Vertex providers (`gemini_provider`, `gemini_key_provider`,
> the Vertex `AgentProvider`, `proxy_client`), the `tests/live/` suite, and the
> `live-test` CI job were **removed**. Real AI is now exclusively bring-your-own.
> `mock` and `mock-agent` (offline) remain; the provider-agnostic `ToolExecutor`
> + `tool_definitions` scaffolding stays so a BYO provider can do agent-style
> tool use.

## Architecture

### Request Flow (v0.10.1)

```
User Prompt
  → ObjectiveClassifier (2-axis: RequestClass × ObjectiveTag)
  → StrategyRegistry (maps classification → StagePipelineDefinition)
  → StageExecutor (runs ordered stages: deterministic + LLM)
  → ResponseBuilder (PlatformResponse envelope)
```

For **edit requests**, the stage pipeline includes the original edit flow:

```
Planner → ChangeSet → Validator → Preview → EditEngine → Save-As DXF
                                                       ↘ RevisionNotes
```

For **analysis requests** (compliance, health, takeoff, summary, RFI), the pipeline runs deterministic extractors without the edit flow.

### Two-Axis Intent Classification

Every prompt is classified on two independent axes:

1. **RequestClass** — *what* the user wants done: `edit`, `analyze`, `compare`, `query`, `generate`
2. **ObjectiveTag** — *why* they want it: `compliance`, `coordination`, `documentation`, `estimation`, `quality`, `general`

The `StrategyRegistry` maps each (RequestClass, ObjectiveTag) pair to a `StagePipelineDefinition` — an ordered list of `StageHandler` implementations. This replaces the original one-shot planner model with composable multi-stage pipelines.

### Agent-Mode (Tool-Use Loop)

Agent mode is a provider-agnostic tool-use loop. The bundled real backend
(Vertex `AgentProvider`) was removed; `MockAgentProvider` (`llm/agent_provider.py`)
exercises the loop offline, and a bring-your-own provider can drive it via the
same `ToolExecutor` + tool definitions:

1. Sends prompt + drawing context + tool definitions to the LLM provider
2. The provider returns tool calls (query tools: list entities, find by layer; edit tools: move, delete, add)
3. `ToolExecutor` (`llm/tool_executor.py`) dispatches each call, enforcing protected-layer rules at the executor level
4. Results feed back to the provider for the next iteration (max 10 turns)
5. Final ChangeSet extracted from accumulated tool calls

Tool definitions in `llm/tool_definitions.py` — 20+ tools split into query (read-only) and edit (state-changing) categories.

### Core Pipeline Steps

1. **dxf_reader** loads DXF via `ezdxf` into a `DrawingContext` (Pydantic model with `EntityRef` list)
2. **semantic_model** builds a JSON-serializable context summary; `build_enriched_context()` adds family detection, primitive extraction, and zone data
3. **objective_classifier** classifies prompt intent on 2 axes → `ObjectiveClassification`
4. **strategy_registry** selects a `StagePipelineDefinition` for the classification
5. **stage_executor** runs each stage handler in order, with `StageGate` checkpoints between stages
6. For edit pipelines: **validators** check ops against `RuleConfig`, **edit_engine** applies to working copy, **revision_notes** adds deterministic notes
7. **response_builder** wraps outputs in `PlatformResponse` envelope (includes `TaskFamily`, `ResponseType`, `RiskLevel`, `AuditMetadata`)
8. **dxf_writer** saves to a new file path (original untouched)

### Key Architectural Rules

- **LLM never touches DXF directly** (see `000-docs/005-AT-ADEC-llm-plans-not-dxf.md`). It returns structured `EditOperation` objects with `OpType` enum: `move_entity`, `edit_text`, `delete_entity`, `add_block`, `rotate_entity`, `copy_entity`, `scale_entity`, `mirror_entity`, `add_line`, `add_polyline`, `add_circle`, `add_arc`, `add_text`. Invalid/unsupported ops reject the entire changeset.
- **Protected layers** (TITLE, TITLEBLOCK, SEAL, REVISION) cannot be edited. Enforced at both validator and ToolExecutor levels.
- **Revision notes are deterministic** — generated from operation metadata, never from freeform LLM output.
- **Supported entity types**: LINE, LWPOLYLINE, TEXT, MTEXT, INSERT, CIRCLE, ARC. Other types are skipped during load.
- **Response contracts** — every API response wraps in `PlatformResponse` with `TaskFamily` (11 categories), `ResponseType` (7 kinds), and `AuditMetadata` for traceability.

### Source Layout

```
src/cad_dxf_agent/
  models/              # 30 Pydantic schemas
    cad_schema         #   DrawingContext, EntityRef, LayerInfo, BlockInfo
    ops_schema         #   EditOperation, OpType enum, ChangeSet
    objective_schema   #   RequestClass, ObjectiveTag, ObjectiveClassification
    response_schema    #   PlatformResponse, TaskFamily, ResponseType, RiskLevel
    compliance_schema  #   ComplianceProfile, ComplianceFinding
    takeoff_schema     #   TakeoffResult, quantity extraction models
    health_schema      #   HealthReport, quality metrics
    zone_schema        #   Zone, room/area detection models
    document_schema    #   UserDocument metadata for persistence
    config_schema      #   RuleConfig, ValidationResult
    ...                #   + comparison, region, qna, precision, rfi, stats, etc.

  core/                # 43 modules — DXF I/O, validation, editing, platform services
    dxf_reader         #   Load DXF → DrawingContext
    dxf_writer         #   Save working copy to new path
    edit_engine        #   Apply validated ops to DXF
    entity_index       #   R-tree spatial index (nearest, find_in_radius)
    semantic_model     #   Drawing context → planner-ready summary
    validators         #   RuleConfig enforcement (blockers + warnings)
    preview_builder    #   Human-readable change descriptions
    revision_notes     #   Deterministic notes on AI_REV_NOTES layer
    family_detector    #   20 architectural families, 150+ signal patterns
    primitive_extractors  # Symbol detection, label extraction, layer classification
    zone_detector      #   Closed-loop room/zone detection, area calc
    compliance_rules   #   Deterministic ADA/IBC/custom compliance checker
    takeoff_engine     #   Automated quantity extraction
    health_checker     #   Drawing quality metrics
    drawing_summarizer #   Structured narrative summaries
    rfi_generator      #   Request For Information generation
    session_store      #   ABC + InMemory + GCS (2h TTL ephemeral sessions)
    document_store     #   ABC + InMemory + GCS (persistent user documents)
    edit_history       #   Undo/redo + named snapshots
    comparison/        #   Revision diff engine (alignment, matching, changelog, bundle, overlay)

  llm/                 # intent classification, planning, agent loop
    planner            #   Orchestrator: prompt → ChangeSet; loads built-in + BYO providers
    providers          #   PlannerProvider ABC (the bring-your-own seam)
    mock_provider      #   Keyword-matching (offline / CI / default)
    agent_provider     #   MockAgentProvider — offline tool-use loop
    tool_executor      #   Dispatches 20+ tools with safety enforcement
    tool_definitions   #   Query + edit tool schemas (function-calling format)
    objective_classifier  # 2-axis intent classification
    strategy_registry  #   (RequestClass, ObjectiveTag) → StagePipelineDefinition
    stage_executor     #   Runs ordered stage handlers with gate checkpoints
    stage_handlers/    #   analyze, summarize, compliance, health, detect_zones
    response_builder   #   Builds PlatformResponse envelopes
    intent_router      #   Routes prompts to intent families
    capability_registry   # Declares tool capabilities per RequestClass
    prompt_templates   #   System prompts + AGENT_SYSTEM_PROMPT

  cli/                 # Revision CLI (cad-revision diff/align/apply/bundle/explain)
  ui/                  # PySide6 desktop shell (MainWindow, pipeline_worker)
  settings.py          # Env-based config (all CAD_* prefixed)
  app.py               # Desktop entry point
  otel.py              # OpenTelemetry bootstrap

web/
  backend/             # FastAPI on Cloud Run
    main.py            #   App + 20+ endpoints (upload, plan, apply, compare, documents)
    api_v1.py          #   /api/v1 router
    session.py         #   SessionManager for ephemeral work
    auth.py            #   Firebase auth validation
  frontend/            # React + Vite SPA on Firebase Hosting
```

### Tool Function Architecture (EPIC-CAD-31)

Tool schemas exist in two coexisting representations in `llm/tool_definitions.py`:
1. **Dict-based schemas** — hand-written function-call schema dicts (canonical, used at runtime)
2. **Typed Python functions** — `_fn` stub functions with type hints and docstrings for ADK-pattern schema generation

Both are kept in sync via CI tests (`test_all_tools_typed`, schema-matching assertions). The typed functions `raise NotImplementedError` — dispatch stays in `ToolExecutor`. When ADK migration happens (Phase 2+), the typed functions become the canonical source and the dicts are deleted.

`_hint_to_json_schema()` handles: primitives, `Optional`, `Literal` (→ `enum`), dataclasses (→ nested `object`), `list[X]` (→ `array`).

### Provider Pattern

`PlannerProvider` ABC in `llm/providers.py` → implement `plan(prompt, drawing_context) → ChangeSet` and a `name`. Built-in providers:
- `MockProvider` — keyword-matching (offline / CI / default)
- `MockAgentProvider` — offline mock of the tool-use loop

Real AI is **bring-your-own**: set `CAD_LLM_PROVIDER` to a dotted import path
(`package.module:YourProvider`); `get_provider()` (`llm/planner.py`) imports and
validates it as a `PlannerProvider`. Bad specs raise; bare unknown names fall
back to mock.

## Configuration

All settings via environment variables (`.env` file, `.gitignore`d):

| Variable | Default | Purpose |
|----------|---------|---------|
| `CAD_LLM_PROVIDER` | `mock` | Planner backend: `mock`, `mock-agent`, or a bring-your-own dotted path `package.module:YourProvider` |
| `CAD_GCP_PROJECT` | _(unset)_ | GCP project for generic cloud integrations (e.g. OTel `gcp-trace` exporter) |
| `CAD_PROTECTED_LAYERS` | `TITLE,TITLEBLOCK,SEAL,REVISION` | Comma-separated protected layers |
| `CAD_REVISION_NOTES_ENABLED` | `true` | Insert revision notes after edits |
| `CAD_REVISION_NOTES_LAYER` | `AI_REV_NOTES` | Layer name for revision notes |
| `CAD_WEB_DEV_MODE` | _(unset)_ | Skip Firebase auth for local backend testing |
| `CAD_ALLOWED_EMAILS` | _(unset)_ | Semicolon-separated emails allowed to auto-provision (also checks Firestore `allowlist` collection) |
| `OTEL_ENABLED` | _(unset)_ | Enable OpenTelemetry tracing (`1`, `true`, `yes`) |
| `OTEL_EXPORTER` | `console` | Span exporter: `console`, `otlp`, or `gcp-trace` |
| `OTEL_EXPORTER_OTLP_ENDPOINT` | _(unset)_ | OTLP collector endpoint (e.g., `http://localhost:4317`) |
| `CAD_AGENT_BACKEND` | `cloud_run` | Agent backend selector (`cloud_run` local pipeline; `agent_engine` reserved/unwired) |
| `CAD_AGENT_ENGINE_URL` | _(unset)_ | Remote agent-engine endpoint (reserved/unwired) |

### Observability (OpenTelemetry)

Optional tracing + metrics via `otel.py` bootstrap module. Off by default, CI-safe (no network). Each pipeline stage emits a span (e.g., `cad.load_dxf`, `cad.run_planner`, `cad.validate`). Core metrics: `cad.request.count`, `cad.request.latency_ms`, `cad.agent.turns`, `cad.tool.success`, `cad.tool.failure`. No full file paths or drawing text in span attributes. Install extras: `pip install -e ".[otel]"`.

## Testing

### Test Tiers

| Tier | Location | Count | What |
|------|----------|-------|------|
| Unit | `tests/unit/` | ~3600 | Schemas, validators, reader, writer, engine, preview, semantic model, snapshots, comparison, compliance, takeoff, zones, families |
| Integration | `tests/integration/` | ~100 | Full pipeline, undo/redo, agent loop with ScriptedAgentProvider |
| Web | `tests/web/` | ~420 | FastAPI backend endpoints (TestClient), document library, session management |
| Eval | `tests/eval/` | ~40 | Intent classification accuracy scorecard |
| E2E | `tests/e2e/` | ~33 | End-to-end tests with real DXF files |
| Benchmark | `tests/benchmark/` | ~19 | Performance micro-benchmarks (pytest-benchmark) |
| GUI | `tests/gui/` | ~10 | PySide6 UI tests (require `QT_QPA_PLATFORM=offscreen`) |
| Property | `tests/property/` | ~7 | Fuzz/property tests (randomized, bounded runtime) |
| Smoke | `tests/smoke/` + `scripts/smoke_test.py` | ~7 | End-to-end pipeline via mock planner |

Total: ~4600 tests collected (the Gemini live tier was removed with the providers).

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
make test-e2e          # E2E tests (need scripts/download_e2e_fixtures.sh first)
make test-cov          # All tests with coverage report
make scorecard         # Eval scorecard (mock mode)
```

- Pytest markers: `@pytest.mark.smoke`, `@pytest.mark.slow`, `@pytest.mark.integration`, `@pytest.mark.web`, `@pytest.mark.e2e`, `@pytest.mark.benchmark`, `@pytest.mark.property`, `@pytest.mark.gui`
- Coverage threshold: 65% (`fail_under` in pyproject.toml)

## CI

GitHub Actions on push/PR to main: lint, format check, mypy, tests (matrix: ubuntu, Python 3.11+3.12), the vendored audit-harness gate (verify + escape-scan), and benchmarks on main only. Security: bandit + pip-audit. Pre-commit hooks enforce ruff, trailing whitespace, no `.env` commits, no direct commits to main.

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

| Epic | Bead | Title | Phase | Status |
|------|------|-------|-------|--------|
| EPIC-CAD-01 | cad-uns | Capability Audit + Architecture Baseline | 1 | Done |
| EPIC-CAD-02 | cad-d9a | Core Contracts + Routing Foundation | 1 | Done |
| EPIC-CAD-03 | cad-wd2 | Selection + Markup Interpretation Foundation | 1 | Done |
| EPIC-CAD-04 | cad-grx | Region Q&A Vertical Slice | 2 | Done |
| EPIC-CAD-05 | cad-ccd | Repeated-Condition Detection | 2 | Done |
| EPIC-CAD-06 | cad-3e4 | Compare + Diff Service Hardening | 2 | Done |
| ARCH-REVIEW-01 | cad-sfw | Post-EPIC-06 Architecture Review | — | Done |
| EPIC-CAD-07 | cad-9ug | Structured Edit Planning | 3 | Done |
| EPIC-CAD-08 | cad-6zz | Preview + Apply Workflow | 3 | Done |
| EPIC-CAD-09 | cad-ady | Design Operations Workflow Pack | 4 | Done |
| EPIC-CAD-10 | cad-8p2 | Construction Drawing Workflow Pack | 4 | Done |
| EPIC-CAD-11 | cad-36p | Session Durability + Scale Readiness | 5 | Done |
| EPIC-CAD-12 | cad-m7d | Evaluation Harness + Quality Governance | 5 | Done |
| EPIC-CAD-13 | cad-dxf-agent-lk9 | Objective Intelligence | 6 | Done |
| EPIC-CAD-14 | cad-dxf-agent-bmw | Professional Precision Controls | 6 | Done |
| EPIC-CAD-15 | cad-dxf-agent-aqw | Document Persistence | 6 | Done |
| EPIC-CAD-16 | cad-dxf-agent-5ds | Drafting Vocabulary Foundation | 7 | Done |
| EPIC-CAD-17 | cad-dxf-agent-ofi | Entity Creation Pipeline | 7 | Done |
| EPIC-CAD-18 | cad-dxf-agent-omx | Scale + Entity Cap | 7 | Done |
| EPIC-CAD-19 | cad-dxf-agent-xz4 | Drawing Health Report | 8 | Done |
| EPIC-CAD-20 | cad-dxf-agent-50c | Intelligent Batch Operations | 8 | Done |
| EPIC-CAD-21 | cad-dxf-agent-ons | Compliance Validation Engine | 8 | Done |
| EPIC-CAD-22 | cad-dxf-agent-76v | Cross-Drawing Consistency Checker | 8 | Done |
| EPIC-CAD-23 | cad-dxf-agent-bqt | Automated Takeoff Engine | 8 | Done |
| EPIC-CAD-24 | cad-dxf-agent-a6b | Plain-English Drawing Summary | 8 | Done |
| EPIC-CAD-25 | cad-dxf-agent-owv | RFI Generator | 8 | Done |
| EPIC-CAD-26 | cad-dxf-agent-4xc | Revision Summary Report | 8 | Done |
| EPIC-CAD-27 | cad-dxf-agent-xvs | Session Undo/Redo + Snapshots | 8 | Done |
| EPIC-CAD-29 | cad-dxf-agent-9cd | Agent-Mode API v1 | 8 | Done |
| EPIC-CAD-30 | cad-dxf-agent-qvf | User Accounts, Workspaces & Persistent Work Progress | 9 | Done |
| EPIC-CAD-31 | cad-dxf-agent-ees | System Design Pattern Adoption | — | Phase 0+1 Done; Phase 2+ (Vertex Agent Engine) superseded by EPIC-CAD-32 |
| EPIC-CAD-32 | cad-dxf-agent-jvc | Bring-Your-Own-Provider LLM Backend (provider-agnostic loader; bundled Gemini/Vertex providers removed) | — | Done |

### EPIC-CAD-32 Bring-Your-Own-Provider LLM Backend

Pivoted the planner off any bundled LLM vendor onto a bring-your-own model.

- **`get_provider()` (`llm/planner.py`)** loads any `PlannerProvider` from a dotted import path — `CAD_LLM_PROVIDER=package.module:YourProvider` — imported and validated at startup; bad specs raise (no silent mock). Bare unknown names still fall back to mock. (#178, bead `cad-dxf-agent-jvc`)
- **Bundled Gemini/Vertex providers removed** — `gemini_provider`, `gemini_key_provider`, `proxy_client`, `vision_describer`, the Vertex `AgentProvider`, their settings/extras/tests, the `tests/live/` suite, and the `live-test` CI job (−4,225 lines). (#179, bead `cad-dxf-agent-udo`)
- **Kept (provider-agnostic):** `MockProvider`, `MockAgentProvider`, and the `ToolExecutor` + `tool_definitions` + `capability_registry` tool-use scaffolding — load-bearing for entity creation + the web backend, and reusable by a BYO provider for agent-style tool use.
- Docs (`README.md`, `.env.example`, `CLAUDE.md`) rewritten vendor-neutral: `mock` to try, bring-your-own for real use, no vendor named.

### EPIC-CAD-31 Review Outcome

> **Superseded (2026-06-14) by EPIC-CAD-32:** Phase 2+ targeted Vertex AI Agent Engine. The bundled Gemini/Vertex providers were removed (#179), so the Agent Engine path, the `CAD_AGENT_BACKEND=agent_engine` flag, and the "tools as Cloud Run endpoints" plan below no longer apply — real AI is now bring-your-own. Findings retained for historical reference.

A 12-specialist engineer review (ADK, security, database, performance, backend architecture, Python, cloud, DevOps, testing, architecture review, DX, observability) evaluated the EPIC-CAD-31 rollout plan. Key findings:

- **Decision:** Phase 0+1 shipped, Phase 2+ deferred until user growth demands it.
- **Critical finding:** Tools cannot run inside Agent Engine (ezdxf C library, R-tree, local file I/O). When ready, adopt the HTTP-Client FunctionTool pattern (tools as Cloud Run endpoints).
- **Pre-existing bugs fixed:** V1 API had zero rate limiting (now 60 req/min per IP), `CAD_WEB_DEV_MODE` parsing was inconsistent across auth/lifespan (now `is_dev_mode()` helper), `SessionManager.get_by_id()` bypassed ownership (now private `_get_by_id_internal()`).
- **Dead code removed:** `from __future__ import annotations` in tool_definitions (latent `get_type_hints()` bug), dead `Point2D` dataclass (name collision), dead `pname == "return"` guard, loop-body imports in agent_provider.
- **Foundation completed:** All 23 tools have typed function stubs with schema sync tests, `_hint_to_json_schema()` handles Literal/dataclass/list types, drift detection extended (6 checks), OTel metrics baseline added.
- **`CAD_AGENT_BACKEND` feature flag** exists (`cloud_run` default) but Agent Engine routing is not wired — just the config plumbing for future use.
- **Reference materials** for Phase 2 resumption preserved in `memory/reference_*.md`.

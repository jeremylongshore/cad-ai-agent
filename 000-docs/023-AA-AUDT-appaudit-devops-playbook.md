# cad-dxf-agent: Operator-Grade System Analysis

*For: DevOps Engineer*
*Generated: 2026-02-23*
*Version: 0.1.0 (commit 4411bfe)*

---

## 1. Executive Summary

### Business Purpose

**cad-dxf-agent** is a local-first desktop application for prompt-driven DXF layout editing, built for structural engineering and drafting professionals. Users describe edits in natural language ("Move the column east by 2 feet"), and the tool translates them into validated, deterministic operations on 2D DXF drawings. The original file is never modified—all changes are saved as new files.

The project is in **alpha status** (v0.1.0), with Phases 1-9 complete and Phase 10 (QA hardening and release) in progress. The client is a PhD researcher and iOS developer in Guadalajara, Mexico building tools for the AEC (Architecture, Engineering, Construction) industry. Core functionality works entirely offline—an LLM API is optional and used only for planning.

The technology foundation is Python 3.11+, ezdxf for DXF manipulation, Pydantic for validation, PySide6 for desktop GUI, and optional Vertex AI/Gemini for LLM-powered planning. A mock planner enables the full pipeline to work without any API key or network access.

**Key risks:** Real-world DXF files vary wildly in structure; V1 handles this by skipping unsupported entity types with warnings. The tool is local-first by design, meaning no cloud deployment or auto-updates—distribution requires installers.

### Operational Status Matrix

| Environment | Status | Uptime Target | Release Cadence |
|-------------|--------|---------------|-----------------|
| Local Dev | Stable | N/A | Continuous |
| CI (GitHub Actions) | Green | 99% | Per-PR |
| Live API Tests | WIF-authenticated | N/A | On push to main |
| Production Desktop | Not yet released | N/A | Manual releases |

### Technology Stack

| Category | Technology | Version | Purpose |
|----------|------------|---------|---------|
| Language | Python | 3.11-3.12 | Core runtime |
| DXF Library | ezdxf | >=1.3.0 | DXF read/write/manipulation |
| Validation | Pydantic | >=2.0 | Schema validation |
| HTTP Client | httpx | >=0.27 | API calls (proxy mode) |
| GUI | PySide6 | >=6.6 | Desktop window |
| Build | hatchling | latest | Python package build |
| Linting | ruff | >=0.5 | Lint + format |
| Type Check | mypy | >=1.10 | Static types |
| Testing | pytest | >=8.0 | Test framework |
| Security | bandit, pip-audit | latest | SAST + dependency audit |
| Tracing | OpenTelemetry | >=1.21 | Optional observability |
| LLM (optional) | Vertex AI / Gemini | gemini-2.5-flash | Planning provider |
| CI/CD | GitHub Actions | v6 actions | Lint, test, security, live tests |

---

## 2. System Architecture

### Architecture Diagram

```
┌─────────────────────────────────────────────────────────────────────────┐
│                           USER INTERFACE                                 │
│  ┌─────────────────────────────────────────────────────────────────┐    │
│  │                    PySide6 Desktop (MainWindow)                  │    │
│  │   • Open DXF/DWG/PDF          • Prompt Input                    │    │
│  │   • Layout Selector            • Plan & Preview                  │    │
│  │   • Per-Operation Checkboxes   • Apply & Save As                │    │
│  │   • Undo/Redo (Ctrl+Z/Y)       • Export (DXF/PNG/PDF/DWG)       │    │
│  └──────────────────────────────────┬──────────────────────────────┘    │
└─────────────────────────────────────┼───────────────────────────────────┘
                                      │
┌─────────────────────────────────────┼───────────────────────────────────┐
│                           PIPELINE CORE                                  │
│                                     ▼                                    │
│  ┌──────────────┐    ┌──────────────────────┐    ┌─────────────────┐    │
│  │  DXF Reader  │───▶│   DrawingContext     │───▶│  Entity Index   │    │
│  │  (ezdxf)     │    │   (Pydantic model)   │    │  (fast lookup)  │    │
│  └──────────────┘    └──────────────────────┘    └─────────────────┘    │
│         │                      │                          │              │
│         │                      ▼                          │              │
│         │            ┌──────────────────┐                 │              │
│         │            │  Semantic Model  │                 │              │
│         │            │  (context JSON)  │                 │              │
│         │            └────────┬─────────┘                 │              │
│         │                     │                           │              │
│         │                     ▼                           │              │
│         │   ┌─────────────────────────────────────────┐   │              │
│         │   │           LLM Planner Layer             │   │              │
│         │   │  ┌───────────┬────────────┬───────────┐ │   │              │
│         │   │  │  Mock     │  Gemini    │  Agent    │ │   │              │
│         │   │  │ Provider  │  Provider  │  Provider │ │   │              │
│         │   │  └───────────┴────────────┴───────────┘ │   │              │
│         │   │                     │                    │   │              │
│         │   │              ┌──────┴──────┐            │   │              │
│         │   │              │  ChangeSet  │            │   │              │
│         │   │              │  (ops JSON) │            │   │              │
│         │   └──────────────┴──────┬──────┴────────────┘   │              │
│         │                         │                        │              │
│         │                         ▼                        │              │
│         │                ┌─────────────────┐               │              │
│         │                │   Validator     │◀──────────────┘              │
│         │                │ (rules engine)  │                              │
│         │                └────────┬────────┘                              │
│         │                         │                                       │
│         │                         ▼                                       │
│         │                ┌─────────────────┐                              │
│         │                │  Preview Model  │                              │
│         │                │ (human summary) │                              │
│         │                └────────┬────────┘                              │
│         │                         │ (user approves)                       │
│         │                         ▼                                       │
│         │                ┌─────────────────┐                              │
│         │                │   Edit Engine   │                              │
│         │                │  (apply ops)    │                              │
│         │                └────────┬────────┘                              │
│         │                         │                                       │
│         │                         ▼                                       │
│         │                ┌─────────────────┐                              │
│         │                │ Revision Notes  │                              │
│         │                │ (AI_REV_NOTES)  │                              │
│         │                └────────┬────────┘                              │
│         │                         │                                       │
│         │                         ▼                                       │
│         │                ┌─────────────────┐                              │
│         └───────────────▶│   DXF Writer    │                              │
│                          │  (save-as new)  │                              │
│                          └─────────────────┘                              │
└─────────────────────────────────────────────────────────────────────────┘

┌─────────────────────────────────────────────────────────────────────────┐
│                         SECURITY BOUNDARIES                              │
│  • Protected layers: TITLE, TITLEBLOCK, SEAL, REVISION (configurable)   │
│  • LLM never touches raw DXF - only structured JSON operations          │
│  • Original file is read-only; all saves are new files                  │
│  • API keys loaded from env only, never logged                          │
└─────────────────────────────────────────────────────────────────────────┘
```

### Data Flow

1. **Load**: User opens DXF file → `dxf_reader.load_dxf()` → `DrawingContext` (Pydantic)
2. **Index**: `EntityIndex` builds fast lookup tables (handle, layer, type, text)
3. **Summarize**: `semantic_model.build_planner_context()` → JSON context for LLM
4. **Plan**: User prompt → `planner.run_planner()` → `ChangeSet` (structured ops)
5. **Validate**: `validators.validate_changeset()` → blockers/warnings
6. **Preview**: `PreviewModel` → human-readable summary
7. **Apply**: User approves → `EditEngine.apply_changeset()` → modified ezdxf doc
8. **Notes**: `revision_notes.insert_revision_note()` → deterministic note on AI_REV_NOTES
9. **Save**: `EditEngine.save()` → new DXF file (original untouched)

### Key Architectural Rules

| Rule | Rationale |
|------|-----------|
| LLM returns structured ops only | Prevents hallucinated DXF corruption |
| All ops validated before apply | Protected layers enforced, bad params caught |
| Save-as workflow | Original file always recoverable |
| Deterministic revision notes | Never freeform LLM output in drawing |
| Mock provider works offline | Full pipeline testable without API |

---

## 3. Directory Analysis

### Project Structure

```
cad-dxf-agent/                    # Repository root
├── .beads/                       # Beads task tracking state
├── .github/
│   ├── ISSUE_TEMPLATE/           # Bug, feature, CAD parser, planner targeting
│   ├── workflows/
│   │   ├── ci.yml                # Lint, typecheck, test (matrix), live API tests
│   │   ├── security.yml          # Bandit, pip-audit, dependency review
│   │   └── release-dryrun.yml    # Build verification on tags
│   ├── dependabot.yml            # Weekly pip updates
│   └── PULL_REQUEST_TEMPLATE.md
├── 000-docs/                     # Flat, sequenced documentation (23 docs)
│   ├── 000-INDEX.md              # Category + chronological index
│   ├── 001-DR-GUID-agent-instructions.md
│   ├── 002-TQ-SECU-security-policy.md
│   ├── 004-007 (ADRs)            # Architecture decisions
│   ├── 008-PP-PROD-prd-addendum.md
│   ├── 012-PM-PLAN-v1-10-phase-roadmap.md
│   └── ... (specs, AARs, task plans)
├── scripts/
│   ├── smoke_test.py             # Standalone E2E test (no API key)
│   └── build.py                  # PyInstaller packaging
├── src/cad_dxf_agent/            # Main package (39 files, 4385 LOC)
│   ├── app.py                    # Entry point (PySide6 QApplication)
│   ├── settings.py               # Env var configuration
│   ├── otel.py                   # OpenTelemetry bootstrap
│   ├── core/                     # DXF processing modules
│   │   ├── dxf_reader.py         # Load DXF → DrawingContext
│   │   ├── dxf_writer.py         # Save-as new DXF
│   │   ├── entity_index.py       # Fast entity lookups
│   │   ├── semantic_model.py     # Build planner context
│   │   ├── context_builder.py    # Progressive context disclosure
│   │   ├── selectors.py          # Deterministic target resolution
│   │   ├── validators.py         # Rule-based validation
│   │   ├── edit_engine.py        # Apply operations
│   │   ├── edit_history.py       # Undo/redo stack
│   │   ├── preview_model.py      # Human-readable preview
│   │   ├── revision_notes.py     # AI_REV_NOTES insertion
│   │   ├── converter.py          # DWG/PDF to DXF conversion
│   │   └── renderer.py           # PNG/PDF export
│   ├── llm/                      # LLM planner layer
│   │   ├── planner.py            # Provider orchestrator
│   │   ├── providers.py          # ABC for providers
│   │   ├── mock_provider.py      # Offline keyword-based planner
│   │   ├── gemini_provider.py    # Vertex AI Gemini one-shot
│   │   ├── agent_provider.py     # Tool-use agent with Gemini
│   │   ├── proxy_client.py       # Cloud Run proxy client
│   │   ├── vision_describer.py   # Gemini vision for redlines
│   │   ├── response_parser.py    # JSON → ChangeSet
│   │   ├── prompt_templates.py   # System/user prompts
│   │   └── tool_definitions.py   # Agent tool schemas
│   ├── models/                   # Pydantic schemas
│   │   ├── cad_schema.py         # EntityRef, DrawingContext
│   │   ├── ops_schema.py         # EditOperation, ChangeSet
│   │   ├── config_schema.py      # RuleConfig, RevisionNoteConfig
│   │   └── changes_schema.py     # ValidationResult
│   ├── ui/
│   │   └── main_window.py        # PySide6 desktop shell (579 lines)
│   └── api/
│       └── local_api.py          # Local HTTP API (scaffolded)
├── tests/                        # 297 tests total
│   ├── conftest.py               # Shared fixtures
│   ├── helpers/
│   │   ├── dxf_factory.py        # Programmatic DXF builders
│   │   ├── changeset_factory.py  # ChangeSet builders
│   │   └── scripted_provider.py  # Fake-backend for agent loop
│   ├── fixtures/
│   │   └── trajectories/         # 5 golden trajectory JSON files
│   ├── unit/                     # ~282 unit tests
│   ├── integration/              # 15 integration tests
│   ├── smoke/                    # E2E smoke tests
│   └── live/                     # Gemini API tests (WIF auth)
├── .env.example                  # Template for local env vars
├── .pre-commit-config.yaml       # Ruff, hooks, no .env commits
├── pyproject.toml                # Build config, deps, tool settings
├── Makefile                      # Common commands
├── CLAUDE.md                     # Agent instructions
├── README.md                     # User-facing docs
├── CHANGELOG.md                  # Keep a Changelog format
├── CONTRIBUTING.md               # Contributor guide
├── LICENSE                       # MIT
└── CODEOWNERS                    # GitHub code owners
```

### Key Directories

**`src/cad_dxf_agent/core/`** — DXF processing pipeline
- Entry points: `dxf_reader.load_dxf()`, `EditEngine.apply_changeset()`
- All DXF manipulation via ezdxf library
- Validator enforces protected layers before any edit

**`src/cad_dxf_agent/llm/`** — LLM planner layer
- `planner.get_provider()` selects backend: mock, gemini, agent, proxy
- Mock provider responds to keywords (move, delete, text, rename)
- All providers return `ChangeSet` with typed `EditOperation` objects

**`tests/`** — Comprehensive test suite
- Unit: schemas, validators, reader, writer, engine, preview, settings
- Integration: full pipeline, undo/redo, agent loop with scripted provider
- Smoke: E2E pipeline with mock planner
- Live: Gemini API tests (WIF-authenticated in CI)
- Helpers: DXF factory, ChangeSet factory, golden trajectories

**`000-docs/`** — Flat documentation filing
- Category codes: AT (Architecture), PP (Product), PM (Project Mgmt), etc.
- Type codes: ADEC (Decision), ARCH (Architecture), SPEC (Specification), etc.
- See `000-INDEX.md` for complete index

---

## 4. Operational Reference

### Deployment Workflows

#### Local Development

**Prerequisites:**
- Python 3.11 or 3.12
- pip
- Git
- (Optional) PySide6 for GUI: requires display server

**Setup:**
```bash
# Clone
git clone https://github.com/jeremylongshore/cad-dxf-agent.git
cd cad-dxf-agent

# Create virtual environment
python -m venv .venv
source .venv/bin/activate  # Windows: .venv\Scripts\activate

# Install editable with dev deps
pip install -e ".[dev]"

# Install pre-commit hooks
pre-commit install
```

**Verification:**
```bash
# Run all quality checks
make check

# Or individually:
make lint          # ruff check
make format        # ruff format
make typecheck     # mypy
make test          # pytest
make smoke         # scripts/smoke_test.py
make security      # bandit + pip-audit
```

#### CI/CD Pipeline

**Trigger:** Push to main, PRs to main

**Jobs:**
1. **lint** (ubuntu-latest, Python 3.12)
   - `pip install -e ".[dev]"`
   - `ruff check src/ tests/`
   - `ruff format --check src/ tests/`

2. **typecheck** (ubuntu-latest, Python 3.12)
   - `mypy src/`

3. **test** (matrix: ubuntu+windows × Python 3.11+3.12)
   - `pytest --cov=cad_dxf_agent --cov-report=term-missing -v`
   - Upload coverage artifact on ubuntu/3.12

4. **live-test** (ubuntu-latest, only on push to main)
   - WIF authentication to GCP project `cad-dxf-agent`
   - `pytest tests/live/ -v -m live_api -s`
   - Tests real Gemini API

**Security Workflow:**
- **bandit**: SAST scan on `src/`
- **pip-audit**: Dependency vulnerability check
- **dependency-review**: PR-only, GitHub advisory check
- Runs on push, PR, and weekly (Monday 6 AM UTC)

#### Release Process

**Current:** Manual tagging + dry-run workflow

1. Update `CHANGELOG.md` with release notes
2. Bump version in `pyproject.toml`
3. Tag: `git tag v0.1.0`
4. Push tag: `git push origin v0.1.0`
5. `release-dryrun.yml` runs:
   - Build sdist + wheel
   - Verify import: `python -c "import cad_dxf_agent"`
   - Upload artifacts

**Future:** PyPI publish, Windows installer via PyInstaller

### Monitoring & Alerting

**Current State:** Optional OpenTelemetry tracing, no external monitoring.

**OpenTelemetry Spans:**
| Span | Attributes |
|------|------------|
| `cad.load_dxf` | file.name, entities.count, layers.count |
| `cad.build_context` | entities.count |
| `cad.run_planner` | mode, ops.count |
| `cad.validate` | ops.count, validation.valid, validation.blockers |
| `cad.apply_changeset` | ops.count, ops.success_count |
| `cad.save` | save.output_basename |
| `cad.revision_note` | revision.layer |

**Enable tracing:**
```bash
# Console exporter
OTEL_ENABLED=1 python scripts/smoke_test.py

# OTLP collector (Jaeger, Grafana Tempo)
OTEL_ENABLED=1 OTEL_EXPORTER=otlp OTEL_EXPORTER_OTLP_ENDPOINT=http://localhost:4317 python scripts/smoke_test.py
```

**Privacy:** No file paths, drawing text, or API keys in span attributes.

### Incident Response

| Severity | Definition | Response | Playbook |
|----------|------------|----------|----------|
| P0 | Data corruption, security breach | Immediate | [See Security Policy](#security--access) |
| P1 | CI failures on main | 1 hour | Revert or fix forward |
| P2 | Test flakiness, minor bugs | 1 day | Triage and fix |
| P3 | Documentation gaps | 1 week | Update docs |

---

## 5. Security & Access

### Security Design Principles

1. **Local-first**: DXF processing happens entirely on user's machine
2. **No raw DXF by LLM**: LLM returns structured JSON ops only
3. **Protected layers**: TITLE, TITLEBLOCK, SEAL, REVISION blocked by default
4. **Save-as workflow**: Original files never overwritten
5. **No hardcoded secrets**: API keys from environment only
6. **Safe logging**: Keys never logged, no sensitive data in OTel spans

### IAM

| Role | Purpose | Permissions |
|------|---------|-------------|
| Developer | Code changes | Push to feature branches, create PRs |
| Maintainer | Merge, release | Push to main, create tags |
| CI Service Account | WIF-authenticated | Vertex AI API access (live tests) |

**GCP Setup (Live Tests):**
- Project: `cad-dxf-agent`
- WIF Provider: Configured in GitHub vars
- Service Account: Vertex AI User role

### Secrets Management

**Local:**
- `.env` file (gitignored)
- Copy from `.env.example`
- Never commit `.env` (pre-commit hook blocks)

**CI:**
- GitHub Actions vars: `WIF_PROVIDER`, `WIF_SERVICE_ACCOUNT`, `GCP_PROJECT_ID`
- No stored secrets—WIF provides tokenless auth

**Environment Variables:**
| Variable | Default | Purpose |
|----------|---------|---------|
| `CAD_LLM_PROVIDER` | `mock` | Planner backend |
| `CAD_PROTECTED_LAYERS` | `TITLE,TITLEBLOCK,SEAL,REVISION` | Protected layers |
| `CAD_REVISION_NOTES_ENABLED` | `true` | Insert AI notes |
| `CAD_REVISION_NOTES_LAYER` | `AI_REV_NOTES` | Notes layer |
| `CAD_GCP_PROJECT` | (unset) | GCP project for Vertex AI |
| `CAD_GCP_LOCATION` | `us-central1` | Vertex AI region |
| `CAD_GEMINI_MODEL` | `gemini-2.5-flash` | Gemini model |
| `OTEL_ENABLED` | (unset) | Enable tracing |

### Vulnerability Reporting

1. Do NOT open public GitHub issue
2. Email maintainer directly with:
   - Description, reproduction steps, potential impact
3. Allow 72 hours for initial response

---

## 6. Cost & Performance

### Monthly Costs

**Current (Development):**
- Compute: $0 (local development)
- Storage: $0 (no cloud storage)
- CI: Free tier (GitHub Actions public repo)
- Vertex AI: Pay-per-use for live tests (~$5/month)

**Production Estimate (Desktop Distribution):**
- Vertex AI (optional): $0.0001/1k input tokens, $0.0004/1k output tokens
- Typical prompt: ~$0.001 per edit
- No hosting costs (desktop app)

### Performance Baseline

**Pipeline Benchmarks (local, mock provider):**
| Stage | Time |
|-------|------|
| Load DXF (200 entities) | ~100ms |
| Build context | ~10ms |
| Mock planner | ~5ms |
| Validate | ~5ms |
| Apply changeset (1 op) | ~20ms |
| Save DXF | ~50ms |
| **Total E2E** | **~200ms** |

**Test Suite:**
- 297 tests in ~27s
- Coverage: 68%
- fail_under: 65%

**CI:**
- Full workflow: ~5 minutes
- Live tests: +2 minutes (Gemini API)

---

## 7. Current State Assessment

### What's Working

- **Complete V1 pipeline**: load → plan → validate → preview → apply → save
- **Comprehensive test suite**: 297 tests, 68% coverage, CI green
- **Mock provider**: Full pipeline works offline without API key
- **Protected layer enforcement**: Validator blocks edits to TITLE, TITLEBLOCK, etc.
- **Deterministic revision notes**: Never freeform LLM output in drawings
- **Undo/redo**: In-memory edit history with Ctrl+Z/Y
- **Multi-format support**: DXF, DWG, PDF input (with conversion)
- **Export options**: DXF, PNG, PDF, DWG output
- **WIF-authenticated live tests**: CI tests real Gemini API without secrets
- **Well-documented**: 23 docs covering architecture, specs, AARs

### Areas Needing Attention

**Technical Debt:**
- UI module (main_window.py) has 0% coverage (requires display server)
- Local HTTP API scaffolded but not wired to pipeline
- Real LLM providers not fully tested in CI (only live tests on push to main)

**Documentation Gaps:**
- No deployment/distribution guide
- No troubleshooting playbook
- No operator runbook (this document fills that gap)

**Infrastructure:**
- No Windows installer published
- No PyPI package published
- No auto-update mechanism

### Immediate Priorities

| # | Priority | Issue | Impact | Owner |
|---|----------|-------|--------|-------|
| 1 | HIGH | Phase 10: QA hardening and V1 release | Blocks delivery | Dev |
| 2 | MEDIUM | Publish Windows installer | User distribution | DevOps |
| 3 | MEDIUM | PyPI package | pip install | DevOps |
| 4 | LOW | UI test coverage | Quality | Dev |
| 5 | LOW | Local API wiring | Scripting use cases | Dev |

---

## 8. Quick Reference

### Command Map

| Capability | Command | Notes |
|------------|---------|-------|
| Install (editable) | `pip install -e ".[dev]"` | Includes dev tools |
| Install hooks | `pre-commit install` | Required after clone |
| Run all checks | `make check` | lint + format + typecheck + test + smoke |
| Run tests | `make test` | pytest -v |
| Run with coverage | `make test-cov` | 65% threshold |
| Run smoke test | `make smoke` | No API key needed |
| Run live tests | `make test-live` | Requires GCP auth |
| Type check | `make typecheck` | mypy src/ |
| Lint | `make lint` | ruff check |
| Format | `make format` | ruff format |
| Security scan | `make security` | bandit + pip-audit |
| Launch GUI | `make run` | Requires PySide6 |
| Build installer | `make build` | PyInstaller |
| Clean artifacts | `make clean` | Remove dist/, .coverage, etc. |

### Critical Files

| File | Purpose |
|------|---------|
| `pyproject.toml` | Build config, dependencies, tool settings |
| `Makefile` | Common commands |
| `.env.example` | Environment variable template |
| `.pre-commit-config.yaml` | Pre-commit hooks config |
| `src/cad_dxf_agent/settings.py` | Runtime configuration |
| `src/cad_dxf_agent/app.py` | Application entry point |
| `scripts/smoke_test.py` | Standalone E2E verification |
| `tests/conftest.py` | Shared test fixtures |

### Critical URLs

| Resource | URL |
|----------|-----|
| Repository | https://github.com/jeremylongshore/cad-dxf-agent |
| CI Workflows | https://github.com/jeremylongshore/cad-dxf-agent/actions |
| GCP Console | https://console.cloud.google.com/home/dashboard?project=cad-dxf-agent |
| Vertex AI | https://console.cloud.google.com/vertex-ai?project=cad-dxf-agent |

### First-Week Checklist

- [ ] Clone repo and verify `pip install -e ".[dev]"` succeeds
- [ ] Run `make check` — all checks should pass
- [ ] Run `make smoke` — smoke test exits 0
- [ ] Review `README.md` and `000-docs/000-INDEX.md`
- [ ] Read ADRs: `000-docs/004-006` (architecture decisions)
- [ ] Read V1 Blueprint: `000-docs/007-AT-ARCH-v1-blueprint.md`
- [ ] Review CI workflows in `.github/workflows/`
- [ ] (Optional) Launch GUI with `make run` if display server available
- [ ] (Optional) Set up GCP auth for live tests: `gcloud auth application-default login`

---

## 9. Recommendations Roadmap

### Week 1 — Stabilization

**Goals:**
- [ ] Complete Phase 10 QA hardening
- [ ] Tag v0.1.0 release
- [ ] Verify all 10 acceptance criteria from PRD

**Measurable Outcomes:**
- `make check` passes
- `git tag v0.1.0` created
- CHANGELOG.md updated

### Month 1 — Distribution

**Goals:**
- [ ] Publish Windows installer (.exe)
- [ ] Create PyPI package
- [ ] Write installation documentation
- [ ] Set up Dependabot alerts monitoring

**Measurable Outcomes:**
- Windows installer downloadable from GitHub Releases
- `pip install cad-dxf-agent` works
- README includes installation instructions for Windows/Linux

### Quarter 1 — Strategic

**Goals:**
- [ ] V2 features: layout/paper space editing, dimension regeneration
- [ ] Production monitoring (error tracking, usage analytics)
- [ ] User feedback loop established
- [ ] Consider macOS support

**Measurable Outcomes:**
- V2 release with paper space support
- Error tracking dashboard operational
- User feedback channel active

---

## Appendices

### A. Glossary

| Term | Definition |
|------|------------|
| DXF | Drawing Exchange Format — open CAD file format |
| DWG | AutoCAD native format (proprietary) |
| ezdxf | Python library for DXF manipulation |
| Entity | DXF object (LINE, TEXT, INSERT, etc.) |
| Handle | Unique hex identifier for DXF entity |
| Layer | DXF grouping mechanism (like Photoshop layers) |
| Block | Reusable DXF symbol definition |
| INSERT | Block reference (instance of a block) |
| Model Space | Primary DXF drawing area |
| Paper Space | Layout/print sheets in DXF |
| ChangeSet | Collection of edit operations from one prompt |
| Protected Layer | Layer that cannot be edited (TITLE, etc.) |
| Mock Provider | Offline planner using keyword matching |
| WIF | Workload Identity Federation (GCP tokenless auth) |

### B. Entity Type Support

| Type | Status | Read | Edit | Notes |
|------|--------|------|------|-------|
| LINE | V1 | Yes | Move/Delete | Simple line segment |
| LWPOLYLINE | V1 | Yes | Move/Delete | Lightweight polyline |
| TEXT | V1 | Yes | Move/Edit/Delete | Single-line text |
| MTEXT | V1 | Yes | Move/Edit/Delete | Multi-line text |
| INSERT | V1 | Yes | Move/Delete | Block reference |
| CIRCLE | V2 | Yes | Move/Delete | — |
| ARC | V2 | Yes | Move/Delete | — |
| DIMENSION | V2 | Yes | Move/Delete | No regeneration |
| HATCH | V2 | Yes | Move/Delete | — |
| SPLINE | V2 | Yes | Move/Delete | — |
| POLYLINE | V2 | Yes | Move/Delete | Legacy format |
| ELLIPSE | V2 | Yes | Move/Delete | — |
| MLEADER | V2 | Yes | Move/Delete | Multi-leader |
| SOLID | V2 | Yes | Move/Delete | Filled triangle |
| LEADER | V2 | Yes | Move/Delete | Arrow + text |

### C. Troubleshooting

**Problem:** `ModuleNotFoundError: No module named 'ezdxf'`
**Solution:** Activate virtual environment: `source .venv/bin/activate`

**Problem:** Tests fail with `ImportError: libxcb.so.1`
**Solution:** PySide6 requires display server. Run headless tests with `pytest -v -m "not gui"`

**Problem:** Live tests fail with `PermissionDenied`
**Solution:** Run `gcloud auth application-default login` and set `CAD_GCP_PROJECT=cad-dxf-agent`

**Problem:** Pre-commit hook rejects .env file
**Solution:** Don't commit .env files. Use `.env.example` as template.

**Problem:** `make run` shows blank window
**Solution:** Ensure PySide6 installed: `pip install -e ".[gui]"`

### D. Reference Links

- [ezdxf Documentation](https://ezdxf.readthedocs.io/)
- [DXF Reference (Autodesk)](https://help.autodesk.com/view/OARX/2024/ENU/?guid=GUID-235B22E0-A567-4CF6-92D3-38A2306D73F3)
- [Pydantic V2 Documentation](https://docs.pydantic.dev/latest/)
- [PySide6 Documentation](https://doc.qt.io/qtforpython-6/)
- [Vertex AI Gemini](https://cloud.google.com/vertex-ai/docs/generative-ai/model-reference/gemini)
- [OpenTelemetry Python](https://opentelemetry.io/docs/languages/python/)
- [GitHub Actions](https://docs.github.com/en/actions)

### E. Open Questions

1. **Distribution strategy**: GitHub Releases only, or also PyPI/Homebrew/Chocolatey?
2. **Telemetry**: Should we add opt-in usage analytics?
3. **macOS support**: Worth the testing effort?
4. **Local LLM**: Ollama/llama.cpp integration priority?

---

*Document generated by appaudit skill. Last updated: 2026-02-23*

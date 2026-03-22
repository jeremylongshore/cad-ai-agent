# IntentCAD (cad-dxf-agent): Operator-Grade System Analysis
*Generated: 2026-03-21*
*Version: v0.10.1 (30 epics shipped)*

---

## 1. This System in 5 Minutes

IntentCAD is a Drawing Intelligence Platform that turns natural-language prompts into structured operations on 2D architectural drawings. Users upload DXF, PDF, or DWG files, type what they want ("move the column east by 2 feet", "check ADA compliance", "run a quantity takeoff"), and the platform figures out what kind of request it is, routes it to the right pipeline, and delivers results. For edits, the LLM generates structured JSON operations (never raw DXF bytes), which are validated against protected-layer rules before a deterministic edit engine applies them. Original files are never modified — every save produces a new file.

The system ships as both a PySide6 desktop app (Windows/Linux) and a React + FastAPI web app on Google Cloud. The web version is the primary deployment: Firebase Hosting serves the React SPA, Cloud Run hosts the FastAPI backend with 8GB RAM and 4 CPUs, and Gemini (via Vertex AI) handles LLM planning. Authentication is Firebase Auth (Google Sign-In), with user profiles and tenant isolation stored in Firestore. Document persistence uses GCS with a 2-hour session TTL for ephemeral work and permanent storage for saved documents.

The architecture's defining characteristic is that the **LLM never touches DXF directly**. This is an intentional risk mitigation: LLMs can hallucinate, and letting them edit binary files directly would be a liability nightmare for AEC professionals. Instead, the LLM returns one of 13 typed operation kinds (`move_entity`, `edit_text`, `delete_entity`, `add_block`, etc.), each validated against a Pydantic schema and a protected-layer ruleset before execution. If validation fails, the entire changeset is rejected — no partial edits.

Current state: 30 epics shipped across 9 phases. The test suite has 4,556 tests across 10 tiers (unit, integration, web, eval, live API, E2E, benchmark, GUI, property, smoke). CI runs on GitHub Actions with WIF-based GCP auth for live API tests. Production deploys are automatic on merge to main. The biggest operational risk is single-region deployment (us-central1) and the external dependency on ODA File Converter for DWG support — if ODA isn't installed, DWG uploads return HTTP 422.

---

## 2. Executive Summary

### What It Does

IntentCAD is a multi-capability platform for AEC (Architecture, Engineering, Construction) professionals who work with 2D drawings. It handles nine distinct workflows: **edit** (move, rotate, copy, scale, mirror, delete entities; add lines, polylines, circles, arcs, text, blocks), **compliance** (ADA/IBC/custom rule validation), **health report** (drawing quality metrics), **quantity takeoff** (count extraction), **summary** (plain-English description), **RFI generation** (detect ambiguities), **zone detection** (closed-loop room detection with area calculation), **revision comparison** (diff two DXF versions), and **agent mode** (iterative multi-turn tool-use for complex requests).

The platform is fully implemented and production-deployed. The web app runs at `cad-dxf-agent.web.app` with Firebase Auth (Google Sign-In). Users upload drawings, describe what they need, and the platform classifies intent on two axes (RequestClass × ObjectiveTag), selects the appropriate stage pipeline, and executes. For edit requests, the flow is: prompt → objective classification → strategy selection → LLM planning → validation → preview → user approval → edit engine → save-as DXF + revision notes. For analysis requests, the flow runs deterministic extractors without the edit stages.

The technical foundation is Python 3.11/3.12 with ezdxf for DXF manipulation, Pydantic v2 for schema validation, FastAPI + Uvicorn for the web backend, React 18 + Vite for the frontend, and Gemini 2.5 Flash via Vertex AI for LLM planning. The desktop app uses PySide6. OpenTelemetry instrumentation (optional) sends traces to console, OTLP, or GCP Cloud Trace.

Key risks: (1) single-region deployment creates a SPOF, (2) ODA File Converter is a proprietary external dependency, (3) no staging environment — deploys go straight to production, (4) Firestore/GCS costs could spike with user growth.

### Operational Status

| Environment | Status | Uptime Target | Release Cadence | Last Deploy |
|-------------|--------|---------------|-----------------|-------------|
| Production (Web) | Active | Best-effort (Cloud Run default SLA) | Merge-to-main auto-deploy | Continuous |
| Desktop | Builds available | N/A (local) | Tag-triggered (v* tags) | v0.10.1 |
| CI | Green (main) | N/A | Every push/PR | Continuous |
| Staging | None | N/A | N/A | N/A |

### Technology Stack

| Category | Technology | Version | Purpose |
|----------|------------|---------|---------|
| Language | Python | 3.11 / 3.12 | Core pipeline, backend |
| DXF Engine | ezdxf | >=1.3.0 | DXF read/write/entity manipulation |
| Data Models | Pydantic | >=2.0 | Schema validation, 30 model files |
| LLM | Gemini (Vertex AI) | gemini-2.5-flash | Edit planning, vision, agent tool-use |
| Backend | FastAPI + Uvicorn | latest | REST API (3,033 lines in main.py) |
| Frontend | React + Vite | 18.x / 6.x | SPA (22 components) |
| DXF Viewer | dxf-viewer + Three.js | 1.0.46 / 0.183.x | WebGL drawing preview |
| Auth | Firebase Authentication | v11 | Google Sign-In |
| Hosting | Firebase Hosting | — | Static SPA delivery |
| Compute | Cloud Run | — | Containerized backend (8Gi/4CPU) |
| Storage | GCS + Firestore | — | Documents, profiles, tenants |
| Registry | Artifact Registry | — | Docker images (us-central1) |
| Tracing | OpenTelemetry → Cloud Trace | >=1.21 | Pipeline span instrumentation |
| Desktop UI | PySide6 | >=6.6 | Qt-based desktop shell |
| CI/CD | GitHub Actions | — | Lint, test, deploy (WIF auth) |
| Linting | Ruff | >=0.5 | Lint + format |
| Type Check | Mypy | >=1.10 | Static type analysis |
| Security | Bandit + pip-audit | — | SAST + dependency audit |
| Build | Hatchling + PyInstaller | — | Package + desktop executable |
| Spatial Index | Rtree + libspatialindex | >=1.0 | R-tree for nearest-neighbor queries |
| PDF Conversion | PyMuPDF | >=1.24 | PDF → DXF fallback |
| DWG Conversion | ODA File Converter | 27.1 | DWG → DXF (optional, proprietary) |

---

## 3. Architecture

### Stack (Detailed)

| Layer | Technology | Version | Purpose | Why This |
|-------|------------|---------|---------|----------|
| DXF I/O | ezdxf | 1.3+ | Read/write DXF, entity manipulation | Only mature Python DXF library; MIT licensed |
| Validation | Pydantic v2 | 2.0+ | Schema validation, serialization | Type safety, performance (Rust core) |
| Spatial Index | Rtree | 1.0+ | Nearest-neighbor, find-in-radius | R-tree is standard for 2D spatial queries |
| LLM | Gemini 2.5 Flash | latest | Planning, vision, tool-use | Best latency/quality ratio for tool-use |
| Backend | FastAPI | latest | REST API | Async, OpenAPI generation, Pydantic native |
| Frontend | React + Vite | 18/6 | SPA | Standard choice, fast dev experience |
| Auth | Firebase Auth | v11 | Google Sign-In | Zero-friction for users, handles OAuth |
| Storage | GCS + Firestore | — | Binary blobs + metadata | GCP-native, consistent latency |
| Compute | Cloud Run | — | Containerized backend | Auto-scaling, pay-per-use |
| Tracing | OpenTelemetry | 1.21+ | Observability | Vendor-neutral, GCP Trace export |
| Desktop | PySide6 | 6.6+ | Qt GUI | Cross-platform, mature |

### System Diagram

```
                         ┌─────────────────────────┐
                         │   Firebase Hosting       │
                         │   (React SPA)            │
                         │   cad-dxf-agent.web.app  │
                         └────────┬────────────────┘
                                  │ /api/* rewrite
                                  ▼
                         ┌─────────────────────────┐
                         │   Cloud Run              │
                         │   cad-dxf-web            │
                         │   FastAPI (8Gi/4CPU)     │
                         │   us-central1            │
                         └────────┬────────────────┘
                                  │
          ┌───────────────────────┼───────────────────────┐
          ▼                       ▼                       ▼
┌──────────────────┐  ┌──────────────────┐  ┌──────────────────┐
│  Pipeline Core   │  │   Vertex AI      │  │  Firebase/GCP    │
│  (43 core mods,  │  │   Gemini API     │  │  Auth, Firestore │
│   24 llm mods,   │  │   (WIF auth)     │  │  GCS (documents) │
│   30 models)     │  │                  │  │  Cloud Trace     │
└──────────────────┘  └──────────────────┘  └──────────────────┘
```

### The Critical Path

**Edit Request Flow** (most important path):

1. **Upload** → User uploads DXF via `/api/upload` → Session created with 2h TTL → DXF bytes stored in `/tmp/cad-sessions/{session_id}/`
2. **Context Build** → `dxf_reader.load()` parses DXF → `DrawingContext` (Pydantic model) with `EntityRef` list → `semantic_model.build_enriched_context()` adds family detection, primitive extraction
3. **Classification** → User types prompt → `ObjectiveClassifier` classifies on 2 axes (RequestClass × ObjectiveTag) → Returns `ObjectiveClassification`
4. **Strategy Selection** → `StrategyRegistry.get_pipeline()` maps classification to `StagePipelineDefinition`
5. **LLM Planning** → `GeminiProvider.plan()` sends prompt + context to Gemini → Returns `ChangeSet` with `EditOperation` list
6. **Validation** → `validators.validate()` checks each op against `RuleConfig` → Rejects ops targeting protected layers
7. **Preview** → `preview_builder.build()` generates human-readable descriptions → User reviews and approves
8. **Apply** → `edit_engine.apply()` executes ops on ezdxf document → Deterministic, no LLM involvement
9. **Save** → `dxf_writer.save()` writes to new file path → Original untouched
10. **Revision Notes** → `revision_notes.add()` inserts deterministic note on AI_REV_NOTES layer

**Failure Points**:
- Step 3: Classification fails → Falls back to `general` objective
- Step 5: Gemini timeout/error → Returns empty ChangeSet
- Step 6: Validation rejects → HTTP 400 with blockers
- Step 8: ezdxf error → Operation logged, skipped

### Dependency Graph

```
┌─────────────────────────────────────────────────────────────┐
│                       Web Frontend                          │
│  (React) → depends on Firebase Auth, API backend            │
└────────────────────────────┬────────────────────────────────┘
                             │
┌────────────────────────────▼────────────────────────────────┐
│                       FastAPI Backend                        │
│  main.py + api_v1.py + auth.py + session.py                 │
│  depends on: Firestore, GCS, Pipeline Core, Vertex AI       │
└────────────────────────────┬────────────────────────────────┘
                             │
┌────────────────────────────▼────────────────────────────────┐
│                       Pipeline Core                          │
│  43 modules in core/, 24 modules in llm/, 30 models         │
│  depends on: ezdxf, Pydantic, Rtree, numpy, httpx           │
└────────────────────────────┬────────────────────────────────┘
                             │
┌────────────────────────────▼────────────────────────────────┐
│                       External Services                      │
│  Vertex AI (Gemini), Firebase Auth, Firestore, GCS          │
│  Optional: ODA File Converter (DWG), Cloud Trace            │
└─────────────────────────────────────────────────────────────┘
```

**Build Order**: ezdxf → Pipeline Core → FastAPI Backend → React Frontend

**Dependency Unavailability**:
- Gemini down → Edit requests fail, analysis requests still work (deterministic)
- Firestore down → Auth fails, profile/tenant creation fails
- GCS down → Document persistence fails, upload/download fails
- ODA missing → DWG uploads return HTTP 422, DXF/PDF still work

---

## 4. Design Decisions & Tradeoffs

### Decision Log

#### LLM Returns JSON Operations, Not DXF Edits
- **Chosen**: LLM outputs structured `EditOperation` objects with typed parameters
- **Over**: LLM directly editing DXF bytes or generating ezdxf code
- **Because**: Liability risk. AEC drawings are legal documents. LLM hallucinations editing raw files = undetectable corruption. Structured ops can be validated, logged, reversed.
- **Cost**: More pipeline complexity; multi-turn agent loop needed for complex edits
- **Revisit when**: LLMs achieve provably deterministic output (unlikely near-term)

#### Protected Layers as Hard Block
- **Chosen**: Validator rejects ANY operation touching TITLE, TITLEBLOCK, SEAL, REVISION layers
- **Over**: Soft warning with user override
- **Because**: These layers contain legal seals, revision tables, title blocks. Editing them could invalidate stamped drawings. Not worth the risk.
- **Cost**: Users can't fix typos in title blocks via this tool
- **Revisit when**: We implement title block revision table support (V2 scope)

#### Single Backend File (main.py = 3,033 lines)
- **Chosen**: Monolithic main.py with all endpoints
- **Over**: Split into routers per domain
- **Because**: Started small, grew organically. Refactoring is tech debt, not blocking.
- **Cost**: Harder to navigate, risk of merge conflicts
- **Revisit when**: Next major refactor sprint

#### No Staging Environment
- **Chosen**: CI → main → production (direct deploy)
- **Over**: CI → staging → manual promote → production
- **Because**: Small team, fast iteration. Comprehensive test suite (4,556 tests) provides confidence. E2E tests run against production.
- **Cost**: Production outages if bad code merges
- **Revisit when**: User base grows, SLA commitments emerge

#### Session TTL of 2 Hours
- **Chosen**: Ephemeral sessions expire after 2h of inactivity
- **Over**: Permanent sessions or shorter TTL
- **Because**: Balance between resource usage (tmp storage, memory) and user convenience
- **Cost**: Users lose work if they step away > 2h without saving
- **Revisit when**: User complaints about lost work

#### Gemini 2.5 Flash over GPT-4 / Claude
- **Chosen**: Gemini via Vertex AI
- **Over**: OpenAI GPT-4, Anthropic Claude
- **Because**: GCP-native (WIF auth, same project), tool-use support, vision capability, cost
- **Cost**: Single-vendor lock-in for LLM
- **Revisit when**: Better tool-use model emerges, or Gemini quality degrades

### What Was Deliberately Not Built

- **Title block revision table updates**: Out of scope for V1. Too complex, legal implications.
- **3D entity support**: V1 is 2D only. Would require different viewer, different mental model.
- **Xref resolution**: External references not followed. Would require recursive loading, access control.
- **Multi-user collaboration**: Single-user sessions. Real-time collab would need CRDTs, conflict resolution.
- **Self-hosted LLM**: Requires Gemini. No local model fallback (mock provider is for testing only).

### Assumptions the Architecture Rests On

1. **Gemini tool-use remains stable**: If Gemini changes tool-call format, agent loop breaks
2. **ezdxf handles common DXF variants**: If users upload exotic DXF versions, parsing may fail
3. **2-hour session TTL is acceptable**: Users save work within 2 hours of last activity
4. **Protected layers are named consistently**: If users name title blocks differently, protection fails
5. **Single region is sufficient**: us-central1 outage = full outage

---

## 5. Directory Structure

### Layout

```
cad-dxf-agent/
├── src/cad_dxf_agent/          # Core Python package (28,784 lines)
│   ├── core/                   # 43 modules — DXF I/O, validation, analysis
│   ├── llm/                    # 24 modules — planning, agent, classification
│   ├── models/                 # 30 Pydantic schemas
│   ├── cli/                    # Revision CLI (cad-revision)
│   ├── ui/                     # PySide6 desktop UI
│   ├── app.py                  # Desktop entry point
│   ├── settings.py             # Env-based config
│   └── otel.py                 # OpenTelemetry bootstrap
├── web/
│   ├── backend/                # FastAPI on Cloud Run
│   │   ├── main.py             # 3,033 lines — all endpoints
│   │   ├── api_v1.py           # /api/v1 router
│   │   ├── auth.py             # Firebase auth validation
│   │   ├── session.py          # Session manager
│   │   └── Dockerfile          # Container image
│   └── frontend/               # React + Vite SPA
│       ├── src/components/     # 22 React components
│       └── playwright.config.ts # E2E test config
├── tests/                      # 4,556 tests across 10 tiers
│   ├── unit/                   # 137 test files
│   ├── integration/            # Integration tests
│   ├── web/                    # 40 API test files
│   ├── e2e/                    # 4 Playwright test files
│   ├── live/                   # Live Gemini API tests
│   └── fixtures/               # Test data, trajectories
├── 000-docs/                   # 73 documentation files
├── .github/workflows/          # 8 CI/CD workflows
└── pyproject.toml              # Package config
```

### Load-Bearing Files

| File | Role | Why Critical |
|------|------|-------------|
| `src/cad_dxf_agent/core/dxf_reader.py` | DXF → DrawingContext | First step of every operation |
| `src/cad_dxf_agent/core/validators.py` | Protected layer enforcement | Security boundary |
| `src/cad_dxf_agent/core/edit_engine.py` | Apply ops to ezdxf document | Core edit execution |
| `src/cad_dxf_agent/llm/gemini_provider.py` | Gemini API integration | LLM planning |
| `src/cad_dxf_agent/llm/objective_classifier.py` | Intent classification | Request routing |
| `src/cad_dxf_agent/models/ops_schema.py` | EditOperation, OpType enum | Operation contract |
| `web/backend/main.py` | All API endpoints | Web app functionality |
| `web/backend/auth.py` | Firebase auth validation | Security |
| `.github/workflows/deploy-web.yml` | Production deploy | Deployment pipeline |
| `web/backend/Dockerfile` | Container image | Runtime environment |

---

## 6. Getting Started

### Prerequisites

| Tool | Version | Install | Verify |
|------|---------|---------|--------|
| Python | 3.11 or 3.12 | `brew install python@3.12` or system package | `python --version` |
| pip | latest | Comes with Python | `pip --version` |
| Node.js | 22.x | `brew install node` or nvm | `node --version` |
| Git | any | `brew install git` | `git --version` |
| gcloud | latest | `brew install google-cloud-sdk` | `gcloud --version` |

### Zero to Running

```bash
# 1. Clone and enter
git clone https://github.com/jeremylongshore/cad-dxf-agent.git && cd cad-dxf-agent

# 2. Create venv and install — expect "Successfully installed" with ~50 packages
python -m venv .venv && source .venv/bin/activate
pip install -e ".[dev]"

# 3. Verify install — should see 4,556 tests collected
pytest --collect-only -q | tail -3

# 4. Run tests (mock mode, no API key needed) — expect all pass
pytest tests/unit/ -v -x --tb=short

# 5. Run smoke test — expect "PASS" at end
python scripts/smoke_test.py

# 6. Launch desktop app (optional, needs PySide6)
pip install -e ".[gui]"
python -m cad_dxf_agent.app
```

### Local Web Development

```bash
# Terminal 1: Backend
cd cad-dxf-agent
source .venv/bin/activate
CAD_WEB_DEV_MODE=1 uvicorn web.backend.main:app --port 8322 --reload

# Terminal 2: Frontend
cd cad-dxf-agent/web/frontend
npm ci
npm run dev

# Open http://localhost:3000
# CAD_WEB_DEV_MODE=1 skips Firebase auth — you'll see a fake user
```

### Using Real Gemini

```bash
# Authenticate with GCP
gcloud auth application-default login

# Set environment
export CAD_LLM_PROVIDER=gemini
export CAD_GCP_PROJECT=cad-dxf-agent

# Run with real LLM
python -m cad_dxf_agent.app
```

### Common Setup Problems

| Symptom | Cause | Fix |
|---------|-------|-----|
| `ModuleNotFoundError: ezdxf` | Not in venv | `source .venv/bin/activate` |
| `rtree.core.RTreeError` | libspatialindex missing | `apt install libspatialindex-dev` or `brew install spatialindex` |
| Gemini auth fails | No ADC configured | `gcloud auth application-default login` |
| DWG upload returns 422 | ODA not installed | Install ODA File Converter or use DXF/PDF |
| Tests fail with import errors | pytest outside venv | `.venv/bin/python -m pytest` |

---

## 7. Operations

### Command Map

| Task | Command | Notes |
|------|---------|-------|
| Run locally (desktop) | `python -m cad_dxf_agent.app` | Needs PySide6 |
| Run locally (web backend) | `CAD_WEB_DEV_MODE=1 uvicorn web.backend.main:app --port 8322` | Skips auth |
| Run locally (web frontend) | `cd web/frontend && npm run dev` | Port 3000 |
| Run all tests | `make test` or `pytest -v` | Mock mode |
| Run unit tests only | `make test-unit` or `pytest tests/unit/ -v` | Fast |
| Run web tests only | `pytest tests/web/ -v` | API tests |
| Run E2E tests | `cd web/frontend && npm run e2e` | Needs running app |
| Run live API tests | `CAD_GCP_PROJECT=cad-dxf-agent pytest tests/live/ -v -m live_api` | Real Gemini |
| Lint | `make lint` or `ruff check src/ tests/` | |
| Format | `make format` or `ruff format src/ tests/` | |
| Type check | `make typecheck` or `mypy src/` | |
| Security scan | `make security` or `bandit -r src/ && pip-audit` | |
| Build desktop exe | `make build` | PyInstaller |
| View deploy status | `gh run list --workflow=deploy-web.yml` | GitHub CLI |
| Manual backend deploy | See below | Avoid — use auto-deploy |
| Rollback | Route traffic to previous revision | See below |

### Deployment

**Normal Path** (recommended): Merge to main → GitHub Actions auto-deploys both frontend and backend.

**Pre-flight Checklist**:
1. All CI checks pass on PR
2. `make check` passes locally
3. Live API tests pass (if touching LLM code)
4. E2E tests pass (if touching frontend)

**Manual Deploy (if GitHub Actions is broken)**:

```bash
# ALWAYS specify --project (local gcloud may point elsewhere)

# Backend
gcloud run deploy cad-dxf-web \
  --source . --dockerfile web/backend/Dockerfile \
  --region us-central1 --project cad-dxf-agent \
  --allow-unauthenticated --memory 8Gi --cpu 4 --timeout 600 \
  --service-account cad-dxf-web-run@cad-dxf-agent.iam.gserviceaccount.com \
  --set-env-vars CAD_LLM_PROVIDER=gemini,CAD_GCP_PROJECT=cad-dxf-agent,OTEL_ENABLED=1,OTEL_EXPORTER=gcp-trace

# Frontend
cd web/frontend && npm run build
cd web && npx firebase-tools deploy --only hosting --project cad-dxf-agent
```

**Verification**:
- Backend: `curl https://cad-dxf-web-<hash>-uc.a.run.app/api/health`
- Frontend: Visit https://cad-dxf-agent.web.app, check console for errors
- E2E: `npm run e2e` against production

**Rollback Protocol**:

```bash
# List recent revisions
gcloud run revisions list --service cad-dxf-web --region us-central1 --project cad-dxf-agent

# Route traffic to previous revision
gcloud run services update-traffic cad-dxf-web \
  --to-revisions PREVIOUS_REVISION=100 \
  --region us-central1 --project cad-dxf-agent
```

### Monitoring & Alerting

- **Dashboards**: GCP Console → Cloud Run → cad-dxf-web (request count, latency, errors)
- **Traces**: GCP Console → Cloud Trace (spans: `cad.load_dxf`, `cad.run_planner`, etc.)
- **Logs**: GCP Console → Cloud Logging, filter `resource.type="cloud_run_revision"`
- **SLIs/SLOs**: Not formally defined. Informal target: <5s P95 latency, <1% error rate.
- **On-call**: Not established. Jeremy monitors via GCP Console.

### Incident Response

| Severity | Definition | Response Time | Playbook |
|----------|------------|---------------|----------|
| P0 | Full outage (web app unreachable) | Immediate | Check Cloud Run → rollback if needed |
| P1 | Auth broken or Gemini errors | 15 min | Check Firebase Console, Vertex AI status |
| P2 | Specific feature broken | 1 hour | Check logs, reproduce locally |
| P3 | Performance degradation | 4 hours | Check traces, scale up if needed |

---

## 8. Things That Will Bite You

### 8.1 ODA File Converter Missing
- **Symptom**: DWG uploads return HTTP 422 "DWG conversion requires ODA File Converter"
- **Cause**: ODA not installed in container, or oda.deb not downloaded during build
- **Fix**: Download ODA from GCS before `docker build`, or upload DXF/PDF instead
- **Prevention**: CI downloads ODA from `gs://cad-dxf-agent-deps/oda/` before build

### 8.2 Session Expires Mid-Work
- **Symptom**: User gets "session not found" error after stepping away
- **Cause**: 2-hour TTL expired
- **Fix**: User must re-upload drawing
- **Prevention**: Save work frequently; WorkProgress auto-saves on apply

### 8.3 Gemini Timeout on Complex Drawings
- **Symptom**: Edit request hangs, then fails after 60s
- **Cause**: Drawing has >5000 entities, context too large for Gemini
- **Fix**: Reduce entity count, use simpler prompts
- **Prevention**: ENTITY_CAP is 5000; larger drawings get warnings

### 8.4 Protected Layer Blocks Legitimate Edit
- **Symptom**: "Entity on protected layer" validation error
- **Cause**: Entity is on TITLE, TITLEBLOCK, SEAL, or REVISION layer
- **Fix**: Edit drawing in CAD software to move entity to different layer
- **Prevention**: Set `CAD_PROTECTED_LAYERS` env var to customize

### 8.5 pytest Runs System pytest Instead of Venv
- **Symptom**: Import errors, missing modules
- **Cause**: System pytest doesn't have project dependencies
- **Fix**: `.venv/bin/python -m pytest` or activate venv first
- **Prevention**: Always activate venv before running tests

### 8.6 Local gcloud Points to Wrong Project
- **Symptom**: Deploy fails with permission errors or deploys to wrong project
- **Cause**: `gcloud config get project` returns different project
- **Fix**: Always use `--project cad-dxf-agent` flag
- **Prevention**: Check `gcloud config get project` before manual deploys

### 8.7 Firestore Rules Block Write
- **Symptom**: Profile or workspace save fails with permission error
- **Cause**: Firestore security rules not deployed or incorrect
- **Fix**: `cd web && npx firebase-tools deploy --only firestore:rules --project cad-dxf-agent`
- **Prevention**: Rules deploy is part of frontend deploy workflow

### 8.8 PDF Conversion Produces Sparse DXF
- **Symptom**: PDF upload converts but many elements missing
- **Cause**: PDF contains vector graphics that don't map cleanly to DXF entities
- **Fix**: Use original DXF if available; adjust `CAD_PDF_*` settings
- **Prevention**: PDF → DXF is inherently lossy; warn users

---

## 9. Security & Access

### Access Control

| Role | Purpose | Permissions | MFA |
|------|---------|-------------|-----|
| GCP Owner | Full project access | All IAM roles | Required |
| Cloud Run SA | Runtime identity | Vertex AI User, GCS Object Admin, Firestore User | N/A (SA) |
| WIF SA | CI/CD deploy | Cloud Run Admin, Artifact Registry Writer, Firebase Hosting Admin | N/A (WIF) |
| Firebase User | End users | Read/write own documents only | Optional (Google) |

### Secrets

- **Where**: Environment variables in Cloud Run service, GitHub Actions vars
- **Rotation**: No formal rotation policy
- **Emergency access**: GCP Console → Cloud Run → Environment Variables

**Secrets inventory**:
- `CAD_ALLOWED_EMAILS`: Semicolon-separated allowlist (not secret, just config)
- `WIF_PROVIDER`, `WIF_SERVICE_ACCOUNT`: GitHub Actions vars for WIF auth
- Firebase config (API key, etc.): Public in frontend (by design — Firebase keys are scoped by domain)

### Honest Security Assessment

**Implemented**:
- Firebase Auth (Google Sign-In) — token validation server-side
- Protected layer enforcement — validator + tool executor both check
- No raw DXF manipulation by LLM — structured ops only
- Bandit + pip-audit in CI — SAST and dependency scanning
- Pre-commit hooks — prevent secrets in commits
- CORS restricted to `cad-dxf-agent.web.app`
- GCS paths include tenant/user ID — no cross-tenant access

**Not Implemented**:
- Rate limiting — no per-user throttling
- Input validation on drawing content — ezdxf handles parsing, but malformed files could cause issues
- Formal penetration testing — not done
- SOC 2 / compliance certification — not pursued
- WAF — no Cloud Armor configured

---

## 10. Cost & Performance

### Monthly Costs (estimated)

| Resource | Cost | Notes |
|----------|------|-------|
| Cloud Run | ~$50-200 | Pay-per-request, 8Gi/4CPU instances |
| Firebase Hosting | ~$0-10 | Static hosting, minimal bandwidth |
| Firestore | ~$10-50 | Depends on reads/writes |
| GCS | ~$5-20 | Depends on storage volume |
| Vertex AI (Gemini) | ~$50-500 | Per-token pricing, depends on usage |
| Artifact Registry | ~$5 | Docker images |
| **Total** | **~$100-800/month** | Depends heavily on usage |

### Performance

| Metric | Target | Current |
|--------|--------|---------|
| Upload latency | <2s | ~1-2s (small files) |
| Edit plan latency | <10s | ~3-8s (Gemini response) |
| Analysis latency | <5s | ~1-3s (deterministic) |
| Error rate | <1% | <0.5% (observed) |

### Scaling Limits

- **Cloud Run max instances**: Default 100, can increase via quota
- **Session storage**: `/tmp` on Cloud Run, limited by instance memory (8Gi)
- **Entity count per drawing**: ENTITY_CAP = 5000 (performance degrades above this)
- **Concurrent users**: Limited by Cloud Run scaling, not explicitly tested
- **Gemini rate limits**: Vertex AI quotas apply

---

## 11. Current State

### What's Working

- **30 epics shipped** — Full feature set implemented (edit, compliance, health, takeoff, summary, RFI, zones, revision, agent)
- **4,556 tests passing** — 10 tiers of testing (unit, integration, web, eval, live, e2e, benchmark, gui, property, smoke)
- **Auto-deploy via WIF** — No secrets in CI, merge-to-main deploys
- **User accounts + persistence** — Firestore profiles, GCS documents, WorkProgress auto-save
- **E2E production testing** — 58 Playwright tests against live Firebase + Cloud Run

### What Needs Attention

- **HIGH** — Single-region deployment → Impact: Full outage if us-central1 down → Fix: Multi-region or failover
- **HIGH** — No staging environment → Impact: Bad deploys hit prod immediately → Fix: Add staging workflow
- **MEDIUM** — main.py is 3,033 lines → Impact: Hard to navigate, merge conflicts → Fix: Split into routers
- **MEDIUM** — ODA dependency → Impact: DWG support requires proprietary software → Fix: Explore alternatives
- **LOW** — No rate limiting → Impact: Potential abuse → Fix: Add Cloud Armor or app-level throttling
- **LOW** — Informal SLOs → Impact: No alerting on degradation → Fix: Define SLIs, set up alerts

### Implementation Status

| Component | Status | Evidence |
|-----------|--------|----------|
| Edit pipeline | Complete | 13 op types, all tested |
| Compliance engine | Complete | ADA/IBC rules, stage handler |
| Health checker | Complete | Quality metrics, findings |
| Takeoff engine | Complete | Count extraction, area calc |
| Drawing summarizer | Complete | Plain-English output |
| RFI generator | Complete | Ambiguity detection |
| Zone detector | Complete | Closed-loop detection |
| Revision comparison | Complete | CLI + web workflow |
| Agent mode | Complete | 10-turn tool-use loop |
| User accounts | Complete | Firestore profiles, tenants |
| Document persistence | Complete | GCS storage, WorkProgress |

---

## 12. Roadmap

### Week 1 — Stabilization
- [ ] Monitor production for post-v0.10.1 issues
- [ ] Address any E2E test flakiness
- [ ] Update gist with v0.10.1 content

### Month 1 — Foundation
- [ ] Split main.py into domain-specific routers
- [ ] Add staging environment workflow
- [ ] Define formal SLIs/SLOs
- [ ] Set up alerting on error rate/latency

### Quarter 1 — Strategic
- [ ] Multi-region deployment or failover
- [ ] Rate limiting / abuse prevention
- [ ] Explore ODA alternatives (if any)
- [ ] Performance optimization for large drawings

---

## 13. Quick Reference

### URLs

| Resource | URL |
|----------|-----|
| Production Web App | https://cad-dxf-agent.web.app |
| Cloud Run Service | https://cad-dxf-web-<hash>-uc.a.run.app |
| GitHub Repo | https://github.com/jeremylongshore/cad-dxf-agent |
| GCP Console | https://console.cloud.google.com/run?project=cad-dxf-agent |
| Firebase Console | https://console.firebase.google.com/project/cad-dxf-agent |
| Cloud Trace | https://console.cloud.google.com/traces/list?project=cad-dxf-agent |
| CI Workflows | https://github.com/jeremylongshore/cad-dxf-agent/actions |

### First-Week Checklist

- [ ] Access granted: GitHub repo, GCP project viewer, Firebase console
- [ ] Local environment running: `pytest tests/unit/ -v` passes
- [ ] Read this document
- [ ] Read CLAUDE.md (project conventions)
- [ ] Completed local web dev setup (backend + frontend running)
- [ ] Reviewed deploy workflow (`.github/workflows/deploy-web.yml`)
- [ ] Reviewed key ADRs (005-AT-ADEC-llm-plans-not-dxf.md)
- [ ] Met with system owner (Jeremy)

---

## Appendices

### A. Environment Variables Reference

| Variable | Default | Purpose |
|----------|---------|---------|
| `CAD_LLM_PROVIDER` | `mock` | LLM backend: `gemini` or `mock` |
| `CAD_GCP_PROJECT` | — | GCP project for Vertex AI |
| `CAD_GCP_LOCATION` | `us-central1` | Vertex AI region |
| `CAD_GEMINI_MODEL` | `gemini-2.5-flash` | Gemini model ID |
| `CAD_PROTECTED_LAYERS` | `TITLE,TITLEBLOCK,SEAL,REVISION` | Layers that cannot be edited |
| `CAD_REVISION_NOTES_ENABLED` | `true` | Insert AI revision notes |
| `CAD_REVISION_NOTES_LAYER` | `AI_REV_NOTES` | Layer for revision notes |
| `CAD_WEB_DEV_MODE` | — | Skip Firebase auth (local dev) |
| `CAD_ALLOWED_EMAILS` | — | Semicolon-separated allowlist |
| `OTEL_ENABLED` | — | Enable OpenTelemetry tracing |
| `OTEL_EXPORTER` | `console` | Trace exporter: `console`, `otlp`, `gcp-trace` |

### B. CI/CD Workflows

| Workflow | Trigger | Purpose |
|----------|---------|---------|
| `ci.yml` | Push/PR to main | Lint, typecheck, test, benchmark, live tests |
| `deploy-web.yml` | Push to main (web/** or src/**) | Deploy backend + frontend |
| `build-windows.yml` | Tag (v*) | Build Windows installer |
| `canary-monitoring.yml` | Schedule | Production health checks |
| `gemini-review.yml` | PR | Gemini code review |
| `security.yml` | Schedule | Dependency audit |

### C. Test Tiers

| Tier | Location | Count | Purpose |
|------|----------|-------|---------|
| Unit | `tests/unit/` | ~3,600 | Module-level tests |
| Integration | `tests/integration/` | ~100 | Cross-module tests |
| Web | `tests/web/` | ~420 | API endpoint tests |
| Eval | `tests/eval/` | ~40 | Intent classification accuracy |
| Live | `tests/live/` | ~42 | Real Gemini API tests |
| E2E | `tests/e2e/` | ~33 | Playwright browser tests |
| Benchmark | `tests/benchmark/` | ~19 | Performance tests |
| GUI | `tests/gui/` | ~10 | PySide6 UI tests |
| Property | `tests/property/` | ~7 | Fuzz/property tests |
| Smoke | `tests/smoke/` | ~7 | Quick sanity checks |

### D. Glossary

| Term | Definition |
|------|------------|
| DrawingContext | Pydantic model containing parsed DXF entities, layers, blocks |
| EntityRef | Reference to a DXF entity with handle, type, layer, coordinates |
| EditOperation | Structured edit command (OpType + parameters) |
| ChangeSet | Collection of EditOperations returned by planner |
| ObjectiveClassification | Two-axis classification (RequestClass × ObjectiveTag) |
| StagePipelineDefinition | Ordered list of stage handlers for a request type |
| Protected Layer | Layer that cannot be edited (TITLE, TITLEBLOCK, SEAL, REVISION) |
| WorkProgress | Auto-saved state for document-bound sessions |

### E. Troubleshooting Playbooks

**"Gemini returns empty changeset"**
1. Check Cloud Trace for `cad.run_planner` span
2. Look for timeout or error in span attributes
3. Try simpler prompt or smaller drawing
4. Check Vertex AI quotas in GCP Console

**"Auth fails after deploy"**
1. Check Firebase Console → Authentication → Sign-in providers
2. Verify Firestore rules deployed
3. Check `CAD_ALLOWED_EMAILS` in Cloud Run env vars
4. Clear browser cache/cookies

**"E2E tests fail intermittently"**
1. Check for network timing issues
2. Increase timeouts in Playwright config
3. Check for race conditions in async operations
4. Review recent changes to affected components

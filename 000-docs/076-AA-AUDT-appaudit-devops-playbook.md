# IntentCAD: Operator-Grade System Analysis
*Generated: 2026-04-06*
*Version: v0.12.0*

---

## 1. This System in 5 Minutes

IntentCAD is a **web application** that lets AEC professionals edit and analyze 2D drawings using natural language. Users upload a **DXF**, **PDF**, or **DWG** file, type a request like "move the column east by 2 feet" or "check ADA compliance," and the system classifies the intent, runs it through the appropriate pipeline, and returns results. PDFs are automatically classified per-page (vector layout, raster scan, mixed) and converted to editable geometry with Bézier curve recovery. DWG files are converted via ODA File Converter. The web app is deployed on Google Cloud: React SPA on Firebase Hosting, FastAPI backend on Cloud Run.

The core architectural constraint is that **the LLM never touches DXF directly**. Instead, it returns structured JSON operations (`move_entity`, `delete_entity`, `add_text`, etc.) which are validated against a schema before a deterministic engine applies them. This prevents LLM hallucinations from corrupting drawings — critical for AEC where drawings are legal documents.

The system handles nine workflows: **edit** (13 operation types), **compliance** (ADA/IBC rule checking), **health report** (quality metrics), **quantity takeoff** (counting), **summary** (plain-English description), **RFI generation** (detect ambiguities), **zone detection** (room finding), **revision comparison** (diff two DXFs), and **agent mode** (multi-turn tool-use loop).

Current state: **4,687 tests**, 31 epics shipped, production-deployed at `cad-dxf-agent.web.app`. Self-registration is now open (v0.12.0). The biggest risks are single-region deployment (us-central1 only) and no staging environment — code goes directly from CI to production.

---

## 2. Executive Summary

### What It Does

IntentCAD processes DXF, PDF, and DWG drawings through a two-axis intent classification system. Users upload in any of the three formats — PDFs are classified per-page and converted to editable geometry with Bézier curve recovery via PyMuPDF, DWGs are converted via ODA File Converter. Every prompt is classified by *what* the user wants (edit, analyze, compare, query, generate) and *why* they want it (compliance, coordination, documentation, estimation, quality, general). This routes the request to a purpose-built pipeline rather than a generic LLM response.

For **edits**, the pipeline is: classify intent → select strategy → LLM plans operations → validate against rules → preview for user → apply deterministically → save as new file. For **analysis**, the pipeline runs deterministic extractors (no LLM involved) that produce identical results every time.

The backend (`web/backend/main.py`, 3,105 lines) is a single FastAPI file handling 20+ endpoints. It runs on Cloud Run with 8GB RAM, 4 CPUs, and 600s timeout. Authentication is Firebase Auth (Google Sign-In only). Document persistence uses GCS with Firestore for metadata.

Key risks: (1) single-region deployment in us-central1, (2) no staging environment, (3) ODA File Converter dependency for DWG support is proprietary, (4) main.py is a 3K-line monolith.

### Operational Status

| Environment | Status | Uptime Target | Release Cadence | Last Deploy |
|-------------|--------|---------------|-----------------|-------------|
| Production (Web) | Active | Best-effort (Cloud Run SLA) | Merge-to-main auto-deploy | Continuous |
| Staging | **None** | N/A | N/A | N/A |
| Local Dev | Works | N/A | N/A | N/A |

### Technology Stack

| Category | Technology | Version | Purpose |
|----------|------------|---------|---------|
| Language | Python | 3.11/3.12 | Backend, pipeline |
| DXF Engine | ezdxf | >=1.3.0 | DXF read/write/manipulation |
| PDF Engine | PyMuPDF (fitz) | Latest | Vector extraction, page classification, preview rendering |
| PDF Fallback | pdfplumber | Latest | Backup extraction when PyMuPDF unavailable |
| DWG Converter | ODA File Converter | Latest | DWG-to-DXF conversion via ezdxf addon |
| Schemas | Pydantic | >=2.0 | Operation and response validation |
| Spatial | Rtree + Shapely | >=1.0 / >=2.0 | Entity indexing, geometry |
| LLM | Gemini 2.5 Flash | via Vertex AI | Intent classification, edit planning |
| Backend | FastAPI | latest | REST API |
| Frontend | React + Vite | 18.x | SPA (22 components) |
| Auth | Firebase Auth | — | Google Sign-In |
| Storage | GCS + Firestore | — | Documents, profiles |
| Hosting | Cloud Run | — | 8Gi/4CPU/600s |
| CI/CD | GitHub Actions | — | WIF-based deploy |

---

## 3. Architecture

### Stack (Detailed)

| Layer | Technology | Version | Purpose | Why This |
|-------|------------|---------|---------|----------|
| DXF I/O | ezdxf | 1.3+ | Read/write DXF | Only mature Python DXF library; MIT |
| Validation | Pydantic v2 | 2.0+ | Schema validation | Type safety, Rust-core perf |
| Spatial | Rtree | 1.0+ | Nearest-neighbor queries | Standard for 2D spatial |
| Geometry | Shapely | 2.0+ | Polygon/line operations | De facto Python geometry lib |
| LLM | Gemini | 2.5 Flash | Planning, vision | GCP-native, good tool-use |
| Backend | FastAPI | latest | REST API | Async, OpenAPI, Pydantic-native |
| Frontend | React + Vite | 18/6 | SPA | Standard, fast DX |
| Auth | Firebase | v11 | Google Sign-In | Zero-friction OAuth |
| Storage | GCS | — | Binary blobs | GCP-native |
| Metadata | Firestore | — | Profiles, tenants | GCP-native, real-time |

### System Diagram

```
┌─────────────────────────────────────┐
│        Firebase Hosting              │
│    cad-dxf-agent.web.app             │
│    (React SPA, 22 components)        │
└─────────────┬───────────────────────┘
              │ /api/* rewrite
              ▼
┌─────────────────────────────────────┐
│         Cloud Run                    │
│    cad-dxf-web (us-central1)         │
│    FastAPI (8Gi RAM, 4 CPU)          │
│    main.py: 3,105 lines              │
└─────────────┬───────────────────────┘
              │
    ┌─────────┼─────────┐
    ▼         ▼         ▼
┌────────┐ ┌────────┐ ┌────────┐
│Pipeline│ │Vertex  │ │Firebase│
│Core    │ │AI      │ │/GCS    │
│30K LOC │ │Gemini  │ │        │
└────────┘ └────────┘ └────────┘
```

### The Critical Path

**Edit request flow** (file: `web/backend/main.py`):

1. **Upload** (`/api/upload`) → Session created, file converted if needed (PDF → vector extraction, DWG → ODA convert), DXF stored in `/tmp/cad-sessions/{id}/`
2. **Load** (`core/dxf_reader.py`) → Parse DXF into `DrawingContext` Pydantic model
3. **Enrich** (`core/semantic_model.py`) → Add family detection, primitives
4. **Classify** (`llm/objective_classifier.py`) → 2-axis intent classification
5. **Route** (`llm/strategy_registry.py`) → Select pipeline for (RequestClass, ObjectiveTag)
6. **Plan** (`llm/gemini_provider.py`) → LLM returns `ChangeSet` with operations
7. **Validate** (`core/validators.py`) → Check protected layers, schema compliance
8. **Preview** (`core/preview_builder.py`) → Human-readable descriptions
9. **Apply** (`core/edit_engine.py`) → Deterministic execution on ezdxf doc
10. **Save** (`core/dxf_writer.py`) → Write to new file path (original untouched)

**Failure points**:
- Step 6: Gemini timeout → empty ChangeSet
- Step 7: Validation fails → HTTP 400
- Step 9: ezdxf error → operation skipped, logged

### Dependency Graph

```
React SPA
    ↓
FastAPI Backend (main.py)
    ↓
Pipeline Core (55 modules in core/)
    ↓
├── ezdxf (DXF manipulation)
├── Pydantic (validation)
├── Rtree (spatial index)
├── Shapely (geometry)
└── httpx (API calls)
    ↓
External Services
├── Vertex AI (Gemini)
├── Firebase Auth
├── Firestore
└── GCS
```

**What breaks when dependencies fail**:
- Gemini down → Edit requests fail, analysis still works (deterministic)
- Firebase down → Auth fails, no new sessions
- GCS down → No document persistence
- ezdxf bug → All DXF operations fail

---

## 4. Design Decisions & Tradeoffs

### Decision Log

#### LLM Returns JSON, Never Edits DXF (ADR 0002)
- **Chosen**: LLM outputs `EditOperation` objects (13 types)
- **Over**: LLM directly editing DXF bytes
- **Because**: AEC drawings are legal documents. LLM hallucinations = liability disaster.
- **Cost**: Can't express operations outside schema; complex edits need multi-turn
- **Revisit when**: Never (core safety principle)

*Source: `000-docs/005-AT-ADEC-llm-plans-not-dxf.md`*

#### Web-First Deployment
- **Chosen**: React + Cloud Run as primary deployment
- **Over**: Native desktop distribution
- **Because**: Web is accessible anywhere, zero install, immediate updates
- **Cost**: Requires internet connection
- **Revisit when**: Users demand offline capability

#### PDF Vector Extraction over OCR
- **Chosen**: PyMuPDF vector path extraction with Bézier curve recovery
- **Over**: OCR-based reconstruction of scanned drawings
- **Because**: CAD-generated PDFs contain clean vector data; OCR adds noise and inaccuracy
- **Cost**: Scanned/raster-only PDFs are rejected (user is told to export as DXF)
- **Revisit when**: Users need scanned PDF support

*Source: `core/converter.py:192-308`*

#### DWG via ODA File Converter
- **Chosen**: ODA File Converter (industry standard, proprietary)
- **Over**: Native DWG parsing
- **Because**: No open-source DWG library exists; ODA handles all DWG versions
- **Cost**: Proprietary dependency; DWG is convert-only (no native editing)
- **Revisit when**: Open DWG library emerges or native DWG editing is needed

*Source: `core/converter.py:152-183`*

#### Protected Layers as Hard Block
- **Chosen**: Reject ANY operation on TITLE, TITLEBLOCK, SEAL, REVISION layers
- **Over**: Soft warning with override
- **Because**: These contain legal seals. Editing = invalidating stamped drawings.
- **Cost**: Can't fix typos in title blocks via this tool
- **Revisit when**: Title block revision table support (not planned)

*Source: `core/validators.py:27-35`*

#### Single Backend File (3,105 lines)
- **Chosen**: Monolithic `main.py` with all endpoints
- **Over**: Split into domain routers
- **Because**: Started small, grew organically
- **Cost**: Hard to navigate, merge conflicts
- **Revisit when**: Next refactor sprint (overdue)

*Evidence: `wc -l web/backend/main.py` = 3105*

#### No Staging Environment
- **Chosen**: CI → main → production
- **Over**: CI → staging → promote → production
- **Because**: Small team, fast iteration, 4,688 tests provide confidence
- **Cost**: Bad merges hit production immediately
- **Revisit when**: User base grows, SLA commitments emerge

*Evidence: No staging workflow in `.github/workflows/`*

#### Google Sign-In + Email/Password (v0.12.0)
- **Chosen**: Firebase Auth with Google and email/password providers
- **Over**: OAuth-only
- **Because**: User feedback requested email/password option; Google remains primary
- **Cost**: Password management overhead, but Firebase handles it
- **Revisit when**: Enterprise demands SAML/OIDC

*Source: `web/backend/auth.py` — validates Firebase ID tokens from any provider*

### What Was Deliberately Not Built

- **Title block revision tables**: Too complex, legal implications
- **3D entity support**: 2D only in V1, different mental model needed
- **Xref resolution**: Would require recursive loading, access control
- **Multi-user collaboration**: Would need CRDTs, conflict resolution
- **Offline mode**: Web-only, requires internet
- **Self-hosted LLM**: Requires Gemini; mock provider is test-only

### Assumptions the Architecture Rests On

1. **Gemini tool-use format remains stable** — agent loop breaks if format changes
2. **ezdxf handles common DXF variants** — exotic versions may fail
3. **2-hour session TTL acceptable** — users save within 2 hours
4. **Protected layers named consistently** — if users name differently, protection fails
5. **Single region sufficient** — us-central1 outage = full outage

---

## 5. Directory Structure

### Layout

```
cad-dxf-agent/
├── src/cad_dxf_agent/           # 30,210 lines Python
│   ├── core/                    # 41 modules — DXF I/O, validation, analysis
│   │   ├── converter.py         # PDF/DWG → DXF conversion pipeline
│   │   ├── pdf_classifier.py    # Per-page PDF content classification
│   │   └── comparison/          # 14 modules — revision diff engine
│   ├── llm/                     # 22 modules — planning, classification
│   │   └── stage_handlers/      # 6 modules — pipeline stages
│   ├── models/                  # 30 Pydantic schemas
│   ├── cli/                     # Revision CLI
│   ├── settings.py              # Env config
│   └── otel.py                  # OpenTelemetry
├── web/
│   ├── backend/
│   │   ├── main.py              # 3,105 lines — ALL endpoints
│   │   ├── auth.py              # Firebase auth
│   │   ├── session.py           # Session management
│   │   └── Dockerfile
│   └── frontend/
│       └── src/components/      # 22 React components
├── tests/                       # 4,687 tests
├── 000-docs/                    # 67 doc files
└── .github/workflows/           # 8 CI/CD workflows
```

### Load-Bearing Files

| File | Lines | Role | If It Breaks |
|------|-------|------|--------------|
| `web/backend/main.py` | 3,105 | All API endpoints | Web app dead |
| `core/converter.py` | ~900 | PDF/DWG → DXF conversion | No multi-format upload |
| `core/dxf_reader.py` | ~400 | DXF → DrawingContext | Nothing loads |
| `core/validators.py` | ~300 | Protected layer enforcement | Security bypassed |
| `core/edit_engine.py` | ~500 | Apply ops to DXF | No edits work |
| `llm/gemini_provider.py` | ~400 | Gemini API integration | No LLM planning |
| `llm/objective_classifier.py` | ~200 | Intent classification | Wrong pipelines |
| `models/ops_schema.py` | ~300 | EditOperation, OpType | Schema validation fails |
| `web/backend/auth.py` | ~300 | Firebase token validation | Auth broken |
| `.github/workflows/deploy-web.yml` | ~100 | Production deploy | Deploys fail |

---

## 6. Getting Started

### Prerequisites

| Tool | Version | Install | Verify |
|------|---------|---------|--------|
| Python | 3.11+ | `brew install python@3.12` | `python --version` |
| Node.js | 22.x | `brew install node` | `node --version` |
| gcloud | latest | `brew install google-cloud-sdk` | `gcloud --version` |

### Zero to Running

```bash
# Clone
git clone https://github.com/jeremylongshore/cad-dxf-agent.git
cd cad-dxf-agent

# Install — expect ~50 packages
python -m venv .venv && source .venv/bin/activate
pip install -e ".[dev]"

# Verify — should see "4687 tests collected"
pytest --collect-only -q | tail -3

# Run tests (mock mode, no API key)
pytest tests/unit/ -v -x --tb=short

# Smoke test
python scripts/smoke_test.py
```

### Local Web Development

```bash
# Terminal 1: Backend (skips auth in dev mode)
CAD_WEB_DEV_MODE=1 uvicorn web.backend.main:app --port 8322 --reload

# Terminal 2: Frontend
cd web/frontend && npm ci && npm run dev

# Open http://localhost:3000
```

### Using Real Gemini

```bash
gcloud auth application-default login
export CAD_LLM_PROVIDER=gemini
export CAD_GCP_PROJECT=cad-dxf-agent
```

### Common Setup Problems

| Symptom | Cause | Fix |
|---------|-------|-----|
| `ModuleNotFoundError: ezdxf` | Not in venv | `source .venv/bin/activate` |
| `rtree.core.RTreeError` | libspatialindex missing | `apt install libspatialindex-dev` |
| Gemini auth fails | No ADC | `gcloud auth application-default login` |
| DWG returns 422 | ODA not installed | Use DXF/PDF instead |

---

## 7. Operations

### Command Map

| Task | Command |
|------|---------|
| Run tests | `make test` or `pytest -v` |
| Run unit tests | `pytest tests/unit/ -v` |
| Run web tests | `pytest tests/web/ -v` |
| Lint | `ruff check src/ tests/` |
| Format | `ruff format src/ tests/` |
| Type check | `mypy src/` |
| Security scan | `bandit -r src/ && pip-audit` |
| Local backend | `CAD_WEB_DEV_MODE=1 uvicorn web.backend.main:app --port 8322` |
| Local frontend | `cd web/frontend && npm run dev` |
| Deploy | Push to main (auto-deploys) |
| View deploy status | `gh run list --workflow=deploy-web.yml` |

### Deployment

**Normal path**: Merge to main → GitHub Actions auto-deploys both frontend and backend via WIF.

**Manual deploy (if CI broken)**:
```bash
# Backend — ALWAYS use --project
gcloud run deploy cad-dxf-web \
  --source . --dockerfile web/backend/Dockerfile \
  --region us-central1 --project cad-dxf-agent \
  --memory 8Gi --cpu 4 --timeout 600

# Frontend
cd web/frontend && npm run build
firebase deploy --only hosting --project cad-dxf-agent
```

**Rollback**:
```bash
gcloud run revisions list --service cad-dxf-web --region us-central1 --project cad-dxf-agent
gcloud run services update-traffic cad-dxf-web --to-revisions PREV_REV=100 --region us-central1 --project cad-dxf-agent
```

### Monitoring

- **Logs**: GCP Console → Cloud Logging, filter `resource.type="cloud_run_revision"`
- **Traces**: GCP Console → Cloud Trace (spans: `cad.load_dxf`, `cad.run_planner`)
- **Dashboards**: Cloud Run console → cad-dxf-web
- **SLIs/SLOs**: Not defined. Informal: <5s P95, <1% errors.
- **On-call**: Not established. Jeremy monitors manually.

---

## 8. Things That Will Bite You

### 8.1 Session Expires (2h TTL)
- **Symptom**: "session not found" after stepping away
- **Cause**: Sessions expire after 2 hours inactivity
- **Fix**: Re-upload file
- **Prevention**: Save frequently; WorkProgress auto-saves on apply

### 8.2 Protected Layer Blocks Edit
- **Symptom**: "Entity on protected layer" error
- **Cause**: Entity on TITLE/TITLEBLOCK/SEAL/REVISION layer
- **Fix**: Edit in CAD software to move entity
- **Prevention**: Set `CAD_PROTECTED_LAYERS` env var to customize

### 8.3 Gemini Timeout
- **Symptom**: Request hangs, fails after 60s
- **Cause**: Drawing >5000 entities, context too large
- **Fix**: Simplify prompt, reduce entity count
- **Prevention**: ENTITY_CAP is 5000

### 8.4 DWG Returns 422
- **Symptom**: DWG upload fails
- **Cause**: ODA File Converter not installed in container
- **Fix**: Use DXF or PDF instead
- **Prevention**: ODA downloaded from GCS during CI build

### 8.5 Wrong gcloud Project
- **Symptom**: Deploy fails with permission errors
- **Cause**: Local gcloud points to different project
- **Fix**: Always use `--project cad-dxf-agent`
- **Prevention**: Check `gcloud config get project` first

### 8.6 pytest Outside Venv
- **Symptom**: Import errors
- **Cause**: System pytest lacks dependencies
- **Fix**: `.venv/bin/python -m pytest`
- **Prevention**: Always activate venv first

---

## 9. Security & Access

### Access Control

| Role | Purpose | Permissions |
|------|---------|-------------|
| GCP Owner | Full access | All IAM roles |
| Cloud Run SA | Runtime | Vertex AI User, GCS Admin, Firestore User |
| WIF SA | CI/CD | Cloud Run Admin, Artifact Registry Writer |
| Firebase User | End users | Own documents only |

### Secrets

- **Where**: Cloud Run env vars, GitHub Actions vars
- **Rotation**: None established
- **Inventory**: `WIF_PROVIDER`, `WIF_SERVICE_ACCOUNT`, `CAD_ALLOWED_EMAILS`

### Security Assessment

**Implemented**:
- Firebase Auth with Google Sign-In
- Protected layer enforcement (validator + tool executor)
- LLM never touches raw DXF
- Rate limiting: 60 req/min per IP (`web/backend/main.py:70-90`)
- Bandit + pip-audit in CI
- GCS paths include tenant/user ID

**Not implemented**:
- WAF (no Cloud Armor)
- Formal pen testing
- SOC 2 certification
- Per-user rate limiting

---

## 10. Cost & Performance

### Monthly Costs (estimated)

| Resource | Cost |
|----------|------|
| Cloud Run | ~$50-200 |
| Firebase Hosting | ~$0-10 |
| Firestore | ~$10-50 |
| GCS | ~$5-20 |
| Vertex AI (Gemini) | ~$50-500 |
| **Total** | **~$100-800/month** |

### Performance

| Metric | Target | Actual |
|--------|--------|--------|
| Upload latency | <2s | ~1-2s |
| Edit planning | <10s | ~3-8s |
| Analysis | <5s | ~1-3s |
| Error rate | <1% | <0.5% |

### Scaling Limits

- Cloud Run: 100 max instances (default)
- Entity cap: 5,000 per drawing
- Session storage: 8Gi instance memory
- Gemini: Vertex AI quotas

---

## 11. Current State

### What's Working

- **4,687 tests passing** — 10 tiers (unit, integration, web, eval, live, e2e, benchmark, gui, property, smoke)
- **31 epics shipped** — edit, compliance, health, takeoff, summary, RFI, zones, revision, agent
- **Multi-format upload** — DXF (native), PDF (vector extraction with curve recovery), DWG (ODA conversion)
- **Auto-deploy via WIF** — no secrets in CI
- **User accounts + persistence** — Firestore profiles, GCS documents
- **Rate limiting** — 60 req/min per IP

### What Needs Attention

| Severity | Issue | Impact | Fix |
|----------|-------|--------|-----|
| HIGH | Single-region (us-central1) | Full outage if region down | Multi-region |
| HIGH | No staging environment | Bad code hits prod | Add staging |
| MEDIUM | main.py is 3,105 lines | Hard to maintain | Split into routers |
| MEDIUM | Scanned/raster PDFs rejected | Vector-only PDF support | Add OCR pipeline |
| LOW | Basic rate limiting | No per-user granularity | Add Cloud Armor |

### Implementation Status

| Component | Status | Evidence |
|-----------|--------|----------|
| Edit pipeline | Complete | 13 op types tested |
| Compliance | Complete | ADA/IBC rules |
| Health checker | Complete | Quality metrics |
| Takeoff | Complete | Count extraction |
| Summarizer | Complete | Plain-English output |
| RFI generator | Complete | Ambiguity detection |
| Zone detector | Complete | Closed-loop detection |
| Revision diff | Complete | CLI + web |
| Agent mode | Complete | 10-turn tool-use |
| PDF conversion | Complete | PyMuPDF vector extraction + page classification |
| DWG conversion | Complete | ODA File Converter integration |

---

## 12. Roadmap

### Week 1
- [ ] Split main.py into domain routers

### Month 1
- [ ] Split main.py into domain routers
- [ ] Add staging environment

### Quarter 1
- [ ] Multi-region deployment
- [ ] Cloud Armor WAF
- [ ] Formal SLIs/SLOs

---

## 13. Quick Reference

### URLs

| Resource | URL |
|----------|-----|
| Production | https://cad-dxf-agent.web.app |
| GitHub | https://github.com/jeremylongshore/cad-dxf-agent |
| GCP Console | https://console.cloud.google.com/run?project=cad-dxf-agent |
| CI | https://github.com/jeremylongshore/cad-dxf-agent/actions |

### First-Week Checklist

- [ ] Get GitHub repo access
- [ ] Get GCP project access
- [ ] Run `make check` locally
- [ ] Read this document
- [ ] Read `CLAUDE.md`
- [ ] Deploy to production (merge a typo fix)

---

## Appendix A: Glossary

| Term | Definition |
|------|------------|
| ChangeSet | Collection of EditOperations applied atomically |
| DrawingContext | Pydantic model of a loaded DXF |
| EditOperation | Single edit (move, delete, add, etc.) |
| EntityRef | Reference to DXF entity with ID, type, layer |
| ObjectiveClassification | 2-axis intent result |
| RequestClass | What: edit, analyze, compare, query, generate |
| ObjectiveTag | Why: compliance, coordination, documentation, etc. |

## Appendix B: Environment Variables

| Variable | Default | Purpose |
|----------|---------|---------|
| `CAD_LLM_PROVIDER` | `mock` | `gemini` for production |
| `CAD_GCP_PROJECT` | — | GCP project ID |
| `CAD_PROTECTED_LAYERS` | `TITLE,TITLEBLOCK,SEAL,REVISION` | Protected layers |
| `CAD_WEB_DEV_MODE` | — | Skip auth for local dev |
| `OTEL_ENABLED` | — | Enable tracing |

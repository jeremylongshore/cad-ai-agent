# CAD DXF Agent: Operator-Grade System Analysis
*For: DevOps Engineer / Beta Tester*
*Generated: 2026-02-24*
*Version: feat/web-mvp (commit e603114)*

## 1. Executive Summary

### Business Purpose

CAD DXF Agent is a **local-first DXF layout editor** that uses LLM-assisted planning to edit 2D CAD drawings via natural-language prompts. Target users: engineers, architects, and CAD technicians who need to make bulk edits to DXF files without manual point-and-click work.

**Current State: Beta v0.2.0** — Core pipeline complete (297 tests, 68% coverage), web MVP deployed for external testing. Desktop GUI scaffolded but not production-ready.

**Revenue Model**: Not yet monetized. Future SaaS pricing likely based on edits/month or seats.

**Tech Foundation**:
- Python 3.11+ pipeline using `ezdxf` for DXF manipulation
- FastAPI backend on Cloud Run
- React + Vite frontend on Firebase Hosting
- Firebase Auth (anonymous + email/Google)
- Mock LLM provider (real Gemini via Vertex AI for live tests)

**Top Risk**: LLM hallucination producing invalid operations. Mitigated by strict schema validation — LLM never touches raw DXF, only returns structured JSON ops.

### Operational Status Matrix

| Environment | Status | URL | Notes |
|-------------|--------|-----|-------|
| Production (Web) | **Live** | https://cad-dxf-agent.web.app | Firebase Hosting + Cloud Run |
| Backend API | **Live** | https://cad-dxf-agent-web-186084840804.us-central1.run.app | Cloud Run |
| Local Dev | **Green** | localhost:3000 (FE) / localhost:8322 (BE) | `CAD_WEB_DEV_MODE=1` |
| CI | **Green** | GitHub Actions | Lint + format + type + tests on push |

### Technology Stack

| Category | Technology | Version | Purpose |
|----------|------------|---------|---------|
| Language | Python | 3.11+ | Core pipeline |
| DXF Library | ezdxf | 1.4.x | Read/write DXF |
| Web Framework | FastAPI | 0.115.x | HTTP API |
| Frontend | React + Vite | 18.x / 6.x | SPA |
| Auth | Firebase Auth | 11.x | Anonymous, email, Google |
| Hosting | Firebase Hosting | - | Static frontend |
| Backend Hosting | Cloud Run | - | Containerized API |
| CI/CD | GitHub Actions | - | Lint, test, deploy |
| LLM | Mock / Vertex AI Gemini | - | Planner backend |

---

## 2. System Architecture

### Pipeline Flow

```
User Prompt
    │
    ▼
┌─────────────────┐
│   dxf_reader    │  Load DXF via ezdxf → DrawingContext (Pydantic)
└────────┬────────┘
         │
         ▼
┌─────────────────┐
│ semantic_model  │  Build JSON context summary for LLM (no raw DXF exposed)
└────────┬────────┘
         │
         ▼
┌─────────────────┐
│    planner      │  Route to PlannerProvider → returns ChangeSet
└────────┬────────┘
         │
         ▼
┌─────────────────┐
│   validators    │  Check ops against RuleConfig (protected layers, distances)
└────────┬────────┘
         │
         ▼
┌─────────────────┐
│  preview_model  │  Generate human-readable change descriptions
└────────┬────────┘
         │
         ▼
┌─────────────────┐
│  edit_engine    │  Apply validated ops to working DXF copy
└────────┬────────┘
         │
         ▼
┌─────────────────┐
│ revision_notes  │  Insert deterministic notes on AI_REV_NOTES layer
└────────┬────────┘
         │
         ▼
┌─────────────────┐
│   dxf_writer    │  Save to new file (original untouched)
└─────────────────┘
```

### Web Architecture

```
┌──────────────────┐     ┌─────────────────────┐     ┌──────────────────┐
│  Firebase Auth   │────▶│   Firebase Hosting  │────▶│    Cloud Run     │
│  (ID Tokens)     │     │   (React SPA)       │     │   (FastAPI)      │
└──────────────────┘     └─────────────────────┘     └────────┬─────────┘
                                                              │
                              /api/** rewrite ────────────────┘
                                                              │
                                                   ┌──────────▼──────────┐
                                                   │  SessionManager     │
                                                   │  /tmp/cad-sessions/ │
                                                   │  (2h TTL)           │
                                                   └─────────────────────┘
```

### Key Architectural Rules

1. **LLM never touches raw DXF** — Returns structured `EditOperation` JSON only
2. **Protected layers block edits** — TITLE, TITLEBLOCK, SEAL, REVISION
3. **Revision notes are deterministic** — Generated from op metadata, never LLM freeform
4. **Save-as workflow** — Original file never modified
5. **V1 entity types** — LINE, LWPOLYLINE, TEXT, MTEXT, INSERT only

---

## 3. Directory Analysis

### Project Structure

```
cad-dxf-agent/
├── src/cad_dxf_agent/           # Core Python pipeline
│   ├── models/                  # Pydantic schemas
│   ├── core/                    # DXF I/O, validation, editing
│   ├── llm/                     # Planner, providers, prompts
│   ├── ui/                      # PySide6 desktop (not production)
│   └── settings.py              # Env-based config (CAD_* vars)
├── web/
│   ├── frontend/                # React + Vite SPA
│   │   ├── src/
│   │   │   ├── components/      # Workspace, Login, Footer, etc.
│   │   │   ├── hooks/           # useAuth.js
│   │   │   └── lib/             # firebase.js, api.js
│   │   └── dist/                # Production build
│   └── backend/
│       ├── main.py              # FastAPI app (all endpoints)
│       ├── auth.py              # Firebase token verification
│       ├── session.py           # SessionManager class
│       └── Dockerfile           # Cloud Run container
├── tests/
│   ├── unit/                    # ~270 tests
│   ├── integration/             # ~15 tests
│   ├── web/                     # ~65 tests (new)
│   └── live/                    # Live API tests (Vertex AI)
├── 000-docs/                    # Project documentation
├── .github/workflows/           # CI/CD
└── pyproject.toml               # Package config
```

### Critical Files

| File | Purpose |
|------|---------|
| `src/cad_dxf_agent/core/edit_engine.py` | Applies operations to DXF |
| `src/cad_dxf_agent/core/validators.py` | Validates ops against rules |
| `src/cad_dxf_agent/llm/planner.py` | LLM orchestration |
| `web/backend/main.py` | All API endpoints |
| `web/backend/session.py` | Session storage |
| `web/frontend/src/App.jsx` | App entry, routing |
| `web/frontend/src/components/Workspace.jsx` | Main editor UI |

---

## 4. Operational Reference

### Local Development Setup

**Prerequisites:**
- Python 3.11+
- Node.js 20+
- Firebase CLI (`npm install -g firebase-tools`)
- gcloud CLI (for Cloud Run deployment)

**Backend Setup:**
```bash
cd /home/jeremy/000-projects/cad-dxf-agent

# Create virtualenv and install
python3 -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"
pip install fastapi uvicorn python-multipart httpx firebase-admin

# Run backend (dev mode skips Firebase auth)
CAD_WEB_DEV_MODE=1 uvicorn web.backend.main:app --reload --port 8322
```

**Frontend Setup:**
```bash
cd web/frontend
npm install
npm run dev   # Runs on http://localhost:3000
```

**Environment Variables (.env):**
```bash
# Backend
CAD_LLM_PROVIDER=mock              # Use mock planner (no API key needed)
CAD_WEB_DEV_MODE=1                 # Skip Firebase auth locally
CAD_PROTECTED_LAYERS=TITLE,TITLEBLOCK,SEAL,REVISION

# Frontend (web/frontend/.env)
VITE_API_URL=http://localhost:8322
VITE_FIREBASE_API_KEY=...
VITE_FIREBASE_AUTH_DOMAIN=cad-dxf-agent.firebaseapp.com
VITE_FIREBASE_PROJECT_ID=cad-dxf-agent
```

### Running Tests

```bash
# All tests (297 unit + integration)
make test

# Web backend tests only (65 tests)
make test-web

# With coverage
make test-cov

# Live API tests (requires Vertex AI auth)
CAD_GCP_PROJECT=cad-dxf-agent pytest tests/live/ -v -m live_api -s

# Deployed smoke tests
CAD_WEB_URL=https://cad-dxf-agent.web.app pytest tests/live/test_deployed_smoke.py -v -m web_live -s
```

### Deployment Commands

**Frontend (Firebase Hosting):**
```bash
cd web/frontend
npm run build
firebase deploy --only hosting
# URL: https://cad-dxf-agent.web.app
```

**Backend (Cloud Run):**
```bash
# From project root
gcloud builds submit --config web/backend/cloudbuild.yaml .
# URL: https://cad-dxf-agent-web-186084840804.us-central1.run.app
```

**Full Deploy (CI):**
Push to `main` branch triggers GitHub Actions workflow that:
1. Runs lint, format, type checks
2. Runs all tests
3. Deploys frontend to Firebase Hosting
4. Deploys backend to Cloud Run via WIF (no secrets needed)

### API Endpoints

| Endpoint | Method | Auth | Purpose |
|----------|--------|------|---------|
| `/api/health` | GET | No | Health check |
| `/api/upload` | POST | Yes | Upload DXF/PDF file |
| `/api/plan` | POST | Yes | Generate edit plan |
| `/api/apply` | POST | Yes | Apply changes |
| `/api/render` | GET | Yes | Get PNG preview |
| `/api/download` | GET | Yes | Download edited DXF |

**Example: Upload + Plan + Apply**
```python
import httpx

# Get Firebase ID token (frontend handles this)
token = "eyJ..."

headers = {"Authorization": f"Bearer {token}"}

# Upload
with open("drawing.dxf", "rb") as f:
    resp = httpx.post(
        "https://cad-dxf-agent.web.app/api/upload",
        files={"file": ("drawing.dxf", f)},
        headers=headers
    )
session_id = resp.json()["session_id"]

# Plan
resp = httpx.post(
    "https://cad-dxf-agent.web.app/api/plan",
    json={"session_id": session_id, "prompt": "Move all text 10 units right"},
    headers=headers
)
operations = resp.json()["operations"]

# Apply
resp = httpx.post(
    "https://cad-dxf-agent.web.app/api/apply",
    json={"session_id": session_id},
    headers=headers
)

# Download
resp = httpx.get(
    f"https://cad-dxf-agent.web.app/api/download?session_id={session_id}",
    headers=headers
)
with open("edited.dxf", "wb") as f:
    f.write(resp.content)
```

---

## 5. Security & Access

### Authentication

- **Firebase Auth** with three providers:
  - Anonymous (default for beta testing)
  - Email/Password
  - Google OAuth

- **Backend validation**: All `/api/*` endpoints (except `/health`) require `Authorization: Bearer <id_token>` header
- **Token verification**: `firebase_admin.auth.verify_id_token()` in `web/backend/auth.py`

### Session Isolation

- Each upload creates a unique session in `/tmp/cad-sessions/{session_id}/`
- Sessions are tied to user UID
- Cross-user access returns 404 (not 403, to avoid enumeration)
- Sessions expire after 2 hours (TTL cleanup)

### Protected Layers

Operations targeting these layers are **blocked**:
- TITLE
- TITLEBLOCK
- SEAL
- REVISION

Configurable via `CAD_PROTECTED_LAYERS` env var.

### IAM (Google Cloud)

| Role | Who | Purpose |
|------|-----|---------|
| `roles/firebase.admin` | jeremy@intentsolutions.io, pablo@intentsolutions.io | Full Firebase access |
| `roles/run.admin` | GitHub Actions (WIF) | Deploy Cloud Run |
| `roles/iam.workloadIdentityUser` | GitHub Actions | WIF authentication |

---

## 6. Cost & Performance

### Monthly Cost Estimate (Beta)

| Service | Estimated Cost | Notes |
|---------|---------------|-------|
| Firebase Hosting | $0 | Spark plan (free tier) |
| Firebase Auth | $0 | First 50k MAU free |
| Cloud Run | ~$5-20 | Pay per request, min instances = 0 |
| Vertex AI (Gemini) | ~$0 | Mock mode default, live tests only |
| **Total** | **~$5-25/mo** | Beta traffic |

### Performance Baseline

| Operation | Target | Notes |
|-----------|--------|-------|
| DXF load (500 entities) | <100ms | ezdxf is fast |
| Plan generation (mock) | <50ms | No network |
| Plan generation (Gemini) | 2-5s | Network latency |
| Validation | <10ms | Pure Python |
| Apply changes | <100ms | ezdxf write |
| PNG render | 500ms-2s | matplotlib |
| End-to-end (mock) | <3s | Upload to download |

---

## 7. Current State Assessment

### What's Working

- **Core pipeline** (phases 1-9): 297 tests, 68% coverage
- **Web MVP deployed**: Firebase Hosting + Cloud Run
- **Anonymous auth**: Users can test without account
- **Full edit flow**: Upload → Plan → Apply → Download
- **CI/CD**: GitHub Actions with WIF (no secrets)
- **Dev mode**: `CAD_WEB_DEV_MODE=1` bypasses auth locally

### Known Issues

| Issue | Severity | Status |
|-------|----------|--------|
| PDF conversion untested in prod | Medium | Scaffolded, not wired |
| Desktop GUI not production-ready | Low | PySide6 scaffold only |
| No rate limiting | Medium | Cloud Run handles some |
| Session cleanup is manual | Low | TTL logic exists, cron not set |

### Recent Bug Fixes (2026-02-24)

1. **`source_prompt` field bug** — Changed to `prompt` in `web/backend/main.py:271`
2. **Anonymous auth not enabled** — Enabled via Identity Platform API
3. **Login gate removed** — Auto-signs in anonymously, goes straight to workspace

---

## 8. Quick Reference

### Command Map

| Task | Command |
|------|---------|
| Install deps | `pip install -e ".[dev]"` |
| Run tests | `make test` |
| Run web tests | `make test-web` |
| Local backend | `CAD_WEB_DEV_MODE=1 uvicorn web.backend.main:app --port 8322` |
| Local frontend | `cd web/frontend && npm run dev` |
| Build frontend | `cd web/frontend && npm run build` |
| Deploy frontend | `firebase deploy --only hosting` |
| Deploy backend | `gcloud builds submit --config web/backend/cloudbuild.yaml .` |
| Check coverage | `make test-cov` |
| Lint + format | `make check` |

### Critical URLs

| Resource | URL |
|----------|-----|
| Production Site | https://cad-dxf-agent.web.app |
| Cloud Run Backend | https://cad-dxf-agent-web-186084840804.us-central1.run.app |
| GitHub Repo | https://github.com/intent-solutions/cad-dxf-agent |
| Firebase Console | https://console.firebase.google.com/project/cad-dxf-agent |
| Cloud Run Console | https://console.cloud.google.com/run?project=cad-dxf-agent |

### Beta Testing Checklist

- [ ] Go to https://cad-dxf-agent.web.app
- [ ] Auto-signs in anonymously (no login required)
- [ ] Upload a DXF file
- [ ] Enter a natural language prompt (e.g., "Move all text 10 units right")
- [ ] Review the proposed changes
- [ ] Click Apply
- [ ] Download the edited file
- [ ] Verify changes in a CAD viewer

### First-Week Checklist (New DevOps)

- [ ] Clone repo and set up local dev environment
- [ ] Run `make test` — all 362 tests should pass
- [ ] Run local frontend + backend, upload a test DXF
- [ ] Review `web/backend/main.py` for API flow
- [ ] Review `src/cad_dxf_agent/core/edit_engine.py` for edit logic
- [ ] Deploy a test change to staging (if exists) or prod
- [ ] Set up gcloud ADC for Vertex AI live tests
- [ ] Review GitHub Actions workflow in `.github/workflows/`

---

## 9. Recommendations Roadmap

### Week 1 — Stabilization

- [ ] Add Cloud Run health checks and readiness probes
- [ ] Set up session cleanup cron (Cloud Scheduler)
- [ ] Add basic request logging (Cloud Logging)

### Month 1 — Hardening

- [ ] Add rate limiting (Cloud Armor or app-level)
- [ ] Implement proper PDF conversion testing
- [ ] Add Sentry or similar for error tracking
- [ ] Set up uptime monitoring (Cloud Monitoring)

### Quarter 1 — Scale

- [ ] Move sessions to Cloud Storage (for multi-instance)
- [ ] Add real LLM provider (Gemini) for production
- [ ] Implement user accounts with persistent history
- [ ] Add billing/usage tracking infrastructure

---

## Appendices

### A. Environment Variables Reference

| Variable | Default | Used In | Purpose |
|----------|---------|---------|---------|
| `CAD_LLM_PROVIDER` | `mock` | Backend | Planner backend |
| `CAD_PROTECTED_LAYERS` | `TITLE,TITLEBLOCK,SEAL,REVISION` | Backend | Protected layers |
| `CAD_REVISION_NOTES_ENABLED` | `true` | Backend | Insert revision notes |
| `CAD_REVISION_NOTES_LAYER` | `AI_REV_NOTES` | Backend | Layer for notes |
| `CAD_WEB_DEV_MODE` | _(unset)_ | Backend | Skip Firebase auth |
| `CAD_GCP_PROJECT` | _(unset)_ | Live tests | GCP project for Vertex AI |
| `CAD_WEB_URL` | _(unset)_ | Live tests | Deployed URL for smoke tests |
| `VITE_API_URL` | _(empty)_ | Frontend | Backend URL (empty = same origin) |
| `VITE_FIREBASE_*` | - | Frontend | Firebase config |

### B. Test Markers

```bash
# Run specific test categories
pytest -m "not slow"           # Skip slow tests
pytest -m smoke                # Smoke tests only
pytest -m integration          # Integration tests only
pytest -m web                  # Web backend tests only
pytest -m web_live             # Live deployed tests only
pytest -m live_api             # Vertex AI live tests
```

### C. Troubleshooting

**"Not authenticated" error locally:**
```bash
# Set dev mode to skip Firebase auth
export CAD_WEB_DEV_MODE=1
uvicorn web.backend.main:app --port 8322
```

**Tests fail with "No module named 'ezdxf'":**
```bash
# Use the virtualenv Python
.venv/bin/python -m pytest tests/
```

**Cloud Run deploy fails:**
```bash
# Check if WIF is configured
gcloud iam service-accounts list --project=cad-dxf-agent

# Manual deploy (authenticated)
gcloud run deploy cad-dxf-agent-web \
  --source web/backend \
  --region us-central1 \
  --project cad-dxf-agent
```

**Frontend shows old version after deploy:**
```bash
# Clear CDN cache
firebase hosting:channel:deploy live --only cad-dxf-agent

# Or force rebuild
cd web/frontend && rm -rf dist && npm run build && firebase deploy --only hosting
```

### D. Contact

- **Project Owner**: jeremy@intentsolutions.io
- **Client**: Tonatiuh Guadalupe Nava Razon (Universidad de Guadalajara)
- **GitHub Issues**: https://github.com/intent-solutions/cad-dxf-agent/issues

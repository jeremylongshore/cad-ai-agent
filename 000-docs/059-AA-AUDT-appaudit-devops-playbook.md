# IntentCAD (cad-dxf-agent): Operator-Grade System Analysis
*For: DevOps Engineer*
*Generated: 2026-03-07*
*Version: v0.6.0 (cba9400)*

## 1. Executive Summary

### Business Purpose

IntentCAD is a local-first DXF layout editor that uses LLM-assisted planning to edit 2D CAD drawings via natural-language prompts. Users upload architectural drawings (DXF or PDF), describe changes in plain English ("move column C-4 east by 10 feet"), and the system generates structured edit operations that are validated against safety rules before applying. Original files are never modified — every save produces a new file.

The system is in active Phase 6 development (EPIC-CAD-13/14/15), evolving from a CAD edit tool into an "Objective Intelligence" platform. It ships as both a PySide6 desktop app (Windows/Linux) and a React + FastAPI web app deployed on Google Cloud (Firebase Hosting + Cloud Run). The LLM backend is Gemini via Vertex AI, with a mock provider for CI determinism.

The core architectural invariant: **the LLM never touches DXF directly.** It returns structured JSON operations (`move_entity`, `edit_text`, `delete_entity`, `add_block`) which are validated against protected-layer rules before a deterministic edit engine applies them. This design eliminates a class of LLM hallucination risks at the architecture level.

Current risk profile: the system is well-tested (2,730 tests, 65% coverage threshold) with green CI, automated deploys via WIF, and comprehensive security scanning. Primary operational risks are session storage volatility (Cloud Run `/tmp`), single-region deployment, and the external ODA File Converter dependency for DWG support.

### Operational Status Matrix

| Environment | Status | Uptime Target | Release Cadence |
|-------------|--------|---------------|-----------------|
| Production (Web) | Active | Best-effort (Cloud Run default SLA) | Merge-to-main auto-deploy |
| Desktop | Builds available | N/A (local) | Tag-triggered (v* tags) |
| CI | Green (main) | N/A | Every push/PR |
| Staging | None (direct-to-prod) | N/A | N/A |

### Technology Stack

| Category | Technology | Version | Purpose |
|----------|------------|---------|---------|
| Language | Python | 3.11 / 3.12 | Core pipeline, backend |
| DXF Engine | ezdxf | >=1.3.0 | DXF read/write/entity manipulation |
| Data Models | Pydantic | >=2.0 | Schema validation, serialization |
| LLM | Gemini (Vertex AI) | gemini-2.5-flash | Edit planning, vision description |
| Backend | FastAPI + Uvicorn | >=0.115.0 | REST API for web frontend |
| Frontend | React 18 + Vite | 18.3.1 / 6.0.5 | SPA interface |
| DXF Viewer | dxf-viewer + Three.js | 1.0.46 / 0.183.2 | WebGL drawing preview |
| Auth | Firebase Authentication | 11.0.0 | Email/password + Google OAuth |
| Hosting | Firebase Hosting | — | Static SPA delivery |
| Compute | Cloud Run | — | Containerized backend (8Gi/4CPU) |
| Registry | Artifact Registry | — | Docker images (us-central1) |
| Tracing | OpenTelemetry → Cloud Trace | >=1.21 | Pipeline span instrumentation |
| Desktop UI | PySide6 | >=6.6 | Qt-based desktop shell |
| CI/CD | GitHub Actions | — | Lint, test, deploy (WIF auth) |
| Linting | Ruff | >=0.5 | Lint + format |
| Type Check | Mypy | >=1.10 | Static type analysis |
| Security | Bandit + pip-audit | — | SAST + dependency audit |
| Build | Hatchling + PyInstaller | — | Package + desktop executable |

## 2. System Architecture

### Architecture Diagram

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
               ┌──────────────────┼──────────────────┐
               ▼                  ▼                  ▼
     ┌──────────────┐  ┌──────────────┐  ┌──────────────┐
     │ Pipeline Core│  │  Vertex AI   │  │ Firebase     │
     │ (ezdxf,      │  │  Gemini API  │  │ Admin SDK    │
     │  validators, │  │  (WIF auth)  │  │ (token       │
     │  edit engine) │  │              │  │  validation) │
     └──────────────┘  └──────────────┘  └──────────────┘

Pipeline Flow:
  User Prompt → IntentRouter → Planner(Gemini) → ChangeSet
                                                     │
                    Validator ◄──────────────────────┘
                       │ (block protected layers, warn on large moves)
                       ▼
                  PreviewModel → user approval → EditEngine → Save-As DXF
                                                                  │
                                                        RevisionNotes (deterministic)

Desktop variant:
  PySide6 UI → same pipeline → local file I/O
       │
       └── Optional: Cloud Run proxy (shields users from GCP credentials)
```

### Failure Domains

| Domain | Impact | Mitigation |
|--------|--------|-----------|
| Gemini API down | No edit planning (read/compare still work) | Mock provider fallback in CI; timeout + retry with backoff |
| Cloud Run cold start | 5-15s latency spike | 8Gi memory, min-instances=0 (cost tradeoff) |
| Firebase Hosting | Frontend unavailable | CDN-backed, rarely fails |
| ODA binary missing | DWG uploads return 422 | DXF and PDF uploads unaffected; size-validated download in CI |
| `/tmp` session loss | Active session data lost on instance recycle | 2h TTL design; persistent store planned (EPIC-CAD-15) |

## 3. Directory Analysis

### Project Structure

```
cad-dxf-agent/
├── src/cad_dxf_agent/          # Core Python package (298 .py files, 54k LOC)
│   ├── models/                 # 20 Pydantic schemas (cad, ops, config, zone, etc.)
│   ├── core/                   # DXF I/O, validation, editing, preview, zone detection
│   │   └── comparison/         # Revision diff engine (14 modules, alignment/matching)
│   ├── llm/                    # Planner, providers (Gemini/mock), intent router, tools
│   │   └── stage_handlers/     # Stage pipeline handlers (analyze, detect_zones)
│   ├── cli/                    # cad-revision CLI (diff/align/bundle/explain)
│   ├── ui/                     # PySide6 desktop GUI
│   ├── settings.py             # Env-based configuration (all CAD_* prefixed)
│   ├── otel.py                 # OpenTelemetry bootstrap (off by default)
│   └── app.py                  # Desktop entry point
├── web/
│   ├── backend/                # FastAPI on Cloud Run
│   │   ├── main.py             # ~1900 lines — all API routes
│   │   ├── auth.py             # Firebase token validation
│   │   ├── session.py          # In-memory session manager
│   │   ├── Dockerfile          # Production image (Python 3.12-slim + ODA)
│   │   └── requirements.txt    # Backend-specific deps
│   ├── frontend/               # React 18 + Vite SPA
│   │   ├── src/pages/          # Upload, Editor, Compare, RevisionWizard
│   │   ├── src/components/     # Reusable UI components
│   │   ├── e2e/                # 9 Playwright test files
│   │   └── package.json        # Frontend deps
│   ├── firebase.json           # Hosting config + /api/** → Cloud Run rewrite
│   ├── firestore.rules         # All client reads/writes denied
│   └── .firebaserc             # Project: cad-dxf-agent
├── proxy/                      # Cloud Run proxy for desktop licensing
│   ├── main.py                 # FastAPI, rate-limited Gemini forwarder
│   └── Dockerfile              # 12-line minimal image
├── tests/                      # 120+ test modules, 43k LOC
│   ├── unit/                   # ~75 modules, schemas/validators/reader/writer/engine
│   ├── integration/            # Full pipeline, agent loop (ScriptedAgentProvider)
│   ├── web/                    # FastAPI TestClient endpoint tests
│   ├── benchmark/              # pytest-benchmark micro-benchmarks
│   ├── gui/                    # PySide6 tests (QT_QPA_PLATFORM=offscreen)
│   ├── property/               # Fuzz/property tests
│   ├── smoke/                  # Pipeline smoke tests
│   ├── live/                   # Real Gemini API tests (WIF in CI)
│   ├── eval/                   # Scorecard evaluation
│   ├── fixtures/               # DXF zoo, revision cases, trajectories, prompt bank
│   └── helpers/                # DXF factory, changeset factory, scripted provider
├── scripts/                    # Build, smoke test, eval runner, fixture downloads
├── 000-docs/                   # 58 architectural/planning documents
├── .github/workflows/          # 7 CI/CD workflows
├── Makefile                    # 68-line task runner
├── pyproject.toml              # Build config, tool settings, dep groups
└── .pre-commit-config.yaml     # Ruff, trailing whitespace, .env block, main protection
```

### Codebase Metrics (tokei)

| Language | Files | Code Lines | Comments | Blanks |
|----------|-------|------------|----------|--------|
| Python | 298 | 54,031 | 2,679 | 11,759 |
| JSON | 39 | 6,066 | 0 | 8 |
| JavaScript | 17 | 2,075 | 249 | 465 |
| JSX | 14 | 2,215 | 62 | 189 |
| CSS | 6 | 1,515 | 56 | 255 |
| **Total** | **386** | **66,022** | **3,177** | **12,717** |

## 4. Operational Reference

### Deployment Workflows

#### Local Development

1. **Prerequisites**: Python 3.11+, Node.js 22+, `gcloud` CLI
2. **Setup**:
   ```bash
   # Python backend
   pip install -e ".[dev]"
   pre-commit install
   gcloud auth application-default login  # One-time GCP auth

   # Create .env (gitignored)
   echo 'CAD_LLM_PROVIDER=gemini' > .env
   echo 'CAD_GCP_PROJECT=cad-dxf-agent' >> .env

   # Frontend
   cd web/frontend && npm ci
   ```
3. **Run**:
   ```bash
   # Backend on :8322
   CAD_WEB_DEV_MODE=1 uvicorn web.backend.main:app --port 8322

   # Frontend on :3000
   cd web/frontend && npm run dev
   ```
4. **Verification**: `make check` (lint → format → typecheck → test → smoke)

#### Production Deployment

**Normal path (automated)**: Merge PR to `main` touching `web/**` or `src/**` → GitHub Actions `deploy-web.yml` fires → builds Docker image → pushes to Artifact Registry → deploys Cloud Run → deploys Firebase Hosting. No manual steps.

**Pre-flight checklist**:
- [ ] All CI checks green on PR
- [ ] `make check` passes locally
- [ ] PR reviewed and approved
- [ ] No secrets in diff

**Manual deploy (emergency only)**:
```bash
# ALWAYS specify --project (local gcloud may point elsewhere)
cd web/frontend && npm run build
firebase deploy --only hosting --project cad-dxf-agent

gcloud run deploy cad-dxf-web \
  --source . --dockerfile web/backend/Dockerfile \
  --region us-central1 --project cad-dxf-agent \
  --allow-unauthenticated --memory 8Gi --cpu 4 --timeout 600 \
  --service-account cad-dxf-web-run@cad-dxf-agent.iam.gserviceaccount.com \
  --set-env-vars CAD_LLM_PROVIDER=gemini,CAD_GCP_PROJECT=cad-dxf-agent,OTEL_ENABLED=1,OTEL_EXPORTER=gcp-trace
```

**Do NOT use**: `gcloud builds submit --config cloudbuild.yaml` — `$SHORT_SHA` is only set by triggers, not manual submits.

**Rollback protocol**:
```bash
# List recent revisions
gcloud run revisions list --service cad-dxf-web --region us-central1 --project cad-dxf-agent

# Route traffic to previous revision
gcloud run services update-traffic cad-dxf-web \
  --to-revisions=PREVIOUS_REVISION=100 \
  --region us-central1 --project cad-dxf-agent
```

### Monitoring & Alerting

- **Cloud Trace**: All pipeline stages emit OTel spans (`cad.load_dxf`, `cad.run_planner`, `cad.validate`, `cad.build_context`, etc.). Enabled via `OTEL_ENABLED=1` + `OTEL_EXPORTER=gcp-trace`.
- **Cloud Run Logs**: `gcloud run services logs read cad-dxf-web --region us-central1 --project cad-dxf-agent`
- **CI Status**: `gh run list --workflow=ci.yml` and `gh run list --workflow=deploy-web.yml`
- **SLIs**: No formal SLOs defined yet. Cloud Run provides built-in request latency, error rate, and instance count metrics.
- **Dashboards**: GCP Console → Cloud Run → cad-dxf-web service page (built-in metrics)
- **On-call**: No rotation — single-developer project.

### Incident Response

| Severity | Definition | Response | Playbook |
|----------|------------|----------|----------|
| P0 | Web app completely down | Immediate — check Cloud Run status, rollback if deploy broke it | `gcloud run revisions list` → route traffic to last-good |
| P1 | Gemini API failures (edit planning broken) | 15 min — check Vertex AI status page, verify ADC credentials | Read-only features still work; users see "planning unavailable" |
| P2 | ODA converter missing (DWG uploads 422) | Next business day — rebuild with ODA .deb from GCS | DXF and PDF uploads unaffected |
| P3 | Test failures on main | Same day — fix or revert the breaking commit | `gh run list --workflow=ci.yml` → investigate |

## 5. Security & Access

### IAM

| Role | Purpose | Permissions | Where |
|------|---------|-------------|-------|
| `cad-dxf-web-run` SA | Cloud Run runtime | Vertex AI API, Cloud Trace, Artifact Registry read | GCP IAM |
| WIF (GitHub Actions) | CI/CD deploy | Cloud Run deploy, Artifact Registry push, Firebase deploy, GCS read | Federated via `WIF_PROVIDER` / `WIF_SERVICE_ACCOUNT` (GitHub vars, not secrets) |
| Firebase Admin SDK | Token validation | Firebase Auth read | Initialized in backend startup |

### Secrets Management

- **No stored secrets**: WIF provides tokenless authentication from GitHub Actions to GCP. No API keys, service account JSON files, or secrets in GitHub.
- **Firebase API keys**: Public-safe client config (hardcoded in `deploy-web.yml`). These are designed to be public per Firebase documentation.
- **Local dev**: `gcloud auth application-default login` provides ADC credentials. `.env` file is gitignored.
- **Break-glass**: If WIF breaks, manual deploy uses developer's own `gcloud auth` credentials with `--project cad-dxf-agent`.

### Pre-commit Security Gates

- `detect-private-key`: Blocks commits containing private keys
- `forbid-env-files`: Blocks `.env` file commits
- `no-commit-to-branch`: Prevents direct commits to `main`
- `check-added-large-files`: Blocks files >1MB (catches accidental binary commits)
- `bandit`: Python SAST on every CI run
- `pip-audit`: Dependency vulnerability scan on every CI run

## 6. Cost & Performance

### Monthly Costs (estimated)

- **Cloud Run**: ~$5-20/mo (low traffic, scale-to-zero, 8Gi/4CPU per request)
- **Vertex AI (Gemini)**: ~$10-50/mo (depends on edit volume; gemini-2.5-flash pricing)
- **Firebase Hosting**: Free tier (SPA CDN)
- **Firebase Auth**: Free tier (<50k MAU)
- **Artifact Registry**: ~$1/mo (container storage)
- **Cloud Trace**: Free tier (first 5M spans/mo)
- **Total**: ~$20-75/mo at current usage

### Performance Baseline

- **DXF load**: <100ms for 200-entity drawings, ~500ms for 1000-entity (benchmarked in `tests/benchmark/`)
- **Gemini planning**: 2-8s per edit prompt (network + inference)
- **Validation**: <1ms per operation
- **Edit engine**: <10ms per changeset application
- **Cloud Run cold start**: 5-15s (Python image + ODA libraries)
- **Web API P95**: ~3-10s end-to-end (dominated by Gemini latency)

## 7. Current State Assessment

### What's Working

- **Comprehensive CI**: Lint (ruff), format, typecheck (mypy), 2,730 tests, security scans — all automated on push/PR
- **Automated deploys**: Merge to main → GitHub Actions deploys both frontend + backend via WIF. Zero manual steps.
- **Multi-tier testing**: Unit, integration, web API, benchmarks, GUI, property/fuzz, smoke, live Gemini API, E2E Playwright
- **Safety architecture**: LLM never touches DXF directly; protected layers enforced; deterministic revision notes; save-as workflow
- **Modern tooling**: Pydantic schemas, Ruff linting, syrupy snapshots, pytest-benchmark, OpenTelemetry tracing
- **Strong documentation**: 58 docs covering architecture decisions, specs, audit reports, and epic AARs
- **WIF authentication**: No secrets stored anywhere — tokenless GCP access from CI

### Areas Needing Attention

- **No staging environment**: Production deploys go direct-to-prod. A staging Cloud Run service would catch deploy issues before users see them.
- **Session volatility**: Cloud Run `/tmp` sessions expire on instance recycle. EPIC-CAD-15 (Document Persistence) addresses this but isn't shipped yet.
- **Single-region**: Cloud Run only in `us-central1`. No multi-region failover.
- **No CODEOWNERS**: No automated review assignment for critical paths (`src/`, `web/`, `.github/`).
- **Mypy pre-existing errors**: 2 errors in `session_store.py` and `document_store.py` (`google.cloud.storage` not typed). Not blocking but noisy.
- **Proxy service**: Not deployed via CI — ad-hoc manual deploys. No monitoring.
- **ODA dependency**: External binary downloaded from GCS. If the bucket or file is lost, DWG support breaks. Document acquisition process.
- **Desktop build**: Windows-only PyInstaller builds. Linux desktop builds not automated.
- **No dependency pinning**: `pyproject.toml` uses `>=` ranges. No lock file for reproducible builds.

### Immediate Priorities

1. **[High]** Add CODEOWNERS file — ensure PR reviews on `src/`, `web/`, `.github/` changes. Owner: DevOps. Effort: 10 min.
2. **[High]** Pin CI action versions to SHA — `actions/checkout@v6` → `@<sha>` to prevent supply chain attacks. Owner: DevOps. Effort: 30 min.
3. **[Medium]** Create staging Cloud Run service — deploy to `cad-dxf-web-staging` before production. Owner: DevOps. Effort: 2h.
4. **[Medium]** Fix mypy pre-existing errors — add `google-cloud-storage` stubs or suppress cleanly. Owner: Dev. Effort: 30 min.
5. **[Medium]** Document ODA .deb acquisition — where it comes from, how to update, how to recover if GCS bucket is lost. Owner: DevOps. Effort: 1h.
6. **[Low]** Add `pip-compile` or `uv.lock` for reproducible Python builds. Owner: Dev. Effort: 1h.
7. **[Low]** Automate proxy deploys via CI. Owner: DevOps. Effort: 2h.

## 8. Quick Reference

### Command Map

| Capability | Command | Notes |
|------------|---------|-------|
| Install + setup | `pip install -e ".[dev]" && pre-commit install` | Editable install with all dev deps |
| All quality checks | `make check` | lint → format → typecheck → test → smoke |
| Lint only | `make lint` | `ruff check src/ tests/` |
| Format only | `make format` | `ruff format src/ tests/` |
| Type check | `make typecheck` | `mypy src/` |
| All tests | `.venv/bin/python -m pytest -v` | System pytest may lack ezdxf |
| Unit tests only | `make test-unit` | ~1,100 tests, <10s |
| Web API tests | `make test-web` | FastAPI TestClient, ~120 tests |
| Live Gemini tests | `make test-live` | Requires `gcloud auth application-default login` |
| Coverage report | `make test-cov` | Threshold: 65% |
| Security scan | `make security` | `bandit -r src/ -ll && pip-audit` |
| Smoke test | `make smoke` | Full pipeline with mock provider |
| Local backend | `CAD_WEB_DEV_MODE=1 uvicorn web.backend.main:app --port 8322` | Skips Firebase auth |
| Local frontend | `cd web/frontend && npm run dev` | Vite on :3000 |
| Desktop app | `make run` | Requires `pip install -e ".[gui]"` |
| Build executable | `make build` | PyInstaller → `dist/cad-dxf-agent/` |
| Revision CLI | `cad-revision diff master.dxf rev.dxf --output-dir ./out` | Compare two DXFs |
| Deploy status | `gh run list --workflow=deploy-web.yml` | Latest deploy results |
| Cloud Run logs | `gcloud run services logs read cad-dxf-web --region us-central1 --project cad-dxf-agent` | Recent request logs |
| Rollback | See Section 4 rollback protocol | Traffic splitting to previous revision |

### Critical URLs

- **Production**: https://cad-dxf-agent.web.app
- **Cloud Run service**: `gcloud run services describe cad-dxf-web --region us-central1 --project cad-dxf-agent`
- **CI/CD**: https://github.com/jeremylongshore/cad-dxf-agent/actions
- **Artifact Registry**: `us-central1-docker.pkg.dev/cad-dxf-agent/cad-dxf-agent/web-backend`
- **Firebase Console**: https://console.firebase.google.com/project/cad-dxf-agent
- **GCP Console**: https://console.cloud.google.com/run?project=cad-dxf-agent
- **Cloud Trace**: https://console.cloud.google.com/traces?project=cad-dxf-agent

### First-Week Checklist

- [ ] GCP access granted (`gcloud auth login` with project `cad-dxf-agent`)
- [ ] GitHub repo access (push to branches, not main)
- [ ] `gcloud auth application-default login` for local Gemini access
- [ ] `pip install -e ".[dev]"` + `pre-commit install`
- [ ] `make check` passes locally (all green)
- [ ] Understood pipeline flow: load → plan → validate → preview → apply → save
- [ ] Run `make smoke` to see full pipeline execute with mock provider
- [ ] Reviewed CLAUDE.md (project conventions, commit format, PR template)
- [ ] Read 000-docs/000-INDEX.md for doc inventory
- [ ] Completed a local web dev session (upload DXF → prompt → preview → apply)
- [ ] Reviewed `deploy-web.yml` to understand the auto-deploy pipeline
- [ ] Understood WIF authentication (no secrets — vars in GitHub repo settings)

## 9. Recommendations Roadmap

### Week 1 — Stabilization

- [ ] Add CODEOWNERS file (`src/ @jeremylongshore`, `web/ @jeremylongshore`, `.github/ @jeremylongshore`)
- [ ] Pin GitHub Actions to SHA digests (prevent supply chain compromise)
- [ ] Fix 2 pre-existing mypy errors (google.cloud.storage typing)
- [ ] Document ODA .deb acquisition process in 000-docs/

### Month 1 — Foundation

- [ ] Create staging Cloud Run service (`cad-dxf-web-staging`) with separate deploy step
- [ ] Add `uv.lock` or `pip-compile` for reproducible Python builds
- [ ] Set up Cloud Run min-instances=1 if latency matters (cost: ~$10/mo extra)
- [ ] Add basic uptime monitoring (Cloud Monitoring uptime check on `/api/health`)
- [ ] Automate proxy service deploys via CI
- [ ] Add Dependabot or Renovate for automated dependency updates

### Quarter 1 — Strategic

- [ ] Multi-region Cloud Run deployment (if user base expands beyond US)
- [ ] Persistent session storage (completing EPIC-CAD-15 work)
- [ ] Load testing with realistic DXF files (establish P50/P95/P99 baselines)
- [ ] Cost alerting (GCP budget alerts on the cad-dxf-agent project)
- [ ] Formal SLOs: 99.5% availability, P95 latency < 10s for edit prompts
- [ ] Desktop auto-update mechanism (currently manual download of new builds)

## Appendices

### A. Environment Variables Reference

| Variable | Default | Purpose |
|----------|---------|---------|
| `CAD_LLM_PROVIDER` | `mock` | `gemini` for prod/dev, `mock` for CI |
| `CAD_GCP_PROJECT` | _(none)_ | GCP project ID (required for Vertex AI) |
| `CAD_GCP_LOCATION` | `us-central1` | Vertex AI region |
| `CAD_GEMINI_MODEL` | `gemini-2.5-flash` | Gemini model for planning |
| `CAD_VISION_MODEL` | `gemini-2.5-flash` | Gemini model for vision description |
| `CAD_PROTECTED_LAYERS` | `TITLE,TITLEBLOCK,SEAL,REVISION` | Layers the LLM cannot edit |
| `CAD_REVISION_NOTES_ENABLED` | `true` | Insert deterministic revision notes |
| `CAD_REVISION_NOTES_LAYER` | `AI_REV_NOTES` | Layer for revision notes |
| `CAD_LLM_TEMPERATURE` | `0.0` | Gemini temperature (0 = deterministic) |
| `CAD_LLM_MAX_OUTPUT_TOKENS` | `4096` | Max response tokens |
| `CAD_PLANNER_TIMEOUT` | `60` | Planner timeout (seconds) |
| `CAD_PLANNER_MAX_RETRIES` | `2` | Retry count on planner failure |
| `CAD_RENDER_DPI` | `150` | PNG render resolution |
| `CAD_MAX_UNDO_SNAPSHOTS` | `50` | Edit history depth |
| `CAD_VISION_ENABLED` | `true` | Enable DXF → image → description pipeline |
| `CAD_ODA_PATH` | _(auto)_ | ODA File Converter path (DWG support) |
| `CAD_WEB_DEV_MODE` | _(unset)_ | Skip Firebase auth for local dev (`1`) |
| `CAD_WEB_CORS_ORIGIN` | _(unset)_ | Additional CORS origin |
| `CAD_PROXY_URL` | _(unset)_ | Cloud Run proxy for desktop |
| `CAD_LICENSE_KEY` | _(unset)_ | Proxy authentication key |
| `OTEL_ENABLED` | _(unset)_ | Enable tracing (`1`, `true`, `yes`) |
| `OTEL_EXPORTER` | `console` | `console`, `otlp`, or `gcp-trace` |
| `OTEL_EXPORTER_OTLP_ENDPOINT` | _(unset)_ | OTLP collector URL |

### B. CI/CD Workflows

| Workflow | Trigger | Jobs | Duration |
|----------|---------|------|----------|
| `ci.yml` | Push to main, all PRs | lint, typecheck, test (matrix 3.11+3.12), benchmark (main only), live-test (main only) | ~3-5 min |
| `deploy-web.yml` | Push to main (web/src changes), manual | deploy-backend (Docker → Cloud Run), deploy-frontend (npm → Firebase) | ~5-8 min |
| `security.yml` | Push to main, all PRs | bandit, pip-audit | ~2 min |
| `build-windows.yml` | Tag push (v*), manual | PyInstaller build, Inno Setup installer, upload artifacts | ~10 min |
| `gemini-review.yml` | PRs | CodeRabbit AI review | ~2 min |
| `publish-pypi.yml` | Manual | PyPI publish | ~2 min |
| `release-dryrun.yml` | Manual | Validate release artifacts | ~3 min |

### C. Test Tiers

| Tier | Location | Count | Runner | Notes |
|------|----------|-------|--------|-------|
| Unit | `tests/unit/` | ~1,100 | `make test-unit` | Fast, mocked, all CI runs |
| Integration | `tests/integration/` | ~78 | `make test-integration` | Full pipeline, ScriptedAgentProvider |
| Web API | `tests/web/` | ~123 | `make test-web` | FastAPI TestClient |
| Benchmark | `tests/benchmark/` | ~15 | CI (main only) | pytest-benchmark, JSON artifacts |
| GUI | `tests/gui/` | ~10 | Manual | Requires `QT_QPA_PLATFORM=offscreen` |
| Property | `tests/property/` | ~7 | CI | Randomized, bounded runtime |
| Smoke | `tests/smoke/` | ~7 | `make smoke` | End-to-end mock pipeline |
| Live API | `tests/live/` | varies | CI (main only) | Real Gemini via WIF |
| E2E | `web/frontend/e2e/` | 9 | Manual / Playwright | Browser-level web flows |
| Eval | `tests/eval/` | varies | `make scorecard` | Intent accuracy scorecard |

### D. Glossary

| Term | Meaning |
|------|---------|
| **DrawingContext** | Normalized Pydantic model of a loaded DXF (entities, layers, blocks, metadata) |
| **EntityRef** | Single DXF entity reference (handle, type, layer, position, text, block) |
| **ChangeSet** | Batch of EditOperations from a single user prompt |
| **OpType** | Edit operation type: `move_entity`, `edit_text`, `delete_entity`, `add_block` |
| **Protected layer** | Layer that cannot be edited (TITLE, TITLEBLOCK, SEAL, REVISION) |
| **TaskFamily** | Intent category from the router (QNA, EDIT_PLAN, COMPARE, SUMMARY, etc.) |
| **RequestClass** | Objective axis 1: what kind of response (understand, estimate, modify, etc.) |
| **ObjectiveTag** | Objective axis 2: what the user wants to achieve (cost_reduction, space_count, etc.) |
| **WIF** | Workload Identity Federation — GCP's secretless auth for CI/CD |
| **ADC** | Application Default Credentials — local GCP auth via `gcloud auth application-default login` |
| **ODA** | Open Design Alliance File Converter — DWG → DXF conversion tool |
| **Save-as** | Architectural invariant: original files are never modified; edits produce new files |

### E. Troubleshooting Playbooks

**Tests fail with `ModuleNotFoundError: No module named 'ezdxf'`**:
System pytest doesn't have project deps. Use `.venv/bin/python -m pytest -v` instead of bare `pytest`.

**`make check` mypy fails on `google.cloud.storage`**:
Pre-existing issue (2 errors in session_store.py and document_store.py). Safe to ignore. New code should pass cleanly.

**Cloud Run deploy fails**:
1. Check `gh run list --workflow=deploy-web.yml` for the failing step
2. Verify WIF vars are set: `gh variable list` (should show `WIF_PROVIDER`, `WIF_SERVICE_ACCOUNT`, `GCP_PROJECT_ID`)
3. Check Artifact Registry permissions: the WIF service account needs `roles/artifactregistry.writer`

**ODA .deb download fails in CI**:
1. Check GCS bucket: `gsutil ls gs://cad-dxf-agent-deps/oda/`
2. If missing, DWG support is unavailable but DXF/PDF uploads work fine
3. Size validation catches corrupt downloads (<1MB = skip install)

**Session data lost after edit**:
Cloud Run instances recycle. Session data in `/tmp` is ephemeral. User needs to re-upload. This is by design until EPIC-CAD-15 ships persistent storage.

### F. Open Questions

1. Should the proxy service be included in CI/CD? Currently manual deploy.
2. Is a staging environment worth the cost (~$10/mo) at current traffic levels?
3. Should we add `dependabot.yml` for automated dependency PRs?
4. Desktop auto-update: embed update check in PySide6 app startup?
5. Multi-region: is there user demand outside US that justifies the complexity?

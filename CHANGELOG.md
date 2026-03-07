# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

## [0.6.0] - 2026-03-07

### Added
- **EPIC-CAD-02: Core Contracts + Routing Foundation**: `PlatformResponse` envelope, `TaskFamily` taxonomy, `IntentRouter` with heuristic classification, `CapabilityRegistry` (#74, #75)
- **EPIC-CAD-03: Selection + Markup Interpretation**: `RegionSchema`, `MarkupParser`, `RegionAssociator`, `SelectionDebug` for region-based entity selection (#77)
- **EPIC-CAD-04: Region Q&A Vertical Slice**: Deterministic Q&A pipeline with 8 question types, template-based answers, 6 golden trajectories (#78)
- **EPIC-CAD-05: Repeated-Condition Detection**: 6-signal similarity scoring, spatial clustering, preview/approval workflow (#81)
- **EPIC-CAD-06: Compare + Diff Service Hardening**: Typed compare schema, text-trust scorer, changelog enrichment, export package (#82)
- **SIDEQUEST-CAD-67: Text Positional Accuracy**: `TextGeometry` + `TextProvenance` models, trust hierarchy (NATIVE > BLOCK > VECTOR > OCR), enhanced extraction (#79)
- **Multi-user Workspace**: Google auth integration with email allowlist for team access (#80)
- **IntentCAD Rebrand**: Updated web UI branding and polished login page

### Fixed
- Firestore rules deploy made non-blocking for CI stability
- PDF text display and color detection improvements (#72)

### Changed
- Test count: 1375 → 1924 tests
- Coverage: 95% → 95.24%
- Golden trajectories: 5 → 15 (qna, repeated_condition, edit_plan families)
- Task families tested: 2 → 4

### Documentation
- EPIC-CAD-01: 8 foundation documents (capability audit, target architecture, evaluation plan, roadmap, etc.)
- ARCH-REVIEW-CAD-01: 10-dimension architecture review with CONDITIONAL GO for EPIC-CAD-07 (#84)
- After-action reports for EPIC-CAD-02 and EPIC-CAD-03

## [0.5.0] - 2026-03-06

### Added
- **Interactive WebGL Viewer**: Hardware-accelerated DXF rendering with pan/zoom/rotate in browser (#63)
- **Compare Tab UX Overhaul**: Streamlined revision comparison workflow with improved side-by-side views (#65)
- **DWG on Cloud Run**: Server-side DWG-to-DXF conversion via ODA File Converter for web uploads

### Fixed
- Filter sub-pixel noise entities from PDF extraction to reduce false matches (#68)
- PDF entity colors, classifier heuristics, and render quality guard (#67)
- E2E global auth setup and sidebar close behavior (#66)
- Fetch timeouts, friendly error messages, and request logging in web backend
- Anonymous Firebase users bypass license check (#auth)
- Docker ODA install made optional with file-size guard (#docker)
- E2E test stability: sourced upload batching, suggestion chips, alignment confidence

### Changed
- Test count: 1150 → 1375 tests
- Coverage: 89% → 95% across all modules (#61)
- E2E suite: +36 tests (interactive viewer, sourced uploads)

### Dependencies
- Bump docker/login-action from 3 to 4 (#69)

## [0.4.0] - 2026-03-02

### Added
- **Revision Workflow**: Complete upload → align → review → approve → export pipeline (#60)
  - Alignment ladder with Kabsch rigid transform for geometric alignment (#48)
  - Confidence-scored entity matching with MatchExplanation (#49, #60)
  - Per-op approve/reject with bulk actions in web wizard (#60)
  - Bundle export with alignment_result.json, file hashes, changelog (#50, #60)
- **DWG Support**: Server-side ODA File Converter integration with license gating (#59)
- **Comparison Profiles**: Structural filtering presets (e.g., `structural`, `electrical`) (#55-#57)
  - `ComparisonProfile` schema with layer/entity filters and tolerance settings
  - Titleblock auto-detection to exclude border regions (#58)
  - Profile warnings when >25% entities filtered
- **Revision CLI**: `cad-revision` command for headless revision pipeline
- **Web Enhancements**:
  - Chat UX overhaul with progressive loading, suggestions, history (#39, #41)
  - Separate Apply/Download flow with edited preview (#34)
  - Clear conversation button
  - Playwright E2E tests against deployed app
- Canonical model with stable entity IDs for revision workflow (#47)
- Revision test corpus with clean/nasty taxonomy (#51)
- Manual control-point alignment for large offset drawings (#52)
- Integration tests for alignment ladder orchestrator (#53)
- DiffSummary with headline, per-layer counts, and warnings (#60)
- Xref and dynamic block detection with graceful warnings (#60)
- Semantic DXF validation in E2E + GUI tests (#35)
- Gemini API key provider (`gemini-key`) option

### Fixed
- OpenTelemetry tracing in production Cloud Run (#36, #37)
- Dedicated Cloud Run service account + OTEL env vars in CI deploy (#37)
- Firebase rewrite 401 handling + planner token explosion (#38)
- Silent render failures now surface errors (#38)
- Web layout: drawing preview center, chat sidebar
- Add pymupdf to backend deps for PDF upload support
- Qt event loop flush after QThread.wait() in GUI tests
- CI: GUI module coverage exclusion, web test deps, Qt system package for Noble
- Docker build in GH Actions instead of Cloud Build --source
- UTF-8 encoding for changelog file writes (Windows compatibility)
- Pre-existing lint and test collection failures

### Changed
- Test count: 578 → 1150+ tests (coverage 68%)
- 141 files changed, +19654 lines since v0.3.0

### Dependencies
- Bump google-github-actions/auth from 2 to 3 (#46)
- Bump google-github-actions/deploy-cloudrun from 2 to 3 (#42)
- Bump actions/upload-artifact from 6 to 7 (#45)
- Bump actions/setup-node from 4 to 6 (#43)
- Bump Minionguyjpro/Inno-Setup-Action from 1.2.4 to 1.2.7 (#44)

## [0.3.0] - 2026-02-25

### Added
- Wire OpenTelemetry init in web backend lifespan, enabling all 7 pipeline spans for web requests (#32)
- Google Cloud Trace exporter option (`OTEL_EXPORTER=gcp-trace`) with ADC support on Cloud Run (#33)
- `gcp-trace` optional dependency group in pyproject.toml
- Web OTel tests verifying spans propagate through upload→plan flow

### Changed
- Test count: 573 → 578 tests (coverage maintained at 68%)

### Fixed
- Ruff format compliance across codebase (9 files reformatted)

## [0.2.0] - 2026-02-24

### Added
- **Web MVP**: Firebase Hosting frontend + Cloud Run backend with 65-test suite (#31)
- Paper space / layout editing support (#15)
- Windows packaging & installer infrastructure (#16)
- Live Gemini API test infrastructure with WIF-based CI (#17, #19)
- Responsive pipeline with QThread worker and progress UI (#23)
- Planner hardening: drawing stats, deterministic execution, trace view (#24, #25)
- Vision pipeline integration with PDF-to-edit conversion (#28)
- Validation feedback loop for planner self-correction
- Live PDF-to-edit full journey tests
- v0.2.0 testing infrastructure: ScriptedAgentProvider, golden trajectories, syrupy snapshots (#14)
- Max snapshots cap to EditHistory (default 50) (#26)
- Validator micro-benchmarks in CI (#27)
- Beta testing DevOps operations playbook

### Fixed
- Handle pymupdf 1.27 quad item API change in PDF converter (#29)
- Web backend deps: google-cloud-aiplatform and matplotlib
- Strip mocks from web test suite, fix anonymous auth error handling (#31)
- Use ADC auto-detection for live API tests instead of env var (#18)
- Broaden live test error expectations for GCP API responses (#20)
- Resolve critical audit findings for v0.1.0 (#22)

### Changed
- Test count: 222 → 573 tests (coverage 68%)
- Planner now uses compact summaries by default to reduce token usage

## [0.1.0] - 2026-02-20

### Added
- Initial project scaffolding and repository structure
- DXF reader/writer with ezdxf (model space + paper space layouts)
- Expanded entity type support: LINE, LWPOLYLINE, TEXT, MTEXT, INSERT, CIRCLE, ARC, DIMENSION, HATCH, SPLINE, POLYLINE, ELLIPSE, MLEADER, SOLID, LEADER
- Pydantic schemas for operations, entities, and configuration
- Validator engine with protected layer/block enforcement
- AI revision notes module (deterministic, safe layer insertion)
- Mock LLM planner for offline testing
- Tool-use agent provider with Gemini integration (#12)
- Proxy client for Cloud Run deployment (#12)
- PySide6 desktop UI with undo/redo support (#12)
- DWG/PDF conversion layer with ODA File Converter support (#10)
- PDF to DXF conversion with PyMuPDF and arc-fitting heuristic (#13)
- PNG/PDF rendering for drawing preview (#10)
- Gemini vision pipeline provider on Vertex AI (#11)
- Entity index with spatial and text search (#8)
- Progressive context disclosure for LLM agents (#13)
- Compact drawing summaries to reduce token usage (#13)
- OpenTelemetry instrumentation for pipeline observability (#5)
- GitHub Actions CI/CD (lint, test, security)
- Pre-commit hooks (ruff, formatting checks)
- ADR documents for key architectural decisions
- V1 blueprint and beads planning documents
- Smoke test harness with programmatic DXF fixture
- 222 tests with comprehensive coverage

### Fixed
- Entity parsing for DIMENSION entities without insert points (#13)
- PDF conversion quality with PyMuPDF Bezier curve extraction (#13)
- LLM context overload by using compact summaries instead of full entity dumps (#13)

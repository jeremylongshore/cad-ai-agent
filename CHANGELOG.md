# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

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

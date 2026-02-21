# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

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

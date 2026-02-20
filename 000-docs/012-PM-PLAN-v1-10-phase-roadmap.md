# 012-PM-PLAN — V1 Ten-Phase Roadmap

**Date:** 2026-02-20
**Category:** PM (Project Management)
**Type:** PLAN (Roadmap)

---

## Overview

The cad-dxf-agent V1 build follows a ten-phase progression from bare repo to shippable desktop application. Each phase has clear entry criteria, deliverables, and exit criteria. Phases are sequential — a phase cannot start until the previous phase's exit criteria are met.

### V1 constraints (apply to all phases)

- Local-first: all DXF processing happens on the user's machine
- DXF only, 2D only, model space only
- Supported entity types: LINE, LWPOLYLINE, TEXT, MTEXT, INSERT
- The LLM returns structured operations (never raw DXF); a deterministic tool applies them
- The validator protects configured layers from edits
- No title block revision table writes; revision notes go to the AI_REV_NOTES layer
- Save-as workflow: the original file is never modified

---

## Phase 1 — Repository foundation, CI/CD, security baseline, and beads scaffolding

**Status:** Complete
**Beads epic:** `cad-6kc.1`
**AAR:** [010-AA-AACR-phase-01-aar.md](010-AA-AACR-phase-01-aar.md)

**Deliverables:**
- Git repo with governance files, issue templates, and PR template
- `pyproject.toml` with hatchling build, tooling config, and dependency groups
- Pre-commit hooks (ruff, trailing whitespace, no .env commits, no direct main commits)
- GitHub Actions CI (lint, typecheck, test — matrix: ubuntu+windows, Python 3.11+3.12)
- GitHub Actions security workflow (bandit, pip-audit, dependency review)
- Settings module with env var loading
- Minimal PySide6 window shell
- Beads V1 plan with six-epic task breakdown
- Three ADR documents, V1 blueprint, PRD addendum

**Exit criteria:**
- CI green on main
- `pip install -e ".[dev]"` succeeds
- `pre-commit run --all-files` passes
- PySide6 window opens

---

## Phase 2 — Core data schemas, DXF read/write contracts, fixture strategy, and test plan

**Status:** In progress (planning only, no implementation code)
**Beads epic:** `cad-xoh`

**Deliverables:**
- Pydantic schema specifications for all domain models (EntityRef, DrawingContext, EditOperation, ChangeSet, ValidationResult, RuleConfig)
- DXF reader contract (input/output, supported entities, field extraction, ID strategy)
- DXF writer contract (save-as behavior, preservation guarantees, roundtrip definition)
- Fixture strategy (programmatic DXF generation, all V1 entity types, determinism)
- Unit and roundtrip test plan (test matrix, CI expectations, coverage targets)

**Exit criteria:**
- All schema specifications documented with strictness rules and error behavior
- Reader and writer I/O contracts defined
- Fixture spec covers all V1 entity types
- Test matrix documented; CI can run all tests without API keys

---

## Phase 3 — Implement Pydantic schemas and DXF reader

**Status:** Not started
**Depends on:** Phase 2

**Deliverables:**
- Pydantic models: EntityType, Point2D, EntityRef, LayerRule, DrawingContext
- DXF reader module (model space entities, V1 types only, skip unsupported with warnings)
- Entity index (lookup by handle, layer, type)
- Semantic model (JSON-serializable planner context builder)
- Unit tests for schemas, reader, and index
- Programmatic DXF test fixtures

**Exit criteria:**
- `load_dxf()` loads a sample DXF and returns a valid DrawingContext
- Entity index lookups return correct results
- Unsupported entity types logged but not fatal
- All unit tests pass

---

## Phase 4 — Operation model and validator engine

**Status:** Not started
**Depends on:** Phase 3

**Deliverables:**
- OpType enum (move_entity, edit_text, delete_entity, add_block)
- EditOperation and ChangeSet Pydantic models
- ValidationResult with severity levels (blocker vs warning)
- RuleConfig with protected layers and blocks
- Validator: protected layer check, move param checks, edit_text checks, missing entity handle, add_block checks
- Unit tests for every validator path

**Exit criteria:**
- Validator blocks operations on protected layers
- Validator blocks NaN/Inf coordinates, missing params
- Warnings (e.g., large move distance) don't block apply
- All validator tests pass with 100% path coverage

---

## Phase 5 — LLM planner interface and mock provider

**Status:** Not started
**Depends on:** Phase 4

**Deliverables:**
- PlannerProvider abstract interface with `plan()` method
- MockProvider (keyword-based, works offline)
- Response parser (JSON string to validated ChangeSet)
- Prompt templates for future real LLM integration
- Planner orchestrator (`get_provider()`, `run_planner()`)
- Unit tests for parser and mock provider (no API key needed)

**Exit criteria:**
- MockProvider returns valid operations for move/delete/text prompts
- Response parser accepts valid JSON, rejects malformed input
- All tests pass without any API key

---

## Phase 6 — Edit engine and DXF writer

**Status:** Not started
**Depends on:** Phase 5

**Deliverables:**
- EditEngine: move_entity, edit_text, delete_entity, add_block implementations
- DXF writer (save-as new file, original untouched)
- AppliedChange records for each operation

**Exit criteria:**
- Each operation type modifies the DXF correctly via ezdxf
- Save produces a valid DXF file
- Original file hash unchanged after save
- Unit tests for each operation type

---

## Phase 7 — Preview model and AI revision notes

**Status:** Not started
**Depends on:** Phase 6

**Deliverables:**
- PreviewModel: human-readable change summary
- Revision note text generation (deterministic, from operation metadata, never LLM output)
- Revision note DXF insertion (AI_REV_NOTES layer)
- RevisionNoteConfig (anchor point, text height, prefix, toggle)
- Unit tests for note generation and preview

**Exit criteria:**
- Preview accurately describes all proposed changes
- Revision notes are deterministic and reproducible
- Notes appear on AI_REV_NOTES layer, never on protected layers

---

## Phase 8 — End-to-end integration and smoke tests

**Status:** Not started
**Depends on:** Phase 7

**Deliverables:**
- Standalone smoke test script (`scripts/smoke_test.py`)
- Pytest smoke test suite (`tests/smoke/`)
- End-to-end verification: load → plan → validate → preview → apply → save → verify
- Protected layer enforcement verified in E2E context
- Original file preservation verified in E2E context

**Exit criteria:**
- `python scripts/smoke_test.py` exits 0
- `pytest -m smoke` passes
- Full pipeline works with mock provider, no API key

---

## Phase 9 — Desktop UI wiring

**Status:** Not started
**Depends on:** Phase 8

**Deliverables:**
- MainWindow wired to full pipeline
- Open DXF button → file picker → load
- Prompt text input → Plan & Preview button → display preview
- Apply & Save As button → apply changeset → save new file
- Status bar with progress feedback
- Error display for validation blockers

**Exit criteria:**
- User can complete full workflow via the desktop window
- Protected layer violations display as blockers in UI
- Save-as dialog produces new file

---

## Phase 10 — QA hardening, documentation, and V1 release

**Status:** Not started
**Depends on:** Phase 9

**Deliverables:**
- README with quickstart, mock test instructions, architecture overview
- V1 blueprint document
- PRD addendum with acceptance criteria
- Final CI verification (lint, typecheck, test, security — all green)
- CHANGELOG entry for V1
- Release tag

**Exit criteria:**
- `make check` passes (lint → format → typecheck → tests → smoke)
- Security scan clean (bandit, pip-audit)
- All documentation accurate and up to date
- Git tag created for V1 release

---

## Dependency chain

```
Phase 1 → Phase 2 → Phase 3 → Phase 4 → Phase 5 → Phase 6 → Phase 7 → Phase 8 → Phase 9 → Phase 10
```

Each phase depends on the previous one completing its exit criteria.

## Beads epic mapping

| Phase | Beads ID | Status |
|-------|----------|--------|
| 1 | `cad-6kc.1` | Complete |
| 2 | `cad-xoh` | In progress |
| 3 | — | Not started |
| 4 | — | Not started |
| 5 | — | Not started |
| 6 | — | Not started |
| 7 | — | Not started |
| 8 | — | Not started |
| 9 | — | Not started |
| 10 | — | Not started |

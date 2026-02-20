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

**Status:** Complete
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

## Phase 3 — Entity index, context builder, and deterministic selectors

**Status:** Complete
**Depends on:** Phase 2
**Beads epic:** `cad-85u`
**AAR:** [020-AA-AACR-phase-03-aar.md](020-AA-AACR-phase-03-aar.md)

**Deliverables:**
- Enhanced EntityIndex with `filter()`, `search_text()`, `nearest()`, `get_by_id()`
- Context builder with full/subset serialization and token-economy summaries
- Deterministic selectors module (5 resolve functions for target resolution)
- 68 new unit tests across 3 test files (118 total suite)
- Phase 3 beads doc and AAR

**Exit criteria:**
- EntityIndex supports id/layer/type/text/nearest queries
- Context builder supports full + subset serialization and summaries
- Deterministic selectors exist and are unit-tested
- CI lint clean, all 118 tests pass in ~2.7s

---

## Phase 4 — Operation model and validator engine

**Status:** Complete (code predates formal phase tracking)
**Depends on:** Phase 3

**Deliverables:**
- OpType enum with 4 operation types (`ops_schema.py`)
- EditOperation and ChangeSet Pydantic models (`ops_schema.py`)
- ValidationResult with Severity enum, blockers/warnings properties (`changes_schema.py`)
- RuleConfig with protected layers/blocks, coordinate tolerance (`config_schema.py`)
- Validator engine: protected layer, move params, edit_text, add_block, missing handle (`validators.py`)
- Unit tests for schemas and validator paths

**Exit criteria:**
- Validator blocks operations on protected layers
- Validator blocks NaN/Inf coordinates, missing params
- Warnings (e.g., large move distance) don't block apply
- All validator tests pass

---

## Phase 5 — LLM planner interface and mock provider

**Status:** Complete (code predates formal phase tracking)
**Depends on:** Phase 4

**Deliverables:**
- PlannerProvider ABC with `plan()` method (`providers.py`)
- MockProvider keyword-based, offline (`mock_provider.py`)
- Response parser with code-fence stripping (`response_parser.py`)
- Prompt templates: system + user (`prompt_templates.py`)
- Planner orchestrator with OTel tracing (`planner.py`)
- 6 unit tests for parser (`test_planner_parser.py`)

**Exit criteria:**
- MockProvider returns valid operations for move/delete/text prompts
- Response parser accepts valid JSON, rejects malformed input
- All tests pass without any API key

---

## Phase 6 — Edit engine and DXF writer

**Status:** Complete (code predates formal phase tracking)
**Depends on:** Phase 5

**Deliverables:**
- EditEngine with all 4 op handlers + OTel tracing (`edit_engine.py`, 184 lines)
- DXF writer with save-as and copy-for-editing (`dxf_writer.py`, 50 lines)
- AppliedChange records for each operation (`ops_schema.py`)

**Exit criteria:**
- Each operation type modifies the DXF correctly via ezdxf
- Save produces a valid DXF file
- Original file hash unchanged after save (verified in E2E smoke test)

---

## Phase 7 — Preview model and AI revision notes

**Status:** Complete (code predates formal phase tracking)
**Depends on:** Phase 6

**Deliverables:**
- PreviewModel with human-readable summaries (`preview_model.py`, 81 lines)
- Deterministic revision note generation with direction/distance (`revision_notes.py`, 133 lines)
- DXF insertion on AI_REV_NOTES layer
- RevisionNoteConfig in `config_schema.py`
- 6 unit tests (`test_revision_notes.py`)

**Exit criteria:**
- Preview accurately describes all proposed changes
- Revision notes are deterministic and reproducible
- Notes appear on AI_REV_NOTES layer, never on protected layers

---

## Phase 8 — End-to-end integration and smoke tests

**Status:** Complete (code predates formal phase tracking)
**Depends on:** Phase 7

**Deliverables:**
- Standalone smoke test (`scripts/smoke_test.py`, 166 lines) — 7-step pipeline
- Pytest smoke suite (`tests/smoke/test_e2e_mock.py`, 106 lines) — 4 tests
- Move, delete, text-edit, and file-preservation E2E tests
- SHA256 verification of original file invariance

**Exit criteria:**
- `python scripts/smoke_test.py` exits 0
- `pytest -m smoke` passes
- Full pipeline works with mock provider, no API key

---

## Phase 9 — Desktop UI wiring

**Status:** Complete (code predates formal phase tracking)
**Depends on:** Phase 8

**Deliverables:**
- MainWindow fully wired to pipeline (`ui/main_window.py`, 208 lines)
- Open DXF → file picker → `load_dxf()` → entity count display
- Prompt input → Plan & Preview → `run_planner()` → `validate_changeset()` → `PreviewModel`
- Apply & Save As → `EditEngine` → `insert_revision_note()` → save
- Status log panel with real-time feedback
- Blocker display in operations list, warnings in status

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

Each phase strictly depends on the successful completion of the previous one. A phase cannot begin until every exit criterion of its predecessor is met and verified.

## Beads epic mapping

| Phase | Beads ID | Status |
|-------|----------|--------|
| 1 | `cad-6kc.1` | Complete |
| 2 | `cad-xoh` | Complete |
| 3 | `cad-85u` | Complete |
| 4 | — | Complete (pre-tracked) |
| 5 | — | Complete (pre-tracked) |
| 6 | — | Complete (pre-tracked) |
| 7 | — | Complete (pre-tracked) |
| 8 | — | Complete (pre-tracked) |
| 9 | — | Complete (pre-tracked) |
| 10 | `cad-m9m` | In progress |

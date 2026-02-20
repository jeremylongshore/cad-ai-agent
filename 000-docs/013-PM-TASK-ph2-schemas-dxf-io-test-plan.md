# 013-PM-TASK — Phase 2 Epic: Schemas, DXF I/O Contracts, Fixtures, and Test Strategy

**Date:** 2026-02-20
**Category:** PM (Project Management)
**Type:** TASK (Task Breakdown)
**Beads epic:** `cad-xoh`

---

## Epic summary

**Title:** Plan the core data schemas, DXF read/write contracts, test fixtures, and unit test strategy
**Objective:** Produce complete planning artifacts that specify every data model, I/O contract, fixture, and test expectation for Phases 3–4. No implementation code is written in this phase — only specifications and acceptance criteria.

**Entry criteria (from Phase 1):**
- Repository foundation complete with CI, security, and tooling
- Settings module loads environment variables
- PySide6 window shell opens
- Beads plan accessible for task tracking

**Exit criteria (before Phase 3 starts):**
- All five tasks below are closed with documented deliverables
- Schema specifications cover every domain model
- Reader and writer contracts define inputs, outputs, and guarantees
- Fixture spec includes all V1 entity types
- Test matrix is documented with CI expectations

---

## Task breakdown

### cad-xoh.1 — Specify all Pydantic data schemas with strictness rules and error behavior

**Depends on:** Phase 1 complete

**Description:**
Define the complete set of Pydantic models that will be used throughout the pipeline. This is a planning document — the actual Python implementation happens in Phase 3.

**Inputs:**
- V1 blueprint entity type list (LINE, LWPOLYLINE, TEXT, MTEXT, INSERT)
- V1 operation list (move_entity, edit_text, delete_entity, add_block)
- Protected layer configuration requirements

**Deliverables:**
- Schema specification for each model:
  - `EntityType` — StrEnum of V1 entity types
  - `Point2D` — 2D coordinate with x, y floats
  - `EntityRef` — entity handle, type, layer, insert point, text content, block name
  - `LayerRule` — layer name, protected flag, visibility, frozen state, color
  - `DrawingContext` — file path, entity list, layer rules, blocks, metadata
  - `EditOperation` — op type, target handle, target layer, params dict
  - `OpType` — StrEnum of allowed operations
  - `ChangeSet` — operation list, prompt text, revision label
  - `AppliedChange` — operation reference, success flag, description
  - `ValidationResult` — valid flag, list of issues with severity (blocker/warning)
  - `RuleConfig` — protected layers, protected blocks, max move distance, coordinate tolerance
  - `RevisionNoteConfig` — enabled flag, layer name, anchor point, text height, prefix, revision number
- Strictness rules:
  - Unknown fields rejected (Pydantic strict mode or `model_config`)
  - Invalid op types rejected at parse time
  - Invalid entity types rejected at parse time
- Error behavior:
  - If the LLM returns an invalid or unsupported operation, the entire changeset is rejected
  - Validation blockers prevent apply; warnings are informational only

**Acceptance criteria:**
- Every model listed above has a field-level specification
- Strict union strategy is documented (how invalid ops are caught)
- Error behavior is explicit (what happens when the LLM returns garbage)

---

### cad-xoh.2 — Define the DXF reader contract, supported entity fields, and ID strategy

**Depends on:** cad-xoh.1

**Description:**
Specify what the DXF reader module does, what it returns, and how it handles the full spectrum of DXF content.

**Inputs:**
- Schema specifications from cad-xoh.1
- ezdxf library capabilities for model space traversal
- V1 entity type list

**Deliverables:**
- Reader I/O contract:
  - Input: file path to a DXF file
  - Output: `DrawingContext` populated with entities, layers, blocks, metadata
  - Errors: `FileNotFoundError` for missing files, graceful handling of corrupt DXF
- Supported entity extraction — fields required per type:
  - LINE: handle, layer, start point (as insert_point)
  - LWPOLYLINE: handle, layer, first vertex (as insert_point)
  - TEXT: handle, layer, insert point, text content
  - MTEXT: handle, layer, insert point, text content (plain text extraction)
  - INSERT: handle, layer, insert point, block name
- Deterministic stable ID strategy:
  - Use the DXF entity handle (unique within a drawing, assigned by ezdxf)
  - Handles are hex strings, stable across read/write cycles
  - No custom ID generation needed
- Unsupported entity handling:
  - Log a warning listing skipped entity types
  - Record skipped types in `DrawingContext.unsupported_entity_types`
  - Never raise an error for unsupported entities

**Acceptance criteria:**
- Reader I/O contract fully defined (input, output, errors)
- Every V1 entity type has its extracted fields listed
- ID strategy documented (DXF handles)
- Unsupported entity behavior specified (warn, skip, record)

---

### cad-xoh.3 — Define the DXF writer contract with save-as guarantees and roundtrip requirements

**Depends on:** cad-xoh.2

**Description:**
Specify what the DXF writer does, its safety guarantees, and what "roundtrip success" means.

**Inputs:**
- Reader contract from cad-xoh.2
- Save-as workflow requirement from V1 blueprint

**Deliverables:**
- Writer I/O contract:
  - Input: in-memory ezdxf document + output file path
  - Output: new DXF file on disk
  - Constraint: never overwrites the original input file
- Save-as behavior:
  - Output path must differ from input path
  - Parent directories created automatically if missing
  - File saved via `ezdxf.document.Drawing.saveas()`
- Preservation guarantees:
  - Original file byte-identical after the full pipeline runs
  - All entities not targeted by operations remain unchanged
  - Layer table preserved (including protected layers)
  - Block definitions preserved
- Roundtrip definition:
  - A DXF file loaded by the reader, saved by the writer (with no edits), and reloaded should produce an identical `DrawingContext`
  - Entity count, handles, layers, and blocks must match
- Future hook point:
  - The edit engine (Phase 6) will sit between reader and writer
  - Writer does not apply operations — it just saves the document state

**Acceptance criteria:**
- Writer contract defined (input, output, constraints)
- Save-as naming and directory behavior documented
- Preservation guarantees explicit (original untouched, non-targeted entities unchanged)
- Roundtrip success defined in testable terms

---

### cad-xoh.4 — Design the test fixture strategy for programmatic DXF generation

**Depends on:** cad-xoh.1

**Description:**
Plan how test fixtures will be created, what they contain, and where they live.

**Inputs:**
- Schema specifications from cad-xoh.1
- V1 entity type list
- ezdxf programmatic creation API

**Deliverables:**
- Fixture creation approach:
  - Generate DXF files programmatically using `ezdxf.new()` at test time
  - Do not commit binary DXF files to the repository
  - Use pytest fixtures (`@pytest.fixture`) for on-demand generation
- Required fixture content:
  - At least one entity of each V1 type:
    - LINE on an editable layer
    - LWPOLYLINE on an editable layer
    - TEXT on an editable layer (with text content)
    - MTEXT on an editable layer (with text content)
    - INSERT on an editable layer (with block definition)
  - At least one entity on a protected layer (to test validator blocking)
  - Multiple named layers (editable + protected)
  - At least one block definition with geometry
- Fixture location:
  - Pytest fixtures in `tests/conftest.py`
  - Helper functions in `tests/fixtures/` if needed
- Determinism requirements:
  - Fixtures must produce identical entity counts and handles across runs
  - No random data in fixtures
  - DXF version pinned (R2018)

**Acceptance criteria:**
- Fixture spec includes all V1 entity types
- At least one protected-layer entity included
- Programmatic generation approach documented (no committed binary files)
- Determinism requirements stated

---

### cad-xoh.5 — Write the unit and roundtrip test plan with CI expectations

**Depends on:** cad-xoh.2, cad-xoh.3, cad-xoh.4

**Description:**
Define the test matrix, CI constraints, and coverage expectations for Phases 3–4.

**Inputs:**
- Schema, reader, writer, and fixture specs from cad-xoh.1–4
- CI workflow from Phase 1 (GitHub Actions, matrix: ubuntu+windows, Python 3.11+3.12)

**Deliverables:**
- Test matrix:
  - **Schema tests:**
    - Valid model construction succeeds
    - Invalid entity types rejected
    - Invalid op types rejected
    - Missing required fields rejected
    - Strictness enforced (unknown fields rejected if configured)
  - **Reader tests:**
    - Load succeeds on sample fixture
    - Entity count matches expected
    - All V1 entity types found
    - Correct layer assignments
    - Protected layers marked correctly
    - Blocks discovered
    - Metadata populated (DXF version, encoding)
    - `FileNotFoundError` raised for missing files
    - Unsupported entities skipped and recorded
  - **Writer tests:**
    - Save produces a valid DXF (reloadable by ezdxf)
    - Roundtrip preserves entity count
    - Original file untouched after save
  - **Entity index tests:**
    - Lookup by handle returns correct entity
    - Missing handle returns None
    - Lookup by layer returns correct subset
- CI expectations:
  - All tests must pass without any API key
  - Tests run on both Ubuntu and Windows
  - Tests run on Python 3.11 and 3.12
  - No network calls during tests
  - Test duration under 30 seconds total
- Coverage targets:
  - Minimum 50% line coverage (`fail_under` in pyproject.toml)
  - Aim for 100% path coverage on validators (Phase 4)
  - No hard coverage gate initially; revisit after Phase 4

**Acceptance criteria:**
- Test matrix documented with every test scenario listed
- CI expectations clear (no API keys, cross-platform, cross-Python)
- Coverage targets stated
- Roundtrip test defined in concrete terms

---

## Dependency graph

```
cad-xoh.1 (schemas)
  ├──→ cad-xoh.2 (reader contract)
  │       └──→ cad-xoh.3 (writer contract)
  │                └──→ cad-xoh.5 (test plan)
  └──→ cad-xoh.4 (fixture strategy)
              └──→ cad-xoh.5 (test plan)
```

Task cad-xoh.5 (test plan) is the final gate — it depends on all other tasks because the test matrix references schemas, reader, writer, and fixture specs.

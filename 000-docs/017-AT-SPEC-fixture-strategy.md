# 017-AT-SPEC — Test Fixture Strategy

**Date:** 2026-02-20
**Category:** AT (Architecture & Technical)
**Type:** SPEC (Specification)
**Beads task:** `cad-xoh.4`
**Depends on:** `cad-xoh.1` (schema specification, doc 014)

---

## Purpose

This document specifies how test fixtures are created, what they contain, where they live, and what determinism guarantees they provide.

**Two fixture strategies coexist:**

1. **Programmatic (unit/integration tests)** — DXF files generated in-process via `ezdxf.new()`, saved to `tmp_path`, never committed. Used for unit tests, integration tests, and property/fuzz tests.
2. **Committed static (revision golden tests)** — Pre-generated DXF pairs committed to `tests/fixtures/revision/`. Required for golden-file regression testing where the comparison result must be deterministic across runs and diffable in review. See `tests/fixtures/revision/README.md` for the clean/nasty taxonomy.

---

## Fixture Creation Approach

### Strategy 1: Programmatic generation (unit/integration)

Most DXF fixtures are created in-process using `ezdxf.new()`. This avoids:
- Binary files in version control (DXF files are opaque to git diff)
- Stale fixtures that drift from the schema specification
- Platform-specific line ending issues

### Strategy 2: Committed static DXFs (revision golden tests)

Revision pipeline golden tests require committed DXF pairs (`master.dxf` + `revision.dxf`) alongside `expected.json` golden files. These are committed because:
- Golden files (`expected.json`) must diff cleanly in PRs
- The master/revision pairs must be identical across CI runs (no regeneration variance)
- Real-world DXF files (seeded from MIT-licensed sources) cannot be recreated programmatically
- The `UPDATE_GOLDENS=1` workflow requires stable input files

Static fixtures live in `tests/fixtures/revision/` with clean/nasty taxonomy. Factory functions in `tests/helpers/comparison_factory.py` generate the synthetic pairs; real-world-seeded pairs are created once and committed.

### DXF version

All fixtures use `ezdxf.new(dxfversion="R2018")`. R2018 (AC1032) is the target version for V1. Pinning the version eliminates variation across runs and ensures consistent handle assignment.

### Fixture lifecycle

1. Pytest calls the fixture function
2. The function creates an ezdxf document in memory
3. Entities, layers, and blocks are added programmatically
4. The document is saved to a `tmp_path` directory (pytest-managed, auto-cleaned)
5. The file path is returned to the test

No fixture files persist after the test session.

---

## Required Fixture Content

### Primary fixture: `sample_dxf`

The main fixture creates a DXF with comprehensive coverage of all V1 entity types, layers, and blocks.

#### Layers

| Layer Name | Color | Protected | Purpose |
|------------|-------|-----------|---------|
| `0` | — | no | Default layer (created by ezdxf automatically) |
| `STRUCTURAL` | 1 (red) | no | Editable geometry layer |
| `NOTES` | 3 (green) | no | Editable text layer |
| `TITLE` | 7 (white) | yes | Protected — title text |
| `TITLEBLOCK` | 7 (white) | yes | Protected — title block geometry |
| `SEAL` | 7 (white) | yes | Protected — seal/stamp area |
| `REVISION` | 7 (white) | yes | Protected — revision history |

#### Entities

| # | Type | Layer | Key Properties | Purpose |
|---|------|-------|----------------|---------|
| 1 | LINE | STRUCTURAL | start=(0,0), end=(100,0) | Basic geometry, move/delete target |
| 2 | LWPOLYLINE | STRUCTURAL | 4 vertices, closed rectangle | Multi-vertex geometry |
| 3 | TEXT | NOTES | text="Column C-4", insert=(10,10) | Editable text, edit_text target |
| 4 | MTEXT | NOTES | text="Footing detail note", insert=(20,20) | Multi-line text target |
| 5 | TEXT | TITLE | text="PROJECT TITLE", insert=(0,-20) | Protected layer entity — validator must block |
| 6 | INSERT | STRUCTURAL | block="COLUMN_MARK", insert=(25,25) | Block reference |

#### Block Definitions

| Block Name | Content | Purpose |
|------------|---------|---------|
| `COLUMN_MARK` | Circle at origin, radius=2 | Minimal block for INSERT testing |

### Entity count expectations

The `sample_dxf` fixture produces exactly **6 entities** of V1 types in model space. Tests that assert entity counts must use this number.

### Handle stability

ezdxf assigns handles sequentially starting from a deterministic base when creating a new document. As long as entities are added in the same order with the same parameters, handles are identical across runs. Tests may assert specific handle values if needed, but testing by entity type and layer is preferred for resilience.

---

## Derived Fixtures

### `sample_context`

Loads `sample_dxf` through `load_dxf()` and returns the resulting `DrawingContext`. This fixture depends on `sample_dxf` and exercises the reader contract (doc 015).

**Expected postconditions:**
- `context.entity_count == 6`
- Entity types present: LINE, LWPOLYLINE, TEXT (x2), MTEXT, INSERT
- Layers present: 0, STRUCTURAL, NOTES, TITLE, TITLEBLOCK, SEAL, REVISION
- Protected layers: TITLE, TITLEBLOCK, SEAL, REVISION
- Blocks: `COLUMN_MARK`
- `unsupported_entity_types` is empty (only V1 types in the fixture)
- `metadata["dxf_version"]` is `"AC1032"` (R2018)

### `rule_config`

Returns a default `RuleConfig()` with factory defaults:
- `protected_layers`: `["TITLE", "TITLEBLOCK", "SEAL", "REVISION"]`
- `protected_blocks`: `[]`
- `max_move_distance`: `None`
- `coordinate_tolerance`: `1e-6`

---

## Fixture Location

| Fixture | Location | Scope |
|---------|----------|-------|
| `sample_dxf` | `tests/conftest.py` | Session or function (currently function) |
| `sample_context` | `tests/conftest.py` | Function (depends on `sample_dxf`) |
| `rule_config` | `tests/conftest.py` | Function |
| Revision pairs | `tests/fixtures/revision/` | Static, committed |
| DXF factories | `tests/helpers/dxf_factory.py` | Imported by tests |
| Comparison factories | `tests/helpers/comparison_factory.py` | Imported by fixture generators |

All shared programmatic fixtures live in `tests/conftest.py`. Static revision fixtures live in `tests/fixtures/revision/` organized by clean/nasty taxonomy (see that directory's `README.md`).

Helper functions for DXF generation live in `tests/helpers/dxf_factory.py` (general drawings) and `tests/helpers/comparison_factory.py` (master/revision pairs for the comparison pipeline).

---

## Determinism Requirements

### Entity count

The primary fixture must produce the same number of entities every time. This is guaranteed by the programmatic creation approach — no external data sources, no randomness, no conditional entity creation.

### Handle assignment

ezdxf assigns handles deterministically within a new document. The sequence depends on:
1. The order entities are added to model space
2. The order blocks and layers are created

As long as the fixture code does not change, handles are stable. Tests should prefer looking up entities by type or layer rather than by exact handle value, to tolerate minor fixture refactors.

### Coordinate precision

All coordinates in fixtures use integer or simple float values (e.g., `0`, `100`, `10.0`, `25.0`). This avoids floating-point representation issues and ensures exact equality in assertions.

### No random data

Fixtures must not use `random`, `uuid`, timestamps, or any non-deterministic source. Every property of every entity is explicitly specified.

### DXF version pinned

Always `ezdxf.new(dxfversion="R2018")`. Never use `ezdxf.new()` without specifying the version, as the default may change across ezdxf releases.

---

## Future Fixture Needs

As Phases 3-10 are implemented, additional fixtures may be needed:

| Scenario | Phase | Notes |
|----------|-------|-------|
| DXF with unsupported entity types (CIRCLE, ARC) | 3 | Test reader skipping behavior |
| DXF with zero entities | 3 | Edge case for empty model space |
| DXF with entities on default layer (0) only | 4 | Validator edge case |
| DXF with duplicate block names | 6 | Edit engine edge case |
| DXF from older DXF versions (R12, R2000) | 3 | Compatibility testing |
| Region/markup/association test builders | EPIC-03 | Inline test builders in `test_region_schema.py`, `test_markup_parser.py`, `test_region_associator.py`, `test_selection_debug.py`. No factory file — fixtures are constructed per-test using `NormalizedRegion`, `MarkupOverlay`, and `EntityRef` directly. |

These are documented here for awareness but are not part of the Phase 2 deliverable. They should be added as test needs arise.

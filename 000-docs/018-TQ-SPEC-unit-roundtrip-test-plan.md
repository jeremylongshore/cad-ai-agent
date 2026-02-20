# 018-TQ-SPEC — Unit and Roundtrip Test Plan

**Date:** 2026-02-20
**Category:** TQ (Testing & Quality)
**Type:** SPEC (Specification)
**Beads task:** `cad-xoh.5`
**Depends on:** `cad-xoh.2` (reader, doc 015), `cad-xoh.3` (writer, doc 016), `cad-xoh.4` (fixtures, doc 017)

---

## Purpose

This document defines the complete test matrix, CI expectations, and coverage targets for Phases 3-4. Every test scenario is listed with its inputs, expected outcome, and the spec it validates. Implementation of these tests happens in Phase 3 (reader/schema tests) and Phase 4 (validator tests).

---

## Test Matrix

### 1. Schema Tests

Target module: `models/cad_schema.py`, `models/ops_schema.py`, `models/config_schema.py`, `models/changes_schema.py`
Spec reference: doc 014

| ID | Scenario | Input | Expected Outcome |
|----|----------|-------|------------------|
| S-01 | Valid EntityRef construction | All required fields with valid EntityType | Model created successfully |
| S-02 | Invalid entity type rejected | `entity_type="CIRCLE"` | `ValueError` raised by StrEnum |
| S-03 | Valid OpType construction | Each of the 4 valid op types | Model created successfully |
| S-04 | Invalid op type rejected | `op_type="rotate_entity"` | `ValueError` raised by StrEnum |
| S-05 | Missing required field (handle) | `EntityRef(entity_type="LINE", layer="0")` | `ValidationError` — handle is required |
| S-06 | Optional fields default correctly | `EntityRef(handle="1A", entity_type="LINE", layer="0")` | `insert_point=None`, `text_content=None`, `block_name=None`, `attributes={}` |
| S-07 | Point2D construction | `Point2D(x=10.0, y=20.0)` | Model created with correct values |
| S-08 | DrawingContext entity_count | Context with 3 entities | `entity_count == 3` |
| S-09 | DrawingContext get_entity_by_handle | Known handle | Returns correct EntityRef |
| S-10 | DrawingContext get_entity_by_handle miss | Unknown handle | Returns `None` |
| S-11 | DrawingContext get_protected_layers | Layers with mixed protected flags | Returns only protected layer names |
| S-12 | ValidationResult add_blocker | Call `add_blocker("msg", 0)` | `valid=False`, blocker in issues |
| S-13 | ValidationResult add_warning | Call `add_warning("msg", 0)` | `valid=True` (unchanged), warning in issues |
| S-14 | ValidationResult blockers/warnings separation | Mix of blockers and warnings | `.blockers` returns only blockers, `.warnings` returns only warnings |
| S-15 | ChangeSet op_count | ChangeSet with 3 operations | `op_count == 3` |
| S-16 | RuleConfig defaults | `RuleConfig()` | Protected layers are TITLE, TITLEBLOCK, SEAL, REVISION |
| S-17 | Severity enum values | `Severity.WARNING`, `Severity.BLOCKER` | Values are `"warning"`, `"blocker"` |

### 2. Reader Tests

Target module: `core/dxf_reader.py`
Spec reference: doc 015
Fixture: `sample_dxf`, `sample_context`

| ID | Scenario | Input | Expected Outcome |
|----|----------|-------|------------------|
| R-01 | Load succeeds on valid DXF | `sample_dxf` path | Returns `DrawingContext` without error |
| R-02 | Entity count matches fixture | `sample_context` | `entity_count == 6` |
| R-03 | All V1 entity types present | `sample_context` | LINE, LWPOLYLINE, TEXT, MTEXT, INSERT all found |
| R-04 | Correct layer assignments | `sample_context` | LINE on STRUCTURAL, TEXT on NOTES and TITLE |
| R-05 | Protected layers marked | `sample_context` | TITLE, TITLEBLOCK, SEAL, REVISION have `protected=True` |
| R-06 | Editable layers not protected | `sample_context` | STRUCTURAL, NOTES have `protected=False` |
| R-07 | Blocks discovered | `sample_context` | `"COLUMN_MARK"` in `context.blocks` |
| R-08 | Internal blocks excluded | `sample_context` | No `*`-prefixed block names in `context.blocks` |
| R-09 | Metadata populated | `sample_context` | `metadata["dxf_version"]` is `"AC1032"`, `metadata["encoding"]` is `"utf-8"` |
| R-10 | FileNotFoundError for missing file | Non-existent path | `FileNotFoundError` raised |
| R-11 | Unsupported entities skipped | DXF with a CIRCLE added | CIRCLE not in entities, `"CIRCLE"` in `unsupported_entity_types` |
| R-12 | TEXT entity fields extracted | TEXT entity from `sample_context` | `text_content == "Column C-4"`, `insert_point` is `(10, 10)` |
| R-13 | MTEXT entity fields extracted | MTEXT entity from `sample_context` | `text_content == "Footing detail note"`, `insert_point` is `(20, 20)` |
| R-14 | INSERT entity fields extracted | INSERT entity from `sample_context` | `block_name == "COLUMN_MARK"`, `insert_point` is `(25, 25)` |
| R-15 | LINE entity fields extracted | LINE entity from `sample_context` | `insert_point` is `(0, 0)` (start point) |
| R-16 | LWPOLYLINE entity fields extracted | LWPOLYLINE entity from `sample_context` | `insert_point` is `(0, 0)` (first vertex) |

### 3. Writer Tests

Target module: `core/dxf_writer.py`, `core/edit_engine.py`
Spec reference: doc 016
Fixture: `sample_dxf`

| ID | Scenario | Input | Expected Outcome |
|----|----------|-------|------------------|
| W-01 | Save produces valid DXF | `sample_dxf` → `save_as_new_dxf` | Output file loadable by `ezdxf.readfile()` |
| W-02 | Roundtrip preserves entity count | Load → save → reload | Entity count identical |
| W-03 | Roundtrip preserves entity handles | Load → save → reload | All handles present in reloaded context |
| W-04 | Roundtrip preserves layer table | Load → save → reload | Layer names, protected flags, colors identical |
| W-05 | Roundtrip preserves blocks | Load → save → reload | Block names identical |
| W-06 | Roundtrip preserves text content | Load → save → reload | TEXT and MTEXT content identical |
| W-07 | Roundtrip preserves metadata | Load → save → reload | `dxf_version` identical |
| W-08 | Original file untouched after save | Read source bytes → save_as → re-read source bytes | Bytes identical |
| W-09 | Same path rejected | `save_as_new_dxf(path, path)` | `ValueError` raised |
| W-10 | Parent directory created | Output path with non-existent parent | Directory created, file written |

### 4. Entity Index Tests

Target module: `core/entity_index.py`
Spec reference: doc 014 (entity index section)
Fixture: `sample_context`

| ID | Scenario | Input | Expected Outcome |
|----|----------|-------|------------------|
| I-01 | Lookup by handle succeeds | Known handle from `sample_context` | Returns correct `EntityRef` |
| I-02 | Lookup by handle miss | Handle `"FFFFF"` | Returns `None` |
| I-03 | Lookup by layer returns correct subset | Layer `"STRUCTURAL"` | Returns LINE, LWPOLYLINE, INSERT |
| I-04 | Lookup by layer case-insensitive | Layer `"structural"` | Returns same entities as `"STRUCTURAL"` |
| I-05 | Lookup by type | `EntityType.TEXT` | Returns both TEXT entities |
| I-06 | Handles list complete | `sample_context` | Length matches entity count |
| I-07 | Count property | `sample_context` | `count == 6` |

### 5. Validator Tests (Phase 4)

Target module: `core/validators.py`
Spec reference: doc 014 (error behavior section)
Fixture: `sample_context`, `rule_config`

| ID | Scenario | Input | Expected Outcome |
|----|----------|-------|------------------|
| V-01 | Valid move operation passes | move_entity on STRUCTURAL entity | `valid=True`, no blockers |
| V-02 | Protected layer blocked | move_entity targeting TITLE entity | `valid=False`, blocker message |
| V-03 | Missing target_handle blocked | move_entity with no handle | `valid=False`, blocker |
| V-04 | Nonexistent entity blocked | move_entity targeting handle `"FFFFF"` | `valid=False`, blocker |
| V-05 | move_entity missing dx/dy blocked | move with empty params | `valid=False`, blocker |
| V-06 | move_entity NaN dx blocked | `dx=float('nan')` | `valid=False`, blocker |
| V-07 | move_entity Inf dy blocked | `dy=float('inf')` | `valid=False`, blocker |
| V-08 | move_entity non-numeric dx blocked | `dx="ten"` | `valid=False`, blocker |
| V-09 | Max move distance warning | Move exceeding `max_move_distance` | `valid=True`, warning present |
| V-10 | edit_text missing new_text blocked | edit_text with empty params | `valid=False`, blocker |
| V-11 | edit_text non-string blocked | `new_text=42` | `valid=False`, blocker |
| V-12 | add_block missing block_name blocked | add_block with no block_name | `valid=False`, blocker |
| V-13 | add_block missing insert_point blocked | add_block with no insert_point | `valid=False`, blocker |
| V-14 | add_block on protected layer blocked | `target_layer="TITLE"` | `valid=False`, blocker |
| V-15 | Valid delete passes | delete_entity on editable entity | `valid=True` |
| V-16 | Mixed valid/invalid ops | Batch with one valid, one blocked | `valid=False` (entire batch rejected) |

---

## CI Expectations

### Environment constraints

| Constraint | Requirement |
|------------|-------------|
| API keys | No API keys required — all tests use mock planner |
| Network | No network calls — no OTLP exporter, no external APIs |
| File system | Tests use `tmp_path` (auto-cleaned by pytest) |
| Platform | Must pass on Ubuntu and Windows |
| Python versions | Must pass on 3.11 and 3.12 |

### CI matrix (from `.github/workflows/ci.yml`)

```
os: [ubuntu-latest, windows-latest]
python-version: ["3.11", "3.12"]
```

Total: 4 combinations. All must pass for a PR to merge.

### Test duration

Target: total test suite completes in under 30 seconds on CI runners. Individual tests should complete in under 1 second. The `@pytest.mark.slow` marker is available for tests that legitimately take longer (e.g., large DXF generation).

### Test isolation

Each test function must be independent. No shared mutable state between tests. Fixtures that create DXF files use `tmp_path` (function-scoped by default) for isolation.

---

## Coverage Targets

| Phase | Target | Rationale |
|-------|--------|-----------|
| Phase 3 | 50% line coverage | `fail_under = 50` in `pyproject.toml`. Covers schemas + reader + writer + entity index |
| Phase 4 | 65% line coverage | Adding validator tests significantly increases coverage |
| Post-Phase 4 | 100% path coverage on `validators.py` | Validators are safety-critical — every code path must be tested |

### What counts toward coverage

- All files under `src/cad_dxf_agent/` are measured
- Test files themselves are excluded from coverage measurement
- The `otel.py` module's graceful-degradation branches (import errors) are difficult to cover in the same process — these are excluded from the 100% path target

### Coverage enforcement

```bash
make test-cov   # pytest --cov=cad_dxf_agent --cov-report=term-missing -v
```

CI runs `pytest -v` (without coverage) for speed. Coverage is checked locally and in the `make check` workflow.

---

## Roundtrip Test — Concrete Definition

This test directly implements the roundtrip definition from doc 016.

### Test procedure

```
1. Create DXF via sample_dxf fixture → source_path
2. ctx_a = load_dxf(source_path)
3. save_as_new_dxf(source_path, output_path)
4. ctx_b = load_dxf(output_path)
5. Assert ctx_a and ctx_b are semantically equal
```

### Assertions (in order)

1. `ctx_a.entity_count == ctx_b.entity_count`
2. For each entity pair (matched by handle):
   - `a.entity_type == b.entity_type`
   - `a.layer == b.layer`
   - `a.insert_point.x ≈ b.insert_point.x` (within `1e-6`)
   - `a.insert_point.y ≈ b.insert_point.y` (within `1e-6`)
   - `a.text_content == b.text_content`
   - `a.block_name == b.block_name`
3. `set(ctx_a.blocks) == set(ctx_b.blocks)`
4. Layer table match (name, protected, visible, frozen, color)
5. `ctx_a.metadata["dxf_version"] == ctx_b.metadata["dxf_version"]`

### Excluded from comparison

- `file_path` (different files by definition)
- `encoding` (ezdxf may normalize)
- `unsupported_entity_types` (fixture has none, but this is informational)

---

## Test File Organization

| File | Contents | Phase |
|------|----------|-------|
| `tests/conftest.py` | Shared fixtures: `sample_dxf`, `sample_context`, `rule_config` | 1 (exists) |
| `tests/unit/test_schemas.py` | S-01 through S-17 | 3 |
| `tests/unit/test_reader.py` | R-01 through R-16 | 3 |
| `tests/unit/test_writer.py` | W-01 through W-10 | 3 |
| `tests/unit/test_entity_index.py` | I-01 through I-07 | 3 |
| `tests/unit/test_validators.py` | V-01 through V-16 | 4 |
| `tests/smoke/test_e2e_mock.py` | Full pipeline smoke test | 1 (exists) |
| `tests/unit/test_otel.py` | OTel span emission tests | 1 (exists) |

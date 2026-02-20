# 019-PM-TASK — Phase 3: Entity Index + Context Builder + Deterministic Selectors

**Date:** 2026-02-20
**Category:** PM (Project Management)
**Type:** TASK (Task)
**Beads epic:** `cad-85u`

---

## Epic

`cad-85u` — Entity index, context builder, and deterministic selectors

## Tasks

| ID | Title | Status | Deliverable |
|----|-------|--------|-------------|
| cad-85u.1 | Enhance EntityIndex with text search and spatial nearest | Done | `entity_index.py` enhanced |
| cad-85u.2 | Build context builder with full and subset serialization | Done | `context_builder.py` created |
| cad-85u.3 | Create deterministic selectors module | Done | `selectors.py` created |
| cad-85u.4 | Add unit tests for index, context builder, and selectors | Done | 68 tests across 3 files |
| cad-85u.5 | File Phase 3 beads doc and AAR | Done | This doc + AAR |

## Dependencies

- Depends on: Phase 2 specs (docs 014-018), Phase 1 foundation
- Blocks: Phase 4 (validator + op executor uses selectors for target resolution)

## Modules Delivered

### entity_index.py (enhanced)

| Method | Purpose |
|--------|---------|
| `get_by_handle(handle)` | O(1) lookup by DXF handle |
| `get_by_id(id)` | Alias for get_by_handle |
| `get_by_layer(layer)` | Case-insensitive layer lookup |
| `get_by_type(entity_type)` | Lookup by EntityType enum |
| `filter(layer?, type?)` | Combined filter, intersection when both provided |
| `search_text(query)` | Normalized token matching across TEXT/MTEXT |
| `nearest(x, y, type?, layer?)` | Spatial proximity via bbox-center distance |
| `handles()` | All indexed handles |
| `count` | Total entity count property |

### context_builder.py (new)

| Function | Purpose |
|----------|---------|
| `full_context(ctx)` | Complete LLM-friendly JSON with all entities + summary |
| `subset_context(ctx, ...)` | Filtered subset by ids, spatial radius, layers, types |
| `token_economy_summary(ctx)` | Compact counts by layer/type, top text labels |

### selectors.py (new)

| Function | Purpose |
|----------|---------|
| `resolve_target_by_id(ctx, id)` | Exact handle match |
| `resolve_targets_by_layer_type(ctx, layer?, type?)` | Layer + type filter |
| `resolve_targets_by_text(ctx, query)` | Text content search |
| `resolve_target_nearest_point(ctx, x, y, ...)` | Spatial nearest |
| `resolve_candidate_set(ctx, hints)` | Multi-strategy resolution from structured hints |

## Test Coverage

| File | Tests | Scenarios |
|------|-------|-----------|
| test_entity_index.py | 25 | Handle hit/miss, layer case-insensitive, type, filter, text search, nearest, empty context |
| test_context_builder.py | 20 | Full/subset serialization, spatial radius, summaries, empty context |
| test_selectors.py | 23 | All 5 resolve functions, priority ordering, determinism, edge cases |

**Total:** 68 new tests, 118 total suite, all passing in ~2.7s.

## Acceptance Criteria

- [x] EntityIndex supports id/layer/type/text/nearest queries
- [x] Context builder supports full + subset serialization and summaries
- [x] Deterministic selectors exist and are unit-tested
- [x] CI lint clean
- [x] All 118 tests pass
- [x] Phase 3 beads doc exists
- [x] Phase 3 AAR exists

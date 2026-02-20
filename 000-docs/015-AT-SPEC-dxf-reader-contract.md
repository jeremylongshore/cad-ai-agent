# 015-AT-SPEC — DXF Reader Contract

**Date:** 2026-02-20
**Category:** AT (Architecture & Technical)
**Type:** SPEC (Specification)
**Beads task:** `cad-xoh.2`
**Depends on:** `cad-xoh.1` (schema specification, doc 014)

---

## Purpose

This document defines the complete I/O contract for `core/dxf_reader.py`. It specifies what the reader accepts, what it returns, how it handles each V1 entity type, how entities are identified, and what happens when the DXF contains content outside V1 scope.

---

## Module Interface

### `load_dxf(file_path: str | Path) -> DrawingContext`

The sole public function. Loads a DXF file from disk and returns a fully populated `DrawingContext`.

---

## I/O Contract

### Input

| Parameter | Type | Description |
|-----------|------|-------------|
| `file_path` | `str \| Path` | Path to a DXF file on disk. Converted to `Path` internally. |

**Preconditions:**
- The file must exist on disk
- The file must be a valid DXF readable by ezdxf
- No specific DXF version requirement (ezdxf handles R12 through R2018+)

### Output

| Return | Type | Description |
|--------|------|-------------|
| context | `DrawingContext` | Fully populated context with entities, layers, blocks, metadata |

**Postconditions:**
- `context.file_path` is the string representation of the input path
- `context.entities` contains one `EntityRef` for every model-space entity of a V1 type
- `context.layers` contains one `LayerRule` for every layer in the DXF layer table
- `context.blocks` contains the names of all user-defined blocks (excluding `*`-prefixed internal blocks)
- `context.unsupported_entity_types` lists any non-V1 entity types found (sorted, deduplicated)
- `context.metadata` contains `dxf_version` and `encoding`

### Errors

| Condition | Exception | Message Pattern |
|-----------|-----------|-----------------|
| File does not exist | `FileNotFoundError` | `"DXF file not found: {path}"` |
| File is corrupt / not valid DXF | `ezdxf.DXFError` (or subclass) | Propagated from ezdxf — not caught by the reader |

The reader does not catch ezdxf parse errors. A corrupt DXF propagates naturally and the caller (planner or UI) handles the exception.

---

## Entity Extraction

### Scope

Only model-space entities are processed. Paper space, layout tabs, and entities inside block definitions are ignored.

### V1 Entity Types and Extracted Fields

#### LINE

| Field | Source | Description |
|-------|--------|-------------|
| `handle` | `entity.dxf.handle` | Hex string, unique within drawing |
| `entity_type` | `EntityType.LINE` | — |
| `layer` | `entity.dxf.layer` | Layer name |
| `insert_point` | `entity.dxf.start` → `Point2D(x, y)` | Start point of the line |
| `text_content` | — | Always `None` |
| `block_name` | — | Always `None` |

#### LWPOLYLINE

| Field | Source | Description |
|-------|--------|-------------|
| `handle` | `entity.dxf.handle` | Hex string |
| `entity_type` | `EntityType.LWPOLYLINE` | — |
| `layer` | `entity.dxf.layer` | Layer name |
| `insert_point` | `entity.get_points("xy")[0]` → `Point2D(x, y)` | First vertex of the polyline |
| `text_content` | — | Always `None` |
| `block_name` | — | Always `None` |

**Edge case:** If the polyline has zero vertices, `insert_point` is `None`.

#### TEXT

| Field | Source | Description |
|-------|--------|-------------|
| `handle` | `entity.dxf.handle` | Hex string |
| `entity_type` | `EntityType.TEXT` | — |
| `layer` | `entity.dxf.layer` | Layer name |
| `insert_point` | `entity.dxf.insert` → `Point2D(x, y)` | Insertion point |
| `text_content` | `entity.dxf.text` | Single-line text content |
| `block_name` | — | Always `None` |

#### MTEXT

| Field | Source | Description |
|-------|--------|-------------|
| `handle` | `entity.dxf.handle` | Hex string |
| `entity_type` | `EntityType.MTEXT` | — |
| `layer` | `entity.dxf.layer` | Layer name |
| `insert_point` | `entity.dxf.insert` → `Point2D(x, y)` | Insertion point |
| `text_content` | `entity.text` (property) | Plain text with formatting stripped by ezdxf |
| `block_name` | — | Always `None` |

**Note:** `entity.text` on MTEXT returns plain text. `entity.dxf.text` would return raw MTEXT formatting codes. The reader uses the plain-text property.

#### INSERT

| Field | Source | Description |
|-------|--------|-------------|
| `handle` | `entity.dxf.handle` | Hex string |
| `entity_type` | `EntityType.INSERT` | — |
| `layer` | `entity.dxf.layer` | Layer name |
| `insert_point` | `entity.dxf.insert` → `Point2D(x, y)` | Block insertion point |
| `text_content` | — | Always `None` |
| `block_name` | `entity.dxf.name` | Name of the referenced block definition |

---

## ID Strategy

### DXF Handles

Entities are identified by their DXF handle (`entity.dxf.handle`), which is:

- A hexadecimal string (e.g., `"1A"`, `"2F5"`)
- Unique within a single DXF file
- Assigned by ezdxf during file creation or load
- Stable across read/write cycles (ezdxf preserves handles on save)
- Not reused within the same document after deletion

### Why not custom IDs?

DXF handles are the native identity mechanism. Custom UUIDs or sequential IDs would add a mapping layer with no benefit. The handle is the canonical reference throughout the pipeline: the planner returns handles, the validator looks up handles, and the edit engine resolves handles.

---

## Layer Resolution

The reader builds `LayerRule` objects from the DXF layer table:

| Field | Source | Logic |
|-------|--------|-------|
| `name` | `layer.dxf.name` | Raw layer name from the table |
| `protected` | settings comparison | `True` if `name.upper()` matches any `settings.protected_layers` entry (case-insensitive) |
| `visible` | `layer.is_off()` | `True` if the layer is not off |
| `frozen` | `layer.is_frozen()` | Direct boolean |
| `color` | `layer.color` | AutoCAD color index |

**Protected layer matching:** The comparison is case-insensitive. Both `"Title"` and `"TITLE"` match the protected layer `"TITLE"`.

---

## Block Discovery

The reader collects block names from `doc.blocks`, filtering out internal blocks:

```
blocks = [block.name for block in doc.blocks if not block.name.startswith("*")]
```

Internal blocks (like `*Model_Space`, `*Paper_Space`) are excluded. Only user-defined block definitions are listed. The block geometry itself is not extracted — only the name is recorded for reference by INSERT entities.

---

## Unsupported Entity Handling

When the reader encounters an entity whose `dxftype()` is not in the `SUPPORTED_TYPES` set:

1. The entity type string is added to a `set` (deduplicated)
2. The entity is skipped — no `EntityRef` is created
3. After iteration, the set is sorted and stored in `context.unsupported_entity_types`
4. A log message is emitted at INFO level: `"Skipped unsupported entity types: CIRCLE, DIMENSION"`

**Guarantees:**
- No exception is raised for unsupported entities
- The reader never fails due to unknown entity types
- The caller can inspect `unsupported_entity_types` to understand what was skipped

---

## Metadata

The reader populates `context.metadata` with:

| Key | Source | Example |
|-----|--------|---------|
| `dxf_version` | `doc.dxfversion` | `"AC1032"` (R2018) |
| `encoding` | `doc.encoding` | `"utf-8"` |

---

## Observability

The reader emits an OpenTelemetry span `cad.load_dxf` with attributes:

| Attribute | Value |
|-----------|-------|
| `cad.file.name` | Basename of the input file (no directory path for privacy) |
| `cad.entities.count` | Number of extracted entities |
| `cad.layers.count` | Number of layers |

When OTel is disabled (default), these calls are no-ops via `_NoOpSpan`.

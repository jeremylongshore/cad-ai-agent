# 016-AT-SPEC — DXF Writer Contract

**Date:** 2026-02-20
**Category:** AT (Architecture & Technical)
**Type:** SPEC (Specification)
**Beads task:** `cad-xoh.3`
**Depends on:** `cad-xoh.2` (reader contract, doc 015)

---

## Purpose

This document defines the complete I/O contract for `core/dxf_writer.py` and the save path in `core/edit_engine.py`. It specifies what the writer accepts, what it produces, its safety guarantees, and the precise definition of "roundtrip success."

---

## Module Interface

### `save_as_new_dxf(source_path, output_path) -> Path`

Standalone save function. Reads a DXF from `source_path`, writes it to `output_path`. Used for copy-without-edits scenarios.

### `copy_dxf_for_editing(source_path, work_path) -> Path`

Copies a DXF file to a working location via `shutil.copy2`. Used internally to stage a file before in-memory editing.

### `EditEngine.save(output_path) -> Path`

Saves the in-memory ezdxf document (after operations have been applied) to `output_path`. This is the primary save path for the editing pipeline.

---

## I/O Contract — `save_as_new_dxf`

### Input

| Parameter | Type | Description |
|-----------|------|-------------|
| `source_path` | `str \| Path` | Path to the source DXF file on disk |
| `output_path` | `str \| Path` | Path where the new DXF will be written |

**Preconditions:**
- `source_path` must exist and be a valid DXF readable by ezdxf
- `output_path` must differ from `source_path` (resolved absolute comparison)

### Output

| Return | Type | Description |
|--------|------|-------------|
| path | `Path` | The resolved output path where the file was written |

### Errors

| Condition | Exception | Message Pattern |
|-----------|-----------|-----------------|
| Output path equals source path | `ValueError` | `"Output path must differ from source path (save-as workflow)."` |
| Source file does not exist | `FileNotFoundError` | Propagated from ezdxf |
| Source file is corrupt DXF | `ezdxf.DXFError` | Propagated from ezdxf |

### Side Effects

- Creates parent directories for `output_path` if they do not exist (`mkdir(parents=True, exist_ok=True)`)
- Writes a new DXF file to disk at `output_path`
- Logs the output path at INFO level

---

## I/O Contract — `copy_dxf_for_editing`

### Input

| Parameter | Type | Description |
|-----------|------|-------------|
| `source_path` | `str \| Path` | Path to the source DXF file |
| `work_path` | `str \| Path` | Path for the working copy |

### Output

| Return | Type | Description |
|--------|------|-------------|
| path | `Path` | The resolved work path |

### Errors

| Condition | Exception | Message Pattern |
|-----------|-----------|-----------------|
| Work path equals source path | `ValueError` | `"Work path must differ from source path."` |
| Source file does not exist | `FileNotFoundError` | Propagated from `shutil.copy2` |

### Side Effects

- Creates parent directories for `work_path`
- Copies the file via `shutil.copy2` (preserves metadata)

---

## I/O Contract — `EditEngine.save`

### Input

| Parameter | Type | Description |
|-----------|------|-------------|
| `output_path` | `str \| Path` | Path where the edited DXF will be saved |

### Output

| Return | Type | Description |
|--------|------|-------------|
| path | `Path` | The resolved output path |

### Behavior

- Creates parent directories if needed
- Calls `ezdxf.document.Drawing.saveas()` on the in-memory document
- Emits an OTel span `cad.save` with attribute `cad.save.output_basename`
- Logs the output path at INFO level

### Relationship to `save_as_new_dxf`

| Function | When to Use |
|----------|-------------|
| `EditEngine.save()` | After applying operations through the pipeline (primary path) |
| `save_as_new_dxf()` | Copying a DXF without modifications (utility path) |

Both paths enforce the save-as guarantee: the original file is never overwritten.

---

## Save-As Behavior

### Path constraint

The output path must differ from the input/source path. This is enforced by:
- `save_as_new_dxf`: explicit `ValueError` if `output_path.resolve() == source_path.resolve()`
- `EditEngine.save`: not enforced at the method level (caller is responsible), but the pipeline convention is that output is always a new path

### Directory creation

Both `save_as_new_dxf` and `EditEngine.save` create parent directories automatically:

```python
output_path.parent.mkdir(parents=True, exist_ok=True)
```

This means the caller does not need to pre-create output directories.

### File naming convention

No specific naming convention is enforced. The caller provides the full output path. The smoke test uses the pattern `{stem}_edited.dxf`. The UI or API layer is responsible for generating user-friendly output names.

---

## Preservation Guarantees

### Original file integrity

The source DXF file is never modified by any writer function. Evidence:

1. `save_as_new_dxf` reads the source via `ezdxf.readfile()` (read-only), then writes to a different path
2. `copy_dxf_for_editing` uses `shutil.copy2` (read-only on source)
3. `EditEngine.__init__` reads via `ezdxf.readfile()` (read-only), all mutations happen in memory, `save()` writes to a new path

**Testable assertion:** After the full pipeline runs (load → edit → save), the source file must be byte-identical to its state before the pipeline started.

### Non-targeted entity preservation

Entities that are not targeted by any operation in the changeset remain unchanged in the output DXF. The edit engine only modifies entities explicitly referenced by handle in the operations. ezdxf preserves all other entities, layers, blocks, and metadata during `saveas()`.

**Testable assertion:** Load the output DXF, iterate all entities not targeted by operations, and verify their handles, positions, text content, and layer assignments are identical to the original.

### Layer table preservation

The layer table (names, colors, frozen/off states) is preserved in its entirety. The edit engine does not add, remove, or modify layers. The revision notes module may create the `AI_REV_NOTES` layer if it does not exist, but all other layers remain untouched.

### Block definitions preservation

All block definitions present in the source DXF are preserved in the output. The edit engine does not modify block definitions. `add_block` operations insert block references but do not alter the definitions themselves.

---

## Roundtrip Definition

### What "roundtrip" means

A roundtrip test verifies that loading a DXF and immediately saving it (with no edits) produces an output that, when reloaded, yields an identical `DrawingContext`.

### Formal definition

Given:
1. `ctx_a = load_dxf(source_path)` — load the original
2. `save_as_new_dxf(source_path, output_path)` — save without edits
3. `ctx_b = load_dxf(output_path)` — reload the output

Then:
- `len(ctx_a.entities) == len(ctx_b.entities)` — entity count preserved
- For each entity `a` in `ctx_a.entities`, there exists an entity `b` in `ctx_b.entities` where:
  - `a.handle == b.handle` — handle preserved
  - `a.entity_type == b.entity_type` — type preserved
  - `a.layer == b.layer` — layer preserved
  - `a.insert_point == b.insert_point` (within coordinate tolerance) — position preserved
  - `a.text_content == b.text_content` — text preserved
  - `a.block_name == b.block_name` — block reference preserved
- `set(ctx_a.blocks) == set(ctx_b.blocks)` — block definitions preserved
- `len(ctx_a.layers) == len(ctx_b.layers)` — layer count preserved
- For each layer `la` in `ctx_a.layers`, there exists a layer `lb` in `ctx_b.layers` where:
  - `la.name == lb.name`
  - `la.protected == lb.protected`
  - `la.visible == lb.visible`
  - `la.frozen == lb.frozen`
  - `la.color == lb.color`
- `ctx_a.metadata["dxf_version"] == ctx_b.metadata["dxf_version"]` — version preserved

### What roundtrip does NOT guarantee

- **Byte-identical output:** The output DXF is not guaranteed to be byte-identical to the source. ezdxf may reorder internal structures, normalize whitespace, or update header fields. The roundtrip guarantee is at the `DrawingContext` semantic level, not the byte level.
- **Unsupported entity types:** Entities of non-V1 types (CIRCLE, ARC, DIMENSION, etc.) are preserved in the DXF file by ezdxf, but they are not tracked in `DrawingContext`. The roundtrip test only verifies V1 entities.
- **`file_path` field:** This will differ between `ctx_a` and `ctx_b` because they were loaded from different files. It is excluded from comparison.

---

## Observability

### `EditEngine.save`

Emits an OTel span `cad.save` with:

| Attribute | Value |
|-----------|-------|
| `cad.save.output_basename` | Filename only (no directory path) |

### `save_as_new_dxf`

No OTel span currently emitted. If tracing is added in a future phase, use span name `cad.save_as_copy`.

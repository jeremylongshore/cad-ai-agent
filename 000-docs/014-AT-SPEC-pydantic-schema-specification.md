# 014-AT-SPEC — Pydantic Data Schema Specification

**Date:** 2026-02-20
**Category:** AT (Architecture & Technical)
**Type:** SPEC (Specification)
**Beads task:** `cad-xoh.1`

---

## Purpose

This document is the authoritative field-level specification for every Pydantic model used in the cad-dxf-agent pipeline. Phase 3 implementation must conform to these definitions. No code is written here — only specifications and behavioral contracts.

---

## Domain Models (`models/cad_schema.py`)

### EntityType (StrEnum)

Enumerates the V1-supported DXF entity types. Any value not in this enum is rejected at parse time.

| Member | Value | DXF Meaning |
|--------|-------|-------------|
| `LINE` | `"LINE"` | Straight line segment between two points |
| `LWPOLYLINE` | `"LWPOLYLINE"` | Lightweight polyline (2D, vertex list) |
| `TEXT` | `"TEXT"` | Single-line text entity |
| `MTEXT` | `"MTEXT"` | Multi-line / rich text entity |
| `INSERT` | `"INSERT"` | Block reference insertion |

**Strictness:** StrEnum inherently rejects unknown values with `ValueError`.

---

### Point2D (BaseModel)

Represents a 2D coordinate. Used for entity positions, insertion points, and anchor points.

| Field | Type | Required | Default | Constraints |
|-------|------|----------|---------|-------------|
| `x` | `float` | yes | — | Finite (no NaN/Inf) |
| `y` | `float` | yes | — | Finite (no NaN/Inf) |

**Notes:**
- All coordinates in drawing units (typically inches or millimeters, determined by the DXF file)
- Z coordinate is always 0 in V1 (2D only) and is not stored

---

### EntityRef (BaseModel)

Normalized reference to a single DXF entity extracted by the reader.

| Field | Type | Required | Default | Description |
|-------|------|----------|---------|-------------|
| `handle` | `str` | yes | — | DXF entity handle (hex string, unique within drawing) |
| `entity_type` | `EntityType` | yes | — | One of the V1 entity types |
| `layer` | `str` | yes | — | Layer name the entity belongs to |
| `insert_point` | `Point2D \| None` | no | `None` | Primary position (start point for LINE, first vertex for LWPOLYLINE, insert for TEXT/MTEXT/INSERT) |
| `text_content` | `str \| None` | no | `None` | Text payload (TEXT: `dxf.text`, MTEXT: plain text extraction) |
| `block_name` | `str \| None` | no | `None` | Referenced block definition name (INSERT only) |
| `attributes` | `dict[str, Any]` | no | `{}` | Extensible bag for future entity-specific properties |

**Field population by entity type:**

| Entity Type | `insert_point` | `text_content` | `block_name` |
|-------------|----------------|----------------|--------------|
| LINE | start point (`dxf.start`) | — | — |
| LWPOLYLINE | first vertex | — | — |
| TEXT | insert point (`dxf.insert`) | `dxf.text` | — |
| MTEXT | insert point (`dxf.insert`) | plain text via `.text` | — |
| INSERT | insert point (`dxf.insert`) | — | `dxf.name` |

---

### LayerRule (BaseModel)

Describes a layer's state and protection status.

| Field | Type | Required | Default | Description |
|-------|------|----------|---------|-------------|
| `name` | `str` | yes | — | Layer name as stored in the DXF layer table |
| `protected` | `bool` | no | `False` | Whether edits to entities on this layer are blocked |
| `visible` | `bool` | no | `True` | Whether the layer is on (not off) |
| `frozen` | `bool` | no | `False` | Whether the layer is frozen |
| `color` | `int \| None` | no | `None` | AutoCAD color index (ACI) |

**Protection resolution:** A layer is marked `protected=True` by the reader when its name (case-insensitive) matches any entry in `settings.protected_layers` (loaded from the `CAD_PROTECTED_LAYERS` environment variable). The validator separately checks against the `RuleConfig.protected_layers` list passed by the caller. Both default to `["TITLE", "TITLEBLOCK", "SEAL", "REVISION"]`.

---

### DrawingContext (BaseModel)

Top-level model representing a fully loaded DXF drawing. This is the only object the planner and validator see — they never touch raw DXF.

| Field | Type | Required | Default | Description |
|-------|------|----------|---------|-------------|
| `file_path` | `str` | yes | — | Absolute or relative path to the source DXF |
| `entities` | `list[EntityRef]` | no | `[]` | All V1 entities from model space |
| `layers` | `list[LayerRule]` | no | `[]` | Layer table with protection flags |
| `blocks` | `list[str]` | no | `[]` | Named block definitions (excluding `*`-prefixed internal blocks) |
| `unsupported_entity_types` | `list[str]` | no | `[]` | DXF types encountered but skipped (sorted, deduplicated) |
| `metadata` | `dict[str, Any]` | no | `{}` | Drawing-level metadata (dxf_version, encoding) |

**Computed properties:**
- `entity_count: int` — `len(self.entities)`

**Methods:**
- `get_entity_by_handle(handle: str) -> EntityRef | None` — linear scan lookup
- `get_protected_layers() -> list[str]` — filters `layers` where `protected=True`

---

## Operation Models (`models/ops_schema.py`)

### OpType (StrEnum)

Enumerates the V1-supported edit operations. Any value not in this enum is rejected at parse time.

| Member | Value | Description |
|--------|-------|-------------|
| `MOVE_ENTITY` | `"move_entity"` | Translate an entity by (dx, dy) |
| `EDIT_TEXT` | `"edit_text"` | Replace text content on TEXT/MTEXT |
| `DELETE_ENTITY` | `"delete_entity"` | Remove an entity from model space |
| `ADD_BLOCK` | `"add_block"` | Insert an existing block definition |

**Strictness:** StrEnum rejects unknown values with `ValueError`.

---

### EditOperation (BaseModel)

A single structured edit instruction. The LLM planner returns these — never raw DXF commands.

| Field | Type | Required | Default | Description |
|-------|------|----------|---------|-------------|
| `op_type` | `OpType` | yes | — | The operation to perform |
| `target_handle` | `str \| None` | no | `None` | DXF handle of target entity (required for move/edit/delete) |
| `target_layer` | `str \| None` | no | `None` | Layer for add_block insertion |
| `params` | `dict[str, Any]` | no | `{}` | Operation-specific parameters |

**Params contract per operation:**

| Op Type | Required Params | Optional Params |
|---------|----------------|-----------------|
| `move_entity` | `dx: float`, `dy: float` | — |
| `edit_text` | `new_text: str` | — |
| `delete_entity` | _(none)_ | — |
| `add_block` | `block_name: str`, `insert_point: {x: float, y: float}` | `scale: float` (default 1.0), `rotation: float` (default 0.0) |

---

### ChangeSet (BaseModel)

A batch of operations produced by a single planner invocation.

| Field | Type | Required | Default | Description |
|-------|------|----------|---------|-------------|
| `operations` | `list[EditOperation]` | no | `[]` | Ordered list of edits to apply |
| `prompt` | `str` | no | `""` | Original user prompt that produced these operations |
| `revision_label` | `str \| None` | no | `None` | Human label for this batch (used in revision notes) |

**Computed properties:**
- `op_count: int` — `len(self.operations)`

---

### AppliedChange (BaseModel)

Post-execution record of a single operation.

| Field | Type | Required | Default | Description |
|-------|------|----------|---------|-------------|
| `operation` | `EditOperation` | yes | — | The operation that was applied |
| `success` | `bool` | no | `True` | Whether the operation succeeded |
| `entity_handle` | `str \| None` | no | `None` | Handle of the affected entity (may differ from target for add_block) |
| `description` | `str` | no | `""` | Human-readable summary of what happened |

---

## Validation Models (`models/changes_schema.py`)

### Severity (StrEnum)

| Member | Value | Effect |
|--------|-------|--------|
| `WARNING` | `"warning"` | Informational; does not prevent apply |
| `BLOCKER` | `"blocker"` | Prevents the entire changeset from being applied |

---

### ValidationIssue (BaseModel)

A single problem found during changeset validation.

| Field | Type | Required | Default | Description |
|-------|------|----------|---------|-------------|
| `severity` | `Severity` | yes | — | Warning or blocker |
| `message` | `str` | yes | — | Human-readable description of the issue |
| `operation_index` | `int \| None` | no | `None` | Zero-based index of the offending operation |
| `field` | `str \| None` | no | `None` | Specific field that caused the issue (if applicable) |

---

### ValidationResult (BaseModel)

Aggregate result of validating an entire changeset.

| Field | Type | Required | Default | Description |
|-------|------|----------|---------|-------------|
| `valid` | `bool` | no | `True` | False if any blocker exists |
| `issues` | `list[ValidationIssue]` | no | `[]` | All issues found |

**Computed properties:**
- `blockers: list[ValidationIssue]` — issues with severity BLOCKER
- `warnings: list[ValidationIssue]` — issues with severity WARNING

**Methods:**
- `add_blocker(message, operation_index=None)` — appends blocker and sets `valid=False`
- `add_warning(message, operation_index=None)` — appends warning (does not affect `valid`)

---

## Configuration Models (`models/config_schema.py`)

### RuleConfig (BaseModel)

Controls validation behavior and layer protection.

| Field | Type | Required | Default | Description |
|-------|------|----------|---------|-------------|
| `protected_layers` | `list[str]` | no | `["TITLE", "TITLEBLOCK", "SEAL", "REVISION"]` | Layer names blocked from editing (case-insensitive match) |
| `protected_blocks` | `list[str]` | no | `[]` | Block names blocked from deletion (reserved for future use) |
| `max_move_distance` | `float \| None` | no | `None` | If set, moves exceeding this distance emit a warning |
| `coordinate_tolerance` | `float` | no | `1e-6` | Tolerance for coordinate comparison |

---

### RevisionNoteConfig (BaseModel)

Controls the deterministic revision note insertion.

| Field | Type | Required | Default | Description |
|-------|------|----------|---------|-------------|
| `enabled` | `bool` | no | `True` | Whether to insert revision notes after edits |
| `layer_name` | `str` | no | `"AI_REV_NOTES"` | Target layer for notes |
| `anchor_point` | `Point2D` | no | `(0.0, -50.0)` | Where to place the note text |
| `text_height` | `float` | no | `2.5` | Text height in drawing units |
| `prefix` | `str` | no | `"REV"` | Prefix for revision labels |
| `revision_number` | `int` | no | `1` | Current revision counter |

---

## Strictness Rules

### Unknown field rejection

All models use Pydantic's default behavior where unknown fields passed to the constructor are silently ignored. For V1, this is acceptable because:
- The LLM response is parsed through `response_parser.py` which extracts only known fields
- Schema-level validation catches type mismatches and missing required fields
- The validator catches invalid op types and missing params

If stricter rejection is needed in a future phase, models can add:
```python
model_config = ConfigDict(extra="forbid")
```

### Invalid operation type rejection

`OpType` is a `StrEnum`. Constructing an `EditOperation` with an invalid `op_type` string raises `ValueError` at parse time. This is enforced by Pydantic's enum validation — no additional code is needed.

### Invalid entity type rejection

`EntityType` is a `StrEnum`. Constructing an `EntityRef` with an invalid `entity_type` string raises `ValueError` at parse time.

---

## Error Behavior

### LLM returns invalid JSON

The `response_parser.py` module wraps `json.loads()` and `ChangeSet.model_validate()`. If either fails, the entire response is rejected with a parse error. No partial changeset is created.

### LLM returns unsupported operation type

Pydantic rejects the `EditOperation` construction when `op_type` is not a valid `OpType` member. The entire changeset is rejected.

### LLM returns valid ops targeting nonexistent entities

Validation passes at the schema level (the operation is well-formed). The validator catches this during `validate_changeset()` and adds a BLOCKER. The changeset is not applied.

### LLM returns ops targeting protected layers

The validator checks entity layers against `RuleConfig.protected_layers` (case-insensitive). A BLOCKER is added and the changeset is not applied.

### Changeset has mixed valid and invalid ops

If any operation produces a BLOCKER, the entire changeset is rejected. Partial application never occurs. This is the atomic batch guarantee.

---

## Entity Index (`core/entity_index.py`)

The `EntityIndex` is not a Pydantic model but is a critical data structure built from `DrawingContext`:

| Lookup | Method | Return |
|--------|--------|--------|
| By handle | `get_by_handle(handle: str)` | `EntityRef \| None` |
| By layer | `get_by_layer(layer: str)` | `list[EntityRef]` (case-insensitive) |
| By type | `get_by_type(entity_type: EntityType)` | `list[EntityRef]` |
| All handles | `handles()` | `list[str]` |
| Total count | `count` (property) | `int` |

The index is built once per `DrawingContext` and used by the validator for O(1) handle lookups.

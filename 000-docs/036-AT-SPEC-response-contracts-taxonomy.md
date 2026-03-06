# 036 — Response Contracts and Task Taxonomy

**Status:** Proposed
**Date:** 2026-03-05
**Depends on:** 034-AT-AUDT (capability audit), 035-AT-ARCH (target architecture)

---

## 1. Problem

Current API responses are ad-hoc dicts constructed per-endpoint with no shared
schema. Callers must know which endpoint they hit to parse the response. There is
no way to distinguish "the LLM answered a question" from "the LLM planned an edit"
from "the system needs clarification." This blocks multi-task-family routing.

---

## 2. TaskFamily Enum

All prompts are classified into exactly one task family before processing.

```python
class TaskFamily(str, Enum):
    """Classifies user intent into a processing pipeline."""
    QNA                      = "qna"                       # Answer a question (read-only)
    MARKUP_INTERPRETATION    = "markup_interpretation"      # Interpret redline annotations
    REPEATED_CONDITION       = "repeated_condition_search"  # Find recurring patterns
    COMPARE                  = "compare"                    # Diff two drawings
    EDIT_PLAN                = "edit_plan"                  # Propose edits (preview)
    APPLY_EDIT               = "apply_edit"                 # Execute confirmed edits
    SUMMARY                  = "summary"                    # Drawing statistics/overview
    TAKEOFF_ESTIMATE         = "takeoff_estimate"           # Quantity/material estimation
    DESIGN_ASSIST            = "design_assist"              # Suggest improvements
```

**Location:** `src/cad_dxf_agent/models/response_schema.py` (proposed)

---

## 3. ResponseType Enum

Discriminator for the response envelope. Determines how the frontend renders results.

```python
class ResponseType(str, Enum):
    """What kind of response is this?"""
    ANSWER_ONLY           = "answer_only"            # Text answer, no operations
    PLAN_ONLY             = "plan_only"               # Proposed operations, not yet applied
    PREVIEW_EDIT          = "preview_edit"             # Proposed operations with visual preview
    APPLIED_EDIT          = "applied_edit"             # Operations have been applied
    NEEDS_CLARIFICATION   = "needs_clarification"     # System needs more information
    UNSUPPORTED_OPERATION = "unsupported_operation"    # Request cannot be fulfilled
```

---

## 4. EvidenceRef Schema

Every response that references drawing entities should include evidence citations
so the frontend can highlight relevant entities and the user can verify answers.

```python
class EvidenceRef(BaseModel):
    """A grounded reference to a drawing entity or region."""
    entity_handle: str | None = None        # Specific entity handle
    layer: str | None = None                # Layer name
    entity_type: str | None = None          # EntityType value
    location: Point2D | None = None         # Spatial reference point
    text_excerpt: str | None = None         # Relevant text content
    description: str                        # Human-readable explanation
```

**Usage examples:**
- Q&A: "The title block is on layer TITLEBLOCK" → evidence refs to TITLEBLOCK entities
- Edit: "Moving entity 1A3 by (10, 0)" → evidence ref to entity 1A3
- Compare: "Entity 2B7 was deleted in revision" → evidence ref to missing entity

---

## 5. PlatformResponse Envelope

All API responses wrapped in a single typed envelope.

```python
class PlatformResponse(BaseModel):
    """Universal response envelope for all task families."""

    # Discriminators
    response_type: ResponseType
    task_family: TaskFamily

    # Payload
    message: str                                    # Human-readable summary
    data: dict[str, Any] | None = None              # Task-specific payload
    evidence: list[EvidenceRef] = []                 # Grounded citations

    # Operations (edit/compare families only)
    operations: list[EditOperation] = []             # Proposed or applied ops
    validation: ValidationResult | None = None       # Blockers and warnings

    # Metadata
    confidence: float | None = None                  # Router confidence (0.0-1.0)
    processing_time_ms: int | None = None            # Pipeline execution time
    session_id: str | None = None                    # Session identifier

    # Render availability
    renders: dict[str, bool] = {}                    # {"original": true, "edited": true, ...}
```

---

## 6. Task Family to ResponseType Mapping

Each task family produces a predictable set of response types.

| TaskFamily | Primary ResponseType | Alternative ResponseTypes |
|-----------|---------------------|--------------------------|
| `qna` | `answer_only` | `needs_clarification` |
| `markup_interpretation` | `answer_only` | `needs_clarification`, `unsupported_operation` |
| `repeated_condition` | `answer_only` | `needs_clarification` |
| `compare` | `answer_only` (changelog) | `plan_only` (revision ops) |
| `edit_plan` | `plan_only` or `preview_edit` | `needs_clarification`, `unsupported_operation` |
| `apply_edit` | `applied_edit` | `unsupported_operation` |
| `summary` | `answer_only` | — |
| `takeoff_estimate` | `answer_only` | `needs_clarification` |
| `design_assist` | `answer_only` or `plan_only` | `needs_clarification` |

**Invariants:**
- `answer_only` responses MUST have zero operations
- `plan_only` and `preview_edit` responses MUST have one or more operations
- `applied_edit` responses MUST have operations AND all validation blockers resolved
- `needs_clarification` responses MUST have a descriptive message
- `unsupported_operation` responses MUST explain why the request cannot be fulfilled

---

## 7. Task-Specific Data Payloads

The `data` field carries task-family-specific information.

### Q&A Data
```python
{
    "answer": "The drawing uses 3 layers: WALLS, DOORS, WINDOWS.",
    "entities_referenced": ["1A3", "2B7", "3C1"],
    "layers_referenced": ["WALLS", "DOORS", "WINDOWS"]
}
```

### Compare Data
```python
{
    "total_changes": 12,
    "changelog": { "by_layer": {...}, "by_type": {...} },
    "diff_summary": { "headline": "12 changes across 3 layers", "warnings": [] }
}
```

### Summary Data
```python
{
    "entity_count": 247,
    "layer_breakdown": { "WALLS": 89, "DOORS": 34, "WINDOWS": 28, ... },
    "type_breakdown": { "LINE": 120, "LWPOLYLINE": 45, "TEXT": 32, ... },
    "bounding_box": { "min": [0, 0], "max": [100, 80] },
    "block_definitions": ["DOOR_SINGLE", "WINDOW_DBL", ...]
}
```

### Takeoff Data
```python
{
    "items": [
        { "name": "Single doors", "count": 12, "block_name": "DOOR_SINGLE" },
        { "name": "Double windows", "count": 8, "block_name": "WINDOW_DBL" }
    ],
    "total_items": 20,
    "methodology": "Block reference count on layers DOORS, WINDOWS"
}
```

---

## 8. Migration Strategy

### Phase 1: Introduce v2 Alongside v1

- Add `/api/v2/prompt` — single unified endpoint accepting any prompt
- `/api/v2/prompt` returns `PlatformResponse` envelope
- All existing `/api/` endpoints continue to work unchanged
- New `PlatformResponse` model in `models/response_schema.py`

### Phase 2: Frontend Migration

- Frontend switches to `/api/v2/prompt` for new features
- Existing edit/compare workflows migrate to v2 responses
- v1 endpoints remain for backward compatibility

### Phase 3: Deprecation

- v1 endpoints marked deprecated (HTTP header + docs)
- Removal after all clients migrated (minimum 2 release cycles)

### Backward Compatibility Rules

- v1 endpoints NEVER break (same request → same response shape)
- v2 responses are a superset (all v1 data available in v2 envelope)
- `task_family` and `response_type` fields are always present in v2
- Unknown `task_family` values → `unsupported_operation` response

---

## 9. Validation Rules for Contracts

These rules should be enforced by tests (see 037-TQ-SPEC).

1. Every `PlatformResponse` must have a non-empty `message`
2. `answer_only` responses must have `len(operations) == 0`
3. `plan_only` / `preview_edit` / `applied_edit` must have `len(operations) > 0`
4. `applied_edit` must have `validation.valid == True` (no unresolved blockers)
5. `needs_clarification` must have `confidence < 0.9` or explicit ambiguity flag
6. `evidence` list should be non-empty for `qna` and `compare` responses
7. `processing_time_ms` must be set by the response formatter (not by callers)

---

## Related Documents

- 034-AT-AUDT — Capability audit (current response format gaps)
- 035-AT-ARCH — Target architecture (response formatter as Layer 6)
- 037-TQ-SPEC — Evaluation plan (contract validation tests)
- 039-AT-ADEC — Intent router (produces TaskFamily for envelope)

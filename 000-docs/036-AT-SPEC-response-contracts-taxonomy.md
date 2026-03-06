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

## 10. Per-Task-Family Detail

### 10.1 Q&A (`qna`)

| Dimension | Detail |
|-----------|--------|
| **Intent signals** | Question words (what/where/how/which), no edit verbs, single-drawing context |
| **Inputs** | Prompt + DrawingContext (single file) |
| **Outputs** | `answer_only` with `data.answer` string + `evidence` refs |
| **Confidence model** | High if entity/layer found; low if ambiguous reference |
| **Failure modes** | Entity not found → `needs_clarification`; ambiguous reference → low confidence |
| **Deterministic tooling** | `find_entities`, `get_entity`, `list_layers` — read-only query tools |
| **Example prompt** | "What layer is entity 1A3 on?" |
| **Example response** | `answer_only` with `data.answer = "Entity 1A3 is on layer WALLS"` |

### 10.2 Markup Interpretation (`markup_interpretation`)

| Dimension | Detail |
|-----------|--------|
| **Intent signals** | "revision cloud", "redline", "markup", "annotation" keywords |
| **Inputs** | Prompt + DrawingContext with markup entities (revision clouds, arrows) |
| **Outputs** | `answer_only` with `data.markups` list; or `plan_only` if edits derived |
| **Confidence model** | High if cloud/arrow entities detected; low if no markup entities found |
| **Failure modes** | No markup entities → `unsupported_operation`; ambiguous markup → `needs_clarification` |
| **Deterministic tooling** | Cloud/arrow detection heuristics (entity type + layer pattern matching) |
| **Example prompt** | "What do the revision clouds indicate?" |
| **Status** | MISSING — requires EPIC-03 (markup entity detection) |

### 10.3 Repeated Condition Search (`repeated_condition_search`)

| Dimension | Detail |
|-----------|--------|
| **Intent signals** | "find all", "every", "recurring", "pattern", "instances of" |
| **Inputs** | Prompt + DrawingContext + optional search pattern (text, block name, spatial) |
| **Outputs** | `answer_only` with `data.matches` list + `evidence` refs per match |
| **Confidence model** | High if exact text/block matches; lower for spatial/similarity matches |
| **Failure modes** | No matches → `answer_only` with empty matches; ambiguous pattern → `needs_clarification` |
| **Deterministic tooling** | `find_entities` (text search), block-name matching, spatial proximity |
| **Example prompt** | "Find all concrete callouts in this drawing" |
| **Status** | PARTIAL (5%) — text search is literal token only, no regex/fuzzy/semantic |

### 10.4 Compare (`compare`)

| Dimension | Detail |
|-----------|--------|
| **Intent signals** | "compare", "diff", "what changed", "revision"; requires two files |
| **Inputs** | Prompt + master DrawingContext + revision DrawingContext |
| **Outputs** | `answer_only` (changelog) or `plan_only` (revision ops for approval) |
| **Confidence model** | Per-change confidence from matching pipeline (0.0-1.0) |
| **Failure modes** | Alignment failure → low overall confidence; no changes → empty changelog |
| **Deterministic tooling** | 15 comparison submodules: alignment, matching, scoring, classification |
| **Example prompt** | "What changed between master and revision B?" |
| **Status** | DONE (70%) — full pipeline exists, needs typed response envelope |

### 10.5 Edit Plan (`edit_plan`)

| Dimension | Detail |
|-----------|--------|
| **Intent signals** | Edit verbs (move, delete, change, add, rename, replace) |
| **Inputs** | Prompt + DrawingContext (single file) |
| **Outputs** | `plan_only` (proposed ops) or `preview_edit` (with visual preview) |
| **Confidence model** | High if entities resolved and ops valid; low if ambiguous targets |
| **Failure modes** | Protected layer → blocker; entity not found → `needs_clarification`; unsupported entity type → `unsupported_operation` |
| **Deterministic tooling** | `find_entities`, `get_entity`, `is_protected`, `propose_edit` — query + edit tools |
| **Example prompt** | "Move all doors on layer DOORS 10 units right" |
| **Status** | DONE (75%) — full planner pipeline with 4 OpTypes |

### 10.6 Apply Edit (`apply_edit`)

| Dimension | Detail |
|-----------|--------|
| **Intent signals** | "apply", "confirm", "yes do it", "execute" — follows a plan_only response |
| **Inputs** | Session with pending ChangeSet (from prior `edit_plan`) |
| **Outputs** | `applied_edit` with validation result + file paths |
| **Confidence model** | Binary — validation passes or fails, no gradations |
| **Failure modes** | No pending plan → `unsupported_operation`; validation blockers → rejected |
| **Deterministic tooling** | `edit_engine.py` applies ops; `validators.py` checks constraints |
| **Example prompt** | "Yes, apply those changes" |
| **Status** | DONE (85%) — edit engine, validation, rendering, download all work |

### 10.7 Summary (`summary`)

| Dimension | Detail |
|-----------|--------|
| **Intent signals** | "summarize", "overview", "statistics", "describe this drawing" |
| **Inputs** | Prompt + DrawingContext (single file) |
| **Outputs** | `answer_only` with `data` containing entity/layer/type breakdowns |
| **Confidence model** | Always high — deterministic aggregation, no LLM interpretation needed |
| **Failure modes** | Empty drawing → valid but sparse summary; large drawing → may hit context cap |
| **Deterministic tooling** | `DrawingStats`, `stats_schema.py`, layer/type counters |
| **Example prompt** | "Give me a summary of this floor plan" |
| **Status** | PARTIAL (15%) — DrawingStats exists but no summary tool or formatted output |

### 10.8 Takeoff / Estimate (`takeoff_estimate`)

| Dimension | Detail |
|-----------|--------|
| **Intent signals** | "count", "how many", "quantity", "takeoff", "estimate", "bill of" |
| **Inputs** | Prompt + DrawingContext + optional scope (layer filter, entity type filter) |
| **Outputs** | `answer_only` with `data.items` list (name, count, block_name) |
| **Confidence model** | High for block counts; lower for inferred quantities (length, area) |
| **Failure modes** | No matching entities → empty items; ambiguous scope → `needs_clarification` |
| **Deterministic tooling** | Block reference counting, entity aggregation by layer/type |
| **Example prompt** | "Count all electrical outlet symbols" |
| **Status** | MISSING (0%) — no quantity logic, counting, or measurement tools |

### 10.9 Design Assist (`design_assist`)

| Dimension | Detail |
|-----------|--------|
| **Intent signals** | "suggest", "improve", "optimize", "recommend", "best practice" |
| **Inputs** | Prompt + DrawingContext + optional domain constraints |
| **Outputs** | `answer_only` (suggestions text) or `plan_only` (proposed improvement ops) |
| **Confidence model** | Lower baseline — suggestions are advisory, not deterministic |
| **Failure modes** | No applicable suggestions → generic advice; out-of-domain → `unsupported_operation` |
| **Deterministic tooling** | None — fully LLM-driven analysis and recommendation |
| **Example prompt** | "Suggest improvements to this floor layout" |
| **Status** | MISSING (0%) — no suggestion pipeline, domain rules, or improvement heuristics |

---

## 11. Per-Response-Type Detail

### 11.1 `answer_only`

Returns text information without modifying the drawing. Used by read-only task families.

```json
{
  "response_type": "answer_only",
  "task_family": "qna",
  "message": "Entity 1A3 is a LINE on layer WALLS, running from (0,0) to (10,5).",
  "data": {
    "answer": "Entity 1A3 is a LINE on layer WALLS, running from (0,0) to (10,5).",
    "entities_referenced": ["1A3"],
    "layers_referenced": ["WALLS"]
  },
  "evidence": [
    {
      "entity_handle": "1A3",
      "layer": "WALLS",
      "entity_type": "LINE",
      "description": "The queried entity"
    }
  ],
  "operations": [],
  "confidence": 0.98
}
```

**Evidence model:** Must include at least one `EvidenceRef` for `qna` and `compare` families. Optional for `summary`.
**Ambiguity flags:** If confidence < 0.7, include `data.ambiguity_note` explaining uncertainty.
**Safety:** Read-only — no drawing modification possible.

### 11.2 `plan_only`

Proposed edit operations not yet applied. Awaits user confirmation.

```json
{
  "response_type": "plan_only",
  "task_family": "edit_plan",
  "message": "I propose moving 3 door entities 10 units to the right.",
  "operations": [
    {"op_type": "move_entity", "target_handle": "2B7", "layer": "DOORS", "params": {"dx": 10, "dy": 0}},
    {"op_type": "move_entity", "target_handle": "2B8", "layer": "DOORS", "params": {"dx": 10, "dy": 0}},
    {"op_type": "move_entity", "target_handle": "2B9", "layer": "DOORS", "params": {"dx": 10, "dy": 0}}
  ],
  "validation": {"valid": true, "blockers": [], "warnings": []},
  "evidence": [
    {"entity_handle": "2B7", "layer": "DOORS", "entity_type": "INSERT", "description": "Door to move"},
    {"entity_handle": "2B8", "layer": "DOORS", "entity_type": "INSERT", "description": "Door to move"},
    {"entity_handle": "2B9", "layer": "DOORS", "entity_type": "INSERT", "description": "Door to move"}
  ],
  "confidence": 0.95
}
```

**Evidence model:** One ref per targeted entity. Helps frontend highlight affected entities.
**Safety:** No modifications until user confirms. Validation runs pre-emptively.
**Transition:** User confirms → triggers `apply_edit` flow returning `applied_edit`.

### 11.3 `preview_edit`

Same as `plan_only` but includes rendered visual preview.

```json
{
  "response_type": "preview_edit",
  "task_family": "edit_plan",
  "message": "Preview: moving 3 doors. See before/after renders.",
  "operations": [
    {"op_type": "move_entity", "target_handle": "2B7", "layer": "DOORS", "params": {"dx": 10, "dy": 0}}
  ],
  "validation": {"valid": true, "blockers": [], "warnings": []},
  "renders": {"original": true, "preview": true},
  "confidence": 0.95
}
```

**Render availability:** `renders.preview = true` signals that a preview PNG is available for download.
**Safety:** Same as `plan_only` — no modifications until confirmed.

### 11.4 `applied_edit`

Operations have been applied to the drawing. File is ready for download.

```json
{
  "response_type": "applied_edit",
  "task_family": "apply_edit",
  "message": "Applied 3 move operations. Edited file ready for download.",
  "operations": [
    {"op_type": "move_entity", "target_handle": "2B7", "layer": "DOORS", "params": {"dx": 10, "dy": 0}}
  ],
  "validation": {"valid": true, "blockers": [], "warnings": []},
  "renders": {"original": true, "edited": true},
  "confidence": 1.0
}
```

**Safety:** Validation MUST show `valid: true` with zero blockers. Original file never modified (save-as).
**Invariant:** `applied_edit` responses MUST have `validation.valid == True`.

### 11.5 `needs_clarification`

System cannot proceed without additional information from the user.

```json
{
  "response_type": "needs_clarification",
  "task_family": "edit_plan",
  "message": "I found 3 entities matching 'door'. Which one do you want to move?",
  "data": {
    "candidates": [
      {"handle": "2B7", "layer": "DOORS", "description": "Single door at (10, 20)"},
      {"handle": "2B8", "layer": "DOORS", "description": "Double door at (30, 20)"},
      {"handle": "2B9", "layer": "DOORS", "description": "Fire door at (50, 20)"}
    ],
    "ambiguity_type": "multiple_matches",
    "suggestion": "Try specifying the entity handle or location."
  },
  "evidence": [
    {"entity_handle": "2B7", "layer": "DOORS", "description": "Candidate match"},
    {"entity_handle": "2B8", "layer": "DOORS", "description": "Candidate match"},
    {"entity_handle": "2B9", "layer": "DOORS", "description": "Candidate match"}
  ],
  "operations": [],
  "confidence": 0.4
}
```

**Ambiguity types:** `multiple_matches`, `no_matches`, `unclear_intent`, `missing_parameter`.
**Safety:** No operations executed. User must re-prompt with clarification.

### 11.6 `unsupported_operation`

Request cannot be fulfilled by the platform.

```json
{
  "response_type": "unsupported_operation",
  "task_family": "edit_plan",
  "message": "Cannot edit entities on the TITLEBLOCK layer — it is protected.",
  "data": {
    "reason": "protected_layer",
    "blocked_layer": "TITLEBLOCK",
    "suggestion": "Protected layers (TITLE, TITLEBLOCK, SEAL, REVISION) cannot be modified."
  },
  "operations": [],
  "confidence": 1.0
}
```

**Reasons:** `protected_layer`, `unsupported_entity_type`, `unsupported_task`, `no_drawing_loaded`, `session_expired`.
**Safety:** No operations executed. Clear explanation of why the request was blocked.

---

## Related Documents

- 034-AT-AUDT — Capability audit (current response format gaps)
- 035-AT-ARCH — Target architecture (response formatter as Layer 6)
- 037-TQ-SPEC — Evaluation plan (contract validation tests)
- 039-AT-ADEC — Intent router (produces TaskFamily for envelope)

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
    UNSUPPORTED              = "unsupported_operation"      # Catch-all for unclassifiable prompts
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
| `unsupported_operation` | `unsupported_operation` | — |

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

### 10.10 Unsupported Operation (`unsupported_operation`)

| Dimension | Detail |
|-----------|--------|
| **Intent signals** | Prompt does not match any known task family pattern; or explicitly out-of-scope request |
| **Inputs** | Raw prompt text (drawing context may or may not be available) |
| **Outputs** | `unsupported_operation` response with reason code and suggestion |
| **Confidence model** | Always 1.0 — the system is certain the request is unsupported |
| **Failure modes** | False positive — a legitimate prompt misclassified as unsupported (router confidence too low for all families). Mitigated by tuning router thresholds and adding `needs_clarification` as an intermediate step. |
| **Deterministic tooling** | Not required — classification is the router's responsibility |
| **Example prompt** | "Generate a 3D rendering of this floor plan" |
| **Example response** | `unsupported_operation` with `data.reason = "unsupported_task"` and helpful suggestion |
| **Status** | PARTIAL — `unsupported_operation` ResponseType exists, but no dedicated router fallback path yet |

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

## 12. Required vs Optional Fields Matrix

Each `PlatformResponse` field is classified per response type as **REQ** (required — must be present and non-empty), **OPT** (optional — may be present), or **N/A** (not applicable — should be absent or empty).

| Field | `answer_only` | `plan_only` | `preview_edit` | `applied_edit` | `needs_clarification` | `unsupported_operation` |
|-------|:---:|:---:|:---:|:---:|:---:|:---:|
| `message` | REQ | REQ | REQ | REQ | REQ | REQ |
| `data` | REQ | OPT | OPT | OPT | OPT | REQ |
| `evidence` | REQ (qna, compare) / OPT (others) | OPT | OPT | OPT | OPT | N/A |
| `operations` | N/A (must be empty) | REQ (>=1) | REQ (>=1) | REQ (>=1) | N/A (must be empty) | N/A (must be empty) |
| `validation` | N/A | REQ | REQ | REQ (valid=true) | N/A | N/A |
| `confidence` | REQ | REQ | REQ | REQ | REQ | REQ |
| `renders` | N/A | N/A | REQ (preview=true) | REQ (edited=true) | N/A | N/A |
| `warnings` | OPT | OPT (in validation) | OPT (in validation) | OPT (in validation) | OPT | OPT |

**Notes:**
- `message` is universally required — every response must be explainable in natural language.
- `data` is required for `answer_only` (carries the answer payload) and `unsupported_operation` (carries reason code). Optional elsewhere for supplemental metadata.
- `operations` being N/A means the field must be an empty list (`[]`), not absent.
- `validation` is required for any response that includes operations, even if all checks pass.

---

## 13. Confidence Model

### 13.1 Confidence Sources

Confidence values in `PlatformResponse.confidence` originate from different sources depending on the pipeline stage.

| Source | Description | Produces |
|--------|-------------|----------|
| **Router confidence** | How certain the intent classifier is about the selected `TaskFamily` | Float 0.0–1.0 |
| **LLM confidence** | Self-reported certainty from the LLM provider (when available) | Float 0.0–1.0 |
| **Validation confidence** | Deterministic — binary pass/fail from the validator | 1.0 (pass) or 0.0 (fail) |
| **Matching confidence** | Per-entity confidence from the comparison/matching pipeline | Float 0.0–1.0 |

### 13.2 Confidence by Response Type

| ResponseType | Confidence Source | Calculation |
|-------------|------------------|-------------|
| `answer_only` | Router + LLM | `min(router_confidence, llm_confidence)` — both must agree |
| `plan_only` | Router + LLM | `min(router_confidence, llm_confidence)` — entity resolution factors in |
| `preview_edit` | Router + LLM | Same as `plan_only` |
| `applied_edit` | Validation | Always 1.0 — validation passed, operations applied successfully |
| `needs_clarification` | Router | Router confidence that triggered the clarification request |
| `unsupported_operation` | Router or Validation | 1.0 — the system is certain the request is unsupported or blocked |

### 13.3 Thresholds

| Threshold | Value | Effect |
|-----------|-------|--------|
| **Clarification trigger** | Router confidence < 0.5 | Prompt is routed to `needs_clarification` instead of a task family |
| **Low confidence warning** | confidence < 0.7 | Response includes `data.ambiguity_note` explaining uncertainty |
| **High confidence** | confidence >= 0.9 | Response is presented without caveats |

### 13.4 Per-Task-Family Acceptable Ranges

| TaskFamily | Typical Range | Notes |
|-----------|--------------|-------|
| `qna` | 0.7–1.0 | High when entities found; drops for ambiguous references |
| `markup_interpretation` | 0.5–0.9 | Depends on markup entity detection quality |
| `repeated_condition_search` | 0.6–1.0 | Exact text matches = high; fuzzy/spatial = lower |
| `compare` | 0.6–1.0 | Per-change confidence aggregated to overall |
| `edit_plan` | 0.7–1.0 | High when entities resolved and ops valid |
| `apply_edit` | 1.0 | Always 1.0 — validation is binary pass/fail |
| `summary` | 0.9–1.0 | Deterministic aggregation, always high |
| `takeoff_estimate` | 0.6–0.9 | Block counts = high; inferred quantities = lower |
| `design_assist` | 0.4–0.8 | Advisory nature means lower baseline |
| `unsupported_operation` | 1.0 | Always certain |

### 13.5 Propagation Rules

- **Router confidence** is computed deterministically by the intent classifier (heuristic or hybrid). It is NOT an LLM-generated value.
- **LLM confidence** is extracted from the provider response when available (e.g., Gemini function-call confidence). If unavailable, defaults to 0.8.
- **Final confidence** on the `PlatformResponse` is the minimum of all contributing sources — the weakest link determines overall confidence.
- Confidence values MUST NOT be fabricated. If no meaningful confidence can be computed, the field should be omitted (`None`) rather than set to an arbitrary value.

---

## 14. Schema Versioning

### 14.1 Version Field

The `PlatformResponse` envelope includes a `schema_version` field to support forward-compatible evolution.

```python
class PlatformResponse(BaseModel):
    schema_version: str = "1.0"  # Semantic version of the response schema
    # ... all other fields as defined in section 5
```

### 14.2 Versioning Rules

1. **Additive-only within a major version.** New optional fields may be added to `PlatformResponse` or `data` payloads without bumping the major version. Existing fields never change type or meaning within a major version.
2. **Breaking changes require a major version bump.** Removing a field, changing a field's type, renaming a field, or altering enum semantics constitutes a breaking change and requires incrementing the major version (e.g., `1.x` → `2.0`).
3. **Minor versions for additions.** Adding a new optional field bumps the minor version (e.g., `1.0` → `1.1`). Adding a new `TaskFamily` or `ResponseType` enum value bumps the minor version.
4. **Clients must tolerate unknown fields.** Pydantic's `model_config = ConfigDict(extra="ignore")` ensures that newer responses with additional fields do not break older clients.
5. **Version announced in response.** Every `PlatformResponse` includes `schema_version` so clients can detect and adapt to schema changes programmatically.

### 14.3 Migration Path

- v1.0: Initial schema as defined in this document
- Future additions (new task families, new data fields) increment minor version
- If the envelope structure itself changes (different discriminator pattern, nested envelopes), that triggers v2.0

---

## 15. Data Payload Schemas for Unimplemented Task Families

These schemas define the target `data` shape for task families not yet implemented. They serve as contracts for future development — implementations MUST conform to these shapes.

### 15.1 Markup Interpretation Data

```python
{
    "markups": [
        {
            "markup_type": "revision_cloud",       # revision_cloud | arrow | callout | strikethrough
            "entity_handles": ["4D1", "4D2"],      # Handles of entities forming the markup
            "layer": "MARKUP",                      # Layer the markup resides on
            "bounding_box": {"min": [10, 20], "max": [30, 40]},
            "affected_entities": ["1A3", "2B7"],   # Entities the markup references/surrounds
            "interpretation": "These walls should be moved 5 units north.",
            "confidence": 0.75
        }
    ],
    "total_markups": 3,
    "unresolved_markups": 1,                       # Markups that could not be interpreted
    "suggested_operations": []                      # Optional: derived edit ops if markup implies changes
}
```

**Status:** MISSING — requires EPIC-03 (markup entity detection and interpretation pipeline).

### 15.2 Repeated Condition Search Data

```python
{
    "matches": [
        {
            "entity_handle": "3C1",
            "layer": "NOTES",
            "entity_type": "TEXT",
            "text_content": "SEE DETAIL A",
            "location": [45.0, 22.5],
            "match_type": "exact_text",            # exact_text | fuzzy_text | block_name | spatial_pattern
            "match_score": 1.0
        }
    ],
    "total_matches": 7,
    "search_pattern": "SEE DETAIL A",              # The pattern that was searched for
    "search_scope": {                               # Filters applied during search
        "layers": null,                             # null = all layers searched
        "entity_types": ["TEXT", "MTEXT"],
        "spatial_bounds": null                      # null = entire drawing
    },
    "match_methods_used": ["exact_text"]            # Which methods produced results
}
```

**Status:** PARTIAL (5%) — literal text search only. Fuzzy, regex, and spatial pattern matching not yet implemented.

### 15.3 Design Assist Data

```python
{
    "suggestions": [
        {
            "category": "spacing",                 # spacing | alignment | accessibility | code_compliance | efficiency
            "severity": "recommendation",          # recommendation | warning | critical
            "description": "Door swing overlaps with adjacent wall segment.",
            "affected_entities": ["2B7", "1A3"],
            "suggested_action": "Move door 2B7 by (2, 0) to clear wall 1A3.",
            "proposed_operations": [               # Optional: concrete ops if suggestion is actionable
                {"op_type": "move_entity", "target_handle": "2B7", "params": {"dx": 2, "dy": 0}}
            ],
            "confidence": 0.6
        }
    ],
    "total_suggestions": 3,
    "domain": "architectural_floor_plan",          # Detected or user-specified domain context
    "analysis_scope": "full_drawing"               # full_drawing | selected_region | selected_layer
}
```

**Status:** MISSING (0%) — no suggestion pipeline, domain rules, or improvement heuristics.

---

## 16. Risk Model

### 16.1 Risk Level Field

Each `PlatformResponse` carries a `risk_level` field indicating the potential for irreversible or destructive changes.

```python
class RiskLevel(str, Enum):
    """Classification of response risk to the user's drawing."""
    NONE        = "none"          # Read-only, no modification possible
    LOW         = "low"           # Proposed changes, not yet applied; easily reversible
    DESTRUCTIVE = "destructive"   # Changes have been applied to a file on disk
```

```python
class PlatformResponse(BaseModel):
    risk_level: RiskLevel = RiskLevel.NONE
    # ... all other fields as defined in section 5
```

### 16.2 Risk Classification by Response Type

| ResponseType | Risk Level | Rationale |
|-------------|-----------|-----------|
| `answer_only` | `none` | Read-only — no drawing modification possible |
| `plan_only` | `low` | Proposed operations are not applied; user can discard |
| `preview_edit` | `low` | Same as `plan_only` — preview renders but does not persist changes |
| `applied_edit` | `destructive` | Operations applied and written to a new file. Original is preserved (save-as) but the edit is committed. |
| `needs_clarification` | `none` | No operations executed; informational only |
| `unsupported_operation` | `none` | No operations executed; request was blocked |

### 16.3 Risk Classification by Task Family

| TaskFamily | Max Risk Level | Notes |
|-----------|---------------|-------|
| `qna` | `none` | Always read-only |
| `markup_interpretation` | `low` | May propose derived edits, never auto-applies |
| `repeated_condition_search` | `none` | Always read-only search |
| `compare` | `none` | Read-only diff; revision ops are `plan_only` at most |
| `edit_plan` | `low` | Proposes but does not apply |
| `apply_edit` | `destructive` | Applies edits to file (save-as workflow preserves original) |
| `summary` | `none` | Always read-only |
| `takeoff_estimate` | `none` | Always read-only |
| `design_assist` | `low` | May propose edits, never auto-applies |
| `unsupported_operation` | `none` | No processing occurs |

### 16.4 Safety Invariants

1. **No silent writes.** A response with `risk_level = "destructive"` MUST have been preceded by a `plan_only` or `preview_edit` response that the user explicitly confirmed.
2. **Original preserved.** Even `destructive` responses use save-as workflow — the original DXF file is never overwritten.
3. **Protected layers block destructive ops.** Any operation targeting a protected layer (TITLE, TITLEBLOCK, SEAL, REVISION) is rejected before reaching `destructive` risk level.
4. **Risk level is deterministic.** It is set by the response formatter based on `response_type`, never by the LLM.

---

## Related Documents

- 034-AT-AUDT — Capability audit (current response format gaps)
- 035-AT-ARCH — Target architecture (response formatter as Layer 6)
- 037-TQ-SPEC — Evaluation plan (contract validation tests)
- 039-AT-ADEC — Intent router (produces TaskFamily for envelope)

# 035 — Drawing Intelligence Target Architecture

**Status:** Proposed
**Date:** 2026-03-05
**Depends on:** 034-AT-AUDT (capability audit baseline)

---

## 1. Vision

Evolve cad-dxf-agent from a single-purpose DXF edit tool into a Drawing Intelligence
Platform that supports two user workflow classes:

- **Design Operations User** — architects, engineers using CAD daily for design iteration
- **Construction Drawing User** — contractors, inspectors reviewing drawings for field work

The platform must route any natural-language prompt to the correct pipeline, apply
appropriate safety checks, and return a typed response with evidence citations.

---

## 2. Layered Architecture

```
                     User Prompt
                         |
                   [Intent Router]              ← NEW (see 039-AT-ADEC)
                    /    |    \
            Q&A  Edit  Compare  ...TaskFamily
              |    |      |
         [Selection Engine]                     ← ENHANCED (entity_index.py)
              |    |      |
         [Context Builder]                      ← ENHANCED (semantic_model.py)
              |    |      |
           [Tool Layer]                         ← EXTENDED (new tools)
              |    |      |
          [Safety Layer]                        ← ENHANCED (validators.py)
              |    |      |
       [Response Formatter]                     ← NEW (see 036-AT-SPEC)
              |    |      |
          [Eval Layer]                          ← NEW (see 037-TQ-SPEC)
              |
           Response
```

---

## 3. Layer Specifications

### 3.1 Intent Router (NEW)

**Input:** Raw user prompt (string) + session context (optional)
**Output:** `TaskFamily` enum + confidence score + extracted parameters

**Design:** Hybrid heuristic + LLM (see 039-AT-ADEC for full ADR).

- Fast path: regex/keyword rules for unambiguous intents (95%+ of prompts)
- Slow path: LLM classification for ambiguous prompts
- Fallback: `needs_clarification` response if confidence < threshold

**Key decisions:**
- Router runs BEFORE any drawing context is loaded for the fast path
- `compare` requires two files; `qna` operates on a single drawing
- Router output determines which downstream pipeline is invoked

**Integration point:** New module `src/cad_dxf_agent/llm/intent_router.py`

### 3.2 Selection Engine (ENHANCED)

**Input:** TaskFamily + prompt parameters + DrawingContext
**Output:** Filtered entity set relevant to the task

**Current:** `core/entity_index.py` — handle, layer, type, text-token, radius queries.

**Enhancements needed:**
- Regex and fuzzy text search (`search_text_pattern()`)
- Bounding-box region selection (`find_in_bbox(x1, y1, x2, y2)`)
- Multi-drawing selection for compare workflows
- "Find similar" pattern matching (same block, same text pattern)

**Integration point:** Extend `core/entity_index.py` with new query methods.

### 3.3 Context Builder (ENHANCED)

**Input:** TaskFamily + selected entities + DrawingContext metadata
**Output:** Task-specific JSON context for the planner/tool layer

**Current:** `core/semantic_model.py` — flat JSON dump capped at 500 entities.

**Enhancements needed:**
- Task-family-aware context shaping (Q&A needs layer summary, edit needs entity detail)
- Region-focused context (only entities near the target area)
- Cross-drawing context for compare (both drawings in one payload)
- Token budget awareness (stay within LLM context window)

**Integration point:** Extend `core/semantic_model.py` or create
`core/context_strategies.py` with strategy pattern per TaskFamily.

### 3.4 Tool Layer (EXTENDED)

**Input:** LLM tool calls from planner
**Output:** Tool results (query data or accumulated EditOperations)

**Current:** 9 tools (5 query + 4 edit) in `llm/tool_definitions.py`.

**New tools needed:**

| Tool | TaskFamily | Returns |
|------|-----------|---------|
| `answer` | qna | Text answer with entity references |
| `summarize_drawing` | summary | DrawingStats + layer breakdown |
| `measure_distance` | qna, takeoff | Distance between two points/entities |
| `count_entities` | summary, takeoff | Filtered count with breakdown |
| `find_pattern` | repeated_condition | Entities matching a regex/spatial pattern |
| `annotate` | markup_interpretation | Add annotation without editing geometry |

**Integration point:** Add to `llm/tool_definitions.py` and `llm/tool_executor.py`.

### 3.5 Safety Layer (ENHANCED)

**Input:** Proposed operations + RuleConfig + TaskFamily
**Output:** ValidationResult (blockers + warnings)

**Current:** `core/validators.py` — protected layers, entity existence, numeric checks.

**Enhancements needed:**
- Cross-operation conflict detection (two moves on same entity)
- Task-family-appropriate validation (Q&A should produce zero edits)
- Impact estimation (entity count, spatial area of change)
- Enforce `protected_blocks` (field exists in RuleConfig but unused)

**Integration point:** Extend `core/validators.py`.

### 3.6 Response Formatter (NEW)

**Input:** Task result + TaskFamily + evidence references
**Output:** `PlatformResponse` envelope (see 036-AT-SPEC)

**Design:** Every response wrapped in a typed envelope with:
- `response_type` discriminator (answer_only, plan_only, preview_edit, etc.)
- `task_family` tag
- `evidence` list of entity/layer references
- `data` payload (task-family-specific)

**Integration point:** New module `src/cad_dxf_agent/models/response_schema.py`
and formatter in `core/response_formatter.py`.

### 3.7 Eval Layer (NEW)

**Input:** Prompt + response + expected outcome (from golden fixtures)
**Output:** Pass/fail + capability scorecard metrics

**Design:** See 037-TQ-SPEC for full evaluation plan.

**Integration point:** `tests/eval/` directory with scorecard runner.

---

## 4. Workflow Mappings

### Design Operations User Workflows

| Workflow | Intent | Pipeline Path |
|----------|--------|--------------|
| "Move the north wall 2 feet right" | `edit_plan` → `apply_edit` | Router → Selection → Context → Planner → Validator → Preview → Apply |
| "What scale is this drawing?" | `qna` | Router → Context (metadata-only) → Answer tool → Response |
| "Show me all door symbols" | `qna` | Router → Selection (type=INSERT, block=*DOOR*) → Answer tool → Response |
| "Compare with yesterday's revision" | `compare` | Router → Two-file Selection → Comparison Engine → Approval → Apply |
| "Summarize this floor plan" | `summary` | Router → Context → Summarize tool → Response |

### Construction Drawing User Workflows

| Workflow | Intent | Pipeline Path |
|----------|--------|--------------|
| "Are there any revision clouds?" | `markup_interpretation` | Router → Selection (markup entities) → Classifier → Response |
| "Find all concrete callouts" | `repeated_condition` | Router → Pattern search → Grouped results → Response |
| "What changed between rev A and rev B?" | `compare` | Router → Comparison Engine → Changelog → Response |
| "Count all electrical outlets" | `takeoff_estimate` | Router → Selection (block=OUTLET) → Count → Response |
| "Flag non-compliant dimensions" | `design_assist` | Router → Selection → Rule engine → Response |

---

## 5. Integration with Existing Modules

The architecture extends existing code rather than replacing it.

| Existing Module | Role in New Architecture | Changes |
|----------------|------------------------|---------|
| `core/entity_index.py` | Selection Engine | Add regex search, bbox query, find-similar |
| `core/semantic_model.py` | Context Builder | Add task-family strategies, token budgeting |
| `core/validators.py` | Safety Layer | Add cross-op checks, impact estimation |
| `core/edit_engine.py` | Tool Layer (apply) | No changes (stable) |
| `core/comparison/` | Compare pipeline | Integrate with intent router, response formatter |
| `llm/tool_definitions.py` | Tool Layer (schemas) | Add 6+ new tool schemas |
| `llm/tool_executor.py` | Tool Layer (dispatch) | Add handlers for new tools |
| `llm/providers.py` | Planner provider ABC | No changes (stable) |
| `models/ops_schema.py` | Data models | Add new OpTypes if needed |
| `web/backend/main.py` | API surface | Add `/api/v2/` endpoints using response envelope |
| `settings.py` | Configuration | Add intent router settings |

---

## 6. Service Boundaries

### In-Process (single Python process)

All layers run in the same process. No microservices, no message queues. The platform
is local-first by design (see 004-AT-ADEC).

### External Dependencies

| Dependency | Layer | Required? |
|-----------|-------|-----------|
| Gemini (Vertex AI) | Tool Layer (planner) | Yes for prod; mock for CI |
| ezdxf | Selection, Context, Tool | Yes (core DXF library) |
| ODA FileConverter | Input (DWG→DXF) | Optional |
| Firebase Auth | Web API | Yes for web; dev mode skips |
| Cloud Run | Web deployment | Yes for web |

### API Versioning

- `/api/` — current endpoints, stable, no breaking changes
- `/api/v2/` — new endpoints using `PlatformResponse` envelope (proposed in 036)
- Migration: v2 endpoints introduced alongside v1; deprecation after all clients migrate

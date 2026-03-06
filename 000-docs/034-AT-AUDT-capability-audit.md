# 034 — Capability Audit: Current vs Target

**Status:** Baseline snapshot (proposed)
**Date:** 2026-03-05
**Scope:** Map existing cad-dxf-agent capabilities against Design Operations and
Construction Drawing workflow requirements.

---

## 1. Task Family x Capability Matrix

Nine task families the platform must eventually support, scored against current
implementation. Scores: DONE = production-ready, PARTIAL = exists but incomplete,
MISSING = no implementation.

| # | Task Family | Intent Detection | Selection/Query | Context Building | Tool Coverage | Safety/Validation | Response Format | Score |
|---|------------|-----------------|----------------|-----------------|--------------|-------------------|----------------|-------|
| 1 | **Edit (move/delete/text/block)** | PARTIAL (keyword in mock, one-shot in Gemini) | DONE (9 tools: 5 query + 4 edit) | DONE (semantic_model.py caps at 500 entities) | DONE (4 OpTypes) | DONE (protected layers + numeric checks) | PARTIAL (ad-hoc dict) | 75% |
| 2 | **Q&A** (answer questions about drawing) | MISSING | PARTIAL (query tools exist but no Q&A path) | DONE (DrawingContext serializable) | MISSING (no answer-only tool) | N/A | MISSING (no answer envelope) | 15% |
| 3 | **Compare** (revision diff) | MISSING (hardcoded to compare endpoint) | DONE (15 comparison submodules) | DONE (GeometrySnapshot + matcher) | DONE (6 RevisionOpTypes) | PARTIAL (approval workflow, no cross-op checks) | PARTIAL (compare response dict) | 70% |
| 4 | **Markup Interpretation** | MISSING | MISSING (no markup/cloud detection) | MISSING | MISSING | MISSING | MISSING | 0% |
| 5 | **Repeated Condition Search** | MISSING | PARTIAL (text search is token-only, no regex/pattern) | MISSING (no multi-region context) | MISSING | MISSING | MISSING | 5% |
| 6 | **Summary** (drawing statistics) | MISSING | PARTIAL (DrawingStats exists) | PARTIAL (stats_schema.py) | MISSING (no summary tool) | N/A | MISSING | 15% |
| 7 | **Takeoff/Estimate** | MISSING | MISSING | MISSING | MISSING | MISSING | MISSING | 0% |
| 8 | **Design Assist** (suggest improvements) | MISSING | MISSING | MISSING | MISSING | MISSING | MISSING | 0% |
| 9 | **Apply Edit** (execute approved plan) | DONE (edit_engine.py) | DONE | DONE | DONE | DONE | PARTIAL (results dict) | 85% |

---

## 2. Technical Layer Assessment

### Layer 1: Intent Routing

**Current:** No router. Web endpoints are manually separated (`/api/plan` for edits,
`/api/compare` for diffs). The mock provider uses keyword matching; Gemini providers
receive the raw prompt with no pre-classification.

**Evidence:**
- `web/backend/main.py` — endpoints hardcoded by workflow type
- `llm/mock_provider.py:13-89` — keyword patterns (move/delete/text/block)
- `llm/agent_provider.py:38+` — all prompts go through same tool-use loop

**Gap:** No intent classification. Every prompt is assumed to be an edit request unless
the user hits a different endpoint. Q&A prompts produce empty changesets or hallucinated
operations.

### Layer 2: Selection Engine

**Current:** EntityIndex provides handle, layer, type, text-token, and radius-based
spatial queries. Gemini tools expose these as `find_entities`, `get_entity`,
`find_nearest`, `list_layers`, `is_protected`.

**Evidence:**
- `core/entity_index.py:37-177` — 7 query methods
- `llm/tool_definitions.py:38-152` — 5 query tool schemas
- `llm/tool_executor.py:43-60` — tool dispatch

**Gaps:**
- Text search is literal token match only (no regex, no fuzzy, no semantic)
- Spatial query is radius-only (no bbox, no polygon region)
- No multi-drawing selection (compare needs two DrawingContexts)
- No "find similar" or pattern-matching query

### Layer 3: Context Building

**Current:** `semantic_model.py` serializes DrawingContext to JSON for the planner.
Caps at 500 entities. Vision pipeline renders DXF to PNG for multimodal input.

**Evidence:**
- `core/semantic_model.py` — JSON context builder
- `llm/vision_describer.py` — DXF-to-PNG-to-description pipeline
- `core/context_builder.py` — summary metadata extraction

**Gaps:**
- No task-family-specific context shaping (Q&A needs different context than edit)
- No region-focused context (send only relevant entities for a localized question)
- No cross-drawing context (compare needs both drawings in one context)

### Layer 4: Tool Layer

**Current:** 9 tools (5 query + 4 edit) via `tool_definitions.py`. ToolExecutor
dispatches calls and accumulates EditOperations.

**Evidence:**
- `llm/tool_definitions.py` — 9 function schemas
- `llm/tool_executor.py` — dispatch + accumulation
- `models/ops_schema.py:11-17` — OpType enum (4 values)

**Gaps:**
- No "answer" tool (return text without editing)
- No "summarize" tool (aggregate statistics)
- No "measure" tool (distance, area calculations)
- No "annotate" tool (add markup without editing geometry)
- Entity types limited to V1 set (5 of 14 defined types)

### Layer 5: Safety Layer

**Current:** `validators.py` checks protected layers, entity existence, numeric
validity, and optional move-distance warnings. Entire changeset rejected if any
blocker found.

**Evidence:**
- `core/validators.py` — validation pipeline
- `models/config_schema.py` — RuleConfig, protected layers
- `models/changes_schema.py` — ValidationResult with blockers + warnings

**Gaps:**
- No cross-operation conflict detection (two ops on same entity)
- No undo-safety check (verify entity state before re-edit)
- No cost/impact estimation (how many entities affected, area of change)
- `protected_blocks` field exists in RuleConfig but not enforced in code

### Layer 6: Response Formatting

**Current:** Web endpoints return ad-hoc dicts. Each endpoint constructs its own
response shape. No shared envelope, no typed response models, no evidence citations.

**Evidence:**
- `web/backend/main.py:346-355` — plan response dict
- `web/backend/main.py:416-423` — apply response dict
- `web/backend/main.py:521-529` — compare response dict

**Gaps:**
- No `ResponseType` discriminator (caller must know which endpoint it hit)
- No evidence references (which entities support the answer)
- No confidence scores on non-comparison responses
- No structured error taxonomy (generic HTTPException)

---

## 3. System Boundary Analysis

### Inputs

| Input Type | Supported | Format | Limitations |
|-----------|-----------|--------|-------------|
| DXF file | DONE | R12-R2018 via ezdxf | V1 entity types only |
| PDF file | DONE | via pymupdf → DXF conversion | Quality depends on PDF structure |
| DWG file | PARTIAL | via ODA FileConverter (external) | Requires ODA installation |
| Natural language prompt | DONE | Text string | No structured intent parsing |
| Revision DXF (second file) | DONE | Same as master | Compare endpoint only |
| Markup/redline annotations | MISSING | — | — |
| Image of drawing | PARTIAL | Vision pipeline renders DXF→PNG | Cannot accept external images |

### Outputs

| Output Type | Supported | Format | Limitations |
|------------|-----------|--------|-------------|
| Edited DXF | DONE | Save-as new file | V1 entity types only |
| Operation preview | DONE | Human-readable text | No visual diff preview |
| PNG render | DONE | Via ezdxf/matplotlib | Static, no zoom/pan |
| Comparison overlay | DONE | Colored-layer DXF | Requires viewer |
| Changelog | DONE | JSON + markdown | Comparison only |
| Revision bundle | DONE | ZIP (master + revision + overlay + changelog) | Compare only |
| Text answer | MISSING | — | No Q&A pipeline |
| Evidence citations | MISSING | — | No grounded references |
| Domain outputs (BOQ, schedule) | MISSING | — | — |

### Failure Points

1. **Ambiguous prompts** — No clarification mechanism; system either guesses or returns empty changeset
2. **Large drawings** — 500-entity cap in semantic model drops information silently
3. **Wrong intent** — Q&A prompt routed to edit pipeline produces garbage operations
4. **Unhandled entity types** — V2 entities loaded but silently skipped in edits
5. **Multi-step workflows** — No durable session state; conversation history is in-memory only

---

## 4. Gap Priority Ranking

Ranked by impact on Design Operations and Construction Drawing workflows.

| Priority | Gap | Blocks | Effort |
|----------|-----|--------|--------|
| P0 | Intent router (separate Q&A from edit from compare) | All new task families | Medium |
| P0 | Typed response envelope | Clean API contracts for all families | Low |
| P1 | Q&A pipeline (answer without editing) | Drawing questions workflow | Medium |
| P1 | Enhanced text/pattern search | Repeated condition search | Medium |
| P2 | Markup interpretation | Construction redline workflow | High |
| P2 | Summary/statistics tool | Drawing overview workflow | Low |
| P2 | Evidence citations in responses | Trust and auditability | Medium |
| P3 | Domain-specific outputs (BOQ, takeoff) | Specialized construction workflows | High |
| P3 | Design assist (suggestions) | Advanced design operations | High |
| P3 | Durable sessions | Multi-step workflows | Medium |

---

## 5. Current Inventory Summary

| Dimension | Count | Detail |
|-----------|-------|--------|
| Source modules | ~60 | Python files under `src/cad_dxf_agent/` |
| Pydantic models | ~35 | Across 7 schema files in `models/` |
| LLM providers | 6 | Mock, Gemini, Agent, MockAgent, Proxy, GeminiKey |
| Agent tools | 9 | 5 query + 4 edit |
| Entity types (V1) | 5 | LINE, LWPOLYLINE, TEXT, MTEXT, INSERT |
| Entity types (V2) | 9 | CIRCLE, ARC, DIMENSION, HATCH, SPLINE, POLYLINE, ELLIPSE, SOLID, LEADER |
| Edit operations | 4 | move_entity, edit_text, delete_entity, add_block |
| Comparison ops | 6 | MOVE, DELETE, ADD, MODIFY_GEOMETRY, MODIFY_TEXT, MODIFY_ATTRIBUTES |
| Web endpoints | 19 | Core edit + comparison + revision + metadata |
| CLI commands | 6 | diff, align, dry-run, apply, bundle, explain |
| Comparison modules | 15 | Geometry, matching, scoring, alignment, classification, approval, bundle |
| Tests | ~1351 | Unit ~1069, integration ~78, web ~123, benchmark ~15, GUI ~10, property ~7, smoke ~7, live varies |
| Settings | 31 | Environment variables (all CAD_* prefixed) |
| Coverage | 65% | Threshold in pyproject.toml |

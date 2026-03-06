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

### API Surface

#### Endpoint Groups

| Group | Endpoints | Purpose |
|-------|----------|---------|
| **Upload** | `POST /api/upload` | Upload DXF/PDF, start session, return file info + renders |
| **Prompt** | `POST /api/plan` | Send natural-language prompt, get planned operations + preview |
| **Apply** | `POST /api/apply` | Apply confirmed operations, produce edited DXF |
| **Status** | `GET /api/health` | Health check, readiness probe |
| **Results** | `GET /api/render`, `GET /api/dxf`, `GET /api/download` | Retrieve renders, raw DXF, or download edited file |
| **Compare** | `POST /api/compare` | Upload revision DXF, compare against master |
| **Revision** | `POST /api/revision/upload`, `/align`, `/diff`, `/approve`, `/apply`; `GET /api/revision/download` | Multi-step revision pipeline (upload → align → diff → approve → apply → download) |
| **v2 Unified** | `POST /api/v2/prompt` (proposed) | Single endpoint accepting any prompt, returns `PlatformResponse` envelope |

#### Response Envelope (v2)

All v2 responses use the `PlatformResponse` envelope (see 036-AT-SPEC):

```json
{
  "response_type": "<ResponseType enum>",
  "task_family": "<TaskFamily enum>",
  "message": "Human-readable summary",
  "data": { ... },
  "evidence": [ { "entity_handle": "...", "description": "..." } ],
  "operations": [ ... ],
  "validation": { "valid": true, "blockers": [], "warnings": [] },
  "confidence": 0.95,
  "processing_time_ms": 1234,
  "session_id": "abc123",
  "renders": { "original": true, "edited": true }
}
```

**Discriminators:** `response_type` (answer_only, plan_only, preview_edit, applied_edit, needs_clarification, unsupported_operation) and `task_family` (qna, edit_plan, compare, etc.) tell the frontend how to render the result.

#### Long-Running Operations

- **Current:** Poll-based. Client calls `POST /api/plan`, receives a synchronous response. Planner timeout (60s) bounds the wait.
- **Target:** Server-Sent Events (SSE) for streaming progress updates during long-running planner or compare operations. Client opens an SSE connection, receives incremental status events, then a final result event.
- **Transition:** SSE endpoints introduced as v2 alternatives; synchronous endpoints remain for backward compatibility.

#### API Versioning

- `/api/` — current endpoints, stable, no breaking changes
- `/api/v2/` — new endpoints using `PlatformResponse` envelope (proposed in 036)
- Migration: v2 endpoints introduced alongside v1; deprecation after all clients migrate

### Storage Architecture

#### File Lifecycle

```
Upload → /tmp/cad-sessions/{id}/upload.dxf
       → copy to working.dxf (mutable)
       → original.png (render)
       → Plan/Apply → edited.dxf + edited.png
       → Download → user retrieves edited.dxf
       → Expire → session + all files deleted after TTL
```

#### Retention Policy

- **Current TTL:** 2 hours (`SESSION_TTL_SECONDS = 7200` in `web/backend/session.py`)
- **Configurable:** Via environment variable (target)
- **Cleanup:** `SessionManager.cleanup_expired()` removes expired sessions and their temp directories

#### Migration Path: /tmp/ to GCS

| Phase | Storage | Metadata | Trigger |
|-------|---------|----------|---------|
| **Now** | `/tmp/cad-sessions/` (ephemeral, single instance) | In-memory `SessionManager` dict | Session create |
| **EPIC-11** | GCS bucket (`gs://cad-dxf-sessions/`) | Firestore document per session | Session create |
| **Post-11** | GCS with lifecycle rules (auto-delete after TTL) | Firestore with TTL field | Session create |

**Why migrate:** `/tmp/` is lost on Cloud Run cold start or instance rotation. GCS provides durable cross-instance storage. Firestore provides queryable session metadata surviving restarts.

#### Session Metadata (Target Schema)

```
Firestore: sessions/{session_id}
  user_id: string
  created_at: timestamp
  ttl_expires_at: timestamp
  original_gcs_path: string
  working_gcs_path: string
  state: "active" | "expired" | "completed"
  file_info: map
```

---

## 7. Error Handling & Resilience

### Failure Modes by Layer

| Layer | Failure Mode | Symptom | Response |
|-------|-------------|---------|----------|
| **Intent Router** | LLM classification unavailable | Slow-path times out or errors | Fall back to heuristic-only classification; if confidence too low, return `needs_clarification` |
| **Intent Router** | Ambiguous prompt | Multiple task families score equally | Return `needs_clarification` with candidates |
| **Planner** | LLM timeout | No response within budget | Raise `PlannerTimeoutError`; surface to user as "request timed out, try again" |
| **Planner** | Malformed LLM output | JSON parse failure or invalid ops | Retry with corrective prompt (validation-retry loop); exhaust retries → `PlannerRetryExhaustedError` |
| **Planner** | API quota / transient error | 429 or 5xx from Vertex AI | Exponential backoff retry (up to `max_retries`); exhaust → error response |
| **Validator** | Blockers found | Protected layer edit, missing entity | Block the changeset; return `unsupported_operation` with blocker details |
| **Validator** | Warnings found | Large move distance, unusual op count | Allow changeset but include warnings in response |
| **Response Formatter** | Missing required fields | Envelope construction fails | Internal error logged; return generic error response with `processing_time_ms` |
| **DXF Reader** | Corrupt or unsupported file | ezdxf parse exception | Return 400 with descriptive error; session not created |
| **DXF Writer** | Disk full / write error | Save-as fails | Return 500; original file untouched (save-as guarantees no corruption) |

### Timeout Budgets

| Stage | Budget | Source | Retryable? |
|-------|--------|--------|-----------|
| **Planner (LLM call)** | 60s wall-clock | `CAD_PLANNER_TIMEOUT` setting | No — timeout is terminal for that attempt |
| **Validation-retry loop** | 60s per re-call | Same timeout applies per LLM re-call | Yes — up to `planner_max_validation_retries` (default 2) |
| **Error-retry loop** | 60s per attempt + exponential backoff | `CAD_PLANNER_MAX_RETRIES` (default 2) | Yes — with `retry_delay * 2^(attempt-1)` backoff |
| **DXF load** | No explicit timeout | Bounded by file size (~2s for large drawings) | No |
| **Rendering** | No explicit timeout | Bounded by entity count (~5s typical) | No |
| **Intent Router (fast path)** | <10ms | Regex/keyword, no LLM | N/A |
| **Intent Router (slow path)** | Shares planner timeout | LLM classification call | Falls back to heuristic |

### Retry Policy

The planner implements a two-tier retry strategy (`llm/planner.py`):

1. **Error retry** — If the LLM call raises a non-timeout exception (network error, malformed response), the planner retries up to `planner_max_retries` (default 2) with exponential backoff starting at `planner_retry_delay` (default 1.0s).

2. **Validation retry** — If the LLM returns a syntactically valid changeset that fails validation (e.g., targets a protected layer), the validation blockers are formatted into a corrective prompt and the LLM is re-called up to `planner_max_validation_retries` (default 2) times. This loop runs inside a successful error-retry attempt.

**Non-retryable:** `PlannerTimeoutError` is always terminal — the planner does not retry after a timeout.

### Graceful Degradation

| Component | Degraded Mode | Trigger |
|-----------|--------------|---------|
| **Intent Router** | Heuristic-only (regex/keyword rules, no LLM slow path) | LLM unavailable, quota exhausted, or slow-path timeout |
| **Vision Pipeline** | Plan without image context | Render fails or `CAD_VISION_ENABLED=false` |
| **ODA Converter** | Reject DWG files (DXF-only mode) | ODA FileConverter not installed |
| **Revision Notes** | Skip note insertion | `CAD_REVISION_NOTES_ENABLED=false` |
| **OpenTelemetry** | No-op spans (zero overhead) | `OTEL_ENABLED` not set or OTel packages not installed |

### Error Response Envelope

All error responses follow the `PlatformResponse` envelope (see 036-AT-SPEC) with appropriate fields:

```json
{
  "response_type": "unsupported_operation",
  "task_family": "edit_plan",
  "message": "Planner timed out after 60s. Please try a simpler request.",
  "data": {
    "reason": "planner_timeout",
    "timeout_seconds": 60
  },
  "operations": [],
  "confidence": null,
  "processing_time_ms": 60012
}
```

**Error reasons:** `planner_timeout`, `planner_retry_exhausted`, `validation_blocked`, `protected_layer`, `unsupported_entity_type`, `unsupported_task`, `no_drawing_loaded`, `session_expired`, `file_parse_error`.

### Circuit Breaker Considerations

The LLM stage (planner, intent router slow path) is the only external dependency with meaningful failure rates. Circuit breaker logic is not yet implemented but should be considered for EPIC-11:

- **Threshold:** Open circuit after N consecutive LLM failures within a time window (e.g., 5 failures in 60s)
- **Fallback:** When circuit is open, immediately return `needs_clarification` or fall back to deterministic planner / heuristic router
- **Half-open:** Allow one probe request after cooldown period to test recovery
- **Scope:** Per-instance (in-process); no shared state needed since Cloud Run instances are independent

---

## 8. Multi-User & Session Model

### Session Lifecycle

```
Create (upload) → Active → [plan/apply/compare cycles] → Expire (TTL) → Delete
                     ↓
                  Download → (session remains active until TTL)
```

1. **Create:** `POST /api/upload` generates a session with a unique 16-character hex ID and a temp directory under `/tmp/cad-sessions/{id}/`.
2. **Active:** Session holds uploaded file, working copy, renders, changeset state, comparison state, conversation history, and revision pipeline state.
3. **Expire:** `SessionManager.get()` checks TTL on every access. If `time.time() - created_at > SESSION_TTL_SECONDS`, the session is deleted and a `KeyError` is raised.
4. **Delete:** Session dict entry removed, temp directory recursively deleted via `shutil.rmtree`.

### Storage Backend

| Aspect | Current | Target (EPIC-11) |
|--------|---------|-------------------|
| **File storage** | `/tmp/cad-sessions/` (ephemeral) | GCS bucket with lifecycle rules |
| **Session metadata** | In-memory Python dict (`SessionManager._sessions`) | Firestore with TTL field |
| **Persistence** | Lost on process restart / instance rotation | Durable across restarts |
| **Cross-instance** | No — each Cloud Run instance has its own sessions | Yes — GCS + Firestore shared |

### Concurrent Access Model

- **Single-writer per session:** Each session is owned by one authenticated user (`session.user_id`). `SessionManager.get()` validates ownership on every access.
- **Thread safety:** `SessionManager` uses a `threading.Lock` for dict operations. Session state mutations (e.g., setting `changeset`, `edited_path`) are not individually locked — safe under the single-writer constraint.
- **No cross-session coordination:** Sessions are fully independent. No shared state between sessions.

### Authentication Mapping

- **Web:** Firebase Auth (email/password + Google OAuth). Every authenticated request includes a Firebase ID token validated server-side. Session ownership is tied to `user["uid"]` from the decoded token.
- **Dev mode:** `CAD_WEB_DEV_MODE=1` skips Firebase auth and uses a hardcoded dev user ID. Sessions are still created and scoped to this dev user.
- **Read-only endpoints:** `/api/render`, `/api/dxf`, `/api/download` use `get_by_id()` without ownership check — the session UUID itself serves as an access credential (unguessable 16-char hex).

### Design Constraint

**Single-user sessions only.** Multi-user collaborative editing (multiple users modifying the same drawing simultaneously) is explicitly out of scope. Each session is a private workspace for one user. This simplifies concurrency, conflict resolution, and state management. Collaborative features would require operational transforms or CRDTs, which are not justified by current user workflows.

---

## 9. Observability Plan

### Span Coverage

Each pipeline layer emits a named span via the existing `otel.py` bootstrap module. Spans are hierarchical — child spans nest under the parent pipeline span.

#### Existing Spans

| Span Name | Module | Layer |
|-----------|--------|-------|
| `cad.load_dxf` | `core/dxf_reader.py` | DXF Reader |
| `cad.build_context` | `core/semantic_model.py` | Context Builder |
| `cad.run_planner` | `llm/planner.py` | Planner Orchestrator |
| `cad.gemini_plan` | `llm/gemini_provider.py` | Gemini Provider |
| `cad.agent_plan` | `llm/agent_provider.py` | Agent Provider |
| `cad.validate` | `core/validators.py` | Safety Layer |
| `cad.apply_changeset` | `core/edit_engine.py` | Edit Engine |
| `cad.save` | `core/edit_engine.py` | DXF Writer |
| `cad.render` | `core/renderer.py` | Renderer |
| `cad.revision_note` | `core/revision_notes.py` | Revision Notes |
| `cad.vision_describe` | `llm/vision_describer.py` | Vision Pipeline |
| `cad.convert` | `core/converter.py` | DWG Converter |
| `cad.compare.*` | `core/comparison/` | Compare Pipeline (align, match, classify, changelog, overlay) |

#### New Spans (Planned)

| Span Name | Module | Layer | Epic |
|-----------|--------|-------|------|
| `cad.router.classify` | `llm/intent_router.py` | Intent Router | EPIC-02 |
| `cad.router.heuristic` | `llm/intent_router.py` | Intent Router (fast path) | EPIC-02 |
| `cad.router.llm_classify` | `llm/intent_router.py` | Intent Router (slow path) | EPIC-02 |
| `cad.format_response` | `core/response_formatter.py` | Response Formatter | EPIC-02 |
| `cad.select_entities` | `core/entity_index.py` | Selection Engine | EPIC-03 |
| `cad.build_task_context` | `core/context_strategies.py` | Context Builder (task-aware) | EPIC-03 |

### Key SLIs

| SLI | Definition | Target | Alert Threshold |
|-----|-----------|--------|----------------|
| **Router latency p99** | 99th percentile wall-clock time for `cad.router.classify` | <50ms (heuristic), <5s (LLM) | >100ms (heuristic), >10s (LLM) |
| **Planner success rate** | `1 - (PlannerTimeoutError + PlannerRetryExhaustedError) / total_planner_calls` | >95% | <90% over 1h window |
| **Validation rejection rate** | Changesets with blockers / total changesets validated | <20% | >40% (indicates LLM quality degradation) |
| **Pipeline end-to-end p99** | Total time from prompt receipt to response delivery | <30s (edit), <5s (Q&A) | >60s |
| **Session expiry rate** | Sessions expired without any download / total sessions | Informational | N/A |

### Export Target

- **Production:** GCP Cloud Trace via `opentelemetry.exporter.cloud_trace.CloudTraceSpanExporter` (already configured in `otel.py` when `OTEL_EXPORTER=gcp-trace`)
- **Local dev:** Console exporter (default) or OTLP to local collector
- **CI:** Disabled (no `OTEL_ENABLED` set, all spans are no-ops via `_NoOpTracer`)

### Implementation Notes

- All tracing is optional — `otel.py` provides `_NoOpTracer` and `_NoOpSpan` when OTel is not installed or not enabled. Zero runtime overhead when disabled.
- Span attributes follow the `cad.*` namespace convention. No full file paths or drawing text content in attributes (privacy constraint).
- `init_otel()` is safe to call multiple times (idempotent). Called once at app startup in the web backend.
- Test support via `init_otel_testing(exporter)` with `SimpleSpanProcessor` for immediate span capture in assertions.

---

## 10. Migration Phasing

This section maps the 12 epics to architecture layers, showing what is built in each phase and what the system looks like at each intermediate state.

### Phase 1: Foundation (EPICs 01-03)

**Layers built:** Intent Router, Response Formatter, Selection Engine (enhanced)

| Epic | Layers Affected | What Changes |
|------|----------------|-------------|
| EPIC-01 | (none — docs only) | Capability audit, architecture baseline, evaluation plan documented |
| EPIC-02 | Intent Router (NEW), Response Formatter (NEW) | `TaskFamily` + `ResponseType` enums, `PlatformResponse` envelope, `intent_router.py` with heuristic classifier, `/api/v2/prompt` endpoint stub |
| EPIC-03 | Selection Engine (ENHANCED), Context Builder (ENHANCED) | Regex/fuzzy text search, bbox region selection, markup overlay ingestion, task-family-aware context shaping |

**System state after Phase 1:** Prompts are classified by task family. Responses use typed envelopes. Selection supports region and pattern queries. But only `edit_plan` and `compare` task families produce meaningful results — other families return `unsupported_operation` or basic answers.

### Phase 2: Core Intelligence (EPICs 04-06)

**Layers built:** Tool Layer (new tools), Context Builder (task-specific strategies)

| Epic | Layers Affected | What Changes |
|------|----------------|-------------|
| EPIC-04 | Context Builder, Tool Layer, Response Formatter | Region-focused context builder, `answer` and `summarize_drawing` tools, grounded Q&A pipeline producing `answer_only` responses with evidence |
| EPIC-05 | Selection Engine, Tool Layer | `find_pattern` tool, similarity scoring, repeated-condition search pipeline |
| EPIC-06 | Compare Pipeline, Response Formatter | Typed compare response schema, alignment diagnostics, compare results wrapped in `PlatformResponse` |

**System state after Phase 2:** Three task families are fully operational (`qna`, `repeated_condition`, `compare`). Edit pipeline still uses v1 response format. Architecture review gate (ARCH-REVIEW-01) evaluates the design before proceeding to structured editing.

### Architecture Review Gate (ARCH-REVIEW-01)

Mandatory review after Phase 2 completes. Evaluates:
- Whether the router/formatter/tool patterns are scaling well
- LLM/tool boundary quality (are tools doing too much? too little?)
- Performance under realistic drawing sizes
- Decision: keep, change, or remove architectural patterns before building edit planning

### Phase 3: Structured Editing (EPICs 07-08)

**Layers built:** Safety Layer (enhanced), Edit Engine (workflow integration)

| Epic | Layers Affected | What Changes |
|------|----------------|-------------|
| EPIC-07 | Safety Layer (ENHANCED), Tool Layer | Cross-operation conflict detection, impact estimation, task-family-appropriate validation (Q&A → zero edits enforced), structured edit plan schema |
| EPIC-08 | Response Formatter, Edit Engine | Preview pipeline integrated with `PlatformResponse`, apply pipeline with audit trail, `preview_edit` and `applied_edit` response types fully functional via v2 API |

**System state after Phase 3:** Full plan → preview → apply workflow through v2 API with typed responses. All read-only and edit task families operational. Safety layer enforces task-family constraints (Q&A cannot produce edits).

### Phase 4: Workflow Packs (EPICs 09-10)

**Layers built:** Tool Layer (domain-specific tools), Context Builder (domain strategies)

| Epic | Layers Affected | What Changes |
|------|----------------|-------------|
| EPIC-09 | Tool Layer, Context Builder | Design-ops tools (`measure_distance`, `count_entities`), layout recommendations, takeoff estimation, `summary` and `takeoff_estimate` families fully operational |
| EPIC-10 | Tool Layer, Selection Engine | Construction-drawing tools (`annotate`), grid/bay summaries, markup-to-redline interpretation, batch repeated-condition plans, `markup_interpretation` and `design_assist` families operational |

**System state after Phase 4:** All 9 task families operational (excluding `unsupported_operation` catch-all). Both user workflow classes (Design Operations, Construction Drawing) have dedicated tooling. Platform is feature-complete.

### Phase 5: Production Readiness (EPICs 11-12)

**Layers built:** Storage (durable), Observability (full), Eval Layer

| Epic | Layers Affected | What Changes |
|------|----------------|-------------|
| EPIC-11 | Storage (NEW — GCS + Firestore), Observability | Migrate sessions from `/tmp/` to GCS, session metadata in Firestore, circuit breaker for LLM stage, scale smoke tests, full span coverage for all new layers |
| EPIC-12 | Eval Layer (NEW) | Capability scorecard runner, domain fixture packs, confidence tracking, CI regression suite, live scorecard on push to main |

**System state after Phase 5:** Production-grade platform with durable storage, comprehensive tracing, and quality governance. All 9 task families tested via golden trajectories and scorecard. Regression rate <5% on live API.

### Layer Build Timeline

```
                  Phase 1    Phase 2    Review   Phase 3    Phase 4    Phase 5
                 (01-03)    (04-06)    (AR-01)  (07-08)    (09-10)    (11-12)
                 --------   --------   ------   --------   --------   --------
Intent Router    [BUILD ]   [stable ]           [stable ]  [stable ]  [stable ]
Selection Eng    [ENHANCE]  [ENHANCE]           [stable ]  [ENHANCE]  [stable ]
Context Builder  [ENHANCE]  [EXTEND ]           [stable ]  [EXTEND ]  [stable ]
Tool Layer       [       ]  [EXTEND ]           [EXTEND ]  [EXTEND ]  [stable ]
Safety Layer     [       ]  [       ]           [ENHANCE]  [stable ]  [stable ]
Response Fmt     [BUILD ]   [EXTEND ]           [EXTEND ]  [stable ]  [stable ]
Eval Layer       [       ]  [       ]           [       ]  [       ]  [BUILD  ]
Storage          [       ]  [       ]           [       ]  [       ]  [BUILD  ]
Observability    [spans  ]  [spans  ]           [spans  ]  [spans  ]  [HARDEN ]
```

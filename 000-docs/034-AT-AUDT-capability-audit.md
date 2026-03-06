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

## 5. User Workflow Capability Matrix

Capability score per user workflow class. Each task family scored for how well
the current system serves that specific user type. Target state defines "done"
for each capability per user type.

**Categorical labels:** 0–20% = unsupported, 21–50% = risky/unclear,
51–75% = partially supported, 76–100% = supported.

### Design Ops User

| # | Task Family | Current | Label | Target | Target Label |
|---|------------|---------|-------|--------|--------------|
| 1 | Edit (move/delete/text/block) | 75% | partially supported | 95% | supported — full multi-turn edit with undo, bulk ops, and V2 entity types |
| 2 | Q&A | 15% | unsupported | 85% | supported — intent-routed Q&A with evidence citations from entities |
| 3 | Compare | 80% | supported | 95% | supported — cross-operation conflict checks, visual diff preview |
| 4 | Markup Interpretation | 5% | unsupported | 80% | supported — redline/cloud detection from uploaded markup images |
| 5 | Repeated Condition Search | 10% | unsupported | 80% | supported — regex + spatial pattern search across layers |
| 6 | Summary | 25% | risky/unclear | 85% | supported — formatted statistics with layer/type breakdowns |
| 7 | Takeoff/Estimate | 0% | unsupported | 70% | partially supported — quantity extraction for common element types |
| 8 | Design Assist | 5% | unsupported | 60% | partially supported — code-compliance suggestions for known domains |
| 9 | Apply Edit | 85% | supported | 95% | supported — streaming apply with rollback on failure |

### Construction Drawing User

| # | Task Family | Current | Label | Target | Target Label |
|---|------------|---------|-------|--------|--------------|
| 1 | Edit (move/delete/text/block) | 70% | partially supported | 90% | supported — redline markup as edit input, approval workflow for edits |
| 2 | Q&A | 10% | unsupported | 85% | supported — construction-spec-aware answers with reference citations |
| 3 | Compare | 85% | supported | 95% | supported — automated revision numbering, transmittal-ready bundles |
| 4 | Markup Interpretation | 0% | unsupported | 90% | supported — primary workflow; cloud/delta/revision triangle detection |
| 5 | Repeated Condition Search | 15% | unsupported | 85% | supported — find all instances of detail/condition across sheets |
| 6 | Summary | 20% | unsupported | 85% | supported — drawing register integration, scope-of-work summaries |
| 7 | Takeoff/Estimate | 5% | unsupported | 75% | partially supported — BOQ extraction for structural/architectural elements |
| 8 | Design Assist | 0% | unsupported | 50% | risky/unclear — code-check suggestions (limited domain coverage) |
| 9 | Apply Edit | 75% | partially supported | 90% | supported — approval workflow for edits matching revision process |

### General Review User

| # | Task Family | Current | Label | Target | Target Label |
|---|------------|---------|-------|--------|--------------|
| 1 | Edit (move/delete/text/block) | 65% | partially supported | 85% | supported — guided edit wizard, confirmation prompts for destructive ops |
| 2 | Q&A | 40% | risky/unclear | 90% | supported — natural language answers without needing CAD expertise |
| 3 | Compare | 70% | partially supported | 90% | supported — simplified diff view with plain-language change summary |
| 4 | Markup Interpretation | 5% | unsupported | 60% | partially supported — basic redline detection for review comments |
| 5 | Repeated Condition Search | 20% | unsupported | 70% | partially supported — text search with fuzzy matching |
| 6 | Summary | 50% | risky/unclear | 90% | supported — dashboard-style overview accessible to non-engineers |
| 7 | Takeoff/Estimate | 0% | unsupported | 40% | risky/unclear — high-level counts only, no domain-specific quantities |
| 8 | Design Assist | 0% | unsupported | 30% | risky/unclear — generic suggestions, limited without domain expertise |
| 9 | Apply Edit | 70% | partially supported | 85% | supported — simplified apply with clear rollback option |

**Overall current scores:** Design Ops 33%, Construction Drawing 31%, General Review 36%.
**Overall target scores:** Design Ops 83%, Construction Drawing 83%, General Review 71%.

---

## 6. Frontend Architecture

**Framework:** React 18.3.1 + Vite, deployed to Firebase Hosting.

**Component structure:**

| Component | Purpose | Path |
|-----------|---------|------|
| `App` | Root router, auth check | `web/frontend/src/App.jsx` |
| `Workspace` | Main layout, orchestrates all panels | `web/frontend/src/components/Workspace.jsx` |
| `ChatPanel` | Conversational UI, message history, follow-ups | `web/frontend/src/components/ChatPanel.jsx` |
| `PreviewPanel` | Tabbed viewer (Original/Edited/Compare), revision wizard | `web/frontend/src/components/PreviewPanel.jsx` |
| `DxfViewerComponent` | WebGL renderer (dxf-viewer + Three.js) | `web/frontend/src/components/DxfViewerComponent.jsx` |
| `FileUpload` | Drag-drop file picker | `web/frontend/src/components/FileUpload.jsx` |

**State management:** React hooks only (`useSession` custom hook, 504 lines). No Redux.
All API calls via `fetch()` in `web/frontend/src/lib/api.js`.

**CSS:** Hand-written, 8px grid, CSS custom properties, dark mode via `prefers-color-scheme`.

---

## 7. Session and State Handling

**Session lifecycle:**
1. `POST /api/upload` → `session_mgr.create(user_id)` → 16-char UUID
2. Temp directory at `/tmp/cad-sessions/{id}/`
3. TTL: 2 hours (lazy expiration on next `.get()` call)
4. No background cleanup daemon

**In-memory state (lost on restart):**
- Session dict (all session objects)
- DrawingContext (parsed DXF model)
- Conversation history (capped at 10 entries)
- ChangeSet from last plan
- ComparisonResult, ApprovalSet

**On-disk state (lost on restart):**
- Original/working/edited DXF files
- PNG renders
- Revision files, comparison overlays
- Bundle directory (master + revision + overlay + changelog)

**Evidence:** `web/backend/session.py` lines 15-136

---

## 8. Storage and File Handling

**Temp file structure:**
```
/tmp/cad-sessions/{id}/
  original.dxf        # User upload (or converted from PDF/DWG)
  working.dxf         # Working copy for multi-step edits
  edited.dxf          # Result of /api/apply
  *.png               # PNG renders (original, edited)
  revision.dxf        # Uploaded revision for comparison
  comparison/          # Diff overlay DXF + render
  bundle/              # Export package (master + revision + overlay + changelog)
```

**Upload processing:** DXF passthrough, PDF via pymupdf, DWG via ODA FileConverter.
**Save strategy:** Always save-as (original never modified).
**Download formats:** DXF (raw copy) or DWG (via ezdxf odafc addon).

---

## 9. Current Inventory Summary

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

---

## 10. Scale Risks

Production deployment risks that emerge under load or multi-instance scenarios.

| # | Risk | Impact | Detail |
|---|------|--------|--------|
| 1 | **In-memory session store** | No horizontal scaling | `SessionManager` is a process-local dict. A second Cloud Run instance sees no sessions from the first. Sticky sessions or external state store required for >1 instance. |
| 2 | **Ephemeral `/tmp` on Cloud Run** | Data loss on restart | All DXF files, renders, and bundles live under `/tmp/cad-sessions/`. Cloud Run instances can be evicted at any time; ~2 GB tmpfs limit means large files or many concurrent sessions can exhaust storage. |
| 3 | **Synchronous matplotlib rendering** | Event loop blocking | `renderer.py` calls matplotlib synchronously. On the async FastAPI backend this blocks the event loop for the duration of the render (seconds for complex drawings), starving other requests. |
| 4 | **No rate limiting or request queuing** | Resource exhaustion | Any authenticated user can fire unlimited `/api/plan` or `/api/compare` requests. No middleware throttle, no per-user queue, no backpressure signal. |
| 5 | **Gemini API rate limits not handled** | Silent failures under load | Vertex AI enforces per-project QPM/TPM quotas. The planner retry loop catches generic exceptions but does not detect or back off from 429 rate-limit responses specifically. |
| 6 | **No background session cleanup daemon** | Disk leak | Session TTL (2 h) is enforced lazily on `.get()` only. If no one fetches an expired session, its `/tmp` directory remains until the container is evicted. No background sweep. |
| 7 | **All state lost on container restart** | Workflow interruption | In-memory sessions, DrawingContexts, conversation histories, and pending ChangeSets vanish when the container is replaced. Users lose work with no warning or recovery path. |
| 8 | **Cloud Run default concurrency (80) with CPU-bound sync ops** | Throughput collapse | Planner calls and matplotlib renders are CPU-bound and synchronous. At concurrency 80, a few long-running plans can saturate the single vCPU, causing timeouts for queued requests. |
| 9 | **No streaming for long-running LLM operations** | Poor perceived latency | `/api/plan` blocks until the full ChangeSet is returned (up to `planner_timeout` seconds). No SSE/WebSocket streaming means the frontend shows a spinner with no progress indication. |

---

## 11. LLM Touchpoint Catalog

All LLM and pseudo-LLM components that participate in the prompt-to-changeset flow.

| Component | Module | API | Auth Model | When Used | Known Failure Modes |
|-----------|--------|-----|-----------|-----------|---------------------|
| **deterministic_planner** | `llm/deterministic_planner.py` | None (regex) | N/A | Always — first-try bypass before any LLM call | Returns `None` for prompts that don't match rigid patterns; false positives on ambiguous phrasing |
| **MockProvider** | `llm/mock_provider.py` | None (keyword match) | N/A | CI tests, smoke tests, fallback when SDK missing | Returns empty ChangeSet for unrecognized keywords; no multi-turn support |
| **GeminiProvider** | `llm/gemini_provider.py` | Vertex AI `GenerativeModel` | ADC (Application Default Credentials) | Dev, prod (one-shot mode) | Safety filter blocks (`ValueError`), empty response, JSON parse failure, Vertex import missing |
| **AgentProvider** | `llm/agent_provider.py` | Vertex AI function calling | ADC | Prod (tool-use loop, up to 10 turns) | Infinite loop (capped at `MAX_AGENT_TURNS=10`), per-turn timeout, tool dispatch errors, vision describer failure |
| **MockAgentProvider** | `llm/agent_provider.py` | None (scripted tool calls) | N/A | CI tests for tool-use flow | Only handles simple move/delete/text; context reconstruction may fail on missing fields |
| **GeminiKeyProvider** | `llm/gemini_key_provider.py` | Public Gemini API (`google-generativeai` SDK) | API key (`CAD_GEMINI_API_KEY`) | Desktop users without GCP credentials | API key leak risk, no Vertex-specific features (grounding, tuning), rate limits differ from Vertex |
| **ProxyAgentProvider** | `llm/proxy_client.py` | Cloud Run proxy (HTTP) | License key header | Desktop app via proxy | Proxy downtime, license validation failure, network latency added, double-hop timeout risk |

**Orchestration:** `planner.py:run_planner()` drives the flow: deterministic check → provider
selection via `get_provider()` → `_call_with_timeout()` with `ThreadPoolExecutor` → optional
validation feedback loop (re-call LLM with blockers) → retry with exponential backoff on failure.
Raises `PlannerTimeoutError` on wall-clock timeout, `PlannerRetryExhaustedError` when all
retry attempts fail.

---

## 12. Backend Architecture

### FastAPI App Structure

The web backend (`web/backend/main.py`) is a single FastAPI application deployed as one
Cloud Run container. Key structural elements:

- **Lifespan handler** — initializes logging and OpenTelemetry on startup
- **CORS middleware** — allows Firebase Hosting origins (`cad-dxf-agent.web.app`,
  `cad-dxf-agent.firebaseapp.com`) plus `localhost:3000`/`localhost:5173` for dev;
  custom origin via `CAD_WEB_CORS_ORIGIN` env var
- **Request logging middleware** — logs method, path, status code, and duration for
  every request; warnings for 4xx/5xx
- **19 endpoints** — grouped by workflow: upload, plan, apply, compare, revision
  (upload/align/diff/approve/apply/download), render, download, health

### Auth Dependency Chain

All protected endpoints use FastAPI's `Depends(get_user)` which resolves to
`get_licensed_user()` in `web/backend/auth.py`:

1. **`verify_token(request)`** — extracts `Authorization: Bearer <token>`, calls
   `firebase_admin.auth.verify_id_token()`. Returns decoded token dict (`uid`, `email`).
   Bypassed when `CAD_WEB_DEV_MODE=1`.
2. **`check_license(user)`** — queries Firestore `licenses/{uid}` for `active: true`.
   Results cached 5 min (`_license_cache` dict). Anonymous users bypass license check.
   **Fails closed** — Firestore errors return 403, not 200.
3. **`get_licensed_user(request)`** — composes `verify_token` then `check_license`.

### Cloud Run Deployment Model

- **Single container** — one Docker image, no sidecar
- **Ephemeral filesystem** — `/tmp` is tmpfs (~2 GB), lost on instance replacement
- **Concurrency** — default 80 concurrent requests per instance
- **CPU** — 1 vCPU, 1 GiB memory (set in deploy command)
- **Timeout** — 300 s per request
- **Auto-scaling** — 0 to N instances (scale to zero enabled)
- **Service account** — `cad-dxf-web-run@cad-dxf-agent.iam.gserviceaccount.com`

### SessionManager Singleton

`session_mgr = SessionManager()` is instantiated at module level in `main.py`. It is a
plain Python object with no persistence backend:

- `create(user_id)` — generates 16-char UUID, creates `/tmp/cad-sessions/{id}/` directory
- `get(session_id)` — returns `Session` dataclass or `None` (lazy TTL expiration on access)
- All session state (DrawingContext, ChangeSet, conversation history, comparison result,
  approval set) lives in the `Session` dataclass's fields — all in-memory

---

## 13. Pipeline Step-by-Step Flows

### Edit Pipeline

```
1. Upload         POST /api/upload → save to /tmp/cad-sessions/{id}/original.dxf
                  (PDF/DWG auto-converted via converter.py)
2. Load           ezdxf.readfile() → DXF document object
3. Context build  dxf_reader.load_dxf() → DrawingContext (entities, layers, blocks)
                  semantic_model.build_planner_context() → JSON dict (capped at 500 entities)
4. Deterministic  deterministic_planner.deterministic_plan() — regex match for trivial ops
   check          Returns ChangeSet directly if matched, skipping LLM entirely
5. LLM plan       provider.plan(prompt, context_dict) → ChangeSet
                  AgentProvider: multi-turn tool-use loop (query → edit → query → ...)
                  GeminiProvider: one-shot JSON generation with optional PNG
6. Validate       validators.validate_changeset(changeset, context, rule_config)
                  Checks: entity existence, protected layers, numeric validity, move distance
7. Retry loop     If blockers found: format errors → re-call LLM with corrective prompt
                  Up to planner_max_validation_retries attempts
8. Preview        preview_model.generate_preview() → human-readable operation descriptions
                  Sent to frontend for user review before apply
9. Apply          edit_engine.apply_changeset() → modified DXF document
                  Each EditOperation applied to working copy via ezdxf
10. Revision      revision_notes.insert_notes() → AI_REV_NOTES layer entries
    notes         Deterministic text from operation metadata (never LLM-generated)
11. Save          dxf_writer.save_dxf() → /tmp/cad-sessions/{id}/edited.dxf
                  Original file untouched (save-as workflow)
```

### Compare Pipeline

```
1. Extract        geometry.extract_snapshots(master) → list[GeometrySnapshot]
   snapshots      geometry.extract_snapshots(revision) → list[GeometrySnapshot]
                  Each snapshot: entity type, vertices/points, layer, text, attributes
2. Titleblock     geometry.detect_titleblock_region(master_snaps) → BBox | None
   detect         Auto-excludes titleblock area from comparison to reduce noise
3. Canonical IDs  canonical.assign_stable_ids(snaps) → snaps with content-hash IDs
                  canonical.sort_snapshots(snaps) → deterministic ordering
                  Ensures comparison results are reproducible across runs
4. Align          alignment.align_drawings(master, revision, config) → AlignmentResult
                  Alignment ladder: identity → centroid → ICP → manual control points
                  alignment.apply_alignment(revision, result) → transformed snapshots
5. Match          matcher.match_entities(master, revision, config) → MatchResult
                  Pairs master↔revision entities by type + proximity + similarity
                  Produces: matched pairs, master-only (deleted), revision-only (added)
6. Classify       classifier.classify_changes(match_result, config) → ClassifiedResult
                  Each pair → change type: MOVE, MODIFY_GEOMETRY, MODIFY_TEXT,
                  MODIFY_ATTRIBUTES, or UNCHANGED
                  Unmatched master → DELETE, unmatched revision → ADD
7. Changelog      changelog.generate_changelog(result) → ChangeLog
                  JSON + plain-text summary of all classified changes
8. Overlay        diff_overlay.write_diff_overlay(master, result, output) → DXF
                  Color-coded layers: green=added, red=deleted, yellow=modified
```

---

## 14. Extended Failure Modes

Additions to the failure points listed in section 3.

| # | Failure Mode | Trigger | Impact | Mitigation |
|---|-------------|---------|--------|------------|
| 6 | **PlannerTimeoutError** | LLM call exceeds `planner_timeout` (default 120 s) | Request fails with 500; user must retry manually | `_call_with_timeout()` uses `ThreadPoolExecutor` with wall-clock limit; not retryable |
| 7 | **PlannerRetryExhaustedError** | All `planner_max_retries` attempts fail (API errors, malformed responses) | Request fails with 500; last error propagated | Exponential backoff between retries; configurable via `CAD_PLANNER_MAX_RETRIES` |
| 8 | **Vision pipeline silent fallback** | `describe_drawing()` fails (matplotlib import missing, render crash, Gemini Flash error) | Agent proceeds with entity JSON only — no visual context; may produce lower-quality plans | `vision_describer.py` is optional; `pipeline_worker.py` logs warning and continues without image |
| 9 | **Firebase auth failure** | Firebase Admin SDK init fails, token expired/revoked, network error to Google Identity | 401 returned; user cannot access any endpoint | `verify_token()` catches all exceptions and returns generic 401; no retry or token refresh on backend |
| 10 | **Firestore license fail-closed** | Firestore unreachable, permission denied, or timeout | 403 returned even for licensed users — service effectively down for paid users | `check_license()` explicitly fails closed (`raise HTTPException(403)`); cache mitigates for 5 min |
| 11 | **ODA converter missing** | DWG upload on system without ODA File Converter installed | DWG conversion fails; cloud API fallback not yet implemented | `_convert_dwg()` returns `ConversionResult(success=False)` with install instructions |
| 12 | **Concurrent session mutation** | Two requests modify the same session simultaneously (e.g., plan + apply race) | Undefined behavior — ChangeSet may be overwritten mid-apply, partial state corruption | No locking on `Session` dataclass; single-user assumption baked in |
| 13 | **Large file memory pressure** | DXF with 10k+ entities uploaded; multiple concurrent sessions | OOM on 1 GiB Cloud Run instance; `extract_snapshots()` holds all geometry in memory | 500-entity cap in semantic model limits planner context but full DXF still loaded |

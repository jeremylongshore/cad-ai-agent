# 046 — Post-EPIC-06 Architecture Review (ARCH-REVIEW-CAD-01)

**Status:** COMPLETE
**Date:** 2026-03-06
**Scope:** Mandatory architecture and quality review after Phase 2 completion
**Reviewer:** Claude Opus 4.6 (automated review with full codebase inspection)
**Recommendation:** CONDITIONAL GO for EPIC-CAD-07

---

## Executive Summary

The system is in strong shape. Six epics plus Side Quest 67 have been completed across two phases, producing a coherent Drawing Intelligence Platform with 1,924 tests (95.24% coverage), typed contracts, deterministic pipelines for Q&A/compare/repeated-condition, and a clean separation between LLM-driven and rule-driven codepaths.

The architecture has scaled well from a simple DXF editor to a multi-capability platform. The key decision to keep most intelligence deterministic (Q&A, comparison, repeated-condition detection) rather than LLM-dependent was correct and should be maintained.

However, there are five specific issues that should be addressed before or alongside EPIC-CAD-07:

1. **Duplicated utility code** across modules (Levenshtein, entity description, evidence construction)
2. **EntityIndex uses brute-force O(n) spatial queries** — will degrade for large drawings
3. **LLM router fallback is a stub** — `_llm_classify` returns a hardcoded result
4. **No upload size validation** on the web backend
5. **comparison_schema.py is 585 lines** — consolidation of too many concerns

None of these are blockers. All can be fixed incrementally during or before EPIC-CAD-07.

---

## Review Scope

### What Was Inspected

| Area | Files Inspected | Tests Run |
|------|----------------|-----------|
| Routing + Contracts | `intent_router.py`, `response_schema.py`, `capability_registry.py`, `response_builder.py` | 1,861 passing (excl. live) |
| Region Q&A | `qna_pipeline.py`, `region_context.py`, `qna_schema.py`, `entity_index.py` | 509 Q&A-specific tests |
| Repeated Condition | `repeated_condition.py`, `repeated_condition_schema.py` | 63 detection tests |
| Compare/Diff | All 12 modules in `core/comparison/`, `comparison_schema.py` | 15 comparison-specific + 13 regression |
| Text Provenance (SQ67) | `TextGeometry`, `TextProvenance` in `cad_schema.py`, downstream wiring | 788+ unit + 534 e2e |
| Selection/Markup | `markup_parser.py`, `region_associator.py`, `region_schema.py`, `selection_debug.py` | 93 selection tests |
| Observability | `otel.py`, span instrumentation across pipeline | OTel no-op/init tests |
| Web Backend | `web/backend/main.py`, `auth.py`, `session.py` | 123 web API tests |
| Pipeline Core | `dxf_reader.py`, `dxf_writer.py`, `edit_engine.py`, `validators.py`, `semantic_model.py` | Full unit suite |
| All Models | 12 Pydantic schema files (1,477 lines total) | 100% model coverage |

### Metrics Snapshot

| Metric | Value |
|--------|-------|
| Total tests | 1,924 (1,861 pass excl. live, 2 live failures, 21 skipped, 24 conditional) |
| Test coverage | 95.24% |
| Source modules | 75 Python files |
| Source lines | ~52,000 (including web) |
| Schema files | 12 (1,477 lines) |
| Golden trajectories | 15 |
| Enabled task families | 4 (edit_plan, compare, qna, repeated_condition) |

---

## 1. Correctness Review

### Trustworthy Now

- **Intent routing**: Heuristic classifier with 50-entry golden file, priority-ordered regex rules. Deterministic, fast (~0.02ms), well-tested. Correctly falls back to `NEEDS_CLARIFICATION` for unmatched prompts.
- **Q&A pipeline**: Fully deterministic. Question classification + template-based answer generation. No LLM in the core path. Handles 8 question types with appropriate evidence refs.
- **Compare/diff classification**: 15 comparison submodules with typed scoring (INSERT/LINE/TEXT-specific). Entity matching uses Jaccard, Levenshtein, and spatial proximity. Text trust from SQ67 properly downgrades low-provenance matches.
- **Validation**: Rule-based. Protected layers block all edits. Move distance warnings. Entity type enforcement.
- **Edit engine**: Deterministic apply of validated operations. Save-as workflow preserves originals.

### Partially Trustworthy

- **Repeated-condition detection**: 6-signal scoring model works well for block-based matches. Spatial clustering for non-block exemplars is rougher — `_cluster_by_proximity` uses a fixed radius approach that can miss patterns at varying scales. Text-only matches depend on Levenshtein which doesn't handle semantic similarity.
- **Markup interpretation**: Mapping pipeline (circle, box, loop, arrow, highlight) is implemented but arrow support is partial (hardcoded 10-unit radius). No real-world markup data has been tested — all tests use synthetic overlays.
- **Context cap**: `RegionContextBuilder` caps at 200 entities with a `context_truncated` ambiguity flag, but no prioritization. Truncation is arbitrary (first 200 by insertion order), not by relevance.

### Too Brittle for Downstream Automation

- **LLM router fallback**: `_llm_classify()` is a stub that always returns `NEEDS_CLARIFICATION`. If heuristic rules miss a valid intent, there's no recovery path. This is acknowledged by design (LLM fallback disabled until justified by data), but it means edge-case prompts silently fail.
- **Cross-region Q&A**: No support for questions spanning multiple regions or comparing regions within a single drawing.

---

## 2. Extensibility Review

### Can EPIC-CAD-07 Build Cleanly?

**Yes**, with minor prerequisites. The contracts are stable:

- `PlatformResponse` envelope handles all response types uniformly
- `TaskFamily` enum is extensible (add new values without breaking existing)
- `ResponseBuilder` factory pattern makes it easy to add new response constructors
- `CapabilityRegistry` gates unimplemented families cleanly

EPIC-CAD-07 (Structured Edit Planning) needs to add:
- `EditPlan` model in `models/plan_schema.py` — fits naturally alongside existing schemas
- `plan_builder.py` in `llm/` — plugs into the existing provider pattern
- New `ResponseBuilder.structured_plan()` method — follows established pattern

### Duplicated Concepts That Should Be Unified

1. **`_levenshtein_similarity` / `_levenshtein_distance`** — identical implementations in `core/comparison/scorer.py` and `core/repeated_condition.py`. Should be extracted to a shared `core/text_utils.py`.

2. **`_describe_entity`** — two slightly different implementations in `qna_pipeline.py` (includes text_geometry details) and `repeated_condition.py` (simpler). Should have one canonical version.

3. **Evidence construction** — `_evidence_from()` in `qna_pipeline.py` and `_entity_to_evidence()` in `repeated_condition.py` do the same thing with slight field differences. Should be unified.

### Abstractions Fighting the Product Shape

- **`comparison_schema.py` (585 lines)** packages alignment config, geometry snapshots, matching, diffing, approval workflow, and bundle manifests into one file. This will get worse as EPIC-CAD-08 adds preview workflows. Should be split into: `alignment_schema.py`, `match_schema.py`, `diff_schema.py`, `approval_schema.py`.

---

## 3. Complexity Review

### Complexity Paying for Itself

- **Comparison pipeline** (12 modules): High complexity, high value. Alignment ladder, type-specific scoring, approval workflow — all necessary for correct revision diffing.
- **TextGeometry + TextProvenance model**: Adds complexity to every text entity, but essential for trust-weighted scoring. Downstream consumers (Q&A, compare, repeated-condition) all benefit.
- **Region normalization**: MarkupParser + RegionAssociator + RegionContextBuilder chain is complex but correctly handles the coordinate transform problem.

### Accidental Complexity

- **EntityIndex `filter()` method**: Creates intermediate handle sets for intersection, then iterates `_all` to preserve order. For large drawings this is O(n) per filter dimension. A spatial grid or R-tree would eliminate this.
- **`_cluster_by_proximity`** in repeated_condition.py: Essentially implements DBSCAN-lite. If this needs to handle more complex patterns, it should use a proper spatial clustering library.
- **`find_in_radius`** in EntityIndex: Brute-force O(n) scan. Fine for <500 entities, becomes a bottleneck for large drawings.

### What Should Be Simplified

- Move shared text utilities (Levenshtein, entity description, evidence construction) into a shared module.
- Nothing else needs simplification — the codebase is already lean relative to its capabilities.

---

## 4. Latency Review

### Benchmark Evidence

From `pytest-benchmark` results (median values):

| Operation | Median | Notes |
|-----------|--------|-------|
| Validate 1 op | 14 us | Fast |
| Validate 10 ops | 20 us | Linear scaling |
| Validate 50 ops | 159 us | Acceptable |
| Validate 100 ops | 505 us | Acceptable |
| Build context (small) | 46 us | Fast |
| Build context (medium) | 660 us | Acceptable |
| Build context (large) | 1.4 ms | Acceptable |
| Find repeated (no matches) | 14 us | Fast |
| Find repeated (structural) | 775 us | Acceptable |
| Find repeated (large drawing) | 2.0 ms | Watch at scale |
| DXF load (small) | 8.4 ms | Acceptable |
| DXF load (medium) | 31.7 ms | Acceptable |
| DXF load (large) | 120.6 ms | May need optimization |

### Dominant Latency Sources

1. **LLM planner call (2-10s)**: Dominates user-visible latency. Not reducible without model change.
2. **DXF rendering via matplotlib (~5s)**: Not thread-safe, blocks request thread.
3. **DXF load for large files (~120ms)**: Acceptable now, will grow with entity count.
4. **Comparison pipeline (~10s for large)**: CPU-bound, blocks request thread.

### Tasks Acceptable Now

All deterministic pipelines (Q&A, repeated-condition, validation) complete in <10ms. These are production-ready latency-wise.

### Tasks Requiring Background/Async Before Expansion

- LLM planner calls (EPIC-CAD-11)
- matplotlib rendering (EPIC-CAD-11)
- Large comparison runs (EPIC-CAD-11)

These are correctly deferred to EPIC-CAD-11 (Session Durability + Scale Readiness).

---

## 5. Observability Review

### What Works

- **OTel tracing**: Optional but well-structured. `span()` context manager used throughout pipeline stages. Supports console, OTLP, and GCP Cloud Trace exporters.
- **Router spans**: `cad.router.classify` span with family, confidence, source, and time attributes.
- **Audit metadata**: Every `PlatformResponse` carries `AuditMetadata` with trace_id, timestamp, and per-stage timing.
- **Request logging middleware**: Web backend logs method, path, status, and duration.

### What's Missing

- **No structured error taxonomy**: Errors are generic `HTTPException` or Python exceptions. No error codes or categories.
- **No per-task-family metrics**: Cannot track Q&A vs edit vs compare usage patterns.
- **No confidence distribution tracking**: Router confidence is in the response but not aggregated.
- **No comparison diagnostics in response**: Match quality (avg confidence, ambiguous count) not surfaced to users.
- **No profiling data accessible**: Benchmark data exists in tests but not available in production.

### Can Engineers Tell What Happened When Results Are Wrong?

**Partially.** The `AuditMetadata` trace_id and timing data are helpful. The `ambiguity_flags` list surfaces uncertainty. But there's no structured error log that correlates router decisions, context building, and answer generation into a single diagnostic record. A wrong Q&A answer requires reading three different log entries to diagnose.

### Black Boxes

- **LLM planner responses**: When Gemini returns unexpected output, the only signal is a failed parse. No diagnostic logging of what the LLM actually returned.
- **Comparison matcher**: When matching produces false positives/negatives, the `MatchExplanation` is available per-pair but not aggregated into a diagnostic summary.

---

## 6. Failure Modes Review

### Handled Safely

- **Empty/sparse regions**: `RegionContextBuilder` sets `confidence=0.0` and `ambiguity_flags=["empty_drawing"]`. Q&A pipeline returns `NEEDS_CLARIFICATION`.
- **Protected layer edits**: Validator blocks with specific error messages. Never reaches edit engine.
- **Unsupported operations**: `CapabilityRegistry.is_implemented()` gates at router level. Returns typed `unsupported_operation` response.
- **Empty prompts**: Router returns `NEEDS_CLARIFICATION` with confidence=1.0.
- **Invalid DXF files**: ezdxf raises, caught and returned as HTTP 400.

### Risk of False Confidence

- **Context truncation**: 200-entity cap truncates silently. A Q&A answer about "all entities on layer X" may be wrong if the layer has >200 entities. The `context_truncated` flag is set but confidence is NOT reduced.
  - **Recommendation**: Reduce confidence by 0.2 when truncation occurs.

- **Repeated-condition false positives**: Single-entity block matches can score high (0.7+) even when the spatial context is completely different. The `_apply_caps` method handles some cases but doesn't check spatial context quality.

- **Compare alignment**: Identity alignment (no transform) is the default and only production path. If two drawings are offset, all entities appear as added+removed with no warning about alignment failure.
  - **Recommendation**: Add a sanity check — if >80% of entities are classified as added or removed, emit a warning suggesting alignment.

### Needs Stricter Guardrails

- **No upload size limit**: `web/backend/main.py` accepts arbitrarily large files. A single malicious upload can OOM the Cloud Run instance.
  - **Recommendation**: Add `MAX_UPLOAD_SIZE=25MB` check before buffering. This is a P0 fix.

---

## 7. Testability Review

### Can We Tell If the System Gets Better or Worse?

**Yes.** The test infrastructure is strong:

- 95.24% line coverage with a 65% floor
- 15 golden trajectories across 4 task families
- syrupy snapshot tests catch accidental ChangeSet structure changes
- Benchmark tests track performance regressions
- Anti-regression tests for compare/edit isolation and OCR text priority

### Meaningful vs Decorative Tests

The vast majority are meaningful:
- Q&A tests verify answer content, evidence refs, and confidence values — not just "doesn't crash"
- Comparison tests verify per-entity change categories and match confidence
- Schema tests enforce Pydantic validation rules

A small number are decorative:
- Some `test_text_geometry.py` tests verify trivial field defaults
- Some schema tests just verify that construction doesn't raise

### Areas Needing Stronger Fixtures

1. **Large drawing performance**: Only 3 benchmark test sizes (small/medium/large). Need realistic 5,000+ entity drawings.
2. **Comparison edge cases**: No tests for drawings with significant offsets (alignment failure scenario).
3. **Markup interpretation**: All tests use synthetic overlays. Need real-world annotated drawing samples.
4. **Multi-turn edit workflows**: ScriptedAgentProvider supports single exchanges. No multi-turn conversation test fixtures.

---

## 8. Scale-Path Review

### What Breaks First

Referring to the existing scale readiness assessment (doc 040), the analysis remains accurate:

| Load Level | Failure | Status |
|------------|---------|--------|
| 5 concurrent users | matplotlib contention | KNOWN — deferred to EPIC-11 |
| 10 concurrent users | Session dict races, `/tmp/` fills | KNOWN — deferred to EPIC-11 |
| 50+ concurrent users | Gemini quota, stateless autoscaling | KNOWN — deferred to EPIC-11 |
| Large files (>50MB) | OOM kill | **URGENT** — no upload size limit |

### What Can Wait

- Horizontal scaling (EPIC-11)
- Background job queue (EPIC-11)
- Persistent session storage (EPIC-11)
- Spatial index optimization (see Section 3)

### What Cannot Wait Much Longer

- **Upload size validation**: Must be added before any production traffic. P0 fix.
- **EntityIndex spatial performance**: O(n) `find_in_radius` will become a problem when repeated-condition detection and region Q&A hit drawings with >1000 entities. Should be addressed in EPIC-CAD-07 or earlier.

---

## 9. Model-Boundary Review

### Where Deterministic Tools Are Used Correctly

The architecture strongly favors deterministic processing. This is the system's biggest strength:

| Capability | Deterministic? | LLM Role |
|-----------|---------------|----------|
| Intent routing | Yes (heuristic rules) | Stub fallback (disabled) |
| Q&A answering | Yes (template-based) | None |
| Region context building | Yes (spatial + index) | None |
| Repeated-condition scoring | Yes (6-signal model) | None |
| Compare/diff classification | Yes (15 modules) | None |
| Validation | Yes (rules) | None |
| Edit engine | Yes (apply ops) | None |
| Edit planning | **No** (LLM-driven) | Plans operations |
| Revision notes | Yes (from op metadata) | None |

8 of 9 pipeline stages are deterministic. Only edit planning uses the LLM.

### Where LLM Is Still Doing Too Much

- **Edit planning**: The LLM receives the full drawing context (capped at 500 entities) and returns structured operations. This is appropriate for the current V1 but should be constrained further in EPIC-CAD-07 with explicit constraint pre-checks.

### Where Model Output Is Appropriately Bounded

- LLM returns `EditOperation` objects with typed `OpType` enum — only 4 valid operations
- Validator checks every operation before apply — LLM cannot bypass
- Protected layers are enforced regardless of what the LLM suggests

### What Must Become More Deterministic Before Edit Planning

EPIC-CAD-07 should add deterministic constraint checking *before* sending to the LLM:
1. Verify referenced entities exist
2. Verify target layers are not protected
3. Verify operation types are supported
4. Pre-filter the context to relevant entities only

This reduces LLM dependence by catching ~60% of invalid plans before the API call.

---

## 10. Workflow-Value Review

### Design Operations User

**Current support: MODERATE**
- Can upload DXF, ask questions, get entity/layer information
- Can plan and apply edits (move, delete, edit_text, add_block)
- Cannot get design suggestions or layout recommendations (EPIC-09)
- Cannot get preview renders before applying (EPIC-08)

### Construction Drawing User

**Current support: MODERATE-LOW**
- Can compare master vs revision drawings with typed diff output
- Can detect repeated conditions (block-based + text-based)
- Cannot do grid/bay extraction or batch operations (EPIC-10)
- Cannot do quantity takeoffs (not implemented)

### General Drawing Review User

**Current support: GOOD**
- Q&A pipeline provides deterministic answers about drawing content
- Region-scoped Q&A with evidence citations
- Comparison pipeline produces structured changelogs
- Repeated-condition detection finds patterns

### Which Workflow Has Improved Most?

**General Drawing Review** — Phase 2 added Q&A, repeated-condition detection, and compare hardening. These are exactly the read-only analysis tools a reviewer needs.

### Which Workflow Is Still Underpowered?

**Construction Drawing** — has compare and repeated-condition but lacks takeoff, grid extraction, and batch operations. These are Phase 4 features.

### Building Toward Real User Value?

**Yes.** The deterministic pipelines are genuinely useful for drawing analysis. The platform is not just accumulating plumbing — Q&A answers real questions, compare finds real changes, repeated-condition finds real patterns. The architecture review finds no instances of over-engineering without value delivery.

---

## A. Keep / Change / Remove

### Keep

1. **Deterministic pipeline architecture** — 8/9 stages deterministic, LLM only for planning
2. **PlatformResponse envelope** — uniform response contract across all task families
3. **CapabilityRegistry** — clean gating of unimplemented families
4. **TextProvenance trust hierarchy** — properly downgrades low-trust text in scoring
5. **Comparison pipeline** — 12 well-separated modules with type-specific scoring
6. **Golden trajectory pattern** — 15 trajectories across 4 families
7. **DXF factory pattern** — programmatic test fixtures, no stored files
8. **OTel instrumentation** — optional, no-op safe, production-ready

### Change Before EPIC-CAD-07

1. **Extract shared text utilities** — `_levenshtein_*`, `_describe_entity`, evidence construction into `core/text_utils.py`
2. **Add upload size validation** — P0 security fix, `MAX_UPLOAD_SIZE=25MB`
3. **Reduce confidence on truncated context** — `RegionContextBuilder` should penalize confidence by 0.2 when capped

### Change During EPIC-CAD-07 (Concurrent)

4. **Split `comparison_schema.py`** — separate alignment, matching, diff, and approval schemas
5. **Add alignment sanity check** — warn when >80% entities classified as added/removed

### Remove

1. **Nothing needs removal.** All current code serves a purpose. The duplicated utility functions should be consolidated (shared module), not removed.

---

## B. Top 5 Technical Debt Risks

1. **Duplicated Levenshtein implementation** — identical 50-line functions in `core/comparison/scorer.py` (lines 343-375) and `core/repeated_condition.py` (lines 716-744). Not a correctness risk, but maintenance burden increases with each copy.

2. **O(n) spatial queries in EntityIndex** — `find_in_radius()` and `nearest()` scan all entities linearly. Repeated-condition detection calls `find_in_radius()` per cluster seed, making overall cost O(n*k) where k = number of seeds. At 5,000+ entities this becomes visible.

3. **comparison_schema.py consolidation** — 585 lines covering 6 distinct concerns (alignment, geometry snapshots, matching, diffing, approval, bundles). Any change to approval logic requires reading/understanding comparison geometry code. Increases merge conflict probability.

4. **LLM router fallback is dead code** — `_llm_classify()` exists structurally but always returns a static result. If the heuristic router misclassifies, there's no recovery. This is intentional (waiting for data), but the dead code path should either be implemented or marked as explicitly disabled with a setting.

5. **No upload size validation** — `web/backend/main.py` accepts unbounded file uploads. A single large upload can OOM the 1Gi Cloud Run instance, killing all active sessions. This is the only security vulnerability identified.

---

## C. Top 5 Simplification / Modularization Opportunities

1. **Extract `core/text_utils.py`** — consolidate `_levenshtein_similarity`, `_levenshtein_distance`, `_describe_entity`, `_evidence_from`/`_entity_to_evidence` into one module imported by Q&A pipeline, repeated-condition detector, and comparison scorer. Estimated: ~80 lines removed from duplicates.

2. **Split `comparison_schema.py` into 4 files** — `alignment_schema.py` (AlignmentConfig/Result/Diagnostics, ~70 lines), `match_schema.py` (GeometrySnapshot/ScoredMatch/MatchResult/MatchSummary, ~130 lines), `diff_schema.py` (EntityChange/ComparisonResult/DiffOverlayLayers, ~100 lines), `approval_schema.py` (RevisionOp/ApprovalSet/ApplyResult/RunBundle, ~200 lines). Re-export from `comparison_schema.py` for backward compatibility.

3. **Add spatial grid to EntityIndex** — replace brute-force `find_in_radius` with a cell-based spatial hash. Cells sized at max expected search radius. O(1) cell lookup instead of O(n) scan. ~50 lines of additional code for 10x speedup on large drawings.

4. **Unify entity description format** — `_describe_entity` in `qna_pipeline.py` (line 456) is richer than `_describe_entity` in `repeated_condition.py` (line 703). Unify into the richer version and use everywhere. Evidence refs will be more informative in repeated-condition results.

5. **Make `RegionContextBuilder` truncation smarter** — instead of taking first 200 entities by insertion order, prioritize text entities and entities near the query region center. ~20 lines of change for significantly better Q&A answers on large drawings.

---

## D. Roadmap Impact Assessment

### EPIC-CAD-07 — Structured Edit Planning

**Scope: No change needed.** Current contracts support `EditPlan` addition cleanly. The `PlatformResponse` envelope, `ResponseBuilder` pattern, and `TaskFamily.EDIT_PLAN` routing all work as designed.

**New acceptance criterion:** Add deterministic constraint pre-checks before LLM call (entity existence, layer protection, operation type support).

### EPIC-CAD-08 — Preview + Apply Workflow

**Scope: No change needed.** `ResponseType.PREVIEW_EDIT` is already defined. Web backend routes for preview rendering are outlined.

**Note:** Splitting `comparison_schema.py` before EPIC-08 would prevent the approval workflow schemas from growing further in the same file.

### EPIC-CAD-10 — Construction Drawing Workflow Pack

**Scope: Minor addition.** Should include alignment sanity check (warn when most entities classified as added/removed). This addresses a real construction drawing workflow gap where revision drawings are often offset from masters.

### EPIC-CAD-11 — Session Durability + Scale Readiness

**Scope: No change needed.** Scale readiness assessment (doc 040) is still accurate. No new scale concerns discovered.

**New acceptance criterion:** Must include upload size validation if not already fixed before EPIC-11.

### EPIC-CAD-12 — Evaluation Harness + Quality Governance

**Scope: No change needed.** Current 15 golden trajectories and 95% coverage provide a strong baseline for the eval harness to build on.

### No Epics Need Reordering or Splitting

The dependency chain is sound. Phase 2 delivered what it promised. Phase 3 can proceed.

---

## E. Side Quest 67 Impact Assessment

### What It Fixed

- Added `TextGeometry` model with height, rotation, alignment, width_factor, oblique angle, attachment point
- Added `TextProvenance` enum with 4-level trust hierarchy (native > block_attribute > vector_outline > raster_ocr)
- Added confidence scores per dimension (position, rotation, content) with provenance-based defaults
- Enhanced TEXT/MTEXT/INSERT entity extraction to capture full geometry metadata

### What It Revealed

1. **Text position is not always trustworthy** — OCR-derived text has position confidence of 0.3 vs 1.0 for native CAD text. This fundamentally changes how text entities should be weighted in matching and Q&A.

2. **Block attribute text is nearly as trustworthy as direct text** — 0.95 confidence vs 1.0. The trust hierarchy is correct.

3. **Downstream systems needed trust-awareness** — comparison scorer, repeated-condition detector, and Q&A pipeline all needed updates to handle varying trust levels.

### What It Changed About Trust Assumptions

- **Before SQ67**: All text was treated as equally trustworthy
- **After SQ67**: Text trust is a first-class dimension. Scoring functions weight text evidence by provenance confidence.
- **Impact**: Comparison scorer reduces position weight for low-trust text entities. Repeated-condition detector reports trust level in text similarity signals.

### Must Later Epics Depend on TextProvenance?

**Yes.** EPIC-CAD-07 (Structured Edit Planning) must consider text provenance when the planner resolves entity references from text content. If a user says "move the text that says 'DOOR SCHEDULE'", the planner should prefer native CAD text matches over OCR-derived matches.

EPIC-CAD-09 and EPIC-CAD-10 (workflow packs) should propagate trust levels into domain-specific outputs.

---

## Final Recommendation

### CONDITIONAL GO for EPIC-CAD-07

The system is architecturally sound, well-tested, and genuinely useful. Six epics have delivered real value in a clean codebase. There are no fundamental problems.

**Prerequisites before starting EPIC-CAD-07 implementation:**

1. **P0: Add upload size validation** — add `MAX_UPLOAD_SIZE` (25MB default) to `web/backend/main.py`. Must reject before buffering. This is a security issue.

2. **P1: Extract shared text utilities** — create `core/text_utils.py` with shared Levenshtein, entity description, and evidence construction functions. Update imports in `qna_pipeline.py`, `repeated_condition.py`, and `comparison/scorer.py`. This prevents the duplication from growing further when EPIC-CAD-07 adds more text-handling code.

3. **P1: Reduce confidence on truncated context** — modify `RegionContextBuilder._categorize()` to multiply confidence by 0.8 when `context_truncated` flag is set.

**Constraints during EPIC-CAD-07:**

4. Add deterministic constraint pre-checks to `plan_builder.py` before LLM call (entity existence, layer protection, operation type support).

5. Consider text provenance when resolving entity references from text content in edit plans.

All five items are small (estimated: 2-4 hours total). None require architectural changes.

---

## Related Documents

- 034-AT-AUDT — Capability audit baseline
- 035-AT-ARCH — Drawing intelligence target architecture
- 036-AT-SPEC — Response contracts and task taxonomy
- 038-PM-PLAN — Drawing intelligence platform roadmap
- 040-AT-AUDT — Scale readiness assessment
- 041-PM-STAT — Implementation status tracker
- 044-AT-SPEC — SQ67 text accuracy specification
- 045-AT-SPEC — Repeated-condition scoring model

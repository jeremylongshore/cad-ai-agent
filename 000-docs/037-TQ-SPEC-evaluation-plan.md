# 037 — Evaluation Plan

**Status:** Proposed
**Date:** 2026-03-05
**Depends on:** 034-AT-AUDT (capability audit), 036-AT-SPEC (response contracts)

---

## 1. Evaluation Tiers

Five-tier evaluation strategy, from fastest/cheapest to slowest/most-comprehensive.

| Tier | Name | Speed | Cost | Runs On | Purpose |
|------|------|-------|------|---------|---------|
| 1 | Unit tests | <30s | Free | Every commit | Schema validation, response contract invariants |
| 2 | Golden trajectory | <60s | Free | Every PR | Known-good prompt→response pairs (mock provider) |
| 3 | Capability scorecard | <120s | Free | Every PR | Task-family coverage matrix (mock provider) |
| 4 | Live LLM regression | ~5min | API cost | Push to main | Same scorecard against real Gemini |
| 5 | End-to-end workflow | ~10min | API cost | Release gate | Full user workflow simulation |

---

## 2. Tier 1: Unit Tests (Contract Validation)

Tests that enforce response contract invariants from 036-AT-SPEC.

### New Test File: `tests/unit/test_response_contracts.py`

| Test | Validates |
|------|----------|
| `test_answer_only_has_no_operations` | `answer_only` responses have `len(operations) == 0` |
| `test_plan_only_has_operations` | `plan_only` responses have `len(operations) > 0` |
| `test_applied_edit_has_valid_validation` | `applied_edit` has `validation.valid == True` |
| `test_needs_clarification_has_message` | `needs_clarification` has non-empty `message` |
| `test_evidence_refs_on_qna` | `qna` responses have at least one `EvidenceRef` |
| `test_task_family_response_type_mapping` | Each task family produces only allowed response types |
| `test_platform_response_serialization` | `PlatformResponse` round-trips through JSON |

### Existing Tests (No Changes)

Current test suite (~1351 tests) continues to validate existing functionality.
No modifications needed — new tests are additive.

---

## 3. Tier 2: Golden Trajectories

Extend the existing 5 golden trajectories to 25+ covering all 9 task families.

### Current Trajectories (`tests/fixtures/trajectories/`)

| File | Task Family | Status |
|------|-----------|--------|
| `move.json` | edit_plan | EXISTS |
| `delete.json` | edit_plan | EXISTS |
| `edit_text.json` | edit_plan | EXISTS |
| `add_block.json` | edit_plan | EXISTS |
| `protected_layer_reject.json` | edit_plan (blocked) | EXISTS |

### Proposed New Trajectories

| File | Task Family | Prompt Example | Expected ResponseType |
|------|-----------|---------------|----------------------|
| `qna_layer_query.json` | qna | "What layer is entity X on?" | answer_only |
| `qna_entity_count.json` | qna | "How many doors are there?" | answer_only |
| `qna_drawing_scale.json` | qna | "What scale is this drawing?" | answer_only |
| `qna_find_entity.json` | qna | "Where is the north stairwell?" | answer_only |
| `compare_basic.json` | compare | "What changed between these?" | answer_only (changelog) |
| `compare_with_approval.json` | compare | "Compare and apply rev B" | plan_only → applied_edit |
| `summary_basic.json` | summary | "Summarize this floor plan" | answer_only |
| `summary_layer_breakdown.json` | summary | "Break down entities by layer" | answer_only |
| `repeated_text_search.json` | repeated_condition | "Find all concrete callouts" | answer_only |
| `repeated_block_search.json` | repeated_condition | "Find all door symbols" | answer_only |
| `markup_cloud_detect.json` | markup_interpretation | "Are there revision clouds?" | answer_only |
| `takeoff_block_count.json` | takeoff_estimate | "Count all electrical outlets" | answer_only |
| `design_assist_suggest.json` | design_assist | "Suggest improvements" | answer_only / plan_only |
| `ambiguous_prompt.json` | (routed) | "doors" | needs_clarification |
| `unsupported_prompt.json` | (rejected) | "Print this drawing" | unsupported_operation |
| `multi_op_edit.json` | edit_plan | "Move walls and delete doors" | plan_only |
| `edit_then_apply.json` | edit_plan → apply_edit | "Move wall" → "yes apply" | plan_only → applied_edit |
| `empty_drawing.json` | qna | "What's in this drawing?" | answer_only |
| `large_drawing.json` | edit_plan | "Move entity X" (500+ entities) | plan_only |
| `cross_layer_edit.json` | edit_plan | "Move all WALLS entities right" | plan_only |

### Trajectory File Format

Same format as existing trajectories. Each file contains:

```json
{
  "name": "qna_layer_query",
  "task_family": "qna",
  "prompt": "What layer is entity 1A3 on?",
  "drawing_fixture": "structural_200",
  "expected_response_type": "answer_only",
  "expected_operations": [],
  "expected_evidence_count_min": 1,
  "tool_sequence": [
    {"tool": "get_entity", "args": {"handle": "1A3"}},
    {"tool": "answer", "args": {"text": "Entity 1A3 is on layer WALLS."}}
  ]
}
```

### Test Runner: `tests/eval/test_golden_trajectories.py`

Uses `ScriptedAgentProvider` to replay tool sequences and validates:
1. Correct `response_type` produced
2. Correct `task_family` assigned
3. Operation count matches expected
4. Evidence references present where required
5. No validation blockers on applied edits

---

## 4. Tier 3: Capability Scorecard

A structured matrix testing every task family x prompt type combination.

### Scorecard Schema

```python
class ScorecardEntry(BaseModel):
    task_family: TaskFamily
    prompt_id: str                  # Unique prompt identifier
    prompt: str                     # Natural language prompt
    drawing_fixture: str            # DXF factory method name
    expected_response_type: ResponseType
    expected_op_count: int | None   # None = don't check
    expected_evidence: bool         # Should evidence refs be present?
    pass_criteria: list[str]        # Human-readable pass conditions

class ScorecardResult(BaseModel):
    entry: ScorecardEntry
    actual_response_type: ResponseType | None
    actual_op_count: int
    actual_evidence_count: int
    passed: bool
    failure_reason: str | None
    latency_ms: int
```

### Scorecard Matrix (Target: 45+ entries)

| TaskFamily | Prompt Types | Count |
|-----------|-------------|-------|
| qna | layer query, entity find, count, scale, metadata | 5 |
| edit_plan | move, delete, edit_text, add_block, multi-op | 5 |
| apply_edit | confirm previous plan | 2 |
| compare | basic diff, layered diff, with approval | 3 |
| summary | full summary, layer breakdown, type breakdown | 3 |
| repeated_condition | text pattern, block pattern, spatial pattern | 3 |
| markup_interpretation | cloud detection, arrow detection | 2 |
| takeoff_estimate | block count, linear measure | 2 |
| design_assist | suggest move, suggest cleanup | 2 |
| **cross-cutting** | ambiguous, unsupported, empty drawing, large drawing, protected layer | 5 |
| | | **32+** |

### CI Integration

```makefile
# In Makefile
scorecard:        ## Run capability scorecard (mock provider)
	pytest tests/eval/test_scorecard.py -v --tb=short

scorecard-live:   ## Run capability scorecard (live Gemini)
	CAD_LLM_PROVIDER=gemini pytest tests/eval/test_scorecard.py -v --tb=short -m live_api
```

- `make scorecard` runs on every PR (mock provider, free, <120s)
- `make scorecard-live` runs on push to main (Gemini, costs API calls)
- Results output as JSON for trend tracking

---

## 5. Tier 4: Live LLM Regression

Same scorecard entries but executed against real Gemini provider.

### Differences from Tier 3

| Dimension | Tier 3 (Mock) | Tier 4 (Live) |
|-----------|--------------|--------------|
| Provider | MockProvider / ScriptedAgentProvider | GeminiProvider / AgentProvider |
| Latency | <100ms per entry | 2-10s per entry |
| Determinism | 100% reproducible | LLM variance expected |
| Cost | Free | ~$0.01-0.05 per entry |
| Pass criteria | Exact match | Relaxed (correct type, reasonable ops) |

### Relaxed Pass Criteria for Live

- Response type must match expected
- Operation count within +/-1 of expected (LLM may split/merge ops)
- Evidence references present (content not exact-matched)
- No validation blockers on responses that should succeed
- Latency < 30s per entry

### CI Trigger

```yaml
# In .github/workflows/ci.yml
- name: Live scorecard
  if: github.ref == 'refs/heads/main'
  run: make scorecard-live
```

---

## 6. Tier 5: End-to-End Workflow

Full user workflow simulation testing multi-step interactions.

### Workflow Scenarios

| Scenario | Steps | Task Families Involved |
|----------|-------|----------------------|
| "Edit and verify" | Upload → plan → preview → apply → download | edit_plan, apply_edit |
| "Compare and approve" | Upload master → upload revision → diff → approve → apply | compare, apply_edit |
| "Question then edit" | Upload → ask question → get answer → edit based on answer | qna, edit_plan |
| "Iterative refinement" | Upload → plan → reject → re-prompt → plan → apply | edit_plan, apply_edit |

### Implementation

- Use FastAPI TestClient for web workflows
- Use pipeline functions directly for CLI workflows
- Each scenario is a single test function with multiple assertions
- Located in `tests/eval/test_workflows.py`

---

## 7. Fixture Inventory

### Existing DXF Factories (`tests/helpers/dxf_factory.py`)

| Factory | Entities | Layers | Use Case |
|---------|----------|--------|----------|
| `create_structural_drawing()` | ~200 | 8+ | General pipeline testing |
| `create_minimal_drawing()` | ~5 | 2 | Fast unit tests |
| `create_empty_drawing()` | 0 | 0 | Edge case testing |

### Proposed New Factories

| Factory | Entities | Layers | Use Case |
|---------|----------|--------|----------|
| `create_qna_drawing()` | ~50 | 5 | Q&A prompts (metadata-heavy) |
| `create_large_drawing()` | 500+ | 10+ | Scale/performance testing |
| `create_markup_drawing()` | ~30 | 4 | Markup interpretation (clouds, arrows) |
| `create_multi_block_drawing()` | ~100 | 6 | Takeoff/counting (many INSERT refs) |
| `create_revision_pair()` | 2x ~100 | 6 | Compare workflows (master + modified) |

### Prompt Sets

Prompt sets are YAML files listing natural-language prompts per task family.

**Location:** `tests/fixtures/prompts/`

```yaml
# tests/fixtures/prompts/qna.yaml
prompts:
  - id: qna_001
    text: "What layer is entity {handle} on?"
    variables: { handle: "1A3" }
    expected_response_type: answer_only

  - id: qna_002
    text: "How many {entity_type} entities are on layer {layer}?"
    variables: { entity_type: "TEXT", layer: "NOTES" }
    expected_response_type: answer_only
```

---

## 8. Success Metrics

| Metric | Current | Target (EPIC-01 complete) | Target (all epics) |
|--------|---------|--------------------------|-------------------|
| Golden trajectories | 5 | 5 (no code changes this epic) | 25+ |
| Scorecard entries | 0 | 0 (design only this epic) | 32+ |
| Task families tested | 1 (edit_plan) | 1 | 9 |
| Test count | ~1351 | ~1351 (no new tests this epic) | ~1500+ |
| Coverage | 65% | 65% | 70%+ |

Note: This epic is docs-only. Test counts increase in subsequent epics as
schemas and pipelines are implemented.

---

## 9. Evaluation by Workflow Class

Each user persona maps to a set of critical task families. Minimum pass rates
are defined per workflow class to ensure the platform meets the needs of its
primary audiences.

### Design Operations User

Persona focused on editing, planning, and design assistance workflows.

| Task Family | Description | Minimum Pass Rate |
|-------------|-------------|-------------------|
| edit_plan | Move, delete, edit text, add block planning | >= 90% |
| apply_edit | Confirm and apply a previously planned changeset | >= 90% |
| design_assist | Suggest improvements, layout optimizations | >= 90% |

**Aggregate requirement:** All three task families must individually meet >= 90%
pass rate before the Design Operations workflow class is considered ready.

### Construction Drawing User

Persona focused on revision comparison, markup reading, and quantity takeoff.

| Task Family | Description | Minimum Pass Rate |
|-------------|-------------|-------------------|
| compare | Diff two drawing revisions, identify changes | >= 85% |
| markup_interpretation | Detect revision clouds, arrows, markup annotations | >= 85% |
| takeoff_estimate | Count blocks, measure linear elements | >= 85% |

**Aggregate requirement:** All three task families must individually meet >= 85%
pass rate before the Construction Drawing workflow class is considered ready.

### General Drawing Review User

Persona focused on querying, summarizing, and searching drawing content.

| Task Family | Description | Minimum Pass Rate |
|-------------|-------------|-------------------|
| qna | Layer queries, entity lookups, metadata questions | >= 80% |
| summary | Drawing summaries, layer/type breakdowns | >= 80% |
| repeated_condition_search | Find repeated text patterns, block patterns | >= 80% |

**Aggregate requirement:** All three task families must individually meet >= 80%
pass rate before the General Drawing Review workflow class is considered ready.

---

## 10. Quality Gates (Go/No-Go)

Concrete aggregate thresholds that must be met before merging or releasing.
Failures at any tier block progression until resolved.

### Per-Tier Gate Criteria

| Tier | Gate | Threshold | On Failure |
|------|------|-----------|------------|
| 2 — Golden Trajectory | All trajectories pass | 100% pass rate (deterministic with mock) | Block merge; fix immediately |
| 3 — Mock Scorecard | All scorecard entries pass | 100% pass rate (deterministic with mock) | Block merge; file issue if systemic |
| 4 — Live Scorecard | Aggregate pass rate | >= 85% overall, no task family below 70% | Block release; investigate regressions |
| 5 — End-to-End Workflow | All workflow scenarios | Complete without blockers | Block release; file issue per failing scenario |

### Failure Response Protocol

1. **Tier 2/3 failure (deterministic):** These use mock providers and must be
   100% reproducible. A failure indicates a code regression, not LLM variance.
   Block the PR merge. The author must fix before re-requesting review.

2. **Tier 4 failure (live LLM):** LLM variance is expected, but sustained
   failures indicate prompt or schema regressions. If aggregate drops below 85%
   or any task family drops below 70%:
   - Block the release.
   - Re-run the scorecard 3 times to rule out transient variance.
   - If failure persists, file an investigation issue with the failing entries
     and tag the responsible epic owner.

3. **Tier 5 failure (workflow):** A workflow blocker means a user-facing flow is
   broken end-to-end. Block the release. File an issue per failing scenario
   with severity `critical`.

### Per-Phase Exit Criteria

| Phase | Exit Gate | "Good Enough to Continue" Criteria |
|-------|-----------|-----------------------------------|
| Phase 1 | Contracts + routing foundation | Tier 2: 100%. Tier 3: 100% for `edit_plan` and `qna` families only. No live scorecard required yet. |
| Phase 2 | Selection + region Q&A + compare | Tier 2: 100%. Tier 3: 100% for all implemented families. Tier 4: >= 80% aggregate (relaxed from 85% — early LLM integration). |
| Phase 3 | Structured edit + preview/apply | Tier 2: 100%. Tier 3: 100%. Tier 4: >= 85% aggregate, no family below 70%. Design Operations class meets >= 90%. |
| Phase 4 | Workflow packs (design + construction) | All tiers at full thresholds. All three workflow classes meet their per-class minimums. Tier 5: all scenarios pass. |
| Phase 5 | Session durability + eval governance | All tiers at full thresholds. Regression detection operational. Scorecard trend data covers >= 30 days. |

---

## 11. Scoring Dimensions

Binary pass/fail is insufficient for tracking quality trends. Each scorecard
entry is evaluated across multiple dimensions on a 0–1 numeric scale.

### Dimension Definitions

| Dimension | Weight | Scale | Description |
|-----------|--------|-------|-------------|
| Intent classification accuracy | 0.20 | 0–1 | Did the router assign the correct `TaskFamily`? 1.0 = exact match, 0.0 = wrong family. |
| Entity targeting precision | 0.20 | 0–1 | Did operations target the correct entities? 1.0 = all targets correct, 0.0 = all wrong. For non-edit responses, score is 1.0 (not applicable). |
| Operation correctness | 0.20 | 0–1 | Are the operations valid and semantically correct? 1.0 = all ops correct, 0.0 = all ops wrong. For answer-only responses, score is 1.0. |
| Response quality | 0.15 | 0–1 | For Q&A: factual correctness of the answer. For edits: completeness of the changeset. 1.0 = fully correct/complete, 0.0 = entirely wrong/missing. |
| Safety | 0.15 | 0–1 | No operations on protected layers, no destructive unintended side effects. 1.0 = fully safe, 0.0 = violated a protected layer or caused unintended changes. Any safety score below 1.0 forces the entry to fail regardless of composite. |
| Latency | 0.10 | 0–1 | Response time relative to budget. 1.0 = under 2s, linear decay to 0.0 at 30s. Mock-provider entries always score 1.0. |

### Composite Score

```
composite = sum(dimension_score * weight for each dimension)
```

- **Pass threshold:** composite >= 0.70
- **Safety override:** if `safety < 1.0`, the entry fails regardless of composite
- **Per-entry output:** all six dimension scores plus the composite are recorded

### Scorecard Result Schema (Extended)

```python
class ScorecardResult(BaseModel):
    entry: ScorecardEntry
    actual_response_type: ResponseType | None
    actual_op_count: int
    actual_evidence_count: int
    passed: bool
    failure_reason: str | None
    latency_ms: int
    # Scoring dimensions (0.0–1.0)
    score_intent: float
    score_targeting: float
    score_operations: float
    score_quality: float
    score_safety: float
    score_latency: float
    score_composite: float
```

---

## 12. Regression Detection

### Result Persistence

Scorecard results are persisted as JSON files in `tests/eval/results/` with
timestamped filenames:

```
tests/eval/results/
  scorecard-2026-03-05T14:30:00-mock.json
  scorecard-2026-03-05T14:35:00-live.json
```

Each file contains the full list of `ScorecardResult` entries plus run metadata
(provider, git SHA, timestamp, aggregate scores). These files are committed to
the repository to maintain a historical record.

### Baseline Establishment

- The first full scorecard run after a phase exit becomes the **baseline** for
  that phase.
- Baselines are recorded in `tests/eval/baselines/` as a JSON file per phase:
  `baseline-phase-1.json`, `baseline-phase-2.json`, etc.
- Each baseline contains per-task-family aggregate scores and per-dimension
  averages.

### Regression Definition

A **regression** is detected when any of the following conditions are met
relative to the most recent baseline:

| Condition | Threshold | Severity |
|-----------|-----------|----------|
| Task family aggregate drop | > 5 percentage points from baseline | `warning` if 5–10 points, `critical` if > 10 points |
| Individual dimension drop (any family) | > 10 percentage points from baseline | `warning` |
| Safety score drop (any entry) | Any decrease below 1.0 | `critical` (always) |
| Overall composite drop | > 5 percentage points from baseline | `warning` |

### Alerting

- **CI integration:** The scorecard runner compares results against the active
  baseline and emits warnings/failures in the test output.
- **PR blocking:** A `critical` regression blocks the PR merge (same as a
  Tier 4 gate failure).
- **Warning behavior:** A `warning` regression does not block merge but is
  surfaced in the PR check summary. Two consecutive `warning` regressions on
  the same dimension auto-escalate to `critical`.
- **Trend tracking:** A summary of per-family scores over the last 10 runs is
  printed at the end of each scorecard execution to surface gradual drift.

---

## Related Documents

- 034-AT-AUDT — Capability audit (current test inventory)
- 036-AT-SPEC — Response contracts (invariants to test)
- 038-PM-PLAN — Roadmap (eval tier rollout per phase)

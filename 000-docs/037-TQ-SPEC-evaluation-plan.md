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

## Related Documents

- 034-AT-AUDT — Capability audit (current test inventory)
- 036-AT-SPEC — Response contracts (invariants to test)
- 038-PM-PLAN — Roadmap (eval tier rollout per phase)

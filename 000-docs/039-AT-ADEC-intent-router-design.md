# 039 — ADR: Intent Router Design

**Status:** Proposed
**Date:** 2026-03-05
**Depends on:** 034-AT-AUDT (capability audit), 036-AT-SPEC (task taxonomy)

---

## Context

Every prompt currently enters the same pipeline regardless of intent. A question
like "what layer is entity X on?" goes through the planner and produces either an
empty changeset or hallucinated edit operations. The platform needs to distinguish
at least 9 task families before invoking the appropriate pipeline.

## Decision

**Two-stage hybrid router: keyword heuristics first, LLM fallback for ambiguous.**

```
Prompt
  |
  v
[Stage 1: Heuristic Rules]
  |
  ├── High confidence (>0.9) → TaskFamily + params → pipeline
  |
  └── Low confidence (<0.9)
        |
        v
      [Stage 2: LLM Classification]
        |
        ├── Classified → TaskFamily + params → pipeline
        |
        └── Still ambiguous → needs_clarification response
```

## Rationale

### Options Considered

| Option | Pros | Cons |
|--------|------|------|
| **A: LLM-only router** | Handles all edge cases, no rule maintenance | Every prompt costs an LLM call (~200ms + cost), overkill for obvious requests |
| **B: Heuristic-only router** | Zero LLM cost, deterministic, testable | Fails on ambiguous prompts, brittle for creative phrasing |
| **C: Hybrid (chosen)** | Fast path for obvious requests, LLM for edge cases | Two code paths to maintain |

Option C was chosen because:
1. ~80% of prompts are unambiguous ("move X", "what is Y", "compare with Z")
2. Heuristic stage adds <1ms latency vs ~200ms for LLM classification
3. Heuristic rules are fully testable with unit tests (no API dependency)
4. LLM fallback handles creative/ambiguous phrasing gracefully
5. `needs_clarification` response avoids wrong-pipeline errors

### Why Not Fine-Tuned Classifier?

A fine-tuned classification model was considered but rejected because:
- Training data doesn't exist yet (need production prompt logs first)
- Maintenance burden (retrain on every taxonomy change)
- Hybrid approach achieves same accuracy with less infrastructure

## Heuristic Rule Examples

Rules operate on lowercased, whitespace-normalized prompt text.

| Pattern | TaskFamily | Confidence |
|---------|-----------|------------|
| `move\|shift\|relocate\|displace` + entity reference | `edit_plan` | 0.95 |
| `delete\|remove\|erase` + entity reference | `edit_plan` | 0.95 |
| `change text\|rename\|relabel\|edit text` | `edit_plan` | 0.95 |
| `add\|insert\|place` + block reference | `edit_plan` | 0.90 |
| `compare\|diff\|what changed\|revision` + file reference | `compare` | 0.95 |
| `how many\|count\|list all\|find all` | `qna` or `summary` | 0.80 |
| `what is\|which layer\|where is\|show me` | `qna` | 0.85 |
| `summarize\|overview\|describe\|statistics` | `summary` | 0.90 |
| `takeoff\|quantity\|estimate\|bill of` | `takeoff_estimate` | 0.90 |
| `markup\|cloud\|redline\|revision cloud` | `markup_interpretation` | 0.85 |
| `repeat\|recurring\|pattern\|every\|all instances` | `repeated_condition` | 0.80 |
| `suggest\|improve\|optimize\|recommend` | `design_assist` | 0.80 |

Rules with confidence < 0.9 fall through to LLM classification for confirmation.

### Heuristic Priority Order

When a prompt matches multiple heuristic rules, the highest-priority (lowest number)
family wins. Rules are evaluated in this explicit order:

1. `compare` — most specific; requires two-file context signals
2. `markup_interpretation` — graphical annotation keywords are unambiguous
3. `edit_plan` — move/delete/add/edit-text verbs with entity references
4. `takeoff_estimate` — quantity/cost language distinct from Q&A
5. `repeated_condition` — pattern/recurrence keywords
6. `design_assist` — suggest/optimize/recommend
7. `summary` — overview/statistics language
8. `qna` — broadest read-only bucket; matches last
9. `needs_clarification` — nothing matched above threshold

If two rules from different families both exceed 0.9 confidence, the higher-priority
family is selected and the secondary match is logged as a diagnostic attribute.

## Task Family Boundaries

| Boundary | Rule |
|----------|------|
| `compare` requires two files | If session has only one file, reclassify as `qna` or prompt for second file |
| `qna` is read-only | If LLM produces edit operations for a `qna` intent, discard them and re-prompt as Q&A |
| `edit_plan` vs `apply_edit` | `edit_plan` = preview only; `apply_edit` = user confirmed, execute now |
| `markup_interpretation` vs `qna` | Markup requires detecting graphical annotations (clouds, arrows); Q&A is text/entity lookup |

## Implementation Sketch

**Module:** `src/cad_dxf_agent/llm/intent_router.py`

```python
class IntentResult(BaseModel):
    task_family: TaskFamily
    confidence: float
    params: dict[str, Any]  # extracted entities, layers, coordinates
    source: Literal["heuristic", "llm", "default"]

class IntentRouter:
    def __init__(self, rules: list[HeuristicRule], llm_provider: PlannerProvider | None = None):
        ...

    def classify(self, prompt: str, session: SessionContext | None = None) -> IntentResult:
        # Stage 1: heuristic rules
        result = self._heuristic_classify(prompt)
        if result.confidence >= 0.9:
            return result

        # Stage 2: LLM classification (if provider available)
        if self.llm_provider:
            return self._llm_classify(prompt, session)

        # Fallback: low confidence → ask for clarification (never default to a write-capable pipeline)
        return IntentResult(task_family=TaskFamily.NEEDS_CLARIFICATION, confidence=0.0, source="default")
```

## Edge Cases

| Scenario | Strategy |
|----------|----------|
| **Multi-intent prompt** ("count all doors and move them left") | Classify by primary/dominant intent (the action verb `move` dominates over `count`). The secondary intent is noted in `IntentResult.params["secondary_intent"]` for downstream use. |
| **Ambiguous prompt matching multiple families equally** | If the confidence spread between the top two heuristic matches is < 0.1, skip heuristic result and route to LLM classification. If LLM also returns a spread < 0.1, route to `needs_clarification`. |
| **Adversarial or nonsense input** | Heuristic stage produces no match. LLM fallback classifies as `unsupported_operation` or `needs_clarification` depending on whether it detects malformed intent or complete gibberish. |
| **Empty prompt** (whitespace-only or zero-length) | Immediate `needs_clarification` return from the heuristic stage — no LLM call needed. |
| **Non-English prompt** | Heuristic rules (English keyword patterns) will not match; prompt falls through to LLM classification, which handles multilingual input natively. |
| **Contradictory signals** (edit verbs + question structure, e.g., "should I move this wall?") | Heuristic stage defers (low confidence due to mixed signals). LLM resolves by interpreting pragmatic intent — in this example, `qna` (the user is asking, not commanding). |

## LLM Classification Specification

When the heuristic stage produces confidence < 0.9, the router invokes the LLM
classification stage.

### System Prompt Skeleton

```
You are a task classifier for a CAD drawing assistant.

Classify the following user prompt into exactly one of these task families:
  edit_plan, compare, qna, summary, takeoff_estimate,
  markup_interpretation, repeated_condition, design_assist,
  unsupported_operation, needs_clarification

Respond with JSON only. No explanation outside the JSON object.
```

### Expected JSON Response Schema

```json
{
  "task_family": "edit_plan",
  "confidence": 0.92,
  "reasoning": "Prompt contains 'move' verb targeting a named entity with explicit coordinates."
}
```

| Field | Type | Constraints |
|-------|------|-------------|
| `task_family` | string | Must be one of the enumerated family names |
| `confidence` | float | 0.0–1.0 |
| `reasoning` | string | One-sentence justification (logged, not shown to user) |

### Mapping to IntentResult

The LLM JSON response maps directly to `IntentResult`:

- `task_family` → `IntentResult.task_family` (validated against `TaskFamily` enum)
- `confidence` → `IntentResult.confidence`
- `reasoning` → stored in `IntentResult.params["llm_reasoning"]`
- `source` → set to `"llm"`

If the LLM returns an unrecognized `task_family` value or malformed JSON, the router
treats it as a classification failure and returns `needs_clarification`.

### Timeout and Error Handling

| Condition | Behavior |
|-----------|----------|
| LLM response within budget (< 2s) | Parse and return classification |
| LLM timeout (> 2s) | Return `needs_clarification` with `source="default"` |
| LLM returns malformed JSON | Log error, return `needs_clarification` |
| LLM provider unavailable | Heuristic result used regardless of confidence; if no heuristic match, return `needs_clarification` |

## Performance Budget

| Stage | Target | Rationale |
|-------|--------|-----------|
| Heuristic classification | p99 < 5ms | Regex/keyword matching on short strings; no I/O |
| LLM classification | p95 < 500ms | Single short-prompt LLM call; timeout at 2s |
| Overall router (end-to-end) | p95 < 50ms | ~80% of prompts resolve at heuristic stage; LLM invoked for ~20% |

The overall p95 target reflects the weighted mix: 80% of requests at <5ms and 20% at
<500ms yields a blended p95 well under 50ms.

## Observability

The router emits OpenTelemetry spans for each classification stage.

| Span Name | When | Key Attributes |
|-----------|------|----------------|
| `cad.router.classify` | Wraps entire `classify()` call | `router.task_family`, `router.confidence`, `router.source`, `router.latency_ms` |
| `cad.router.heuristic` | Heuristic stage execution | `router.source="heuristic"`, `router.confidence`, `router.task_family`, `router.latency_ms` |
| `cad.router.llm_fallback` | LLM stage (only when invoked) | `router.source="llm"`, `router.confidence`, `router.task_family`, `router.latency_ms` |

Attributes follow the existing `cad.*` namespace convention (see `otel.py`). No prompt
text is recorded in span attributes to avoid PII/data leakage.

## Testability

### Unit Tests — Heuristic Rules

Each heuristic rule is tested in isolation: pattern-in, family-out. Tests cover exact
keyword matches, partial matches, and near-miss patterns that should not match.

### Mock-Based Tests — LLM Stage

The LLM classification stage is tested with a `MockPlannerProvider` that returns
predetermined JSON responses, verifying correct parsing, enum mapping, and error handling
(malformed JSON, timeout simulation, unrecognized family names).

### Integration Tests — Two-Stage Flow

End-to-end tests exercise the full `classify()` method with prompts that:
- Resolve at heuristic stage (verify LLM is never called)
- Fall through to LLM stage (verify heuristic confidence < 0.9 triggers LLM)
- Hit both stages and still return `needs_clarification`

### Golden-File Test Suite

A suite of ~50 prompts with expected classifications lives in
`tests/fixtures/router_golden.json`. Each entry specifies:

```json
{
  "prompt": "move the north wall 2 feet left",
  "expected_family": "edit_plan",
  "expected_source": "heuristic",
  "min_confidence": 0.9
}
```

CI runs all golden-file entries on every push. New prompts from production logs are
periodically added to this file to prevent regressions.

## Versioning & Evolution

### Adding a New Task Family

1. Add the family to the `TaskFamily` enum in `ops_schema.py`
2. Add heuristic rules (keyword patterns + confidence) to the rule list
3. Update the LLM classification system prompt to include the new family
4. Add entries to `tests/fixtures/router_golden.json`
5. Document the family in 036-AT-SPEC (response contracts)

### Deprecating a Heuristic Rule

Rules are never silently removed. To deprecate:
1. Set the rule's confidence to 0.0 (effectively disabling it)
2. Add a `deprecated` flag to the rule metadata
3. Log a warning when a deprecated rule would have matched
4. Remove after two release cycles with no matches in production logs

### Feedback Loop from Production

Production prompt logs (with classification results) feed back into rule improvement:
- Prompts where heuristic and LLM disagree are flagged for review
- Prompts that reach `needs_clarification` are candidates for new rules
- Classification accuracy is tracked as a monthly metric

### Path to ML-Only Classification

As production prompt logs accumulate (target: 10k+ classified prompts), the hybrid
router can transition to an ML-only classifier:
1. Train a lightweight classifier (e.g., fine-tuned embedding model) on logged prompts
2. Run in shadow mode alongside hybrid router, comparing accuracy
3. Once ML accuracy exceeds hybrid accuracy on the golden-file suite, promote to primary
4. Retain LLM fallback for low-confidence ML predictions (hybrid-ML instead of hybrid-heuristic)

## Consequences

### Positive
- No wasted LLM calls for obvious requests
- Deterministic behavior for common patterns (fully testable)
- Graceful degradation without LLM (heuristic-only mode)
- `needs_clarification` prevents wrong-pipeline errors

### Negative
- Two code paths to maintain and keep in sync
- Heuristic rules need updating as vocabulary evolves
- Confidence threshold (0.9) may need tuning with production data

### Risks
- Heuristic rules may conflict (prompt matches multiple families) — resolve by priority ordering
- LLM classification adds latency for ambiguous prompts — acceptable since these are rare
- New task families require both heuristic rules and LLM prompt updates

## Related Documents
- 034-AT-AUDT — Capability audit (gap analysis)
- 035-AT-ARCH — Target architecture (router as Layer 1)
- 036-AT-SPEC — Response contracts and task taxonomy (TaskFamily enum)

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

        # Fallback: default to edit_plan (backward compatible)
        return IntentResult(task_family=TaskFamily.EDIT_PLAN, confidence=0.5, source="default")
```

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

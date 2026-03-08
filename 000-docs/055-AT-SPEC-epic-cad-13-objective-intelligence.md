# 055-AT-SPEC — EPIC-CAD-13: Objective Intelligence

**Epic:** EPIC-CAD-13
**Bead:** cad-dxf-agent-lk9
**Phase:** 6
**Status:** Open
**Created:** 2026-03-07

---

## Problem

Users are forced to speak CAD — "move entity X east 24 inches" — when they think in objectives: "cut cost", "shrink this room", "make this cheaper." The current router maps prompts to 11 TaskFamily values via keyword heuristics. It's 96.9% accurate for CAD operations, but it has no concept of *why* a user is asking.

## Solution

A two-axis intent classification layer above the existing router, plus a multi-stage reasoning pipeline that decomposes objectives into inspectable steps.

### Axis 1 — Primary Request Class

| Class | Description | Example |
|-------|-------------|---------|
| `understand` | Direct factual answer | "How many rooms?" |
| `estimate` | Quantity/cost approximation | "How much might this cost?" |
| `recommend` | Options with tradeoffs | "How many plants would look good?" |
| `optimize` | Reduce cost/labor/area | "Make this 20% cheaper" |
| `modify` | Change the drawing | "Shrink this room" |
| `summarize` | Deliverable for others | "Summarize for the customer" |
| `compare` | Revision differences | "What changed?" |

### Axis 2 — Objective Tag

`cost_reduction`, `labor_reduction`, `area_change`, `aesthetics`, `quantity_estimation`, `customer_communication`, `constructability`, `compliance`, `revision_explanation`

### Multi-Stage Pipeline

```
analyze → recommend → plan → preview
```

Each stage has:
- **Typed contract** — input model → output model (Pydantic)
- **Explicit gate** — user-visible checkpoint between stages
- **Audit trail** — inputs, outputs, timing, confidence recorded
- **No autonomy** — stages run in defined order, no branching

### Architecture Diagram

```
User prompt → ObjectiveClassifier (new)
                    ↓
              primary_class + objective_tag
                    ↓
              Strategy selector (registry)
                    ↓
              stage pipeline definition + output mode
                    ↓
              Multi-stage executor
                    ↓
              Stage 1: analyze → Gate → Stage 2: recommend → Gate → Stage 3: plan → Gate → preview
                    ↓
              TaskFamily handlers (existing)
                    ↓
              PlatformResponse (extended with objective + stage metadata)
```

## Key Design Decisions

1. **No agentic frameworks.** Multi-stage pipeline uses deterministic orchestration with typed contracts. No LangChain, LangGraph, CrewAI, or ADK.
2. **ObjectiveClassifier wraps IntentRouter.** Backward compatible — existing TaskFamily routing still works. Objective layer adds context, doesn't replace.
3. **Strategy selector is a registry.** New objectives = config entries, not code changes. Maps `(RequestClass, ObjectiveTag)` → stage pipeline definition.
4. **Classification starts heuristic.** Same pattern as current router. Can graduate to LLM when needed.
5. **Stages are composable.** New stages slot in without rewriting the executor.

## New Models

### `objective_schema.py`

```python
class RequestClass(StrEnum):
    UNDERSTAND = "understand"
    ESTIMATE = "estimate"
    RECOMMEND = "recommend"
    OPTIMIZE = "optimize"
    MODIFY = "modify"
    SUMMARIZE = "summarize"
    COMPARE = "compare"

class ObjectiveTag(StrEnum):
    COST_REDUCTION = "cost_reduction"
    LABOR_REDUCTION = "labor_reduction"
    AREA_CHANGE = "area_change"
    AESTHETICS = "aesthetics"
    QUANTITY_ESTIMATION = "quantity_estimation"
    CUSTOMER_COMMUNICATION = "customer_communication"
    CONSTRUCTABILITY = "constructability"
    COMPLIANCE = "compliance"
    REVISION_EXPLANATION = "revision_explanation"

class AnalysisResult(BaseModel):
    """Output of the analyze stage."""
    summary: str
    evidence: list[EvidenceRef]
    cost_drivers: list[dict[str, Any]] = []
    area_metrics: dict[str, float] = {}
    confidence: float

class RecommendationSet(BaseModel):
    """Output of the recommend stage."""
    options: list[RecommendationOption]
    selected_index: int | None = None

class RecommendationOption(BaseModel):
    """A single recommendation with tradeoffs."""
    title: str
    description: str
    estimated_impact: str
    tradeoffs: list[str]
    confidence: float
    operations_hint: list[str] = []  # OpType hints for plan stage

class StageGate(BaseModel):
    """Checkpoint between pipeline stages."""
    stage_name: str
    status: Literal["pending", "completed", "rejected", "skipped"]
    output_summary: str
    requires_user_input: bool = False
    timestamp: str
```

## Files to Create/Modify

| File | Action | Purpose |
|------|--------|---------|
| `src/cad_dxf_agent/models/objective_schema.py` | Create | RequestClass, ObjectiveTag, AnalysisResult, RecommendationSet, StageGate |
| `src/cad_dxf_agent/models/response_schema.py` | Modify | Extend PlatformResponse with objective + stage metadata |
| `src/cad_dxf_agent/llm/objective_classifier.py` | Create | Two-axis classifier wrapping IntentRouter |
| `src/cad_dxf_agent/llm/strategy_selector.py` | Create | Registry: (class, objective) → pipeline definition |
| `src/cad_dxf_agent/core/stage_pipeline.py` | Create | Multi-stage executor with typed I/O and gates |
| `web/backend/main.py` | Modify | Wire ObjectiveClassifier into /api/v2/prompt |
| `tests/eval/scorecard_entries.json` | Modify | Add objective-classified entries |

## Stories

| # | Title | Size |
|---|-------|------|
| 1 | Objective models — Pydantic schemas + tests | S |
| 2 | ObjectiveClassifier — heuristic two-axis classifier | M |
| 3 | Strategy selector registry | S |
| 4 | Stage pipeline executor | M |
| 5 | Wire into /api/v2/prompt (backward compatible) | M |
| 6 | Analyze stage — drawing analysis for cost/area/quantity | L |
| 7 | Recommend stage — ranked options with tradeoffs | L |
| 8 | Golden file expansion — 30+ objective-classified prompts | M |
| 9 | Scorecard extension — objective + stage accuracy | M |
| 10 | Response enrichment — objective context in PlatformResponse | S |

## Acceptance Criteria

- ObjectiveClassifier handles all example prompts correctly
- Multi-stage pipeline runs analyze → recommend → plan for optimize/modify
- Each stage gate is inspectable (user sees intermediate results)
- Existing single-stage requests (Q&A, compare, summary) unchanged
- Existing router golden file tests pass (backward compatible)
- New scorecard entries cover all 7 request classes
- Strategy selector is registry-based (new objectives = config, not code)
- No agentic framework dependency

# 056-AT-SPEC — EPIC-CAD-14: Professional Precision Controls

**Epic:** EPIC-CAD-14
**Bead:** cad-dxf-agent-bmw
**Phase:** 6
**Status:** Open
**Created:** 2026-03-07

---

## Problem

Professionals can't override AI inference. When the system picks the wrong entity or infers the wrong distance, the only option is to rephrase and hope. No way to target by handle, see why something was chosen, or provide exact measurements. This makes the tool a demo, not a production tool.

## Solution

Progressive disclosure — simple by default, precise on demand. Four capability layers that extend existing models without new systems.

### Capability 1 — Exact Targeting

- Target by entity handle, layer, or object type
- Override inferred regions/selections
- Constrain operation scope ("model space only", "exclude layer X")

### Capability 2 — Inspectability

- Show why the system picked a target (evidence, confidence, provenance)
- Display candidate match lists before committing
- Surface ambiguity explicitly ("I found 3 possible matches — which one?")

### Capability 3 — Deterministic Overrides

- Exact distance/delta inputs ("move east 24 inches" with numeric precision)
- Confidence threshold controls
- AI inference on/off per request

### Capability 4 — Structured Preview/Audit

- Exact action list before apply
- Before/after summary per entity
- Skipped/blocked actions visible
- Exportable audit trail

## How It Maps to Existing Code

Most extends existing models:

| Existing | Extension |
|----------|-----------|
| `PlatformRequest.client_metadata` | Precision control fields (targeting, scope, thresholds) |
| `PlatformResponse.evidence` | Richer provenance, confidence scores, match candidates |
| `PlatformResponse.ambiguity_flags` | Structured candidate lists, not just string flags |
| `PlatformResponse.validation` | Already surfaces blockers/warnings |
| `EditOperation.params` | Exact deltas, explicit units |
| Preview endpoint (`/api/v2/preview`) | Already exists, needs detail expansion |

## Key Design Decisions

1. **Extend, don't replace.** All precision controls go into existing model fields. No new request/response types.
2. **Optional always.** Every precision field has a default. Omitting them = current behavior.
3. **Progressive disclosure in UI.** Default view is simple. "Advanced" panel reveals targeting, scope, thresholds.
4. **Ambiguity is a first-class response.** When multiple targets match, return a candidate list + ask user, instead of silently guessing.

## Model Extensions

### PlatformRequest additions

```python
# Added to PlatformRequest or client_metadata
class PrecisionControls(BaseModel):
    """Optional precision overrides for professional users."""
    target_handles: list[str] = []          # Explicit entity handles
    target_layers: list[str] = []           # Layer filter (include)
    exclude_layers: list[str] = []          # Layer filter (exclude)
    target_types: list[str] = []            # Entity type filter
    model_space_only: bool = False          # Exclude paper space
    exact_delta: dict[str, float] | None = None  # {"dx": 24.0, "dy": 0.0}
    exact_units: str | None = None          # "inches", "mm", etc.
    confidence_threshold: float = 0.0       # Minimum confidence to proceed
    disable_inference: bool = False         # Skip AI inference, use only explicit targets
```

### PlatformResponse enrichments

```python
class MatchCandidate(BaseModel):
    """A potential target entity with match reasoning."""
    handle: str
    layer: str
    entity_type: str
    confidence: float
    match_reason: str
    location: tuple[float, float] | None = None

# Added to PlatformResponse
ambiguity_candidates: list[MatchCandidate] = []
stage_actions: list[ActionDetail] = []  # Per-entity action breakdown

class ActionDetail(BaseModel):
    """Detailed view of a single planned action."""
    entity_handle: str
    action: str  # "move", "delete", "edit_text", etc.
    before: dict[str, Any] = {}
    after: dict[str, Any] = {}
    status: str = "planned"  # planned | applied | skipped | blocked
    skip_reason: str | None = None
```

## UI/UX Design Strategy

> Frontend components designed with progressive disclosure pattern.
> Strategic UI/UX planning conducted via ui-ux-pro-max methodology.

### Component Architecture

| Component | Purpose | Disclosure Level |
|-----------|---------|-----------------|
| `PrecisionPanel.jsx` | Expandable precision controls | Advanced |
| `CandidateList.jsx` | Ambiguity resolution UI | On-demand (when ambiguous) |
| `ActionDetailView.jsx` | Per-entity action breakdown | Advanced preview |
| `AuditExport.jsx` | Download action log | Settings/export |

### Design Principles

1. **Zero-click default** — Simple users never see precision controls
2. **One-click expand** — "Show details" reveals targeting/scope panel
3. **Inline resolution** — Ambiguity candidates shown in chat flow, not modal
4. **Evidence-first** — Every AI decision shows "why" on hover/expand

## Files to Modify

| File | Action | Purpose |
|------|--------|---------|
| `src/cad_dxf_agent/models/response_schema.py` | Modify | Add PrecisionControls, MatchCandidate, ActionDetail |
| `src/cad_dxf_agent/models/ops_schema.py` | Modify | Explicit targeting params on EditOperation |
| `web/backend/main.py` | Modify | Honor precision overrides in dispatch |
| `src/cad_dxf_agent/llm/response_builder.py` | Modify | Richer evidence/ambiguity in responses |
| `web/frontend/src/components/PrecisionPanel.jsx` | Create | Progressive disclosure UI |
| `web/frontend/src/components/CandidateList.jsx` | Create | Ambiguity resolution |
| `web/frontend/src/components/ActionDetailView.jsx` | Create | Per-entity action breakdown |

## Stories

| # | Title | Size |
|---|-------|------|
| 1 | Explicit targeting params on PlatformRequest | S |
| 2 | Evidence enrichment — provenance, confidence, candidates | M |
| 3 | Ambiguity surfacing — candidate list instead of guessing | M |
| 4 | Exact delta support — precise measurements honored | S |
| 5 | Scope constraints — layer filter, model-space-only | S |
| 6 | Preview detail expansion — skipped/blocked actions visible | M |
| 7 | Frontend progressive disclosure — PrecisionPanel + CandidateList | L |
| 8 | Audit export — downloadable action log per session | M |

## Acceptance Criteria

- Professional user can override AI entity selection via explicit handle
- Ambiguous requests surface candidate list instead of silent guess
- Exact measurement inputs honored without LLM reinterpretation
- Preview shows complete action list including skipped/blocked
- All precision controls optional — default behavior unchanged
- Progressive disclosure UI: simple default, expandable advanced panel

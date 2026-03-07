# 045-AT-SPEC: EPIC-CAD-05 -- Repeated-Condition Scoring Model

## Problem Statement

Construction and structural drawings contain repeated conditions -- similar arrangements
of entities (block references, labeled regions, structural bays) that appear multiple times.
Users need to find all instances of a given condition to verify consistency, apply batch edits,
or audit annotation coverage.

## Approach

Given a user-selected **exemplar** (a set of entity handles defining one instance of the condition),
the system searches the drawing for spatially distinct clusters that exhibit similar characteristics.

The system does NOT use an LLM for detection. Matching is deterministic, using weighted
similarity signals from existing primitives (entity index, comparison scorer, text geometry).

## Similarity Scoring Model

### Signal Types

| Signal | Weight | Source | Description |
|--------|--------|--------|-------------|
| `block_name` | 0.30 | EntityIndex | Same block definition (INSERT entities) |
| `text_content` | 0.25 | EntityIndex + Levenshtein | Similar text labels nearby |
| `geometry_shape` | 0.20 | comparison/scorer | Geometry signature similarity (length, angles, turn hash) |
| `layer_context` | 0.10 | EntityIndex | Same layer distribution as exemplar |
| `spatial_pattern` | 0.10 | EntityIndex | Similar relative spacing between entities |
| `text_geometry` | 0.05 | TextGeometry | Height/rotation match for text entities |

### Text Trust Weighting

From SIDEQUEST-CAD-67, text signals are weighted by provenance:

| Provenance | Trust Multiplier | Rationale |
|------------|-----------------|-----------|
| native_cad_text | 1.0 | Full trust in native CAD text |
| block_attribute_text | 0.95 | Slight deduction for transform composition |
| vector_outline_text | 0.6 | Future: approximate geometry |
| raster_ocr_text | 0.3 | Future: unreliable positioning |

When a text signal contributes to a match, its effective weight is:
`signal_weight * trust_multiplier`. This prevents OCR-derived text from
dominating over native geometry signals.

### Confidence Thresholds

| Confidence | Interpretation |
|------------|---------------|
| >= 0.85 | High confidence -- likely same condition |
| 0.65 - 0.84 | Medium -- probable match, may need user review |
| 0.50 - 0.64 | Low -- ambiguous near-match |
| < 0.50 | Not reported (below min_confidence default) |

### Ambiguity Handling

When multiple candidates have confidence within 0.05 of each other, the result
includes an `ambiguity_flag` noting the near-tie. The UI should present these
for explicit user review rather than auto-approving.

### False Positive Mitigation

1. Candidates must be spatially distinct from the exemplar (min separation > exemplar radius)
2. Single-entity matches (e.g., one TEXT entity) require confidence >= 0.70
3. Block-only matches (same INSERT, nothing else) are capped at 0.80 unless
   nearby text also matches

## Search Algorithm

1. Build **exemplar profile**: entity types, block names, text content, layer distribution,
   centroid, radius (bounding circle from entity positions)
2. For each unique block_name in the exemplar, find all other INSERTs with that block_name
3. Cluster candidate INSERTs by spatial proximity (radius = exemplar radius * 1.5)
4. For each candidate cluster, score against exemplar profile using weighted signals
5. Filter by min_confidence, sort by confidence descending
6. Apply spatial deduplication (merge overlapping clusters)
7. Cap results at max_results

## Data Flow

```
User selects exemplar entities
  -> ConditionDetector.find_repeated(handles, ...)
    -> Build exemplar profile
    -> Search EntityIndex for candidate seeds (blocks, text)
    -> Cluster seeds spatially
    -> Score each cluster against exemplar
    -> Filter, rank, deduplicate
  -> RepeatedConditionResult
    -> Candidates with confidence, evidence, explanation
    -> Preview in UI for approval
```

## Preview/Approval Workflow

The result is **read-only**. No edits are applied in this epic.

Users can:
- View the list of candidate matches
- See confidence score and signal breakdown per match
- See which entities are in each match (with handles for drill-down)
- Approve or reject individual candidates
- Approval state is stored in-memory (session-scoped)

Future epics (EPIC-CAD-07/08) will use approved candidates for batch edit operations.

## Files

| File | Purpose |
|------|---------|
| `models/repeated_condition_schema.py` | Pydantic schemas |
| `core/repeated_condition.py` | Detector + scoring logic |
| `llm/capability_registry.py` | Register REPEATED_CONDITION as implemented |
| `llm/response_builder.py` | Build PlatformResponse for repeated_condition |
| `web/backend/main.py` | Wire endpoint (or extend /api/v2/prompt) |

## Known Limitations

1. No spatial index (quadtree/R-tree) -- O(n) scan acceptable for < 5000 entities
2. Text content matching uses Levenshtein, not semantic similarity
3. Geometry matching limited to V1 entity types
4. No nested block pattern recognition
5. Approval state is session-scoped (no persistence until EPIC-CAD-11)

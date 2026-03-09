# 070-AN-TEST: Real-World Prompt Test Matrix

**Status:** Active
**Created:** 2026-03-09
**Scope:** 118 prompts across 23 categories, all platform capabilities

## Purpose

Validates that the Drawing Intelligence Platform handles what real architects, engineers, and contractors actually type — not just clean developer-written prompts. Identifies classification gaps before beta launch.

## Test Results Summary

| Metric | Value |
|--------|-------|
| Total prompts | 118 |
| Correctly classified (scored) | 68 / 68 (100%) |
| Documented gaps (needs_clarification → xfail) | 41 |
| Unscored (expected needs_clarification) | 50 |
| Pipeline crashes | 0 |
| Safety violations | 0 |
| Categories covered | 23 |

**Key insight:** The router correctly classifies every prompt it has patterns for (100% on scored prompts). The problem is missing patterns — 41 prompts that SHOULD classify as something useful fall through to `needs_clarification`.

## Gap Analysis — 24 Distinct Gap Types

### High Priority (will break for beta users)

| Gap Type | Count | Impact | Fix |
|----------|-------|--------|-----|
| `gap-typo-handling` | 6 | "moev", "delet", "roatate" — real users misspell | Add fuzzy alternations to regex patterns |
| `gap-check-keyword` | 4 | "check compliance", "audit drawing" — zero match | Add `check\|audit\|inspect` to design_assist |
| `gap-draw-keyword` | 3 | "draw a line" — creation verb missing | Add `\bdraw\b` to edit_plan |
| `gap-copy-keyword` | 3 | "copy", "duplicate", "paste" — zero match | Add `\bcopy\b\|\bduplicate\b` to edit_plan |
| `gap-change-keyword` | 3 | "change the X" — only `change text` matches | Broaden to `\bchange\b` in edit_plan |
| `gap-mirror-keyword` | 1 | "mirror" op exists but keyword missing | Add `\bmirror\b` to edit_plan |

### Medium Priority (degraded experience)

| Gap Type | Count | Impact | Fix |
|----------|-------|--------|-----|
| `gap-jargon` | 2 | MEP, CD set, PCO not recognized | Add industry abbreviation patterns |
| `gap-whats-contraction` | 2 | "What's the area?" — contraction fails `\bwhat\s+is\b` | Change to `\bwhat(?:'s\|\s+is)\b` |
| `gap-nudge-keyword` | 1 | "nudge" = move synonym | Add to edit_plan patterns |
| `gap-bump-keyword` | 1 | "bump" = move synonym | Add to edit_plan patterns |
| `gap-cleanup-keyword` | 1 | "clean up" = implicit delete | Add to edit_plan patterns |
| `gap-getrid-keyword` | 1 | "get rid of" = delete | Add to edit_plan patterns |
| `gap-fix-keyword` | 1 | "fix the typo" — common real-world verb | Add `\bfix\b` to edit_plan |
| `gap-place-keyword` | 1 | "place the text" = add synonym | Add `\bplace\b` to edit_plan |
| `gap-swap-keyword` | 1 | "swap positions" — complex op | Add `\bswap\b` to edit_plan |
| `gap-explain-keyword` | 1 | "explain this plan" — summary verb | Add `\bexplain\b` to summary |
| `gap-verify-keyword` | 1 | "verify fire egress" | Add `\bverify\b` to design_assist |
| `gap-rfi-keyword` | 1 | "generate RFIs" | Add `\brfi\b` to design_assist |
| `gap-quality-keyword` | 1 | "quality check" | Add to design_assist |

### Low Priority (edge cases)

| Gap Type | Count | Impact | Fix |
|----------|-------|--------|-----|
| `gap-non-english` | 2 | Spanish/Japanese prompts | LLM fallback (future) |
| `gap-are-the-vs-are-there` | 1 | "Are the corridors" ≠ "Are there" | Broaden `\bare\b` qna patterns |
| `gap-does-keyword` | 1 | "Does every room" | Add `\bdoes\b` to qna |
| `gap-which-keyword` | 1 | "Which doors" — only "which layer" matched | Broaden `\bwhich\b` |
| `gap-is-this-vs-is-there` | 1 | "Is this CD set" ≠ "Is there" | Broaden `\bis\b` qna patterns |

### Fix Effort Summary

| Fix Location | Gap Count | Effort |
|-------------|-----------|--------|
| `intent_router.py` — add keywords to edit_plan | 17 | Small (add ~15 patterns) |
| `intent_router.py` — add design_assist patterns | 8 | Small (add ~5 patterns) |
| `intent_router.py` — broaden qna patterns | 5 | Small (widen 4 regexes) |
| `intent_router.py` — add summary patterns | 1 | Trivial |
| `intent_router.py` — add jargon aliases | 2 | Small |
| Future: LLM fallback for non-English | 2 | Large |

## Coverage by Drawing Fixture

| Fixture | Prompts | Purpose |
|---------|---------|---------|
| structural | 110 | Main test drawing — grids, columns, text, title block |
| overlapping | 3 | Spatial disambiguation, dedup |
| empty_layers | 3 | Orphan layers, sparse drawing |
| unicode | 1 | CJK/accented text labels |
| residential | 1 | Rooms, doors, walls — compliance/zone testing |

## Coverage by Expected Family

| Family | Prompts | Notes |
|--------|---------|-------|
| needs_clarification | 50 | 41 are documented gaps; 9 are correctly vague/adversarial |
| edit_plan | 38 | Move, delete, text, create, transform, batch, multi-op |
| summary | 9 | Includes prompts reclassified from qna via `\bwhat.+this\s+drawing\b` |
| qna | 8 | Layer queries, position, existence, spatial |
| takeoff_estimate | 6 | Counts, measurements, BOM |
| compare | 5 | Diff, revision, layer-scoped |
| design_assist | 1 | Field report (matches `\bfield\s+report\b`) |
| markup_interpretation | 1 | Red-cloud ASI (matches `\bcloud\b`) |

## Coverage by Difficulty

| Difficulty | Count | Examples |
|-----------|-------|---------|
| targeted | 37 | Specific entity/layer references |
| basic | 31 | Clean, well-formed commands |
| adversarial | 18 | Typos, injection, emoji, long prompts |
| conversational | 13 | Polite, vague, context-dependent |
| multi-step | 5 | Chained operations |
| jargon | 5 | MEP, ASI, CD set, PCO, T-bar |
| vague | 5 | "Fix it", "Make it better" |
| spatial | 4 | Coordinates, relative positions |

## Running the Tests

```bash
# All 118 prompts (fast, ~0.8s, no API calls)
.venv/bin/python -m pytest tests/eval/test_realworld_prompts.py -v

# Classification only
.venv/bin/python -m pytest tests/eval/test_realworld_prompts.py::TestRealWorldIntentClassification -v

# Safety constraint tests
.venv/bin/python -m pytest tests/eval/test_realworld_prompts.py::TestRealWorldSafetyConstraints -v

# Gap analysis (41 xfail tests documenting what needs fixing)
.venv/bin/python -m pytest tests/eval/test_realworld_prompts.py::TestRealWorldGapAnalysis -v

# Coverage report with accuracy table
.venv/bin/python -m pytest tests/eval/test_realworld_prompts.py::TestRealWorldCoverageReport -v -s

# Single category
.venv/bin/python -m pytest tests/eval/test_realworld_prompts.py -v -k "move"
```

## Files

| File | Purpose |
|------|---------|
| `tests/fixtures/realworld_prompts.json` | 118-prompt dataset |
| `tests/eval/test_realworld_prompts.py` | Parametrized test runner (5 test classes) |
| `tests/eval/scorecard_entries.json` | 56 scorecard entries (32 original + 24 new) |
| `tests/helpers/dxf_factory.py` | 2 new builders: `create_residential_drawing`, `create_electrical_drawing` |
| `000-docs/070-AN-TEST-realworld-prompt-matrix.md` | This document |

## Methodology

1. **Capability-Coverage Matrix** — enumerated all 13 OpTypes, 23 tools, 5 analysis handlers, 8 RequestClass values, 15 ObjectiveTags, 8 TaskFamilies. Counted existing test prompts per capability → found 13 capabilities with zero prompt coverage.

2. **Category × Difficulty × Fixture** — designed 118 prompts spanning 23 categories and 8 difficulty levels. Each prompt traced through the actual regex heuristic rules to determine ground-truth expected_family.

3. **Regex-Accurate Classification** — every `expected_family` was determined by simulating the priority-ordered pattern matching against the actual `_RULES` in `intent_router.py`. No aspirational values.

4. **Gap Tagging** — prompts that classify as `needs_clarification` but SHOULD classify as something else are tagged with `should_be_*` and `gap-*` tags for systematic tracking.

## Adding New Prompts

1. Add entry to `tests/fixtures/realworld_prompts.json` with all required fields
2. Trace through `_RULES` in `intent_router.py` to determine correct `expected_family`
3. Run: `.venv/bin/python -m pytest tests/eval/test_realworld_prompts.py -v -k "rw-new-001"`
4. If a gap, add `should_be_*` and `gap-*` tags
5. Update coverage stats in this document

# 048 — EPIC-CAD-07 End-of-Phase Report: Structured Edit Planning

**Date:** 2026-03-07
**Epic:** EPIC-CAD-07 (Structured Edit Planning)
**Bead:** cad-9ug
**Branch:** `feature/epic-cad-07-edit-planning`
**PR:** #85
**Gate:** ARCH-REVIEW-CAD-01 CONDITIONAL GO (all 3 prerequisites satisfied)

---

## 1. Scope Delivered

Four stories completed:

| Story | Deliverable | Status |
|-------|------------|--------|
| 1 — Schema | `models/plan_schema.py` — EditPlan, EditAction, EditActionType (5 values), PlanValidationStatus (4 values), ApprovalRequirement, PlanLatency, ActionValidationDetail | DONE |
| 2 — Builder | `llm/plan_builder.py` — Deterministic EditPlanBuilder (no LLM), PlanRequest dataclass, regex-based intent routing, displacement/text parsing, target resolution by handle or region | DONE |
| 3 — Validator | `core/plan_validator.py` — PlanValidator enforcing protected layers, entity/action compatibility, SQ67 text trust, move distance limits, batch replication approval gates | DONE |
| 4 — Tests | 109 tests across 6 test files — golden scenarios, anti-regression guards, unit coverage for schema/builder/validator/text_utils | DONE |

### ARCH-REVIEW-CAD-01 Prerequisites

| # | Prerequisite | Deliverable | Status |
|---|-------------|-------------|--------|
| P0 | Upload size validation (25MB) | `web/backend/main.py` — 413 response for oversized uploads | DONE |
| P1 | Extract shared text_utils | `core/text_utils.py` — levenshtein, describe_entity, entity_to_evidence; deduplicates scorer.py + repeated_condition.py | DONE |
| P1 | Truncation confidence penalty | `core/region_context.py` — `-0.2` confidence reduction when context is truncated | DONE |

---

## 2. Architecture Alignment

### Design Decisions

1. **Deterministic builder, no LLM** — EditPlanBuilder uses regex + rules, never calls an LLM. This keeps plan generation fast, testable, and predictable. LLM routing stays in the existing IntentRouter.

2. **Plan-only output** — EditPlan has no `apply()` or `execute()` method. The plan is a data structure that describes proposed changes. Actual application is deferred to EPIC-08 (Preview + Apply).

3. **Typed action enum** — 5 bounded action types: `MOVE_ENTITY`, `EDIT_TEXT`, `DELETE_ENTITY`, `ADD_BLOCK`, `REPLICATE_NOTE`. Unsupported requests produce `NEEDS_CLARIFICATION` status with zero actions, never freeform blobs.

4. **SQ67 text trust integration** — OCR-provenance entities get reduced confidence and `low_text_trust` ambiguity flags. The validator surfaces text trust warnings independently.

5. **Batch replication gate** — Plans from repeated-condition results require `APPROVED` state on every candidate. `PENDING` candidates block the entire plan.

### Source Layout

```
src/cad_dxf_agent/
  models/plan_schema.py      # EditPlan, EditAction, EditActionType, PlanValidationStatus
  llm/plan_builder.py        # EditPlanBuilder, PlanRequest
  core/plan_validator.py      # PlanValidator
  core/text_utils.py          # Shared: levenshtein, describe_entity, entity_to_evidence
  llm/response_builder.py     # Updated: structured_plan() method
  core/region_context.py      # Updated: truncation confidence penalty
  core/comparison/scorer.py   # Updated: uses text_utils
  core/repeated_condition.py  # Updated: uses text_utils
  web/backend/main.py         # Updated: 25MB upload limit
```

---

## 3. Test Evidence

### New Tests (109 total)

| File | Tests | Coverage |
|------|-------|----------|
| `test_plan_schema.py` | 25 | Enums, model creation, serialization, bounds, properties |
| `test_plan_builder.py` | 30 | Move/delete/text-edit/add/batch routing, evidence, latency, parsing |
| `test_plan_validator.py` | 20 | Protected layers, entity/action compat, missing targets, confidence, text trust, move/edit params, replicate |
| `test_plan_anti_regression.py` | 15 | No-apply, no non-edit routing, no freeform, blocked persists, OCR trust, approval required |
| `test_plan_golden.py` | 10 | Construction edit, annotation review, text provenance, batch replication |
| `test_text_utils.py` | 16 | Levenshtein distance/similarity, describe_entity, entity_to_evidence |

### Anti-Regression Guards

| Guard | Test Class | Enforces |
|-------|-----------|----------|
| Edit planning does not apply edits | `TestEditPlanDoesNotApplyEdits` | No `apply()` or `execute()` on EditPlan |
| Non-edit families excluded | `TestNonEditFamiliesExcluded` | Q&A, summary, compare, repeated_condition don't route to edit planning |
| No freeform actions | `TestNoUnsupportedFreeformActions` | All actions are valid EditActionType enum values |
| Blocked plans remain blocked | `TestBlockedPlansRemainBlocked` | Blocked status persists, pending batch stays blocked |
| OCR text trust | `TestOcrTextDoesNotMasqueradeAsExact` | Low-trust OCR reduces confidence, flags ambiguity |
| Batch approval required | `TestRepeatedConditionApprovalRequired` | Unapproved candidates blocked, approved proceed |

### Golden Scenarios

| Scenario | Tests | Validates |
|----------|-------|-----------|
| Construction drawing: callout edit | 3 | Move with displacement, text edit, title-layer blocking |
| Annotation review: region delete | 1 | Multi-entity delete in region, destructive confirmation |
| Text provenance: native vs OCR | 3 | Native high confidence, OCR reduced confidence, validator warns |
| Batch replication | 1 | Approved matches generate replication plan with match confidences |

### Full Suite

```
1760 passed, 0 failed, 5 skipped (32.75s)
ruff: All checks passed
mypy: Success, no issues found in 4 source files
```

---

## 4. Compliance Checklist

| # | Requirement | Status | Evidence |
|---|------------|--------|----------|
| C1 | EditPlan has no apply/execute method | PASS | `test_plan_has_no_apply_method` |
| C2 | Non-edit families never route to edit | PASS | `TestNonEditFamiliesExcluded` (4 parametrized + 2 explicit) |
| C3 | All actions are typed enum values | PASS | `test_all_action_types_are_valid_enum` |
| C4 | Blocked plans stay blocked | PASS | `test_blocked_status_persists_after_creation` |
| C5 | OCR text reduces confidence | PASS | `test_ocr_text_reduces_confidence` (anti-regression + golden) |
| C6 | Batch replication requires approval | PASS | `test_unapproved_candidates_blocked`, `test_approved_candidates_proceed` |
| C7 | Protected layers block edits | PASS | `TestProtectedLayerBlocking` (4 tests) |
| C8 | Upload size validation (P0) | PASS | 25MB limit in `web/backend/main.py` |
| C9 | Shared text_utils (P1) | PASS | `text_utils.py` extracted, scorer + repeated_condition updated |
| C10 | Truncation confidence penalty (P1) | PASS | `-0.2` in `region_context.py` |

---

## 5. Metrics Delta

| Metric | Before | After | Delta |
|--------|--------|-------|-------|
| Total tests (collected) | 1,651 | 1,760 | +109 |
| Source files (new) | — | 4 | +4 |
| Source files (modified) | — | 5 | +5 |
| Lines added | — | 2,882 | +2,882 |
| Lines removed | — | 64 | -64 |

---

## 6. Dependency Graph Update

```
EPIC-01 (DONE) -> EPIC-02 (DONE)
                    |-> EPIC-03 (DONE) -> EPIC-04 (DONE) + SQ67 (DONE) -> EPIC-05 (DONE)
                    |-> EPIC-06 (DONE)
              EPIC-04 + 05 + 06 -> ARCH-REVIEW-01 (DONE)
                                    |-> EPIC-07 (DONE) -> EPIC-08 (next)
                                    |-> EPIC-11
              EPIC-04 + 08 -> EPIC-09
              EPIC-03 + 06 + 07 -> EPIC-10
              EPIC-04..10 -> EPIC-12
```

---

## 7. Risks & Issues

| Risk | Status | Mitigation |
|------|--------|------------|
| Plan builder regex may miss edge cases | ACTIVE | Golden tests cover representative scenarios; extend as real user prompts arrive |
| No LLM-assisted disambiguation | ACCEPTED | Intentional — builder is deterministic. LLM disambiguation deferred to EPIC-08 preview flow |
| Batch replication may need richer source context | LOW | Current schema captures source_handles + target_centroid; extend if needed in EPIC-10 |

---

## 8. Open Items for EPIC-08

1. Wire EditPlan into preview generation (human-readable diff)
2. Implement apply workflow (EditPlan -> ChangeSet -> EditEngine)
3. Frontend PreviewPanel component with approve/reject UI
4. Audit trail: record plan ID, approval timestamp, applied actions
5. Undo support: revert from applied plan

---

## 9. Files Changed

### New Files
- `src/cad_dxf_agent/models/plan_schema.py`
- `src/cad_dxf_agent/llm/plan_builder.py`
- `src/cad_dxf_agent/core/plan_validator.py`
- `src/cad_dxf_agent/core/text_utils.py`
- `tests/unit/test_plan_schema.py`
- `tests/unit/test_plan_builder.py`
- `tests/unit/test_plan_validator.py`
- `tests/unit/test_plan_anti_regression.py`
- `tests/unit/test_plan_golden.py`
- `tests/unit/test_text_utils.py`

### Modified Files
- `src/cad_dxf_agent/core/comparison/scorer.py` — uses shared text_utils
- `src/cad_dxf_agent/core/repeated_condition.py` — uses shared text_utils
- `src/cad_dxf_agent/core/region_context.py` — truncation confidence penalty
- `src/cad_dxf_agent/llm/response_builder.py` — structured_plan() method
- `web/backend/main.py` — upload size validation

---

## 10. Conclusion

EPIC-CAD-07 is complete. The Structured Edit Planning system provides a typed, validated, auditable edit plan schema with deterministic generation and comprehensive constraint enforcement. All 3 ARCH-REVIEW-CAD-01 prerequisites are satisfied. The system is ready for EPIC-08 (Preview + Apply Workflow) to wire plans into the execution pipeline.

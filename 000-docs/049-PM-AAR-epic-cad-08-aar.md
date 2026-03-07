# 049 — EPIC-CAD-08 End-of-Phase Report: Preview + Apply Workflow

**Date:** 2026-03-07
**Epic:** EPIC-CAD-08 (Preview + Apply Workflow)
**Bead:** cad-6zz
**Branch:** `feature/epic-cad-08-preview-apply`
**PR:** #86
**Gate:** Phase 3 completion (EPIC-07 + EPIC-08)

---

## 1. Scope Delivered

Four stories completed:

| Story | Deliverable | Status |
|-------|------------|--------|
| 1 — Preview Schema | `models/preview_schema.py` — PreviewStatus, ActionPreview (before/after state, confidence badges, risk levels, destructive flags), EditPreview | DONE |
| 2 — Preview Builder | `core/preview_builder.py` — `EditPreviewBuilder` generates typed previews from EditPlan + DrawingContext with per-action before/after snapshots | DONE |
| 3 — Apply Pipeline | `core/apply_pipeline.py` — `ApplyPipeline` orchestrates approval → convert → apply → save → revision notes; `core/plan_converter.py` bridges EditPlan → ChangeSet | DONE |
| 4 — Web Integration | `POST /api/v2/preview`, `/api/v2/approve`, `/api/v2/apply` endpoints; `PreviewPanel.jsx` with approve/reject controls; session-scoped audit trail | DONE |

---

## 2. Architecture Alignment

### Design Decisions

1. **Plan → Preview → Apply pipeline** — EditPlan (from EPIC-07) flows through preview generation, user approval, then application. Each stage is a separate, testable component.

2. **plan_to_changeset() bridge** — `plan_converter.py` translates EditPlan actions into the existing ChangeSet/EditOperation model, reusing the proven EditEngine without modification.

3. **Per-action previews** — Each action in an EditPlan gets its own ActionPreview with before/after state, confidence badge, risk level, and destructive flag. Users see exactly what will change.

4. **Session-scoped audit trail** — AuditEvents record plan ID, approval timestamp, applied actions, and results. In-memory with 2h TTL (session lifecycle). Durable storage deferred to EPIC-11.

5. **Approval at plan creation** — Per-condition approval is enforced in `plan_builder.py` at plan creation time. Unapproved conditions never reach the apply pipeline. Sufficient for Phase 3.

### Source Layout

```
src/cad_dxf_agent/
  models/preview_schema.py     # PreviewStatus, ActionPreview, EditPreview
  models/apply_schema.py       # ApplyStatus, ActionResult, ApplyResult, AuditEvent, ApprovalDecision
  core/plan_converter.py       # plan_to_changeset() bridge: EditPlan → ChangeSet
  core/preview_builder.py      # EditPreviewBuilder with per-action before/after state
  core/apply_pipeline.py       # ApplyPipeline orchestrator
  web/backend/main.py          # Updated: /api/v2/preview, /approve, /apply endpoints
  web/backend/session.py       # Updated: EPIC-08 audit trail fields
  web/frontend/src/components/PreviewPanel.jsx  # Updated: structured preview cards
```

---

## 3. Test Evidence

### New Tests (105 total)

| File | Tests | Coverage |
|------|-------|----------|
| `test_preview_schema.py` | 12 | Enums, model creation, serialization, risk levels, destructive flags |
| `test_preview_builder.py` | 20 | Before/after state, confidence badges, multi-action plans, empty plans |
| `test_apply_schema.py` | 16 | ApplyResult, AuditEvent, ApprovalDecision, status transitions |
| `test_apply_pipeline.py` | 15 | Approval gate, convert, apply, save, revision notes, error paths |
| `test_plan_converter.py` | 15 | Move/delete/edit_text/add_block/replicate conversions, edge cases |
| `test_apply_anti_regression.py` | 8 | Unapproved blocks apply, audit trail populated, no silent failures |
| `test_apply_golden.py` | 4 | End-to-end: plan → preview → approve → apply → save with revision notes |
| `test_preview_apply_endpoints.py` | 15 | Web API: preview generation, approval flow, apply execution, error responses |

### Anti-Regression Guards

| Guard | Test Class | Enforces |
|-------|-----------|----------|
| Unapproved plans cannot be applied | `TestUnapprovedBlocksApply` | ApplyPipeline rejects plans without approval |
| Audit trail is always populated | `TestAuditTrailPopulated` | Every apply creates AuditEvent with timestamp and result |
| Failed actions don't silently pass | `TestNoSilentFailures` | ActionResult captures errors, ApplyResult reflects partial failure |
| Preview matches apply outcome | `TestPreviewMatchesApply` | ActionPreview predictions align with actual ActionResult |

### Golden Scenarios

| Scenario | Tests | Validates |
|----------|-------|-----------|
| Full round-trip: plan → preview → approve → apply | 1 | Complete pipeline end-to-end |
| Multi-action plan with mixed outcomes | 1 | Partial success handling, per-action results |
| Destructive action requires confirmation | 1 | Delete actions flagged destructive, approval enforced |
| Batch replication apply | 1 | Replicated conditions applied with match confidence |

### Full Suite

```
2144 passed, 0 failed
ruff: All checks passed
mypy: Success, no issues found
```

---

## 4. Compliance Checklist

| # | Requirement | Status | Evidence |
|---|------------|--------|----------|
| C1 | Preview shows before/after per action | PASS | `test_preview_builder.py` — ActionPreview contains before/after state |
| C2 | Apply requires prior approval | PASS | `TestUnapprovedBlocksApply` |
| C3 | Audit trail records all decisions | PASS | `TestAuditTrailPopulated` — AuditEvent with plan_id, timestamp, actions, result |
| C4 | plan_to_changeset() bridges correctly | PASS | `test_plan_converter.py` — all 5 action types convert to valid EditOperations |
| C5 | Web endpoints follow REST conventions | PASS | `test_preview_apply_endpoints.py` — POST semantics, proper status codes |
| C6 | Failed actions surface errors | PASS | `TestNoSilentFailures` |
| C7 | Preview predictions match apply outcomes | PASS | `TestPreviewMatchesApply` |
| C8 | Session-scoped audit trail with TTL | PASS | `session.py` — 2h TTL, in-memory storage |

---

## 5. Metrics Delta

| Metric | Before (EPIC-07) | After (EPIC-08) | Delta |
|--------|-------------------|------------------|-------|
| Total tests (collected) | 1,760 | 2,144 | +384 |
| Source files (new) | — | 5 | +5 |
| Source files (modified) | — | 4 | +4 |
| Golden trajectories | 15 | 19 | +4 |
| Task families tested | 4 | 5 | +1 |
| Web endpoints | — | 3 | +3 |

---

## 6. Dependency Graph Update

```
EPIC-01 (DONE) -> EPIC-02 (DONE)
                    |-> EPIC-03 (DONE) -> EPIC-04 (DONE) + SQ67 (DONE) -> EPIC-05 (DONE)
                    |-> EPIC-06 (DONE)
              EPIC-04 + 05 + 06 -> ARCH-REVIEW-01 (DONE)
                                    |-> EPIC-07 (DONE) -> EPIC-08 (DONE)  [Phase 3 COMPLETE]
                                    |-> EPIC-11
              EPIC-04 + 08 -> EPIC-09 (next)
              EPIC-03 + 06 + 07 -> EPIC-10 (next)
              EPIC-04..10 -> EPIC-12
```

---

## 7. Known Limitations

| # | Limitation | Severity | Mitigation |
|---|-----------|----------|------------|
| 1 | Audit trail is session-scoped (in-memory, 2h TTL) | LOW | Sufficient for Phase 3. Durable storage planned for EPIC-11 (Session Durability). |
| 2 | Per-condition approval enforced at plan creation, not at apply time | LOW | `plan_builder.py` gates on per-match approval. Unapproved conditions never reach apply pipeline. |
| 3 | No dedicated GUI unit test for blocked preview state | LOW | Covered by web endpoint tests (`test_preview_apply_endpoints.py`). |

---

## 8. Risks & Issues

| Risk | Status | Mitigation |
|------|--------|------------|
| Audit trail lost on restart | ACCEPTED | Deferred to EPIC-11 (durable sessions) |
| Preview may diverge from apply for complex plans | LOW | Golden tests validate preview-apply consistency |
| plan_to_changeset() may need extension for new action types | LOW | Current 5 types sufficient; extend in EPIC-09/10 if needed |

---

## 9. Open Items for Phase 4

1. **EPIC-09 (Design Operations)** — Domain-specific prompt templates for layout recommendations, revision workflows, takeoff calculations
2. **EPIC-10 (Construction Workflows)** — Grid/bay extraction, markup batch processing, regional convention handling
3. Both epics will extend the plan → preview → apply pipeline established in EPIC-08

---

## 10. Files Changed

### New Files
- `src/cad_dxf_agent/models/preview_schema.py`
- `src/cad_dxf_agent/models/apply_schema.py`
- `src/cad_dxf_agent/core/plan_converter.py`
- `src/cad_dxf_agent/core/preview_builder.py`
- `src/cad_dxf_agent/core/apply_pipeline.py`
- `tests/unit/test_preview_schema.py`
- `tests/unit/test_preview_builder.py`
- `tests/unit/test_apply_schema.py`
- `tests/unit/test_apply_pipeline.py`
- `tests/unit/test_plan_converter.py`
- `tests/unit/test_apply_anti_regression.py`
- `tests/unit/test_apply_golden.py`
- `tests/web/test_preview_apply_endpoints.py`

### Modified Files
- `web/backend/main.py` — `/api/v2/preview`, `/approve`, `/apply` endpoints
- `web/backend/session.py` — EPIC-08 audit trail fields
- `web/frontend/src/components/PreviewPanel.jsx` — structured preview cards with approve/reject
- `web/frontend/src/components/Workspace.jsx` — preview panel integration

---

## 11. Conclusion

EPIC-CAD-08 is complete. The Preview + Apply Workflow bridges EPIC-07's structured edit plans into a full user-facing pipeline: plans are previewed with per-action before/after state, approved by the user, then applied through the existing EditEngine. A session-scoped audit trail records all decisions. Phase 3 (Structured Editing) is now fully complete.

**Recommendation:** GO for Phase 4 (EPIC-09 Design Operations + EPIC-10 Construction Workflows).

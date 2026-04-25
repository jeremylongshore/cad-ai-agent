<!-- RETROFIT banner ------------------------------------------------------------
This Requirements Traceability Matrix was generated in RETROFIT mode from an
existing ~4,687-test codebase with 31 completed epics. Rows were harvested
from:
  - CLAUDE.md § Epic Registry (EPIC-CAD-01 .. EPIC-CAD-31)
  - 000-docs/004-AT-ADEC-* (safe-edits / save-as workflow)
  - 000-docs/005-AT-ADEC-llm-plans-not-dxf.md
  - 000-docs/006-AT-ADEC-* (deterministic revision notes)
  - 000-docs/036-AT-SPEC-response-contracts-taxonomy.md
No requirements were invented. Rows with uncovered or ambiguous test evidence
are flagged TODO in the "Retrofit queue" section at the end — engineer review.
-----------------------------------------------------------------------------
-->

# Requirements Traceability Matrix — cad-ai-agent

## Legend
- **MoSCoW**: MUST (non-negotiable), SHOULD (strongly expected), COULD (nice-to-have)
- **Source**: ADR = docs/ADR (`000-docs/00X-AT-ADEC-*`), EPIC = CLAUDE.md Epic Registry entry, SPEC = `000-docs/NNN-*-SPEC-*.md`

## Core contracts (ADR-derived MUSTs)

| REQ-ID  | MoSCoW | Source   | Description                                                                        | Test file(s)                                                                 |
|---------|--------|----------|------------------------------------------------------------------------------------|------------------------------------------------------------------------------|
| REQ-001 | MUST   | ADR-005  | LLM never emits raw DXF — only structured ChangeSet ops                            | tests/unit/test_apply_schema.py, test_changeset_snapshot.py                  |
| REQ-002 | MUST   | CLAUDE.md| Protected layers (TITLE/TITLEBLOCK/SEAL/REVISION) cannot be edited                 | tests/unit/test_applier.py::test_protected_layer_reject                      |
| REQ-003 | MUST   | ADR-004  | Original DXF never modified (save-as workflow)                                     | tests/unit/test_apply_pipeline.py, test_apply_anti_regression.py             |
| REQ-004 | MUST   | ADR-006  | Revision notes are deterministic, not LLM-generated                                | tests/unit/test_revision_notes*.py                                           |
| REQ-005 | MUST   | EPIC-13  | Two-axis intent classification (RequestClass × ObjectiveTag)                       | tests/unit/test_objective_classifier*.py + tests/eval/ scorecard             |

## Intent + strategy (EPIC-CAD-02, 13)

| REQ-ID  | MoSCoW | Source  | Description                                                                         | Test file(s)                                                                   |
|---------|--------|---------|-------------------------------------------------------------------------------------|--------------------------------------------------------------------------------|
| REQ-006 | MUST   | EPIC-02 | StrategyRegistry maps (RequestClass, ObjectiveTag) → StagePipelineDefinition        | tests/unit/test_strategy_registry.py                                           |
| REQ-007 | MUST   | EPIC-13 | StageExecutor runs ordered stages with StageGate checkpoints                        | tests/unit/test_stage_executor.py                                              |
| REQ-008 | SHOULD | EPIC-12 | Intent classification accuracy ≥ 96% on eval scorecard                              | tests/eval/ (mock + live modes)                                                |
| REQ-009 | MUST   | SPEC-036| Every response wraps in PlatformResponse (TaskFamily, ResponseType, RiskLevel)      | tests/unit/test_response_builder*.py, tests/web/test_platform_response_api.py  |

## Validation + apply (EPIC-CAD-07, 08)

| REQ-ID  | MoSCoW | Source  | Description                                                                         | Test file(s)                                                                   |
|---------|--------|---------|-------------------------------------------------------------------------------------|--------------------------------------------------------------------------------|
| REQ-010 | MUST   | EPIC-07 | Validators reject the entire changeset on any invalid/unsupported op                | tests/unit/test_validators.py                                                  |
| REQ-011 | MUST   | EPIC-08 | Preview produces human-readable change descriptions before apply                    | tests/unit/test_preview_builder.py                                             |
| REQ-012 | MUST   | EPIC-08 | EditEngine applies validated ops deterministically to a working copy                | tests/unit/test_edit_engine*.py, tests/integration/test_pipeline.py            |
| REQ-013 | MUST   | EPIC-17 | Supported entity types (LINE/LWPOLYLINE/TEXT/MTEXT/INSERT/CIRCLE/ARC) enforced      | tests/unit/test_dxf_reader.py, tests/unit/test_entity_creation*.py             |

## Domain capabilities (EPIC-CAD-19..29)

| REQ-ID  | MoSCoW | Source  | Description                                                                         | Test file(s)                                                                   |
|---------|--------|---------|-------------------------------------------------------------------------------------|--------------------------------------------------------------------------------|
| REQ-014 | MUST   | EPIC-19 | Drawing health report aggregates deterministic quality metrics                      | tests/unit/test_health_checker.py                                              |
| REQ-015 | MUST   | EPIC-20 | Batch-ops pipeline produces atomic all-or-nothing results                           | tests/unit/test_batch_ops*.py, tests/integration/test_batch_pipeline.py        |
| REQ-016 | MUST   | EPIC-21 | Compliance rules are deterministic (ADA/IBC/custom) — no LLM in the rule path       | tests/unit/test_compliance_rules*.py                                           |
| REQ-017 | SHOULD | EPIC-22 | Cross-drawing consistency checker flags title-block + layer mismatches              | tests/unit/test_consistency_checker.py (TODO — confirm file name)              |
| REQ-018 | MUST   | EPIC-23 | Automated takeoff engine extracts quantities by family + layer                      | tests/unit/test_takeoff_engine*.py                                             |
| REQ-019 | SHOULD | EPIC-24 | Plain-English summaries are structured (no freeform paragraph blobs)                | tests/unit/test_drawing_summarizer*.py                                         |
| REQ-020 | SHOULD | EPIC-25 | RFI generator produces traceable line-items with source entity refs                 | tests/unit/test_rfi_generator*.py                                              |
| REQ-021 | SHOULD | EPIC-26 | Revision summary report is derived from diff engine output, not LLM                 | tests/unit/test_revision_summary*.py                                           |
| REQ-022 | MUST   | EPIC-27 | Undo/redo preserves full edit history; named snapshots are restorable               | tests/unit/test_edit_history*.py, tests/integration/test_undo_redo.py          |

## Agent + API (EPIC-CAD-29, 31)

| REQ-ID  | MoSCoW | Source  | Description                                                                         | Test file(s)                                                                   |
|---------|--------|---------|-------------------------------------------------------------------------------------|--------------------------------------------------------------------------------|
| REQ-023 | MUST   | EPIC-29 | Agent loop bounded to max 10 turns                                                  | tests/unit/test_agent_provider.py, tests/integration/test_agent_loop.py        |
| REQ-024 | MUST   | EPIC-29 | ToolExecutor enforces protected-layer rules at dispatch (defense-in-depth with L2)  | tests/unit/test_tool_executor*.py                                              |
| REQ-025 | MUST   | EPIC-29 | V1 API: 60 req/min per IP rate limit (retrofit fix during EPIC-31 review)           | tests/web/test_rate_limit.py (TODO — confirm file name)                        |
| REQ-026 | COULD  | EPIC-31 | CAD_AGENT_BACKEND feature flag routes between cloud_run and agent_engine            | tests/unit/test_settings_agent_backend.py (TODO — wired config, not routed)    |

## Persistence + multi-tenancy (EPIC-CAD-15, 30)

| REQ-ID  | MoSCoW | Source  | Description                                                                         | Test file(s)                                                                   |
|---------|--------|---------|-------------------------------------------------------------------------------------|--------------------------------------------------------------------------------|
| REQ-027 | MUST   | EPIC-30 | Tenant + UserProfile auto-provisioned on first login via Firestore                  | tests/web/test_auth_provisioning.py                                            |
| REQ-028 | MUST   | EPIC-30 | WorkProgress auto-saves on apply; restores on document load with `restored` flag    | tests/web/test_work_progress*.py                                               |
| REQ-029 | MUST   | EPIC-30 | GCS path layout documents/{tenant_id}/{user_id}/{doc_id}/ (with legacy fallback)    | tests/unit/test_document_store*.py, tests/web/test_document_api.py             |
| REQ-030 | MUST   | EPIC-30 | SessionManager.get_by_id enforces ownership (post-review fix)                       | tests/web/test_session_ownership.py (TODO — confirm file name)                 |
| REQ-031 | SHOULD | EPIC-15 | Session TTL 2h for ephemeral uploads                                                | tests/web/test_session_lifecycle.py                                            |

## Retrofit queue (uncovered MUSTs — engineer review)

These rows emerged during retrofit harvest but either have no obvious test
evidence in the tree, or the evidence is ambiguous. Each needs engineer
attention before the next audit.

| REQ-ID  | MoSCoW | Source   | Description                                                                         | TODO (engineer guidance)                                                   |
|---------|--------|----------|-------------------------------------------------------------------------------------|----------------------------------------------------------------------------|
| REQ-100 | MUST   | EPIC-30  | Tenant isolation: user A cannot read documents under tenant B via any API path      | Add cross-tenant negative test to tests/web/                               |
| REQ-101 | MUST   | EPIC-31  | Phase-2 deferred: tools-as-Cloud-Run-endpoints (HTTP-Client FunctionTool pattern)   | Defer until Agent Engine adoption; tracking note only                      |
| REQ-102 | MUST   | CLAUDE.md| OTel span attributes exclude full file paths + drawing text (PII/cardinality)       | Add span-attribute assertion test in tests/unit/test_otel_guards.py        |
| REQ-103 | MUST   | CLAUDE.md| OTel metrics cardinality bounded (tool_name, request_class only — no user_id)       | Add cardinality assertion on cad.tool.success / cad.tool.failure labels    |
| REQ-104 | MUST   | EPIC-30  | Firestore allowlist failure modes (network down, doc missing) fail closed           | Add tests/web/test_allowlist_failure_modes.py                              |
| REQ-105 | MUST   | EPIC-29  | Rate limit (60 req/min per IP) returns 429 with Retry-After; no silent drop         | Confirm test file name for REQ-025; add Retry-After assertion if missing   |
| REQ-106 | SHOULD | EPIC-22  | Consistency checker test file location unconfirmed                                  | Locate or create tests/unit/test_consistency_checker.py                    |
| REQ-107 | MUST   | ADR-005  | Negative test: malformed LLM JSON → whole changeset rejected, no partial apply      | Add malformed-output fuzz to tests/property/                               |
| REQ-108 | MUST   | EPIC-30  | Cache invalidation: profile (5min) + workspace (10min) TTLs honored under churn     | Add tests/web/test_cache_ttl.py                                            |
| REQ-109 | SHOULD | EPIC-27  | Snapshot GC / max-snapshot-count policy documented + enforced                       | Clarify policy in a doc, add test if enforced                              |

## Notes

- Hard test-file names above were harvested from the known test tree layout.
  Where a name is marked `(TODO — confirm file name)`, the engineer should
  run `rg -l <keyword> tests/` and update this RTM in the same commit as any
  rename.
- This matrix is consumed by the audit-harness RTM lint on next audit; do not
  reflow columns without re-running `audit-harness rtm --check`.

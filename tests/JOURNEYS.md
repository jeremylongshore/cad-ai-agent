<!-- RETROFIT banner ------------------------------------------------------------
Journeys derived from ADR-004 / ADR-005 / ADR-006 + EPIC Registry (CLAUDE.md).
Each step maps to a taxonomy layer (L1-L7) so the audit-harness can verify
coverage per journey. Actor names reference archetypes in tests/PERSONAS.md.
Requirement IDs reference tests/RTM.md.
-----------------------------------------------------------------------------
-->

# Journeys — cad-ai-agent

## JOURNEY-1 — Edit pipeline happy path
**Actor**: Design Author
**Pre-conditions**: user authenticated; DXF uploaded; session active; prompt well-formed.

**Steps**
1. Prompt submitted to API — **L6 e2e** (tests/e2e/)
2. ObjectiveClassifier produces (RequestClass=edit, ObjectiveTag=…) — **L3 unit**
3. StrategyRegistry selects the edit StagePipelineDefinition — **L3 unit**
4. Planner (Gemini or Agent) emits a structured ChangeSet — **L3 unit / L4 integration**
5. Validator checks ops against RuleConfig — **L3 unit**
6. Preview renders human-readable change descriptions — **L3 unit**
7. EditEngine applies ops to a working copy — **L4 integration**
8. DXFWriter saves to a new path (original untouched) — **L4 integration**
9. RevisionNotes appended deterministically on AI_REV_NOTES layer — **L3 unit**

**Expected outcome**: save-as DXF with applied ops + deterministic revision notes; original file unchanged.

**Linked MUST REQ-IDs**: REQ-001, REQ-003, REQ-004, REQ-010, REQ-011, REQ-012, REQ-013
**Test coverage**: tests/integration/test_pipeline.py, tests/unit/test_apply_pipeline.py, tests/smoke/, scripts/smoke_test.py

---

## JOURNEY-2 — Analysis pipeline (no edits)
**Actor**: Reviewer / Compliance Officer, Estimator / Coordinator, Field / Operator
**Pre-conditions**: drawing loaded; prompt is an analyze/query/compare/generate class.

**Steps**
1. Prompt submitted — **L6 e2e / L4 web**
2. ObjectiveClassifier produces (RequestClass=analyze|query|generate, ObjectiveTag=…) — **L3 unit**
3. StrategyRegistry selects a non-edit StagePipelineDefinition — **L3 unit**
4. StageHandlers run deterministic extractors (compliance / health / takeoff / summary / rfi) — **L3 unit + L4 integration**
5. ResponseBuilder wraps outputs in PlatformResponse (TaskFamily, ResponseType, RiskLevel, AuditMetadata) — **L3 unit**

**Expected outcome**: structured analysis payload; no DXF mutation; findings cite entity refs.

**Linked MUST REQ-IDs**: REQ-005, REQ-007, REQ-009, REQ-014, REQ-016, REQ-018
**Test coverage**: tests/unit/test_compliance_rules*.py, tests/unit/test_health_checker.py, tests/unit/test_takeoff_engine*.py, tests/unit/test_response_builder*.py, tests/web/test_platform_response_api.py

---

## JOURNEY-3 — Agent-mode tool loop
**Actor**: Design Author (complex multi-step requests)
**Pre-conditions**: CAD_LLM_PROVIDER=gemini; AgentProvider enabled; prompt complex enough to need tool use.

**Steps**
1. AgentProvider sends prompt + drawing context + tool definitions — **L4 integration**
2. Gemini returns tool calls — **L4 integration (ScriptedAgentProvider replays)**
3. ToolExecutor dispatches, enforcing protected-layer rules — **L3 unit**
4. Results feed back; loop continues up to **10 turns max** — **L3 unit (bound assertion)**
5. Final ChangeSet extracted from accumulated tool calls — **L3 unit**
6. ChangeSet validated + applied via JOURNEY-1 steps 5-9 — **L4 integration**

**Expected outcome**: bounded agent loop produces a validated ChangeSet; runaway is impossible.

**Linked MUST REQ-IDs**: REQ-001, REQ-002, REQ-023, REQ-024
**Test coverage**: tests/integration/test_agent_loop.py, tests/unit/test_agent_provider.py, tests/unit/test_tool_executor*.py, tests/helpers/scripted_provider.py, tests/fixtures/trajectories/*.json

---

## JOURNEY-4 — Revision comparison CLI
**Actor**: Estimator / Coordinator
**Pre-conditions**: two DXF revisions on disk (master + revision); `cad-revision` CLI installed.

**Steps**
1. `cad-revision diff master.dxf revision.dxf --output-dir ./out` — **L6 e2e**
2. Alignment stage matches entities across revisions — **L3 unit**
3. Change classifier tags each delta (add/remove/modify/move) — **L3 unit**
4. `cad-revision bundle … --approve-all` packages the diff bundle — **L4 integration**
5. Overlay artifact produced for stakeholder review — **L4 integration**

**Expected outcome**: deterministic diff bundle + overlay; no LLM in the diff path.

**Linked MUST REQ-IDs**: REQ-021 (SHOULD), and supports REQ-005 classification consistency.
**Test coverage**: tests/unit/test_compare*.py, tests/e2e/test_revision_cli.py (TODO — confirm file name), `src/cad_dxf_agent/cli/`

---

## JOURNEY-5 — Web session lifecycle
**Actor**: Field / Operator, Design Author (web entry)
**Pre-conditions**: Firebase sign-in flow active; backend deployed; frontend live.

**Steps**
1. Upload DXF via web frontend — **L6 e2e (Playwright)**
2. Firebase token validated server-side — **L4 web**
3. Session scaffolded under `/tmp/cad-sessions/{id}/` with 2h TTL — **L4 web**
4. WorkProgress auto-saves on each apply — **L4 web**
5. Reconnect / document load returns payload with `restored: true` when state exists — **L4 web**
6. Session expires after 2h; cleanup removes scratch dir — **L4 web**

**Expected outcome**: user can drop off and return within 2h; work is never silently lost inside the window.

**Linked MUST REQ-IDs**: REQ-028, REQ-031 (SHOULD)
**Test coverage**: tests/web/test_session_lifecycle.py, tests/web/test_work_progress*.py, web/frontend/ Playwright scripts

---

## JOURNEY-6 — Protected-layer rejection
**Actor**: Design Author (any who happens to target a protected layer)
**Pre-conditions**: prompt explicitly or implicitly targets TITLE / TITLEBLOCK / SEAL / REVISION.

**Steps**
1. Prompt submitted — **L6 e2e**
2. Planner / AgentProvider may propose an op on a protected layer — **L3 unit (allowed to propose)**
3. Validator rejects the whole changeset — **L3 unit**
4. ToolExecutor independently rejects any tool call on a protected layer (defense-in-depth) — **L3 unit**
5. Structured error returned; no partial apply; original file untouched — **L4 integration**

**Expected outcome**: two independent enforcement points both refuse; error payload is structured (PlatformResponse with RiskLevel).

**Linked MUST REQ-IDs**: REQ-002, REQ-003, REQ-010, REQ-024
**Test coverage**: tests/unit/test_applier.py::test_protected_layer_reject, tests/unit/test_tool_executor*.py, tests/fixtures/trajectories/protected_layer_reject.json

---

## JOURNEY-7 — Document persistence (EPIC-15 + EPIC-30)
**Actor**: Platform Admin / Tenant Owner (provisioning) + Design Author (saving)
**Pre-conditions**: Firestore available; GCS bucket reachable; first-login or returning user.

**Steps**
1. First login — Tenant + UserProfile auto-provisioned via Firestore — **L4 web**
2. User uploads a DXF and performs edits via JOURNEY-1 — **L4 web / L6 e2e**
3. Document saved to GCS path `documents/{tenant_id}/{user_id}/{doc_id}/` — **L3 unit + L4 web**
4. Legacy path fallback handled for pre-EPIC-30 documents — **L3 unit**
5. Document list returns `has_work_progress` flag per document — **L4 web**
6. Load document restores in-progress state (`restored: true`) — **L4 web**
7. Profile cache (5 min TTL) + workspace cache (10 min TTL) honored — **L3 unit (TODO — REQ-108)**

**Expected outcome**: a returning user sees their drawings + in-flight work; a different tenant never sees them.

**Linked MUST REQ-IDs**: REQ-027, REQ-028, REQ-029, REQ-030
Retrofit queue: REQ-100 (cross-tenant isolation negative test), REQ-104 (allowlist failure modes), REQ-108 (cache TTL).
**Test coverage**: tests/web/test_auth_provisioning.py, tests/web/test_document_api.py, tests/unit/test_document_store*.py

---

## Cross-reference
- Personas: `tests/PERSONAS.md`
- Requirements: `tests/RTM.md`
- ADRs: `000-docs/004-AT-ADEC-*`, `000-docs/005-AT-ADEC-llm-plans-not-dxf.md`, `000-docs/006-AT-ADEC-*`
- Response taxonomy: `000-docs/036-AT-SPEC-response-contracts-taxonomy.md`

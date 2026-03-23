# 074-AT-ARCH — ADK Agent Engine Architecture Decision Record

**Status:** Accepted
**Epic:** EPIC-CAD-31 (System Design Pattern Adoption)
**Date:** 2026-03-22
**Author:** Jeremy Longshore + Claude

---

## Context

After completing Phase 9 (User Accounts & Workspaces) and the Pascal Editor PR #127 (cached EntityIndex + tool narrowing), a cross-project research sweep identified system design patterns worth adopting from three sources:

1. **Google ADK** (v1.27.2) — official Agent Development Kit with managed runtime, auto-schema tools, session management, and Agent Engine deployment
2. **bobs-brain** — Jeremy's production ADK reference implementation, featured in Google's agent-starter-pack community showcase (PR #580, merged) and vertex-ai-samples inline deployment tutorial (PR #4393, merged)
3. **External projects** — Shapely (geometry), OPA/Cedar (rules), Aider (architect/editor), Great Expectations (composable validation)

The cad-dxf-agent currently runs a custom tool-use loop (`AgentProvider`) with 758 lines of hand-written JSON Schema for 20+ tool definitions. Sessions are managed by a custom `SessionStore` ABC. Geometry computations are hand-rolled. Compliance rules are hardcoded Python.

## Decision

Adopt a phased migration toward ADK Agent Engine as the LLM runtime, while keeping Cloud Run as the REST gateway for file I/O, auth, and document CRUD.

### Architecture: Gateway + Agent Engine (R2/R3 Pattern)

```
Client → Cloud Run (FastAPI gateway)  → Agent Engine (ADK runtime)
              ↓                              ↓
     REST endpoints (~29)            Agent loop (plan/preview/apply)
     File I/O, auth, CRUD          LLM tool-use, sessions, memory
     Documents, renders             Managed scaling + observability
```

### What Stays on Cloud Run
- File upload/download, DXF processing, rendering
- Firebase auth validation, tenant/user provisioning
- Document library (GCS-backed), session CRUD
- Health checks, static serving, CORS

### What Moves to Agent Engine
- The agent tool-use loop (currently `AgentProvider._get_model()` + while loop)
- Tool definitions (as typed Python functions, not JSON Schema dicts)
- Session state for agent conversations (via `VertexAiSessionService`)
- Cross-session memory (via `VertexAiMemoryBankService`)

### Why Agent Engine Over Cloud Run for the Agent Loop

| Concern | Cloud Run (current) | Agent Engine (target) |
|---------|--------------------|-----------------------|
| Session management | Custom `SessionStore` ABC | Built-in, managed |
| Observability | Custom OTel bootstrap | Cloud Trace + Logging built-in |
| Scaling | Configured per-container | Auto-managed |
| Memory/learning | None | `VertexAiMemoryBankService` |
| Tool definition | 758 LOC hand-written JSON | Type-hint auto-generation |
| Agent loop | Custom while loop (10 turns) | Managed `Runner` |
| Cold start | vertexai.init() in hot path | Pre-warmed by platform |

### What We're NOT Doing
- **Not replacing Cloud Run** — it stays as the REST gateway. This follows bobs-brain R3: "Gateway = pure HTTP proxy, no Runner."
- **Not adopting A2A protocol** — single-agent architecture is sufficient for CAD workflows. Multi-agent orchestration adds complexity without clear benefit here.
- **Not breaking the existing pipeline** — all changes are additive. Existing dict-based tools remain canonical until ADK migration is complete and validated.

## Migration Phases

### Phase 1: ADK Foundation (Week 1-2)
1. **Typed tool functions** — Add Python functions with type hints alongside existing JSON Schema dicts. Validate auto-generated schemas match hand-written ones. (5 query tools first, then edit tools.)
2. **Drift detection in CI** — `scripts/ci/check_nodrift.sh` runs FIRST in CI, blocks on violation. Catches framework imports, raw DXF mutation outside allowed files, protected layer enforcement gaps.
3. **Lazy-loading refinement** — Extract `_ensure_vertexai()` method, clean up `_get_model()`. Extends PR #127 direction.

### Phase 2: Agent Engine Deployment (Week 2-3)
1. **Session alignment** — Align `SessionStore` method signatures toward ADK `SessionService` interface (`app_name`, `append_event`). Production: swap to `VertexAiSessionService`.
2. **ADK agent module** — `src/cad_dxf_agent/adk/` with `Agent()` definition using typed tool functions. Reuses all existing pipeline code.
3. **Agent Engine deployment** — GitHub Actions workflow, CI-only (R4 pattern). Cloud Run proxies agent requests.

### Phase 3: Geometry + Rules (Week 3-4, parallel)
1. **Shapely 2.0** — Replace `_shoelace_area`, `_polygon_perimeter`, `_polygon_centroid`, `_aspect_ratio` with Shapely `Polygon`. Enables arc handling and polygon intersection.
2. **Externalized compliance rules** — YAML rule specs alongside Python functions. Firms can customize without code changes. Python stays canonical.

### Phase 4: Design Patterns
1. **Composable validation suites** (Great Expectations pattern) — Extend `ComplianceProfile` to compose from atomic rules.
2. **Architect/editor separation** (Aider pattern) — Design principle for future planner improvements.

## Dependency Chain

```
1A (typed tools) → 2B (ADK agent module) → 2C (deploy to Agent Engine)
                 → 2A (session alignment) ↗
1B (drift detection) — independent
1C (lazy loading) — independent
3A (Shapely) — independent, parallel with Phase 2
3B (YAML rules) — independent, after 3A
```

## Risks and Mitigations

| Risk | Severity | Mitigation |
|------|----------|------------|
| Agent Engine cold start latency | Medium | Benchmark before/after; keep Cloud Run fallback |
| ADK version churn | Low | Pin version like bobs-brain (`>=1.18.0,<1.19.0`) |
| Dual tool definition maintenance burden | Low | Schema-match tests enforce sync; sunset dicts after validation |
| Session migration data loss | Medium | Migration script + parallel run period |
| Shapely dependency size | Low | Core dep (~3MB wheel); zone detection is a core feature, conditional imports not worth the complexity |

## Verification

Per-change gates:
- `make check` (lint + format + typecheck + tests + smoke)
- `make scorecard` — no classification regression
- Coverage stays above 65%

Pattern-specific:
- Drift detection: CI fails when forbidden import is added (test with intentional violation)
- Tool functions: auto-generated schemas match hand-written dicts (test)
- ADK agent: `adk run` starts locally, tool calls execute against test DXF
- Agent Engine deploy: health check returns 200
- Shapely: zone detection tests produce identical results
- YAML rules: produce identical `ComplianceReport` as Python functions

## References

- [Google ADK docs](https://google.github.io/adk-docs/)
- [google/adk-python](https://github.com/google/adk-python) (Apache 2.0)
- [bobs-brain](https://github.com/GoogleCloudPlatform/agent-starter-pack/pull/580) — community showcase
- [Agent Engine deployment tutorial](https://github.com/GoogleCloudPlatform/vertex-ai-samples/pull/4393)
- [Shapely 2.0](https://github.com/shapely/shapely) (BSD)
- [OPA](https://openpolicyagent.org/) / [Cedar](https://docs.cedarpolicy.com/)
- [Aider](https://aider.chat/) (Apache 2.0)
- [Great Expectations](https://greatexpectations.io/) (Apache 2.0)

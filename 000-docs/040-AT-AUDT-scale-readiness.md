# 040 — Scale Readiness Assessment

**Status:** Proposed
**Date:** 2026-03-05
**Depends on:** 034-AT-AUDT (capability audit), 035-AT-ARCH (target architecture)

---

## 1. Current State Risks

### Ephemeral Session Storage

Sessions live in `/tmp/cad-sessions/{id}/` with 2-hour expiration. All state is
in-memory or on local disk. A Cloud Run instance restart loses everything.

**Evidence:**
- `web/backend/main.py` — session dict in-memory, files in `/tmp`
- No database, no object storage, no Redis

**Impact:** Users lose work on instance restart or cold start. No multi-instance
support. Cannot resume sessions across devices.

**Migration priority:** P1 — required before real user workloads.

### 500-Entity Context Cap

`core/semantic_model.py` caps the JSON context at 500 entities. Drawings with
more entities silently drop information, leading to missing entities in planner
context and potentially wrong edits.

**Impact:** Large structural drawings (1000+ entities) produce incomplete plans.
No warning to the user.

**Migration priority:** P1 — token-budget-aware context builder needed (EPIC-03).

### In-Memory Conversation History

Conversation history for multi-turn interactions is stored in a Python list on
the session object. Lost on restart.

**Impact:** Multi-step workflows (plan → review → apply) break on instance
recycle. Context lost between sessions.

**Migration priority:** P2 — acceptable for single-request workflows, blocks
durable multi-step flows.

### Single-Instance Architecture

No load balancer awareness. No shared state. No background job queue.

**Impact:** Cannot horizontally scale. Long-running comparisons block the
request thread.

**Migration priority:** P3 — acceptable at current user volume.

---

## 2. Scale Bottleneck Inventory

| Bottleneck | Component | Current Limit | Symptom |
|-----------|-----------|---------------|---------|
| Entity context cap | `semantic_model.py` | 500 entities | Silent information loss |
| Session storage | `/tmp/` filesystem | Instance lifetime | Lost sessions on restart |
| Conversation history | In-memory list | Instance lifetime | Lost context on restart |
| DXF rendering | matplotlib in-process | ~5s per render | Blocks request thread |
| Comparison pipeline | Single-threaded | ~10s for large drawings | Blocks request thread |
| File conversion (ODA) | Subprocess call | External binary required | Fails if ODA not installed |
| Gemini API latency | Network call | 2-10s per planner call | User-visible delay |

---

## 3. Durable State Migration Path

### Phase A: Metadata Separation (EPIC-11.2)

Separate session metadata from blob storage:

```
Current:  /tmp/cad-sessions/{id}/master.dxf
          /tmp/cad-sessions/{id}/edited.dxf
          In-memory session dict

Target:   Cloud Storage bucket for DXF/PDF blobs
          Firestore or Cloud SQL for session metadata
          Session dict serializable to/from storage
```

### Phase B: Background Execution (EPIC-11.3+)

Move long-running operations off the request thread:

```
Current:  POST /api/plan → synchronous planner call → response

Target:   POST /api/plan → enqueue job → return job ID
          GET /api/job/{id} → poll for result
          WebSocket notification when complete (stretch)
```

### Phase C: Multi-Instance (post-EPIC-12)

Enable horizontal scaling:

```
Current:  Single Cloud Run instance, all state local

Target:   Stateless Cloud Run instances
          Shared storage (GCS + Firestore)
          Session affinity optional, not required
```

---

## 4. Storage Evolution Summary

| Layer | Current | Phase A | Phase B | Phase C |
|-------|---------|---------|---------|---------|
| Drawing files | `/tmp/` | GCS bucket | GCS bucket | GCS bucket |
| Session metadata | In-memory dict | Firestore | Firestore | Firestore |
| Conversation history | In-memory list | Firestore | Firestore | Firestore |
| Job queue | N/A | N/A | Cloud Tasks | Cloud Tasks |
| Render cache | Per-request | Per-request | GCS + CDN | GCS + CDN |

---

## 5. Observability Gaps

| Gap | Current State | Target |
|-----|--------------|--------|
| Request timing | OTEL spans (optional) | Always-on, per-pipeline-stage |
| Error categorization | Generic HTTPException | Typed error taxonomy |
| Task family metrics | Not tracked | Counter per TaskFamily |
| Planner latency | Not tracked | Histogram by provider |
| Session lifecycle | Not tracked | Create/expire/resume events |
| Confidence distribution | Not tracked | Histogram per task family |

---

## Related Documents

- 034-AT-AUDT — Capability audit (failure points in Section 3)
- 035-AT-ARCH — Target architecture (service boundaries in Section 6)
- 038-PM-PLAN — Roadmap (EPIC-11 covers scale readiness implementation)

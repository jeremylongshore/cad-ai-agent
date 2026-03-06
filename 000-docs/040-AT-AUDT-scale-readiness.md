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

## 3. What Breaks First

Explicit failure cascade as concurrent load increases:

| Load Level | What Breaks | Why |
|------------|------------|-----|
| **5 concurrent users** | matplotlib rendering contention | matplotlib is not thread-safe; concurrent renders corrupt state or segfault. Memory pressure on 1Gi instance with multiple DXF loads + renders in flight. |
| **10 concurrent users** | Session dict lock contention, `/tmp/` fills | In-memory session dict has no locking; concurrent writes cause race conditions. Uploaded DXF files accumulate in `/tmp/` with no cleanup under load. |
| **50+ concurrent users** | Gemini API rate limits, stateless autoscaling | Vertex AI quota exhausted. Cloud Run autoscaling spawns new instances but all session state is lost — users on recycled instances get 404s. |
| **Large files (>50MB DXF)** | OOM kill on 1Gi instance | `ezdxf` loads the full document into memory; combined with semantic model construction and matplotlib rendering, a single large file exceeds the memory limit. |
| **Malicious upload** | Instance crash, no recovery | No `MAX_UPLOAD_SIZE` validation exists on the upload endpoint. A single oversized upload can OOM the instance and kill all active sessions. |

### Upload Size Limit (Missing)

The `/api/upload` endpoint in `web/backend/main.py` accepts files without any size
validation. There is no `MAX_UPLOAD_SIZE` setting, no `Content-Length` check, and
no streaming size guard. A single multi-hundred-megabyte upload will be buffered
entirely into memory before any processing begins, likely triggering an OOM kill.

**Recommendation:** Add a `MAX_UPLOAD_SIZE` setting (default 25MB), enforce via
`Content-Length` header check and streaming byte-count guard. Reject oversized
uploads with 413 before buffering.

---

## 4. Cost Analysis

Rough monthly cost estimates by scale tier (USD, as of 2026-03):

### Per-Request Cost Breakdown

- **Gemini API:** ~2,000 input tokens + ~500 output tokens per planner call.
  At Gemini 1.5 Pro pricing (~$1.25/1M input, ~$5.00/1M output): ~$0.005/request.
- **Cloud Run:** ~0.5 vCPU-seconds per request (CPU-on-request billing).
- **GCS:** ~$0.02/GB/month storage, $0.004/10K reads.
- **Firestore:** $0.06/100K reads, $0.18/100K writes.

### Monthly Projections

| Resource | 10 DAU | 100 DAU | 1,000 DAU |
|----------|--------|---------|-----------|
| **Cloud Run** (CPU-on-request) | ~$2 | ~$15 | ~$120 |
| **Cloud Run** (always-on, 1 min-instance) | ~$30 | ~$30 | ~$60+ |
| **Gemini API** (~5 requests/user/day) | ~$0.75 | ~$7.50 | ~$75 |
| **GCS** (~3 files/session, 7-day retention) | ~$0.10 | ~$1 | ~$8 |
| **Firestore** (~20 ops/session) | ~$0.01 | ~$0.10 | ~$1 |
| **Firebase Auth** | Free | Free | Free |
| **Firebase Hosting** (CDN) | Free | Free | ~$5 |
| **Estimated total** | **~$3–$33** | **~$24–$54** | **~$209–$269** |

**Current monthly spend:** ~$0 (no persistent infrastructure; Cloud Run scales to
zero, no min-instances configured).

**Key cost driver:** Gemini API dominates at scale. Cloud Run is significant only
if `--min-instances` is set for cold-start mitigation.

---

## 5. Latency Analysis

### End-to-End Request Breakdown

| Stage | Typical Latency | Notes |
|-------|----------------|-------|
| File upload (network) | ~1s | Depends on file size and client bandwidth |
| DXF load (`ezdxf`) | ~0.5s | Scales with entity count |
| Semantic model build | ~0.2s | 500-entity cap keeps this bounded |
| **LLM planner call** | **2–10s** | **Dominates total latency** |
| Validation | <0.1s | Rule checks against `RuleConfig` |
| DXF rendering (matplotlib) | ~5s | Not thread-safe; blocks request thread |
| **Total (warm instance)** | **~8–16s** | |

### Worst-Case Latency

- **Cold start:** Cloud Run cold start adds ~3–5s. No `--min-instances` is
  configured, so the first request after idle always pays this cost.
- **Planner timeout:** `PlannerProvider` has a 60s timeout with retry. A single
  retry doubles the planner stage to ~120s. Worst-case user-facing latency for a
  plan request: **~125s** (cold start + retry + render).
- **Comparison pipeline:** ~10s for large drawings, additive to plan latency if
  triggered in the same request flow.

### Dominant Stage

The LLM planner call (2–10s typical, up to 60s timeout) is the single largest
contributor to user-visible latency. All other pipeline stages combined total
~6–7s. Optimization efforts should focus on planner response time, streaming
partial results, or moving the planner call to a background job.

---

## 6. Background Job Candidates

Operations that should move off the request thread (Phase B):

| # | Operation | Typical Duration | Why It Must Be Async |
|---|-----------|-----------------|---------------------|
| 1 | **Planner/LLM calls** | 2–10s (up to 60s timeout) | Dominates latency; retry logic can double duration. Blocks request thread for the entire call. |
| 2 | **DXF rendering** (matplotlib) | ~5s | matplotlib is not thread-safe. Concurrent renders on the same process corrupt state. Must be serialized or run in subprocess. |
| 3 | **Comparison pipeline** | ~10s for large drawings | Entity alignment + matching + changelog generation is CPU-bound. Blocks all other requests on a 1-CPU instance. |
| 4 | **ODA file conversion** | Unbounded (subprocess) | Shells out to external `ODAFileConverter` binary. No timeout configured. Can hang indefinitely on malformed input. |
| 5 | **Bundle export** | 2–5s | File I/O intensive: writes DXF + overlay + changelog + metadata. Competes with upload I/O on the same `/tmp/` volume. |
| 6 | **PDF-to-DXF conversion** | Scales with page count | PyMuPDF extraction is CPU-bound. A 50-page PDF can take 30s+. No page-count limit enforced. |

**Recommended pattern:** `POST` returns a job ID immediately. Client polls
`GET /api/job/{id}` or receives a WebSocket notification on completion. Cloud
Tasks or an in-process queue (for single-instance) handles dispatch.

---

## 7. Cloud Run Configuration Analysis

### Current Configuration

```
--cpu=1 --memory=1Gi --concurrency=80 --min-instances=0 --timeout=300
```

(Concurrency 80 is the Cloud Run default when not explicitly set.)

### Problems

- **80 concurrent requests on 1 CPU:** Every pipeline stage (DXF load, semantic
  model, planner call, validation, rendering) is synchronous and CPU-bound.
  With 80 concurrent requests on a single vCPU, most requests queue behind
  active work. Effective throughput is ~1–2 requests at a time.
- **1Gi memory with no upload limit:** A few concurrent large-file uploads can
  exhaust memory before any processing begins.
- **No min-instances:** Every idle period triggers a cold start (~3–5s) on the
  next request. For a tool users expect to be responsive, this is a poor
  experience.
- **matplotlib contention:** Even with concurrency=1, matplotlib global state
  can corrupt across sequential requests if prior cleanup is incomplete.

### Recommended Production Configuration

```
--cpu=2 --memory=2Gi --concurrency=4 --min-instances=1 --timeout=300
```

| Setting | Current | Recommended | Rationale |
|---------|---------|-------------|-----------|
| `--cpu` | 1 | 2 | CPU-bound pipeline needs headroom for concurrent ops |
| `--memory` | 1Gi | 2Gi | Large DXF files + matplotlib rendering exceed 1Gi |
| `--concurrency` | 80 (default) | 4 | Match actual throughput capacity; prevent queueing |
| `--min-instances` | 0 | 1 | Eliminate cold-start latency for active users |
| `--timeout` | 300 | 300 | Keep as-is; covers planner retry worst case |

**Cost impact:** `--min-instances=1` with `--cpu=2` adds ~$30–$50/month in
always-on cost. Justified once there are regular users.

---

## 8. Durable State Migration Path

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

## 9. Storage Evolution Summary

| Layer | Current | Phase A | Phase B | Phase C |
|-------|---------|---------|---------|---------|
| Drawing files | `/tmp/` | GCS bucket | GCS bucket | GCS bucket |
| Session metadata | In-memory dict | Firestore | Firestore | Firestore |
| Conversation history | In-memory list | Firestore | Firestore | Firestore |
| Job queue | N/A | N/A | Cloud Tasks | Cloud Tasks |
| Render cache | Per-request | Per-request | GCS + CDN | GCS + CDN |

---

## 10. Observability Gaps

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

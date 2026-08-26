<!-- RETROFIT banner ------------------------------------------------------------
Canonical persona inventory lives at 000-docs/072-TQ-TEST-realworld-user-profiles.md
(25 real-world profiles). This file collapses those 25 into 5 archetypes so
the RTM (tests/RTM.md) can cross-reference persona → REQ-ID without having to
fan out to every profile variant. When adding a new REQ-ID, link it to one of
the 5 archetypes below; add a detailed profile to 072 only if no existing
profile covers the case.
-----------------------------------------------------------------------------
-->

# Personas — cad-ai-agent (5 archetypes)

## 1. Design Author
**Role**: Structural engineer, architectural engineer, drafter, junior designer.
**Background**: Uses AutoCAD / Revit / similar authoring tool daily. Comfortable
with DXF exports; wants assistance editing, not replacement. Sensitive to
liability — refuses any workflow that modifies the original file.

**Key goals**
- Apply bulk edits via natural-language prompts without hand-editing each entity
- Create new primitives (lines, polylines, circles, arcs, text) with the same pipeline
- Trust that protected layers + title blocks are untouched
- See a preview before commit, with the ability to reject

**Key flows**
- Edit pipeline happy path (JOURNEY-1)
- Agent-mode tool loop for multi-step requests (JOURNEY-3)
- Protected-layer rejection (JOURNEY-6)

**Linked MUST REQ-IDs**
REQ-001, REQ-002, REQ-003, REQ-004, REQ-010, REQ-011, REQ-012, REQ-013,
REQ-022, REQ-023, REQ-024

**Applicable capabilities**: edit, creation, undo/redo, snapshots

---

## 2. Reviewer / Compliance Officer
**Role**: Plan reviewer, code official, AHJ reviewer, QA/QC lead.
**Background**: Read-only workflow. Needs deterministic, auditable findings
that cite the exact entity refs. Cannot accept "LLM-written" compliance
verdicts — rule path must be pure code.

**Key goals**
- Run compliance checks (ADA, IBC, custom firm rules) and get findings
- Generate RFIs traceable back to source entities
- Never see a compliance verdict that came from the LLM

**Key flows**
- Analysis pipeline (JOURNEY-2)
- Compliance-only run with RFI output

**Linked MUST REQ-IDs**
REQ-005, REQ-007, REQ-009, REQ-016, REQ-020 (SHOULD)

**Applicable capabilities**: compliance, rfi, health, summary (read-only)

---

## 3. Estimator / Coordinator
**Role**: GC estimator, MEP coordinator, project engineer.
**Background**: Works across revisions. Needs quantity takeoffs, revision
diffs, and plain-English summaries to move up the decision chain.

**Key goals**
- Extract quantities by family / layer (windows, doors, fixtures, steel, etc.)
- Compare drawing revisions + produce a bundle for stakeholders
- Summarize a drawing for a non-technical audience

**Key flows**
- Revision comparison CLI (JOURNEY-4)
- Takeoff + summary analysis (JOURNEY-2 variant)

**Linked MUST REQ-IDs**
REQ-005, REQ-009, REQ-015, REQ-018, REQ-019 (SHOULD), REQ-021 (SHOULD)

**Applicable capabilities**: takeoff, summary, revision-compare, batch-ops

---

## 4. Field / Operator
**Role**: Superintendent, fabricator, field engineer, shop lead.
**Background**: Works off PDFs and printed plans; occasionally needs the
digital drawing to answer a targeted question. Wants short, structured
answers — not long narratives.

**Key goals**
- Ask a question about a specific area/zone and get a grounded answer
- Pull a short, structured summary before a pre-task brief
- Open a drawing on an older laptop via the web app without install

**Key flows**
- Analysis pipeline — region Q&A / summary (JOURNEY-2)
- Web session lifecycle (JOURNEY-5)

**Linked MUST REQ-IDs**
REQ-005, REQ-009, REQ-019 (SHOULD), REQ-031 (SHOULD)

**Applicable capabilities**: summary, region-qna, health

---

## 5. Platform Admin / Tenant Owner
**Role**: Firm IT owner, platform admin, tenant owner (EPIC-CAD-30 persona).
**Background**: Manages user provisioning, workspace scoping, quotas. Never
edits drawings — but their correct configuration is what lets every other
persona work safely. Multi-tenant isolation is the hill they die on.

**Key goals**
- Have tenants + users auto-provisioned on first login (no manual onboarding)
- Guarantee cross-tenant isolation (user A never reads user B's documents)
- See work-progress auto-save working for every user without intervention
- Enforce rate limits at the API edge

**Key flows**
- Document persistence + tenant provisioning (JOURNEY-7)
- Web session lifecycle (JOURNEY-5)

**Linked MUST REQ-IDs**
REQ-025, REQ-027, REQ-028, REQ-029, REQ-030
Retrofit queue: REQ-100 (cross-tenant negative test), REQ-104 (allowlist
failure modes), REQ-108 (cache TTL under churn).

**Applicable capabilities**: admin, workspace, quotas, allowlist

---

## Cross-reference
- Canonical 25-profile inventory: `000-docs/072-TQ-TEST-realworld-user-profiles.md`
- Journeys: `tests/JOURNEYS.md`
- Requirements: `tests/RTM.md`

# V1 Beads Plan — cad-dxf-agent

## Top Epic

**cad-dxf-agent-v1** — Local-First Prompt-Based DXF Layout Editor (V1)

**Acceptance criteria**: Desktop app loads a DXF, accepts a prompt, runs the planner, validates operations, previews changes, applies edits, inserts AI revision notes, and saves as a new DXF. All tests pass. CI green. Protected layers enforced.

---

## Child Epics

### v1.1 — Foundation + Repo + Local App Skeleton

**Depends on**: nothing
**Acceptance**: Repo initialized with CI, security, tooling, and a runnable PySide6 shell window.

| Task ID | Task | Acceptance |
|---------|------|------------|
| v1.1.1 | Initialize repo with git, .gitignore, LICENSE, CODEOWNERS | Files present and committed |
| v1.1.2 | Create pyproject.toml with dependencies and tooling | `pip install -e ".[dev]"` succeeds |
| v1.1.3 | Set up pre-commit hooks | `pre-commit run --all-files` passes |
| v1.1.4 | Create GitHub Actions CI (lint, type, test) | CI runs on push to main |
| v1.1.5 | Create GitHub Actions security workflow | Security scan runs on PR |
| v1.1.6 | Add issue templates and PR template | Templates visible on GitHub |
| v1.1.7 | Create settings module with env var loading | Settings load without crash |
| v1.1.8 | Create minimal PySide6 window shell | Window opens with buttons |

---

### v1.2 — DXF Parsing + Normalized Context Model

**Depends on**: v1.1
**Acceptance**: Can load a DXF file, parse supported entities, build DrawingContext, and skip unsupported types with warnings.

| Task ID | Task | Acceptance |
|---------|------|------------|
| v1.2.1 | Define Pydantic schemas: EntityRef, Point2D, EntityType | Models validate correctly |
| v1.2.2 | Define DrawingContext and LayerRule schemas | Context builds from entity list |
| v1.2.3 | Implement DXF reader (model space, V1 types) | Loads sample DXF, returns context |
| v1.2.4 | Implement entity index (by handle, layer, type) | Lookups return correct entities |
| v1.2.5 | Implement semantic model (planner context builder) | Produces JSON-serializable dict |
| v1.2.6 | Add unit tests for reader and index | Tests pass |

---

### v1.3 — Safe Operation Model + Validator Engine

**Depends on**: v1.2
**Acceptance**: EditOperation and ChangeSet schemas defined. Validator blocks protected layers, NaN coords, missing targets. Warning vs blocker separation works.

| Task ID | Task | Acceptance |
|---------|------|------------|
| v1.3.1 | Define OpType enum (4 allowed ops) | Only V1 ops accepted |
| v1.3.2 | Define EditOperation and ChangeSet schemas | Pydantic validation works |
| v1.3.3 | Define ValidationResult with severity levels | Blockers/warnings separate |
| v1.3.4 | Define RuleConfig with protected layers/blocks | Default config correct |
| v1.3.5 | Implement validator: protected layer check | Blocks ops on TITLE etc. |
| v1.3.6 | Implement validator: move param checks (NaN, missing) | Blocks invalid coords |
| v1.3.7 | Implement validator: edit_text param check | Blocks missing new_text |
| v1.3.8 | Implement validator: missing entity handle | Blocks nonexistent handle |
| v1.3.9 | Implement validator: add_block param check | Blocks missing block_name |
| v1.3.10 | Add unit tests for all validator paths | Tests pass, 100% path coverage |

---

### v1.4 — LLM Planner + Tool Interface

**Depends on**: v1.3
**Acceptance**: PlannerProvider interface defined. Mock provider returns valid ops. Response parser validates JSON. Planner orchestrator wires it all.

| Task ID | Task | Acceptance |
|---------|------|------------|
| v1.4.1 | Define PlannerProvider abstract interface | Interface has plan() method |
| v1.4.2 | Implement MockProvider (keyword-based) | Returns ops for move/delete/text |
| v1.4.3 | Define prompt templates for real LLM | System + user prompt templates |
| v1.4.4 | Implement response parser (JSON → ChangeSet) | Parses valid JSON, rejects bad |
| v1.4.5 | Implement planner orchestrator | get_provider() + run_planner() work |
| v1.4.6 | Add unit tests for parser and mock provider | Tests pass without API key |

---

### v1.5 — Preview, Apply, and Save DXF

**Depends on**: v1.4
**Acceptance**: Preview model shows human-readable changes. EditEngine applies ops. DXF writer saves new file. AI revision notes insert on dedicated layer. Original file untouched.

| Task ID | Task | Acceptance |
|---------|------|------------|
| v1.5.1 | Implement PreviewModel | Summary lists all ops with descriptions |
| v1.5.2 | Implement EditEngine: move_entity | Entity position changes |
| v1.5.3 | Implement EditEngine: edit_text | Text content updates |
| v1.5.4 | Implement EditEngine: delete_entity | Entity removed from model space |
| v1.5.5 | Implement EditEngine: add_block | Block ref inserted |
| v1.5.6 | Implement DXF writer (save-as new file) | New file created, original untouched |
| v1.5.7 | Implement revision note generation | Deterministic text from ops |
| v1.5.8 | Implement revision note DXF insertion | Note on AI_REV_NOTES layer |
| v1.5.9 | Define RevisionNoteConfig | Config with anchor, height, toggle |
| v1.5.10 | Add unit tests for revision notes | Tests pass |

---

### v1.6 — End-to-End Workflow, QA, and V1 Hardening

**Depends on**: v1.5
**Acceptance**: Full pipeline works end-to-end. Smoke test passes. UI wired to pipeline. CI green. Docs complete.

| Task ID | Task | Acceptance |
|---------|------|------------|
| v1.6.1 | Wire UI to full pipeline (open → plan → validate → preview → apply → save) | Desktop workflow functional |
| v1.6.2 | Create smoke test script | `python scripts/smoke_test.py` exits 0 |
| v1.6.3 | Create pytest smoke test suite | `pytest -m smoke` passes |
| v1.6.4 | Verify protected layers enforced end-to-end | Validator blocks TITLE ops in E2E |
| v1.6.5 | Verify original file untouched end-to-end | Hash comparison test passes |
| v1.6.6 | Add ADR documents (3 required) | ADRs in docs/adr/ |
| v1.6.7 | Write v1-blueprint.md | Blueprint in docs/specs/ |
| v1.6.8 | Write PRD addendum | Addendum in docs/specs/ |
| v1.6.9 | Write README with quickstart + mock test docs | README present and accurate |
| v1.6.10 | Final CI verification (lint + type + test + security) | All checks pass |

---

## Dependency Chain

```
v1.1 → v1.2 → v1.3 → v1.4 → v1.5 → v1.6
```

Each epic depends on the previous one. Tasks within an epic may be parallelized where dependencies allow.

## Beads CLI Commands (Reference)

```bash
# Create top epic
bd create --id cad-dxf-agent-v1 --type epic --title "Local-First Prompt-Based DXF Layout Editor (V1)"

# Create child epics
bd create --id cad-dxf-agent-v1.1 --type epic --parent cad-dxf-agent-v1 --title "Foundation + Repo + Local App Skeleton"
bd create --id cad-dxf-agent-v1.2 --type epic --parent cad-dxf-agent-v1 --title "DXF Parsing + Normalized Context Model" --blocked-by cad-dxf-agent-v1.1
bd create --id cad-dxf-agent-v1.3 --type epic --parent cad-dxf-agent-v1 --title "Safe Operation Model + Validator Engine" --blocked-by cad-dxf-agent-v1.2
bd create --id cad-dxf-agent-v1.4 --type epic --parent cad-dxf-agent-v1 --title "LLM Planner + Tool Interface" --blocked-by cad-dxf-agent-v1.3
bd create --id cad-dxf-agent-v1.5 --type epic --parent cad-dxf-agent-v1 --title "Preview, Apply, and Save DXF" --blocked-by cad-dxf-agent-v1.4
bd create --id cad-dxf-agent-v1.6 --type epic --parent cad-dxf-agent-v1 --title "End-to-End Workflow, QA, and V1 Hardening" --blocked-by cad-dxf-agent-v1.5

# Sync
bd sync
```

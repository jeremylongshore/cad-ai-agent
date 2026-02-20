# PRD Addendum — cad-dxf-agent V1

## 1) Purpose

cad-dxf-agent is a local-first desktop tool that lets drafting and engineering professionals edit 2D DXF layouts using natural-language prompts. Instead of manually selecting and moving entities in a CAD program, users describe what they want changed, and the tool plans, validates, previews, and applies the edit safely — saving the result as a new DXF file. The original drawing is never modified.

V1 solves the problem of repetitive layout edits (column shifts, label updates, entity deletions, block insertions) that are tedious to perform manually across large drawings.

## 2) V1 Scope (In Scope)

- Local-first desktop workflow (Windows-first, Linux supported)
- DXF file input only
- 2D model space only
- Prompt-based edit planning via pluggable LLM providers
- Structured, safe operation model (no raw DXF editing by LLM)
- Deterministic validation before any edit is applied
- Human-readable preview of proposed changes
- Save as new DXF (original file always preserved)
- Protected layers and blocks (configurable, default: TITLE, TITLEBLOCK, SEAL, REVISION)
- Optional AI revision notes inserted on dedicated `AI_REV_NOTES` layer
- Mock planner mode for offline testing without an API key

## 3) V1 Out of Scope (Explicit)

- DWG native editing (unless externally converted to DXF first)
- Paper space / layout tab editing
- External references (xrefs)
- Automatic dimension regeneration
- Direct title block revision table editing
- 3D entities
- Cloud-hosted application
- Fully offline/local LLM mode (planned for future phase)
- Multi-file batch processing
- Undo/redo within the application (user reopens original instead)

## 4) Functional Requirements (V1)

### User Flow
1. **Open DXF** — user selects a DXF file from local filesystem
2. **Enter prompt** — user types a natural-language description of the desired edit
3. **Plan** — the planner (LLM or mock) returns structured operation JSON
4. **Validate** — all operations are checked against rules (protected layers, valid coords, supported ops)
5. **Preview** — user sees a human-readable summary of what will change
6. **Approve** — user confirms the changes
7. **Apply + Save** — operations are applied and saved as a new DXF file
8. **Revision note** — optional AI revision note is inserted on the `AI_REV_NOTES` layer

### Supported Operations
| Operation | Description |
|-----------|-------------|
| `move_entity` | Move an entity by (dx, dy) in drawing units |
| `edit_text` | Change the text content of a TEXT or MTEXT entity |
| `delete_entity` | Remove an entity from model space |
| `add_block` | Insert a block reference at a specified point |

### Supported Entity Types
| Type | Description |
|------|-------------|
| `LINE` | Simple line segment |
| `LWPOLYLINE` | Lightweight polyline |
| `TEXT` | Single-line text |
| `MTEXT` | Multi-line text |
| `INSERT` | Block reference insertion |

## 5) AI Revision Notes Addendum (Client-Specific)

### Protected Layer Policy
- Protected layers (`TITLE`, `TITLEBLOCK`, `SEAL`, `REVISION`) remain fully protected. No operation may target or modify entities on these layers.
- V1 does **not** write into the real title block revision table. The revision table block structure varies across firms and CAD software, making automated editing unreliable.

### AI Revision Notes
- V1 inserts revision-style notes on a dedicated layer: `AI_REV_NOTES`
- Note text is generated **deterministically** from applied operations — it is never freeform LLM output
- Notes include a configurable prefix (default: `REV`) and revision number
- The anchor point and text height are configurable
- The feature can be toggled on/off via environment variable or config

### Example Notes
- `REV 8 - Column shift`
- `REV 8 - Moved entity east 2'-0"`
- `REV 5 - Updated text to 'New Label'; Deleted entity`

## 6) Safety and Validation Requirements

- **LLM cannot directly edit raw DXF text.** The LLM planner only returns structured JSON operations.
- **All planner output must validate against Pydantic schemas** before any edit is applied.
- **Protected layers and blocks cannot be edited.** Operations targeting protected layers are blocked with clear error messages.
- **Invalid or ambiguous operations are blocked.** NaN coordinates, missing parameters, and unsupported operation types are rejected.
- **Original file must remain unchanged.** The save-as workflow creates a new file; the source DXF is read-only.
- **No partial application.** If any operation in a changeset is blocked, the entire changeset is rejected in V1.

## 7) Non-Functional Requirements (V1)

- **Local-first operation**: core functionality works without internet
- **Windows-first**: tested and supported on Windows 10/11; Linux also supported
- **Mock planner mode**: full pipeline works without an API key
- **Test coverage**: unit tests for schemas, validators, revision notes, parser; smoke tests for full pipeline
- **CI checks**: automated lint (ruff), type checking (mypy), tests (pytest), security scanning (bandit, pip-audit) on every PR
- **Configurable protected layers**: users can add/remove protected layers via environment variables
- **Configurable tolerances**: coordinate tolerance configurable in rule config

## 8) Acceptance Criteria (Client Demo Ready)

| # | Criterion | Verification |
|---|-----------|--------------|
| 1 | Can load a sample DXF without crashing | Smoke test step 2 |
| 2 | Can process a prompt via mock planner | Smoke test step 3 |
| 3 | Can validate operations and block invalid ones | Unit tests + smoke test step 4 |
| 4 | Can preview changes before apply | Smoke test step 5 |
| 5 | Can save updated DXF as new file | Smoke test step 6 |
| 6 | Original file is untouched after save | Smoke test hash comparison |
| 7 | AI revision note appears on `AI_REV_NOTES` layer when enabled | Smoke test step 7 |
| 8 | Protected layers remain unchanged | Validator unit tests |
| 9 | Smoke test command passes locally | `python scripts/smoke_test.py` exits 0 |
| 10 | Desktop UI shell opens and basic workflow works | Manual verification |

## 9) Risks / Assumptions

| Risk | Mitigation |
|------|------------|
| Real-world DXFs may be inconsistent or use non-standard entity types | V1 skips unsupported types with warnings; parser tested against sample files |
| Semantic targeting quality depends on meaningful layers/blocks/text labels | Mock planner uses simple keyword matching; real planner quality depends on drawing metadata |
| LLM may hallucinate invalid operation parameters | All output validated against strict Pydantic schemas before apply |
| Large DXF files may be slow to parse | ezdxf is performant; V1 indexes model space only |
| Layout/paper space editing expected by some users | Explicitly out of scope; documented in UI and docs |
| Revision table integration expected by client | Deferred; documented as future phase in ADR-0003 |

## 10) Future Phase Notes

| Phase | Feature |
|-------|---------|
| V2 | Layout / paper space support |
| V2 | Xref awareness and read-only context |
| V2 | Dimension regeneration after entity moves |
| V2 | Revision block/table integration (structured block attribute mapping) |
| V3 | Vision/redline-assisted targeting (image → entity mapping) |
| V3 | Local LLM support (Ollama, llama.cpp) |
| V3 | Multi-file batch processing |
| Future | DWG native support (pending library availability) |

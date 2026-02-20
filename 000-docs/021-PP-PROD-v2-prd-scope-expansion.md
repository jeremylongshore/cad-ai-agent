# 021-PP-PROD — V2 PRD Scope Expansion

**Date:** 2026-02-20
**Category:** PP (Product & Planning)
**Type:** PROD (Product)
**Client:** Tonatiuh Guadalupe Nava Razon

---

## 1) Context

V1 delivered a working DXF editor with mock planner, validation, preview, edit engine, revision notes, and desktop UI. All 10 PRD acceptance criteria are met. V2 expands the product into a real multimodal CAD editing tool.

This work will help shape the future of the world.

## 2) V2 Scope Changes (Delta from V1 PRD)

### Input Formats (NEW)
| Format | V1 | V2 |
|--------|----|----|
| DXF | Supported | Supported |
| DWG | Out of scope | Supported (auto-convert to DXF via ODA) |
| PDF | Out of scope | Supported (vector PDFs only, CAD-generated) |

### Space Support (CHANGED)
| Space | V1 | V2 |
|-------|----|----|
| Model space | Supported | Supported |
| Layout/paper space | Out of scope | Supported |

### Edit Scope (EXPANDED)
| V1 Operations | V2 Entity Targets |
|---------------|-------------------|
| move_entity | Footings, walls, grid lines, columns, text notes, blocks |
| edit_text | Text notes, labels, annotations |
| delete_entity | Any supported entity on editable layers |
| add_block | Block insertions at specified points |

Scale up for additional entity types and operations in V3.

### Prompt-to-Edit Flow (ENHANCED)
| Feature | V1 | V2 |
|---------|----|----|
| Preview before apply | Batch preview | Per-change preview with approve/reject |
| Approve changes | Batch approve | Approve each change individually |
| Undo/redo | Not supported | Undo/redo stack within session |

### LLM Provider (NEW — replaces mock-only)
| Aspect | V1 | V2 |
|--------|----|----|
| Provider | Mock only (keyword matching) | Gemini 1.5 Pro on Vertex AI |
| Vision | None | Hybrid: DXF render (PNG) + structured entity list |
| Structured output | N/A | Pydantic schema validation on Gemini JSON output |
| Offline fallback | Mock provider | Mock provider (preserved) |

### Output Formats (EXPANDED)
| Format | V1 | V2 |
|--------|----|----|
| DXF (save-as) | Supported | Supported |
| PNG preview | Not supported | Supported (ezdxf matplotlib render) |
| PDF export | Not supported | Supported (ezdxf matplotlib PDF) |
| DWG export | Not supported | Supported (ODA File Converter reverse) |

### Platform (CLARIFIED)
| Platform | V1 | V2 |
|----------|----|----|
| Windows | Supported | Primary (first-class) |
| Linux | Supported | Development/CI only |
| macOS | Not mentioned | V3 target |

## 3) Technical Architecture — V2

### Conversion Layer (NEW)
```
Input File (.dwg, .pdf, .dxf)
    ↓
┌─────────────────────┐
│  Conversion Router   │
│  - DWG → DXF (ODA)  │
│  - PDF → DXF (vector)│
│  - DXF → passthrough │
└──────────┬──────────┘
           ↓
    Working DXF (R2010)
```

**Tools:**
- DWG ↔ DXF: ODA File Converter via `ezdxf.addons.odafc`
- PDF → DXF: `pdfplumber` vector extraction → `ezdxf` entity creation
- Target DXF version: R2010 (AC1024) for compatibility

### Vision Pipeline (NEW)
```
Working DXF
    ├──→ DXF Reader → DrawingContext (precise entities, coordinates)
    └──→ PNG Renderer → Layout Image (visual context)
              ↓                          ↓
         ┌────┴──────────────────────────┴────┐
         │   Gemini 1.5 Pro (Vertex AI)       │
         │   Input: image + entity JSON +     │
         │          user prompt               │
         │   Output: ChangeSet JSON           │
         │   Schema: Pydantic validated       │
         └──────────────┬─────────────────────┘
                        ↓
                  ChangeSet (validated)
```

### Undo/Redo (NEW)
```
EditHistory
    ├── states: list[DrawingState]  # stack of snapshots
    ├── cursor: int                  # current position
    ├── undo() → DrawingState        # move cursor back
    ├── redo() → DrawingState        # move cursor forward
    └── push(state) → None           # add new state after edit
```

### Export Layer (NEW)
```
Edited DXF
    ├──→ DXF save-as (always)
    ├──→ PNG preview (ezdxf matplotlib, configurable DPI)
    ├──→ PDF export (ezdxf matplotlib PDF backend)
    └──→ DWG export (ODA File Converter reverse)
```

## 4) LLM Provider Decision

### Recommended: Gemini 1.5 Pro on Vertex AI

**Why Gemini over Claude/OpenAI:**
- GCP infrastructure already available (no vendor onboarding)
- Object detection with bounding box coordinates (unique to Gemini)
- 1M token context window (5x Claude, 8x GPT-4o)
- Cost: ~$0.003/edit vs $0.01-0.02 for Claude/OpenAI
- Model Garden for future fine-tuning on CAD-specific data
- Vertex AI Endpoints for custom model deployment

**Why Hybrid Vision (not image-only):**
- Image alone: LLM can hallucinate entities, imprecise coordinates
- Entity list alone: LLM can't understand spatial relationships visually
- Hybrid: DXF reader provides ground truth (exact coords, handles, layers) while PNG image lets LLM understand layout context (walls near doors, columns in grid)
- Result: LLM plans operations against verified entities with visual understanding

**Structured Output Strategy:**
- Gemini returns JSON matching ChangeSet Pydantic schema
- Pydantic validation layer catches any schema violations
- Retry once on validation failure with error feedback
- Fall back to mock provider if Gemini unavailable

### Fallback Chain
```
Gemini 1.5 Pro (Vertex AI)
    → retry with error feedback (1x)
    → MockProvider (offline fallback)
```

## 5) V2 Acceptance Criteria

| # | Criterion | Verification |
|---|-----------|--------------|
| 1 | Can open DWG file (auto-converts to DXF) | Unit test: DWG → DXF round-trip |
| 2 | Can open vector PDF (auto-converts to DXF) | Unit test: PDF → DXF basic shapes |
| 3 | Can read layout/paper space entities | Unit test: paper space entity count |
| 4 | Gemini produces valid ChangeSet from prompt + image | Integration test |
| 5 | User can approve/reject individual changes | UI test: per-change buttons |
| 6 | Undo reverts last applied change | UI test: undo restores previous state |
| 7 | Redo re-applies undone change | UI test: redo after undo |
| 8 | Can export to PNG with configurable DPI | Unit test: PNG file produced |
| 9 | Can export to PDF | Unit test: PDF file produced |
| 10 | Can export to DWG (via ODA) | Unit test: DWG file produced |
| 11 | All V1 acceptance criteria still pass | Regression: smoke test exits 0 |
| 12 | Windows installer works | Manual: MSI/NSIS install on Win10 |

## 6) V2 Dependencies

### Required Software (Windows)
- Python 3.11+ (bundled or system)
- ODA File Converter (free download, auto-detected by ezdxf)
- Google Cloud SDK (for Vertex AI authentication)

### Required Python Packages (new for V2)
```
google-cloud-aiplatform    # Vertex AI / Gemini API
pdfplumber                 # PDF vector extraction
ezdxf[draw]                # PNG/PDF rendering (matplotlib backend)
Pillow                     # Image handling
```

### Required GCP Setup
- Vertex AI API enabled
- Service account or user credentials
- Gemini 1.5 Pro model access

## 7) V2 Phase Plan

| Phase | Deliverable | Priority |
|-------|-------------|----------|
| V2.1 | DWG/PDF → DXF conversion layer + PNG preview | HIGH |
| V2.2 | Gemini vision pipeline (Vertex AI) | HIGH |
| V2.3 | Layout/paper space support | MEDIUM |
| V2.4 | Per-change approval + undo/redo | MEDIUM |
| V2.5 | Export layer (PNG, PDF, DWG) | MEDIUM |
| V2.6 | Windows packaging (installer) | HIGH |

## 8) Estimated Effort

- V2.1 (conversion + preview): 1-2 sessions
- V2.2 (Gemini pipeline): 1-2 sessions
- V2.3 (paper space): 1 session
- V2.4 (undo/redo): 1 session
- V2.5 (export): 1 session
- V2.6 (Windows packaging): 1 session
- Testing + PR creation: ~2 hours

## 9) Out of Scope (V3+)
- Scanned/raster PDF conversion (OCR + vectorization)
- macOS support
- Local LLM (Ollama)
- Fine-tuned CAD entity detector (YOLO on Vertex AI)
- Multi-file batch processing
- Real-time collaborative editing
- 3D entity support

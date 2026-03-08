# 057-AT-SPEC — EPIC-CAD-15: Document Persistence

**Epic:** EPIC-CAD-15
**Bead:** cad-dxf-agent-aqw
**Phase:** 6
**Status:** Open
**Created:** 2026-03-07

---

## Problem

Users upload a DXF, work on it, close their browser — and it's gone. Sessions live in `/tmp/cad-sessions/{id}/` with a 2-hour expiry. Every upload is a gamble against a timer. This is table stakes for any production tool: users need to trust that their work persists.

## Solution

Per-user document storage backed by GCS, with a document library UI and session-document binding that survives browser refresh.

## User Experience

### First Visit
1. User logs in → empty document library
2. Uploads a DXF → stored permanently under their account, appears in library
3. Works on the drawing → closes browser

### Return Visit
1. User logs in → sees document library with their uploaded files
2. Library shows: filename, upload date, last accessed
3. Clicks a drawing → loads into workspace exactly as if freshly uploaded

### Multi-File Workflow
1. User has 5 drawings in their library
2. Clicks "Floor Plan Rev A" → workspace loads that drawing
3. Works on it, asks questions, plans edits
4. Switches to "Floor Plan Rev B" → workspace swaps
5. Previous session state preserved — switching back restores it
6. Compare workflow: select two library documents (no re-upload)

### What the User Sees
- **Library panel** (sidebar): list of drawings with name, date, status
- **Active drawing indicator**: always clear which drawing is in workspace
- **Upload button**: adds to library permanently, not a temp session
- **Delete from library**: user controls their storage
- **No timer anxiety**: drawings don't expire

### What the User Does NOT See
- Session IDs, GCS paths, or infrastructure details
- "Your session has expired" messages
- Re-upload prompts for drawings already uploaded

## How It Maps to Existing Code

EPIC-CAD-11 built `SessionStore` ABC with `InMemorySessionStore` and `GCSSessionStore`. The persistence infrastructure exists — but it's session-scoped, not user-scoped.

| Existing | Extension |
|----------|-----------|
| `SessionStore` ABC | Add user-document storage methods or new `DocumentStore` ABC |
| `GCSSessionStore` | Extend for user-scoped paths: `gs://bucket/{user_id}/{doc_id}/` |
| `SessionMetadata` | Add `document_id` field linking session → stored document |
| `web/backend/main.py` | New document library endpoints |
| Firebase Auth | Already provides user identity for storage partitioning |

## Data Model

### UserDocument

```python
class UserDocument(BaseModel):
    """A permanently stored user document."""
    user_id: str
    doc_id: str  # UUID
    filename: str  # Original upload filename
    upload_time: str  # ISO 8601
    last_accessed: str  # ISO 8601
    gcs_path: str  # gs://cad-dxf-agent-documents/{user_id}/{doc_id}/original.dxf
    file_size_bytes: int
    status: Literal["active", "deleted"] = "active"
    metadata: dict[str, Any] = {}  # Drawing metadata (layers, entity count, etc.)
```

### GCS Storage Layout

```
gs://cad-dxf-agent-documents/
  {user_id}/
    documents.json              # User's document index
    {doc_id}/
      original.dxf              # Uploaded file
      metadata.json             # UserDocument serialized
      renders/                  # Cached renders (optional)
```

## API Endpoints

| Method | Path | Purpose |
|--------|------|---------|
| `GET` | `/api/documents` | List user's documents (requires auth) |
| `POST` | `/api/documents` | Upload + persist DXF to user's library |
| `DELETE` | `/api/documents/{doc_id}` | Soft-delete document from library |
| `POST` | `/api/documents/{doc_id}/load` | Create working session from stored document |
| `GET` | `/api/documents/{doc_id}/info` | Get document metadata |

### Session-Document Binding

When a user loads a document from their library:
1. Backend copies DXF from GCS to local session dir
2. Creates session with `document_id` reference
3. Session survives refresh — on reconnect, checks for active session bound to document
4. Document's `last_accessed` timestamp updated

## UI/UX Design Strategy

> Frontend components designed with document-centric workflow pattern.
> Strategic UI/UX planning conducted via ui-ux-pro-max methodology.

### Component Architecture

| Component | Purpose | Location |
|-----------|---------|----------|
| `DocumentLibrary.jsx` | Sidebar panel with file list | Left sidebar |
| `DocumentCard.jsx` | Single document entry with metadata | Inside library |
| `UploadToLibrary.jsx` | Upload flow targeting permanent storage | Library header |
| `ActiveDrawingBadge.jsx` | Shows which document is loaded | Workspace header |
| `CompareFromLibrary.jsx` | Two-document selection for comparison | Compare workflow |

### Design Principles

1. **Library-first** — Landing state shows document library, not empty workspace
2. **Instant recognition** — Filename, date, and status visible at glance
3. **Zero-friction switching** — Click to load, state preserved per document
4. **Permanent by default** — Upload = save to library. No temp uploads in v2.
5. **Storage transparency** — Show usage against quota, no hidden limits

### Storage Limits

| Limit | Value | Rationale |
|-------|-------|-----------|
| Max documents per user | 50 | Reasonable for beta, easy to raise |
| Max file size | 25 MB | Covers most architectural DXF files |
| Max total storage | 100 MB per user | GCS cost control |

## Files to Create/Modify

| File | Action | Purpose |
|------|--------|---------|
| `src/cad_dxf_agent/models/document_schema.py` | Create | UserDocument model |
| `src/cad_dxf_agent/core/document_store.py` | Create | DocumentStore ABC + GCS implementation |
| `src/cad_dxf_agent/core/session_store.py` | Modify | Add document_id to SessionMetadata |
| `web/backend/main.py` | Modify | Document library endpoints |
| `web/frontend/src/components/DocumentLibrary.jsx` | Create | Library sidebar panel |
| `web/frontend/src/components/DocumentCard.jsx` | Create | Single document entry |
| `web/frontend/src/components/UploadToLibrary.jsx` | Create | Persistent upload flow |
| `web/frontend/src/components/ActiveDrawingBadge.jsx` | Create | Active document indicator |

## Stories

| # | Title | Size |
|---|-------|------|
| 1 | User document model — Pydantic schema + tests | S |
| 2 | GCS user storage — persist DXFs to user-scoped GCS paths | M |
| 3 | Document library endpoints — list, upload, delete | M |
| 4 | Load from library — create working session from stored doc | M |
| 5 | Document switching — preserve session state per document | M |
| 6 | Session-document binding — survives refresh/reconnect | M |
| 7 | Frontend document library — sidebar + cards + upload | L |
| 8 | Compare from library — select two docs without re-uploading | M |
| 9 | Storage limits — per-user quotas with clear messaging | S |

## Acceptance Criteria

- User uploads drawing, closes browser, returns next day — drawing still in library
- Document library lists all user's uploaded drawings with metadata
- Clicking a library document loads it into workspace (identical to fresh upload)
- Switching between documents preserves session state for each
- Compare workflow references two library documents directly
- Storage limits enforced with clear user messaging
- Refresh/navigate-away does not lose active drawing or session state
- Existing ephemeral session flow still works as fallback

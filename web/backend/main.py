"""CAD DXF Agent — Web Backend (FastAPI on Cloud Run).

Routes:
    GET  /api/health                  — Health check
    POST /api/upload                  — Upload DXF/PDF, get session + file info
    POST /api/plan                    — Send prompt, get planned operations + preview
    POST /api/apply                   — Apply selected operations
    POST /api/compare                 — Upload revision DXF, compare against master
    GET  /api/dxf                     — Get raw DXF file (original/edited/comparison)
    GET  /api/render                  — Get PNG render (original/edited/diff/comparison)
    GET  /api/download                — Download edited DXF
    POST /api/revision/upload         — Upload revision DXF to existing session
    POST /api/revision/align          — Run alignment (auto or manual control points)
    POST /api/revision/diff           — Run comparison + generate revision ops
    POST /api/revision/approve        — Approve/reject individual revision ops
    POST /api/revision/apply          — Apply approved ops + export bundle
    GET  /api/revision/download       — Download bundle as zip

    # Document Library (EPIC-CAD-15)
    GET  /api/documents               — List user's document library
    POST /api/documents               — Upload DXF to library
    GET  /api/documents/usage         — Storage usage stats
    GET  /api/documents/{id}          — Get document metadata
    DELETE /api/documents/{id}        — Delete document
    POST /api/documents/{id}/load     — Load document into session (deduplicates)
    POST /api/documents/compare       — Compare two library documents
    GET  /api/sessions/active         — List active sessions with document bindings
    POST /api/session/reconnect       — Reconnect to or recreate session for a document
"""

from __future__ import annotations

import asyncio
import logging
import os
import shutil
import sys
from contextlib import asynccontextmanager
from pathlib import Path
from typing import TYPE_CHECKING, Any, Literal

if TYPE_CHECKING:
    from cad_dxf_agent.models.cad_schema import DrawingContext
    from cad_dxf_agent.models.objective_schema import ObjectiveClassification
    from cad_dxf_agent.models.ops_schema import ChangeSet

from fastapi import Depends, FastAPI, File, HTTPException, Query, Request, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from pydantic import BaseModel

# Add src/ to path so we can import the existing pipeline
PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(PROJECT_ROOT / "src"))

from cad_dxf_agent.core.edit_history import EditHistory  # noqa: E402
from cad_dxf_agent.otel import span as otel_span  # noqa: E402

from .api_v1 import router as v1_router  # noqa: E402
from .auth import _get_profile, _get_tenant, _update_profile, get_licensed_user  # noqa: E402
from .session import Session, SessionManager  # noqa: E402

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------
MAX_CONVERSATION_HISTORY = 10  # Max user+model entries kept per session
MAX_UPLOAD_SIZE = 25 * 1024 * 1024  # 25 MB — shared across all upload endpoints
RENDER_ENTITY_LIMIT = 100_000  # Skip DXF preview render above this (OOM risk)

# ---------------------------------------------------------------------------
# Session manager (singleton)
# ---------------------------------------------------------------------------
session_mgr = SessionManager()


SESSION_CLEANUP_INTERVAL = 30 * 60  # 30 minutes


async def _session_cleanup_loop():
    """Periodically remove expired sessions to prevent memory/disk leaks.

    Before deleting, saves work progress for document-bound sessions
    so users can resume where they left off (EPIC-CAD-30).
    """
    while True:
        await asyncio.sleep(SESSION_CLEANUP_INTERVAL)
        try:
            # Save progress for expiring document-bound sessions before cleanup
            for session in list(session_mgr._sessions.values()):
                if session.document_id and session.conversation_history:
                    try:
                        await _save_work_progress(session, session.user_id)
                    except Exception:
                        logger.debug("Pre-cleanup save failed for %s", session.session_id)

            removed = session_mgr.cleanup_expired()
            if removed:
                logger.info("Session cleanup: removed %d expired session(s)", removed)
        except Exception:
            logger.exception("Session cleanup failed")


@asynccontextmanager
async def lifespan(app: FastAPI):
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")

    from cad_dxf_agent.otel import init_otel

    init_otel(service_name="cad-dxf-web")
    logger.info("CAD DXF Web Backend starting")

    cleanup_task = asyncio.create_task(_session_cleanup_loop())
    yield
    cleanup_task.cancel()
    logger.info("CAD DXF Web Backend shutting down")


app = FastAPI(
    title="CAD DXF Agent Web API",
    version="0.1.0",
    lifespan=lifespan,
)

# CORS — allow Firebase Hosting origins + local dev
ALLOWED_ORIGINS = [
    "http://localhost:3000",
    "http://localhost:5173",
    "https://cad-dxf-agent.web.app",
    "https://cad-dxf-agent.firebaseapp.com",
]
custom_origin = os.getenv("CAD_WEB_CORS_ORIGIN")
if custom_origin:
    ALLOWED_ORIGINS.append(custom_origin)

# Register API v1 router (stateless agent endpoints)
app.include_router(v1_router)

app.add_middleware(
    CORSMiddleware,
    allow_origins=ALLOWED_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.middleware("http")
async def log_requests(request: Request, call_next):
    """Log every request/response for debugging (method, path, status, duration)."""
    import time

    start = time.monotonic()
    response = await call_next(request)
    elapsed_ms = (time.monotonic() - start) * 1000

    if response.status_code >= 400:
        logger.warning(
            "%s %s → %d (%.0fms)",
            request.method,
            request.url.path,
            response.status_code,
            elapsed_ms,
        )
    else:
        logger.info(
            "%s %s → %d (%.0fms)",
            request.method,
            request.url.path,
            response.status_code,
            elapsed_ms,
        )
    return response


# ---------------------------------------------------------------------------
# Request / response schemas
# ---------------------------------------------------------------------------


class PromptRequest(BaseModel):
    session_id: str
    prompt: str
    selected_regions: list[dict] | None = None
    client_metadata: dict | None = None


class PlanRequest(BaseModel):
    session_id: str
    prompt: str


class ApplyRequest(BaseModel):
    session_id: str
    selected_ops: list[int] | None = None


class ClearHistoryRequest(BaseModel):
    session_id: str


class RevisionAlignRequest(BaseModel):
    session_id: str
    control_points: list[str] | None = None


class RevisionDiffRequest(BaseModel):
    session_id: str
    profile: str | None = None


class RevisionApproveItem(BaseModel):
    op_id: str
    action: Literal["approve", "reject"]


class RevisionApproveRequest(BaseModel):
    session_id: str
    approvals: list[RevisionApproveItem]


class RevisionApplyRequest(BaseModel):
    session_id: str


class V2PreviewRequest(BaseModel):
    session_id: str


class V2ApproveRequest(BaseModel):
    session_id: str
    plan_id: str
    approved: bool
    notes: str = ""


class V2ApplyRequest(BaseModel):
    session_id: str


class ReconnectRequest(BaseModel):
    document_id: str
    session_id: str | None = None


class CompareLibraryRequest(BaseModel):
    master_doc_id: str
    revision_doc_id: str
    profile: str | None = None


# ---------------------------------------------------------------------------
# Dependency: get authenticated user
# ---------------------------------------------------------------------------


async def get_user(request: Request) -> dict:
    return await get_licensed_user(request)


# ---------------------------------------------------------------------------
# Shared helpers
# ---------------------------------------------------------------------------


def _build_typed_compare_response(
    result: ComparisonResult,  # noqa: F821 — forward ref, imported at call site
    outputs: ComparisonOutputs,  # noqa: F821
    *,
    audit: AuditMetadata | None = None,  # noqa: F821
) -> dict:
    """Build a PlatformResponse dict for a comparison result.

    Shared between /api/compare and /api/v2/prompt compare handler.
    """
    from cad_dxf_agent.core.comparison.engine import ComparisonEngine
    from cad_dxf_agent.llm.response_builder import ResponseBuilder

    compare_data = ComparisonEngine.build_compare_response(result, outputs)
    compare_data["changelog"] = outputs.changelog.to_json()

    total = result.total_changes
    message = f"{total} change{'s' if total != 1 else ''} detected"
    resp = ResponseBuilder.comparison_result(
        message=message,
        data=compare_data,
        audit=audit,
    )
    return resp.model_dump()


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------


@app.get("/api/health")
async def health():
    return {"status": "ok", "service": "cad-dxf-web"}


class DrawingHealthRequest(BaseModel):
    session_id: str


@app.post("/api/drawing-health")
async def drawing_health_check(
    req: DrawingHealthRequest,
    user=Depends(get_licensed_user),
):
    """Run drawing health analysis on the uploaded DXF in a session.

    Returns a structured health report with score, issues, and evidence.
    """
    with otel_span("api.drawing_health") as span:
        try:
            session = session_mgr.get(req.session_id, user["uid"])
        except (KeyError, PermissionError) as e:
            raise HTTPException(404, str(e)) from None

        span.set_attribute("cad.session_id", req.session_id)

        dxf_path = session.original_path
        if dxf_path is None or not dxf_path.exists():
            raise HTTPException(400, "No DXF file in session")

        from cad_dxf_agent.core.dxf_reader import load_dxf
        from cad_dxf_agent.core.health_checker import check_drawing_health

        context = load_dxf(str(dxf_path))
        report = check_drawing_health(context)

        span.set_attribute("cad.health.score", report.score)
        span.set_attribute("cad.health.issues", len(report.issues))

        return {
            "score": report.score,
            "summary": report.summary,
            "issues": [issue.model_dump() for issue in report.issues],
            "checks_run": report.checks_run,
            "entity_count": report.entity_count,
            "layer_count": report.layer_count,
            "critical_count": report.critical_count,
            "warning_count": report.warning_count,
            "info_count": report.info_count,
        }


class DrawingComplianceRequest(BaseModel):
    session_id: str
    profile: str = "ibc-2021"


@app.post("/api/drawing-compliance")
async def drawing_compliance_check(
    req: DrawingComplianceRequest,
    user=Depends(get_licensed_user),
):
    """Run regulation-aware compliance validation on the uploaded DXF.

    Checks the drawing against a compliance profile (ada, ibc, residential)
    and returns a structured report with findings, code references, and score.
    """
    with otel_span("api.drawing_compliance") as span:
        try:
            session = session_mgr.get(req.session_id, user["uid"])
        except (KeyError, PermissionError):
            raise HTTPException(404, "Session not found or access denied") from None

        span.set_attribute("cad.session_id", req.session_id)
        span.set_attribute("cad.compliance.profile", req.profile)

        dxf_path = session.original_path
        if dxf_path is None or not dxf_path.exists():
            raise HTTPException(400, "No DXF file in session")

        from cad_dxf_agent.core.compliance_rules import check_compliance
        from cad_dxf_agent.core.dxf_reader import load_dxf
        from cad_dxf_agent.models.compliance_schema import BUILTIN_PROFILES

        if req.profile not in BUILTIN_PROFILES:
            raise HTTPException(
                422,
                f"Unknown profile: {req.profile}. Available: {', '.join(BUILTIN_PROFILES)}",
            )

        # Cache parsed DrawingContext on session for repeated compliance checks
        if session.context is None:
            session.context = load_dxf(str(dxf_path))
        context = session.context
        report = check_compliance(context, profile=req.profile)

        span.set_attribute("cad.compliance.score", report.score)
        span.set_attribute("cad.compliance.violations", report.violation_count)

        return {
            "profile": report.profile_name,
            "passed": report.passed,
            "score": report.score,
            "findings": [f.model_dump() for f in report.findings],
            "checks_run": report.checks_run,
            "violation_count": report.violation_count,
            "warning_count": report.warning_count,
            "pass_count": report.pass_count,
            "zone_count": report.zone_count,
            "entity_count": report.entity_count,
        }


@app.get("/api/compliance-profiles")
async def list_compliance_profiles():
    """List available compliance profiles and their descriptions."""
    from cad_dxf_agent.models.compliance_schema import BUILTIN_PROFILES

    return {
        name: {
            "name": p.name,
            "description": p.description,
            "enabled_categories": [c.value for c in p.enabled_categories],
        }
        for name, p in BUILTIN_PROFILES.items()
    }


@app.get("/api/profiles")
async def get_profiles():
    """List available comparison profiles (builtins only)."""
    from cad_dxf_agent.core.profiles import BUILTIN_PROFILES

    return {name: p.model_dump() for name, p in BUILTIN_PROFILES.items()}


# ---------------------------------------------------------------------------
# Document Library endpoints (EPIC-CAD-15)
# ---------------------------------------------------------------------------

# Document store singleton — InMemory for dev, GCS for production
_document_store = None


def _get_document_store():
    global _document_store
    if _document_store is None:
        from cad_dxf_agent.core.document_store import (
            GCSDocumentStore,
            InMemoryDocumentStore,
        )

        if os.getenv("CAD_WEB_DEV_MODE", "").lower() in ("1", "true"):
            _document_store = InMemoryDocumentStore()
            logger.info("Using InMemory document store (dev mode)")
        else:
            bucket = os.getenv("CAD_DOCUMENT_BUCKET", "cad-dxf-agent-documents")
            _document_store = GCSDocumentStore(bucket_name=bucket)
            logger.info("Using GCS document store (bucket=%s)", bucket)
    return _document_store


# ---------------------------------------------------------------------------
# Work progress auto-save helper (EPIC-CAD-30)
# ---------------------------------------------------------------------------


async def _save_work_progress(session: Session, user_id: str) -> None:
    """Fire-and-forget: persist work progress for a document-bound session."""
    if not session.document_id:
        return
    try:
        from cad_dxf_agent.models.work_progress_schema import WorkProgress

        progress = WorkProgress(
            user_id=user_id,
            doc_id=session.document_id,
            tenant_id=getattr(session, "tenant_id", ""),
            conversation_history=session.conversation_history[-MAX_CONVERSATION_HISTORY:],
            edit_count=len(session.audit_events),
            last_prompt=session.conversation_history[-1].get("content", "")
            if session.conversation_history
            else "",
            has_working_dxf=session.edited_path is not None
            and session.edited_path.exists(),
            audit_events=session.audit_events[-50:],  # Cap at 50 events
        )
        working_path = session.edited_path if progress.has_working_dxf else None
        store = _get_document_store()
        store.save_work_progress(user_id, session.document_id, progress, working_path)
        logger.debug("Auto-saved work progress for doc %s", session.document_id)
    except (OSError, ValueError, TypeError) as exc:
        logger.warning("Work progress auto-save failed (non-fatal): %s", exc)


def _restore_work_progress(session: Session, user_id: str, store) -> bool:
    """Restore saved work progress into a session. Returns True if restored."""
    if not session.document_id:
        return False
    progress = store.get_work_progress(user_id, session.document_id)
    if progress is None:
        return False

    session.conversation_history = progress.conversation_history
    session.audit_events = progress.audit_events

    # Restore working DXF if available
    if progress.has_working_dxf:
        working_data = store.get_working_dxf(user_id, session.document_id)
        if working_data:
            working_path = session.session_dir / "working.dxf"
            working_path.write_bytes(working_data)
            session.working_path = working_path

    return True


# ---------------------------------------------------------------------------
# Profile + Workspace endpoints (EPIC-CAD-30)
# ---------------------------------------------------------------------------


class ProfileUpdateRequest(BaseModel):
    display_name: str | None = None
    company: str | None = None


@app.get("/api/profile")
async def get_profile(user: dict = Depends(get_user)):
    """Get the current user's profile."""
    if os.getenv("CAD_WEB_DEV_MODE", "").lower() in ("1", "true"):
        return {
            "profile": {
                "uid": user["uid"],
                "email": user.get("email", "dev@localhost"),
                "display_name": user.get("display_name", "Dev User"),
                "company": "",
                "tenant_id": user.get("tenant_id", "dev-tenant"),
                "role": "owner",
            }
        }
    from starlette.concurrency import run_in_threadpool

    profile = await run_in_threadpool(_get_profile, user["uid"])
    if profile is None:
        raise HTTPException(status_code=404, detail="Profile not found")
    return {"profile": profile}


@app.put("/api/profile")
async def update_profile(body: ProfileUpdateRequest, user: dict = Depends(get_user)):
    """Update the current user's display name and/or company."""
    if os.getenv("CAD_WEB_DEV_MODE", "").lower() in ("1", "true"):
        return {"profile": {"uid": user["uid"], "display_name": body.display_name or ""}}

    updates = {}
    if body.display_name is not None:
        updates["display_name"] = body.display_name
    if body.company is not None:
        updates["company"] = body.company
    if not updates:
        raise HTTPException(status_code=400, detail="No fields to update")

    from starlette.concurrency import run_in_threadpool

    profile = await run_in_threadpool(_update_profile, user["uid"], updates)
    if profile is None:
        raise HTTPException(status_code=404, detail="Profile not found")
    return {"profile": profile}


@app.get("/api/workspace")
async def get_workspace(user: dict = Depends(get_user)):
    """Get the current user's workspace/tenant info."""
    tenant_id = user.get("tenant_id", "")
    if os.getenv("CAD_WEB_DEV_MODE", "").lower() in ("1", "true"):
        return {
            "workspace": {"tenant_id": "dev-tenant", "name": "Dev Workspace", "plan": "personal"}
        }

    if not tenant_id:
        raise HTTPException(status_code=404, detail="No workspace found")

    from starlette.concurrency import run_in_threadpool

    tenant = await run_in_threadpool(_get_tenant, tenant_id)
    if tenant is None:
        raise HTTPException(status_code=404, detail="Workspace not found")
    return {"workspace": tenant}


@app.post("/api/documents/{doc_id}/save-progress")
async def save_document_progress(doc_id: str, user: dict = Depends(get_user)):
    """Manually save work progress for a document's active session."""
    existing = session_mgr.find_by_document(user["uid"], doc_id)
    if existing is None:
        raise HTTPException(status_code=404, detail="No active session for this document")

    await _save_work_progress(existing, user["uid"])
    return {"status": "saved", "doc_id": doc_id}


@app.delete("/api/documents/{doc_id}/work-progress")
async def clear_document_progress(doc_id: str, user: dict = Depends(get_user)):
    """Clear saved work progress (start fresh next time)."""
    store = _get_document_store()
    cleared = store.clear_work_progress(user["uid"], doc_id)
    if not cleared:
        raise HTTPException(status_code=404, detail="No work progress to clear")
    return {"status": "cleared", "doc_id": doc_id}


@app.get("/api/documents")
async def list_documents(user: dict = Depends(get_user)):
    """List all documents in the user's library."""
    store = _get_document_store()
    docs = store.list_documents(user["uid"])
    return {"documents": [d.model_dump() for d in docs]}


@app.post("/api/documents")
async def upload_document(
    file: UploadFile = File(...),
    user: dict = Depends(get_user),
):
    """Upload a DXF to the user's permanent document library."""
    from cad_dxf_agent.core.document_store import StorageLimitError

    if not file.filename:
        raise HTTPException(status_code=400, detail="No file provided")

    suffix = Path(file.filename).suffix.lower()
    if suffix not in (".dxf",):
        raise HTTPException(status_code=400, detail="Only DXF files are supported")

    data = await file.read()
    if not data:
        raise HTTPException(status_code=400, detail="Empty file")

    store = _get_document_store()
    try:
        doc = store.save_document(user["uid"], file.filename, data)
    except StorageLimitError as e:
        from cad_dxf_agent.core.document_store import (
            MAX_DOCUMENTS_PER_USER,
            MAX_FILE_SIZE_BYTES,
            MAX_TOTAL_STORAGE_BYTES,
        )

        docs = store.list_documents(user["uid"])
        used_bytes = sum(d.file_size_bytes for d in docs)
        raise HTTPException(
            status_code=413,
            detail={
                "message": str(e),
                "used_bytes": used_bytes,
                "max_bytes": MAX_TOTAL_STORAGE_BYTES,
                "document_count": len(docs),
                "max_documents": MAX_DOCUMENTS_PER_USER,
                "max_file_size_bytes": MAX_FILE_SIZE_BYTES,
                "usage_percent": round(used_bytes / MAX_TOTAL_STORAGE_BYTES * 100, 2)
                if MAX_TOTAL_STORAGE_BYTES
                else 0.0,
            },
        ) from e

    return {"document": doc.model_dump()}


@app.get("/api/documents/usage")
async def get_storage_usage(user: dict = Depends(get_user)):
    """Return storage usage stats for the current user's document library."""
    from cad_dxf_agent.core.document_store import (
        MAX_DOCUMENTS_PER_USER,
        MAX_FILE_SIZE_BYTES,
        MAX_TOTAL_STORAGE_BYTES,
    )

    store = _get_document_store()
    docs = store.list_documents(user["uid"])
    used_bytes = sum(d.file_size_bytes for d in docs)
    usage_percent = (used_bytes / MAX_TOTAL_STORAGE_BYTES * 100) if MAX_TOTAL_STORAGE_BYTES else 0.0

    return {
        "used_bytes": used_bytes,
        "max_bytes": MAX_TOTAL_STORAGE_BYTES,
        "document_count": len(docs),
        "max_documents": MAX_DOCUMENTS_PER_USER,
        "max_file_size_bytes": MAX_FILE_SIZE_BYTES,
        "usage_percent": round(usage_percent, 2),
    }


@app.get("/api/documents/{doc_id}")
async def get_document_info(doc_id: str, user: dict = Depends(get_user)):
    """Get metadata for a specific document."""
    store = _get_document_store()
    doc = store.get_document(user["uid"], doc_id)
    if doc is None:
        raise HTTPException(status_code=404, detail="Document not found")
    return {"document": doc.model_dump()}


@app.delete("/api/documents/{doc_id}")
async def delete_document(doc_id: str, user: dict = Depends(get_user)):
    """Delete a document from the user's library."""
    store = _get_document_store()
    if not store.delete_document(user["uid"], doc_id):
        raise HTTPException(status_code=404, detail="Document not found")
    return {"status": "deleted", "doc_id": doc_id}


@app.post("/api/documents/{doc_id}/load")
async def load_document(doc_id: str, user: dict = Depends(get_user)):
    """Load a library document into a working session.

    If the user already has an active session for this document, returns
    that existing session instead of creating a duplicate. Otherwise, copies
    the stored DXF to a new session directory. Returns session_id + file_info
    just like /api/upload.
    """
    store = _get_document_store()
    doc = store.get_document(user["uid"], doc_id)
    if doc is None:
        raise HTTPException(status_code=404, detail="Document not found")

    # Return existing session if one is already bound to this document
    existing = session_mgr.find_by_document(user["uid"], doc_id)
    if existing is not None:
        store.touch_document(user["uid"], doc_id)
        return {
            "session_id": existing.session_id,
            "file_info": existing.file_info,
            "document_id": doc_id,
            "restored": False,
        }

    file_data = store.get_file_data(user["uid"], doc_id)
    if file_data is None:
        raise HTTPException(status_code=404, detail="Document file not found")

    # Create a session linked to this document
    session = session_mgr.create(user["uid"])
    session.document_id = doc_id
    session.tenant_id = user.get("tenant_id", "")
    Path(session.original_path).write_bytes(file_data)

    # Persist document binding in durable metadata
    session_mgr.save_metadata(session)

    # Touch the document's last_accessed (persists to GCS in production)
    store.touch_document(user["uid"], doc_id)

    # Restore work progress if available
    restored = _restore_work_progress(session, user["uid"], store)

    # Load drawing info
    try:
        from cad_dxf_agent.core.dxf_reader import load_dxf

        # Use working DXF if restored, otherwise original
        dxf_to_load = session.working_path or session.original_path
        ctx = load_dxf(str(dxf_to_load))
        session.context = ctx
        file_info = {
            "filename": doc.filename,
            "entity_count": len(ctx.entities),
            "layers": list({e.layer for e in ctx.entities}),
            "drawing_units": ctx.metadata.get("units", "unknown"),
        }
        session.file_info = file_info
    except Exception as e:
        logger.warning("Failed to load DXF from library doc %s: %s", doc_id, e)
        file_info = {"filename": doc.filename, "error": str(e)}

    return {
        "session_id": session.session_id,
        "file_info": file_info,
        "document_id": doc_id,
        "restored": restored,
    }


@app.get("/api/sessions/active")
async def list_active_sessions(user: dict = Depends(get_user)):
    """List all active sessions with their document bindings for the current user."""
    sessions = session_mgr.list_user_sessions(user["uid"])
    return {
        "sessions": [
            {
                "session_id": s.session_id,
                "document_id": s.document_id,
                "file_info": s.file_info,
                "created_at": s.created_at,
            }
            for s in sessions
        ]
    }


@app.post("/api/session/reconnect")
async def reconnect_session(body: ReconnectRequest, user: dict = Depends(get_user)):
    """Reconnect to an existing session for a library document, or create a new one.

    First tries to find an active session already bound to this document.
    If found, returns it (reconnected=True). If not found but the document
    exists, creates a fresh session from the library (reconnected=False).
    Returns 404 if the document does not exist or belongs to another user.
    """
    store = _get_document_store()
    doc = store.get_document(user["uid"], body.document_id)
    if doc is None:
        raise HTTPException(status_code=404, detail="Document not found")

    # Try to find existing active session bound to this document
    existing = session_mgr.find_by_document(user["uid"], body.document_id)
    if existing is not None:
        store.touch_document(user["uid"], body.document_id)
        return {
            "session_id": existing.session_id,
            "file_info": existing.file_info,
            "document_id": body.document_id,
            "reconnected": True,
        }

    # No existing session — create one from the library document
    file_data = store.get_file_data(user["uid"], body.document_id)
    if file_data is None:
        raise HTTPException(status_code=404, detail="Document file not found")

    session = session_mgr.create(user["uid"])
    session.document_id = body.document_id
    session.tenant_id = user.get("tenant_id", "")
    Path(session.original_path).write_bytes(file_data)
    session_mgr.save_metadata(session)
    store.touch_document(user["uid"], body.document_id)

    # Restore work progress if available
    restored = _restore_work_progress(session, user["uid"], store)

    try:
        from cad_dxf_agent.core.dxf_reader import load_dxf

        dxf_to_load = session.working_path or session.original_path
        ctx = load_dxf(str(dxf_to_load))
        session.context = ctx
        file_info = {
            "filename": doc.filename,
            "entity_count": len(ctx.entities),
            "layers": list({e.layer for e in ctx.entities}),
            "drawing_units": ctx.metadata.get("units", "unknown"),
        }
        session.file_info = file_info
    except Exception as e:
        logger.warning("Failed to load DXF for reconnect (doc %s): %s", body.document_id, e)
        file_info = {"filename": doc.filename, "error": str(e)}

    return {
        "session_id": session.session_id,
        "file_info": file_info,
        "document_id": body.document_id,
        "reconnected": False,
        "restored": restored,
    }


@app.post("/api/documents/compare")
async def compare_library_documents(
    body: CompareLibraryRequest,
    user: dict = Depends(get_user),
):
    """Compare two library documents without uploading files.

    Fetches both documents from the store, validates ownership, then runs
    the same comparison pipeline as /api/compare. The master document is
    used as the baseline; the revision document is compared against it.
    """
    store = _get_document_store()

    master_doc = store.get_document(user["uid"], body.master_doc_id)
    if master_doc is None:
        raise HTTPException(status_code=404, detail="Master document not found")

    revision_doc = store.get_document(user["uid"], body.revision_doc_id)
    if revision_doc is None:
        raise HTTPException(status_code=404, detail="Revision document not found")

    master_data = store.get_file_data(user["uid"], body.master_doc_id)
    if master_data is None:
        raise HTTPException(status_code=404, detail="Master document file not found")

    revision_data = store.get_file_data(user["uid"], body.revision_doc_id)
    if revision_data is None:
        raise HTTPException(status_code=404, detail="Revision document file not found")

    # Create a temporary session to hold the files during comparison
    session = session_mgr.create(user["uid"])
    session_dir = Path("/tmp/cad-sessions") / session.session_id

    master_path = session.original_path
    revision_path = session_dir / "revision.dxf"
    Path(master_path).write_bytes(master_data)
    revision_path.write_bytes(revision_data)
    session.revision_path = revision_path

    try:
        from cad_dxf_agent.core.comparison.engine import ComparisonEngine
        from cad_dxf_agent.models.comparison_schema import ComparisonConfig

        config = ComparisonConfig()
        if body.profile:
            from cad_dxf_agent.core.profiles import load_profile

            config = ComparisonConfig(profile=load_profile(body.profile))

        engine = ComparisonEngine()
        result = engine.compare(master_path, revision_path, config)

        output_dir = session_dir / "comparison"
        outputs = engine.generate_outputs(master_path, revision_path, result, output_dir)

        store.touch_document(user["uid"], body.master_doc_id)
        store.touch_document(user["uid"], body.revision_doc_id)

        return _build_typed_compare_response(result, outputs)

    except FileNotFoundError as e:
        raise HTTPException(status_code=400, detail=str(e)) from None
    except Exception as e:
        logger.error("Library comparison failed: %s", e, exc_info=True)
        raise HTTPException(status_code=500, detail="Comparison failed") from None


@app.post("/api/upload")
async def upload(
    file: UploadFile = File(...),
    user: dict = Depends(get_user),
):
    """Upload a DXF or PDF file and start a session."""
    if not file.filename:
        raise HTTPException(status_code=400, detail="No file provided")

    ext = Path(file.filename).suffix.lower()
    if ext not in (".dxf", ".pdf", ".dwg"):
        raise HTTPException(status_code=400, detail=f"Unsupported file type: {ext}")

    session = session_mgr.create(user_id=user["uid"])
    session_dir = Path("/tmp/cad-sessions") / session.session_id

    # Save uploaded file — enforce size limit
    upload_path = session_dir / f"upload{ext}"
    content = await file.read()
    if len(content) > MAX_UPLOAD_SIZE:
        raise HTTPException(
            status_code=413,
            detail=f"File too large ({len(content) / 1024 / 1024:.1f} MB). Maximum is 25 MB.",
        )
    upload_path.write_bytes(content)

    # Convert if needed
    dxf_path = session.original_path
    pdf_classifications = None
    if ext == ".pdf":
        try:
            from cad_dxf_agent.core.converter import convert_to_dxf

            result = convert_to_dxf(upload_path)
            if not result.success:
                detail = _user_friendly_conversion_error(result.error, ext)
                raise HTTPException(status_code=422, detail=detail)
            shutil.copy2(str(result.output_path), str(dxf_path))
            # Store page classifications for response
            pdf_classifications = result.classifications
        except ImportError:
            raise HTTPException(
                status_code=500,
                detail="PDF conversion is temporarily unavailable. Please try a .dxf file.",
            ) from None
    elif ext == ".dwg":
        _convert_dwg_to_dxf(upload_path, output_dir=session_dir, dest_path=dxf_path)
    else:
        shutil.copy2(str(upload_path), str(dxf_path))

    # Also copy as working file
    session.working_path = session_dir / "working.dxf"
    shutil.copy2(str(dxf_path), str(session.working_path))

    # Initialize edit history for undo/redo (EPIC-CAD-27)
    try:
        from cad_dxf_agent.settings import settings as cad_settings

        session.edit_history = EditHistory(
            session.working_path, max_snapshots=cad_settings.max_undo_snapshots
        )
    except OSError as hist_err:
        logger.warning("Edit history init failed (non-fatal): %s", hist_err)

    # Load and analyze
    try:
        from cad_dxf_agent.core.dxf_reader import load_dxf

        context = load_dxf(dxf_path)
        session.context = context

        layers = sorted({e.layer for e in context.entities})
        session.file_info = {
            "filename": file.filename,
            "entity_count": context.entity_count,
            "layer_count": len(layers),
            "layers": layers,
        }
    except Exception as e:
        logger.error("Failed to load DXF: %s", e)
        raise HTTPException(
            status_code=422,
            detail="Failed to read DXF file. It may be corrupted.",
        ) from None

    # Render original preview
    # For PDF uploads: render first page directly (fast, no entity limit concern)
    # For DXF uploads: use ezdxf renderer (skip if too many entities — OOM risk)
    if ext == ".pdf":
        try:
            preview_path = session_dir / "original.png"
            _render_pdf_page(upload_path, preview_path)
            session.original_render = preview_path
        except Exception as e:
            logger.warning("PDF preview render failed (non-fatal): %s", e, exc_info=True)
    elif context.entity_count <= RENDER_ENTITY_LIMIT:
        try:
            from cad_dxf_agent.core.renderer import render_dxf_to_png

            render_result = render_dxf_to_png(dxf_path, session_dir / "original.png")
            if render_result.success:
                session.original_render = render_result.output_path
            else:
                logger.warning("Original render returned failure: %s", render_result.error)
        except Exception as e:
            logger.warning("Original render failed (non-fatal): %s", e, exc_info=True)
    else:
        logger.info(
            "Skipping render for large drawing (%d entities > %d limit)",
            context.entity_count,
            RENDER_ENTITY_LIMIT,
        )

    response: dict = {
        "session_id": session.session_id,
        "file_info": session.file_info,
    }
    if pdf_classifications:
        response["page_classifications"] = [
            {
                "page": c.page_num + 1,
                "type": c.content_type.value,
                "vectors": c.vector_count,
                "text": c.text_count,
            }
            for c in pdf_classifications
        ]
    return response


@app.post("/api/plan")
async def plan(body: PlanRequest, user: dict = Depends(get_user)):
    """Run the planner on a user prompt for an uploaded file."""
    try:
        session = session_mgr.get(body.session_id, user["uid"])
    except (KeyError, PermissionError) as e:
        raise HTTPException(status_code=404, detail=str(e)) from None

    if session.context is None:
        raise HTTPException(status_code=400, detail="No file loaded in session")

    try:
        from cad_dxf_agent.core.semantic_model import build_planner_context
        from cad_dxf_agent.core.validators import validate_changeset
        from cad_dxf_agent.llm.planner import run_planner
        from cad_dxf_agent.models.config_schema import RuleConfig

        planner_context = build_planner_context(session.context)
        rule_config = RuleConfig()

        changeset = run_planner(
            prompt=body.prompt,
            drawing_context=planner_context,
            context=session.context,
            rule_config=rule_config,
            conversation_history=session.conversation_history or None,
        )
        session.changeset = changeset

        # Validate
        validation = validate_changeset(changeset, session.context, rule_config)

        # Build operation summaries
        operations = []
        for op in changeset.operations:
            operations.append(
                {
                    "op_type": op.op_type.value
                    if hasattr(op.op_type, "value")
                    else str(op.op_type),
                    "target_handle": op.target_handle,
                    "target_layer": op.target_layer,
                    "description": _describe_op(op),
                    "params": op.params,
                }
            )

        # Build text summary
        summary_parts = []
        for op_info in operations:
            summary_parts.append(op_info["description"])
        summary = "; ".join(summary_parts) if summary_parts else "No operations planned."

        # Use LLM message if available and no operations were planned
        llm_message = getattr(changeset, "message", None)

        # Track conversation history for multi-turn context (cap at 10 entries)
        history_text = llm_message if llm_message else summary
        session.conversation_history.append({"role": "user", "text": body.prompt})
        session.conversation_history.append({"role": "model", "text": history_text})
        if len(session.conversation_history) > MAX_CONVERSATION_HISTORY:
            session.conversation_history = session.conversation_history[-MAX_CONVERSATION_HISTORY:]

        return {
            "operations": operations,
            "summary": summary,
            "message": llm_message,
            "validation": {
                "blockers": [{"message": b.message} for b in validation.blockers],
                "warnings": [{"message": w.message} for w in validation.warnings],
                "is_valid": len(validation.blockers) == 0,
            },
        }

    except Exception as e:
        logger.error("Plan failed: %s", e, exc_info=True)
        raise HTTPException(status_code=500, detail="Planning failed") from None


@app.post("/api/v2/prompt")
async def v2_prompt(body: PromptRequest, user: dict = Depends(get_user)):
    """Route a user prompt through the intent router and dispatch to the right handler.

    Returns a typed PlatformResponse envelope for all request types.
    Non-edit requests never reach the LLM planner.
    """
    import time as _time

    from cad_dxf_agent.llm.capability_registry import CapabilityRegistry
    from cad_dxf_agent.llm.intent_router import IntentRouter
    from cad_dxf_agent.llm.objective_classifier import ObjectiveClassifier
    from cad_dxf_agent.llm.response_builder import ResponseBuilder
    from cad_dxf_agent.models.response_schema import AuditMetadata, TaskFamily

    with otel_span("cad.web.v2_prompt", {"cad.web.session_id": body.session_id}):
        total_start = _time.monotonic()

        # Validate session
        try:
            session = session_mgr.get(body.session_id, user["uid"])
        except (KeyError, PermissionError) as e:
            raise HTTPException(status_code=404, detail=str(e)) from None

        if session.context is None:
            raise HTTPException(status_code=400, detail="No file loaded in session")

        # Classify intent (TaskFamily routing — existing behavior)
        router = IntentRouter.from_settings()
        intent = router.classify(body.prompt)

        # Objective classification (two-axis: RequestClass + ObjectiveTag)
        # Pass DrawingContext so family detection runs on real drawing data
        objective_cls = ObjectiveClassifier()
        objective = objective_cls.classify_with_family(
            body.prompt,
            intent.family,
            context=session.context,
        )

        audit = AuditMetadata(
            router_time_ms=intent.router_time_ms,
            router_source=intent.source,
            router_confidence=intent.confidence,
        )

        # Helper to enrich response with objective metadata
        def _enrich(resp_dict: dict) -> dict:
            return _enrich_with_objective(resp_dict, objective)

        # Gate unimplemented families
        registry = CapabilityRegistry()
        if not registry.is_implemented(intent.family):
            audit.total_request_time_ms = (_time.monotonic() - total_start) * 1000
            return _enrich(
                ResponseBuilder.unsupported_operation(
                    family=intent.family,
                    audit=audit,
                ).model_dump()
            )

        # Handle needs_clarification
        if intent.family == TaskFamily.NEEDS_CLARIFICATION:
            audit.total_request_time_ms = (_time.monotonic() - total_start) * 1000
            return _enrich(ResponseBuilder.needs_clarification(audit=audit).model_dump())

        # Handle Q&A — deterministic, no LLM
        if intent.family == TaskFamily.QNA:
            from cad_dxf_agent.core.qna_pipeline import QnaPipeline

            pipeline = QnaPipeline()
            region = _parse_selected_region(body.selected_regions)
            ctx_start = _time.monotonic()
            result = pipeline.answer(
                prompt=body.prompt,
                context=session.context,
                region=region,
            )
            audit.context_build_time_ms = (_time.monotonic() - ctx_start) * 1000
            audit.total_request_time_ms = (_time.monotonic() - total_start) * 1000
            result.audit = audit
            return _enrich(result.model_dump())

        # Handle compare (requires revision file)
        if intent.family == TaskFamily.COMPARE:
            if session.revision_path is None or not session.revision_path.exists():
                audit.total_request_time_ms = (_time.monotonic() - total_start) * 1000
                return _enrich(
                    ResponseBuilder.needs_clarification(
                        message="Upload a revision file first to compare drawings.",
                        family=TaskFamily.COMPARE,
                        audit=audit,
                    ).model_dump()
                )

            # Use cached comparison result if available, else run pipeline
            if session.comparison_result is not None and session.comparison_changelog is not None:
                from cad_dxf_agent.core.comparison.engine import ComparisonOutputs

                outputs = ComparisonOutputs(
                    result=session.comparison_result,
                    changelog=session.comparison_changelog,
                    diff_overlay_path=session.diff_overlay_path,
                    master_path=session.original_path or Path(),
                    revision_path=session.revision_path,
                )
                audit.total_request_time_ms = (_time.monotonic() - total_start) * 1000
                return _enrich(
                    _build_typed_compare_response(session.comparison_result, outputs, audit=audit)
                )

            audit.total_request_time_ms = (_time.monotonic() - total_start) * 1000
            return _enrich(
                ResponseBuilder.needs_clarification(
                    message="Use /api/compare for full comparison workflow.",
                    family=TaskFamily.COMPARE,
                    audit=audit,
                ).model_dump()
            )

        # Handle markup_interpretation — deterministic redline report, no LLM
        if intent.family == TaskFamily.MARKUP_INTERPRETATION:
            from cad_dxf_agent.core.construction_ops import MarkupRedlineGenerator

            ctx_start = _time.monotonic()
            result = MarkupRedlineGenerator().generate(session.context, body.prompt)
            audit.context_build_time_ms = (_time.monotonic() - ctx_start) * 1000
            audit.total_request_time_ms = (_time.monotonic() - total_start) * 1000

            return _enrich(
                ResponseBuilder.markup_redline(
                    message=(
                        f"{result.total_clouds} revision cloud(s) found, "
                        f"{result.total_affected_entities} affected entity(ies)."
                    ),
                    data=result.model_dump(),
                    confidence=result.aggregate_confidence,
                    ambiguity_flags=result.ambiguity_flags,
                    audit=audit,
                ).model_dump()
            )

        # Handle repeated_condition — deterministic, no LLM
        if intent.family == TaskFamily.REPEATED_CONDITION:
            from cad_dxf_agent.core.repeated_condition import ConditionDetector

            exemplar_handles = (
                body.selected_regions[0].get("handles", []) if body.selected_regions else []
            )
            prompt_lower = body.prompt.lower()
            is_batch = not exemplar_handles and any(
                kw in prompt_lower
                for kw in (
                    "batch",
                    "all conditions",
                    "condition report",
                    "condition plan",
                    "find all patterns",
                )
            )

            if is_batch:
                from cad_dxf_agent.core.construction_ops import BatchConditionPlanner

                ctx_start = _time.monotonic()
                result = BatchConditionPlanner().plan(session.context, body.prompt)
                audit.context_build_time_ms = (_time.monotonic() - ctx_start) * 1000
                audit.total_request_time_ms = (_time.monotonic() - total_start) * 1000

                return _enrich(
                    ResponseBuilder.repeated_condition(
                        message=(
                            f"{result.total_groups} condition group(s), "
                            f"{result.total_instances} total instance(s)."
                        ),
                        data=result.model_dump(),
                        confidence=result.aggregate_confidence,
                        ambiguity_flags=result.ambiguity_flags,
                        audit=audit,
                    ).model_dump()
                )

            if not exemplar_handles:
                audit.total_request_time_ms = (_time.monotonic() - total_start) * 1000
                return _enrich(
                    ResponseBuilder.needs_clarification(
                        message=(
                            "Select entities to use as the exemplar for repeated-condition search."
                        ),
                        family=TaskFamily.REPEATED_CONDITION,
                        audit=audit,
                    ).model_dump()
                )

            ctx_start = _time.monotonic()
            detector = ConditionDetector(session.context)
            result = detector.find_repeated(exemplar_handles)
            audit.context_build_time_ms = (_time.monotonic() - ctx_start) * 1000
            audit.total_request_time_ms = (_time.monotonic() - total_start) * 1000

            return _enrich(
                ResponseBuilder.repeated_condition(
                    message=result.summary,
                    data=result.model_dump(),
                    evidence=[ev.model_dump() for c in result.candidates for ev in c.evidence[:3]],
                    confidence=result.candidates[0].confidence if result.candidates else 0.0,
                    ambiguity_flags=result.ambiguity_flags,
                    audit=audit,
                ).model_dump()
            )

        # Handle design_assist — deterministic layout analysis, no LLM
        if intent.family == TaskFamily.DESIGN_ASSIST:
            from cad_dxf_agent.core.design_ops import LayoutRecommender, ScopeBuilder
            from cad_dxf_agent.core.region_context import RegionContextBuilder

            ctx_start = _time.monotonic()
            region = None
            parsed_region = _parse_selected_region(body.selected_regions)
            if parsed_region:
                region = RegionContextBuilder().build(session.context, parsed_region)

            prompt_lower = body.prompt.lower()

            # Field summary sub-dispatch
            is_field = any(
                kw in prompt_lower
                for kw in (
                    "field summary",
                    "field report",
                    "construction summary",
                    "site report",
                )
            )
            if is_field:
                from cad_dxf_agent.core.construction_ops import FieldSummaryBuilder

                result = FieldSummaryBuilder().build(
                    context=session.context,
                    prompt=body.prompt,
                    region=region,
                    comparison_result=session.comparison_result,
                    changeset=session.changeset,
                )
                data = result.model_dump()
                message = f"Field summary: {len(result.sections)} section(s) available."
                confidence = result.aggregate_confidence
                flags = result.ambiguity_flags

            # Grid summary sub-dispatch
            elif any(
                kw in prompt_lower
                for kw in (
                    "grid",
                    "bay",
                    "column grid",
                    "structural grid",
                )
            ):
                from cad_dxf_agent.core.construction_ops import GridAnalyzer

                result = GridAnalyzer().analyze(session.context, body.prompt, region)
                data = result.model_dump()
                message = (
                    f"{len(result.grid_lines)} grid line(s), "
                    f"{len(result.bays)} bay(s). {result.drawing_summary}"
                )
                confidence = result.aggregate_confidence
                flags = result.ambiguity_flags

            # Detect scope workflow
            elif any(
                kw in prompt_lower
                for kw in ("scope of work", "full report", "design summary", "scope summary")
            ):
                result = ScopeBuilder().build(
                    context=session.context,
                    prompt=body.prompt,
                    region=region,
                    comparison_result=session.comparison_result,
                    changeset=session.changeset,
                )
                data = result.model_dump()
                message = f"Scope summary: {len(result.sections)} section(s) available."
                confidence = result.aggregate_confidence
                flags = result.ambiguity_flags
            else:
                result = LayoutRecommender().recommend(
                    session.context,
                    body.prompt,
                    region,
                )
                data = result.model_dump()
                message = (
                    f"{result.total_recommendations} recommendation(s). {result.drawing_summary}"
                )
                confidence = result.aggregate_confidence
                flags = result.ambiguity_flags

            audit.context_build_time_ms = (_time.monotonic() - ctx_start) * 1000
            audit.total_request_time_ms = (_time.monotonic() - total_start) * 1000

            return _enrich(
                ResponseBuilder.design_assist(
                    message=message,
                    data=data,
                    confidence=confidence,
                    ambiguity_flags=flags,
                    audit=audit,
                ).model_dump()
            )

        # Handle summary — deterministic revision summary, no LLM
        if intent.family == TaskFamily.SUMMARY:
            from cad_dxf_agent.core.design_ops import RevisionSummarizer

            ctx_start = _time.monotonic()
            result = RevisionSummarizer().summarize(
                comparison_result=session.comparison_result,
                changeset=session.changeset,
                context=session.context,
            )
            audit.context_build_time_ms = (_time.monotonic() - ctx_start) * 1000
            audit.total_request_time_ms = (_time.monotonic() - total_start) * 1000

            return _enrich(
                ResponseBuilder.summary_result(
                    message=result.headline,
                    data=result.model_dump(),
                    confidence=min(
                        (e.confidence for e in result.key_changes),
                        default=0.5,
                    ),
                    ambiguity_flags=result.ambiguity_flags,
                    audit=audit,
                ).model_dump()
            )

        # Handle takeoff_estimate — deterministic counting, no LLM
        if intent.family == TaskFamily.TAKEOFF_ESTIMATE:
            from cad_dxf_agent.core.design_ops import TakeoffGenerator
            from cad_dxf_agent.core.region_context import RegionContextBuilder

            ctx_start = _time.monotonic()
            region = None
            parsed_region = _parse_selected_region(body.selected_regions)
            if parsed_region:
                region = RegionContextBuilder().build(session.context, parsed_region)

            result = TakeoffGenerator().generate(
                session.context,
                body.prompt,
                region,
            )
            audit.context_build_time_ms = (_time.monotonic() - ctx_start) * 1000
            audit.total_request_time_ms = (_time.monotonic() - total_start) * 1000

            _conf_labels = {
                "high": 0.95,
                "medium": 0.7,
                "low": 0.4,
                "estimate_only": 0.2,
            }
            return _enrich(
                ResponseBuilder.takeoff_result(
                    message=(
                        f"{result.total_items} takeoff item(s), "
                        f"{result.total_quantity_items} total quantity."
                    ),
                    data=result.model_dump(),
                    confidence=_conf_labels.get(result.aggregate_confidence.value, 0.5),
                    ambiguity_flags=result.ambiguity_flags,
                    audit=audit,
                ).model_dump()
            )

        # Handle edit_plan — dispatch to existing planner
        if intent.family == TaskFamily.EDIT_PLAN:
            try:
                from cad_dxf_agent.core.semantic_model import build_planner_context
                from cad_dxf_agent.core.validators import validate_changeset
                from cad_dxf_agent.llm.planner import run_planner
                from cad_dxf_agent.models.config_schema import RuleConfig

                ctx_start = _time.monotonic()
                planner_context = build_planner_context(session.context)
                rule_config = RuleConfig()
                audit.context_build_time_ms = (_time.monotonic() - ctx_start) * 1000

                llm_start = _time.monotonic()
                changeset = run_planner(
                    prompt=body.prompt,
                    drawing_context=planner_context,
                    context=session.context,
                    rule_config=rule_config,
                    conversation_history=session.conversation_history or None,
                )
                session.changeset = changeset
                audit.llm_time_ms = (_time.monotonic() - llm_start) * 1000

                # Build structured EditPlan for preview/apply workflow (EPIC-CAD-08)
                try:
                    from cad_dxf_agent.llm.plan_builder import EditPlanBuilder
                    from cad_dxf_agent.llm.plan_builder import PlanRequest as PlanReq

                    plan_req = PlanReq(
                        prompt=body.prompt,
                        drawing_context=session.context,
                        request_id=getattr(body, "request_id", ""),
                        target_handles=[
                            op.target_handle for op in changeset.operations if op.target_handle
                        ]
                        or None,
                    )
                    edit_plan = EditPlanBuilder().build(plan_req)
                    session.edit_plan = edit_plan
                except Exception as plan_err:
                    logger.warning("EditPlan build failed (non-fatal): %s", plan_err)

                val_start = _time.monotonic()
                validation = validate_changeset(changeset, session.context, rule_config)
                audit.validation_time_ms = (_time.monotonic() - val_start) * 1000

                operations = []
                for op in changeset.operations:
                    operations.append(
                        {
                            "op_type": op.op_type.value
                            if hasattr(op.op_type, "value")
                            else str(op.op_type),
                            "target_handle": op.target_handle,
                            "target_layer": op.target_layer,
                            "description": _describe_op(op),
                            "params": op.params,
                        }
                    )

                summary_parts = [o["description"] for o in operations]
                summary = "; ".join(summary_parts) if summary_parts else "No operations planned."
                llm_message = getattr(changeset, "message", None)

                # Track conversation history
                history_text = llm_message if llm_message else summary
                session.conversation_history.append({"role": "user", "text": body.prompt})
                session.conversation_history.append({"role": "model", "text": history_text})
                if len(session.conversation_history) > MAX_CONVERSATION_HISTORY:
                    session.conversation_history = session.conversation_history[
                        -MAX_CONVERSATION_HISTORY:
                    ]

                # Apply precision controls (EPIC-CAD-14)
                precision_candidates = None
                precision_action_details = None
                try:
                    precision_candidates, precision_action_details = _enrich_with_precision(
                        changeset,
                        session.context,
                        validation,
                        body.client_metadata,
                    )
                    if precision_action_details is not None:
                        # Re-serialize operations from potentially modified changeset
                        operations = []
                        for op in changeset.operations:
                            operations.append(
                                {
                                    "op_type": op.op_type.value
                                    if hasattr(op.op_type, "value")
                                    else str(op.op_type),
                                    "target_handle": op.target_handle,
                                    "target_layer": op.target_layer,
                                    "description": _describe_op(op),
                                    "params": op.params,
                                }
                            )
                except (ValueError, KeyError, TypeError) as prec_err:
                    logger.warning("Precision enrichment failed (non-fatal): %s", prec_err)

                audit.total_request_time_ms = (_time.monotonic() - total_start) * 1000

                return _enrich(
                    ResponseBuilder.plan_only(
                        operations=operations,
                        message=llm_message or summary,
                        validation={
                            "blockers": [{"message": b.message} for b in validation.blockers],
                            "warnings": [{"message": w.message} for w in validation.warnings],
                            "is_valid": len(validation.blockers) == 0,
                        },
                        audit=audit,
                        ambiguity_candidates=precision_candidates,
                        precision_actions=precision_action_details,
                    ).model_dump()
                )

            except Exception as e:
                logger.error("v2 plan failed: %s", e, exc_info=True)
                raise HTTPException(status_code=500, detail="Planning failed") from None

        # Catch-all for families that are "implemented" but not yet wired
        audit.total_request_time_ms = (_time.monotonic() - total_start) * 1000
        return _enrich(
            ResponseBuilder.unsupported_operation(
                family=intent.family,
                audit=audit,
            ).model_dump()
        )


# ---------------------------------------------------------------------------
# v2 Preview / Approve / Apply (EPIC-CAD-08)
# ---------------------------------------------------------------------------


@app.post("/api/v2/preview")
async def v2_preview(body: V2PreviewRequest, user: dict = Depends(get_user)):
    """Build a structured preview from the session's edit plan."""
    try:
        session = session_mgr.get(body.session_id, user["uid"])
    except (KeyError, PermissionError) as e:
        raise HTTPException(status_code=404, detail=str(e)) from None

    if session.edit_plan is None:
        raise HTTPException(status_code=400, detail="No edit plan in session. Send a prompt first.")

    from cad_dxf_agent.core.preview_builder import EditPreviewBuilder
    from cad_dxf_agent.llm.response_builder import ResponseBuilder
    from cad_dxf_agent.models.apply_schema import AuditEvent
    from cad_dxf_agent.models.response_schema import AuditMetadata

    builder = EditPreviewBuilder(session.context)
    preview = builder.build(session.edit_plan)
    session.edit_preview = preview

    # Record audit event
    session.audit_events.append(
        AuditEvent(
            event_type="preview_generated",
            plan_id=session.edit_plan.plan_id,
            preview_id=preview.preview_id,
            actor=user["uid"],
            details={"total_actions": preview.total_actions, "status": preview.status.value},
        ).model_dump()
    )

    audit = AuditMetadata()
    return ResponseBuilder.structured_preview(
        preview=preview,
        audit=audit,
    ).model_dump()


@app.post("/api/v2/approve")
async def v2_approve(body: V2ApproveRequest, user: dict = Depends(get_user)):
    """Record an approval or rejection decision for an edit plan."""
    try:
        session = session_mgr.get(body.session_id, user["uid"])
    except (KeyError, PermissionError) as e:
        raise HTTPException(status_code=404, detail=str(e)) from None

    if session.edit_plan is None:
        raise HTTPException(status_code=400, detail="No edit plan in session.")

    if session.edit_plan.plan_id != body.plan_id:
        raise HTTPException(status_code=400, detail="Plan ID mismatch.")

    from cad_dxf_agent.models.apply_schema import ApprovalDecision, AuditEvent

    decision = ApprovalDecision(
        plan_id=body.plan_id,
        approved=body.approved,
        approved_by=user["uid"],
        notes=body.notes,
    )
    session.edit_approval = decision

    event_type = "approval_granted" if body.approved else "approval_rejected"
    session.audit_events.append(
        AuditEvent(
            event_type=event_type,
            plan_id=body.plan_id,
            actor=user["uid"],
            details={"approved": body.approved, "notes": body.notes},
        ).model_dump()
    )

    return {
        "plan_id": body.plan_id,
        "approved": body.approved,
        "event_type": event_type,
    }


@app.post("/api/v2/apply")
async def v2_apply(body: V2ApplyRequest, user: dict = Depends(get_user)):
    """Apply the approved edit plan to the DXF file."""
    try:
        session = session_mgr.get(body.session_id, user["uid"])
    except (KeyError, PermissionError) as e:
        raise HTTPException(status_code=404, detail=str(e)) from None

    if session.edit_plan is None:
        raise HTTPException(status_code=400, detail="No edit plan in session.")

    if session.context is None:
        raise HTTPException(status_code=400, detail="No drawing context in session.")

    from cad_dxf_agent.core.apply_pipeline import ApplyPipeline
    from cad_dxf_agent.llm.response_builder import ResponseBuilder
    from cad_dxf_agent.models.apply_schema import AuditEvent
    from cad_dxf_agent.models.config_schema import RevisionNoteConfig
    from cad_dxf_agent.models.response_schema import AuditMetadata

    session_dir = Path("/tmp/cad-sessions") / session.session_id
    output_path = session_dir / "edited.dxf"

    pipeline = ApplyPipeline(session.context)
    result = pipeline.apply(
        plan=session.edit_plan,
        dxf_path=session.working_path or session.original_path,
        output_path=output_path,
        approval=session.edit_approval,
        revision_config=RevisionNoteConfig(enabled=True),
    )

    session.edit_apply_result = result
    if result.output_path:
        session.edited_path = Path(result.output_path)

    # Push edit snapshot for undo/redo (EPIC-CAD-27)
    if result.output_path and session.edit_history is not None:
        try:
            import ezdxf

            doc = ezdxf.readfile(str(result.output_path))
            label = session.edit_plan.summary if hasattr(session.edit_plan, "summary") else "edit"
            session.edit_history.push(doc, label=label)
        except Exception as hist_err:
            logger.warning("Edit history push failed (non-fatal): %s", hist_err)

    # Render edited preview
    try:
        from cad_dxf_agent.core.renderer import render_dxf_to_png

        render_result = render_dxf_to_png(output_path, session_dir / "edited.png")
        if render_result.success:
            session.edited_render = render_result.output_path
    except Exception as render_err:
        logger.warning("Edited render failed (non-fatal): %s", render_err)

    # Record audit event
    session.audit_events.append(
        AuditEvent(
            event_type="apply_executed",
            plan_id=session.edit_plan.plan_id,
            apply_id=result.apply_id,
            actor=user["uid"],
            details={
                "status": result.status.value,
                "success_count": result.success_count,
                "failure_count": result.failure_count,
            },
        ).model_dump()
    )

    audit = AuditMetadata()

    # Auto-save work progress (fire-and-forget)
    if session.document_id:
        asyncio.create_task(_save_work_progress(session, user["uid"]))

    return ResponseBuilder.structured_apply_result(
        result=result,
        audit=audit,
    ).model_dump()


@app.post("/api/apply")
async def apply_changes(body: ApplyRequest, user: dict = Depends(get_user)):
    """Apply (selected) operations from the last plan."""
    async with session_mgr.session_lock(body.session_id):
        try:
            session = session_mgr.get(body.session_id, user["uid"])
        except (KeyError, PermissionError) as e:
            raise HTTPException(status_code=404, detail=str(e)) from None

        if session.changeset is None:
            raise HTTPException(status_code=400, detail="No plan to apply. Run /api/plan first.")

        try:
            from cad_dxf_agent.core.edit_engine import EditEngine
            from cad_dxf_agent.models.ops_schema import ChangeSet

            changeset = session.changeset

            # Filter to selected ops if specified
            if body.selected_ops is not None:
                selected = [
                    changeset.operations[i]
                    for i in sorted(set(body.selected_ops))
                    if 0 <= i < len(changeset.operations)
                ]
                changeset = ChangeSet(
                    operations=selected,
                    prompt=changeset.prompt,
                )

            # Apply
            engine = EditEngine(session.working_path)
            results = engine.apply_changeset(changeset)

            # Save edited file
            session_dir = Path("/tmp/cad-sessions") / session.session_id
            session.edited_path = session_dir / "edited.dxf"
            engine.save(session.edited_path)

            # Push edit snapshot for undo/redo (EPIC-CAD-27)
            if session.edit_history is not None:
                try:
                    label = changeset.prompt or "edit"
                    session.edit_history.push(engine.doc, label=label)
                except Exception as hist_err:
                    logger.warning("Edit history push failed (non-fatal): %s", hist_err)

            # Render edited preview
            try:
                from cad_dxf_agent.core.renderer import render_dxf_to_png

                render_result = render_dxf_to_png(session.edited_path, session_dir / "edited.png")
                if render_result.success:
                    session.edited_render = render_result.output_path
                else:
                    logger.warning("Edited render returned failure: %s", render_result.error)
                    session.edited_render = None
            except Exception as e:
                logger.warning("Edited render failed (non-fatal): %s", e, exc_info=True)
                session.edited_render = None

            render_available = session.edited_render is not None and session.edited_render.exists()
            success_count = sum(1 for r in results if r.success)

            # Auto-save work progress (fire-and-forget)
            if session.document_id:
                asyncio.create_task(_save_work_progress(session, user["uid"]))

            return {
                "message": f"Applied {success_count}/{len(results)} operations.",
                "render_available": render_available,
                "results": [
                    {
                        "success": r.success,
                        "message": r.message if hasattr(r, "message") else "",
                    }
                    for r in results
                ],
            }

        except Exception as e:
            logger.error("Apply failed: %s", e, exc_info=True)
            raise HTTPException(
                status_code=500,
                detail="Apply failed",
            ) from None


@app.post("/api/clear-history")
async def clear_history(body: ClearHistoryRequest, user: dict = Depends(get_user)):
    """Clear conversation history for a session (keep the file loaded)."""
    try:
        session = session_mgr.get(body.session_id, user["uid"])
    except (KeyError, PermissionError) as e:
        raise HTTPException(status_code=404, detail=str(e)) from None

    session.conversation_history = []
    session.changeset = None
    return {"message": "Conversation cleared."}


# ---------------------------------------------------------------------------
# Edit History endpoints — undo/redo/snapshot (EPIC-CAD-27)
# ---------------------------------------------------------------------------


class UndoRedoRequest(BaseModel):
    session_id: str


class SnapshotRequest(BaseModel):
    session_id: str
    label: str = ""


def _get_session_history(
    session_id: str,
    user: dict,
    *,
    require: bool = True,
) -> tuple[Session, EditHistory | None]:
    """Shared helper: resolve session + edit history, raise on error.

    Returns (session, history). If require=True and no history exists,
    raises 400. If require=False, history may be None.
    """
    try:
        session = session_mgr.get(session_id, user["uid"])
    except (KeyError, PermissionError) as e:
        raise HTTPException(status_code=404, detail=str(e)) from None

    history: EditHistory | None = session.edit_history
    if require and history is None:
        raise HTTPException(status_code=400, detail="No edit history in session.")
    return session, history


def _save_restored_dxf(session: Session, doc: object) -> None:
    """Save a restored ezdxf document as the current edited file.

    Called after undo/redo to persist the restored state to disk.
    """
    restored_path = session.session_dir / "edited.dxf"
    doc.saveas(str(restored_path))  # type: ignore[union-attr]
    session.edited_path = restored_path


@app.post("/api/undo")
async def undo(body: UndoRedoRequest, user: dict = Depends(get_user)):
    """Undo the last edit operation, restoring the previous DXF state."""
    session, history = _get_session_history(body.session_id, user)
    async with session_mgr.session_lock(body.session_id):
        if not history.can_undo:
            return {
                "undone": False,
                "message": "Already at initial state — nothing to undo.",
                "can_undo": False,
                "can_redo": history.can_redo,
                "current_label": history.current_label,
                "depth": history.depth,
            }

        doc = history.undo()
        if doc is not None:
            _save_restored_dxf(session, doc)

        return {
            "undone": True,
            "message": f"Undone. Now at: {history.current_label}",
            "can_undo": history.can_undo,
            "can_redo": history.can_redo,
            "current_label": history.current_label,
            "depth": history.depth,
        }


@app.post("/api/redo")
async def redo(body: UndoRedoRequest, user: dict = Depends(get_user)):
    """Redo the previously undone edit operation."""
    session, history = _get_session_history(body.session_id, user)
    async with session_mgr.session_lock(body.session_id):
        if not history.can_redo:
            return {
                "redone": False,
                "message": "Already at latest state — nothing to redo.",
                "can_undo": history.can_undo,
                "can_redo": False,
                "current_label": history.current_label,
                "depth": history.depth,
            }

        doc = history.redo()
        if doc is not None:
            _save_restored_dxf(session, doc)

        return {
            "redone": True,
            "message": f"Redone. Now at: {history.current_label}",
            "can_undo": history.can_undo,
            "can_redo": history.can_redo,
            "current_label": history.current_label,
            "depth": history.depth,
        }


@app.post("/api/snapshot")
async def create_snapshot(body: SnapshotRequest, user: dict = Depends(get_user)):
    """Create a named snapshot of the current DXF state."""
    _session, history = _get_session_history(body.session_id, user)

    # Get the current document
    doc = history.get_current_doc()
    label = body.label or f"snapshot-{history.depth + 1}"
    history.push(doc, label=label)

    return {
        "message": f"Snapshot created: {label}",
        "label": label,
        "depth": history.depth,
        "can_undo": history.can_undo,
        "can_redo": history.can_redo,
    }


@app.get("/api/history")
async def get_history(session_id: str = Query(...), user: dict = Depends(get_user)):
    """Get edit history timeline for a session."""
    _session, history = _get_session_history(session_id, user, require=False)

    if history is None:
        return {
            "entries": [],
            "current_index": -1,
            "can_undo": False,
            "can_redo": False,
        }

    entries = [{"index": -1, "label": "initial"}]
    labels = history.labels
    for i in range(history.depth):
        entries.append(
            {
                "index": i,
                "label": labels[i],
            }
        )

    return {
        "entries": entries,
        "current_index": history.cursor,
        "current_label": history.current_label,
        "can_undo": history.can_undo,
        "can_redo": history.can_redo,
        "depth": history.depth,
    }


@app.post("/api/compare")
async def compare(
    file: UploadFile = File(...),
    session_id: str = Query(...),
    profile: str | None = Query(default=None),
    user: dict = Depends(get_user),
):
    """Upload a revision DXF and compare against the session's master file."""
    with otel_span("cad.web.compare", {"cad.web.session_id": session_id}) as s:
        if not file.filename:
            raise HTTPException(status_code=400, detail="No file provided")

        ext = Path(file.filename).suffix.lower()
        if ext not in (".dxf", ".dwg"):
            raise HTTPException(status_code=400, detail="Comparison requires a .dxf or .dwg file")

        try:
            session = session_mgr.get(session_id, user["uid"])
        except (KeyError, PermissionError) as e:
            raise HTTPException(status_code=404, detail=str(e)) from None

        if session.original_path is None or not session.original_path.exists():
            raise HTTPException(
                status_code=400, detail="No master file loaded. Upload a file first."
            )

        # Save uploaded file — enforce size limit
        content = await file.read()
        if len(content) > MAX_UPLOAD_SIZE:
            raise HTTPException(
                status_code=413,
                detail=f"File too large ({len(content) / 1024 / 1024:.1f} MB). Maximum is 25 MB.",
            )

        session_dir = Path("/tmp/cad-sessions") / session.session_id
        revision_path = session_dir / "revision.dxf"

        if ext == ".dwg":
            dwg_path = session_dir / "revision_upload.dwg"
            dwg_path.write_bytes(content)
            _convert_dwg_to_dxf(dwg_path, output_dir=session_dir, dest_path=revision_path)
        else:
            revision_path.write_bytes(content)

        try:
            from cad_dxf_agent.core.comparison.engine import ComparisonEngine
            from cad_dxf_agent.models.comparison_schema import ComparisonConfig

            config = ComparisonConfig()
            if profile:
                from cad_dxf_agent.core.profiles import load_profile

                config = ComparisonConfig(profile=load_profile(profile))

            engine = ComparisonEngine()
            result = engine.compare(session.original_path, revision_path, config)

            # Generate outputs
            output_dir = session_dir / "comparison"
            outputs = engine.generate_outputs(
                session.original_path, revision_path, result, output_dir
            )

            # Store in session
            session.comparison_result = result
            session.comparison_changelog = outputs.changelog
            session.diff_overlay_path = outputs.diff_overlay_path

            # Render diff overlay preview
            if outputs.diff_overlay_path and outputs.diff_overlay_path.exists():
                try:
                    from cad_dxf_agent.core.renderer import render_dxf_to_png

                    render_result = render_dxf_to_png(
                        outputs.diff_overlay_path, session_dir / "comparison.png"
                    )
                    if render_result.success:
                        session.diff_overlay_render = render_result.output_path
                except Exception as e:
                    logger.warning("Comparison render failed (non-fatal): %s", e)

            s.set_attribute("cad.compare.total_changes", result.total_changes)

            return _build_typed_compare_response(result, outputs)

        except FileNotFoundError as e:
            raise HTTPException(status_code=400, detail=str(e)) from None
        except Exception as e:
            logger.error("Comparison failed: %s", e, exc_info=True)
            raise HTTPException(status_code=500, detail="Comparison failed") from None


@app.get("/api/dxf")
async def get_dxf_file(
    session_id: str = Query(...),
    render_type: str = Query("original", alias="type"),
    user: dict = Depends(get_user),
):
    """Serve raw DXF for client-side WebGL rendering."""
    try:
        session = session_mgr.get(session_id, user["uid"])
    except (KeyError, PermissionError) as e:
        raise HTTPException(status_code=404, detail=str(e)) from None

    dxf_map: dict[str, Path | None] = {
        "original": session.original_path,
        "edited": session.edited_path,
        "comparison": session.diff_overlay_path,
    }
    path = dxf_map.get(render_type)

    if path is None or not path.exists():
        raise HTTPException(status_code=404, detail=f"No {render_type} DXF available")

    return FileResponse(
        path=str(path),
        media_type="application/dxf",
        filename=f"{render_type}.dxf",
    )


@app.get("/api/render")
async def render(
    session_id: str = Query(...),
    render_type: str = Query("original", alias="type"),
    user: dict = Depends(get_user),
):
    """Return a PNG render of the drawing."""
    try:
        session = session_mgr.get(session_id, user["uid"])
    except (KeyError, PermissionError) as e:
        raise HTTPException(status_code=404, detail=str(e)) from None

    render_map = {
        "original": session.original_render,
        "edited": session.edited_render,
        "diff": session.diff_render,
        "comparison": session.diff_overlay_render,
    }
    path = render_map.get(render_type)

    if path is None or not path.exists():
        raise HTTPException(status_code=404, detail=f"No {render_type} render available")

    return FileResponse(
        path=str(path),
        media_type="image/png",
        filename=f"{render_type}.png",
    )


@app.get("/api/download")
async def download(
    session_id: str = Query(...),
    output_format: str = Query("dxf", alias="format"),
    user: dict = Depends(get_user),
):
    """Download the edited file as DXF or DWG.

    Query params:
        format: "dxf" (default) or "dwg" (converts via ODA before download).
    """
    try:
        session = session_mgr.get(session_id, user["uid"])
    except (KeyError, PermissionError) as e:
        raise HTTPException(status_code=404, detail=str(e)) from None

    if session.edited_path is None or not session.edited_path.exists():
        raise HTTPException(
            status_code=404, detail="No edited file available. Run /api/apply first."
        )

    original_name = session.file_info.get("filename", "drawing.dxf")
    stem = Path(original_name).stem

    if output_format == "dwg":
        # ODA converts both ways — ezdxf odafc.export_dwg writes DWG from DXF
        try:
            import ezdxf
            from ezdxf.addons import odafc

            session_dir = Path("/tmp/cad-sessions") / session.session_id
            dwg_path = session_dir / f"{stem}_edited.dwg"
            doc = ezdxf.readfile(str(session.edited_path))
            odafc.export_dwg(doc, str(dwg_path))  # type: ignore[attr-defined]

            download_name = f"{stem}_edited.dwg"
            return FileResponse(
                path=str(dwg_path),
                media_type="application/octet-stream",
                filename=download_name,
                headers={"Content-Disposition": f'attachment; filename="{download_name}"'},
            )
        except Exception as e:
            raise HTTPException(
                status_code=422,
                detail=f"DWG export failed: {e}. Try downloading as DXF instead.",
            ) from None

    # Default: DXF download
    download_name = f"{stem}_edited.dxf"
    return FileResponse(
        path=str(session.edited_path),
        media_type="application/dxf",
        filename=download_name,
        headers={"Content-Disposition": f'attachment; filename="{download_name}"'},
    )


# ---------------------------------------------------------------------------
# Revision pipeline endpoints
# ---------------------------------------------------------------------------


def _parse_control_points(
    raw: list[str] | None,
) -> list[tuple[tuple[float, float], tuple[float, float]]] | None:
    """Parse control-point strings like '0,0:5,3' into typed tuples."""
    if not raw:
        return None
    pairs: list[tuple[tuple[float, float], tuple[float, float]]] = []
    for token in raw:
        master_str, _, rev_str = token.partition(":")
        if not rev_str:
            raise ValueError(f"Invalid control point format (expected mx,my:rx,ry): {token!r}")
        mx, my = (float(v) for v in master_str.split(","))
        rx, ry = (float(v) for v in rev_str.split(","))
        pairs.append(((mx, my), (rx, ry)))
    return pairs


@app.post("/api/revision/upload")
async def revision_upload(
    file: UploadFile = File(...),
    user: dict = Depends(get_user),
    session_id: str = Query(...),
):
    """Upload a revision DXF to an existing session."""
    with otel_span("cad.web.revision.upload", {"cad.web.session_id": session_id}):
        if not file.filename:
            raise HTTPException(status_code=400, detail="No file provided")

        ext = Path(file.filename).suffix.lower()
        if ext not in (".dxf", ".dwg"):
            raise HTTPException(
                status_code=400, detail="Revision upload requires a .dxf or .dwg file"
            )

        try:
            session = session_mgr.get(session_id, user["uid"])
        except (KeyError, PermissionError) as e:
            raise HTTPException(status_code=404, detail=str(e)) from None

        # Enforce size limit
        content = await file.read()
        if len(content) > MAX_UPLOAD_SIZE:
            raise HTTPException(
                status_code=413,
                detail=f"File too large ({len(content) / 1024 / 1024:.1f} MB). Maximum is 25 MB.",
            )

        session_dir = Path("/tmp/cad-sessions") / session.session_id
        revision_path = session_dir / "revision.dxf"

        if ext == ".dwg":
            dwg_path = session_dir / "revision_upload.dwg"
            dwg_path.write_bytes(content)
            _convert_dwg_to_dxf(dwg_path, output_dir=session_dir, dest_path=revision_path)
        else:
            revision_path.write_bytes(content)
        session.revision_path = revision_path

        return {"session_id": session.session_id, "filename": file.filename}


@app.post("/api/revision/align")
async def revision_align(body: RevisionAlignRequest, user: dict = Depends(get_user)):
    """Run alignment between master and revision with optional control points."""
    with otel_span("cad.web.revision.align", {"cad.web.session_id": body.session_id}):
        try:
            session = session_mgr.get(body.session_id, user["uid"])
        except (KeyError, PermissionError) as e:
            raise HTTPException(status_code=404, detail=str(e)) from None

        if session.original_path is None or not session.original_path.exists():
            raise HTTPException(
                status_code=400, detail="No master file loaded. Upload a file first."
            )
        if session.revision_path is None or not session.revision_path.exists():
            raise HTTPException(
                status_code=400,
                detail="No revision file uploaded. Use /api/revision/upload first.",
            )

        try:
            from cad_dxf_agent.core.comparison.alignment import align_drawings
            from cad_dxf_agent.core.comparison.geometry import extract_snapshots
            from cad_dxf_agent.models.comparison_schema import AlignmentConfig

            control_points = _parse_control_points(body.control_points)
            config = AlignmentConfig(enabled=True, control_points=control_points)

            master_snaps = extract_snapshots(session.original_path)
            revision_snaps = extract_snapshots(session.revision_path)

            result = align_drawings(master_snaps, revision_snaps, config)
            session.alignment_result = result
            session.alignment_control_points = control_points

            return {
                "method": result.method.value,
                "confidence": result.confidence,
                "translation": list(result.translation),
                "rotation_deg": result.rotation_deg,
                "guidance": result.guidance,
                "diagnostics": {
                    "rms_residual": result.diagnostics.rms_residual,
                    "overlap_ratio": result.diagnostics.overlap_ratio,
                    "match_count": result.diagnostics.match_count,
                    "attempts": [
                        {"method": a.method, "success": a.success, "confidence": a.confidence}
                        for a in result.diagnostics.attempts
                    ],
                },
            }

        except ValueError as e:
            raise HTTPException(status_code=400, detail=str(e)) from None
        except Exception as e:
            logger.error("Alignment failed: %s", e, exc_info=True)
            raise HTTPException(status_code=500, detail="Alignment failed") from None


@app.post("/api/revision/diff")
async def revision_diff(body: RevisionDiffRequest, user: dict = Depends(get_user)):
    """Run comparison and generate revision ops."""
    with otel_span("cad.web.revision.diff", {"cad.web.session_id": body.session_id}):
        try:
            session = session_mgr.get(body.session_id, user["uid"])
        except (KeyError, PermissionError) as e:
            raise HTTPException(status_code=404, detail=str(e)) from None

        if session.original_path is None or not session.original_path.exists():
            raise HTTPException(
                status_code=400, detail="No master file loaded. Upload a file first."
            )
        if session.revision_path is None or not session.revision_path.exists():
            raise HTTPException(
                status_code=400,
                detail="No revision file uploaded. Use /api/revision/upload first.",
            )

        try:
            from cad_dxf_agent.core.comparison.approval import build_initial_approvals
            from cad_dxf_agent.core.comparison.engine import ComparisonEngine
            from cad_dxf_agent.core.comparison.revision_ops import comparison_result_to_ops
            from cad_dxf_agent.models.comparison_schema import AlignmentConfig, ComparisonConfig

            # Build config — reuse control points from prior align step if available
            alignment_config = AlignmentConfig(
                enabled=True,
                control_points=session.alignment_control_points,
            )
            loaded_profile = None
            if body.profile:
                from cad_dxf_agent.core.profiles import load_profile

                loaded_profile = load_profile(body.profile)
            config = ComparisonConfig(alignment=alignment_config, profile=loaded_profile)

            engine = ComparisonEngine()
            result = engine.compare(session.original_path, session.revision_path, config)

            ops = comparison_result_to_ops(result)
            approval_set = build_initial_approvals(ops)

            # Store in session
            session.comparison_result = result
            session.revision_ops = ops
            session.approval_set = approval_set

            # Generate outputs for changelog
            session_dir = Path("/tmp/cad-sessions") / session.session_id
            output_dir = session_dir / "comparison"
            outputs = engine.generate_outputs(
                session.original_path, session.revision_path, result, output_dir
            )
            session.comparison_changelog = outputs.changelog
            session.diff_overlay_path = outputs.diff_overlay_path

            diff_response: dict = {
                "summary": result.summary,
                "total_changes": result.total_changes,
                "changelog": outputs.changelog.to_json(),
                "ops": [
                    {
                        "op_id": op.op_id,
                        "op_type": op.op_type.value,
                        "target_handle": op.target_handle,
                        "target_layer": op.target_layer,
                        "description": op.description,
                        "confidence": op.confidence,
                        "status": approval_set.get_decision(op.op_id).status.value
                        if approval_set.get_decision(op.op_id)
                        else "unknown",
                    }
                    for op in ops
                ],
            }
            if result.warnings:
                diff_response["warnings"] = result.warnings
            from cad_dxf_agent.core.comparison.changelog import generate_summary

            diff_summary = generate_summary(result)
            diff_response["diff_summary"] = {
                "headline": diff_summary.headline,
                "warnings": diff_summary.warnings,
                "by_layer": diff_summary.by_layer,
            }
            return diff_response

        except Exception as e:
            logger.error("Diff failed: %s", e, exc_info=True)
            raise HTTPException(status_code=500, detail="Diff failed") from None


@app.post("/api/revision/approve")
async def revision_approve(body: RevisionApproveRequest, user: dict = Depends(get_user)):
    """Approve or reject individual revision ops."""
    with otel_span("cad.web.revision.approve", {"cad.web.session_id": body.session_id}):
        try:
            session = session_mgr.get(body.session_id, user["uid"])
        except (KeyError, PermissionError) as e:
            raise HTTPException(status_code=404, detail=str(e)) from None

        if session.approval_set is None:
            raise HTTPException(
                status_code=400,
                detail="No ops to approve. Run /api/revision/diff first.",
            )

        try:
            from cad_dxf_agent.core.comparison.approval import approve_op, reject_op

            for item in body.approvals:
                if item.action == "approve":
                    approve_op(session.approval_set, item.op_id)
                else:
                    reject_op(session.approval_set, item.op_id)

            approval_set = session.approval_set
            return {
                "ops": [
                    {"op_id": d.op_id, "status": d.status.value} for d in approval_set.decisions
                ],
                "pending_count": len(approval_set.pending_op_ids),
                "approved_count": len(approval_set.approved_op_ids),
                "rejected_count": len(approval_set.rejected_op_ids),
            }

        except ValueError as e:
            raise HTTPException(status_code=400, detail=str(e)) from None
        except Exception as e:
            logger.error("Approve failed: %s", e, exc_info=True)
            raise HTTPException(status_code=500, detail="Approve failed") from None


@app.post("/api/revision/apply")
async def revision_apply(body: RevisionApplyRequest, user: dict = Depends(get_user)):
    """Apply approved revision ops and generate a bundle."""
    with otel_span("cad.web.revision.apply", {"cad.web.session_id": body.session_id}):
        try:
            session = session_mgr.get(body.session_id, user["uid"])
        except (KeyError, PermissionError) as e:
            raise HTTPException(status_code=404, detail=str(e)) from None

        if session.revision_ops is None or session.approval_set is None:
            raise HTTPException(
                status_code=400,
                detail="No revision ops. Run /api/revision/diff first.",
            )

        try:
            import ezdxf

            from cad_dxf_agent.core.comparison.applier import RevisionApplier
            from cad_dxf_agent.core.comparison.bundle import export_bundle

            master_doc = ezdxf.readfile(str(session.original_path))
            applier = RevisionApplier(master_doc)
            apply_result = applier.apply(session.revision_ops, session.approval_set)
            session.apply_result = apply_result

            # Export bundle
            session_dir = Path("/tmp/cad-sessions") / session.session_id
            bundle_dir = session_dir / "bundle"
            bundle = export_bundle(
                master_path=session.original_path,
                revision_path=session.revision_path,
                comparison_result=session.comparison_result,
                apply_result=apply_result,
                ops=session.revision_ops,
                approval_set=session.approval_set,
                updated_doc=master_doc,
                output_dir=bundle_dir,
            )
            session.bundle_dir = bundle_dir

            return {
                "run_id": apply_result.run_id,
                "success_count": apply_result.success_count,
                "failure_count": apply_result.failure_count,
                "bundle_dir": str(bundle.bundle_dir),
            }

        except Exception as e:
            logger.error("Apply failed: %s", e, exc_info=True)
            raise HTTPException(
                status_code=500,
                detail="Apply failed",
            ) from None


@app.get("/api/revision/download")
async def revision_download(
    session_id: str = Query(...),
    user: dict = Depends(get_user),
):
    """Download the revision bundle as a zip file."""
    import io
    import zipfile

    try:
        session = session_mgr.get(session_id, user["uid"])
    except (KeyError, PermissionError) as e:
        raise HTTPException(status_code=404, detail=str(e)) from None

    if session.bundle_dir is None or not session.bundle_dir.exists():
        raise HTTPException(
            status_code=404,
            detail="No bundle available. Run /api/revision/apply first.",
        )

    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        for file_path in session.bundle_dir.iterdir():
            if file_path.is_file():
                zf.write(file_path, arcname=file_path.name)
    buf.seek(0)

    from fastapi.responses import StreamingResponse

    return StreamingResponse(
        buf,
        media_type="application/zip",
        headers={"Content-Disposition": 'attachment; filename="revision_bundle.zip"'},
    )


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _render_pdf_page(pdf_path: Path, output_path: Path, *, dpi: int = 150) -> None:
    """Render first page of a PDF to PNG using PyMuPDF. Fast, no entity limit."""
    import fitz

    doc = fitz.open(str(pdf_path))
    page = doc[0]
    mat = fitz.Matrix(dpi / 72, dpi / 72)
    pix = page.get_pixmap(matrix=mat)
    pix.save(str(output_path))
    doc.close()
    logger.info("Rendered PDF page 1 → %s (%d dpi)", output_path.name, dpi)


def _convert_dwg_to_dxf(dwg_path: Path, output_dir: Path, dest_path: Path) -> list[str]:
    """Convert a DWG file to DXF via ODA, copy to dest_path.

    Returns any conversion warnings.
    Raises HTTPException on failure.
    """
    from cad_dxf_agent.core.converter import convert_to_dxf

    result = convert_to_dxf(dwg_path, output_dir=output_dir)
    if not result.success:
        logger.error("DWG conversion failed — raw error: %s", result.error)
        detail = _user_friendly_conversion_error(result.error, ".dwg")
        raise HTTPException(status_code=422, detail=detail)
    shutil.copy2(str(result.output_path), str(dest_path))
    return result.warnings


def _user_friendly_conversion_error(raw_error: str | None, ext: str) -> str:
    """Map internal converter errors to user-facing messages."""
    if not raw_error:
        return f"Could not process your {ext} file. Please try a different file."
    lower = raw_error.lower()
    if "no pdf library" in lower or "pip install" in lower:
        return (
            "PDF processing is temporarily unavailable. Please try uploading a .dxf file instead."
        )
    if "no vector geometry" in lower or "raster" in lower:
        return (
            "This PDF appears to be a scanned image, not a vector drawing. "
            "Please export as DXF from your CAD software."
        )
    if "no pages" in lower:
        return "This PDF has no pages. Please check the file and try again."
    if "oda file converter" in lower:
        return (
            "DWG conversion is not available on the web. "
            "Please export as DXF from your CAD software."
        )
    return f"Could not convert your {ext} file. Please try exporting as DXF from your CAD software."


def _get_stage_executor():
    """Create a StagePipelineExecutor with all registered handlers."""
    from cad_dxf_agent.llm.stage_executor import StagePipelineExecutor
    from cad_dxf_agent.llm.stage_handlers.analyze_handler import AnalyzeHandler
    from cad_dxf_agent.llm.stage_handlers.compliance_handler import ComplianceHandler
    from cad_dxf_agent.llm.stage_handlers.detect_zones_handler import DetectZonesHandler

    executor = StagePipelineExecutor()
    executor.register("analyze", AnalyzeHandler())
    executor.register("detect_zones", DetectZonesHandler())
    executor.register("compliance_check", ComplianceHandler())
    return executor


def _enrich_with_objective(
    response: dict,
    objective: ObjectiveClassification | None,
) -> dict:
    """Add objective classification metadata to a response dict.

    Populates request_class, objective_tag, document_family, and stage_pipeline.
    Strategy lookup runs here so every response carries pipeline metadata.
    Backward compatible — fields are additive. Existing clients ignore them.
    """
    if objective is None:
        return response
    response["request_class"] = getattr(objective, "request_class", None)
    if response["request_class"] is not None:
        response["request_class"] = str(response["request_class"])
    tag = getattr(objective, "objective_tag", None)
    response["objective_tag"] = str(tag) if tag is not None else None
    family = getattr(objective, "document_family", None)
    response["document_family"] = str(family) if family is not None else None

    # Strategy lookup — populate stage_pipeline so consumers see which
    # stages *would* run for this classification. Actual dispatch still
    # uses the TaskFamily if/elif chain; stage execution comes later.
    try:
        from cad_dxf_agent.llm.strategy_registry import StrategyRegistry

        registry = StrategyRegistry()
        pipeline_def = registry.lookup(objective.request_class, objective.objective_tag)
        response["stage_pipeline"] = pipeline_def.model_dump()
    except Exception:
        logger.debug("Strategy lookup failed, skipping stage_pipeline", exc_info=True)

    return response


def _enrich_with_precision(
    changeset: ChangeSet,
    context: DrawingContext,
    validation: Any,
    client_metadata: dict | None,
) -> tuple[list[dict] | None, list[dict] | None]:
    """Build precision enrichment data from client_metadata.

    Returns (ambiguity_candidates, precision_actions) — both None if no
    precision controls are present.
    """
    from cad_dxf_agent.core.precision_filter import (
        apply_entity_filter,
        apply_exact_delta,
        build_action_details,
        build_match_candidates,
        parse_precision_controls,
    )

    controls = parse_precision_controls(client_metadata)
    if controls is None:
        return None, None

    # Apply exact delta overrides to move operations
    if controls.exact_delta:
        changeset.operations = apply_exact_delta(changeset.operations, controls.exact_delta)

    # Build match candidates for ambiguity reporting
    filtered = apply_entity_filter(list(context.entities), controls)
    candidates = build_match_candidates(filtered, controls)
    candidates_dicts = [c.model_dump() for c in candidates] if candidates else None

    # Build action details
    details = build_action_details(changeset, context, validation)
    details_dicts = [d.model_dump() for d in details] if details else None

    return candidates_dicts, details_dicts


def _parse_selected_region(selected_regions: list[dict] | None):
    """Parse the first selected region dict into a NormalizedRegion, or None."""
    if not selected_regions:
        return None
    try:
        from cad_dxf_agent.models.cad_schema import Point2D
        from cad_dxf_agent.models.region_schema import BoundingBox, NormalizedRegion, RegionType

        r = selected_regions[0]
        bounds = r.get("bounds", {})
        min_x = float(bounds.get("min_x", 0))
        min_y = float(bounds.get("min_y", 0))
        max_x = float(bounds.get("max_x", 0))
        max_y = float(bounds.get("max_y", 0))
        return NormalizedRegion(
            source_type=RegionType(r.get("source_type", "box_select")),
            bounds=BoundingBox(min_x=min_x, min_y=min_y, max_x=max_x, max_y=max_y),
            center=Point2D(x=(min_x + max_x) / 2, y=(min_y + max_y) / 2),
        )
    except (KeyError, ValueError, TypeError):
        logger.debug("Failed to parse selected_region: %s", selected_regions, exc_info=True)
        return None


def _describe_op(op) -> str:
    """Build a human-readable description of an operation."""
    op_type = op.op_type.value if hasattr(op.op_type, "value") else str(op.op_type)

    if op_type == "move_entity":
        dx = op.params.get("dx", 0)
        dy = op.params.get("dy", 0)
        return f"Move entity {op.target_handle} by ({dx}, {dy})"
    elif op_type == "edit_text":
        new_text = op.params.get("new_text", "")
        return f'Change text on entity {op.target_handle} to "{new_text}"'
    elif op_type == "delete_entity":
        return f"Delete entity {op.target_handle} on layer {op.target_layer or '?'}"
    elif op_type == "add_block":
        block_name = op.params.get("block_name", "")
        return f'Insert block "{block_name}" on layer {op.target_layer or "0"}'
    else:
        return f"{op_type} on entity {op.target_handle}"

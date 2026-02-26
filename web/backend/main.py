"""CAD DXF Agent — Web Backend (FastAPI on Cloud Run).

Routes:
    GET  /api/health     — Health check
    POST /api/upload     — Upload DXF/PDF, get session + file info
    POST /api/plan       — Send prompt, get planned operations + preview
    POST /api/apply      — Apply selected operations
    POST /api/compare    — Upload revision DXF, compare against master
    GET  /api/render     — Get PNG render (original/edited/diff/comparison)
    GET  /api/download   — Download edited DXF
"""

from __future__ import annotations

import logging
import os
import shutil
import sys
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import Depends, FastAPI, File, HTTPException, Query, Request, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse
from pydantic import BaseModel

# Add src/ to path so we can import the existing pipeline
PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(PROJECT_ROOT / "src"))

from cad_dxf_agent.otel import span as otel_span  # noqa: E402

from .auth import verify_token
from .session import Session, SessionManager

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------
MAX_CONVERSATION_HISTORY = 10  # Max user+model entries kept per session

# ---------------------------------------------------------------------------
# Session manager (singleton)
# ---------------------------------------------------------------------------
session_mgr = SessionManager()


@asynccontextmanager
async def lifespan(app: FastAPI):
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")

    from cad_dxf_agent.otel import init_otel

    init_otel(service_name="cad-dxf-web")
    logger.info("CAD DXF Web Backend starting")
    yield
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

app.add_middleware(
    CORSMiddleware,
    allow_origins=ALLOWED_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ---------------------------------------------------------------------------
# Request / response schemas
# ---------------------------------------------------------------------------


class PlanRequest(BaseModel):
    session_id: str
    prompt: str


class ApplyRequest(BaseModel):
    session_id: str
    selected_ops: list[int] | None = None


class ClearHistoryRequest(BaseModel):
    session_id: str


# ---------------------------------------------------------------------------
# Dependency: get authenticated user
# ---------------------------------------------------------------------------


async def get_user(request: Request) -> dict:
    return await verify_token(request)


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------


@app.get("/api/health")
async def health():
    return {"status": "ok", "service": "cad-dxf-web"}


@app.post("/api/upload")
async def upload(
    file: UploadFile = File(...),
    user: dict = Depends(get_user),
):
    """Upload a DXF or PDF file and start a session."""
    if not file.filename:
        raise HTTPException(status_code=400, detail="No file provided")

    ext = Path(file.filename).suffix.lower()
    if ext not in (".dxf", ".pdf"):
        raise HTTPException(status_code=400, detail=f"Unsupported file type: {ext}")

    session = session_mgr.create(user_id=user["uid"])
    session_dir = Path("/tmp/cad-sessions") / session.session_id

    # Save uploaded file
    upload_path = session_dir / f"upload{ext}"
    content = await file.read()
    upload_path.write_bytes(content)

    # Convert if needed
    dxf_path = session.original_path
    if ext == ".pdf":
        try:
            from cad_dxf_agent.core.converter import convert_to_dxf

            result = convert_to_dxf(upload_path)
            if not result.success:
                detail = _user_friendly_conversion_error(result.error, ext)
                raise HTTPException(status_code=422, detail=detail)
            shutil.copy2(str(result.output_path), str(dxf_path))
        except ImportError:
            raise HTTPException(
                status_code=500,
                detail="PDF conversion is temporarily unavailable. Please try a .dxf file.",
            )
    else:
        shutil.copy2(str(upload_path), str(dxf_path))

    # Also copy as working file
    session.working_path = session_dir / "working.dxf"
    shutil.copy2(str(dxf_path), str(session.working_path))

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
        raise HTTPException(status_code=422, detail=f"Failed to read DXF: {e}")

    # Render original preview
    try:
        from cad_dxf_agent.core.renderer import render_dxf_to_png

        render_result = render_dxf_to_png(dxf_path, session_dir / "original.png")
        if render_result.success:
            session.original_render = render_result.output_path
        else:
            logger.warning("Original render returned failure: %s", render_result.error)
    except Exception as e:
        logger.warning("Original render failed (non-fatal): %s", e, exc_info=True)

    return {
        "session_id": session.session_id,
        "file_info": session.file_info,
    }


@app.post("/api/plan")
async def plan(body: PlanRequest, user: dict = Depends(get_user)):
    """Run the planner on a user prompt for an uploaded file."""
    try:
        session = session_mgr.get(body.session_id, user["uid"])
    except (KeyError, PermissionError) as e:
        raise HTTPException(status_code=404, detail=str(e))

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
            operations.append({
                "op_type": op.op_type.value if hasattr(op.op_type, "value") else str(op.op_type),
                "target_handle": op.target_handle,
                "target_layer": op.target_layer,
                "description": _describe_op(op),
                "params": op.params,
            })

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
        raise HTTPException(status_code=500, detail=f"Planning failed: {e}")


@app.post("/api/apply")
async def apply_changes(body: ApplyRequest, user: dict = Depends(get_user)):
    """Apply (selected) operations from the last plan."""
    try:
        session = session_mgr.get(body.session_id, user["uid"])
    except (KeyError, PermissionError) as e:
        raise HTTPException(status_code=404, detail=str(e))

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
                for i in body.selected_ops
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

        # Render edited preview
        try:
            from cad_dxf_agent.core.renderer import render_dxf_to_png

            render_result = render_dxf_to_png(
                session.edited_path, session_dir / "edited.png"
            )
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
        return {
            "message": f"Applied {success_count}/{len(results)} operations.",
            "render_available": render_available,
            "results": [
                {"success": r.success, "message": r.message if hasattr(r, "message") else ""}
                for r in results
            ],
        }

    except Exception as e:
        logger.error("Apply failed: %s", e, exc_info=True)
        raise HTTPException(status_code=500, detail=f"Apply failed: {e}")


@app.post("/api/clear-history")
async def clear_history(body: ClearHistoryRequest, user: dict = Depends(get_user)):
    """Clear conversation history for a session (keep the file loaded)."""
    try:
        session = session_mgr.get(body.session_id, user["uid"])
    except (KeyError, PermissionError) as e:
        raise HTTPException(status_code=404, detail=str(e))

    session.conversation_history = []
    session.changeset = None
    return {"message": "Conversation cleared."}


@app.post("/api/compare")
async def compare(
    file: UploadFile = File(...),
    session_id: str = Query(...),
    user: dict = Depends(get_user),
):
    """Upload a revision DXF and compare against the session's master file."""
    with otel_span("cad.web.compare", {"cad.web.session_id": session_id}) as s:
        if not file.filename:
            raise HTTPException(status_code=400, detail="No file provided")

        ext = Path(file.filename).suffix.lower()
        if ext != ".dxf":
            raise HTTPException(status_code=400, detail="Comparison requires a .dxf file")

        try:
            session = session_mgr.get(session_id, user["uid"])
        except (KeyError, PermissionError) as e:
            raise HTTPException(status_code=404, detail=str(e))

        if session.original_path is None or not session.original_path.exists():
            raise HTTPException(
                status_code=400, detail="No master file loaded. Upload a file first."
            )

        # Save revision file
        session_dir = Path("/tmp/cad-sessions") / session.session_id
        revision_path = session_dir / "revision.dxf"
        content = await file.read()
        revision_path.write_bytes(content)

        try:
            from cad_dxf_agent.core.comparison.engine import ComparisonEngine

            engine = ComparisonEngine()
            result = engine.compare(session.original_path, revision_path)

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

            return {
                "summary": result.summary,
                "total_changes": result.total_changes,
                "changelog": outputs.changelog.to_json(),
                "render_available": session.diff_overlay_render is not None,
            }

        except FileNotFoundError as e:
            raise HTTPException(status_code=400, detail=str(e))
        except Exception as e:
            logger.error("Comparison failed: %s", e, exc_info=True)
            raise HTTPException(status_code=500, detail=f"Comparison failed: {e}")


@app.get("/api/render")
async def render(
    session_id: str = Query(...),
    type: str = Query("original"),
):
    """Return a PNG render of the drawing.

    No auth required — the session UUID is unguessable and serves as
    the access credential.  This avoids the problem where Firebase
    Hosting rewrites strip the Authorization header on proxied GETs.
    """
    try:
        session = session_mgr.get_by_id(session_id)
    except KeyError as e:
        raise HTTPException(status_code=404, detail=str(e))

    render_map = {
        "original": session.original_render,
        "edited": session.edited_render,
        "diff": session.diff_render,
        "comparison": session.diff_overlay_render,
    }
    path = render_map.get(type)

    if path is None or not path.exists():
        raise HTTPException(status_code=404, detail=f"No {type} render available")

    return FileResponse(
        path=str(path),
        media_type="image/png",
        filename=f"{type}.png",
    )


@app.get("/api/download")
async def download(
    session_id: str = Query(...),
):
    """Download the edited DXF file.

    No auth required — same rationale as /api/render (Firebase rewrites
    strip Authorization headers on proxied GET requests).
    """
    try:
        session = session_mgr.get_by_id(session_id)
    except KeyError as e:
        raise HTTPException(status_code=404, detail=str(e))

    if session.edited_path is None or not session.edited_path.exists():
        raise HTTPException(status_code=404, detail="No edited file available. Run /api/apply first.")

    # Build download filename from original
    original_name = session.file_info.get("filename", "drawing.dxf")
    stem = Path(original_name).stem
    download_name = f"{stem}_edited.dxf"

    return FileResponse(
        path=str(session.edited_path),
        media_type="application/dxf",
        filename=download_name,
        headers={"Content-Disposition": f'attachment; filename="{download_name}"'},
    )


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _user_friendly_conversion_error(raw_error: str | None, ext: str) -> str:
    """Map internal converter errors to user-facing messages."""
    if not raw_error:
        return f"Could not process your {ext} file. Please try a different file."
    lower = raw_error.lower()
    if "no pdf library" in lower or "pip install" in lower:
        return "PDF processing is temporarily unavailable. Please try uploading a .dxf file instead."
    if "no vector geometry" in lower or "raster" in lower:
        return (
            "This PDF appears to be a scanned image, not a vector drawing. "
            "Please export as DXF from your CAD software."
        )
    if "no pages" in lower:
        return "This PDF has no pages. Please check the file and try again."
    if "oda file converter" in lower:
        return "DWG conversion is not available on the web. Please export as DXF from your CAD software."
    return f"Could not convert your {ext} file. Please try exporting as DXF from your CAD software."


def _describe_op(op) -> str:
    """Build a human-readable description of an operation."""
    op_type = op.op_type.value if hasattr(op.op_type, "value") else str(op.op_type)

    if op_type == "move_entity":
        dx = op.params.get("dx", 0)
        dy = op.params.get("dy", 0)
        return f"Move entity {op.target_handle} by ({dx}, {dy})"
    elif op_type == "edit_text":
        new_text = op.params.get("new_text", "")
        return f"Change text on entity {op.target_handle} to \"{new_text}\""
    elif op_type == "delete_entity":
        return f"Delete entity {op.target_handle} on layer {op.target_layer or '?'}"
    elif op_type == "add_block":
        block_name = op.params.get("block_name", "")
        return f"Insert block \"{block_name}\" on layer {op.target_layer or '0'}"
    else:
        return f"{op_type} on entity {op.target_handle}"

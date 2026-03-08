"""CAD DXF Agent — Web Backend (FastAPI on Cloud Run).

Routes:
    GET  /api/health            — Health check
    POST /api/upload            — Upload DXF/PDF, get session + file info
    POST /api/plan              — Send prompt, get planned operations + preview
    POST /api/apply             — Apply selected operations
    POST /api/compare           — Upload revision DXF, compare against master
    GET  /api/dxf               — Get raw DXF file (original/edited/comparison)
    GET  /api/render            — Get PNG render (original/edited/diff/comparison)
    GET  /api/download          — Download edited DXF
    POST /api/revision/upload   — Upload revision DXF to existing session
    POST /api/revision/align    — Run alignment (auto or manual control points)
    POST /api/revision/diff     — Run comparison + generate revision ops
    POST /api/revision/approve  — Approve/reject individual revision ops
    POST /api/revision/apply    — Apply approved ops + export bundle
    GET  /api/revision/download — Download bundle as zip
"""

from __future__ import annotations

import logging
import os
import shutil
import sys
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Literal

from fastapi import Depends, FastAPI, File, HTTPException, Query, Request, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from pydantic import BaseModel

# Add src/ to path so we can import the existing pipeline
PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(PROJECT_ROOT / "src"))

from cad_dxf_agent.otel import span as otel_span  # noqa: E402

from .auth import get_licensed_user
from .session import SessionManager

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
            request.method, request.url.path, response.status_code, elapsed_ms,
        )
    else:
        logger.info(
            "%s %s → %d (%.0fms)",
            request.method, request.url.path, response.status_code, elapsed_ms,
        )
    return response


# ---------------------------------------------------------------------------
# Request / response schemas
# ---------------------------------------------------------------------------


class PromptRequest(BaseModel):
    session_id: str
    prompt: str
    selected_regions: list[dict] | None = None


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


# ---------------------------------------------------------------------------
# Dependency: get authenticated user
# ---------------------------------------------------------------------------


async def get_user(request: Request) -> dict:
    return await get_licensed_user(request)


# ---------------------------------------------------------------------------
# Shared helpers
# ---------------------------------------------------------------------------


def _build_typed_compare_response(
    result: "ComparisonResult",  # noqa: F821 — forward ref, imported at call site
    outputs: "ComparisonOutputs",  # noqa: F821
    *,
    audit: "AuditMetadata | None" = None,  # noqa: F821
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


@app.get("/api/profiles")
async def get_profiles():
    """List available comparison profiles (builtins only)."""
    from cad_dxf_agent.core.profiles import BUILTIN_PROFILES

    return {name: p.model_dump() for name, p in BUILTIN_PROFILES.items()}


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

    # Save uploaded file — enforce size limit (ARCH-REVIEW-CAD-01 P0)
    MAX_UPLOAD_SIZE = 25 * 1024 * 1024  # 25 MB
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
        raise HTTPException(status_code=422, detail=f"Failed to read DXF: {e}") from None

    # Render original preview
    # For PDF uploads: render first page directly (fast, no entity limit concern)
    # For DXF uploads: use ezdxf renderer (skip if too many entities — OOM risk)
    RENDER_ENTITY_LIMIT = 100_000
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
            context.entity_count, RENDER_ENTITY_LIMIT,
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
        raise HTTPException(status_code=500, detail=f"Planning failed: {e}") from None


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
        objective_cls = ObjectiveClassifier()
        objective = objective_cls.classify_with_family(body.prompt, intent.family)

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
            return _enrich(ResponseBuilder.unsupported_operation(
                family=intent.family, audit=audit,
            ).model_dump())

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
                prompt=body.prompt, context=session.context, region=region,
            )
            audit.context_build_time_ms = (_time.monotonic() - ctx_start) * 1000
            audit.total_request_time_ms = (_time.monotonic() - total_start) * 1000
            result.audit = audit
            return _enrich(result.model_dump())

        # Handle compare (requires revision file)
        if intent.family == TaskFamily.COMPARE:
            if session.revision_path is None or not session.revision_path.exists():
                audit.total_request_time_ms = (_time.monotonic() - total_start) * 1000
                return _enrich(ResponseBuilder.needs_clarification(
                    message="Upload a revision file first to compare drawings.",
                    family=TaskFamily.COMPARE,
                    audit=audit,
                ).model_dump())

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
                return _enrich(_build_typed_compare_response(
                    session.comparison_result, outputs, audit=audit
                ))

            audit.total_request_time_ms = (_time.monotonic() - total_start) * 1000
            return _enrich(ResponseBuilder.needs_clarification(
                message="Use /api/compare for full comparison workflow.",
                family=TaskFamily.COMPARE,
                audit=audit,
            ).model_dump())

        # Handle markup_interpretation — deterministic redline report, no LLM
        if intent.family == TaskFamily.MARKUP_INTERPRETATION:
            from cad_dxf_agent.core.construction_ops import MarkupRedlineGenerator

            ctx_start = _time.monotonic()
            result = MarkupRedlineGenerator().generate(session.context, body.prompt)
            audit.context_build_time_ms = (_time.monotonic() - ctx_start) * 1000
            audit.total_request_time_ms = (_time.monotonic() - total_start) * 1000

            return _enrich(ResponseBuilder.markup_redline(
                message=(
                    f"{result.total_clouds} revision cloud(s) found, "
                    f"{result.total_affected_entities} affected entity(ies)."
                ),
                data=result.model_dump(),
                confidence=result.aggregate_confidence,
                ambiguity_flags=result.ambiguity_flags,
                audit=audit,
            ).model_dump())

        # Handle repeated_condition — deterministic, no LLM
        if intent.family == TaskFamily.REPEATED_CONDITION:
            from cad_dxf_agent.core.repeated_condition import ConditionDetector

            exemplar_handles = body.selected_regions[0].get("handles", []) if body.selected_regions else []
            prompt_lower = body.prompt.lower()
            is_batch = not exemplar_handles and any(
                kw in prompt_lower for kw in (
                    "batch", "all conditions", "condition report",
                    "condition plan", "find all patterns",
                )
            )

            if is_batch:
                from cad_dxf_agent.core.construction_ops import BatchConditionPlanner

                ctx_start = _time.monotonic()
                result = BatchConditionPlanner().plan(session.context, body.prompt)
                audit.context_build_time_ms = (_time.monotonic() - ctx_start) * 1000
                audit.total_request_time_ms = (_time.monotonic() - total_start) * 1000

                return _enrich(ResponseBuilder.repeated_condition(
                    message=(
                        f"{result.total_groups} condition group(s), "
                        f"{result.total_instances} total instance(s)."
                    ),
                    data=result.model_dump(),
                    confidence=result.aggregate_confidence,
                    ambiguity_flags=result.ambiguity_flags,
                    audit=audit,
                ).model_dump())

            if not exemplar_handles:
                audit.total_request_time_ms = (_time.monotonic() - total_start) * 1000
                return _enrich(ResponseBuilder.needs_clarification(
                    message="Select entities to use as the exemplar for repeated-condition search.",
                    family=TaskFamily.REPEATED_CONDITION,
                    audit=audit,
                ).model_dump())

            ctx_start = _time.monotonic()
            detector = ConditionDetector(session.context)
            result = detector.find_repeated(exemplar_handles)
            audit.context_build_time_ms = (_time.monotonic() - ctx_start) * 1000
            audit.total_request_time_ms = (_time.monotonic() - total_start) * 1000

            return _enrich(ResponseBuilder.repeated_condition(
                message=result.summary,
                data=result.model_dump(),
                evidence=[ev.model_dump() for c in result.candidates for ev in c.evidence[:3]],
                confidence=result.candidates[0].confidence if result.candidates else 0.0,
                ambiguity_flags=result.ambiguity_flags,
                audit=audit,
            ).model_dump())

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
                kw in prompt_lower for kw in (
                    "field summary", "field report",
                    "construction summary", "site report",
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
                kw in prompt_lower for kw in (
                    "grid", "bay", "column grid", "structural grid",
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
                    session.context, body.prompt, region,
                )
                data = result.model_dump()
                message = (
                    f"{result.total_recommendations} recommendation(s). "
                    f"{result.drawing_summary}"
                )
                confidence = result.aggregate_confidence
                flags = result.ambiguity_flags

            audit.context_build_time_ms = (_time.monotonic() - ctx_start) * 1000
            audit.total_request_time_ms = (_time.monotonic() - total_start) * 1000

            return _enrich(ResponseBuilder.design_assist(
                message=message,
                data=data,
                confidence=confidence,
                ambiguity_flags=flags,
                audit=audit,
            ).model_dump())

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

            return _enrich(ResponseBuilder.summary_result(
                message=result.headline,
                data=result.model_dump(),
                confidence=min(
                    (e.confidence for e in result.key_changes), default=0.5,
                ),
                ambiguity_flags=result.ambiguity_flags,
                audit=audit,
            ).model_dump())

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
                session.context, body.prompt, region,
            )
            audit.context_build_time_ms = (_time.monotonic() - ctx_start) * 1000
            audit.total_request_time_ms = (_time.monotonic() - total_start) * 1000

            _conf_labels = {
                "high": 0.95,
                "medium": 0.7,
                "low": 0.4,
                "estimate_only": 0.2,
            }
            return _enrich(ResponseBuilder.takeoff_result(
                message=(
                    f"{result.total_items} takeoff item(s), "
                    f"{result.total_quantity_items} total quantity."
                ),
                data=result.model_dump(),
                confidence=_conf_labels.get(result.aggregate_confidence.value, 0.5),
                ambiguity_flags=result.ambiguity_flags,
                audit=audit,
            ).model_dump())

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
                    from cad_dxf_agent.llm.plan_builder import EditPlanBuilder, PlanRequest as PlanReq

                    plan_req = PlanReq(
                        prompt=body.prompt,
                        drawing_context=session.context,
                        request_id=getattr(body, "request_id", ""),
                        target_handles=[
                            op.target_handle
                            for op in changeset.operations
                            if op.target_handle
                        ] or None,
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

                audit.total_request_time_ms = (_time.monotonic() - total_start) * 1000

                return _enrich(ResponseBuilder.plan_only(
                    operations=operations,
                    message=llm_message or summary,
                    validation={
                        "blockers": [{"message": b.message} for b in validation.blockers],
                        "warnings": [{"message": w.message} for w in validation.warnings],
                        "is_valid": len(validation.blockers) == 0,
                    },
                    audit=audit,
                ).model_dump())

            except Exception as e:
                logger.error("v2 plan failed: %s", e, exc_info=True)
                raise HTTPException(status_code=500, detail=f"Planning failed: {e}") from None

        # Catch-all for families that are "implemented" but not yet wired
        audit.total_request_time_ms = (_time.monotonic() - total_start) * 1000
        return _enrich(ResponseBuilder.unsupported_operation(
            family=intent.family, audit=audit,
        ).model_dump())


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
    return ResponseBuilder.structured_apply_result(
        result=result,
        audit=audit,
    ).model_dump()


@app.post("/api/apply")
async def apply_changes(body: ApplyRequest, user: dict = Depends(get_user)):
    """Apply (selected) operations from the last plan."""
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
        raise HTTPException(status_code=500, detail=f"Apply failed: {e}") from None


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

        # Save uploaded file
        session_dir = Path("/tmp/cad-sessions") / session.session_id
        revision_path = session_dir / "revision.dxf"

        if ext == ".dwg":
            dwg_path = session_dir / "revision_upload.dwg"
            content = await file.read()
            dwg_path.write_bytes(content)
            _convert_dwg_to_dxf(dwg_path, output_dir=session_dir, dest_path=revision_path)
        else:
            content = await file.read()
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
            raise HTTPException(status_code=500, detail=f"Comparison failed: {e}") from None


@app.get("/api/dxf")
async def get_dxf_file(
    session_id: str = Query(...),
    render_type: str = Query("original", alias="type"),
):
    """Serve raw DXF for client-side WebGL rendering.

    No auth required — same rationale as /api/render (Firebase rewrites
    strip Authorization headers on proxied GET requests).
    """
    try:
        session = session_mgr.get_by_id(session_id)
    except KeyError as e:
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
):
    """Return a PNG render of the drawing.

    No auth required — the session UUID is unguessable and serves as
    the access credential.  This avoids the problem where Firebase
    Hosting rewrites strip the Authorization header on proxied GETs.
    """
    try:
        session = session_mgr.get_by_id(session_id)
    except KeyError as e:
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
):
    """Download the edited file as DXF or DWG.

    No auth required — same rationale as /api/render (Firebase rewrites
    strip Authorization headers on proxied GET requests).

    Query params:
        format: "dxf" (default) or "dwg" (converts via ODA before download).
    """
    try:
        session = session_mgr.get_by_id(session_id)
    except KeyError as e:
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

        session_dir = Path("/tmp/cad-sessions") / session.session_id
        revision_path = session_dir / "revision.dxf"

        if ext == ".dwg":
            dwg_path = session_dir / "revision_upload.dwg"
            content = await file.read()
            dwg_path.write_bytes(content)
            _convert_dwg_to_dxf(dwg_path, output_dir=session_dir, dest_path=revision_path)
        else:
            content = await file.read()
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
            raise HTTPException(status_code=500, detail=f"Alignment failed: {e}") from None


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
            raise HTTPException(status_code=500, detail=f"Diff failed: {e}") from None


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
            raise HTTPException(status_code=500, detail=f"Approve failed: {e}") from None


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
            raise HTTPException(status_code=500, detail=f"Apply failed: {e}") from None


@app.get("/api/revision/download")
async def revision_download(session_id: str = Query(...)):
    """Download the revision bundle as a zip file.

    No auth required — same rationale as /api/render (Firebase rewrites
    strip Authorization headers on proxied GET requests).
    """
    import io
    import zipfile

    try:
        session = session_mgr.get_by_id(session_id)
    except KeyError as e:
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


def _enrich_with_objective(
    response: dict,
    objective: object | None,
) -> dict:
    """Add objective classification metadata to a response dict.

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
    return response


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

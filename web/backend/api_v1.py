"""API v1 — stateless drawing intelligence endpoints for agent consumption.

Every endpoint accepts a DXF file upload and returns structured JSON.
No session, no auth (initially) — designed for CLI tools, CI/CD pipelines,
MCP servers, and AI agents that need headless drawing analysis.

Routes:
    POST /api/v1/analyze     → DrawingContext summary + entity stats
    POST /api/v1/health      → HealthReport (score, issues, evidence)
    POST /api/v1/zones       → ZoneDetectionResult (rooms, areas)
    POST /api/v1/entities    → Filtered entity search
    POST /api/v1/compliance  → ComplianceReport (findings, code refs, score)
    POST /api/v1/takeoff     → TakeoffReport (item counts, measurements)
    POST /api/v1/summary     → Plain-English drawing summary
    POST /api/v1/rfi         → RFI report (missing items, ambiguities)
"""

from __future__ import annotations

import logging
import tempfile
from pathlib import Path

from fastapi import APIRouter, File, HTTPException, Query, UploadFile

from cad_dxf_agent.core.dxf_reader import load_dxf
from cad_dxf_agent.core.entity_index import EntityIndex
from cad_dxf_agent.otel import span as otel_span

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1", tags=["v1-agent"])


def _save_upload(file: UploadFile) -> Path:
    """Save uploaded file to a temp path and return it."""
    if not file.filename:
        raise HTTPException(400, "No filename provided")

    suffix = Path(file.filename).suffix.lower()
    if suffix not in (".dxf", ".dwg"):
        raise HTTPException(
            400, f"Unsupported file type: {suffix}. Expected .dxf or .dwg"
        )

    with tempfile.NamedTemporaryFile(
        suffix=suffix, delete=False, prefix="cadv1_"
    ) as tmp:
        data = file.file.read()
        tmp.write(data)
        tmp.flush()
        return Path(tmp.name)


def _load_context(file: UploadFile):
    """Upload → save → load_dxf → DrawingContext."""
    path = _save_upload(file)
    try:
        return load_dxf(str(path))
    except Exception as e:
        raise HTTPException(400, f"Failed to parse DXF: {e}") from None
    finally:
        path.unlink(missing_ok=True)


# ---------------------------------------------------------------------------
# POST /api/v1/analyze
# ---------------------------------------------------------------------------


@router.post("/analyze")
async def analyze(file: UploadFile = File(...)):
    """Analyze a DXF file and return a structured drawing context summary.

    Returns entity counts, layer breakdown, entity type distribution,
    and drawing metadata.
    """
    with otel_span("api.v1.analyze"):
        context = _load_context(file)
        index = EntityIndex(context)

        # Layer breakdown
        layers = []
        for layer in context.layers:
            entities = index.get_by_layer(layer.name)
            layers.append({
                "name": layer.name,
                "entity_count": len(entities),
                "color": layer.color,
            })

        # Entity type distribution
        type_counts: dict[str, int] = {}
        for entity in context.entities:
            t = entity.entity_type.value
            type_counts[t] = type_counts.get(t, 0) + 1

        return {
            "entity_count": context.entity_count,
            "layer_count": len(context.layers),
            "layers": layers,
            "entity_types": type_counts,
            "blocks": context.blocks,
            "metadata": context.metadata,
        }


# ---------------------------------------------------------------------------
# POST /api/v1/health
# ---------------------------------------------------------------------------


@router.post("/health")
async def health_check(file: UploadFile = File(...)):
    """Run deterministic health checks on a DXF file.

    Returns a scored health report with categorized issues and
    entity-level evidence references.
    """
    with otel_span("api.v1.health"):
        context = _load_context(file)

        try:
            from cad_dxf_agent.core.health_checker import check_drawing_health
        except ImportError:
            raise HTTPException(
                501, "Health checker not available"
            ) from None

        report = check_drawing_health(context, include_zones=False)

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


# ---------------------------------------------------------------------------
# POST /api/v1/zones
# ---------------------------------------------------------------------------


@router.post("/zones")
async def detect_zones(file: UploadFile = File(...)):
    """Detect enclosed zones/rooms in a DXF file.

    Returns detected zones with area, perimeter, centroid, and
    inferred room type when text labels are present.
    """
    with otel_span("api.v1.zones"):
        context = _load_context(file)

        from cad_dxf_agent.core.zone_detector import detect_zones as run_zones

        result = run_zones(context)

        zones = []
        for z in result.zones:
            zone_data: dict = {
                "zone_id": z.zone_id,
                "area": z.area,
                "perimeter": z.perimeter,
                "centroid": {"x": z.centroid.x, "y": z.centroid.y},
                "boundary_points": len(z.boundary),
                "inferred_type": z.inferred_type,
                "confidence": z.confidence,
            }
            zones.append(zone_data)

        return {
            "zone_count": result.zone_count,
            "total_area": result.total_area,
            "zones": zones,
        }


# ---------------------------------------------------------------------------
# POST /api/v1/entities
# ---------------------------------------------------------------------------


@router.post("/entities")
async def search_entities(
    file: UploadFile = File(...),
    layer: str | None = Query(None, description="Filter by layer name"),
    entity_type: str | None = Query(
        None, description="Filter by entity type (LINE, TEXT, etc.)"
    ),
    text_contains: str | None = Query(
        None, description="Filter TEXT/MTEXT by content substring"
    ),
    limit: int = Query(100, ge=1, le=1000, description="Max entities to return"),
):
    """Search entities in a DXF file with optional filters.

    Returns matching entities with handles, types, layers, positions,
    and text content.
    """
    with otel_span("api.v1.entities"):
        context = _load_context(file)
        index = EntityIndex(context)

        candidates = index.filter(layer=layer, entity_type=entity_type)

        if text_contains:
            text_matches = index.search_text(text_contains)
            match_handles = {e.handle for e in text_matches}
            candidates = [
                e for e in candidates if e.handle in match_handles
            ]

        total = len(candidates)
        entities = []
        for e in candidates[:limit]:
            d: dict = {
                "handle": e.handle,
                "type": e.entity_type.value,
                "layer": e.layer,
            }
            if e.insert_point:
                d["x"] = e.insert_point.x
                d["y"] = e.insert_point.y
            if e.text_content:
                d["text"] = e.text_content
            if e.block_name:
                d["block_name"] = e.block_name
            entities.append(d)

        return {
            "total": total,
            "returned": len(entities),
            "truncated": total > limit,
            "entities": entities,
        }


# ---------------------------------------------------------------------------
# POST /api/v1/compliance
# ---------------------------------------------------------------------------


@router.post("/compliance")
async def compliance_check(
    file: UploadFile = File(...),
    profile: str = Query("ibc-2021", description="Compliance profile (ada, ibc-2021, residential)"),
):
    """Run regulation-aware compliance validation on a DXF file.

    Checks the drawing against a building code profile and returns
    a structured report with findings, code references, and score.
    """
    with otel_span("api.v1.compliance"):
        context = _load_context(file)

        from cad_dxf_agent.core.compliance_rules import check_compliance
        from cad_dxf_agent.models.compliance_schema import BUILTIN_PROFILES

        if profile not in BUILTIN_PROFILES:
            raise HTTPException(
                422,
                f"Unknown profile: {profile}. "
                f"Available: {', '.join(BUILTIN_PROFILES)}",
            )

        report = check_compliance(context, profile=profile)

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


# ---------------------------------------------------------------------------
# POST /api/v1/takeoff
# ---------------------------------------------------------------------------


@router.post("/takeoff")
async def takeoff(file: UploadFile = File(...)):
    """Generate automated quantity takeoff from a DXF file.

    Returns counted items grouped by category with entity-level
    evidence (source handles).
    """
    with otel_span("api.v1.takeoff"):
        context = _load_context(file)

        from cad_dxf_agent.core.design_ops import TakeoffGenerator

        generator = TakeoffGenerator()
        result = generator.generate(context, prompt="full takeoff")

        return result.model_dump()


# ---------------------------------------------------------------------------
# POST /api/v1/summary
# ---------------------------------------------------------------------------


@router.post("/summary")
async def summary(file: UploadFile = File(...)):
    """Generate a plain-English summary of a DXF drawing.

    Returns a structured summary with headline, sections, and
    key statistics — no CAD knowledge required to understand.
    """
    with otel_span("api.v1.summary"):
        context = _load_context(file)

        from cad_dxf_agent.core.drawing_summarizer import summarize_drawing

        result = summarize_drawing(context)

        return result.model_dump()


# ---------------------------------------------------------------------------
# POST /api/v1/rfi
# ---------------------------------------------------------------------------


@router.post("/rfi")
async def rfi_check(file: UploadFile = File(...)):
    """Generate RFI (Request for Information) report for a DXF file.

    Analyzes the drawing for common construction ambiguities:
    missing dimensions, unclear references, symbols without legends,
    and other items that would trigger RFIs from contractors.
    """
    with otel_span("api.v1.rfi"):
        context = _load_context(file)

        from cad_dxf_agent.core.rfi_generator import generate_rfi

        report = generate_rfi(context)

        return {
            "total_items": report.total_items,
            "critical_count": report.critical_count,
            "major_count": report.major_count,
            "minor_count": report.minor_count,
            "items": [item.model_dump() for item in report.items],
            "checks_run": report.checks_run,
            "entity_count": report.entity_count,
            "zone_count": report.zone_count,
        }

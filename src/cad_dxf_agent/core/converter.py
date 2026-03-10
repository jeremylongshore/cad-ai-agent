"""File conversion router — DWG/PDF/DXF → working DXF (R2010).

Accepts .dwg, .pdf, or .dxf files and produces a working DXF file
suitable for the pipeline. Original files are never modified.

DWG conversion requires ODA File Converter (free, auto-detected by ezdxf).
PDF conversion extracts vector geometry from CAD-generated PDFs only.
"""

from __future__ import annotations

import logging
import tempfile
from dataclasses import dataclass, field
from pathlib import Path

import ezdxf

from ..otel import get_tracer
from ..settings import settings

logger = logging.getLogger(__name__)
tracer = get_tracer(__name__)

# ACI white — ezdxf's matplotlib renderer uses blackWhiteInversion so
# entities tagged "white" render as visible black on a white background.
PDF_ENTITY_COLOR = 7


@dataclass
class ConversionResult:
    """Result of a file conversion to working DXF."""

    source_path: Path
    source_format: str  # "dxf", "dwg", "pdf"
    output_path: Path
    success: bool
    warnings: list[str] = field(default_factory=list)
    error: str | None = None
    classifications: list | None = None  # list[PageClassification] when available


class ConversionError(Exception):
    """Raised when file conversion fails."""


def convert_to_dxf(
    source_path: str | Path,
    output_dir: str | Path | None = None,
) -> ConversionResult:
    """Convert a DWG, PDF, or DXF file to a working DXF.

    Args:
        source_path: Path to the input file (.dwg, .pdf, or .dxf).
        output_dir: Directory for the output DXF. Defaults to a temp directory.

    Returns:
        ConversionResult with the output path and any warnings.

    Raises:
        ConversionError: If conversion fails.
        FileNotFoundError: If source file doesn't exist.
        ValueError: If file format is unsupported.
    """
    with tracer.start_as_current_span("cad.convert") as span:
        source_path = Path(source_path)
        if not source_path.exists():
            raise FileNotFoundError(f"Source file not found: {source_path}")

        suffix = source_path.suffix.lower()
        span.set_attribute("cad.convert.source_format", suffix)

        if suffix == ".dxf":
            return _passthrough_dxf(source_path, output_dir)
        elif suffix == ".dwg":
            return _convert_dwg(source_path, output_dir)
        elif suffix == ".pdf":
            return _convert_pdf(source_path, output_dir)
        else:
            raise ValueError(f"Unsupported file format: {suffix}. Expected .dxf, .dwg, or .pdf")


def _get_output_path(source_path: Path, output_dir: str | Path | None) -> Path:
    """Build the output DXF path."""
    if output_dir is None:
        output_dir = Path(tempfile.mkdtemp(prefix="cad_convert_"))
    else:
        output_dir = Path(output_dir)
        output_dir.mkdir(parents=True, exist_ok=True)

    return output_dir / f"{source_path.stem}_working.dxf"


def _passthrough_dxf(source_path: Path, output_dir: str | Path | None) -> ConversionResult:
    """DXF files pass through — just validate and copy to working dir."""
    warnings: list[str] = []

    try:
        doc = ezdxf.readfile(str(source_path))
    except Exception as e:
        return ConversionResult(
            source_path=source_path,
            source_format="dxf",
            output_path=source_path,
            success=False,
            error=f"Invalid DXF file: {e}",
        )

    output_path = _get_output_path(source_path, output_dir)

    version = doc.dxfversion
    target = settings.target_dxf_version
    target_acdb = _version_to_acdb(target)

    if version != target_acdb:
        warnings.append(f"DXF version {version} differs from target {target} ({target_acdb})")

    doc.saveas(str(output_path))
    logger.info("DXF passthrough: %s → %s", source_path.name, output_path)

    return ConversionResult(
        source_path=source_path,
        source_format="dxf",
        output_path=output_path,
        success=True,
        warnings=warnings,
    )


def _convert_dwg_cloud_api(source_path: Path, output_dir: str | Path | None) -> ConversionResult:
    """Future: DWG→DXF via cloud API (CloudConvert, Aspose, etc.).

    Intended as fallback when ODA File Converter is not installed.
    Requires CAD_DWG_API_PROVIDER and CAD_DWG_API_KEY env vars.
    """
    # TODO: Implement cloud API DWG conversion
    # Candidate services: CloudConvert ($0.01/file), Aspose.CAD Cloud
    return ConversionResult(
        source_path=source_path,
        source_format="dwg",
        output_path=source_path,
        success=False,
        error=(
            "DWG conversion unavailable — ODA File Converter not installed "
            "and cloud API fallback not yet implemented. "
            "Please export as DXF from your CAD software."
        ),
    )


def _convert_dwg(source_path: Path, output_dir: str | Path | None) -> ConversionResult:
    """Convert DWG to DXF using ODA File Converter via ezdxf.addons.odafc."""
    from ezdxf.addons import odafc

    if not odafc.is_installed():  # type: ignore[attr-defined]
        return _convert_dwg_cloud_api(source_path, output_dir)

    output_path = _get_output_path(source_path, output_dir)
    warnings: list[str] = []

    try:
        doc = odafc.readfile(str(source_path))  # type: ignore[attr-defined]
        doc.saveas(str(output_path))

        logger.info("DWG → DXF: %s → %s", source_path.name, output_path)

        return ConversionResult(
            source_path=source_path,
            source_format="dwg",
            output_path=output_path,
            success=True,
            warnings=warnings,
        )
    except Exception as e:
        logger.error("DWG conversion exception: %s", e, exc_info=True)
        return ConversionResult(
            source_path=source_path,
            source_format="dwg",
            output_path=source_path,
            success=False,
            error=f"DWG conversion failed: {e}",
        )


_PDF_WARNING = (
    "PDF conversion is experimental and lossy. Curves may be approximated as "
    "line segments. For best results, export as DXF or DWG from your CAD software."
)


def _convert_pdf(source_path: Path, output_dir: str | Path | None) -> ConversionResult:
    """Convert vector PDF to DXF by extracting geometric primitives.

    Prefers PyMuPDF (fitz) for better curve/arc extraction. Falls back to
    pdfplumber if PyMuPDF is not installed. Only handles CAD-generated
    vector PDFs — scanned/raster PDFs are out of scope.
    """
    # Try PyMuPDF first (better curve support), fall back to pdfplumber
    has_fitz = False
    has_pdfplumber = False
    try:
        import fitz  # noqa: F401  # availability check only

        has_fitz = True
    except ImportError:
        pass

    if not has_fitz:
        try:
            import pdfplumber  # noqa: F401  # availability check only

            has_pdfplumber = True
        except ImportError:
            pass

    if not has_fitz and not has_pdfplumber:
        return ConversionResult(
            source_path=source_path,
            source_format="pdf",
            output_path=source_path,
            success=False,
            error=(
                "No PDF library installed. Install with: "
                "pip install pymupdf  (recommended) or  pip install pdfplumber"
            ),
        )

    output_path = _get_output_path(source_path, output_dir)
    warnings: list[str] = [_PDF_WARNING]

    # Run classifier if PyMuPDF is available
    classifications = None
    if has_fitz:
        try:
            from .pdf_classifier import classify_pdf_pages

            classifications = classify_pdf_pages(source_path)
            for c in classifications:
                warnings.append(
                    f"Page {c.page_num + 1}: {c.content_type.value} "
                    f"(vectors={c.vector_count}, text={c.text_count})"
                )
        except Exception as e:
            logger.warning("PDF classification failed (non-fatal): %s", e)

    try:
        doc = ezdxf.new(dxfversion=_version_to_acdb(settings.target_dxf_version))
        # Ensure layer "0" has explicit color
        doc.layers.get("0").color = PDF_ENTITY_COLOR
        msp = doc.modelspace()
        total_entities = 0

        if has_fitz:
            total_entities = _extract_pdf_fitz(msp, source_path, doc)
            if total_entities == 0:
                warnings.append(
                    "No vector geometry found in PDF — may be a raster/scanned document"
                )
        else:
            import pdfplumber as _pdfplumber

            warnings.append("Using pdfplumber fallback — curves will be lost. Install pymupdf.")
            with _pdfplumber.open(str(source_path)) as pdf:
                if len(pdf.pages) == 0:
                    return ConversionResult(
                        source_path=source_path,
                        source_format="pdf",
                        output_path=source_path,
                        success=False,
                        error="PDF has no pages",
                    )
                plumber_x_offset = 0.0
                for page_num, page in enumerate(pdf.pages):
                    layer = f"PDF_PAGE_{page_num + 1}" if page_num > 0 else "0"
                    if page_num > 0 and layer not in doc.layers:
                        doc.layers.add(layer, color=PDF_ENTITY_COLOR)
                    total_entities += _extract_pdf_page_plumber(
                        msp, page, page_num, x_offset=plumber_x_offset
                    )
                    plumber_x_offset += float(page.width) + PDF_PAGE_GAP

                if total_entities == 0:
                    warnings.append(
                        "No vector geometry found in PDF — may be a raster/scanned document"
                    )

        doc.saveas(str(output_path))
        logger.info(
            "PDF → DXF: %s → %s (%d entities)", source_path.name, output_path, total_entities
        )

        return ConversionResult(
            source_path=source_path,
            source_format="pdf",
            output_path=output_path,
            success=True,
            warnings=warnings,
            classifications=classifications,
        )
    except Exception as e:
        return ConversionResult(
            source_path=source_path,
            source_format="pdf",
            output_path=source_path,
            success=False,
            error=f"PDF conversion failed: {e}",
        )


# ── Color helpers ─────────────────────────────────────────────────


def _set_entity_rgb(entity, rgb_tuple) -> None:
    """Apply true RGB color from PDF [0,1] RGB tuple to a DXF entity."""
    if rgb_tuple is None:
        return
    try:
        r, g, b = [max(0, min(255, int(c * 255))) for c in rgb_tuple[:3]]
    except (TypeError, ValueError):
        return
    if r < 30 and g < 30 and b < 30:
        return  # near-black: let ACI white + blackWhiteInversion handle it
    entity.rgb = (r, g, b)


def _rgb_to_aci(rgb_tuple) -> int:
    """Map PDF RGB stroke color to nearest DXF ACI color index.

    ``rgb_tuple`` comes from PyMuPDF ``path_item["color"]`` — an (R, G, B)
    tuple with values in [0, 1].  Returns the closest AutoCAD Color Index.
    """
    if rgb_tuple is None:
        return PDF_ENTITY_COLOR
    try:
        r, g, b = [int(c * 255) for c in rgb_tuple[:3]]
    except (TypeError, ValueError):
        return PDF_ENTITY_COLOR
    # Near-black → use white (viewer inverts to visible black)
    if r < 30 and g < 30 and b < 30:
        return 7
    if r > 200 and g < 50 and b < 50:
        return 1  # red
    if r > 200 and g > 200 and b < 50:
        return 2  # yellow
    if g > 200 and r < 50 and b < 50:
        return 3  # green
    if g > 200 and b > 200 and r < 50:
        return 4  # cyan
    if b > 200 and r < 50 and g < 50:
        return 5  # blue
    if r > 200 and b > 200 and g < 50:
        return 6  # magenta
    return PDF_ENTITY_COLOR


# ── PyMuPDF extraction (preferred) ──────────────────────────────


PDF_PAGE_GAP = 50.0  # gap between pages in DXF units (~17.6mm)

# Minimum entity length in PDF points.  PDF path decomposition produces
# thousands of sub-pixel strokes (fill patterns, hatch artifacts, stroke caps)
# that add density without readable information.  Filtering these reduces the
# "black blob" effect when viewing dense structural PDFs at auto-fit zoom.
PDF_MIN_ENTITY_SIZE = 1.0

# Maximum HATCH entities per page to avoid bloating files with fill patterns.
PDF_MAX_HATCH_ENTITIES = 500


def _create_fill_hatch(msp, path_item, x_offset, page_height, layer, hatch_count):
    """Create a SOLID HATCH from a filled PDF path_item.

    Returns (hatch_or_none, updated_hatch_count).
    """
    fill_rgb = path_item.get("fill")
    if fill_rgb is None or hatch_count >= PDF_MAX_HATCH_ENTITIES:
        return None, hatch_count

    items = path_item.get("items", [])
    if len(items) < 2:
        return None, hatch_count

    hatch = msp.add_hatch(dxfattribs={"layer": layer, "color": _rgb_to_aci(fill_rgb)})
    ep = hatch.paths.add_edge_path()

    for item in items:
        kind = item[0]
        if kind == "l":  # line segment
            p1, p2 = item[1], item[2]
            ep.add_line(
                (x_offset + float(p1.x), page_height - float(p1.y)),
                (x_offset + float(p2.x), page_height - float(p2.y)),
            )
        elif kind == "c":  # cubic Bezier
            p1, p2, p3, p4 = item[1], item[2], item[3], item[4]
            ep.add_spline(
                control_points=[
                    (x_offset + float(p.x), page_height - float(p.y)) for p in (p1, p2, p3, p4)
                ],
                degree=3,
            )
        elif kind == "re":  # rectangle — add 4 line edges
            rect = item[1]
            corners = [
                (x_offset + float(rect.x0), page_height - float(rect.y0)),
                (x_offset + float(rect.x1), page_height - float(rect.y0)),
                (x_offset + float(rect.x1), page_height - float(rect.y1)),
                (x_offset + float(rect.x0), page_height - float(rect.y1)),
            ]
            for i in range(4):
                ep.add_line(corners[i], corners[(i + 1) % 4])

    hatch.set_solid_fill()
    _set_entity_rgb(hatch, fill_rgb)
    return hatch, hatch_count + 1


def _extract_pdf_fitz(msp, source_path: Path, doc=None) -> int:
    """Extract vector geometry using PyMuPDF's page.get_drawings().

    PyMuPDF recovers Bezier curves, arcs, lines, and rects from PDF
    content streams — much better than pdfplumber for CAD PDFs.
    Multi-page PDFs are laid out side-by-side with PDF_PAGE_GAP spacing.

    When ``doc`` is provided (ezdxf Document), per-page layers are created
    with explicit colors so entities are visible in viewers.
    """
    import math

    import fitz

    pdf_doc = fitz.open(str(source_path))
    total = 0
    x_offset = 0.0

    for page_num, page in enumerate(pdf_doc):
        layer = f"PDF_PAGE_{page_num + 1}" if page_num > 0 else "0"
        # Create layer with explicit color so entities are visible
        if doc is not None and page_num > 0 and layer not in doc.layers:
            doc.layers.add(layer, color=PDF_ENTITY_COLOR)
        page_height = page.rect.height
        page_width = page.rect.width
        drawings = page.get_drawings()

        hatch_count = 0
        for path_item in drawings:
            stroke_color = _rgb_to_aci(path_item.get("color"))
            stroke_rgb = path_item.get("color")

            # Create fill HATCH if path has a fill color
            if path_item.get("fill") is not None:
                hatch, hatch_count = _create_fill_hatch(
                    msp, path_item, x_offset, page_height, layer, hatch_count
                )
                if hatch is not None:
                    total += 1

            for item in path_item.get("items", []):
                kind = item[0]
                attribs = {"layer": layer, "color": stroke_color}

                if kind == "l":  # Line
                    p1, p2 = item[1], item[2]
                    x0, y0 = x_offset + float(p1.x), page_height - float(p1.y)
                    x1, y1 = x_offset + float(p2.x), page_height - float(p2.y)
                    if math.hypot(x1 - x0, y1 - y0) < PDF_MIN_ENTITY_SIZE:
                        continue
                    entity = msp.add_line((x0, y0), (x1, y1), dxfattribs=attribs)
                    _set_entity_rgb(entity, stroke_rgb)
                    total += 1

                elif kind == "re":  # Rectangle
                    rect = item[1]
                    x0 = x_offset + float(rect.x0)
                    y0 = page_height - float(rect.y0)
                    x1 = x_offset + float(rect.x1)
                    y1 = page_height - float(rect.y1)
                    if abs(x1 - x0) < PDF_MIN_ENTITY_SIZE and abs(y1 - y0) < PDF_MIN_ENTITY_SIZE:
                        continue
                    points = [(x0, y0), (x1, y0), (x1, y1), (x0, y1)]
                    entity = msp.add_lwpolyline(points, close=True, dxfattribs=attribs)
                    _set_entity_rgb(entity, stroke_rgb)
                    total += 1

                elif kind == "c":  # Cubic Bezier curve
                    p1, p2, p3, p4 = item[1], item[2], item[3], item[4]
                    # Skip tiny curves (fill artifacts)
                    chord = math.hypot(float(p4.x) - float(p1.x), float(p4.y) - float(p1.y))
                    if chord < PDF_MIN_ENTITY_SIZE:
                        continue
                    arc = _fit_arc_from_bezier(p1, p2, p3, p4, page_height)
                    if arc:
                        cx, cy, radius, start_angle, end_angle = arc
                        entity = msp.add_arc(
                            center=(x_offset + cx, cy),
                            radius=radius,
                            start_angle=math.degrees(start_angle),
                            end_angle=math.degrees(end_angle),
                            dxfattribs=attribs,
                        )
                    else:
                        # Approximate as polyline segments
                        pts = _bezier_to_points(p1, p2, p3, p4, page_height, segments=8)
                        if len(pts) >= 2:
                            shifted = [(x_offset + px, py) for px, py in pts]
                            entity = msp.add_lwpolyline(shifted, dxfattribs=attribs)
                        else:
                            entity = None
                    if entity is not None:
                        _set_entity_rgb(entity, stroke_rgb)
                    total += 1

                elif kind == "qu":  # Quad (quadrilateral)
                    # pymupdf >=1.27: ('qu', Quad_object) — Quad[0..3] are Points
                    # pymupdf <1.27:  ('qu', Point, Point, Point, Point)
                    if len(item) == 2:
                        quad = item[1]
                        pts = [
                            (x_offset + float(quad[k].x), page_height - float(quad[k].y))
                            for k in range(4)
                        ]
                    else:
                        pts = [
                            (x_offset + float(item[k].x), page_height - float(item[k].y))
                            for k in range(1, len(item))
                        ]
                    if len(pts) >= 2:
                        entity = msp.add_lwpolyline(pts, close=True, dxfattribs=attribs)
                        _set_entity_rgb(entity, stroke_rgb)
                    total += 1

        # Extract text blocks from the page
        text_blocks = page.get_text("dict", flags=fitz.TEXT_PRESERVE_WHITESPACE).get("blocks", [])
        for block in text_blocks:
            if block.get("type") != 0:  # text block
                continue
            for line in block.get("lines", []):
                for span in line.get("spans", []):
                    text = span.get("text", "").strip()
                    if not text:
                        continue
                    bbox = span.get("bbox", (0, 0, 0, 0))
                    x = x_offset + float(bbox[0])
                    y = page_height - float(bbox[1])
                    height = max(float(bbox[3]) - float(bbox[1]), 1.0)

                    # Extract text color from PyMuPDF packed int
                    span_color_int = span.get("color", 0)
                    sr = (span_color_int >> 16) & 0xFF
                    sg = (span_color_int >> 8) & 0xFF
                    sb = span_color_int & 0xFF

                    text_entity = msp.add_text(
                        text,
                        height=height * 0.7,
                        dxfattribs={
                            "layer": layer,
                            "color": PDF_ENTITY_COLOR,
                            "insert": (x, y),
                        },
                    )
                    if sr > 30 or sg > 30 or sb > 30:
                        text_entity.rgb = (sr, sg, sb)
                    total += 1

        x_offset += page_width + PDF_PAGE_GAP

    pdf_doc.close()
    return total


def _fit_arc_from_bezier(p1, p2, p3, p4, page_height: float):
    """Try to fit a circular arc to a cubic Bezier curve.

    Returns (cx, cy, radius, start_angle, end_angle) if the Bezier is
    near-circular, or None if it's a general curve.
    """
    import math

    # Convert to DXF coords (flip Y)
    x0, y0 = float(p1.x), page_height - float(p1.y)
    x1, y1 = float(p2.x), page_height - float(p2.y)
    x2, y2 = float(p3.x), page_height - float(p3.y)
    x3, y3 = float(p4.x), page_height - float(p4.y)

    # Mid-point of the Bezier (t=0.5)
    mx = 0.125 * (x0 + 3 * x1 + 3 * x2 + x3)
    my = 0.125 * (y0 + 3 * y1 + 3 * y2 + y3)

    # Try to find circumscribed circle of start, mid, end points
    ax, ay = x0, y0
    bx, by = mx, my
    cx, cy = x3, y3

    d = 2 * (ax * (by - cy) + bx * (cy - ay) + cx * (ay - by))
    if abs(d) < 1e-10:
        return None  # Collinear — not an arc

    a_sq = ax * ax + ay * ay
    b_sq = bx * bx + by * by
    c_sq = cx * cx + cy * cy
    ux = (a_sq * (by - cy) + b_sq * (cy - ay) + c_sq * (ay - by)) / d
    uy = (a_sq * (cx - bx) + b_sq * (ax - cx) + c_sq * (bx - ax)) / d

    r1 = math.hypot(ax - ux, ay - uy)
    r2 = math.hypot(bx - ux, by - uy)
    r3 = math.hypot(cx - ux, cy - uy)

    # Check if all three radii match (within 5% tolerance)
    avg_r = (r1 + r2 + r3) / 3
    if avg_r < 0.1:
        return None
    if max(abs(r1 - avg_r), abs(r2 - avg_r), abs(r3 - avg_r)) / avg_r > 0.05:
        return None  # Not circular enough

    start_angle = math.atan2(ay - uy, ax - ux)
    end_angle = math.atan2(cy - uy, cx - ux)

    return (ux, uy, avg_r, start_angle, end_angle)


def _bezier_to_points(p1, p2, p3, p4, page_height: float, segments: int = 8):
    """Approximate a cubic Bezier as polyline points."""
    points = []
    for i in range(segments + 1):
        t = i / segments
        t2 = t * t
        t3 = t2 * t
        mt = 1 - t
        mt2 = mt * mt
        mt3 = mt2 * mt

        x = mt3 * p1.x + 3 * mt2 * t * p2.x + 3 * mt * t2 * p3.x + t3 * p4.x
        y = mt3 * p1.y + 3 * mt2 * t * p2.y + 3 * mt * t2 * p3.y + t3 * p4.y

        points.append((float(x), page_height - float(y)))
    return points


# ── pdfplumber extraction (fallback) ─────────────────────────────


def _extract_pdf_page_plumber(msp, page, page_num: int, x_offset: float = 0.0) -> int:
    """Extract vector geometry from a single PDF page using pdfplumber.

    Fallback when PyMuPDF is not installed. Only extracts lines, rects,
    and text — curves/arcs are lost.  x_offset shifts all X coords for
    side-by-side multi-page layout.
    """
    import math

    count = 0
    layer = f"PDF_PAGE_{page_num + 1}" if page_num > 0 else "0"
    attribs = {"layer": layer, "color": PDF_ENTITY_COLOR}

    # Extract lines
    lines = page.lines or []
    for line in lines:
        x0, y0 = x_offset + float(line["x0"]), float(line["top"])
        x1, y1 = x_offset + float(line["x1"]), float(line["bottom"])
        # Flip Y axis (PDF origin is top-left, DXF is bottom-left)
        page_height = float(page.height)
        y0 = page_height - y0
        y1 = page_height - y1
        if math.hypot(x1 - x0, y1 - y0) < PDF_MIN_ENTITY_SIZE:
            continue
        msp.add_line((x0, y0), (x1, y1), dxfattribs=attribs)
        count += 1

    # Extract rectangles as polylines
    rects = page.rects or []
    for rect in rects:
        x0, y0 = x_offset + float(rect["x0"]), float(rect["top"])
        x1, y1 = x_offset + float(rect["x1"]), float(rect["bottom"])
        page_height = float(page.height)
        y0 = page_height - y0
        y1 = page_height - y1
        if abs(x1 - x0) < PDF_MIN_ENTITY_SIZE and abs(y1 - y0) < PDF_MIN_ENTITY_SIZE:
            continue
        points = [(x0, y0), (x1, y0), (x1, y1), (x0, y1)]
        msp.add_lwpolyline(points, close=True, dxfattribs=attribs)
        count += 1

    # Extract text
    words = page.extract_words() or []
    for word in words:
        x = x_offset + float(word["x0"])
        y = float(page.height) - float(word["top"])
        text = word["text"]
        height = max(float(word["bottom"]) - float(word["top"]), 1.0)
        msp.add_text(
            text,
            height=height * 0.7,  # approximate PDF text height to DXF
            dxfattribs={"layer": layer, "color": PDF_ENTITY_COLOR, "insert": (x, y)},
        )
        count += 1

    return count


# --- Version mapping helpers ---

_ACDB_MAP = {
    "R12": "AC1009",
    "R2000": "AC1015",
    "R2004": "AC1018",
    "R2007": "AC1021",
    "R2010": "AC1024",
    "R2013": "AC1027",
    "R2018": "AC1032",
}

_ODAFC_MAP = {
    "R12": "ACAD12",
    "R2000": "ACAD2000",
    "R2004": "ACAD2004",
    "R2007": "ACAD2007",
    "R2010": "ACAD2010",
    "R2013": "ACAD2013",
    "R2018": "ACAD2018",
}


def _version_to_acdb(version: str) -> str:
    """Map human version (R2010) to ACDB version string (AC1024)."""
    return _ACDB_MAP.get(version, "AC1024")


def _version_to_odafc(version: str) -> str:
    """Map human version (R2010) to ODAFC version string (ACAD2010)."""
    return _ODAFC_MAP.get(version, "ACAD2010")

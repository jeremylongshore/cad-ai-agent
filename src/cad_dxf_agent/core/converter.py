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


@dataclass
class ConversionResult:
    """Result of a file conversion to working DXF."""

    source_path: Path
    source_format: str  # "dxf", "dwg", "pdf"
    output_path: Path
    success: bool
    warnings: list[str] = field(default_factory=list)
    error: str | None = None


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
        target_version = _version_to_odafc(settings.target_dxf_version)
        doc = odafc.readfile(str(source_path))  # type: ignore[attr-defined]
        doc.saveas(str(output_path), fmt=target_version)

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

    try:
        doc = ezdxf.new(dxfversion=_version_to_acdb(settings.target_dxf_version))
        msp = doc.modelspace()
        total_entities = 0

        if has_fitz:
            total_entities = _extract_pdf_fitz(msp, source_path)
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
                for page_num, page in enumerate(pdf.pages):
                    total_entities += _extract_pdf_page_plumber(msp, page, page_num)

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
        )
    except Exception as e:
        return ConversionResult(
            source_path=source_path,
            source_format="pdf",
            output_path=source_path,
            success=False,
            error=f"PDF conversion failed: {e}",
        )


# ── PyMuPDF extraction (preferred) ──────────────────────────────


def _extract_pdf_fitz(msp, source_path: Path) -> int:
    """Extract vector geometry using PyMuPDF's page.get_drawings().

    PyMuPDF recovers Bezier curves, arcs, lines, and rects from PDF
    content streams — much better than pdfplumber for CAD PDFs.
    """
    import math

    import fitz

    pdf_doc = fitz.open(str(source_path))
    total = 0

    for page_num, page in enumerate(pdf_doc):
        layer = f"PDF_PAGE_{page_num + 1}" if page_num > 0 else "0"
        page_height = page.rect.height
        drawings = page.get_drawings()

        for path_item in drawings:
            for item in path_item.get("items", []):
                kind = item[0]

                if kind == "l":  # Line
                    p1, p2 = item[1], item[2]
                    x0, y0 = float(p1.x), page_height - float(p1.y)
                    x1, y1 = float(p2.x), page_height - float(p2.y)
                    msp.add_line((x0, y0), (x1, y1), dxfattribs={"layer": layer})
                    total += 1

                elif kind == "re":  # Rectangle
                    rect = item[1]
                    x0 = float(rect.x0)
                    y0 = page_height - float(rect.y0)
                    x1 = float(rect.x1)
                    y1 = page_height - float(rect.y1)
                    points = [(x0, y0), (x1, y0), (x1, y1), (x0, y1)]
                    msp.add_lwpolyline(points, close=True, dxfattribs={"layer": layer})
                    total += 1

                elif kind == "c":  # Cubic Bezier curve
                    p1, p2, p3, p4 = item[1], item[2], item[3], item[4]
                    arc = _fit_arc_from_bezier(p1, p2, p3, p4, page_height)
                    if arc:
                        cx, cy, radius, start_angle, end_angle = arc
                        msp.add_arc(
                            center=(cx, cy),
                            radius=radius,
                            start_angle=math.degrees(start_angle),
                            end_angle=math.degrees(end_angle),
                            dxfattribs={"layer": layer},
                        )
                    else:
                        # Approximate as polyline segments
                        pts = _bezier_to_points(p1, p2, p3, p4, page_height, segments=8)
                        if len(pts) >= 2:
                            msp.add_lwpolyline(pts, dxfattribs={"layer": layer})
                    total += 1

                elif kind == "qu":  # Quad (quadrilateral)
                    # pymupdf >=1.27: ('qu', Quad_object) — Quad[0..3] are Points
                    # pymupdf <1.27:  ('qu', Point, Point, Point, Point)
                    if len(item) == 2:
                        quad = item[1]
                        pts = [(float(quad[k].x), page_height - float(quad[k].y)) for k in range(4)]
                    else:
                        pts = [
                            (float(item[k].x), page_height - float(item[k].y))
                            for k in range(1, len(item))
                        ]
                    if len(pts) >= 2:
                        msp.add_lwpolyline(pts, close=True, dxfattribs={"layer": layer})
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
                    x = float(bbox[0])
                    y = page_height - float(bbox[1])
                    height = max(float(bbox[3]) - float(bbox[1]), 1.0)
                    msp.add_text(
                        text,
                        height=height * 0.7,
                        dxfattribs={"layer": layer, "insert": (x, y)},
                    )
                    total += 1

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


def _extract_pdf_page_plumber(msp, page, page_num: int) -> int:
    """Extract vector geometry from a single PDF page using pdfplumber.

    Fallback when PyMuPDF is not installed. Only extracts lines, rects,
    and text — curves/arcs are lost.
    """
    count = 0
    layer = f"PDF_PAGE_{page_num + 1}" if page_num > 0 else "0"

    # Extract lines
    lines = page.lines or []
    for line in lines:
        x0, y0 = float(line["x0"]), float(line["top"])
        x1, y1 = float(line["x1"]), float(line["bottom"])
        # Flip Y axis (PDF origin is top-left, DXF is bottom-left)
        page_height = float(page.height)
        y0 = page_height - y0
        y1 = page_height - y1
        msp.add_line((x0, y0), (x1, y1), dxfattribs={"layer": layer})
        count += 1

    # Extract rectangles as polylines
    rects = page.rects or []
    for rect in rects:
        x0, y0 = float(rect["x0"]), float(rect["top"])
        x1, y1 = float(rect["x1"]), float(rect["bottom"])
        page_height = float(page.height)
        y0 = page_height - y0
        y1 = page_height - y1
        points = [(x0, y0), (x1, y0), (x1, y1), (x0, y1)]
        msp.add_lwpolyline(points, close=True, dxfattribs={"layer": layer})
        count += 1

    # Extract text
    words = page.extract_words() or []
    for word in words:
        x = float(word["x0"])
        y = float(page.height) - float(word["top"])
        text = word["text"]
        height = max(float(word["bottom"]) - float(word["top"]), 1.0)
        msp.add_text(
            text,
            height=height * 0.7,  # approximate PDF text height to DXF
            dxfattribs={"layer": layer, "insert": (x, y)},
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

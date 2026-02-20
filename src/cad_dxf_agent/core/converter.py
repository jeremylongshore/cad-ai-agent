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


def _convert_dwg(source_path: Path, output_dir: str | Path | None) -> ConversionResult:
    """Convert DWG to DXF using ODA File Converter via ezdxf.addons.odafc."""
    from ezdxf.addons import odafc

    if not odafc.is_installed():
        return ConversionResult(
            source_path=source_path,
            source_format="dwg",
            output_path=source_path,
            success=False,
            error=(
                "ODA File Converter not installed. "
                "Download free from https://www.opendesign.com/guestfiles/oda_file_converter"
            ),
        )

    output_path = _get_output_path(source_path, output_dir)
    warnings: list[str] = []

    try:
        target_version = _version_to_odafc(settings.target_dxf_version)
        doc = odafc.readfile(str(source_path))
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
        return ConversionResult(
            source_path=source_path,
            source_format="dwg",
            output_path=source_path,
            success=False,
            error=f"DWG conversion failed: {e}",
        )


def _convert_pdf(source_path: Path, output_dir: str | Path | None) -> ConversionResult:
    """Convert vector PDF to DXF by extracting geometric primitives.

    Only handles CAD-generated vector PDFs. Scanned/raster PDFs are out of scope.
    """
    try:
        import pdfplumber
    except ImportError:
        return ConversionResult(
            source_path=source_path,
            source_format="pdf",
            output_path=source_path,
            success=False,
            error="pdfplumber not installed. Install with: pip install pdfplumber",
        )

    output_path = _get_output_path(source_path, output_dir)
    warnings: list[str] = []

    try:
        doc = ezdxf.new(dxfversion=_version_to_acdb(settings.target_dxf_version))
        msp = doc.modelspace()

        total_entities = 0

        with pdfplumber.open(str(source_path)) as pdf:
            if len(pdf.pages) == 0:
                return ConversionResult(
                    source_path=source_path,
                    source_format="pdf",
                    output_path=source_path,
                    success=False,
                    error="PDF has no pages",
                )

            for page_num, page in enumerate(pdf.pages):
                page_entities = _extract_pdf_page(msp, page, page_num)
                total_entities += page_entities

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


def _extract_pdf_page(msp, page, page_num: int) -> int:
    """Extract vector geometry from a single PDF page into DXF model space.

    Returns the count of entities created.
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

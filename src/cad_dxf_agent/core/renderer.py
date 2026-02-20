"""DXF to image renderer — PNG/PDF preview generation via matplotlib.

Uses ezdxf's drawing addon with matplotlib backend for rendering
DXF model space or layout views to PNG images for:
  1. Visual preview in the UI
  2. Vision pipeline input for Gemini (V2.2)
  3. Final export (V2.5)
"""

from __future__ import annotations

import logging
import tempfile
from dataclasses import dataclass
from pathlib import Path

import ezdxf

from ..otel import get_tracer
from ..settings import settings

logger = logging.getLogger(__name__)
tracer = get_tracer(__name__)


@dataclass
class RenderResult:
    """Result of rendering a DXF to an image."""

    output_path: Path
    format: str  # "png" or "pdf"
    dpi: int
    success: bool
    error: str | None = None


def render_dxf_to_png(
    dxf_path: str | Path,
    output_path: str | Path | None = None,
    *,
    dpi: int | None = None,
    background: str | None = None,
    layout_name: str | None = None,
) -> RenderResult:
    """Render a DXF file to a PNG image.

    Args:
        dxf_path: Path to the DXF file to render.
        output_path: Output PNG path. Auto-generated if None.
        dpi: Image resolution. Defaults to settings.render_dpi.
        background: Background color hex (#RRGGBB). Defaults to settings.
        layout_name: Layout name to render. None = model space.

    Returns:
        RenderResult with the output path.
    """
    return _render(
        dxf_path=dxf_path,
        output_path=output_path,
        fmt="png",
        dpi=dpi,
        background=background,
        layout_name=layout_name,
    )


def render_dxf_to_pdf(
    dxf_path: str | Path,
    output_path: str | Path | None = None,
    *,
    dpi: int | None = None,
    background: str | None = None,
    layout_name: str | None = None,
) -> RenderResult:
    """Render a DXF file to a PDF.

    Args:
        dxf_path: Path to the DXF file to render.
        output_path: Output PDF path. Auto-generated if None.
        dpi: Image resolution. Defaults to settings.render_dpi.
        background: Background color hex (#RRGGBB). Defaults to settings.
        layout_name: Layout name to render. None = model space.

    Returns:
        RenderResult with the output path.
    """
    return _render(
        dxf_path=dxf_path,
        output_path=output_path,
        fmt="pdf",
        dpi=dpi,
        background=background,
        layout_name=layout_name,
    )


def _render(
    dxf_path: str | Path,
    output_path: str | Path | None,
    fmt: str,
    dpi: int | None,
    background: str | None,
    layout_name: str | None,
) -> RenderResult:
    """Internal render implementation."""
    with tracer.start_as_current_span("cad.render") as span:
        dxf_path = Path(dxf_path)
        if not dxf_path.exists():
            raise FileNotFoundError(f"DXF file not found: {dxf_path}")

        dpi = dpi or settings.render_dpi
        background = background or _bg_hex(settings.render_background)

        span.set_attribute("cad.render.format", fmt)
        span.set_attribute("cad.render.dpi", dpi)

        if output_path is None:
            suffix = f".{fmt}"
            fd, tmp = tempfile.mkstemp(prefix="cad_render_", suffix=suffix)
            import os

            os.close(fd)
            output_path = Path(tmp)
        else:
            output_path = Path(output_path)
            output_path.parent.mkdir(parents=True, exist_ok=True)

        try:
            doc = ezdxf.readfile(str(dxf_path))

            if layout_name:
                try:
                    layout = doc.layouts.get(layout_name)
                except ezdxf.DXFKeyError:
                    return RenderResult(
                        output_path=output_path,
                        format=fmt,
                        dpi=dpi,
                        success=False,
                        error=f"Layout not found: {layout_name}",
                    )
            else:
                layout = doc.modelspace()

            from ezdxf.addons.drawing.matplotlib import qsave

            qsave(
                layout,
                str(output_path),
                dpi=dpi,
                bg=background,
            )

            span.set_attribute("cad.render.output_basename", output_path.name)
            logger.info("Rendered %s → %s (%d dpi)", dxf_path.name, output_path, dpi)

            return RenderResult(
                output_path=output_path,
                format=fmt,
                dpi=dpi,
                success=True,
            )

        except Exception as e:
            logger.error("Render failed: %s", e)
            return RenderResult(
                output_path=output_path,
                format=fmt,
                dpi=dpi,
                success=False,
                error=f"Render failed: {e}",
            )


def _bg_hex(color_name: str) -> str:
    """Convert a named background color to hex for ezdxf."""
    color_map = {
        "white": "#FFFFFF",
        "black": "#000000",
        "transparent": "#FFFFFF00",
    }
    if color_name.startswith("#"):
        return color_name
    return color_map.get(color_name.lower(), "#FFFFFF")

"""Tests for the DXF to PNG/PDF renderer."""

from __future__ import annotations

from pathlib import Path

import pytest

from cad_dxf_agent.core.renderer import RenderResult, render_dxf_to_pdf, render_dxf_to_png


class TestPngRendering:
    """PNG rendering from DXF files."""

    def test_render_sample_dxf_to_png(self, sample_dxf: Path, tmp_path: Path):
        output = tmp_path / "preview.png"
        result = render_dxf_to_png(sample_dxf, output_path=output)

        assert result.success is True
        assert result.format == "png"
        assert result.output_path.exists()
        assert result.output_path.stat().st_size > 0

    def test_render_auto_output_path(self, sample_dxf: Path):
        result = render_dxf_to_png(sample_dxf)
        assert result.success is True
        assert result.output_path.exists()
        assert result.output_path.suffix == ".png"
        # Cleanup
        result.output_path.unlink()

    def test_render_custom_dpi(self, sample_dxf: Path, tmp_path: Path):
        low = tmp_path / "low.png"
        high = tmp_path / "high.png"

        result_low = render_dxf_to_png(sample_dxf, output_path=low, dpi=72)
        result_high = render_dxf_to_png(sample_dxf, output_path=high, dpi=300)

        assert result_low.success is True
        assert result_high.success is True
        assert result_low.dpi == 72
        assert result_high.dpi == 300

        # Higher DPI should produce a larger file
        assert high.stat().st_size > low.stat().st_size

    def test_render_white_background(self, sample_dxf: Path, tmp_path: Path):
        output = tmp_path / "white_bg.png"
        result = render_dxf_to_png(sample_dxf, output_path=output, background="#FFFFFF")
        assert result.success is True

    def test_render_file_not_found(self, tmp_path: Path):
        with pytest.raises(FileNotFoundError):
            render_dxf_to_png(tmp_path / "nonexistent.dxf")


class TestPdfRendering:
    """PDF rendering from DXF files."""

    def test_render_sample_dxf_to_pdf(self, sample_dxf: Path, tmp_path: Path):
        output = tmp_path / "preview.pdf"
        result = render_dxf_to_pdf(sample_dxf, output_path=output)

        assert result.success is True
        assert result.format == "pdf"
        assert result.output_path.exists()
        assert result.output_path.stat().st_size > 0


class TestRenderResult:
    """RenderResult data class."""

    def test_result_fields(self, tmp_path: Path):
        result = RenderResult(
            output_path=tmp_path / "test.png",
            format="png",
            dpi=150,
            success=True,
        )
        assert result.success is True
        assert result.format == "png"
        assert result.dpi == 150
        assert result.error is None

    def test_result_error(self, tmp_path: Path):
        result = RenderResult(
            output_path=tmp_path / "test.png",
            format="png",
            dpi=150,
            success=False,
            error="Render failed",
        )
        assert result.success is False
        assert result.error == "Render failed"

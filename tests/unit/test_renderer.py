"""Tests for the DXF to PNG/PDF renderer."""

from __future__ import annotations

from pathlib import Path

import pytest

from cad_dxf_agent.core.renderer import (
    RenderResult,
    _check_render_quality,
    render_dxf_to_pdf,
    render_dxf_to_png,
)


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


# ---------------------------------------------------------------------------
# Edge-path tests — error paths not covered by the classes above
# ---------------------------------------------------------------------------


class TestRenderLayoutNotFound:
    """Lines 132-141: layout_name branch — DXFKeyError caught and returned as failure.

    In practice ezdxf raises a plain KeyError from doc.layouts.get(), which is
    NOT caught by the inner `except ezdxf.DXFKeyError:` and falls through to
    the outer `except Exception:`. We cover the inner branch explicitly via
    patching, and cover the outer exception path via the real ezdxf call.
    """

    def test_render_png_nonexistent_layout_returns_failure(self, sample_dxf: Path, tmp_path: Path):
        """Real call with a missing layout — falls into generic exception path."""
        output = tmp_path / "bad_layout.png"
        result = render_dxf_to_png(sample_dxf, output_path=output, layout_name="NONEXISTENT_LAYOUT")

        assert result.success is False
        assert result.error is not None
        # ezdxf raises plain KeyError, caught by outer except Exception
        assert "Render failed" in result.error

    def test_render_dxf_key_error_inner_branch(self, sample_dxf: Path, tmp_path: Path):
        """Lines 132-141: DXFKeyError from layouts.get → inner branch returns failure.

        Patches ezdxf.readfile so that the returned doc's layouts.get raises
        DXFKeyError, which is caught by the inner except clause.
        """
        from unittest.mock import patch

        import ezdxf as _ezdxf

        output = tmp_path / "dxf_key_err.png"

        original_readfile = _ezdxf.readfile

        class _FakeLayouts:
            def get(self, name: str):
                raise _ezdxf.DXFKeyError(name)

        def _patched_readfile(path, *args, **kwargs):
            doc = original_readfile(path, *args, **kwargs)
            doc.layouts = _FakeLayouts()
            return doc

        with patch("cad_dxf_agent.core.renderer.ezdxf.readfile", side_effect=_patched_readfile):
            result = render_dxf_to_png(sample_dxf, output_path=output, layout_name="ANY_LAYOUT")

        assert result.success is False
        assert result.error is not None
        assert "Layout not found" in result.error


class TestRenderExceptionPath:
    """Lines 164-166: generic exception handler in _render."""

    def test_render_exception_returns_failed_result(self, sample_dxf: Path, tmp_path: Path):
        """Patch qsave to raise so the outer except branch is exercised."""
        from unittest.mock import patch

        output = tmp_path / "broken.png"

        with patch(
            "ezdxf.addons.drawing.matplotlib.qsave",
            side_effect=RuntimeError("qsave explosion"),
        ):
            result = render_dxf_to_png(sample_dxf, output_path=output)

        assert result.success is False
        assert result.error is not None
        assert "Render failed" in result.error


class TestRenderQualityGuard:
    """Tests for _check_render_quality black/blank detection."""

    def test_detects_mostly_black(self, tmp_path: Path):
        """A nearly-black image triggers a warning."""
        from PIL import Image

        img = Image.new("L", (100, 100), color=5)
        output = tmp_path / "black.png"
        img.save(str(output))

        warnings = _check_render_quality(output)
        assert len(warnings) == 1
        assert "mostly black" in warnings[0]

    def test_detects_blank_white(self, tmp_path: Path):
        """A nearly-white image triggers a warning."""
        from PIL import Image

        img = Image.new("L", (100, 100), color=252)
        output = tmp_path / "white.png"
        img.save(str(output))

        warnings = _check_render_quality(output)
        assert len(warnings) == 1
        assert "blank" in warnings[0]

    def test_normal_render_no_warnings(self, tmp_path: Path):
        """A normal-luminance image produces no warnings."""
        from PIL import Image

        img = Image.new("L", (100, 100), color=128)
        output = tmp_path / "normal.png"
        img.save(str(output))

        warnings = _check_render_quality(output)
        assert len(warnings) == 0

    def test_skips_non_png(self, tmp_path: Path):
        """Non-PNG files are skipped (PDF renders can't be opened by PIL)."""
        output = tmp_path / "render.pdf"
        output.write_bytes(b"%PDF-fake")

        warnings = _check_render_quality(output)
        assert len(warnings) == 0

    def test_render_result_includes_quality_warnings(self, sample_dxf: Path, tmp_path: Path):
        """Successful PNG render includes quality_warnings field."""
        output = tmp_path / "preview.png"
        result = render_dxf_to_png(sample_dxf, output_path=output)
        assert result.success is True
        assert isinstance(result.quality_warnings, list)

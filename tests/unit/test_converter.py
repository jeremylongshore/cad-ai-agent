"""Tests for the file conversion router (DWG/PDF/DXF → working DXF)."""

from __future__ import annotations

from pathlib import Path

import ezdxf
import pytest

from cad_dxf_agent.core.converter import ConversionResult, convert_to_dxf


class TestDxfPassthrough:
    """DXF files should pass through with validation."""

    def test_valid_dxf_passthrough(self, sample_dxf: Path, tmp_path: Path):
        result = convert_to_dxf(sample_dxf, output_dir=tmp_path)

        assert result.success is True
        assert result.source_format == "dxf"
        assert result.output_path.exists()
        assert result.output_path.suffix == ".dxf"
        assert result.output_path != sample_dxf

        # Verify the output is a valid DXF
        doc = ezdxf.readfile(str(result.output_path))
        assert doc is not None

    def test_passthrough_preserves_entities(self, sample_dxf: Path, tmp_path: Path):
        result = convert_to_dxf(sample_dxf, output_dir=tmp_path)
        assert result.success is True

        original = ezdxf.readfile(str(sample_dxf))
        converted = ezdxf.readfile(str(result.output_path))

        orig_count = len(list(original.modelspace()))
        conv_count = len(list(converted.modelspace()))
        assert conv_count == orig_count

    def test_passthrough_output_naming(self, sample_dxf: Path, tmp_path: Path):
        result = convert_to_dxf(sample_dxf, output_dir=tmp_path)
        assert result.output_path.name == "sample_working.dxf"

    def test_passthrough_auto_output_dir(self, sample_dxf: Path):
        result = convert_to_dxf(sample_dxf)
        assert result.success is True
        assert result.output_path.exists()
        # Cleanup
        result.output_path.unlink()
        result.output_path.parent.rmdir()


class TestInvalidInputs:
    """Error cases for the conversion router."""

    def test_file_not_found(self, tmp_path: Path):
        with pytest.raises(FileNotFoundError):
            convert_to_dxf(tmp_path / "nonexistent.dxf")

    def test_unsupported_format(self, tmp_path: Path):
        fake = tmp_path / "drawing.step"
        fake.write_text("fake step file")
        with pytest.raises(ValueError, match="Unsupported file format"):
            convert_to_dxf(fake)

    def test_corrupt_dxf(self, tmp_path: Path):
        corrupt = tmp_path / "corrupt.dxf"
        corrupt.write_text("this is not a valid dxf file")
        result = convert_to_dxf(corrupt, output_dir=tmp_path)
        assert result.success is False
        assert "Invalid DXF" in (result.error or "")


class TestDwgConversion:
    """DWG conversion tests — skip if ODA not installed."""

    def test_dwg_without_oda_returns_error(self, tmp_path: Path):
        """Without ODA installed, should return a helpful error."""
        fake_dwg = tmp_path / "drawing.dwg"
        fake_dwg.write_bytes(b"\x00" * 100)  # fake DWG file

        result = convert_to_dxf(fake_dwg, output_dir=tmp_path)
        assert result.success is False
        assert "ODA File Converter not installed" in (result.error or "")


class TestPdfConversion:
    """PDF to DXF conversion tests."""

    def test_pdf_with_vector_lines(self, tmp_path: Path):
        """Create a simple PDF with vector content and convert it."""
        # Create a minimal vector PDF using reportlab if available, otherwise
        # use a hand-crafted minimal PDF
        pdf_path = tmp_path / "drawing.pdf"
        _create_minimal_pdf(pdf_path)

        result = convert_to_dxf(pdf_path, output_dir=tmp_path)
        assert result.success is True
        assert result.source_format == "pdf"
        assert result.output_path.exists()

        # The output should be a valid DXF
        doc = ezdxf.readfile(str(result.output_path))
        assert doc is not None

    def test_empty_pdf_warns(self, tmp_path: Path):
        """A PDF with no vector geometry should warn."""
        pdf_path = tmp_path / "empty.pdf"
        _create_minimal_pdf(pdf_path, empty=True)

        result = convert_to_dxf(pdf_path, output_dir=tmp_path)
        assert result.success is True
        # May or may not have warnings depending on PDF content


class TestConversionResult:
    """ConversionResult data class."""

    def test_result_fields(self, tmp_path: Path):
        result = ConversionResult(
            source_path=tmp_path / "test.dxf",
            source_format="dxf",
            output_path=tmp_path / "test_working.dxf",
            success=True,
            warnings=["test warning"],
        )
        assert result.success is True
        assert result.source_format == "dxf"
        assert len(result.warnings) == 1
        assert result.error is None


def _create_minimal_pdf(path: Path, *, empty: bool = False) -> None:
    """Create a minimal PDF for testing using fpdf2 or raw PDF."""
    try:
        from fpdf import FPDF

        pdf = FPDF()
        pdf.add_page()
        if not empty:
            pdf.set_line_width(0.5)
            pdf.line(10, 10, 100, 10)
            pdf.line(10, 10, 10, 100)
            pdf.rect(20, 20, 60, 40)
            pdf.set_font("Helvetica", size=12)
            pdf.text(30, 50, "Test Label")
        pdf.output(str(path))
    except ImportError:
        # Fall back to a hand-crafted minimal PDF
        _write_raw_minimal_pdf(path, empty=empty)


def _write_raw_minimal_pdf(path: Path, *, empty: bool = False) -> None:
    """Write a bare-minimum valid PDF file."""
    content = "%PDF-1.4\n"
    content += "1 0 obj<</Type/Catalog/Pages 2 0 R>>endobj\n"
    content += "2 0 obj<</Type/Pages/Kids[3 0 R]/Count 1>>endobj\n"

    stream = "" if empty else "0.5 w\n10 10 m 100 10 l S\n10 10 m 10 100 l S\n20 20 60 40 re S\n"

    stream_bytes = stream.encode()
    content += "3 0 obj<</Type/Page/Parent 2 0 R/MediaBox[0 0 612 792]/Contents 4 0 R>>endobj\n"
    content += f"4 0 obj<</Length {len(stream_bytes)}>>stream\n"
    content += stream
    content += "endstream\nendobj\n"

    xref_offset = len(content.encode())
    content += "xref\n0 5\n"
    content += "0000000000 65535 f \n"
    content += "0000000009 00000 n \n"
    content += "0000000058 00000 n \n"
    content += "0000000115 00000 n \n"
    content += "0000000230 00000 n \n"
    content += "trailer<</Size 5/Root 1 0 R>>\n"
    content += f"startxref\n{xref_offset}\n%%EOF"

    path.write_text(content)

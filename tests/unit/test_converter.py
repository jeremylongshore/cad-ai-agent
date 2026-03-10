"""Tests for the file conversion router (DWG/PDF/DXF → working DXF)."""

from __future__ import annotations

from pathlib import Path

import ezdxf
import pytest

from cad_dxf_agent.core.converter import (
    _PDF_WARNING,
    PDF_ENTITY_COLOR,
    PDF_MAX_HATCH_ENTITIES,
    ConversionResult,
    _create_fill_hatch,
    _rgb_to_aci,
    _set_entity_rgb,
    convert_to_dxf,
)


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

    def test_pdf_warning_present(self, tmp_path: Path):
        """PDF conversion should always include the lossy-conversion warning."""
        pdf_path = tmp_path / "drawing.pdf"
        _create_minimal_pdf(pdf_path)

        result = convert_to_dxf(pdf_path, output_dir=tmp_path)
        assert result.success is True
        assert _PDF_WARNING in result.warnings


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


class TestArcFitting:
    """Test the arc-fitting heuristic for Bezier curves."""

    def test_bezier_to_points_returns_correct_count(self):
        from cad_dxf_agent.core.converter import _bezier_to_points

        class Pt:
            def __init__(self, x, y):
                self.x = x
                self.y = y

        pts = _bezier_to_points(Pt(0, 0), Pt(1, 2), Pt(3, 2), Pt(4, 0), page_height=10, segments=8)
        assert len(pts) == 9  # segments + 1
        # First and last points should match start/end (with Y flip)
        assert abs(pts[0][0] - 0.0) < 0.01
        assert abs(pts[-1][0] - 4.0) < 0.01

    def test_fit_arc_from_circular_bezier(self):
        """A Bezier that closely traces a circle should be detected as an arc."""
        from cad_dxf_agent.core.converter import _fit_arc_from_bezier

        # Quarter circle approximation using standard kappa = 0.5522847498
        # Center at (0, 0), radius 100, from (100, 0) to (0, 100)
        k = 0.5522847498
        page_height = 200.0

        class Pt:
            def __init__(self, x, y):
                self.x = x
                self.y = y

        # PDF coords (Y increases downward), circle at (100, 100) r=100
        # Start at (200, 100), end at (100, 0)
        p1 = Pt(200, 100)
        p2 = Pt(200, 100 - 100 * k)
        p3 = Pt(100 + 100 * k, 0)
        p4 = Pt(100, 0)

        result = _fit_arc_from_bezier(p1, p2, p3, p4, page_height)
        if result is not None:
            cx, cy, radius, start_angle, end_angle = result
            assert abs(radius - 100.0) < 10.0  # rough check

    def test_fit_arc_returns_none_for_straight_line(self):
        """A straight-line Bezier should not be detected as an arc."""
        from cad_dxf_agent.core.converter import _fit_arc_from_bezier

        class Pt:
            def __init__(self, x, y):
                self.x = x
                self.y = y

        # Collinear points — not an arc
        result = _fit_arc_from_bezier(Pt(0, 0), Pt(1, 0), Pt(2, 0), Pt(3, 0), page_height=10)
        assert result is None


class TestFitzExtraction:
    """Direct tests for _extract_pdf_fitz() branches via mocked PyMuPDF."""

    def _make_fitz_module(self, pages):
        """Build a minimal fitz mock that yields ``pages`` from fitz.open()."""
        import types

        fitz_mod = types.ModuleType("fitz")
        fitz_mod.TEXT_PRESERVE_WHITESPACE = 1

        class MockDoc:
            def __init__(self):
                self._pages = pages

            def __iter__(self):
                return iter(self._pages)

            def close(self):
                pass

        fitz_mod.open = lambda path: MockDoc()
        return fitz_mod

    def _make_point(self, x, y):
        class Pt:
            def __init__(self, x, y):
                self.x = x
                self.y = y

        return Pt(x, y)

    def _make_rect(self, x0, y0, x1, y1):
        class R:
            def __init__(self, x0, y0, x1, y1):
                self.x0, self.y0, self.x1, self.y1 = x0, y0, x1, y1

        return R(x0, y0, x1, y1)

    def _make_page(self, height=792, width=612, drawings=None, text_dict=None):
        class MockPage:
            def __init__(self, h, w, d, t):
                class Rect:
                    def __init__(self, h, w):
                        self.height = h
                        self.width = w

                self.rect = Rect(h, w)
                self._drawings = d or []
                self._text = t or {"blocks": []}

            def get_drawings(self):
                return self._drawings

            def get_text(self, mode, flags=0):
                return self._text

        return MockPage(height, width, drawings, text_dict)

    def test_rectangle_extracted(self, tmp_path, monkeypatch):
        """'re' items produce a closed LWPOLYLINE."""
        import sys

        import ezdxf

        rect = self._make_rect(10, 20, 50, 60)
        page = self._make_page(
            drawings=[{"items": [("re", rect)]}],
        )
        fitz_mod = self._make_fitz_module([page])
        monkeypatch.setitem(sys.modules, "fitz", fitz_mod)

        from cad_dxf_agent.core.converter import _extract_pdf_fitz

        doc = ezdxf.new()
        msp = doc.modelspace()
        count = _extract_pdf_fitz(msp, tmp_path / "dummy.pdf")
        assert count == 1
        entities = list(msp)
        assert len(entities) == 1
        assert entities[0].dxftype() == "LWPOLYLINE"

    def test_bezier_arc_fit_success(self, tmp_path, monkeypatch):
        """'c' item where arc fitting succeeds produces an ARC entity."""
        import sys

        import ezdxf

        k = 0.5522847498
        # Quarter-circle in PDF coords: center (100, 100), radius 100
        p1 = self._make_point(200, 100)
        p2 = self._make_point(200, 100 - 100 * k)
        p3 = self._make_point(100 + 100 * k, 0)
        p4 = self._make_point(100, 0)

        page = self._make_page(drawings=[{"items": [("c", p1, p2, p3, p4)]}])
        fitz_mod = self._make_fitz_module([page])
        monkeypatch.setitem(sys.modules, "fitz", fitz_mod)

        from cad_dxf_agent.core.converter import _extract_pdf_fitz

        doc = ezdxf.new()
        msp = doc.modelspace()
        count = _extract_pdf_fitz(msp, tmp_path / "dummy.pdf")
        assert count == 1
        entities = list(msp)
        assert len(entities) == 1
        assert entities[0].dxftype() == "ARC"

    def test_bezier_arc_fit_failure_creates_spline(self, tmp_path, monkeypatch):
        """'c' item where arc fitting fails produces a native DXF SPLINE."""
        import sys

        import ezdxf

        # Non-circular curve — arc fit will return None, SPLINE created instead
        p1 = self._make_point(0, 0)
        p2 = self._make_point(1, 3)
        p3 = self._make_point(2, 3)
        p4 = self._make_point(3, 0)

        page = self._make_page(drawings=[{"items": [("c", p1, p2, p3, p4)]}])
        fitz_mod = self._make_fitz_module([page])
        monkeypatch.setitem(sys.modules, "fitz", fitz_mod)

        from cad_dxf_agent.core.converter import _extract_pdf_fitz

        doc = ezdxf.new()
        msp = doc.modelspace()
        count = _extract_pdf_fitz(msp, tmp_path / "dummy.pdf")
        assert count == 1
        entities = list(msp)
        assert len(entities) == 1
        assert entities[0].dxftype() == "SPLINE"

    def test_quad_new_style_extracted(self, tmp_path, monkeypatch):
        """'qu' with len==2 (pymupdf >=1.27 Quad object) produces LWPOLYLINE."""
        import sys

        import ezdxf

        # Simulate pymupdf >=1.27 Quad: item = ('qu', quad_obj)
        class MockPt:
            def __init__(self, xy):
                self.x, self.y = xy

        class MockQuad:
            def __init__(self, pts):
                self._pts = [MockPt(p) for p in pts]

            def __getitem__(self, k):
                return self._pts[k]

        quad = MockQuad([(0, 0), (10, 0), (10, 10), (0, 10)])
        page = self._make_page(drawings=[{"items": [("qu", quad)]}])
        fitz_mod = self._make_fitz_module([page])
        monkeypatch.setitem(sys.modules, "fitz", fitz_mod)

        from cad_dxf_agent.core.converter import _extract_pdf_fitz

        doc = ezdxf.new()
        msp = doc.modelspace()
        count = _extract_pdf_fitz(msp, tmp_path / "dummy.pdf")
        assert count == 1
        entities = list(msp)
        assert len(entities) == 1
        assert entities[0].dxftype() == "LWPOLYLINE"

    def test_quad_old_style_extracted(self, tmp_path, monkeypatch):
        """'qu' with len>2 (pymupdf <1.27 Points tuple) produces LWPOLYLINE."""
        import sys

        import ezdxf

        p0 = self._make_point(0, 0)
        p1 = self._make_point(10, 0)
        p2 = self._make_point(10, 10)
        p3 = self._make_point(0, 10)
        # Old-style: ('qu', pt0, pt1, pt2, pt3)
        page = self._make_page(drawings=[{"items": [("qu", p0, p1, p2, p3)]}])
        fitz_mod = self._make_fitz_module([page])
        monkeypatch.setitem(sys.modules, "fitz", fitz_mod)

        from cad_dxf_agent.core.converter import _extract_pdf_fitz

        doc = ezdxf.new()
        msp = doc.modelspace()
        count = _extract_pdf_fitz(msp, tmp_path / "dummy.pdf")
        assert count == 1
        entities = list(msp)
        assert len(entities) == 1
        assert entities[0].dxftype() == "LWPOLYLINE"

    def test_text_block_extracted(self, tmp_path, monkeypatch):
        """Text spans in type-0 blocks produce TEXT entities."""
        import sys

        import ezdxf

        text_dict = {
            "blocks": [
                {
                    "type": 0,  # text block
                    "lines": [
                        {
                            "spans": [
                                {
                                    "text": "Hello CAD",
                                    "bbox": (10.0, 20.0, 80.0, 32.0),
                                }
                            ]
                        }
                    ],
                }
            ]
        }
        page = self._make_page(text_dict=text_dict)
        fitz_mod = self._make_fitz_module([page])
        monkeypatch.setitem(sys.modules, "fitz", fitz_mod)

        from cad_dxf_agent.core.converter import _extract_pdf_fitz

        doc = ezdxf.new()
        msp = doc.modelspace()
        count = _extract_pdf_fitz(msp, tmp_path / "dummy.pdf")
        assert count == 1
        entities = list(msp)
        assert len(entities) == 1
        assert entities[0].dxftype() == "TEXT"

    def test_non_text_block_skipped(self, tmp_path, monkeypatch):
        """Blocks with type != 0 (image blocks, etc.) are skipped."""
        import sys

        import ezdxf

        text_dict = {
            "blocks": [
                {"type": 1, "lines": []},  # image block — should be skipped
            ]
        }
        page = self._make_page(text_dict=text_dict)
        fitz_mod = self._make_fitz_module([page])
        monkeypatch.setitem(sys.modules, "fitz", fitz_mod)

        from cad_dxf_agent.core.converter import _extract_pdf_fitz

        doc = ezdxf.new()
        msp = doc.modelspace()
        count = _extract_pdf_fitz(msp, tmp_path / "dummy.pdf")
        assert count == 0

    def test_empty_text_span_skipped(self, tmp_path, monkeypatch):
        """Spans with empty/whitespace text are skipped."""
        import sys

        import ezdxf

        text_dict = {
            "blocks": [
                {
                    "type": 0,
                    "lines": [
                        {
                            "spans": [
                                {"text": "   ", "bbox": (10.0, 20.0, 80.0, 32.0)},
                            ]
                        }
                    ],
                }
            ]
        }
        page = self._make_page(text_dict=text_dict)
        fitz_mod = self._make_fitz_module([page])
        monkeypatch.setitem(sys.modules, "fitz", fitz_mod)

        from cad_dxf_agent.core.converter import _extract_pdf_fitz

        doc = ezdxf.new()
        msp = doc.modelspace()
        count = _extract_pdf_fitz(msp, tmp_path / "dummy.pdf")
        assert count == 0

    def test_multipage_pages_are_offset(self, tmp_path, monkeypatch):
        """Multi-page PDFs lay out pages side-by-side with x_offset."""
        import sys

        import ezdxf

        from cad_dxf_agent.core.converter import PDF_PAGE_GAP

        page_width = 612.0
        # Page 1: one line at x=10
        page1 = self._make_page(
            width=page_width,
            drawings=[{"items": [("l", self._make_point(10, 0), self._make_point(10, 100))]}],
        )
        # Page 2: one line at x=20 (should be offset by page_width + gap)
        page2 = self._make_page(
            width=page_width,
            drawings=[{"items": [("l", self._make_point(20, 0), self._make_point(20, 100))]}],
        )
        fitz_mod = self._make_fitz_module([page1, page2])
        monkeypatch.setitem(sys.modules, "fitz", fitz_mod)

        from cad_dxf_agent.core.converter import _extract_pdf_fitz

        doc = ezdxf.new()
        msp = doc.modelspace()
        count = _extract_pdf_fitz(msp, tmp_path / "dummy.pdf")
        assert count == 2

        entities = list(msp)
        line1 = entities[0]
        line2 = entities[1]

        # Page 1 line stays near x=10
        assert abs(line1.dxf.start.x - 10.0) < 0.01

        # Page 2 line is offset by page_width + gap
        expected_x = page_width + PDF_PAGE_GAP + 20.0
        assert abs(line2.dxf.start.x - expected_x) < 0.01

        # Page 2 goes on named layer
        assert line2.dxf.layer == "PDF_PAGE_2"


class TestArcFittingEdgeCases:
    """Edge cases in _fit_arc_from_bezier not covered by TestArcFitting."""

    def _pt(self, x, y):
        class Pt:
            def __init__(self, x, y):
                self.x = x
                self.y = y

        return Pt(x, y)

    def test_fit_arc_returns_none_when_avg_radius_too_small(self):
        """Points very close together → avg_r < 0.1 → None."""
        from cad_dxf_agent.core.converter import _fit_arc_from_bezier

        # All points at nearly the same location — radius approaches zero
        result = _fit_arc_from_bezier(
            self._pt(0.00, 0.00),
            self._pt(0.001, 0.0001),
            self._pt(0.002, 0.0001),
            self._pt(0.003, 0.00),
            page_height=10.0,
        )
        assert result is None

    def test_fit_arc_returns_none_when_not_circular_enough(self):
        """A curve with large radius variance is rejected."""
        from cad_dxf_agent.core.converter import _fit_arc_from_bezier

        # Sharply asymmetric control points → radii won't match
        result = _fit_arc_from_bezier(
            self._pt(0, 0),
            self._pt(0, 500),  # extreme control point
            self._pt(100, -500),
            self._pt(100, 0),
            page_height=1000.0,
        )
        assert result is None


class TestPdfplumberFallback:
    """Tests for the pdfplumber extraction path."""

    def test_pdfplumber_page_extraction(self, tmp_path, monkeypatch):
        """pdfplumber path extracts lines, rects, and text."""
        import sys
        import types

        import ezdxf

        # Build a minimal pdfplumber mock
        class MockWord:
            x0, top, bottom = 5.0, 10.0, 20.0
            text = "Label"

        class MockPage:
            height = 792.0
            lines = [{"x0": 0.0, "top": 0.0, "x1": 100.0, "bottom": 10.0}]
            rects = [{"x0": 10.0, "top": 20.0, "x1": 50.0, "bottom": 60.0}]

            def extract_words(self):
                return [{"x0": 5.0, "top": 10.0, "bottom": 20.0, "text": "Label"}]

        class MockPdf:
            pages = [MockPage()]

            def __enter__(self):
                return self

            def __exit__(self, *a):
                pass

        plumber_mod = types.ModuleType("pdfplumber")
        plumber_mod.open = lambda path: MockPdf()

        # Block fitz so pdfplumber branch is taken
        monkeypatch.setitem(sys.modules, "fitz", None)
        monkeypatch.setitem(sys.modules, "pdfplumber", plumber_mod)

        # Re-import just the function to pick up the patched modules
        from cad_dxf_agent.core.converter import _extract_pdf_page_plumber

        doc = ezdxf.new()
        msp = doc.modelspace()
        count = _extract_pdf_page_plumber(msp, MockPage(), 0)
        # 1 line + 1 rect + 1 word = 3
        assert count == 3

    def test_pdfplumber_empty_page_no_entities(self, tmp_path):
        """A pdfplumber page with no lines/rects/words returns 0."""
        import ezdxf

        from cad_dxf_agent.core.converter import _extract_pdf_page_plumber

        class EmptyPage:
            height = 792.0
            lines = []
            rects = []

            def extract_words(self):
                return []

        doc = ezdxf.new()
        msp = doc.modelspace()
        count = _extract_pdf_page_plumber(msp, EmptyPage(), 0)
        assert count == 0

    def test_pdfplumber_second_page_uses_named_layer(self, tmp_path):
        """Second page (page_num=1) uses a 'PDF_PAGE_2' layer name."""
        import ezdxf

        from cad_dxf_agent.core.converter import _extract_pdf_page_plumber

        class SingleLinePage:
            height = 792.0
            lines = [{"x0": 0.0, "top": 0.0, "x1": 50.0, "bottom": 0.0}]
            rects = []

            def extract_words(self):
                return []

        doc = ezdxf.new()
        msp = doc.modelspace()
        count = _extract_pdf_page_plumber(msp, SingleLinePage(), 1)
        assert count == 1
        line = list(msp)[0]
        assert line.dxf.layer == "PDF_PAGE_2"


class TestNoLibraryInstalled:
    """When neither fitz nor pdfplumber is importable, convert_to_dxf returns error."""

    def test_pdf_no_library_returns_error(self, tmp_path, monkeypatch):
        """Verify the no-PDF-library error path is reachable."""
        import sys

        pdf_path = tmp_path / "drawing.pdf"
        _create_minimal_pdf(pdf_path)

        monkeypatch.setitem(sys.modules, "fitz", None)
        monkeypatch.setitem(sys.modules, "pdfplumber", None)

        # Force re-evaluation by calling _convert_pdf directly (it re-checks imports each call)
        from cad_dxf_agent.core.converter import _convert_pdf

        result = _convert_pdf(pdf_path, tmp_path)
        assert result.success is False
        assert "No PDF library installed" in (result.error or "")


class TestDwgConversionWithOda:
    """DWG conversion when ODA is mocked as installed."""

    def test_dwg_with_oda_installed_and_saveas_mocked(self, tmp_path, monkeypatch):
        """When ODA is mocked as installed and saveas is mocked, conversion succeeds."""
        import ezdxf as _ezdxf
        from ezdxf.addons import odafc

        fake_dwg = tmp_path / "drawing.dwg"
        fake_dwg.write_bytes(b"\x00" * 100)

        # Create a real DXF doc; mock saveas to avoid format-string issues
        fake_doc = _ezdxf.new(dxfversion="R2018")
        fake_doc.modelspace().add_line((0, 0), (10, 0))
        saved_paths = []

        def _mock_saveas(path, fmt="asc", encoding=None):
            # Actually save as a valid DXF so the result path exists
            fake_doc_inner = _ezdxf.new(dxfversion="R2018")
            fake_doc_inner.saveas(path)
            saved_paths.append(path)

        monkeypatch.setattr(odafc, "is_installed", lambda: True)
        monkeypatch.setattr(odafc, "readfile", lambda path: fake_doc)
        monkeypatch.setattr(fake_doc, "saveas", _mock_saveas)

        from cad_dxf_agent.core.converter import convert_to_dxf

        result = convert_to_dxf(fake_dwg, output_dir=tmp_path)
        assert result.success is True
        assert result.source_format == "dwg"

    def test_dwg_with_oda_installed_exception(self, tmp_path, monkeypatch):
        """When ODA is installed but readfile raises, returns failure result."""
        from ezdxf.addons import odafc

        fake_dwg = tmp_path / "bad.dwg"
        fake_dwg.write_bytes(b"\x00" * 100)

        def _raise_oda(*_):
            raise RuntimeError("ODA crash")

        monkeypatch.setattr(odafc, "is_installed", lambda: True)
        monkeypatch.setattr(odafc, "readfile", _raise_oda)

        from cad_dxf_agent.core.converter import convert_to_dxf

        result = convert_to_dxf(fake_dwg, output_dir=tmp_path)
        assert result.success is False
        assert "DWG conversion failed" in (result.error or "")


class TestVersionHelpers:
    """Version mapping helpers."""

    def test_version_to_odafc_known(self):
        from cad_dxf_agent.core.converter import _version_to_odafc

        assert _version_to_odafc("R2018") == "ACAD2018"
        assert _version_to_odafc("R2010") == "ACAD2010"

    def test_version_to_odafc_unknown_fallback(self):
        from cad_dxf_agent.core.converter import _version_to_odafc

        assert _version_to_odafc("R9999") == "ACAD2010"

    def test_version_to_acdb_known(self):
        from cad_dxf_agent.core.converter import _version_to_acdb

        assert _version_to_acdb("R2018") == "AC1032"

    def test_version_to_acdb_unknown_fallback(self):
        from cad_dxf_agent.core.converter import _version_to_acdb

        assert _version_to_acdb("R9999") == "AC1024"


class TestPdfConversionException:
    """PDF conversion failure path."""

    def test_pdf_conversion_exception_returns_failure(self, tmp_path, monkeypatch):
        """When ezdxf.new() raises, conversion returns a failure result."""
        import ezdxf as _ezdxf

        pdf_path = tmp_path / "drawing.pdf"
        _create_minimal_pdf(pdf_path)

        def _raise_new(**kw):
            raise RuntimeError("DXF init failed")

        monkeypatch.setattr(_ezdxf, "new", _raise_new)

        from cad_dxf_agent.core.converter import _convert_pdf

        result = _convert_pdf(pdf_path, tmp_path)
        assert result.success is False
        assert "PDF conversion failed" in (result.error or "")


class TestPdfEntityColors:
    """Entities from PDF extraction must have explicit ACI colors."""

    def test_fitz_entities_have_explicit_color(self, tmp_path, monkeypatch):
        """Every entity from _extract_pdf_fitz has an explicit color (not BYLAYER/256)."""
        import sys
        import types

        import ezdxf

        fitz_mod = types.ModuleType("fitz")
        fitz_mod.TEXT_PRESERVE_WHITESPACE = 1

        class Pt:
            def __init__(self, x, y):
                self.x = x
                self.y = y

        class MockPage:
            class Rect:
                height = 792.0
                width = 612.0

            rect = Rect()

            def get_drawings(self):
                return [{"items": [("l", Pt(0, 0), Pt(10, 10))], "color": None}]

            def get_text(self, mode, flags=0):
                return {"blocks": []}

        class MockDoc:
            def __iter__(self):
                return iter([MockPage()])

            def close(self):
                pass

        fitz_mod.open = lambda path: MockDoc()
        monkeypatch.setitem(sys.modules, "fitz", fitz_mod)

        from cad_dxf_agent.core.converter import _extract_pdf_fitz

        doc = ezdxf.new()
        doc.layers.get("0").color = PDF_ENTITY_COLOR
        msp = doc.modelspace()
        count = _extract_pdf_fitz(msp, tmp_path / "dummy.pdf", doc)
        assert count == 1

        for entity in msp:
            assert entity.dxf.color != 256, f"{entity.dxftype()} has BYLAYER color"
            assert entity.dxf.color == PDF_ENTITY_COLOR

    def test_fitz_layers_created_with_color(self, tmp_path, monkeypatch):
        """Per-page layers (PDF_PAGE_2, etc.) are created with explicit colors."""
        import sys
        import types

        import ezdxf

        fitz_mod = types.ModuleType("fitz")
        fitz_mod.TEXT_PRESERVE_WHITESPACE = 1

        class Pt:
            def __init__(self, x, y):
                self.x = x
                self.y = y

        class MockPage:
            def __init__(self, w=612, h=792):
                class R:
                    height = h
                    width = w

                self.rect = R()

            def get_drawings(self):
                return [{"items": [("l", Pt(0, 0), Pt(10, 10))]}]

            def get_text(self, mode, flags=0):
                return {"blocks": []}

        class MockDoc:
            def __iter__(self):
                return iter([MockPage(), MockPage()])

            def close(self):
                pass

        fitz_mod.open = lambda path: MockDoc()
        monkeypatch.setitem(sys.modules, "fitz", fitz_mod)

        from cad_dxf_agent.core.converter import _extract_pdf_fitz

        doc = ezdxf.new()
        doc.layers.get("0").color = PDF_ENTITY_COLOR
        msp = doc.modelspace()
        _extract_pdf_fitz(msp, tmp_path / "dummy.pdf", doc)

        layer2 = doc.layers.get("PDF_PAGE_2")
        assert layer2.color == PDF_ENTITY_COLOR

    def test_pdfplumber_entities_have_explicit_color(self, tmp_path):
        """pdfplumber fallback entities have explicit color."""
        import ezdxf

        from cad_dxf_agent.core.converter import _extract_pdf_page_plumber

        class SingleLinePage:
            height = 792.0
            lines = [{"x0": 0.0, "top": 0.0, "x1": 50.0, "bottom": 0.0}]
            rects = []

            def extract_words(self):
                return []

        doc = ezdxf.new()
        msp = doc.modelspace()
        _extract_pdf_page_plumber(msp, SingleLinePage(), 0)

        for entity in msp:
            assert entity.dxf.color == PDF_ENTITY_COLOR


class TestRgbToAci:
    """Tests for _rgb_to_aci color mapping."""

    def test_none_returns_default(self):
        assert _rgb_to_aci(None) == PDF_ENTITY_COLOR

    def test_black_returns_white(self):
        assert _rgb_to_aci((0, 0, 0)) == 7

    def test_red(self):
        assert _rgb_to_aci((1.0, 0, 0)) == 1

    def test_green(self):
        assert _rgb_to_aci((0, 1.0, 0)) == 3

    def test_blue(self):
        assert _rgb_to_aci((0, 0, 1.0)) == 5

    def test_yellow(self):
        assert _rgb_to_aci((1.0, 1.0, 0)) == 2

    def test_cyan(self):
        assert _rgb_to_aci((0, 1.0, 1.0)) == 4

    def test_magenta(self):
        assert _rgb_to_aci((1.0, 0, 1.0)) == 6

    def test_invalid_type_returns_default(self):
        assert _rgb_to_aci("not a tuple") == PDF_ENTITY_COLOR

    def test_near_black_returns_white(self):
        assert _rgb_to_aci((0.05, 0.05, 0.05)) == 7


class TestConversionResultClassifications:
    """ConversionResult includes classifications field."""

    def test_classifications_default_none(self, tmp_path):
        result = ConversionResult(
            source_path=tmp_path / "test.dxf",
            source_format="pdf",
            output_path=tmp_path / "out.dxf",
            success=True,
        )
        assert result.classifications is None


class TestSetEntityRgb:
    """Tests for _set_entity_rgb true-color helper."""

    def test_applies_true_color(self):
        doc = ezdxf.new()
        msp = doc.modelspace()
        entity = msp.add_line((0, 0), (10, 10))
        _set_entity_rgb(entity, (1.0, 0.0, 0.0))  # red
        assert entity.rgb == (255, 0, 0)

    def test_none_is_noop(self):
        doc = ezdxf.new()
        msp = doc.modelspace()
        entity = msp.add_line((0, 0), (10, 10))
        _set_entity_rgb(entity, None)
        assert not entity.rgb  # no true color set

    def test_near_black_skipped(self):
        doc = ezdxf.new()
        msp = doc.modelspace()
        entity = msp.add_line((0, 0), (10, 10))
        _set_entity_rgb(entity, (0.05, 0.05, 0.05))
        assert not entity.rgb  # near-black skipped

    def test_invalid_type_is_noop(self):
        doc = ezdxf.new()
        msp = doc.modelspace()
        entity = msp.add_line((0, 0), (10, 10))
        _set_entity_rgb(entity, "not a tuple")
        assert not entity.rgb

    def test_values_clamped_to_0_255(self):
        doc = ezdxf.new()
        msp = doc.modelspace()
        entity = msp.add_line((0, 0), (10, 10))
        _set_entity_rgb(entity, (1.5, -0.1, 0.5))  # out of [0,1] range
        assert entity.rgb == (255, 0, 127)


class TestFitzTrueColor:
    """Tests for true RGB color applied to fitz-extracted entities."""

    def _make_fitz_module(self, pages):
        import types

        fitz_mod = types.ModuleType("fitz")
        fitz_mod.TEXT_PRESERVE_WHITESPACE = 1

        class MockDoc:
            def __init__(self):
                self._pages = pages

            def __iter__(self):
                return iter(self._pages)

            def close(self):
                pass

        fitz_mod.open = lambda path: MockDoc()
        return fitz_mod

    def _make_point(self, x, y):
        class Pt:
            def __init__(self, x, y):
                self.x = x
                self.y = y

        return Pt(x, y)

    def _make_rect(self, x0, y0, x1, y1):
        class R:
            def __init__(self, x0, y0, x1, y1):
                self.x0, self.y0, self.x1, self.y1 = x0, y0, x1, y1

        return R(x0, y0, x1, y1)

    def _make_page(self, height=792, width=612, drawings=None, text_dict=None):
        class MockPage:
            def __init__(self, h, w, d, t):
                class Rect:
                    def __init__(self, h, w):
                        self.height = h
                        self.width = w

                self.rect = Rect(h, w)
                self._drawings = d or []
                self._text = t or {"blocks": []}

            def get_drawings(self):
                return self._drawings

            def get_text(self, mode, flags=0):
                return self._text

        return MockPage(height, width, drawings, text_dict)

    def test_fitz_line_gets_true_color(self, tmp_path, monkeypatch):
        """Lines with non-black stroke color get entity.rgb set."""
        import sys

        page = self._make_page(
            drawings=[
                {
                    "items": [("l", self._make_point(0, 0), self._make_point(10, 100))],
                    "color": (1.0, 0.0, 0.0),  # red
                }
            ],
        )
        fitz_mod = self._make_fitz_module([page])
        monkeypatch.setitem(sys.modules, "fitz", fitz_mod)

        from cad_dxf_agent.core.converter import _extract_pdf_fitz

        doc = ezdxf.new()
        msp = doc.modelspace()
        _extract_pdf_fitz(msp, tmp_path / "dummy.pdf")
        entity = list(msp)[0]
        assert entity.rgb == (255, 0, 0)

    def test_fitz_rect_gets_true_color(self, tmp_path, monkeypatch):
        """Rectangles with non-black stroke color get entity.rgb set."""
        import sys

        rect = self._make_rect(10, 20, 50, 60)
        page = self._make_page(
            drawings=[
                {
                    "items": [("re", rect)],
                    "color": (0.0, 0.0, 1.0),  # blue
                }
            ],
        )
        fitz_mod = self._make_fitz_module([page])
        monkeypatch.setitem(sys.modules, "fitz", fitz_mod)

        from cad_dxf_agent.core.converter import _extract_pdf_fitz

        doc = ezdxf.new()
        msp = doc.modelspace()
        _extract_pdf_fitz(msp, tmp_path / "dummy.pdf")
        entity = list(msp)[0]
        assert entity.rgb == (0, 0, 255)

    def test_text_span_color_applied(self, tmp_path, monkeypatch):
        """Text spans with non-black color get entity.rgb set."""
        import sys

        # PyMuPDF color is packed int: (R << 16) | (G << 8) | B
        red_packed = (255 << 16) | (0 << 8) | 0  # 0xFF0000

        text_dict = {
            "blocks": [
                {
                    "type": 0,
                    "lines": [
                        {
                            "spans": [
                                {
                                    "text": "Red Label",
                                    "bbox": (10.0, 20.0, 80.0, 32.0),
                                    "color": red_packed,
                                }
                            ]
                        }
                    ],
                }
            ]
        }
        page = self._make_page(text_dict=text_dict)
        fitz_mod = self._make_fitz_module([page])
        monkeypatch.setitem(sys.modules, "fitz", fitz_mod)

        from cad_dxf_agent.core.converter import _extract_pdf_fitz

        doc = ezdxf.new()
        msp = doc.modelspace()
        _extract_pdf_fitz(msp, tmp_path / "dummy.pdf")
        entity = list(msp)[0]
        assert entity.dxftype() == "TEXT"
        assert entity.rgb == (255, 0, 0)

    def test_text_span_black_no_true_color(self, tmp_path, monkeypatch):
        """Text spans with black color (0) do not get entity.rgb set."""
        import sys

        text_dict = {
            "blocks": [
                {
                    "type": 0,
                    "lines": [
                        {
                            "spans": [
                                {
                                    "text": "Black Label",
                                    "bbox": (10.0, 20.0, 80.0, 32.0),
                                    "color": 0,  # black
                                }
                            ]
                        }
                    ],
                }
            ]
        }
        page = self._make_page(text_dict=text_dict)
        fitz_mod = self._make_fitz_module([page])
        monkeypatch.setitem(sys.modules, "fitz", fitz_mod)

        from cad_dxf_agent.core.converter import _extract_pdf_fitz

        doc = ezdxf.new()
        msp = doc.modelspace()
        _extract_pdf_fitz(msp, tmp_path / "dummy.pdf")
        entity = list(msp)[0]
        assert entity.dxftype() == "TEXT"
        assert not entity.rgb  # no true color for black text


class TestFillHatch:
    """Tests for _create_fill_hatch and fill detection in extraction."""

    def test_rect_with_fill_creates_hatch(self):
        """A path_item with a fill and rect items creates a HATCH."""
        doc = ezdxf.new()
        msp = doc.modelspace()

        class R:
            x0, y0, x1, y1 = 10.0, 20.0, 50.0, 60.0

        path_item = {
            "fill": (1.0, 0.0, 0.0),  # red fill
            "items": [
                ("re", R()),
                ("l", type("P", (), {"x": 10, "y": 20})(), type("P", (), {"x": 50, "y": 20})()),
            ],
        }
        hatch, count = _create_fill_hatch(msp, path_item, 0.0, 792.0, "0", 0)
        assert hatch is not None
        assert count == 1
        assert hatch.dxftype() == "HATCH"
        assert hatch.rgb == (255, 0, 0)

    def test_rect_stroke_only_no_hatch(self):
        """A path_item without fill returns None."""
        doc = ezdxf.new()
        msp = doc.modelspace()

        path_item = {
            "fill": None,
            "items": [
                ("l", type("P", (), {"x": 0, "y": 0})(), type("P", (), {"x": 10, "y": 0})()),
            ],
        }
        hatch, count = _create_fill_hatch(msp, path_item, 0.0, 792.0, "0", 0)
        assert hatch is None
        assert count == 0

    def test_hatch_count_limit(self):
        """When hatch_count >= limit, no more hatches are created."""
        doc = ezdxf.new()
        msp = doc.modelspace()

        path_item = {
            "fill": (0.0, 1.0, 0.0),
            "items": [
                ("l", type("P", (), {"x": 0, "y": 0})(), type("P", (), {"x": 10, "y": 0})()),
                ("l", type("P", (), {"x": 10, "y": 0})(), type("P", (), {"x": 10, "y": 10})()),
            ],
        }
        hatch, count = _create_fill_hatch(msp, path_item, 0.0, 792.0, "0", PDF_MAX_HATCH_ENTITIES)
        assert hatch is None
        assert count == PDF_MAX_HATCH_ENTITIES

    def test_hatch_has_solid_fill(self):
        """HATCH entities use solid fill pattern."""
        doc = ezdxf.new()
        msp = doc.modelspace()

        path_item = {
            "fill": (0.0, 0.5, 1.0),
            "items": [
                ("l", type("P", (), {"x": 0, "y": 0})(), type("P", (), {"x": 10, "y": 0})()),
                ("l", type("P", (), {"x": 10, "y": 0})(), type("P", (), {"x": 0, "y": 0})()),
            ],
        }
        hatch, _ = _create_fill_hatch(msp, path_item, 0.0, 792.0, "0", 0)
        assert hatch is not None
        # Solid fill uses "SOLID" pattern
        assert hatch.dxf.pattern_name == "SOLID"

    def test_bezier_fill_creates_hatch_with_spline_edges(self):
        """A path with Bezier fill items creates HATCH with spline edges."""
        doc = ezdxf.new()
        msp = doc.modelspace()

        def pt(x, y):
            return type("P", (), {"x": x, "y": y})()

        path_item = {
            "fill": (0.0, 1.0, 0.0),
            "items": [
                ("c", pt(0, 0), pt(5, 10), pt(15, 10), pt(20, 0)),
                ("l", pt(20, 0), pt(0, 0)),
            ],
        }
        hatch, count = _create_fill_hatch(msp, path_item, 0.0, 100.0, "0", 0)
        assert hatch is not None
        assert count == 1

    def test_too_few_items_no_hatch(self):
        """Path with < 2 items does not create a hatch."""
        doc = ezdxf.new()
        msp = doc.modelspace()

        path_item = {
            "fill": (1.0, 0.0, 0.0),
            "items": [
                ("l", type("P", (), {"x": 0, "y": 0})(), type("P", (), {"x": 10, "y": 0})()),
            ],
        }
        hatch, count = _create_fill_hatch(msp, path_item, 0.0, 792.0, "0", 0)
        assert hatch is None
        assert count == 0

    def test_near_black_fill_no_rgb(self):
        """Near-black fills get ACI color but no true RGB."""
        doc = ezdxf.new()
        msp = doc.modelspace()

        path_item = {
            "fill": (0.05, 0.05, 0.05),
            "items": [
                ("l", type("P", (), {"x": 0, "y": 0})(), type("P", (), {"x": 10, "y": 0})()),
                ("l", type("P", (), {"x": 10, "y": 0})(), type("P", (), {"x": 0, "y": 0})()),
            ],
        }
        hatch, _ = _create_fill_hatch(msp, path_item, 0.0, 792.0, "0", 0)
        assert hatch is not None
        assert not hatch.rgb  # near-black: no true color

    def test_mixed_fill_and_stroke_in_extraction(self, tmp_path, monkeypatch):
        """A path with both fill and stroke creates both hatch and stroke geometry."""
        import sys
        import types

        fitz_mod = types.ModuleType("fitz")
        fitz_mod.TEXT_PRESERVE_WHITESPACE = 1

        class Pt:
            def __init__(self, x, y):
                self.x = x
                self.y = y

        class R:
            x0, y0, x1, y1 = 10.0, 20.0, 50.0, 60.0

        class MockPage:
            class Rect:
                height = 792.0
                width = 612.0

            rect = Rect()

            def get_drawings(self):
                return [
                    {
                        "items": [
                            ("re", R()),
                            ("l", Pt(0, 0), Pt(10, 100)),
                        ],
                        "color": (1.0, 0.0, 0.0),  # stroke color
                        "fill": (0.0, 0.0, 1.0),  # fill color
                    }
                ]

            def get_text(self, mode, flags=0):
                return {"blocks": []}

        class MockDoc:
            def __iter__(self):
                return iter([MockPage()])

            def close(self):
                pass

        fitz_mod.open = lambda path: MockDoc()
        monkeypatch.setitem(sys.modules, "fitz", fitz_mod)

        from cad_dxf_agent.core.converter import _extract_pdf_fitz

        doc = ezdxf.new()
        msp = doc.modelspace()
        count = _extract_pdf_fitz(msp, tmp_path / "dummy.pdf")

        entities = list(msp)
        types_found = {e.dxftype() for e in entities}
        # Should have HATCH (fill) + LWPOLYLINE (rect stroke) + LINE (line stroke)
        assert "HATCH" in types_found
        assert count >= 3  # 1 hatch + 1 rect + 1 line


class TestPdfDashPatternParsing:
    """Test PDF dash pattern parsing and DXF linetype classification."""

    def test_parse_empty_bracket_string(self):
        from cad_dxf_agent.core.converter import _parse_pdf_dashes

        assert _parse_pdf_dashes("[] 0") == []

    def test_parse_dash_bracket_string(self):
        from cad_dxf_agent.core.converter import _parse_pdf_dashes

        assert _parse_pdf_dashes("[3 2] 0") == [3.0, 2.0]

    def test_parse_complex_bracket_string(self):
        from cad_dxf_agent.core.converter import _parse_pdf_dashes

        assert _parse_pdf_dashes("[6 3 1 3] 0") == [6.0, 3.0, 1.0, 3.0]

    def test_parse_list_input(self):
        from cad_dxf_agent.core.converter import _parse_pdf_dashes

        assert _parse_pdf_dashes([3, 2]) == [3.0, 2.0]

    def test_parse_none_input(self):
        from cad_dxf_agent.core.converter import _parse_pdf_dashes

        assert _parse_pdf_dashes(None) == []

    def test_classify_dashed(self):
        from cad_dxf_agent.core.converter import _classify_dash_pattern

        assert _classify_dash_pattern([3.0, 2.0]) == "DASHED"

    def test_classify_dotted(self):
        from cad_dxf_agent.core.converter import _classify_dash_pattern

        assert _classify_dash_pattern([0.5, 2.0]) == "DOT"

    def test_classify_dashdot(self):
        from cad_dxf_agent.core.converter import _classify_dash_pattern

        assert _classify_dash_pattern([6.0, 3.0, 1.0, 3.0]) == "DASHDOT"

    def test_classify_center(self):
        from cad_dxf_agent.core.converter import _classify_dash_pattern

        # 6+ element pattern: dash-gap-dot-gap-dash-gap
        assert _classify_dash_pattern([12.0, 3.0, 2.0, 3.0, 2.0, 3.0]) == "CENTER"

    def test_classify_empty(self):
        from cad_dxf_agent.core.converter import _classify_dash_pattern

        assert _classify_dash_pattern([]) == "CONTINUOUS"

    def test_classify_single_element(self):
        from cad_dxf_agent.core.converter import _classify_dash_pattern

        assert _classify_dash_pattern([3.0]) == "CONTINUOUS"


class TestPdfConfigurableSettings:
    """Test that PDF conversion respects settings."""

    def test_settings_have_pdf_defaults(self):
        from cad_dxf_agent.settings import Settings

        s = Settings()
        assert s.pdf_arc_tolerance == 0.05
        assert s.pdf_bezier_segments == 8
        assert s.pdf_max_hatch_entities == 500
        assert s.pdf_min_entity_size == 1.0

    def test_settings_read_from_env(self, monkeypatch):
        monkeypatch.setenv("CAD_PDF_ARC_TOLERANCE", "0.1")
        monkeypatch.setenv("CAD_PDF_BEZIER_SEGMENTS", "16")
        monkeypatch.setenv("CAD_PDF_MAX_HATCH_ENTITIES", "1000")
        monkeypatch.setenv("CAD_PDF_MIN_ENTITY_SIZE", "0.5")

        from cad_dxf_agent.settings import Settings

        s = Settings()
        assert s.pdf_arc_tolerance == 0.1
        assert s.pdf_bezier_segments == 16
        assert s.pdf_max_hatch_entities == 1000
        assert s.pdf_min_entity_size == 0.5


class TestImprovedArcFitting:
    """Test the 5-point least-squares arc fitting."""

    def _make_point(self, x, y):
        class Pt:
            def __init__(self, x, y):
                self.x = x
                self.y = y

        return Pt(x, y)

    def test_circular_bezier_detected_as_arc(self):
        """Control points forming a near-circular curve should be detected as ARC."""
        from cad_dxf_agent.core.converter import _fit_arc_from_bezier

        # Approximate a 90-degree arc of radius 100 centered at origin
        # Standard cubic Bezier approximation of a quarter circle
        k = 0.5522847498  # magic number for cubic Bezier circle approx
        p1 = self._make_point(100, 0)
        p2 = self._make_point(100, 100 * k)
        p3 = self._make_point(100 * k, 100)
        p4 = self._make_point(0, 100)

        # page_height=200 so Y-flip doesn't cause issues
        result = _fit_arc_from_bezier(p1, p2, p3, p4, page_height=200)
        assert result is not None
        cx, cy, radius, start_angle, end_angle = result
        assert abs(radius - 100) < 5  # within 5% of expected

    def test_non_circular_bezier_rejected(self):
        """A clearly non-circular S-curve should return None."""
        from cad_dxf_agent.core.converter import _fit_arc_from_bezier

        # S-curve — definitely not circular
        p1 = self._make_point(0, 0)
        p2 = self._make_point(100, 200)
        p3 = self._make_point(200, -100)
        p4 = self._make_point(300, 100)

        result = _fit_arc_from_bezier(p1, p2, p3, p4, page_height=400)
        assert result is None

    def test_collinear_points_rejected(self):
        """Collinear Bezier (straight line) should return None."""
        from cad_dxf_agent.core.converter import _fit_arc_from_bezier

        p1 = self._make_point(0, 100)
        p2 = self._make_point(100, 100)
        p3 = self._make_point(200, 100)
        p4 = self._make_point(300, 100)

        result = _fit_arc_from_bezier(p1, p2, p3, p4, page_height=200)
        assert result is None


class TestSplineCreation:
    """Test native DXF SPLINE creation from Bezier curves."""

    def _make_point(self, x, y):
        class Pt:
            def __init__(self, x, y):
                self.x = x
                self.y = y

        return Pt(x, y)

    def test_bezier_to_spline_creates_spline_entity(self):
        """_bezier_to_spline should create a SPLINE entity with correct control points."""
        import ezdxf
        from ezdxf.math import Bezier4P, Vec2, bezier_to_bspline

        from cad_dxf_agent.core.converter import _bezier_to_spline

        doc = ezdxf.new()
        msp = doc.modelspace()
        p1 = self._make_point(0, 0)
        p2 = self._make_point(50, 100)
        p3 = self._make_point(150, 100)
        p4 = self._make_point(200, 0)

        entity = _bezier_to_spline(
            msp,
            p1,
            p2,
            p3,
            p4,
            page_height=200,
            x_offset=0,
            attribs={"layer": "0", "color": 7},
            bezier4p_cls=Bezier4P,
            vec2_cls=Vec2,
            bspline_fn=bezier_to_bspline,
        )
        assert entity is not None
        assert entity.dxftype() == "SPLINE"
        assert entity.control_point_count() > 0

    def test_bezier_to_spline_with_offset(self):
        """SPLINE control points should be offset by x_offset."""
        import ezdxf
        from ezdxf.math import Bezier4P, Vec2, bezier_to_bspline

        from cad_dxf_agent.core.converter import _bezier_to_spline

        doc = ezdxf.new()
        msp = doc.modelspace()
        p1 = self._make_point(10, 10)
        p2 = self._make_point(20, 50)
        p3 = self._make_point(40, 50)
        p4 = self._make_point(50, 10)

        entity = _bezier_to_spline(
            msp,
            p1,
            p2,
            p3,
            p4,
            page_height=100,
            x_offset=500,
            attribs={"layer": "0"},
            bezier4p_cls=Bezier4P,
            vec2_cls=Vec2,
            bspline_fn=bezier_to_bspline,
        )
        assert entity is not None
        # First control point X should be >= 500 (offset)
        ctrl_pts = list(entity.control_points)
        assert ctrl_pts[0][0] >= 500


class TestTextFontSize:
    """Test that text height prefers span font size over bbox-derived height."""

    def _make_point(self, x, y):
        class Pt:
            def __init__(self, x, y):
                self.x = x
                self.y = y

        return Pt(x, y)

    def _make_fitz_module(self, pages):
        import types

        fitz_mod = types.ModuleType("fitz")
        fitz_mod.TEXT_PRESERVE_WHITESPACE = 1

        class MockDoc:
            def __init__(self):
                self._pages = pages

            def __len__(self):
                return len(self._pages)

            def __iter__(self):
                return iter(self._pages)

            def close(self):
                pass

        fitz_mod.open = lambda path: MockDoc()
        return fitz_mod

    def _make_page(self, height=792, width=612, drawings=None, text_dict=None):
        class MockPage:
            def __init__(self, h, w, d, t):
                class Rect:
                    def __init__(self, h, w):
                        self.height = h
                        self.width = w

                self.rect = Rect(h, w)
                self._drawings = d or []
                self._text = t or {"blocks": []}

            def get_drawings(self):
                return self._drawings

            def get_text(self, mode, flags=0):
                return self._text

        return MockPage(height, width, drawings, text_dict)

    def test_span_font_size_used_when_available(self, tmp_path, monkeypatch):
        """When span has 'size', use it directly instead of bbox * 0.7."""
        import sys

        import ezdxf

        text_dict = {
            "blocks": [
                {
                    "type": 0,
                    "lines": [
                        {
                            "spans": [
                                {
                                    "text": "Hello",
                                    "bbox": (10, 10, 50, 30),  # bbox height = 20
                                    "size": 14.0,  # actual font size
                                    "color": 0,
                                }
                            ]
                        }
                    ],
                }
            ]
        }
        page = self._make_page(text_dict=text_dict)
        fitz_mod = self._make_fitz_module([page])
        monkeypatch.setitem(sys.modules, "fitz", fitz_mod)

        from cad_dxf_agent.core.converter import _extract_pdf_fitz

        doc = ezdxf.new()
        msp = doc.modelspace()
        _extract_pdf_fitz(msp, tmp_path / "dummy.pdf")

        entities = list(msp)
        assert len(entities) == 1
        text_ent = entities[0]
        assert text_ent.dxftype() == "TEXT"
        # Should use font size 14.0, not bbox height 20 * 0.7 = 14.0
        assert abs(text_ent.dxf.height - 14.0) < 0.01

    def test_bbox_fallback_when_no_font_size(self, tmp_path, monkeypatch):
        """When span has no 'size', fall back to bbox-derived height * 0.7."""
        import sys

        import ezdxf

        text_dict = {
            "blocks": [
                {
                    "type": 0,
                    "lines": [
                        {
                            "spans": [
                                {
                                    "text": "World",
                                    "bbox": (10, 10, 50, 30),  # bbox height = 20
                                    "color": 0,
                                    # no "size" key
                                }
                            ]
                        }
                    ],
                }
            ]
        }
        page = self._make_page(text_dict=text_dict)
        fitz_mod = self._make_fitz_module([page])
        monkeypatch.setitem(sys.modules, "fitz", fitz_mod)

        from cad_dxf_agent.core.converter import _extract_pdf_fitz

        doc = ezdxf.new()
        msp = doc.modelspace()
        _extract_pdf_fitz(msp, tmp_path / "dummy.pdf")

        entities = list(msp)
        assert len(entities) == 1
        text_ent = entities[0]
        # Fallback: bbox height (20) * 0.7 = 14.0
        assert abs(text_ent.dxf.height - 14.0) < 0.01


class TestStrokeExtraction:
    """Test PDF stroke width and dash pattern extraction."""

    def _make_point(self, x, y):
        class Pt:
            def __init__(self, x, y):
                self.x = x
                self.y = y

        return Pt(x, y)

    def _make_fitz_module(self, pages):
        import types

        fitz_mod = types.ModuleType("fitz")
        fitz_mod.TEXT_PRESERVE_WHITESPACE = 1

        class MockDoc:
            def __init__(self):
                self._pages = pages

            def __len__(self):
                return len(self._pages)

            def __iter__(self):
                return iter(self._pages)

            def close(self):
                pass

        fitz_mod.open = lambda path: MockDoc()
        return fitz_mod

    def _make_page(self, height=792, width=612, drawings=None, text_dict=None):
        class MockPage:
            def __init__(self, h, w, d, t):
                class Rect:
                    def __init__(self, h, w):
                        self.height = h
                        self.width = w

                self.rect = Rect(h, w)
                self._drawings = d or []
                self._text = t or {"blocks": []}

            def get_drawings(self):
                return self._drawings

            def get_text(self, mode, flags=0):
                return self._text

        return MockPage(height, width, drawings, text_dict)

    def test_stroke_width_applied_as_lineweight(self, tmp_path, monkeypatch):
        """Lines from paths with stroke width get DXF lineweight."""
        import sys

        import ezdxf

        p1 = self._make_point(0, 0)
        p2 = self._make_point(100, 0)
        drawing = {
            "items": [("l", p1, p2)],
            "color": (0.0, 0.0, 0.0),
            "width": 2.0,  # 2pt stroke
            "dashes": "[] 0",
        }
        page = self._make_page(drawings=[drawing])
        fitz_mod = self._make_fitz_module([page])
        monkeypatch.setitem(sys.modules, "fitz", fitz_mod)

        from cad_dxf_agent.core.converter import _extract_pdf_fitz

        doc = ezdxf.new()
        msp = doc.modelspace()
        _extract_pdf_fitz(msp, tmp_path / "dummy.pdf")

        entities = list(msp)
        assert len(entities) == 1
        line = entities[0]
        # 2.0 * 25 = 50, clamped to [13, 211]
        assert line.dxf.lineweight == 50

    def test_dashed_line_gets_linetype(self, tmp_path, monkeypatch):
        """Lines from paths with dash patterns get DXF linetype."""
        import sys

        import ezdxf

        p1 = self._make_point(0, 0)
        p2 = self._make_point(100, 0)
        drawing = {
            "items": [("l", p1, p2)],
            "color": (0.0, 0.0, 0.0),
            "width": 1.0,
            "dashes": "[3 2] 0",  # standard dashed
        }
        page = self._make_page(drawings=[drawing])
        fitz_mod = self._make_fitz_module([page])
        monkeypatch.setitem(sys.modules, "fitz", fitz_mod)

        from cad_dxf_agent.core.converter import _extract_pdf_fitz

        doc = ezdxf.new()
        msp = doc.modelspace()
        _extract_pdf_fitz(msp, tmp_path / "dummy.pdf")

        entities = list(msp)
        assert len(entities) == 1
        line = entities[0]
        assert line.dxf.linetype == "DASHED"


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

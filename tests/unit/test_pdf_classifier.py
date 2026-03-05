"""Tests for the PDF per-page content classifier."""

from __future__ import annotations

from cad_dxf_agent.core.pdf_classifier import (
    PageContentType,
    _classify_page,
)


class TestClassifyPageRules:
    """Test the heuristic classification rules."""

    def test_vector_layout(self):
        result = _classify_page(
            vector_count=500, image_count=0, image_area_ratio=0.0, text_count=10,
        )
        assert result == PageContentType.VECTOR_LAYOUT

    def test_raster_scanned(self):
        result = _classify_page(vector_count=5, image_count=1, image_area_ratio=0.8, text_count=0)
        assert result == PageContentType.RASTER_SCANNED

    def test_mixed(self):
        result = _classify_page(vector_count=200, image_count=2, image_area_ratio=0.6, text_count=5)
        assert result == PageContentType.MIXED

    def test_cover_text_heavy(self):
        result = _classify_page(vector_count=10, image_count=0, image_area_ratio=0.0, text_count=30)
        assert result == PageContentType.COVER_TEXT_HEAVY

    def test_few_vectors_few_images_falls_to_cover(self):
        result = _classify_page(vector_count=5, image_count=0, image_area_ratio=0.0, text_count=2)
        assert result == PageContentType.COVER_TEXT_HEAVY

    def test_raster_with_low_area_but_no_vectors(self):
        result = _classify_page(vector_count=3, image_count=1, image_area_ratio=0.3, text_count=0)
        assert result == PageContentType.RASTER_SCANNED

    def test_many_vectors_with_small_image(self):
        """Vectors dominate despite small embedded image."""
        result = _classify_page(
            vector_count=1000, image_count=1, image_area_ratio=0.1, text_count=50,
        )
        assert result == PageContentType.VECTOR_LAYOUT


class TestClassifyPdfPages:
    """Integration test for classify_pdf_pages using mocked fitz."""

    def test_classify_with_mocked_fitz(self, tmp_path, monkeypatch):
        """Mocked multi-page PDF returns correct classifications."""
        import sys
        import types

        fitz_mod = types.ModuleType("fitz")
        fitz_mod.TEXT_PRESERVE_WHITESPACE = 1

        class MockPage:
            def __init__(self, w, h, drawings, images, text_dict):
                class Rect:
                    def __init__(self, w, h):
                        self.width = w
                        self.height = h
                self.rect = Rect(w, h)
                self._drawings = drawings
                self._images = images
                self._text = text_dict

            def get_drawings(self):
                return self._drawings

            def get_images(self):
                return self._images

            def get_text(self, mode, flags=0):
                return self._text

        # Page 1: cover (few vectors, lots of text)
        page1 = MockPage(612, 792,
            drawings=[{"items": [("l",)]}],  # 1 item
            images=[],
            text_dict={
                "blocks": [{"type": 0, "lines": [
                    {"spans": [{"text": f"word{i}"} for i in range(25)]}
                ]}],
            },
        )
        # Page 2: vector layout (many vectors, no images)
        page2 = MockPage(3024, 2160,
            drawings=[{"items": [("l",)] * 200}],
            images=[],
            text_dict={"blocks": []},
        )

        class MockDoc:
            def __init__(self):
                self._pages = [page1, page2]
            def __iter__(self):
                return iter(self._pages)
            def close(self):
                pass

        fitz_mod.open = lambda path: MockDoc()
        monkeypatch.setitem(sys.modules, "fitz", fitz_mod)

        from cad_dxf_agent.core.pdf_classifier import classify_pdf_pages

        results = classify_pdf_pages(tmp_path / "dummy.pdf")
        assert len(results) == 2
        assert results[0].content_type == PageContentType.COVER_TEXT_HEAVY
        assert results[1].content_type == PageContentType.VECTOR_LAYOUT

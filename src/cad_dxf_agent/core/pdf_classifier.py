"""Per-page PDF content classifier.

Classifies each page of a PDF by content type (vector layout, raster scan,
mixed, or cover/text-heavy) using PyMuPDF metadata.  The converter uses
these classifications to decide extraction strategy per page.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from enum import StrEnum
from pathlib import Path

logger = logging.getLogger(__name__)


class PageContentType(StrEnum):
    """Content type classification for a single PDF page."""

    VECTOR_LAYOUT = "vector_layout"
    RASTER_SCANNED = "raster_scanned"
    MIXED = "mixed"
    COVER_TEXT_HEAVY = "cover_text_heavy"


@dataclass
class PageClassification:
    """Classification result for one PDF page."""

    page_num: int
    content_type: PageContentType
    vector_count: int
    image_count: int
    image_area_ratio: float
    text_count: int


def classify_pdf_pages(source_path: Path) -> list[PageClassification]:
    """Classify each page of a PDF by content type.

    Uses PyMuPDF to count vector paths, embedded images, and text spans
    per page, then applies heuristic rules.

    Args:
        source_path: Path to the PDF file.

    Returns:
        List of PageClassification, one per page.
    """
    import fitz

    doc = fitz.open(str(source_path))
    results: list[PageClassification] = []

    for page_num, page in enumerate(doc):
        drawings = page.get_drawings()
        images = page.get_images()
        text_dict = page.get_text("dict", flags=fitz.TEXT_PRESERVE_WHITESPACE)

        vector_count = sum(len(pi.get("items", [])) for pi in drawings)
        image_count = len(images)

        text_count = sum(
            1
            for block in text_dict.get("blocks", [])
            if block.get("type") == 0
            for line in block.get("lines", [])
            for span in line.get("spans", [])
            if span.get("text", "").strip()
        )

        # Estimate image area ratio
        page_area = page.rect.width * page.rect.height
        image_area_ratio = 0.0
        if page_area > 0 and image_count > 0:
            total_img_area = 0.0
            for img in images:
                # img tuple: (xref, smask, width, height, bpc, ...)
                if len(img) >= 4:
                    total_img_area += img[2] * img[3]
            image_area_ratio = min(total_img_area / page_area, 1.0)

        content_type = _classify_page(vector_count, image_count, image_area_ratio, text_count)

        results.append(
            PageClassification(
                page_num=page_num,
                content_type=content_type,
                vector_count=vector_count,
                image_count=image_count,
                image_area_ratio=image_area_ratio,
                text_count=text_count,
            )
        )
        logger.debug(
            "Page %d: %s (vectors=%d, images=%d, img_ratio=%.2f, text=%d)",
            page_num + 1,
            content_type.value,
            vector_count,
            image_count,
            image_area_ratio,
            text_count,
        )

    doc.close()
    return results


def _classify_page(
    vector_count: int,
    image_count: int,
    image_area_ratio: float,
    text_count: int,
) -> PageContentType:
    """Apply heuristic rules to classify a page."""
    has_vectors = vector_count > 50
    has_large_images = image_area_ratio > 0.5
    is_text_heavy = text_count > 20 and vector_count < 50

    if is_text_heavy:
        return PageContentType.COVER_TEXT_HEAVY
    if has_vectors and has_large_images:
        return PageContentType.MIXED
    if has_vectors:
        return PageContentType.VECTOR_LAYOUT
    if image_count > 0 and (has_large_images or vector_count < 10):
        return PageContentType.RASTER_SCANNED
    # Fallback: few vectors, few images, little text
    return PageContentType.COVER_TEXT_HEAVY

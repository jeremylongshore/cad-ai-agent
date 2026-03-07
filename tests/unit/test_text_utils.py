"""Tests for shared text utilities (ARCH-REVIEW-CAD-01 prerequisite P1)."""

from __future__ import annotations

from cad_dxf_agent.core.text_utils import (
    describe_entity,
    entity_to_evidence,
    levenshtein_distance,
    levenshtein_similarity,
)
from cad_dxf_agent.models.cad_schema import (
    EntityRef,
    EntityType,
    Point2D,
    TextGeometry,
    TextProvenance,
)


class TestLevenshteinDistance:
    def test_identical(self):
        assert levenshtein_distance("hello", "hello") == 0

    def test_single_edit(self):
        assert levenshtein_distance("cat", "bat") == 1

    def test_empty(self):
        assert levenshtein_distance("", "abc") == 3
        assert levenshtein_distance("abc", "") == 3

    def test_both_empty(self):
        assert levenshtein_distance("", "") == 0

    def test_insertion(self):
        assert levenshtein_distance("abc", "abcd") == 1

    def test_deletion(self):
        assert levenshtein_distance("abcd", "abc") == 1


class TestLevenshteinSimilarity:
    def test_identical(self):
        assert levenshtein_similarity("hello", "hello") == 1.0

    def test_completely_different(self):
        sim = levenshtein_similarity("abc", "xyz")
        assert sim == 0.0

    def test_empty_strings(self):
        assert levenshtein_similarity("", "") == 1.0
        assert levenshtein_similarity("abc", "") == 0.0
        assert levenshtein_similarity("", "abc") == 0.0

    def test_partial_match(self):
        sim = levenshtein_similarity("hello", "hallo")
        assert 0.5 < sim < 1.0


class TestDescribeEntity:
    def test_text_entity(self):
        entity = EntityRef(
            handle="T1",
            entity_type=EntityType.TEXT,
            layer="NOTES",
            insert_point=Point2D(x=10, y=20),
            text_content="Hello World",
        )
        desc = describe_entity(entity)
        assert "TEXT" in desc
        assert "NOTES" in desc
        assert "Hello World" in desc

    def test_insert_entity(self):
        entity = EntityRef(
            handle="I1",
            entity_type=EntityType.INSERT,
            layer="SYMBOLS",
            insert_point=Point2D(x=30, y=40),
            block_name="DETAIL_A",
        )
        desc = describe_entity(entity)
        assert "INSERT" in desc
        assert "DETAIL_A" in desc

    def test_entity_with_provenance(self):
        entity = EntityRef(
            handle="T2",
            entity_type=EntityType.TEXT,
            layer="NOTES",
            insert_point=Point2D(x=0, y=0),
            text_content="OCR text",
            text_geometry=TextGeometry(
                provenance=TextProvenance.RASTER_OCR_TEXT,
                confidence_position=0.3,
                confidence_rotation=0.3,
                confidence_content=0.3,
            ),
        )
        desc = describe_entity(entity)
        assert "raster_ocr_text" in desc

    def test_long_text_truncated(self):
        entity = EntityRef(
            handle="T3",
            entity_type=EntityType.TEXT,
            layer="NOTES",
            text_content="A" * 100,
        )
        desc = describe_entity(entity)
        assert "..." in desc


class TestEntityToEvidence:
    def test_basic_conversion(self):
        entity = EntityRef(
            handle="T1",
            entity_type=EntityType.TEXT,
            layer="NOTES",
            insert_point=Point2D(x=10, y=20),
            text_content="Hello",
        )
        evidence = entity_to_evidence(entity)
        assert evidence.entity_handle == "T1"
        assert evidence.layer == "NOTES"
        assert evidence.entity_type == "TEXT"
        assert evidence.location == (10, 20)
        assert evidence.text_excerpt == "Hello"

    def test_no_position(self):
        entity = EntityRef(
            handle="T2",
            entity_type=EntityType.LINE,
            layer="WALLS",
        )
        evidence = entity_to_evidence(entity)
        assert evidence.location is None

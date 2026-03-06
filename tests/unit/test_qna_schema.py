"""Tests for Q&A domain models (qna_schema)."""

from __future__ import annotations

import pytest

from cad_dxf_agent.models.cad_schema import EntityRef, EntityType, Point2D
from cad_dxf_agent.models.qna_schema import QnaAnswer, QnaQuestionType, RegionContext
from cad_dxf_agent.models.region_schema import BoundingBox
from cad_dxf_agent.models.response_schema import EvidenceRef


class TestQnaQuestionType:
    def test_all_values(self):
        assert len(QnaQuestionType) == 8

    def test_string_values(self):
        assert QnaQuestionType.ENTITY_LIST == "entity_list"
        assert QnaQuestionType.TEXT_SEARCH == "text_search"
        assert QnaQuestionType.LAYER_QUERY == "layer_query"
        assert QnaQuestionType.REGION_SUMMARY == "region_summary"
        assert QnaQuestionType.ENTITY_COUNT == "entity_count"
        assert QnaQuestionType.DIMENSION_QUERY == "dimension_query"
        assert QnaQuestionType.BLOCK_QUERY == "block_query"
        assert QnaQuestionType.ENTITY_LOOKUP == "entity_lookup"

    def test_is_str_enum(self):
        assert isinstance(QnaQuestionType.ENTITY_LIST, str)


class TestRegionContext:
    def test_defaults(self):
        ctx = RegionContext()
        assert ctx.entities == []
        assert ctx.text_entities == []
        assert ctx.dimension_entities == []
        assert ctx.block_refs == []
        assert ctx.layers == []
        assert ctx.layer_counts == {}
        assert ctx.block_names == []
        assert ctx.entity_count == 0
        assert ctx.total_drawing_entities == 0
        assert ctx.confidence == 1.0
        assert ctx.ambiguity_flags == []
        assert ctx.is_whole_drawing is False
        assert ctx.bounds is None

    def test_with_entities(self):
        ent = EntityRef(handle="A1", entity_type=EntityType.TEXT, layer="NOTES",
                        insert_point=Point2D(x=10, y=20), text_content="Hello")
        ctx = RegionContext(
            entities=[ent],
            text_entities=[ent],
            layers=["NOTES"],
            layer_counts={"NOTES": 1},
            entity_count=1,
            total_drawing_entities=50,
        )
        assert ctx.entity_count == 1
        assert ctx.text_entities[0].text_content == "Hello"

    def test_with_bounds(self):
        ctx = RegionContext(bounds=BoundingBox(min_x=0, min_y=0, max_x=100, max_y=100))
        assert ctx.bounds is not None
        assert ctx.bounds.width == 100

    def test_serialization_roundtrip(self):
        ctx = RegionContext(
            layers=["A", "B"],
            layer_counts={"A": 3, "B": 5},
            entity_count=8,
            is_whole_drawing=True,
            confidence=0.85,
        )
        data = ctx.model_dump()
        restored = RegionContext.model_validate(data)
        assert restored.layers == ["A", "B"]
        assert restored.layer_counts == {"A": 3, "B": 5}


class TestQnaAnswer:
    def test_defaults(self):
        ans = QnaAnswer(
            question_type=QnaQuestionType.ENTITY_COUNT,
            answer_text="There are 10 entities.",
        )
        assert ans.evidence == []
        assert ans.confidence == 1.0
        assert ans.ambiguity_flags == []
        assert ans.entity_count == 0

    def test_with_evidence(self):
        ev = EvidenceRef(entity_handle="A1", layer="NOTES", description="Text entity")
        ans = QnaAnswer(
            question_type=QnaQuestionType.TEXT_SEARCH,
            answer_text="Found 'FOOTING' on layer NOTES.",
            evidence=[ev],
            confidence=0.9,
            entity_count=1,
        )
        assert len(ans.evidence) == 1
        assert ans.evidence[0].entity_handle == "A1"

    def test_with_ambiguity_flags(self):
        ans = QnaAnswer(
            question_type=QnaQuestionType.REGION_SUMMARY,
            answer_text="Summary of region",
            ambiguity_flags=["context_truncated", "no_entities_inside_region"],
        )
        assert "context_truncated" in ans.ambiguity_flags

    def test_with_region_context_summary(self):
        ans = QnaAnswer(
            question_type=QnaQuestionType.LAYER_QUERY,
            answer_text="Layer NOTES has 5 entities.",
            region_context_summary={"layer": "NOTES", "count": 5},
        )
        assert ans.region_context_summary["layer"] == "NOTES"

    def test_serialization_roundtrip(self):
        ans = QnaAnswer(
            question_type=QnaQuestionType.BLOCK_QUERY,
            answer_text="Found 3 blocks.",
            entity_count=3,
            confidence=0.95,
        )
        data = ans.model_dump()
        restored = QnaAnswer.model_validate(data)
        assert restored.question_type == QnaQuestionType.BLOCK_QUERY
        assert restored.entity_count == 3

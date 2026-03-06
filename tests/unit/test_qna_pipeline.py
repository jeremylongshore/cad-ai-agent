"""Tests for QnaPipeline, QuestionClassifier, and AnswerGenerator."""

from __future__ import annotations

import pytest

from cad_dxf_agent.core.qna_pipeline import (
    AnswerGenerator,
    QnaPipeline,
    QuestionClassifier,
    _extract_layer_name,
    _extract_search_term,
)
from cad_dxf_agent.models.cad_schema import (
    DrawingContext,
    EntityRef,
    EntityType,
    Point2D,
)
from cad_dxf_agent.models.qna_schema import QnaQuestionType, RegionContext
from cad_dxf_agent.models.region_schema import (
    BoundingBox,
    NormalizedRegion,
    RegionType,
)


def _entity(handle, etype, layer, x=0.0, y=0.0, text=None, block=None):
    return EntityRef(
        handle=handle,
        entity_type=etype,
        layer=layer,
        insert_point=Point2D(x=x, y=y),
        text_content=text,
        block_name=block,
    )


def _context(entities):
    return DrawingContext(file_path="test.dxf", entities=entities)


def _region(min_x, min_y, max_x, max_y):
    cx = (min_x + max_x) / 2
    cy = (min_y + max_y) / 2
    return NormalizedRegion(
        source_type=RegionType.BOX_SELECT,
        bounds=BoundingBox(min_x=min_x, min_y=min_y, max_x=max_x, max_y=max_y),
        center=Point2D(x=cx, y=cy),
    )


@pytest.fixture
def sample_entities():
    return [
        _entity("T1", EntityType.TEXT, "NOTES", 10, 10, text="FOOTING F1"),
        _entity("T2", EntityType.MTEXT, "NOTES", 20, 20, text="ALL DIMENSIONS IN FEET"),
        _entity("T3", EntityType.TEXT, "STRUCTURAL", 30, 30, text="COLUMN A-1"),
        _entity("L1", EntityType.LINE, "STRUCTURAL", 10, 10),
        _entity("L2", EntityType.LINE, "STRUCTURAL", 50, 50),
        _entity("L3", EntityType.LWPOLYLINE, "STRUCTURAL", 40, 40),
        _entity("B1", EntityType.INSERT, "STRUCTURAL", 30, 30, block="COLUMN_MARK"),
        _entity("B2", EntityType.INSERT, "STRUCTURAL", 60, 60, block="DOOR"),
        _entity("D1", EntityType.DIMENSION, "NOTES", 15, 15, text="30'-0\""),
        _entity("LD1", EntityType.LEADER, "NOTES", 25, 25, text="SEE DETAIL"),
    ]


@pytest.fixture
def sample_context(sample_entities):
    return _context(sample_entities)


# ==========================================================================
# QuestionClassifier
# ==========================================================================


class TestQuestionClassifier:
    @pytest.fixture
    def classifier(self):
        return QuestionClassifier()

    def test_layer_query_what_on_layer(self, classifier):
        assert classifier.classify("What is on layer NOTES?") == QnaQuestionType.LAYER_QUERY

    def test_layer_query_which_layer(self, classifier):
        assert classifier.classify("Which layer has column marks?") == QnaQuestionType.LAYER_QUERY

    def test_entity_count_how_many(self, classifier):
        assert classifier.classify("How many entities are there?") == QnaQuestionType.ENTITY_COUNT

    def test_entity_count_number_of(self, classifier):
        assert classifier.classify("What is the number of lines?") == QnaQuestionType.ENTITY_COUNT

    def test_text_search_find_text(self, classifier):
        assert classifier.classify("Find text containing FOOTING") == QnaQuestionType.TEXT_SEARCH

    def test_text_search_quoted(self, classifier):
        assert classifier.classify('Find "COLUMN A"') == QnaQuestionType.TEXT_SEARCH

    def test_dimension_query(self, classifier):
        assert classifier.classify("What dimensions are here?") == QnaQuestionType.DIMENSION_QUERY

    def test_block_query(self, classifier):
        assert classifier.classify("What blocks are in this area?") == QnaQuestionType.BLOCK_QUERY

    def test_entity_lookup_where_is(self, classifier):
        assert classifier.classify("Where is entity A1?") == QnaQuestionType.ENTITY_LOOKUP

    def test_entity_lookup_locate(self, classifier):
        assert classifier.classify("Locate column A1") == QnaQuestionType.ENTITY_LOOKUP

    def test_entity_list_list_all(self, classifier):
        assert classifier.classify("List all entities") == QnaQuestionType.ENTITY_LIST

    def test_entity_list_what_is(self, classifier):
        # "What is here?" matches entity_list ("what is") before region_summary
        assert classifier.classify("What is here?") == QnaQuestionType.ENTITY_LIST

    def test_region_summary_tell_me(self, classifier):
        assert classifier.classify("Tell me about this area") == QnaQuestionType.REGION_SUMMARY

    def test_empty_prompt(self, classifier):
        assert classifier.classify("") == QnaQuestionType.REGION_SUMMARY

    def test_ambiguous_defaults_to_summary(self, classifier):
        # Something that doesn't match any pattern
        assert classifier.classify("interesting drawing") == QnaQuestionType.REGION_SUMMARY


# ==========================================================================
# AnswerGenerator
# ==========================================================================


class TestAnswerGenerator:
    @pytest.fixture
    def generator(self):
        return AnswerGenerator()

    @pytest.fixture
    def region_ctx(self, sample_entities):
        texts = [e for e in sample_entities if e.entity_type in (EntityType.TEXT, EntityType.MTEXT)]
        dims = [e for e in sample_entities if e.entity_type in (EntityType.DIMENSION, EntityType.LEADER)]
        blocks = [e for e in sample_entities if e.entity_type == EntityType.INSERT]
        return RegionContext(
            entities=sample_entities,
            text_entities=texts,
            dimension_entities=dims,
            block_refs=blocks,
            layers=["NOTES", "STRUCTURAL"],
            layer_counts={"NOTES": 5, "STRUCTURAL": 5},
            block_names=["COLUMN_MARK", "DOOR"],
            entity_count=10,
            total_drawing_entities=10,
            confidence=0.9,
            is_whole_drawing=True,
        )

    def test_entity_list_answer(self, generator, region_ctx):
        ans = generator.generate(QnaQuestionType.ENTITY_LIST, region_ctx, "List entities")
        assert "10 entity(ies)" in ans.answer_text
        assert ans.question_type == QnaQuestionType.ENTITY_LIST
        assert len(ans.evidence) > 0

    def test_text_search_found(self, generator, region_ctx):
        ans = generator.generate(QnaQuestionType.TEXT_SEARCH, region_ctx, 'Find text "FOOTING"')
        assert "FOOTING" in ans.answer_text
        assert ans.entity_count >= 1

    def test_text_search_not_found(self, generator, region_ctx):
        ans = generator.generate(QnaQuestionType.TEXT_SEARCH, region_ctx, 'Find text "ZZZZZ"')
        assert "No text containing" in ans.answer_text
        assert ans.entity_count == 0

    def test_layer_query_specific_layer(self, generator, region_ctx):
        ans = generator.generate(QnaQuestionType.LAYER_QUERY, region_ctx, "What is on layer NOTES?")
        assert "NOTES" in ans.answer_text
        assert "5 entity(ies)" in ans.answer_text

    def test_layer_query_all_layers(self, generator, region_ctx):
        ans = generator.generate(QnaQuestionType.LAYER_QUERY, region_ctx, "Show layers")
        assert "layer(s)" in ans.answer_text

    def test_region_summary(self, generator, region_ctx):
        ans = generator.generate(QnaQuestionType.REGION_SUMMARY, region_ctx, "What's here?")
        assert "10 entity(ies)" in ans.answer_text
        assert "2 layer(s)" in ans.answer_text

    def test_entity_count_total(self, generator, region_ctx):
        ans = generator.generate(QnaQuestionType.ENTITY_COUNT, region_ctx, "How many entities?")
        assert "10 entity(ies)" in ans.answer_text

    def test_entity_count_by_type(self, generator, region_ctx):
        ans = generator.generate(QnaQuestionType.ENTITY_COUNT, region_ctx, "How many LINE entities?")
        assert "LINE" in ans.answer_text

    def test_dimension_query_with_dims(self, generator, region_ctx):
        ans = generator.generate(QnaQuestionType.DIMENSION_QUERY, region_ctx, "What dimensions?")
        assert "2 dimension(s)" in ans.answer_text

    def test_dimension_query_no_dims(self, generator):
        ctx = RegionContext(entities=[_entity("L1", EntityType.LINE, "L", 0, 0)],
                           entity_count=1, is_whole_drawing=True)
        ans = generator.generate(QnaQuestionType.DIMENSION_QUERY, ctx, "Dimensions?")
        assert "No dimensions" in ans.answer_text

    def test_block_query_with_blocks(self, generator, region_ctx):
        ans = generator.generate(QnaQuestionType.BLOCK_QUERY, region_ctx, "What blocks?")
        assert "2 block reference(s)" in ans.answer_text
        assert "COLUMN_MARK" in ans.answer_text

    def test_block_query_no_blocks(self, generator):
        ctx = RegionContext(entities=[_entity("L1", EntityType.LINE, "L", 0, 0)],
                           entity_count=1, is_whole_drawing=True)
        ans = generator.generate(QnaQuestionType.BLOCK_QUERY, ctx, "Blocks?")
        assert "No block references" in ans.answer_text

    def test_entity_lookup_found(self, generator, region_ctx):
        ans = generator.generate(QnaQuestionType.ENTITY_LOOKUP, region_ctx, "Where is FOOTING F1?")
        assert "FOOTING" in ans.answer_text
        assert ans.entity_count >= 1

    def test_entity_lookup_not_found(self, generator, region_ctx):
        ans = generator.generate(QnaQuestionType.ENTITY_LOOKUP, region_ctx, "Where is ZZZZ?")
        assert "Could not locate" in ans.answer_text

    def test_empty_context(self, generator):
        ctx = RegionContext(entity_count=0, is_whole_drawing=True)
        ans = generator.generate(QnaQuestionType.ENTITY_LIST, ctx, "List entities")
        assert "No entities" in ans.answer_text
        assert ans.confidence == 0.0

    def test_answer_has_region_context_summary(self, generator, region_ctx):
        ans = generator.generate(QnaQuestionType.REGION_SUMMARY, region_ctx, "Summary")
        assert "entity_count" in ans.region_context_summary
        assert ans.region_context_summary["entity_count"] == 10


# ==========================================================================
# QnaPipeline (integration-level)
# ==========================================================================


class TestQnaPipeline:
    @pytest.fixture
    def pipeline(self):
        return QnaPipeline()

    def test_whole_drawing_answer(self, pipeline, sample_context):
        resp = pipeline.answer("How many entities are there?", sample_context)
        assert resp.task_family == "qna"
        assert resp.response_type == "answer_only"
        assert resp.confidence > 0
        assert resp.data["question_type"] == "entity_count"

    def test_region_answer(self, pipeline, sample_context):
        region = _region(0, 0, 50, 50)
        resp = pipeline.answer("What is here?", sample_context, region=region)
        assert resp.task_family == "qna"
        assert resp.response_type == "answer_only"

    def test_empty_region_needs_clarification(self, pipeline):
        ctx = _context([_entity("E1", EntityType.LINE, "L", 100, 100)])
        region = _region(0, 0, 1, 1)
        resp = pipeline.answer("What's here?", ctx, region=region)
        assert resp.response_type == "needs_clarification"

    def test_layer_query_via_pipeline(self, pipeline, sample_context):
        resp = pipeline.answer("What is on layer NOTES?", sample_context)
        assert resp.response_type == "answer_only"
        assert "NOTES" in resp.message

    def test_text_search_via_pipeline(self, pipeline, sample_context):
        resp = pipeline.answer('Find text "FOOTING"', sample_context)
        assert resp.response_type == "answer_only"
        assert "FOOTING" in resp.message

    def test_block_query_via_pipeline(self, pipeline, sample_context):
        resp = pipeline.answer("What blocks are in the drawing?", sample_context)
        assert resp.response_type == "answer_only"
        assert "block" in resp.message.lower()

    def test_evidence_populated(self, pipeline, sample_context):
        resp = pipeline.answer("List entities", sample_context)
        assert len(resp.evidence) > 0

    def test_operations_always_empty(self, pipeline, sample_context):
        resp = pipeline.answer("How many entities?", sample_context)
        assert resp.operations == []

    def test_data_contains_question_type(self, pipeline, sample_context):
        resp = pipeline.answer("How many entities?", sample_context)
        assert "question_type" in resp.data

    def test_data_contains_entity_count(self, pipeline, sample_context):
        resp = pipeline.answer("How many entities?", sample_context)
        assert "entity_count" in resp.data


# ==========================================================================
# Helper extraction functions
# ==========================================================================


class TestExtractSearchTerm:
    def test_double_quoted(self):
        assert _extract_search_term('Find "FOOTING F1"') == "FOOTING F1"

    def test_single_quoted(self):
        assert _extract_search_term("Find 'COLUMN'") == "COLUMN"

    def test_after_find(self):
        assert _extract_search_term("Find FOOTING F1") == "FOOTING F1"

    def test_after_locate(self):
        assert _extract_search_term("Locate COLUMN A1") == "COLUMN A1"

    def test_after_where_is(self):
        result = _extract_search_term("Where is COLUMN A1?")
        assert result is not None
        assert "COLUMN" in result

    def test_no_term(self):
        assert _extract_search_term("Hello world") is None


class TestExtractLayerName:
    def test_explicit_layer(self):
        assert _extract_layer_name("What is on layer NOTES?", ["NOTES", "STRUCTURAL"]) == "NOTES"

    def test_case_insensitive(self):
        assert _extract_layer_name("layer notes", ["NOTES"]) == "NOTES"

    def test_layer_not_in_list(self):
        result = _extract_layer_name("What is on layer UNKNOWN?", ["NOTES"])
        assert result == "UNKNOWN"

    def test_implicit_layer_in_prompt(self):
        assert _extract_layer_name("Show STRUCTURAL entities", ["NOTES", "STRUCTURAL"]) == "STRUCTURAL"

    def test_no_layer(self):
        assert _extract_layer_name("Hello world", ["NOTES"]) is None

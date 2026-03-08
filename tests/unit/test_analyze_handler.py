"""Tests for the analyze stage handler."""

from __future__ import annotations

import pytest

from cad_dxf_agent.llm.stage_executor import StagePipelineExecutor
from cad_dxf_agent.llm.stage_handlers.analyze_handler import AnalyzeHandler
from cad_dxf_agent.models.objective_schema import (
    ObjectiveClassification,
    RequestClass,
    StagePipelineDefinition,
)


@pytest.fixture
def classification():
    return ObjectiveClassification(
        request_class=RequestClass.UNDERSTAND,
        confidence=0.9,
    )


class TestAnalyzeHandler:
    """Tests for AnalyzeHandler.execute()."""

    def test_returns_enriched_context(self, classification, sample_context):
        handler = AnalyzeHandler()
        result = handler.execute(
            classification=classification,
            context={"drawing_context": sample_context},
            prompt="What is this drawing?",
        )
        assert "enriched_context" in result
        assert "document_family" in result
        assert "primitives" in result
        assert "summary" in result

    def test_summary_contains_entity_count(self, classification, sample_context):
        handler = AnalyzeHandler()
        result = handler.execute(
            classification=classification,
            context={"drawing_context": sample_context},
            prompt="Describe this drawing",
        )
        assert "entities" in result["summary"]
        assert "layers" in result["summary"]

    def test_no_drawing_context(self, classification):
        handler = AnalyzeHandler()
        result = handler.execute(
            classification=classification,
            context={},
            prompt="What is this?",
        )
        assert "No drawing context" in result["summary"]

    def test_enriched_context_has_family(self, classification, sample_context):
        handler = AnalyzeHandler()
        result = handler.execute(
            classification=classification,
            context={"drawing_context": sample_context},
            prompt="Analyze",
        )
        family = result["document_family"]
        assert family is not None
        assert "family" in family
        assert "confidence" in family

    def test_enriched_context_has_primitives(self, classification, sample_context):
        handler = AnalyzeHandler()
        result = handler.execute(
            classification=classification,
            context={"drawing_context": sample_context},
            prompt="Analyze",
        )
        primitives = result["primitives"]
        assert primitives is not None
        assert "symbols" in primitives
        assert "labels" in primitives
        assert "layer_classification" in primitives

    def test_integrates_with_pipeline_executor(self, classification, sample_context):
        """Handler works through the StagePipelineExecutor."""
        executor = StagePipelineExecutor()
        executor.register("analyze", AnalyzeHandler())

        pipeline = StagePipelineDefinition(
            stages=["analyze"],
            output_mode="direct",
        )
        result = executor.execute(
            pipeline=pipeline,
            classification=classification,
            initial_context={"drawing_context": sample_context},
            prompt="What is this drawing?",
        )
        assert result.all_completed
        assert "enriched_context" in result.output
        assert "analyze" in result.completed_stages

    def test_chained_with_detect_zones(self, classification, sample_context):
        """Analyze → detect_zones pipeline runs end-to-end."""
        from cad_dxf_agent.llm.stage_handlers.detect_zones_handler import DetectZonesHandler

        executor = StagePipelineExecutor()
        executor.register("analyze", AnalyzeHandler())
        executor.register("detect_zones", DetectZonesHandler())

        pipeline = StagePipelineDefinition(
            stages=["analyze", "detect_zones"],
            output_mode="direct",
        )
        result = executor.execute(
            pipeline=pipeline,
            classification=classification,
            initial_context={"drawing_context": sample_context},
            prompt="How many rooms are there?",
        )
        assert result.all_completed
        assert "analyze" in result.completed_stages
        assert "detect_zones" in result.completed_stages
        # Zone detection should have run (may find 0 or more zones)
        assert "zone_count" in result.output

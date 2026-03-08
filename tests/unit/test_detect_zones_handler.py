"""Tests for the detect_zones stage handler."""

from __future__ import annotations

from pathlib import Path

import ezdxf
import pytest

from cad_dxf_agent.core.dxf_reader import load_dxf
from cad_dxf_agent.llm.stage_executor import StagePipelineExecutor
from cad_dxf_agent.llm.stage_handlers.detect_zones_handler import DetectZonesHandler
from cad_dxf_agent.models.objective_schema import (
    ObjectiveClassification,
    ObjectiveTag,
    RequestClass,
    StagePipelineDefinition,
)


@pytest.fixture
def classification():
    return ObjectiveClassification(
        request_class=RequestClass.ESTIMATE,
        objective_tag=ObjectiveTag.SPACE_COUNT,
        confidence=0.9,
    )


@pytest.fixture
def drawing_with_rooms(tmp_path: Path):
    """Create a drawing with two closed polyline rooms."""
    doc = ezdxf.new(dxfversion="R2018")
    msp = doc.modelspace()
    doc.layers.add("WALL", color=1)
    # Room 1: 10x10
    msp.add_lwpolyline(
        [(0, 0), (10, 0), (10, 10), (0, 10)],
        close=True,
        dxfattribs={"layer": "WALL"},
    )
    # Room 2: 15x15
    msp.add_lwpolyline(
        [(20, 0), (35, 0), (35, 15), (20, 15)],
        close=True,
        dxfattribs={"layer": "WALL"},
    )
    path = tmp_path / "rooms.dxf"
    doc.saveas(str(path))
    return load_dxf(path)


class TestDetectZonesHandler:
    """Tests for DetectZonesHandler.execute()."""

    def test_returns_zone_data(self, classification, drawing_with_rooms):
        handler = DetectZonesHandler()
        result = handler.execute(
            classification=classification,
            context={"drawing_context": drawing_with_rooms},
            prompt="How many rooms?",
        )
        assert result["zone_count"] == 2
        assert len(result["zones"]) == 2
        assert result["total_area"] > 0
        assert "summary" in result

    def test_no_drawing_context(self, classification):
        handler = DetectZonesHandler()
        result = handler.execute(
            classification=classification,
            context={},
            prompt="How many rooms?",
        )
        assert result["zone_count"] == 0
        assert result["zones"] == []
        assert "No drawing context" in result["summary"]

    def test_summary_single_zone(self, classification, tmp_path):
        doc = ezdxf.new(dxfversion="R2018")
        msp = doc.modelspace()
        doc.layers.add("WALL", color=1)
        msp.add_lwpolyline(
            [(0, 0), (10, 0), (10, 10), (0, 10)],
            close=True,
            dxfattribs={"layer": "WALL"},
        )
        path = tmp_path / "single.dxf"
        doc.saveas(str(path))
        ctx = load_dxf(path)

        handler = DetectZonesHandler()
        result = handler.execute(
            classification=classification,
            context={"drawing_context": ctx},
            prompt="How many rooms?",
        )
        assert result["zone_count"] == 1
        assert "1 zone detected" in result["summary"]

    def test_summary_multiple_zones(self, classification, drawing_with_rooms):
        handler = DetectZonesHandler()
        result = handler.execute(
            classification=classification,
            context={"drawing_context": drawing_with_rooms},
            prompt="How many rooms?",
        )
        assert "2 zones detected" in result["summary"]
        assert "total area" in result["summary"]

    def test_handler_output_keys(self, classification, drawing_with_rooms):
        handler = DetectZonesHandler()
        result = handler.execute(
            classification=classification,
            context={"drawing_context": drawing_with_rooms},
            prompt="Count rooms",
        )
        expected_keys = {
            "zones",
            "zone_count",
            "total_area",
            "zone_confidence",
            "zone_method",
            "zone_warnings",
            "summary",
        }
        assert expected_keys <= set(result.keys())

    def test_integrates_with_pipeline_executor(self, classification, drawing_with_rooms):
        """Handler works end-to-end through the StagePipelineExecutor."""
        executor = StagePipelineExecutor()
        executor.register("detect_zones", DetectZonesHandler())

        pipeline = StagePipelineDefinition(
            stages=["detect_zones"],
            output_mode="direct",
        )
        result = executor.execute(
            pipeline=pipeline,
            classification=classification,
            initial_context={"drawing_context": drawing_with_rooms},
            prompt="How many rooms?",
        )
        assert result.all_completed
        assert result.output["zone_count"] == 2
        assert "detect_zones" in result.completed_stages

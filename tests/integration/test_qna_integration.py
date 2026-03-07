"""Integration tests for the Q&A pipeline — golden fixtures + structural drawing."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from cad_dxf_agent.core.dxf_reader import load_dxf
from cad_dxf_agent.core.qna_pipeline import QnaPipeline
from cad_dxf_agent.models.cad_schema import Point2D
from cad_dxf_agent.models.region_schema import BoundingBox, NormalizedRegion, RegionType
from tests.helpers.dxf_factory import create_structural_drawing

FIXTURES_DIR = Path(__file__).parent.parent / "fixtures" / "trajectories"


@pytest.fixture
def structural_dxf(tmp_path):
    return create_structural_drawing(tmp_path)


@pytest.fixture
def structural_context(structural_dxf):
    return load_dxf(str(structural_dxf))


@pytest.fixture
def pipeline():
    return QnaPipeline()


def _load_qna_fixtures():
    """Load all qna_*.json golden fixtures."""
    fixtures = []
    for f in sorted(FIXTURES_DIR.glob("qna_*.json")):
        data = json.loads(f.read_text())
        fixtures.append(pytest.param(data, id=data["name"]))
    return fixtures


class TestQnaGoldenFixtures:
    @pytest.mark.parametrize("fixture", _load_qna_fixtures())
    def test_golden_fixture(self, pipeline, structural_context, fixture):
        region = None
        if fixture.get("region"):
            r = fixture["region"]
            bounds = r["bounds"]
            region = NormalizedRegion(
                source_type=RegionType(r.get("source_type", "box_select")),
                bounds=BoundingBox(**bounds),
                center=Point2D(
                    x=(bounds["min_x"] + bounds["max_x"]) / 2,
                    y=(bounds["min_y"] + bounds["max_y"]) / 2,
                ),
            )

        resp = pipeline.answer(
            prompt=fixture["prompt"],
            context=structural_context,
            region=region,
        )

        assert resp.response_type == fixture["expected_response_type"]
        assert resp.task_family == fixture["task_family"]

        if fixture.get("expected_confidence_min") is not None:
            assert resp.confidence >= fixture["expected_confidence_min"], (
                f"confidence {resp.confidence} < {fixture['expected_confidence_min']}"
            )

        if fixture.get("expected_evidence_min") is not None:
            assert len(resp.evidence) >= fixture["expected_evidence_min"], (
                f"evidence count {len(resp.evidence)} < {fixture['expected_evidence_min']}"
            )

        for keyword in fixture.get("answer_must_contain", []):
            assert keyword.lower() in resp.message.lower(), (
                f"'{keyword}' not found in answer: {resp.message[:200]}"
            )


class TestQnaWholeDrawing:
    def test_entity_count_structural(self, pipeline, structural_context):
        resp = pipeline.answer("How many entities are there?", structural_context)
        assert resp.response_type == "answer_only"
        assert resp.data["entity_count"] > 0

    def test_layer_query_notes(self, pipeline, structural_context):
        resp = pipeline.answer("What is on layer NOTES?", structural_context)
        assert resp.response_type == "answer_only"
        assert "NOTES" in resp.message

    def test_text_search_footing(self, pipeline, structural_context):
        resp = pipeline.answer('Find text containing "FOOTING"', structural_context)
        assert resp.response_type == "answer_only"
        assert "FOOTING" in resp.message

    def test_block_query_column_mark(self, pipeline, structural_context):
        resp = pipeline.answer("What blocks are in the drawing?", structural_context)
        assert resp.response_type == "answer_only"
        assert "COLUMN_MARK" in resp.message


class TestQnaWithRegion:
    def test_region_scoped_query(self, pipeline, structural_context):
        # Region around first grid intersection (0,0)
        region = NormalizedRegion(
            source_type=RegionType.BOX_SELECT,
            bounds=BoundingBox(min_x=-5, min_y=-5, max_x=35, max_y=35),
            center=Point2D(x=15, y=15),
        )
        resp = pipeline.answer("What is here?", structural_context, region=region)
        assert resp.response_type == "answer_only"
        assert resp.data["entity_count"] > 0

    def test_empty_region(self, pipeline, structural_context):
        # Region far from any entities
        region = NormalizedRegion(
            source_type=RegionType.BOX_SELECT,
            bounds=BoundingBox(min_x=9999, min_y=9999, max_x=9999.1, max_y=9999.1),
            center=Point2D(x=9999.05, y=9999.05),
        )
        resp = pipeline.answer("What is here?", structural_context, region=region)
        assert resp.response_type == "needs_clarification"

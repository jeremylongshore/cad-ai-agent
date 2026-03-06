"""Anti-regression tests: Q&A MUST NOT enter edit planning.

These tests prove that:
1. QNA responses never produce operations
2. QnaPipeline does not import the planner
3. QNA response type is ANSWER_ONLY, not PLAN_ONLY
4. V2 endpoint QNA handler dispatches to QnaPipeline, not run_planner
"""

from __future__ import annotations

import importlib
import sys

import pytest

from cad_dxf_agent.core.qna_pipeline import QnaPipeline
from cad_dxf_agent.models.cad_schema import (
    DrawingContext,
    EntityRef,
    EntityType,
    Point2D,
)


def _sample_context():
    return DrawingContext(
        file_path="test.dxf",
        entities=[
            EntityRef(
                handle="T1", entity_type=EntityType.TEXT, layer="NOTES",
                insert_point=Point2D(x=10, y=10), text_content="FOOTING F1",
            ),
            EntityRef(
                handle="L1", entity_type=EntityType.LINE, layer="STRUCTURAL",
                insert_point=Point2D(x=20, y=20),
            ),
            EntityRef(
                handle="B1", entity_type=EntityType.INSERT, layer="STRUCTURAL",
                insert_point=Point2D(x=30, y=30), block_name="COLUMN_MARK",
            ),
        ],
    )


class TestQnaDoesNotProduceOperations:
    """QNA responses MUST have operations=[]."""

    @pytest.fixture
    def pipeline(self):
        return QnaPipeline()

    @pytest.fixture
    def context(self):
        return _sample_context()

    @pytest.mark.parametrize("prompt", [
        "What is on layer NOTES?",
        "How many entities are there?",
        'Find text containing "FOOTING"',
        "What dimensions are here?",
        "What blocks are in the drawing?",
        "Where is entity T1?",
        "Tell me about this area",
        "List all entities",
    ])
    def test_qna_prompt_does_not_produce_operations(self, pipeline, context, prompt):
        resp = pipeline.answer(prompt, context)
        assert resp.operations == [], (
            f"QNA response for '{prompt}' should have no operations, "
            f"got {len(resp.operations)}"
        )


class TestQnaDoesNotImportPlanner:
    """QnaPipeline module MUST NOT import the planner."""

    def test_qna_does_not_import_planner(self):
        mod = importlib.import_module("cad_dxf_agent.core.qna_pipeline")
        source = importlib.util.find_spec(mod.__name__).origin
        with open(source) as f:
            content = f.read()

        # Must not contain planner imports
        assert "from cad_dxf_agent.llm.planner" not in content
        assert "from cad_dxf_agent.llm import planner" not in content
        assert "import planner" not in content.replace("import importlib", "")


class TestQnaResponseType:
    """QNA responses MUST use ANSWER_ONLY, never PLAN_ONLY."""

    @pytest.fixture
    def pipeline(self):
        return QnaPipeline()

    @pytest.fixture
    def context(self):
        return _sample_context()

    @pytest.mark.parametrize("prompt", [
        "What is on layer NOTES?",
        "How many entities?",
        "List entities",
        "Tell me about this area",
    ])
    def test_qna_response_type_is_answer_only(self, pipeline, context, prompt):
        resp = pipeline.answer(prompt, context)
        assert resp.response_type in ("answer_only", "needs_clarification"), (
            f"QNA response for '{prompt}' has type '{resp.response_type}', "
            "expected 'answer_only' or 'needs_clarification'"
        )
        assert resp.response_type != "plan_only"
        assert resp.task_family == "qna"


class TestQnaV2EndpointDoesNotCallPlanner:
    """V2 endpoint QNA handler must dispatch to QnaPipeline, not run_planner."""

    def test_qna_v2_endpoint_does_not_call_run_planner(self):
        starlette = pytest.importorskip("starlette")
        import importlib
        mod = importlib.import_module("web.backend.main")
        source = importlib.util.find_spec(mod.__name__).origin
        with open(source) as f:
            content = f.read()

        # The QNA handler block should use QnaPipeline, not run_planner
        # Find the QNA handler section
        qna_start = content.find("intent.family == TaskFamily.QNA")
        assert qna_start != -1, "QNA handler not found in v2_prompt"

        # Find the next handler (compare or edit_plan)
        next_handler = content.find("intent.family == TaskFamily.COMPARE", qna_start)
        if next_handler == -1:
            next_handler = content.find("intent.family == TaskFamily.EDIT_PLAN", qna_start)

        qna_section = content[qna_start:next_handler] if next_handler != -1 else content[qna_start:]

        assert "QnaPipeline" in qna_section, "QNA handler should use QnaPipeline"
        assert "run_planner" not in qna_section, "QNA handler must not call run_planner"

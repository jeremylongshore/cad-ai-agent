"""Tests for StagePipelineExecutor — runs stage pipelines with gate checkpoints."""

import pytest

from cad_dxf_agent.llm.stage_executor import (
    StagePipelineExecutor,
    StageExecutionResult,
)
from cad_dxf_agent.models.objective_schema import (
    ObjectiveClassification,
    RequestClass,
    StagePipelineDefinition,
)


class _EchoHandler:
    """Test handler that echoes its stage name into context."""

    def __init__(self, name: str, extra: dict | None = None):
        self._name = name
        self._extra = extra or {}

    def execute(self, classification, context, prompt):
        return {"summary": f"{self._name} done", self._name: True, **self._extra}


class _FailHandler:
    """Test handler that always raises."""

    def execute(self, classification, context, prompt):
        raise RuntimeError("Stage failed!")


class _ContextReader:
    """Handler that reads a value from context (proving accumulation works)."""

    def execute(self, classification, context, prompt):
        upstream = context.get("analyze", False)
        return {"summary": "read context", "saw_analyze": upstream}


@pytest.fixture
def classification():
    return ObjectiveClassification(
        request_class=RequestClass.UNDERSTAND,
        confidence=0.9,
    )


@pytest.fixture
def executor():
    ex = StagePipelineExecutor()
    ex.register("analyze", _EchoHandler("analyze"))
    ex.register("quantify", _EchoHandler("quantify", {"count": 42}))
    ex.register("recommend", _EchoHandler("recommend"))
    ex.register("reader", _ContextReader())
    ex.register("fail", _FailHandler())
    return ex


class TestBasicExecution:
    """Happy-path stage execution."""

    def test_single_stage(self, executor, classification):
        pipeline = StagePipelineDefinition(stages=["analyze"], output_mode="direct")
        result = executor.execute(
            pipeline=pipeline,
            classification=classification,
            initial_context={"drawing": "test"},
            prompt="what is this",
        )
        assert result.all_completed
        assert result.completed_stages == ["analyze"]
        assert result.output["analyze"] is True

    def test_multi_stage(self, executor, classification):
        pipeline = StagePipelineDefinition(
            stages=["analyze", "quantify", "recommend"],
            output_mode="staged",
        )
        result = executor.execute(
            pipeline=pipeline,
            classification=classification,
            initial_context={},
            prompt="test",
        )
        assert result.completed_stages == ["analyze", "quantify", "recommend"]
        assert result.output["count"] == 42  # from quantify handler

    def test_context_accumulation(self, executor, classification):
        pipeline = StagePipelineDefinition(
            stages=["analyze", "reader"],
            output_mode="direct",
        )
        result = executor.execute(
            pipeline=pipeline,
            classification=classification,
            initial_context={},
            prompt="test",
        )
        assert result.output["saw_analyze"] is True  # reader saw analyze's output

    def test_initial_context_preserved(self, executor, classification):
        pipeline = StagePipelineDefinition(stages=["analyze"], output_mode="direct")
        result = executor.execute(
            pipeline=pipeline,
            classification=classification,
            initial_context={"foo": "bar"},
            prompt="test",
        )
        assert result.output["foo"] == "bar"


class TestSkippedStages:
    """Unregistered stages are skipped."""

    def test_missing_handler_skipped(self, executor, classification):
        pipeline = StagePipelineDefinition(
            stages=["analyze", "nonexistent", "quantify"],
            output_mode="direct",
        )
        result = executor.execute(
            pipeline=pipeline,
            classification=classification,
            initial_context={},
            prompt="test",
        )
        assert result.skipped_stages == ["nonexistent"]
        assert result.completed_stages == ["analyze", "quantify"]
        assert result.all_completed  # skipped counts as "completed" for pipeline


class TestFailedStages:
    """Failed stages stop the pipeline."""

    def test_failure_stops_pipeline(self, executor, classification):
        pipeline = StagePipelineDefinition(
            stages=["analyze", "fail", "quantify"],
            output_mode="direct",
        )
        result = executor.execute(
            pipeline=pipeline,
            classification=classification,
            initial_context={},
            prompt="test",
        )
        assert result.completed_stages == ["analyze"]
        assert not result.all_completed
        # quantify should be skipped due to failure
        gate_statuses = {g.stage_name: g.status for g in result.gates}
        assert gate_statuses["fail"] == "rejected"
        assert gate_statuses["quantify"] == "skipped"


class TestExecutionResult:
    """StageExecutionResult metadata."""

    def test_total_time_positive(self, executor, classification):
        pipeline = StagePipelineDefinition(stages=["analyze"], output_mode="direct")
        result = executor.execute(
            pipeline=pipeline,
            classification=classification,
            initial_context={},
            prompt="test",
        )
        assert result.total_time_ms >= 0.0

    def test_to_dict(self, executor, classification):
        pipeline = StagePipelineDefinition(stages=["analyze"], output_mode="direct")
        result = executor.execute(
            pipeline=pipeline,
            classification=classification,
            initial_context={},
            prompt="test",
        )
        d = result.to_dict()
        assert "gates" in d
        assert "output" in d
        assert d["output_mode"] == "direct"

    def test_output_mode_preserved(self, executor, classification):
        pipeline = StagePipelineDefinition(stages=["analyze"], output_mode="staged")
        result = executor.execute(
            pipeline=pipeline,
            classification=classification,
            initial_context={},
            prompt="test",
        )
        assert result.output_mode == "staged"


class TestRegistration:
    def test_has_handler(self, executor):
        assert executor.has_handler("analyze")
        assert not executor.has_handler("nonexistent")

    def test_registered_stages(self, executor):
        stages = executor.registered_stages
        assert "analyze" in stages
        assert "quantify" in stages


class TestEmptyPipeline:
    def test_empty_stages(self, executor, classification):
        pipeline = StagePipelineDefinition(stages=[], output_mode="direct")
        result = executor.execute(
            pipeline=pipeline,
            classification=classification,
            initial_context={"x": 1},
            prompt="test",
        )
        assert result.all_completed
        assert result.output == {"x": 1}
        assert result.gates == []

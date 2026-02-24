"""Tests for agent trace capture in MockAgentProvider."""

from __future__ import annotations

from cad_dxf_agent.core.dxf_reader import load_dxf
from cad_dxf_agent.core.semantic_model import build_planner_context
from cad_dxf_agent.llm.agent_provider import MockAgentProvider
from cad_dxf_agent.models.trace_schema import PlannerTrace


class TestMockAgentTrace:
    def test_move_prompt_has_trace(self, sample_dxf):
        """MockAgentProvider attaches a PlannerTrace on move prompts."""
        ctx = load_dxf(sample_dxf)
        planner_ctx = build_planner_context(ctx)
        provider = MockAgentProvider()
        changeset = provider.plan("move this column", planner_ctx)

        assert changeset.planner_trace is not None
        trace = changeset.planner_trace
        assert isinstance(trace, PlannerTrace)
        assert trace.provider_name == "mock-agent"
        assert trace.total_turns >= 1
        assert trace.total_duration_ms >= 0.0
        assert not trace.deterministic

    def test_move_prompt_has_two_turns(self, sample_dxf):
        """Move prompt should produce 2 turns: find + move."""
        ctx = load_dxf(sample_dxf)
        planner_ctx = build_planner_context(ctx)
        provider = MockAgentProvider()
        changeset = provider.plan("move this column", planner_ctx)
        trace = changeset.planner_trace

        assert trace.total_turns == 2
        assert len(trace.turns) == 2
        assert trace.turns[0].tool_calls[0].name == "find_entities"
        assert trace.turns[1].tool_calls[0].name == "move_entity"

    def test_delete_prompt_has_trace(self, sample_dxf):
        """Delete prompt attaches a single-turn trace."""
        ctx = load_dxf(sample_dxf)
        planner_ctx = build_planner_context(ctx)
        provider = MockAgentProvider()
        changeset = provider.plan("delete this element", planner_ctx)
        trace = changeset.planner_trace

        assert trace is not None
        assert trace.total_turns == 1
        assert trace.turns[0].tool_calls[0].name == "delete_entity"

    def test_text_prompt_has_trace(self, sample_dxf):
        """Text prompt attaches a single-turn trace."""
        ctx = load_dxf(sample_dxf)
        planner_ctx = build_planner_context(ctx)
        provider = MockAgentProvider()
        changeset = provider.plan("change text label", planner_ctx)
        trace = changeset.planner_trace

        assert trace is not None
        assert trace.total_turns == 1
        assert trace.turns[0].tool_calls[0].name == "edit_text"

    def test_tool_call_durations_positive(self, sample_dxf):
        """All tool call durations should be non-negative."""
        ctx = load_dxf(sample_dxf)
        planner_ctx = build_planner_context(ctx)
        provider = MockAgentProvider()
        changeset = provider.plan("move this column", planner_ctx)
        trace = changeset.planner_trace

        for turn in trace.turns:
            assert turn.duration_ms >= 0.0
            for tc in turn.tool_calls:
                assert tc.duration_ms >= 0.0

    def test_tool_call_args_captured(self, sample_dxf):
        """Tool call arguments should be captured in the trace."""
        ctx = load_dxf(sample_dxf)
        planner_ctx = build_planner_context(ctx)
        provider = MockAgentProvider()
        changeset = provider.plan("move this column", planner_ctx)
        trace = changeset.planner_trace

        # Turn 1: find_entities with layer arg
        find_call = trace.turns[0].tool_calls[0]
        assert "layer" in find_call.args

        # Turn 2: move_entity with handle, dx, dy
        move_call = trace.turns[1].tool_calls[0]
        assert "handle" in move_call.args
        assert "dx" in move_call.args

    def test_tool_call_results_captured(self, sample_dxf):
        """Tool call results should be captured in the trace."""
        ctx = load_dxf(sample_dxf)
        planner_ctx = build_planner_context(ctx)
        provider = MockAgentProvider()
        changeset = provider.plan("move this column", planner_ctx)
        trace = changeset.planner_trace

        for turn in trace.turns:
            for tc in turn.tool_calls:
                assert isinstance(tc.result, dict)

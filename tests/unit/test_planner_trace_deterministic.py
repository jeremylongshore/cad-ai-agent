"""Tests for deterministic planner trace attachment."""

from __future__ import annotations

from cad_dxf_agent.core.dxf_reader import load_dxf
from cad_dxf_agent.core.semantic_model import build_planner_context
from cad_dxf_agent.llm.agent_provider import MockAgentProvider
from cad_dxf_agent.llm.planner import run_planner
from cad_dxf_agent.models.trace_schema import PlannerTrace


class TestDeterministicPlannerTrace:
    def _get_context_with_handle(self, sample_dxf):
        """Load DXF and return (planner_context, first_handle)."""
        ctx = load_dxf(sample_dxf)
        planner_ctx = build_planner_context(ctx)
        # Find first entity handle from the context
        handle = planner_ctx["entities"][0]["handle"]
        return planner_ctx, handle

    def test_deterministic_delete_has_trace(self, sample_dxf):
        """Deterministic delete attaches a trace with deterministic=True."""
        planner_ctx, handle = self._get_context_with_handle(sample_dxf)
        prompt = f"delete entity {handle}"
        changeset = run_planner(prompt, planner_ctx)

        assert changeset.planner_trace is not None
        trace = changeset.planner_trace
        assert isinstance(trace, PlannerTrace)
        assert trace.deterministic is True
        assert trace.provider_name == "deterministic"
        assert trace.total_turns == 0
        assert trace.total_duration_ms == 0.0
        assert trace.turns == []

    def test_deterministic_move_has_trace(self, sample_dxf):
        """Deterministic move attaches a trace with deterministic=True."""
        planner_ctx, handle = self._get_context_with_handle(sample_dxf)
        prompt = f"move {handle} by (10.0, 5.0)"
        changeset = run_planner(prompt, planner_ctx)

        trace = changeset.planner_trace
        assert trace is not None
        assert trace.deterministic is True

    def test_deterministic_edit_text_has_trace(self, sample_dxf):
        """Deterministic edit_text attaches a trace with deterministic=True."""
        planner_ctx, handle = self._get_context_with_handle(sample_dxf)
        prompt = f"change text of {handle} to 'NEW LABEL'"
        changeset = run_planner(prompt, planner_ctx)

        trace = changeset.planner_trace
        assert trace is not None
        assert trace.deterministic is True

    def test_non_deterministic_via_mock_agent_has_trace(self, sample_dxf):
        """Non-deterministic prompts via MockAgentProvider still attach a trace."""
        ctx = load_dxf(sample_dxf)
        planner_ctx = build_planner_context(ctx)
        provider = MockAgentProvider()
        changeset = provider.plan("move this column", planner_ctx)

        trace = changeset.planner_trace
        assert trace is not None
        assert trace.deterministic is False
        assert trace.provider_name == "mock-agent"

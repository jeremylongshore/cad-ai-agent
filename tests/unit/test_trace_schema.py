"""Tests for the PlannerTrace data model."""

from __future__ import annotations

from cad_dxf_agent.models.trace_schema import AgentTurn, PlannerTrace, ToolCall


class TestToolCall:
    def test_construct_minimal(self):
        tc = ToolCall(name="find_entities")
        assert tc.name == "find_entities"
        assert tc.args == {}
        assert tc.result == {}
        assert tc.duration_ms == 0.0

    def test_construct_full(self):
        tc = ToolCall(
            name="move_entity",
            args={"handle": "A1", "dx": 24.0, "dy": 0.0},
            result={"status": "queued"},
            duration_ms=1.5,
        )
        assert tc.name == "move_entity"
        assert tc.args["handle"] == "A1"
        assert tc.result["status"] == "queued"
        assert tc.duration_ms == 1.5


class TestAgentTurn:
    def test_construct_empty(self):
        turn = AgentTurn(turn_number=1)
        assert turn.turn_number == 1
        assert turn.tool_calls == []
        assert turn.duration_ms == 0.0

    def test_construct_with_calls(self):
        tc = ToolCall(name="find_entities", duration_ms=3.2)
        turn = AgentTurn(turn_number=1, tool_calls=[tc], duration_ms=245.3)
        assert len(turn.tool_calls) == 1
        assert turn.tool_calls[0].name == "find_entities"
        assert turn.duration_ms == 245.3


class TestPlannerTrace:
    def test_construct_defaults(self):
        trace = PlannerTrace()
        assert trace.provider_name == ""
        assert trace.total_turns == 0
        assert trace.total_duration_ms == 0.0
        assert trace.turns == []
        assert trace.deterministic is False

    def test_construct_deterministic(self):
        trace = PlannerTrace(
            provider_name="deterministic",
            deterministic=True,
        )
        assert trace.deterministic is True
        assert trace.total_turns == 0

    def test_construct_full(self):
        tc1 = ToolCall(name="find_entities", args={"layer": "STRUCTURAL"}, duration_ms=3.0)
        tc2 = ToolCall(name="move_entity", args={"handle": "A1"}, duration_ms=0.5)
        turn1 = AgentTurn(turn_number=1, tool_calls=[tc1], duration_ms=200.0)
        turn2 = AgentTurn(turn_number=2, tool_calls=[tc2], duration_ms=100.0)

        trace = PlannerTrace(
            provider_name="agent (gemini-2.5-flash)",
            total_turns=2,
            total_duration_ms=300.0,
            turns=[turn1, turn2],
        )
        assert trace.total_turns == 2
        assert len(trace.turns) == 2
        assert trace.turns[0].tool_calls[0].name == "find_entities"
        assert trace.turns[1].tool_calls[0].name == "move_entity"

    def test_serialization_roundtrip(self):
        """PlannerTrace should serialize and deserialize cleanly."""
        tc = ToolCall(name="test", args={"x": 1}, result={"ok": True}, duration_ms=1.0)
        turn = AgentTurn(turn_number=1, tool_calls=[tc], duration_ms=10.0)
        trace = PlannerTrace(
            provider_name="test-provider",
            total_turns=1,
            total_duration_ms=10.0,
            turns=[turn],
        )
        data = trace.model_dump()
        restored = PlannerTrace.model_validate(data)
        assert restored.provider_name == "test-provider"
        assert restored.turns[0].tool_calls[0].name == "test"

"""Planner trace schema — structured record of agent turn-by-turn behavior.

Captures tool calls, timings, and results for each agent turn so the
UI can display what the LLM did and how long each step took.
"""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field


class ToolCall(BaseModel):
    """A single tool invocation within an agent turn."""

    name: str
    args: dict[str, Any] = Field(default_factory=dict)
    result: dict[str, Any] = Field(default_factory=dict)
    duration_ms: float = 0.0


class AgentTurn(BaseModel):
    """One full agent turn: LLM response + tool executions."""

    turn_number: int
    tool_calls: list[ToolCall] = Field(default_factory=list)
    duration_ms: float = 0.0


class PlannerTrace(BaseModel):
    """Complete trace of a planner invocation."""

    provider_name: str = ""
    total_turns: int = 0
    total_duration_ms: float = 0.0
    turns: list[AgentTurn] = Field(default_factory=list)
    deterministic: bool = False

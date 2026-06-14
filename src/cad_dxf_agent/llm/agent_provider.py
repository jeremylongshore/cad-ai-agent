"""Mock agent provider — simulates the tool-use loop without a real LLM.

The former Vertex AI ``AgentProvider`` was removed along with the bundled Gemini
providers. The real agent backend is now bring-your-own: implement
``PlannerProvider`` (see ``llm/providers.py``) and drive the tool loop via
``ToolExecutor``. ``MockAgentProvider`` keeps the loop exercisable offline and in
tests.
"""

from __future__ import annotations

import time

from ..models.ops_schema import ChangeSet
from ..models.trace_schema import AgentTurn, PlannerTrace, ToolCall
from ..settings import settings
from .providers import PlannerProvider
from .tool_executor import ToolExecutor


class MockAgentProvider(PlannerProvider):
    """Mock agent provider for testing the tool-use flow without a real LLM.

    Simulates a two-turn agent: first searches for an entity, then
    performs the requested edit operation.
    """

    @property
    def name(self) -> str:
        return "mock-agent"

    @property
    def requires_api_key(self) -> bool:
        return False

    def plan(
        self,
        prompt: str,
        drawing_context: dict,
        conversation_history: list[dict] | None = None,
    ) -> ChangeSet:
        """Simulate agent tool-use with deterministic tool calls."""
        from ..models.cad_schema import (
            DrawingContext,
            EntityRef,
            EntityType,
            LayerRule,
            Point2D,
        )

        # Reconstruct context for executor
        entities = []
        for e in drawing_context.get("entities", []):
            try:
                point = None
                if e.get("insert_point"):
                    point = Point2D(x=e["insert_point"]["x"], y=e["insert_point"]["y"])
                entities.append(
                    EntityRef(
                        handle=e["handle"],
                        entity_type=EntityType(e["type"]),
                        layer=e["layer"],
                        insert_point=point,
                        text_content=e.get("text"),
                        block_name=e.get("block_name"),
                    )
                )
            except (KeyError, ValueError):
                continue

        layers = [
            LayerRule(name=lyr["name"], protected=lyr.get("protected", False))
            for lyr in drawing_context.get("layers", [])
        ]

        context = DrawingContext(
            file_path=drawing_context.get("file_path", ""),
            entities=entities,
            layers=layers,
            blocks=drawing_context.get("blocks", []),
        )

        executor = ToolExecutor(context, settings.protected_layers)
        prompt_lower = prompt.lower()
        trace_turns: list[AgentTurn] = []
        loop_t0 = time.monotonic()

        def _traced_execute(tool_name: str, tool_args: dict) -> ToolCall:
            """Execute a tool and return a ToolCall with timing."""
            tc_t0 = time.monotonic()
            result = executor.execute(tool_name, tool_args)
            tc_ms = (time.monotonic() - tc_t0) * 1000
            return ToolCall(
                name=tool_name,
                args=tool_args,
                result=result if isinstance(result, dict) else {"value": result},
                duration_ms=tc_ms,
            )

        # Turn 1: Search for entities
        if "move" in prompt_lower:
            turn_t0 = time.monotonic()
            tc = _traced_execute("find_entities", {"layer": "STRUCTURAL"})
            trace_turns.append(
                AgentTurn(
                    turn_number=1,
                    tool_calls=[tc],
                    duration_ms=(time.monotonic() - turn_t0) * 1000,
                )
            )
            # Turn 2: Move first editable entity
            for e in drawing_context.get("entities", []):
                protected = {
                    lyr["name"].upper()
                    for lyr in drawing_context.get("layers", [])
                    if lyr.get("protected")
                }
                if e.get("layer", "").upper() not in protected:
                    turn_t0 = time.monotonic()
                    tc = _traced_execute(
                        "move_entity",
                        {"handle": e["handle"], "dx": 24.0, "dy": 0.0},
                    )
                    trace_turns.append(
                        AgentTurn(
                            turn_number=2,
                            tool_calls=[tc],
                            duration_ms=(time.monotonic() - turn_t0) * 1000,
                        )
                    )
                    break

        elif "delete" in prompt_lower or "remove" in prompt_lower:
            for e in drawing_context.get("entities", []):
                protected = {
                    lyr["name"].upper()
                    for lyr in drawing_context.get("layers", [])
                    if lyr.get("protected")
                }
                if e.get("layer", "").upper() not in protected:
                    turn_t0 = time.monotonic()
                    tc = _traced_execute("delete_entity", {"handle": e["handle"]})
                    trace_turns.append(
                        AgentTurn(
                            turn_number=1,
                            tool_calls=[tc],
                            duration_ms=(time.monotonic() - turn_t0) * 1000,
                        )
                    )
                    break

        elif "text" in prompt_lower or "label" in prompt_lower:
            for e in drawing_context.get("entities", []):
                if e.get("type") in ("TEXT", "MTEXT") and e.get("text"):
                    turn_t0 = time.monotonic()
                    tc = _traced_execute(
                        "edit_text",
                        {"handle": e["handle"], "new_text": "UPDATED BY CAD-DXF-AGENT"},
                    )
                    trace_turns.append(
                        AgentTurn(
                            turn_number=1,
                            tool_calls=[tc],
                            duration_ms=(time.monotonic() - turn_t0) * 1000,
                        )
                    )
                    break

        else:
            # Default: move first editable entity
            for e in drawing_context.get("entities", []):
                protected = {
                    lyr["name"].upper()
                    for lyr in drawing_context.get("layers", [])
                    if lyr.get("protected")
                }
                if e.get("layer", "").upper() not in protected:
                    turn_t0 = time.monotonic()
                    tc = _traced_execute(
                        "move_entity",
                        {"handle": e["handle"], "dx": 12.0, "dy": 12.0},
                    )
                    trace_turns.append(
                        AgentTurn(
                            turn_number=1,
                            tool_calls=[tc],
                            duration_ms=(time.monotonic() - turn_t0) * 1000,
                        )
                    )
                    break

        total_ms = (time.monotonic() - loop_t0) * 1000
        trace = PlannerTrace(
            provider_name=self.name,
            total_turns=len(trace_turns),
            total_duration_ms=total_ms,
            turns=trace_turns,
        )

        changeset = ChangeSet(
            prompt=prompt,
            operations=executor.operations,
            revision_label=f"Mock agent edit: {prompt[:50]}",
        )
        changeset.planner_trace = trace
        return changeset

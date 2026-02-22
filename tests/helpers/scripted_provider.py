"""Scripted agent provider — replays canned tool-call sequences through the real ToolExecutor.

Industry 'fake backend' pattern: tests declare exactly what tools the 'LLM' calls,
the real executor validates protection rules, builds ops. Better than MagicMock
because it tests actual behavior.
"""

from __future__ import annotations

from cad_dxf_agent.llm.providers import PlannerProvider
from cad_dxf_agent.llm.tool_executor import ToolExecutor
from cad_dxf_agent.models.cad_schema import (
    DrawingContext,
    EntityRef,
    EntityType,
    LayerRule,
    Point2D,
)
from cad_dxf_agent.models.ops_schema import ChangeSet
from cad_dxf_agent.settings import settings


class ScriptedAgentProvider(PlannerProvider):
    """Replays a scripted sequence of tool calls through the real ToolExecutor.

    Args:
        turns: List of turns, where each turn is a list of (tool_name, args) tuples.
               Example: [
                   [("find_entities", {"layer": "STRUCTURAL"})],
                   [("move_entity", {"handle": "ABC", "dx": 24.0, "dy": 0.0})],
               ]
    """

    def __init__(self, turns: list[list[tuple[str, dict]]]) -> None:
        self._turns = turns

    @property
    def name(self) -> str:
        return "scripted-agent"

    @property
    def requires_api_key(self) -> bool:
        return False

    def plan(self, prompt: str, drawing_context: dict) -> ChangeSet:
        """Execute scripted tool calls through the real ToolExecutor."""
        context = _reconstruct_context(drawing_context)
        executor = ToolExecutor(context, settings.protected_layers)

        results: list[dict] = []
        for turn in self._turns:
            for tool_name, args in turn:
                try:
                    result = executor.execute(tool_name, args)
                except KeyError:
                    result = {"error": f"Unknown tool: {tool_name}"}
                results.append(result)

        return ChangeSet(
            prompt=prompt,
            operations=executor.operations,
            revision_label=f"Scripted agent: {prompt[:50]}",
        )


def _reconstruct_context(drawing_context: dict) -> DrawingContext:
    """Reconstruct a DrawingContext from planner context dict."""
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
        except (KeyError, ValueError) as exc:
            import logging

            logging.getLogger(__name__).warning(
                "Skipping malformed entity in test context: %s (data=%s)", exc, e
            )
            continue

    layers = [
        LayerRule(name=lyr["name"], protected=lyr.get("protected", False))
        for lyr in drawing_context.get("layers", [])
    ]

    return DrawingContext(
        file_path=drawing_context.get("file_path", ""),
        entities=entities,
        layers=layers,
        blocks=drawing_context.get("blocks", []),
    )

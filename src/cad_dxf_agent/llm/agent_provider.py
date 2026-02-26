"""Agent provider — tool-use loop for Gemini function calling.

Replaces the one-shot GeminiProvider with an iterative agent that:
  1. Sends the user prompt + drawing context + tool definitions to Gemini
  2. Gemini returns function calls (find_entities, move_entity, etc.)
  3. Host executes each call via ToolExecutor
  4. Results sent back to Gemini for the next turn
  5. Repeats until Gemini stops calling tools
  6. Accumulated EditOperations are returned as a ChangeSet

The LLM never touches DXF — it only calls tools.
"""

from __future__ import annotations

import logging
import time
from pathlib import Path
from typing import Any

from ..models.ops_schema import ChangeSet
from ..models.trace_schema import AgentTurn, PlannerTrace, ToolCall
from ..otel import get_tracer
from ..settings import settings
from .prompt_templates import AGENT_SYSTEM_PROMPT
from .providers import PlannerProvider
from .tool_definitions import ALL_TOOLS
from .tool_executor import ToolExecutor
from .vision_describer import describe_drawing

logger = logging.getLogger(__name__)
tracer = get_tracer(__name__)

# Safety limit on agent turns to prevent infinite loops
MAX_AGENT_TURNS = 10


class AgentProvider(PlannerProvider):
    """Gemini tool-use agent for CAD editing.

    Uses Gemini function calling to iteratively query and edit the
    drawing. More reliable than one-shot JSON generation because the
    LLM can search for entities before acting on them.
    """

    def __init__(
        self,
        project: str | None = None,
        location: str | None = None,
        model_name: str | None = None,
        image_path: str | Path | None = None,
    ) -> None:
        self._project = project or settings.gcp_project
        self._location = location or settings.gcp_location
        self._model_name = model_name or settings.gemini_model
        self._image_path = image_path
        self._model: Any = None  # lazy init

    @property
    def name(self) -> str:
        return f"agent ({self._model_name})"

    @property
    def requires_api_key(self) -> bool:
        return False  # Uses GCP credentials

    def plan(
        self,
        prompt: str,
        drawing_context: dict,
        conversation_history: list[dict] | None = None,
    ) -> ChangeSet:
        """Run the tool-use agent loop to produce a ChangeSet."""
        with tracer.start_as_current_span("cad.agent_plan") as span:
            span.set_attribute("cad.agent.model", self._model_name)

            context = self._reconstruct_context(drawing_context)
            executor = ToolExecutor(context, settings.protected_layers)

            # Build initial prompt with vision description if available
            initial_prompt = self._build_initial_prompt(prompt, drawing_context)

            # Run the agent loop
            model = self._get_model()
            chat_history = self._build_chat_history(conversation_history)
            chat = model.start_chat(history=chat_history)

            # Per-turn timeout: total timeout / max turns
            per_turn_timeout = max(settings.planner_timeout // MAX_AGENT_TURNS, 5)

            # Send initial message
            response = chat.send_message(initial_prompt)
            turns = 0
            trace_turns: list[AgentTurn] = []
            loop_t0 = time.monotonic()

            while turns < MAX_AGENT_TURNS:
                # Check if Gemini wants to call tools
                function_calls = _extract_function_calls(response)
                text_parts = _extract_text(response)

                # Fail-fast: no tool calls AND no text → abort
                if not function_calls and not text_parts:
                    logger.warning("Agent returned empty response on turn %d, aborting", turns)
                    break

                if not function_calls:
                    # No more tool calls — agent is done
                    break

                turns += 1
                turn_t0 = time.monotonic()
                span.add_event(
                    f"agent_turn_{turns}",
                    {
                        "tool_count": len(function_calls),
                    },
                )

                # Execute each tool call and collect results
                tool_results = []
                traced_calls: list[ToolCall] = []
                for fc in function_calls:
                    tool_name = fc["name"]
                    tool_args = fc["args"]
                    logger.info("Agent tool call [%d]: %s(%s)", turns, tool_name, tool_args)

                    tc_t0 = time.monotonic()
                    try:
                        result = executor.execute(tool_name, tool_args)
                    except KeyError:
                        result = {"error": f"Unknown tool: {tool_name}"}
                    except Exception as e:
                        result = {"error": f"Tool execution failed: {e}"}
                    tc_ms = (time.monotonic() - tc_t0) * 1000

                    traced_calls.append(
                        ToolCall(
                            name=tool_name,
                            args=tool_args,
                            result=result if isinstance(result, dict) else {"value": result},
                            duration_ms=tc_ms,
                        )
                    )
                    tool_results.append(
                        {
                            "name": tool_name,
                            "response": result,
                        }
                    )

                # Send results back to Gemini with per-turn timeout
                from concurrent.futures import ThreadPoolExecutor
                from concurrent.futures import TimeoutError as FuturesTimeoutError

                from .errors import PlannerTimeoutError

                with ThreadPoolExecutor(max_workers=1) as pool:
                    future = pool.submit(self._send_tool_results, chat, tool_results)
                    try:
                        response = future.result(timeout=per_turn_timeout)
                    except FuturesTimeoutError as exc:
                        raise PlannerTimeoutError(
                            per_turn_timeout,
                            f"Agent turn {turns} timed out after {per_turn_timeout}s",
                        ) from exc

                turn_ms = (time.monotonic() - turn_t0) * 1000
                trace_turns.append(
                    AgentTurn(
                        turn_number=turns,
                        tool_calls=traced_calls,
                        duration_ms=turn_ms,
                    )
                )

            total_ms = (time.monotonic() - loop_t0) * 1000
            span.set_attribute("cad.agent.turns", turns)
            span.set_attribute("cad.agent.ops_count", len(executor.operations))

            ops = executor.operations
            logger.info(
                "Agent completed in %d turns, produced %d operations",
                turns,
                len(ops),
            )

            trace = PlannerTrace(
                provider_name=self.name,
                total_turns=turns,
                total_duration_ms=total_ms,
                turns=trace_turns,
            )

            changeset = ChangeSet(
                prompt=prompt,
                operations=ops,
                revision_label=f"Agent edit ({turns} turns): {prompt[:50]}",
            )
            changeset.planner_trace = trace
            return changeset

    def _get_model(self):
        """Lazy-initialize the Gemini model with tool declarations and GenerationConfig."""
        if self._model is None:
            try:
                import vertexai
                from vertexai.generative_models import (
                    FunctionDeclaration,
                    GenerationConfig,
                    GenerativeModel,
                    Tool,
                )

                vertexai.init(
                    project=self._project,
                    location=self._location,
                )

                # Convert tool dicts to FunctionDeclaration objects
                declarations = []
                for tool_def in ALL_TOOLS:
                    declarations.append(
                        FunctionDeclaration(
                            name=str(tool_def["name"]),
                            description=str(tool_def["description"]),
                            parameters=dict(tool_def["parameters"]),  # type: ignore[arg-type]
                        )
                    )
                tools = [Tool(function_declarations=declarations)]

                gen_config = GenerationConfig(
                    temperature=settings.llm_temperature,
                    top_p=settings.llm_top_p,
                    top_k=settings.llm_top_k,
                    max_output_tokens=settings.llm_max_output_tokens,
                )

                self._model = GenerativeModel(
                    self._model_name,
                    system_instruction=AGENT_SYSTEM_PROMPT,
                    tools=tools,
                    generation_config=gen_config,
                )
            except ImportError as err:
                raise ImportError(
                    "google-cloud-aiplatform not installed. "
                    "Install with: pip install google-cloud-aiplatform"
                ) from err

        return self._model

    @staticmethod
    def _build_chat_history(conversation_history: list[dict] | None) -> list:
        """Convert conversation_history dicts to Vertex AI Content objects."""
        if not conversation_history:
            return []
        from vertexai.generative_models import Content, Part

        return [
            Content(
                role="user" if entry.get("role") == "user" else "model",
                parts=[Part.from_text(entry.get("text", ""))],
            )
            for entry in conversation_history
        ]

    def _build_initial_prompt(self, prompt: str, drawing_context: dict) -> str:
        """Build the initial message with compact context and optional vision.

        Uses a summary instead of full entity JSON to keep the prompt small.
        The agent discovers specific entities via query tools.
        """
        parts = []

        # Vision description (Stage 1)
        if self._image_path:
            try:
                description = describe_drawing(self._image_path)
                parts.append(f"DRAWING VISUAL DESCRIPTION:\n{description}\n")
            except Exception as e:
                logger.warning("Vision description failed, continuing without: %s", e)

        # Compact context summary (not full entity JSON)
        compact = self._build_compact_summary(drawing_context)
        parts.append(compact)

        # User prompt
        parts.append(f"USER REQUEST:\n{prompt}")

        return "\n".join(parts)

    @staticmethod
    def _build_compact_summary(drawing_context: dict) -> str:
        """Build a compact text summary from the planner context dict."""
        from collections import Counter
        from pathlib import Path

        entities = drawing_context.get("entities", [])
        layers = drawing_context.get("layers", [])
        blocks = drawing_context.get("blocks", [])
        file_path = drawing_context.get("file_path", "unknown")

        counts_by_layer: Counter[str] = Counter()
        counts_by_type: Counter[str] = Counter()
        text_labels: list[str] = []

        for e in entities:
            counts_by_layer[e.get("layer", "")] += 1
            counts_by_type[e.get("type", "")] += 1
            if e.get("text"):
                text_labels.append(e["text"])

        protected = [lyr["name"] for lyr in layers if lyr.get("protected")]

        lines = [
            "DRAWING SUMMARY:",
            f"- File: {Path(file_path).name}",
            f"- Total entities: {len(entities)}",
            f"- Entity types: {', '.join(f'{t}({n})' for t, n in counts_by_type.most_common())}",
            "- Layers:",
        ]

        for lyr in layers:
            count = counts_by_layer.get(lyr["name"], 0)
            prot = " (PROTECTED)" if lyr["name"] in protected else ""
            lines.append(f"    {lyr['name']}: {count} entities{prot}")

        if blocks:
            lines.append(f"- Blocks available: {', '.join(blocks)}")

        if text_labels:
            sample = text_labels[:5]
            lines.append(f"- Sample text labels: {sample}")

        lines.append("")
        lines.append(
            "Use find_entities(), get_entity(), find_nearest() to query specific entities."
        )
        lines.append("Do NOT guess entity handles — always search first.")

        return "\n".join(lines)

    def _send_tool_results(self, chat, tool_results: list[dict]) -> Any:
        """Send tool execution results back to Gemini."""
        from vertexai.generative_models import Content, Part

        parts = []
        for tr in tool_results:
            part = Part.from_function_response(
                name=tr["name"],
                response=tr["response"],
            )
            parts.append(part)

        return chat.send_message(Content(role="function", parts=parts))

    def _reconstruct_context(self, drawing_context: dict) -> Any:
        """Reconstruct a DrawingContext from the planner context dict.

        The planner receives a simplified dict from semantic_model.
        We reconstruct enough of a DrawingContext to feed the EntityIndex.
        """
        from ..models.cad_schema import (
            DrawingContext,
            EntityRef,
            EntityType,
            LayerRule,
            Point2D,
        )

        entities = []
        for e in drawing_context.get("entities", []):
            try:
                point = None
                if e.get("insert_point"):
                    point = Point2D(
                        x=e["insert_point"]["x"],
                        y=e["insert_point"]["y"],
                    )
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
                logger.warning("Skipping malformed entity: %s", exc)

        layers = []
        for lyr in drawing_context.get("layers", []):
            layers.append(
                LayerRule(
                    name=lyr["name"],
                    protected=lyr.get("protected", False),
                )
            )

        return DrawingContext(
            file_path=drawing_context.get("file_path", ""),
            entities=entities,
            layers=layers,
            blocks=drawing_context.get("blocks", []),
        )


class MockAgentProvider(PlannerProvider):
    """Mock agent provider for testing the tool-use flow without Gemini.

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


def _extract_function_calls(response) -> list[dict[str, Any]]:
    """Extract function call name/args pairs from a Gemini response."""
    calls = []
    try:
        for candidate in response.candidates:
            for part in candidate.content.parts:
                if hasattr(part, "function_call") and part.function_call:
                    fc = part.function_call
                    calls.append(
                        {
                            "name": fc.name,
                            "args": dict(fc.args) if fc.args else {},
                        }
                    )
    except (AttributeError, TypeError):
        pass
    return calls


def _extract_text(response) -> list[str]:
    """Extract text parts from a Gemini response (for fail-fast detection)."""
    texts = []
    try:
        for candidate in response.candidates:
            for part in candidate.content.parts:
                if hasattr(part, "text") and part.text:
                    texts.append(part.text)
    except (AttributeError, TypeError):
        pass
    return texts
